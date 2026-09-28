"""mib/providers/edgevoice.py — FREE default voiceover via edge-tts.

No API key. Needs internet. Speed 85 ~= rate "-15%".
Any failure raises EdgeError with a UI-safe message; the voiceover stage
catches it and falls back to a local silent-tone track so the pipeline
never dies on a provider failure.

FIX (Bug 2): synthesis now runs in a subprocess (_edge_worker.py) so
that asyncio never conflicts with the PySide6 Qt event loop. The Qt UI
stays fully responsive during voice generation.
"""
import re
import subprocess
import sys
from pathlib import Path

try:
    import edge_tts as _edge_tts_mod
except Exception:   # noqa: BLE001
    _edge_tts_mod = None


class EdgeError(Exception):
    """Clean, UI-safe error."""


DEFAULT_FEMALE = "en-US-AvaNeural"    # warm female
DEFAULT_MALE   = "en-US-AndrewNeural" # male

# path to the worker script that runs asyncio in isolation
_WORKER = str(Path(__file__).with_name("_edge_worker.py"))


def _rate_for_speed85():
    return "-15%"


def _clean_text(text):
    """Edge-tts chokes on some control chars; strip them."""
    t = str(text or "")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t)
    return t.strip()


def synthesize(text, voice, out_path, rate=None, timeout=300):
    """Synthesize text -> mp3 file via subprocess worker.

    Running edge-tts in a child process (asyncio.run inside _edge_worker.py)
    keeps the asyncio event loop completely separate from PySide6's Qt loop,
    preventing UI freezes and crashes.
    Raises EdgeError on any failure.
    """
    if _edge_tts_mod is None:
        raise EdgeError("edge-tts is not installed (pip install edge-tts).")
    text = _clean_text(text)
    if not text:
        raise EdgeError("Script text is empty — nothing to speak.")
    voice = (voice or "").strip() or DEFAULT_FEMALE
    try:
        result = subprocess.run(
            [sys.executable, _WORKER, text, voice, str(out_path)],
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", errors="replace")[:300]
            raise EdgeError(f"Edge TTS failed: {err}")
        if not Path(out_path).is_file():
            raise EdgeError("Edge TTS produced no output file.")
    except subprocess.TimeoutExpired as e:
        raise EdgeError("Edge TTS timed out (network slow?).") from e
    except EdgeError:
        raise
    except Exception as e:  # noqa: BLE001
        raise EdgeError(f"Edge TTS error: {e}"[:300]) from e
    return str(out_path)


def list_voices(timeout=30):
    """Return [{id, name, gender, locale}] for English voices. UI-safe."""
    if _edge_tts_mod is None:
        return []
    import asyncio
    try:
        async def _go():
            return await _edge_tts_mod.list_voices()
        # list_voices is a one-off lookup called from a settings dialog,
        # not from inside the pipeline — asyncio.run() is safe here.
        voices = asyncio.run(asyncio.wait_for(_go(), timeout=timeout))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for v in voices or []:
        locale = str(v.get("Locale", ""))
        if not locale.startswith("en"):
            continue
        out.append({
            "id":     v.get("ShortName", ""),
            "name":   v.get("FriendlyName", v.get("ShortName", "")),
            "gender": str(v.get("Gender", "")).lower(),
            "locale": locale,
        })
    out.sort(key=lambda v: (v["locale"], v["name"]))
    return out
