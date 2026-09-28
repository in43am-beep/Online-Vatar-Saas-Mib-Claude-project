"""mib/providers/scriptllm.py — optional AI33 Pro LLM scriptwriter.

Same ai33pro_api_key as voice (one entry). OpenAI-compatible
/chat/completions; user sets base_url + model in Settings (the old factory
used the same pattern). Any failure -> caller falls back to the local
rules engine. Never crashes the pipeline.
"""
import json

import requests

from .. import costs
from ..keypool import (KeyExhausted as _KeyExhausted,
                       KeyRejected as _KeyRejected)


class LLMError(Exception):
    """Clean, UI-safe error."""


class LLMExhausted(_KeyExhausted, LLMError):
    """429 / quota: the KeyPool rotates to the next key."""


class LLMRejected(_KeyRejected, LLMError):
    """401/403: the KeyPool parks this key and tries the next."""


DEFAULT_BASE_URL = "https://api.ai33.pro/v1"


def generate(title, target_minutes, api_key, base_url="", model="",
             timeout=180):
    """Ask the LLM for a script JSON. Returns a script dict (same shape as
    the local rules engine). Raises LLMError on any problem."""
    key = (api_key or "").strip()
    if not key:
        raise LLMError("AI33 Pro API key is empty.")
    base = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    model = (model or "").strip()
    if not model:
        raise LLMError("Set the LLM model in Settings → Script first.")
    words = max(60, int(target_minutes or 5) * 140)
    prompt = (
        f'Write a YouTube narration script titled "{title}". '
        f"Total ~{words} words of SPOKEN narration only (no headers, no "
        "stage directions, no bracketed cues). Return JSON ONLY with keys: "
        '{"hook": "...", "beats": [{"name": "...", "narration": "...", '
        '"image_prompt": "..."}], "cta": "..."}. '
        "hook: curiosity + emotion, <=40 words. beats: exactly 6, arc = "
        "problem, complication, setback, twist, payoff, landing. "
        "image_prompt: photorealistic cinematic 16:9, no text, no watermark. "
        "cta: subscribe + comment ask, <=40 words."
    )
    try:
        resp = requests.post(
            base + "/chat/completions",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7,
                  "max_tokens": 6000},
            timeout=timeout)
    except requests.RequestException as e:
        raise LLMError(f"LLM network error: {e}"[:200]) from e
    if resp.status_code == 429:
        raise LLMExhausted("LLM rate limit / quota hit — trying next key.")
    if resp.status_code in (401, 403):
        raise LLMRejected(f"LLM refused this key (HTTP {resp.status_code}) — "
                          "trying next key.")
    if resp.status_code != 200:
        raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"Unexpected LLM response: {e}"[:200]) from e
    # strip code fences if present
    c = content.strip()
    if c.startswith("```"):
        c = c.split("\n", 1)[1] if "\n" in c else c[3:]
        c = c.rsplit("```", 1)[0]
    try:
        data = json.loads(c)
        beats = data.get("beats") or []
        assert isinstance(data.get("hook"), str) and len(beats) == 6
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"LLM did not return valid script JSON: {e}"[:200]) \
            from e
    from ..stages.script import sanitize, _topic, WPM
    topic = _topic(title)
    hook = sanitize(data["hook"])
    clean_beats = []
    for b in beats:
        clean_beats.append({
            "name": str(b.get("name", ""))[:40] or "beat",
            "narration": sanitize(b.get("narration", "")),
            "image_prompt": str(b.get("image_prompt", ""))[:500],
        })
    cta = sanitize(data.get("cta", ""))
    words_n = len(hook.split()) + sum(
        len(b["narration"].split()) for b in clean_beats) + len(cta.split())
    try:
        usage = payload.get("usage") or {}
        tin = usage.get("prompt_tokens") or max(1, len(prompt) // 4)
        tout = usage.get("completion_tokens") or max(1, len(c) // 4)
        costs.log_call(costs.current_job_dir(), "llm", "tokens_in", tin,
                       note=f"ai33pro-llm/{model}")
        costs.log_call(costs.current_job_dir(), "llm", "tokens_out", tout,
                       note=f"ai33pro-llm/{model}")
    except Exception:  # noqa: BLE001
        pass
    return {"title": sanitize(title), "topic": topic, "hook": hook,
            "beats": clean_beats, "cta": cta, "words": words_n,
            "est_minutes": round(words_n / WPM, 2)}
