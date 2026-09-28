"""mib/providers/ai33voice.py — AI33 Pro voice client (https://ai33.pro).

Repackaged from the proven factory/ai33voice.py (import adjusted for the new
package) + voice-clone create/delete (POST /v3/text-to-speech/voice-clone).

Covers the v3 voice library + v3 text-to-speech (multipart FormData), task
polling, and the /v1/credits endpoint.

Auth header on every request: ``xi-api-key: <KEY>``.
The SAME key powers both the ai33pro LLM provider and this voice client —
one entry in config/secrets.yaml: ``ai33pro_api_key``. No second key field.

Voice id prefixes (= provider/model groups):
  elevenlabs_  minimax_  clone_  edge_  kokoro_  vbee_  fishaudio_
"""
import time
from pathlib import Path

import requests

from ..keypool import (KeyExhausted as _KeyExhausted,
                       KeyRejected as _KeyRejected)

from .. import costs

BASE = "https://api.ai33.pro"

PROVIDER_LABELS = {
    "elevenlabs": "ElevenLabs",
    "minimax": "MiniMax",
    "clone": "My cloned voices",
    "edge": "Edge",
    "kokoro": "Kokoro",
    "vbee": "Vbee",
    "fishaudio": "Fish Audio",
}
PROVIDERS = tuple(PROVIDER_LABELS)


class AI33Error(Exception):
    """Clean, UI-safe error (no tracebacks leak to the user)."""


class AI33Exhausted(_KeyExhausted, AI33Error):
    """429 / quota / busy: the KeyPool rotates to the next key."""


class AI33Rejected(_KeyRejected, AI33Error):
    """401/403: the KeyPool parks this key and tries the next."""


def _headers(api_key):
    if not api_key or not str(api_key).strip():
        raise AI33Error(
            "AI33 Pro API key is empty. Paste it in Settings → API keys "
            "(it also powers the Voiceover page).")
    return {"xi-api-key": str(api_key).strip()}


def _clean_error(resp):
    """Best-effort readable message from a failed HTTP response."""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = None
    if isinstance(body, dict):
        for k in ("message", "error", "msg", "detail"):
            v = body.get(k)
            if v:
                return f"{resp.status_code}: {v}"[:300]
    text = (resp.text or "").strip()
    if resp.status_code == 401:
        return "401: invalid API key or insufficient credits — check the key in Settings → API keys."
    if resp.status_code == 429:
        return "429: rate limit / queue full — wait a minute and retry."
    return f"{resp.status_code}: {text[:200]}" or f"HTTP {resp.status_code}"


def _voice_list_shape(body):
    """Accept several plausible list shapes; return the list of voices."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("data", "voices", "items", "results"):
            v = body.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):  # {"items": [...]}
                for kk in ("items", "voices", "list"):
                    if isinstance(v.get(kk), list):
                        return v[kk]
    return []


def _norm_voice(raw, provider):
    if not isinstance(raw, dict):
        return None
    vid = raw.get("voice_id") or raw.get("id") or ""
    return {
        "id": str(vid),
        "name": str(raw.get("name") or raw.get("title") or vid or "?"),
        "provider": provider,
        "provider_label": PROVIDER_LABELS.get(provider, provider),
        "language": str(raw.get("language") or raw.get("locale") or ""),
        "gender": str(raw.get("gender") or ""),
        "preview_url": (raw.get("preview_url") or raw.get("preview")
                        or raw.get("audio_url") or ""),
        "description": str(raw.get("description") or "")[:200],
        "tags": raw.get("tags") or [],
    }


def list_voices(api_key, search="", page_size=100, timeout=30):
    """Fetch the COMPLETE v3 voice library (all 7 provider groups).

    The /v3/voices endpoint requires a `provider` param, so we query each
    group (page 1, up to `page_size` each) and merge into one list, sorted
    by provider then name. Raises AI33Error with a UI-safe message.
    """
    heads = _headers(api_key)
    out = []
    for provider in PROVIDERS:
        params = {"provider": provider, "page": 1,
                  "page_size": min(int(page_size), 100)}
        if search:
            params["search"] = search
        try:
            resp = requests.get(f"{BASE}/v3/voices", headers=heads,
                                params=params, timeout=timeout)
        except requests.RequestException as e:
            raise AI33Error(f"Network error reaching ai33.pro: {e}") from e
        if resp.status_code != 200:
            # One provider failing shouldn't nuke the whole library —
            # but an auth failure will fail them all, so re-raise 401/403.
            if resp.status_code in (401, 403):
                raise AI33Error(_clean_error(resp))
            continue
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            continue
        for raw in _voice_list_shape(body):
            v = _norm_voice(raw, provider)
            if v and v["id"]:
                out.append(v)
    if not out:
        raise AI33Error("No voices returned — key may be invalid or the "
                        "service is down. Check Settings → API keys.")
    out.sort(key=lambda v: (v["provider_label"], v["name"].lower()))
    return out


def list_clones(api_key, timeout=30):
    """Return only the user's cloned voices (provider == 'clone')."""
    try:
        return [v for v in list_voices(api_key, timeout=timeout)
                if v.get("provider") == "clone"]
    except AI33Error:
        raise
    except Exception as e:  # noqa: BLE001
        raise AI33Error(f"Could not list cloned voices: {e}") from e


