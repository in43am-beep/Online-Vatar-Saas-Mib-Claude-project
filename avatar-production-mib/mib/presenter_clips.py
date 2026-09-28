"""mib/presenter_clips.py — Pre-recorded presenter clip system.

HOW IT WORKS (Frontier's secret):
    Instead of AI-generated talking heads (expensive), we use
    pre-recorded short video clips of a real person (you, or anyone
    you hire for 2 hours). These clips are stored in assets/presenters/<id>/.

    At generation time:
    1. Pick a clip from the presenter's folder (random, no repeat until all used)
    2. MUTE the clip's original audio
    3. Overlay Gemini TTS audio on top
    4. Result: a "talking head" video where mouth moves naturally

    WHY NO LIPSYNC NEEDED:
    Natural mouth movement during normal speech already looks like talking.
    The clip is muted so no words are heard twice. The TTS audio plays over.
    This is exactly how Frontier's "$0.22 per appearance" works.

RECORDING GUIDE (record these once, use forever):
    - Phone camera, landscape mode, 1080p
    - Sit at desk or kitchen table (neutral background)
    - Look at camera, talk naturally for 8-10 seconds
    - Make 25+ different clips: looking straight, nodding, gesturing,
      looking slightly left/right, smiling, serious expression
    - Filename: clip_001.mp4, clip_002.mp4 ... clip_025.mp4
    - Place in: assets/presenters/<presenter_id>/

COST:
    One-time recording session (2 hours). $0.00 ongoing.
    Only TTS cost ($0.00 on Gemini free tier) per appearance.
"""
import random
from pathlib import Path

from . import ffmpeg

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}


def _clip_dir(presenter_id):
    """Return the clips directory for a presenter. Checks both ROOT and BUNDLE_DIR."""
    try:
        from .config import ROOT, BUNDLE_DIR
        for base in (ROOT, BUNDLE_DIR):
            d = base / "assets" / "presenters" / str(presenter_id)
            if d.is_dir():
                return d
    except Exception:  # noqa: BLE001
        pass
    return None


def has_clips(presenter_id):
    """True if this presenter has pre-recorded video clips."""
    d = _clip_dir(presenter_id)
    if not d:
        return False
    return any(f.suffix.lower() in VIDEO_EXTS for f in d.iterdir())


def _all_clips(presenter_id):
    """Return sorted list of all clip paths for a presenter."""
    d = _clip_dir(presenter_id)
    if not d:
        return []
    return sorted(f for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() in VIDEO_EXTS)


def pick_clip(presenter_id, appearance_index=0):
    """Pick a clip path for this appearance. Rotates through all clips.

    Uses appearance_index to cycle — ensures variety across appearances.
    Returns None if no clips exist.
    """
    clips = _all_clips(presenter_id)
    if not clips:
        return None
    return str(clips[appearance_index % len(clips)])


def overlay_tts_on_clip(clip_path, tts_audio_path, out_path,
                         target_duration=None, logger=None):
    """Mute clip, overlay TTS audio, trim to shorter of the two.

    This is the core operation:
    - Video: from clip (mouth moving naturally)
    - Audio: from TTS (synthesized speech)
    - Length: min(clip_duration, tts_duration) so they stay in sync

    Args:
        clip_path:       Pre-recorded presenter video clip.
        tts_audio_path:  Gemini TTS synthesized audio file.
        out_path:        Output MP4 path.
        target_duration: Optional max duration in seconds.
        logger:          JobLogger instance.

    Returns:
        str: Output path on success, '' on failure.
    Never raises.
    """
    try:
        clip_dur = ffmpeg.probe(clip_path)["duration"] or 0.0
        tts_dur = ffmpeg.probe(tts_audio_path)["duration"] or 0.0

        if clip_dur <= 0 or tts_dur <= 0:
            if logger:
                logger.log(f"    presenter_clips: zero duration — "
                           f"clip={clip_dur:.1f}s tts={tts_dur:.1f}s")
            return ""

        # Duration = shorter of clip or TTS (natural sync)
        use_dur = min(clip_dur, tts_dur)
        if target_duration:
            use_dur = min(use_dur, float(target_duration))
        use_dur = max(2.0, use_dur)

        # Loop clip if TTS is longer than available clip
        loop_count = max(1, int(tts_dur / clip_dur) + 1)

        cmd = [
            "-y",
            "-stream_loop", str(loop_count - 1),   # loop clip if needed
            "-i", str(clip_path),                    # presenter video (muted)
            "-i", str(tts_audio_path),               # TTS audio
            "-map", "0:v",          # video from clip
            "-map", "1:a",          # audio from TTS (not from clip)
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{use_dur:.2f}",  # trim to sync duration
            # Scale to 1920x1080
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                   "crop=1920:1080",
            str(out_path),
        ]

        rc, _so, se = ffmpeg.run(cmd, timeout=300)
        if rc == 0 and Path(out_path).is_file():
            if logger:
                logger.log(f"    presenter_clips: clip overlay "
                           f"({use_dur:.1f}s) — {Path(out_path).name}")
            return str(out_path)

        if logger:
            logger.log(f"    presenter_clips: overlay failed: "
                       f"{(se or '')[-150:]}")
        return ""

    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    presenter_clips: error: {e}")
        return ""


def make_presenter_segment(presenter_id, tts_audio_path, out_path,
                            appearance_index=0, logger=None):
    """Make one presenter appearance: pick clip, overlay TTS, return path.

    This replaces the static PNG zoompan in avatar.py when real clips exist.
    Returns '' if no clips — caller falls back to PNG zoompan.
    Never raises.
    """
    clip = pick_clip(presenter_id, appearance_index)
    if not clip:
        return ""  # no clips — fall back to PNG zoompan in avatar.py

    return overlay_tts_on_clip(clip, tts_audio_path, out_path,
                               logger=logger)


def setup_presenter_dir(presenter_id, logger=None):
    """Create the clips directory for a presenter (first-time setup).

    Returns the path where clips should be placed.
    Never raises.
    """
    try:
        from .config import ROOT
        d = ROOT / "assets" / "presenters" / str(presenter_id)
        d.mkdir(parents=True, exist_ok=True)
        readme = d / "README.txt"
        if not readme.is_file():
            readme.write_text(
                f"Presenter Clips — {presenter_id}\n"
                "=" * 40 + "\n\n"
                "Place your pre-recorded video clips here:\n"
                "  clip_001.mp4, clip_002.mp4, ... clip_025.mp4\n\n"
                "Recording guide:\n"
                "  - Phone camera, landscape, 1080p\n"
                "  - 8-10 seconds per clip\n"
                "  - Look at camera, talk naturally\n"
                "  - 25+ clips for variety\n"
                "  - Neutral background, good lighting\n\n"
                "Cost: one-time recording session (2 hours)\n"
                "Each appearance then costs only TTS (~$0.00 on Gemini free tier)\n",
                encoding="utf-8"
            )
        if logger:
            logger.log(f"    presenter_clips: clips dir ready: {d}")
        return str(d)
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    presenter_clips: setup error: {e}")
        return ""
