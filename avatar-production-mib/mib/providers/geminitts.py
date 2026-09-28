"""mib/providers/geminitts.py — Gemini TTS (free tier, no subscription needed).

Google AI Studio free tier: 1,500 requests/day, 0 cost.
This replaces Edge TTS as the default voice provider and removes the
robotic sound. The quality is close to ElevenLabs at $0.00 cost.

Voices available (Gemini 2.5 Flash TTS):
  Puck    — upbeat, energetic (good for hooks)
  Charon  — deep, authoritative (dark psychology, military, docs)
  Kore    — calm, warm female (wellness, lifestyle)
  Fenrir  — intense, dramatic (true crime, thriller)
  Aoede   — clear, friendly female (explainers, news)
  Orbit   — neutral male (general purpose)
  Zephyr  — soft, gentle (emotional stories)

Usage:
  Set GEMINI_TTS_KEY in API Keys tab (same key pool as Gemini images).
  Set voice per channel in channels YAML: audio.voice: "Charon"
"""
from pathlib import Path

import requests

from ..keypool import KeyExhausted, KeyRejected, pool_from_secrets

# All available Gemini TTS voices
VOICES = [
    {"id": "Puck",   "name": "Puck — Upbeat, energetic",     "gender": "male"},
    {"id": "Charon", "name": "Charon — Deep, authoritative",  "gender": "male"},
    {"id": "Kore",   "name": "Kore — Calm, warm",             "gender": "female"},
    {"id": "Fenrir", "name": "Fenrir — Intense, dramatic",    "gender": "male"},
    {"id": "Aoede",  "name": "Aoede — Clear, friendly",       "gender": "female"},
    {"id": "Orbit",  "name": "Orbit — Neutral, general",      "gender": "male"},
    {"id": "Zephyr", "name": "Zephyr — Soft, gentle",         "gender": "female"},
]

DEFAULT_VOICE  = "Charon"   # deep authoritative — good for most channels
DEFAULT_MALE   = "Charon"
DEFAULT_FEMALE = "Kore"

_API_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash-preview-tts:generateContent")


class GeminiTTSError(Exception):
    """Clean, UI-safe error."""


class _PoolExhausted(KeyExhausted, GeminiTTSError):
    pass


class _PoolRejected(KeyRejected, GeminiTTSError):
    pass


def _raise_for_status(resp):
    if resp.status_code == 429:
        raise _PoolExhausted("Gemini TTS rate limit — trying next key.")
    if resp.status_code in (401, 403):
        raise _PoolRejected(
            f"Gemini TTS key rejected (HTTP {resp.status_code}) — trying next key.")


def synthesize(api_key, text, voice=None, out_path=None, timeout=120):
    """Generate speech via Gemini TTS API and save to out_path.

    Args:
        api_key:  Google AI Studio API key (free tier works fine).
        text:     Narration text to synthesize.
        voice:    Voice name from VOICES list. Defaults to DEFAULT_VOICE.
        out_path: Path to write the MP3/WAV output.
        timeout:  HTTP timeout in seconds.

    Returns:
        str: path to the generated audio file.

    Raises:
        GeminiTTSError on any failure so voiceover stage can fall through.
    """
    if not api_key or not str(api_key).strip():
        raise GeminiTTSError("Gemini TTS API key is empty (Settings → API Keys).")
    text = str(text or "").strip()
    if not text:
        raise GeminiTTSError("Script text is empty — nothing to synthesize.")
    voice = (voice or DEFAULT_VOICE).strip()

    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice}
                }
            },
        },
    }

    try:
        resp = requests.post(
            _API_URL,
            headers={"x-goog-api-key": api_key.strip(),
                     "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise GeminiTTSError(f"Gemini TTS network error: {e}"[:200]) from e

    _raise_for_status(resp)

    if resp.status_code != 200:
        raise GeminiTTSError(
            f"Gemini TTS HTTP {resp.status_code}: {resp.text[:200]}")

    # Extract inline audio data from response
    try:
        import base64
        cands = resp.json().get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts") or []
        audio_b64 = ""
        mime = "audio/wav"
        for part in parts:
            inline = part.get("inlineData") or {}
            if inline.get("data"):
                audio_b64 = inline["data"]
                mime = inline.get("mimeType", "audio/wav")
                break
        if not audio_b64:
            raise GeminiTTSError("Gemini TTS returned no audio data.")
        raw = base64.b64decode(audio_b64)
    except GeminiTTSError:
        raise
    except Exception as e:  # noqa: BLE001
        raise GeminiTTSError(f"Gemini TTS parse error: {e}"[:200]) from e

    # Determine extension from mime type
    ext = ".wav" if "wav" in mime else ".mp3"
    out = str(out_path)
    if not out.endswith(ext):
        out = out.rsplit(".", 1)[0] + ext if "." in out else out + ext

    Path(out).write_bytes(raw)
    return out


def synthesize_with_pool(secrets, text, voice=None, out_path=None, timeout=120):
    """Synthesize using KeyPool rotation across multiple Gemini TTS keys.

    Automatically rotates to the next key on 429 (rate limit) or
    401/403 (rejected key). Falls through to GeminiTTSError only when
    every key in the pool is exhausted or rejected.
    """
    pool = pool_from_secrets(secrets, "gemini_tts_keys")
    last_err = None
    for key in pool:
        try:
            return synthesize(key, text, voice=voice,
                              out_path=out_path, timeout=timeout)
        except _PoolExhausted as e:
            pool.on_exhausted(key)
            last_err = e
        except _PoolRejected as e:
            pool.on_rejected(key)
            last_err = e
        except GeminiTTSError as e:
            last_err = e
            break
    raise GeminiTTSError(
        f"All Gemini TTS keys failed: {last_err}"[:300]) from last_err


def list_voices():
    """Return the static list of available Gemini TTS voices."""
    return list(VOICES)
