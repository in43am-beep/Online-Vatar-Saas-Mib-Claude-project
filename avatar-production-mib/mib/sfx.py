"""mib/sfx.py — Sound Design: whooshes, hits, risers at scene changes.

Frontier adds free SFX at every scene change: whooshes under cuts,
hits on chapter openings, risers at build-ups.
All SFX are pre-baked local files from assets/sfx/.
Mixed at -20 dB under voiceover so they accent without drowning speech.

Usage:
    from mib.sfx import mix_sfx_into_video
    out = mix_sfx_into_video(job_dir, final_mp4, scene_times, logger)

SFX files expected in assets/sfx/:
    whoosh_01.mp3 ... whoosh_N.mp3   — scene transition swooshes
    hit_01.mp3 ... hit_N.mp3         — chapter opening impacts
    riser_01.mp3 ... riser_N.mp3     — tension build-ups

Download free SFX from: https://freesound.org
Search: "whoosh transition", "impact hit", "riser buildup"
License: CC0 (public domain)
"""
import random
from pathlib import Path

from . import ffmpeg

# Volume of SFX relative to voiceover (dB)
SFX_VOLUME_DB = -20


def _sfx_files(category):
    """Return sorted list of SFX files for a category. Never raises."""
    try:
        from .config import ROOT, BUNDLE_DIR
        for base in (ROOT, BUNDLE_DIR):
            sfx_dir = base / "assets" / "sfx"
            if sfx_dir.is_dir():
                files = sorted(sfx_dir.glob(f"{category}_*.mp3"))
                if files:
                    return files
    except Exception:  # noqa: BLE001
        pass
    return []


def _pick_sfx(category, seed=0):
    """Pick a random SFX file for a category. Returns path or None."""
    files = _sfx_files(category)
    if not files:
        return None
    return str(files[seed % len(files)])


def mix_sfx_into_video(job_dir, video_path, scene_times, cfg=None, logger=None):
    """Overlay SFX at scene cuts and return the mixed video path.

    Args:
        job_dir:     Job working directory.
        video_path:  Input video (final.mp4 after assembly).
        scene_times: List of timestamps (seconds) where scene cuts occur.
        cfg:         Config dict (reads sfx_volume_db).
        logger:      JobLogger instance.

    Returns:
        str: Path to the SFX-mixed video, or video_path unchanged on failure.

    Never raises.
    """
    try:
        if not scene_times:
            return str(video_path)

        job = Path(job_dir)
        out = job / "final_sfx.mp4"
        vol_db = float((cfg or {}).get("providers", {}).get(
            "sfx_volume_db", SFX_VOLUME_DB))

        # Check if we have any SFX files at all
        whooshes = _sfx_files("whoosh")
        hits = _sfx_files("hit")
        if not whooshes and not hits:
            if logger:
                logger.log("    sfx: no SFX files in assets/sfx/ — skipping. "
                           "Download from freesound.org (see mib/sfx.py)")
            return str(video_path)

        # Build FFmpeg filter_complex:
        # 1. Extract audio from video
        # 2. For each scene cut: adelay the SFX to that timestamp
        # 3. amix everything together at relative volume

        all_files = [str(video_path)]
        sfx_inputs = []
        rng = random.Random(42)

        for i, t in enumerate(scene_times[:20]):  # cap at 20 sfx overlays
            # Chapter openings (first 30% of video) get hits, rest get whooshes
            total_dur = ffmpeg.probe(video_path)["duration"] or 1.0
            if whooshes and t < total_dur * 0.3:
                sfx_path = str(rng.choice(whooshes))
            elif whooshes:
                sfx_path = str(rng.choice(whooshes))
            else:
                sfx_path = str(rng.choice(hits))
            all_files.append(sfx_path)
            sfx_inputs.append((i + 1, t))  # (input_index, delay_ms)

        # Build filter_complex string
        # Input 0 = video (audio), inputs 1..N = SFX files
        n_sfx = len(sfx_inputs)
        vol_linear = 10 ** (vol_db / 20.0)  # dB to linear

        filter_parts = []
        mix_inputs = ["[0:a]"]

        for input_idx, t in sfx_inputs:
            delay_ms = int(t * 1000)
            label = f"sfx{input_idx}"
            filter_parts.append(
                f"[{input_idx}:a]volume={vol_linear:.4f},"
                f"adelay={delay_ms}|{delay_ms}[{label}]"
            )
            mix_inputs.append(f"[{label}]")

        n_mix = len(mix_inputs)
        filter_parts.append(
            "".join(mix_inputs) + f"amix=inputs={n_mix}:duration=first:normalize=0[aout]"
        )

        filter_complex = ";".join(filter_parts)

        # Build FFmpeg command
        cmd = ["-y"]
        for f in all_files:
            cmd += ["-i", f]
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "0:v",      # video from original
            "-map", "[aout]",   # mixed audio
            "-c:v", "copy",     # video stream unchanged
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            str(out),
        ]

        rc, _so, se = ffmpeg.run(cmd, timeout=600)
        if rc == 0 and out.is_file():
            if logger:
                logger.log(f"    sfx: {n_sfx} sound effects mixed at {vol_db}dB")
            return str(out)

        if logger:
            logger.log(f"    sfx: mix failed: {(se or '')[-150:]} — using original")
        return str(video_path)

    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    sfx: error: {e} — using original")
        return str(video_path)