def clone_voice(api_key, voice_name, audio_path, timeout=180):
    """Create a voice clone: POST /v3/text-to-speech/voice-clone (multipart).

    Fields: voice_name (str), audio_file (file, max 10MB, clear speech).
    Returns the v3 voice id to use in TTS: "clone_<id>".
    Raises AI33Error with a UI-safe message.
    """
    heads = _headers(api_key)
    name = (voice_name or "").strip()
    if not name:
        raise AI33Error("Give the cloned voice a name first.")
    p = Path(audio_path)
    if not p.is_file():
        raise AI33Error("Voice sample file not found.")
    if p.stat().st_size > 10 * 1024 * 1024:
        raise AI33Error("Sample is over 10MB — trim it to 1–3 minutes.")
    if p.suffix.lower() not in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
        raise AI33Error("Sample must be an audio file (mp3/wav/m4a/ogg/flac).")
    try:
        with open(p, "rb") as f:
            files = {
                "voice_name": (None, name),
                "audio_file": (p.name, f, "application/octet-stream"),
            }
            resp = requests.post(f"{BASE}/v3/text-to-speech/voice-clone",
                                 headers=heads, files=files, timeout=timeout)
    except requests.RequestException as e:
        raise AI33Error(f"Network error reaching ai33.pro: {e}") from e
    if resp.status_code == 429:
        raise AI33Exhausted("ai33.pro rate limit / queue full — "
                            "trying next key.")
    if resp.status_code in (401, 403):
        raise AI33Rejected(f"ai33.pro refused this key "
                           f"(HTTP {resp.status_code}) — trying next key.")
    if resp.status_code != 200:
        raise AI33Error(_clean_error(resp))
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        raise AI33Error("Unexpected clone response from ai33.pro.") from None
    vid = None
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            vid = data.get("voice_id") or data.get("id")
        vid = vid or body.get("voice_id") or body.get("id")
    if not vid:
        raise AI33Error("Clone created but no voice id was returned.")
    vid = str(vid)
    return vid if vid.startswith("clone_") else f"clone_{vid}"


def delete_clone(api_key, voice_clone_id, timeout=60):
    """Delete a cloned voice: DELETE /v3/text-to-speech/voice-clone/{id}.

    Raises AI33Error with a UI-safe message.
    """
    heads = _headers(api_key)
    vid = str(voice_clone_id or "").strip()
    if not vid:
        raise AI33Error("No cloned voice id given.")
    short = vid[6:] if vid.startswith("clone_") else vid
    try:
        resp = requests.delete(
            f"{BASE}/v3/text-to-speech/voice-clone/{short}",
            headers=heads, timeout=timeout)
    except requests.RequestException as e:
        raise AI33Error(f"Network error reaching ai33.pro: {e}") from e
    if resp.status_code not in (200, 204):
        raise AI33Error(_clean_error(resp))
    return True


def get_credits(api_key, timeout=20):
    """Return the current credit balance (number) via GET /v1/credits."""
    heads = _headers(api_key)
    try:
        resp = requests.get(f"{BASE}/v1/credits", headers=heads,
                            timeout=timeout)
    except requests.RequestException as e:
        raise AI33Error(f"Network error reaching ai33.pro: {e}") from e
    if resp.status_code == 429:
        raise AI33Exhausted("ai33.pro rate limit — trying next key.")
    if resp.status_code in (401, 403):
        raise AI33Rejected(f"ai33.pro refused this key "
                           f"(HTTP {resp.status_code}) — trying next key.")
    if resp.status_code != 200:
        raise AI33Error(_clean_error(resp))
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        raise AI33Error("Unexpected credits response.")
    if isinstance(body, (int, float)):
        return body
    if isinstance(body, dict):
        for k in ("credits", "balance", "data"):
            v = body.get(k)
            if isinstance(v, (int, float)):
                return v
            if isinstance(v, dict):
                for kk in ("credits", "balance"):
                    if isinstance(v.get(kk), (int, float)):
                        return v[kk]
    raise AI33Error("Could not read credit balance from the response.")


def download_bytes(url, timeout=60):
    """Download an audio file (result or preview) -> bytes."""
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise AI33Error(f"Download failed: {e}") from e
    if resp.status_code != 200 or not resp.content:
        raise AI33Error(f"Download failed (HTTP {resp.status_code}).")
    return resp.content


