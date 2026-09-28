"""mib/ffmpeg.py — ffmpeg binary location + run/probe helpers (pip-only).

Uses imageio-ffmpeg's bundled binary (works inside the PyInstaller exe too),
falling back to a system ffmpeg. Probing is done by parsing `ffmpeg -i`
stderr so it works even where ffprobe is not shipped.
"""
import re
import shutil
import subprocess

_FFMPEG = None


def exe():
    """Path to a working ffmpeg binary. Never raises (returns '' if none)."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    try:
        import imageio_ffmpeg
        cand = imageio_ffmpeg.get_ffmpeg_exe()
        if cand:
            _FFMPEG = cand
            return _FFMPEG
    except Exception:
        pass
    _FFMPEG = shutil.which("ffmpeg") or ""
    return _FFMPEG


def run(args, timeout=600):
    """Run ffmpeg with the given arg list. Returns (rc, stdout, stderr).

    Never raises: on failure returns (-1, '', <message>).
    """
    try:
        binp = exe()
        if not binp:
            return -1, "", "no ffmpeg binary found"
        p = subprocess.run([binp] + list(args), capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "ffmpeg timed out"
    except Exception as e:  # noqa: BLE001
        return -1, "", f"ffmpeg failed: {e}"


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")
_STREAM_RE = re.compile(r"Stream #\d+:\d+[^:]*:\s*(Video|Audio)")
_RES_RE = re.compile(r"(\d{3,5})x(\d{3,5})")


def probe(path):
    """Probe a media file via `ffmpeg -i`.

    Returns {"duration": float, "has_video": bool, "has_audio": bool,
             "width": int, "height": int}. Never raises; unknown -> 0/False.
    """
    out = {"duration": 0.0, "has_video": False, "has_audio": False,
           "width": 0, "height": 0}
    try:
        rc, _so, se = run(["-hide_banner", "-i", str(path)], timeout=60)
        m = _DUR_RE.search(se or "")
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            out["duration"] = h * 3600 + mi * 60 + s
        for kind in _STREAM_RE.findall(se or ""):
            if kind == "Video":
                out["has_video"] = True
            elif kind == "Audio":
                out["has_audio"] = True
        if out["has_video"]:
            for line in (se or "").splitlines():
                if "Video:" in line:
                    r = _RES_RE.search(line)
                    if r:
                        out["width"], out["height"] = int(r.group(1)), int(r.group(2))
                        break
    except Exception:  # noqa: BLE001
        pass
    return out


def has_encoder(name):
    """True when the bundled ffmpeg lists the given encoder. Never raises."""
    try:
        _rc, so, _se = run(["-hide_banner", "-encoders"], timeout=30)
        return name in (so or "")
    except Exception:  # noqa: BLE001
        return False


def audio_track_args(stem):
    """Pick a valid (encoder, output path) pair for an audio-only file.

    libmp3lame -> "<stem>.mp3", else aac -> "<stem>.m4a".
    (aac in an .mp3 container is invalid, so the extension follows the
    encoder.) Never raises.
    """
    try:
        if has_encoder("libmp3lame"):
            return "libmp3lame", f"{stem}.mp3"
    except Exception:  # noqa: BLE001
        pass
    return "aac", f"{stem}.m4a"