def detect_scene_cuts(video_path, min_gap=3.0, logger=None):
    """Detect scene cut timestamps from a video using FFmpeg scene filter.

    Returns list of timestamps (seconds) where cuts occur.
    Falls back to evenly-spaced cuts if detection fails.
    Never raises.
    """
    try:
        rc, stdout, _se = ffmpeg.run([
            "-y", "-i", str(video_path),
            "-vf", "select='gt(scene,0.3)',showinfo",
            "-vsync", "vfr", "-f", "null", "-",
        ], timeout=300)

        import re
        times = []
        for m in re.finditer(r"pts_time:([\d.]+)", stdout or ""):
            t = float(m.group(1))
            if not times or t - times[-1] >= min_gap:
                times.append(t)

        if times:
            if logger:
                logger.log(f"    sfx: detected {len(times)} scene cuts")
            return times
    except Exception:  # noqa: BLE001
        pass

    # Fallback: evenly spaced every 45 seconds
    try:
        dur = ffmpeg.probe(video_path)["duration"] or 0.0
        times = [t for t in range(45, int(dur), 45)]
        if logger:
            logger.log(f"    sfx: using {len(times)} evenly-spaced SFX positions")
        return times
    except Exception:  # noqa: BLE001
        return []


def create_sample_sfx(assets_dir, logger=None):
    """Generate minimal synthetic SFX using FFmpeg (no downloads needed).

    Creates 3 whoosh and 2 hit files using FFmpeg's sine/noise generators.
    Quality is basic — replace with Freesound downloads for production.
    Never raises.
    """
    sfx_dir = Path(assets_dir) / "sfx"
    try:
        sfx_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        return

    # Synthetic whoosh: frequency sweep 200Hz→2000Hz over 0.8s
    for i in range(1, 4):
        out = sfx_dir / f"whoosh_0{i}.mp3"
        if out.is_file():
            continue
        seed_freq = 200 + (i * 100)
        ffmpeg.run([
            "-y", "-f", "lavfi",
            "-i", f"sine=frequency={seed_freq}:duration=0.8",
            "-af", "afade=t=in:st=0:d=0.1,afade=t=out:st=0.6:d=0.2,volume=0.3",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(out),
        ], timeout=30)

    # Synthetic hit: short noise burst with fast attack
    for i in range(1, 3):
        out = sfx_dir / f"hit_0{i}.mp3"
        if out.is_file():
            continue
        ffmpeg.run([
            "-y", "-f", "lavfi",
            "-i", "anoisesrc=duration=0.3:color=brown",
            "-af", "afade=t=in:st=0:d=0.02,afade=t=out:st=0.15:d=0.15,"
                   "volume=0.4",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(out),
        ], timeout=30)

    if logger:
        logger.log("    sfx: synthetic SFX generated in assets/sfx/ "
                   "(replace with Freesound downloads for better quality)")
