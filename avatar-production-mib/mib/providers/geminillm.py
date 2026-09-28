"""mib/providers/geminillm.py — Gemini as the script writer.

The user picks "gemini" in Settings → Script: Gemini writes the
competitor-level script (following the channel's pattern, never copying),
then Claude reviews it. Uses the SAME gemini key pool as images
(op="script" in the usage report).

Model: configurable, default gemini-2.5-flash (text). Raises LLMError;
pool-aware subclasses trigger key rotation.
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


DEFAULT_MODEL = "gemini-2.5-flash"


def _raise_for_status(resp):
    if resp.status_code == 429:
        raise LLMExhausted(
            "Gemini LLM rate limit / quota hit — trying next key.")
    if resp.status_code in (401, 403):
        raise LLMRejected(
            f"Gemini LLM refused this key (HTTP {resp.status_code}) — "
            "trying next key.")


def build_prompt(title, target_minutes, channel_name="", pattern_notes=""):
    words = max(60, int(target_minutes or 5) * 140)
    pat = (f" Follow this channel pattern closely: {pattern_notes}"
           if pattern_notes else "")
    ch = f" for the channel '{channel_name}'" if channel_name else ""
    return (
        f'You are a top YouTube scriptwriter. Write a COMPETITOR-LEVEL '
        f'narration script{ch} titled "{title}" — original writing only, '
        f'never copy any existing video.{pat} '
        f'Total ~{words} words of SPOKEN narration only (no headers, no '
        'stage directions, no bracketed cues). Return JSON ONLY: '
        '{"hook": "...", "beats": [{"name": "...", "narration": "...", '
        '"image_prompt": "..."}], "cta": "..."}. '
        'Rules: hook = curiosity + emotion, <=40 words, first line must '
        'stop the scroll. beats = exactly 6 with arc problem → complication '
        '→ setback → twist → payoff → landing; each beat 1-2 short '
        'paragraphs, plain vivid words, no repetition between beats. '
        'image_prompt = photorealistic cinematic 16:9 scene description, '
        'no text, no watermark, and 2 of the 6 beats should feature the '
        'channel\'s main character fully visible in the scene where it fits '
        'naturally ("include the main character" only where noted). '
        'cta = subscribe + comment ask, <=40 words, warm.'
    )


def generate(title, target_minutes, api_key, model="", channel_name="",
             pattern_notes="", timeout=180):
    """Ask Gemini for a script JSON. Returns a script dict (same shape as
    the local rules engine). Raises LLMError on any problem."""
    key = (api_key or "").strip()
    if not key:
        raise LLMError("Gemini API key is empty (Settings → API Keys).")
    model = (model or "").strip() or DEFAULT_MODEL
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    prompt = build_prompt(title, target_minutes, channel_name, pattern_notes)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "maxOutputTokens": 8000,
                                 "temperature": 0.8}}
    try:
        resp = requests.post(url, headers={"x-goog-api-key": key},
                             json=body, timeout=timeout)
    except requests.RequestException as e:
        raise LLMError(f"Gemini LLM network error: {e}"[:200]) from e
    _raise_for_status(resp)
    if resp.status_code != 200:
        raise LLMError(f"Gemini LLM HTTP {resp.status_code}: "
                       f"{resp.text[:200]}")
    try:
        cands = resp.json().get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"Unexpected Gemini LLM response: {e}"[:200]) from e
    data = _parse_script_json(text)
    from ..stages.script import sanitize, _topic, WPM
    return _finalize(title, data, sanitize, _topic, WPM, prompt, text,
                     f"gemini-llm/{model}")


def _parse_script_json(text):
    c = (text or "").strip()
    if c.startswith("```"):
        c = c.split("\n", 1)[1] if "\n" in c else c[3:]
        c = c.rsplit("```", 1)[0]
    # tolerate leading/trailing prose: find the outer { ... }
    if not c.startswith("{"):
        s, e = c.find("{"), c.rfind("}")
        if s >= 0 and e > s:
            c = c[s:e + 1]
    try:
        data = json.loads(c)
        beats = data.get("beats") or []
        assert isinstance(data.get("hook"), str) and len(beats) == 6
        return data
    except Exception as e:  # noqa: BLE001
        raise LLMError(
            f"Gemini LLM did not return valid script JSON: {e}"[:200]) \
            from e


def _finalize(title, data, sanitize, _topic, WPM, prompt, raw_text, note):
    topic = _topic(title)
    hook = sanitize(data["hook"])
    clean_beats = []
    for b in data.get("beats") or []:
        clean_beats.append({
            "name": str(b.get("name", ""))[:40] or "beat",
            "narration": sanitize(b.get("narration", "")),
            "image_prompt": str(b.get("image_prompt", ""))[:500],
        })
    cta = sanitize(data.get("cta", ""))
    words_n = len(hook.split()) + sum(
        len(b["narration"].split()) for b in clean_beats) + len(cta.split())
    try:
        costs.log_call(costs.current_job_dir(), "llm", "tokens_in",
                       max(1, len(prompt) // 4), note=note)
        costs.log_call(costs.current_job_dir(), "llm", "tokens_out",
                       max(1, len(raw_text) // 4), note=note)
    except Exception:  # noqa: BLE001
        pass
    return {"title": sanitize(title), "topic": topic, "hook": hook,
            "beats": clean_beats, "cta": cta, "words": words_n,
            "est_minutes": round(words_n / WPM, 2)}