def _norm_words(raw):
    """Normalize a word-timing JSON payload -> [{word,start,end}] seconds."""
    items = raw.get("words") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        w = it.get("word") or it.get("text") or it.get("token")
        s = it.get("start") or it.get("start_time") or it.get("offset")
        e = it.get("end") or it.get("end_time")
        if w is None or s is None or e is None:
            continue
        try:
            s, e = float(s), float(e)
        except (TypeError, ValueError):
            continue
        out.append({"word": str(w), "start": s, "end": e})
    if not out:
        return out
    # Heuristic: values that look like milliseconds -> convert to seconds.
    peak = max(w["end"] for w in out)
    n = len(out)
    if n and peak / n > 4.0:  # avg word longer than 4s => must be ms
        for w in out:
            w["start"] = round(w["start"] / 1000.0, 3)
            w["end"] = round(w["end"] / 1000.0, 3)
    else:
        for w in out:
            w["start"] = round(w["start"], 3)
            w["end"] = round(w["end"], 3)
    return out


def synthesize(api_key, text, voice_id, speed=1.0, with_transcript=True,
               file_name=None, poll_interval=3, timeout=900):
    """Full TTS flow: create task (multipart) -> poll -> download audio.

    Returns {"audio": bytes, "words": [...], "audio_url": str}.
    `words` is the transcript word timings when with_transcript=True and the
    service returned a word JSON; else [] (caller falls back to even split).
    """
    heads = _headers(api_key)
    text = (text or "").strip()
    if not text:
        raise AI33Error("Script text is empty — nothing to speak.")
    if not voice_id:
        raise AI33Error("No voice selected. Fetch voices and pick one first.")
    speed = max(0.5, min(1.5, float(speed)))

    # Multipart FormData (NOT JSON) — files={name: (None, value)} forces
    # multipart encoding in requests.
    form = {
        "text": (None, text),
        "voice_id": (None, str(voice_id)),
        "speed": (None, str(speed)),
        "with_transcript": (None, "true" if with_transcript else "false"),
    }
    if file_name:
        form["file_name"] = (None, str(file_name))
    try:
        resp = requests.post(f"{BASE}/v3/text-to-speech", headers=heads,
                             files=form, timeout=60)
    except requests.RequestException as e:
        raise AI33Error(f"Network error reaching ai33.pro: {e}") from e
    if resp.status_code == 429:
        raise AI33Exhausted("ai33.pro rate limit / queue full — "
                            "trying next key.")
    if resp.status_code in (401, 403):
        raise AI33Rejected(f"ai33.pro refused this key "
                           f"(HTTP {resp.status_code}) — trying next key.")
    if resp.status_code != 200:
        raise AI33Error(_clean_error(resp))
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        raise AI33Error("Unexpected TTS response from ai33.pro.")
    task_id = body.get("task_id") if isinstance(body, dict) else None
    if not task_id:
        raise AI33Error("ai33.pro did not return a task_id.")

    # Poll until done.
    deadline = time.time() + timeout
    task_url = f"{BASE}/v1/task/{task_id}"
    while True:
        if time.time() > deadline:
            raise AI33Error("Timed out waiting for the voiceover "
                            "(task still rendering). Try a shorter script.")
        time.sleep(poll_interval)
        try:
            pr = requests.get(task_url, headers=heads, timeout=30)
        except requests.RequestException as e:
            raise AI33Error(f"Poll failed: {e}") from e
        if pr.status_code != 200:
            raise AI33Error(_clean_error(pr))
        try:
            task = pr.json()
        except Exception:  # noqa: BLE001
            continue
        status = str(task.get("status") or task.get("state") or "").lower()
        if status == "error":
            meta = task.get("metadata") or {}
            msg = meta.get("error") or task.get("message") or "task failed"
            raise AI33Error(f"Voiceover failed: {msg}"[:300])
        if status != "done":
            continue
        meta = task.get("metadata") or {}
        audio_url = (meta.get("audio_url") or meta.get("output_uri")
                     or task.get("output_uri"))
        if not audio_url:
            raise AI33Error("Task finished but no audio URL was returned.")
        audio = download_bytes(audio_url)
        words = []
        if with_transcript:
            json_url = meta.get("json_url")
            if json_url:
                try:
                    jr = requests.get(json_url, timeout=30)
                    if jr.status_code == 200:
                        words = _norm_words(jr.json())
                except Exception:  # noqa: BLE001
                    words = []
        # --- Cost tracker: paid TTS chars. No-op when no job is active.
        # Must never break the flow.
        try:
            costs.log_call(costs.current_job_dir(), "ai33pro", "tts_chars",
                           len(text), note="ai33pro v3 TTS")
        except Exception:  # noqa: BLE001
            pass
        return {"audio": audio, "words": words, "audio_url": audio_url}
