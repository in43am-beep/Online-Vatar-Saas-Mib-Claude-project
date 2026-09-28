"""mib/providers/claudereview.py — Claude script review (mistake check).

After Gemini (or any writer) produces the script, Claude reads it like a
strict editor and returns mistakes + a corrected script. Anthropic
Messages API format:

    POST {base_url}/v1/messages
    headers: x-api-key: <key>, anthropic-version: 2023-06-01

base_url and model are configurable in Settings → API Keys → Claude,
because the user's Claude access comes via a custom endpoint (Antigravity).
Keys rotate through the "claude-review" pool like every other service.

Never crashes the pipeline: any failure -> caller keeps the original
script and logs the reason.
"""
import json

import requests

from .. import costs
from ..keypool import (KeyExhausted as _KeyExhausted,
                       KeyRejected as _KeyRejected)


class ClaudeError(Exception):
    """Clean, UI-safe error."""


class ClaudeExhausted(_KeyExhausted, ClaudeError):
    """429 / quota: the KeyPool rotates to the next key."""


class ClaudeRejected(_KeyRejected, ClaudeError):
    """401/403: the KeyPool parks this key and tries the next."""


DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = ""  # user sets it — endpoint decides which models exist
API_VERSION = "2023-06-01"


def _raise_for_status(resp):
    if resp.status_code == 429:
        raise ClaudeExhausted(
            "Claude rate limit / quota hit — trying next key.")
    if resp.status_code in (401, 403):
        raise ClaudeRejected(
            f"Claude refused this key (HTTP {resp.status_code}) — "
            "trying next key.")


def build_prompt(title, script):
    hook = script.get("hook", "")
    beats_txt = "\n".join(
        f"BEAT {i + 1} [{b.get('name', '')}]: {b.get('narration', '')}"
        for i, b in enumerate(script.get("beats") or []))
    cta = script.get("cta", "")
    return (
        "You are a strict YouTube script editor. Review this narration "
        f'script titled "{title}" for mistakes ONLY — do not rewrite its '
        "style or voice. Check: (1) grammar/spelling, (2) repeated words or "
        "ideas between beats, (3) logic/timeline contradictions, "
        "(4) sentences too long for spoken narration (>25 words), "
        "(5) weak hook (no curiosity in first 2 lines), "
        "(6) CTA longer than 40 words. "
        "Return JSON ONLY: "
        '{"issues": [{"where": "beat 3", "problem": "...", '
        '"fix": "..."}], "fixed_script": '
        '{"hook": "...", "beats": [{"name": "...", "narration": "...", '
        '"image_prompt": "..."}], "cta": "..."} | null}. '
        "If there are no mistakes, issues = [] and fixed_script = null. "
        "If there ARE mistakes, fixed_script = the FULL corrected script "
        "(same 6 beats, same image_prompts unless they were wrong). "
        "Never invent new facts; only fix mistakes.\n\n"
        f"HOOK: {hook}\n{beats_txt}\nCTA: {cta}"
    )


def review(title, script, api_key, base_url="", model="", timeout=180):
    """Run the Claude review. Returns (issues, fixed_script_or_None).

    fixed_script has the same shape as the input script dict (hook, beats
    with name/narration/image_prompt, cta) or None. Raises ClaudeError on
    transport/API problems so the pool can rotate keys.
    """
    key = (api_key or "").strip()
    if not key:
        raise ClaudeError("Claude API key is empty (Settings → API Keys).")
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    model = (model or DEFAULT_MODEL).strip()
    if not model:
        raise ClaudeError("Set the Claude model in Settings → API Keys.")
    prompt = build_prompt(title, script or {})
    body = {"model": model, "max_tokens": 8000,
            "messages": [{"role": "user", "content": prompt}]}
    try:
        resp = requests.post(
            base + "/v1/messages",
            headers={"x-api-key": key, "anthropic-version": API_VERSION,
                     "Content-Type": "application/json"},
            json=body, timeout=timeout)
    except requests.RequestException as e:
        raise ClaudeError(f"Claude network error: {e}"[:200]) from e
    _raise_for_status(resp)
    if resp.status_code != 200:
        raise ClaudeError(f"Claude HTTP {resp.status_code}: "
                          f"{resp.text[:200]}")
    try:
        data = resp.json()
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks
                       if isinstance(b, dict)).strip()
    except Exception as e:  # noqa: BLE001
        raise ClaudeError(f"Unexpected Claude response: {e}"[:200]) from e
    c = text
    if c.startswith("```"):
        c = c.split("\n", 1)[1] if "\n" in c else c[3:]
        c = c.rsplit("```", 1)[0]
    if not c.startswith("{"):
        s, e = c.find("{"), c.rfind("}")
        if s >= 0 and e > s:
            c = c[s:e + 1]
    try:
        payload = json.loads(c)
        issues = payload.get("issues") or []
        fixed = payload.get("fixed_script")
        assert isinstance(issues, list)
    except Exception as e:  # noqa: BLE001
        raise ClaudeError(
            f"Claude did not return valid review JSON: {e}"[:200]) from e
    # validate the fixed script shape before trusting it
    fixed_script = None
    if isinstance(fixed, dict):
        try:
            beats = fixed.get("beats") or []
            assert isinstance(fixed.get("hook"), str) and len(beats) == 6
            fixed_script = {
                "title": script.get("title", title),
                "topic": script.get("topic", ""),
                "hook": fixed["hook"],
                "beats": [{
                    "name": str(b.get("name", ""))[:40] or "beat",
                    "narration": str(b.get("narration", "")),
                    "image_prompt": str(b.get("image_prompt", ""))[:500],
                } for b in beats],
                "cta": str(fixed.get("cta", "")),
            }
        except Exception:  # noqa: BLE001
            fixed_script = None  # malformed fix -> keep original
    try:
        usage = data.get("usage") or {}
        tin = usage.get("input_tokens") or max(1, len(prompt) // 4)
        tout = usage.get("output_tokens") or max(1, len(text) // 4)
        costs.log_call(costs.current_job_dir(), "llm", "tokens_in", tin,
                       note=f"claude-review/{model}")
        costs.log_call(costs.current_job_dir(), "llm", "tokens_out", tout,
                       note=f"claude-review/{model}")
    except Exception:  # noqa: BLE001
        pass
    return issues, fixed_script
