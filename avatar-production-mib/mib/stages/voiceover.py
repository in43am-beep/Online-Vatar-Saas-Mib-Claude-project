"""mib/stages/voiceover.py — per-segment voiceover with free fallbacks.

Provider order: channel locked voice (ai33pro/clone) -> edge-tts (free).
Any provider failure on a segment -> local silent-tone track of the expected
duration, so the pipeline NEVER dies on a provider failure.

Writes audio/seg-00.mp3 ... + audio/voiceover.mp3 (concat).
Verifies the first segment exists and is non-silent (warning only).
"""
from pathlib import Path

from .. import ffmpeg
from .. import config as config_mod
from ..keypool import pool_from_secrets
from ..providers import ai33voice, edgevoice, geminitts
from .script import sanitize

WPM = 140


def _expected_seconds(text):
    words = len(str(text or "").split())
    return max(3.0, words / WPM * 60.0)


def _tone_track(out_path, seconds, logger=None):
    """Local fallback: soft 440Hz tone (passes the non-silent check)."""
    seconds = max(2.0, float(seconds))
    enc, real_path = ffmpeg.audio_track_args(str(out_path).rsplit(".", 1)[0])
    rc, _so, se = ffmpeg.run([
        "-y", "-f", "lavfi", "-i",
        f"sine=frequency=440:duration={seconds:.1f}",
        "-c:a", enc, "-ar", "44100", "-ac", "2", real_path,
    ], timeout=120)
    if (rc != 0 or not Path(real_path).exists()) and enc != "aac":
        # last resort: aac in m4a container — still playable
        enc, real_path = "aac", str(out_path).rsplit(".", 1)[0] + ".m4a"
        ffmpeg.run(["-y", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds:.1f}",
                    "-c:a", "aac", "-ar", "44100", real_path], timeout=120)
    if logger:
        logger.log(f"    voice [local-tone]: {Path(real_path).name} "
                   f"({seconds:.0f}s)")
    return real_path


def _ai33_segment(ai33_pool, voice_id, text, out_path, logger=None):
    res = ai33_pool.run(
        lambda k: ai33voice.synthesize(k, text, voice_id, speed=0.85,
                                      with_transcript=False),
        logger, op="voice")
    Path(out_path).write_bytes(res["audio"])
    if logger:
        logger.log(f"    voice [ai33pro]: {Path(out_path).name}")


def _gemini_tts_segment(api_key, voice_id, text, out_path, logger=None):
    """Synthesize via Gemini TTS free tier. Returns actual output path."""
    path = geminitts.synthesize(api_key, text,
                                voice=voice_id or geminitts.DEFAULT_VOICE,
                                out_path=out_path)
    if logger:
        logger.log(f"    voice [gemini-tts]: {Path(path).name}")
    return path


def _edge_segment(voice_id, text, out_path, logger=None):
    edgevoice.synthesize(text, voice_id or edgevoice.DEFAULT_FEMALE,
                         out_path, rate="-15%")
    if logger:
        logger.log(f"    voice [edge]: {Path(out_path).name}")


def _non_silent(path, logger=None):
    """True when the file has audible content (astats Max_level > -60dB).

    Warning-only check: returns False on any probe problem.
    """
    try:
        rc, so, _se = ffmpeg.run([
            "-hide_banner", "-i", str(path),
            "-af", "astats=metadata=1:reset=0", "-f", "null", "-",
        ], timeout=60)
        import re
        m = re.search(r"Max level dB:\s*(-?[\d.]+|-\s*inf)", so or "")
        if not m:
            return ffmpeg.probe(path)["duration"] > 0
        val = m.group(1).replace(" ", "")
        if "inf" in val:
            return False
        return float(val) > -60.0
    except Exception:  # noqa: BLE001
        return False


def run(job_dir, script, voice_cfg, secrets, logger=None):
    """Synthesize every segment. Returns dict; never raises."""
    job = Path(job_dir)
    audio_dir = job / "audio"
    try:
        audio_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    voice_cfg = voice_cfg or {}
    secrets = secrets or {}
    provider = (voice_cfg.get("provider") or "gemini-tts").lower()
    voice_id = voice_cfg.get("voice_id") or ""
    ai33_pool = pool_from_secrets("ai33-voice", secrets,
                                  "ai33pro_api_key", "ai33pro_api_keys",
                                  config_mod.CONFIG_PATH.parent)
    # Gemini TTS key — pulled from secrets (same tab as Gemini image keys)
    gemini_tts_key = ""
    try:
        gemini_tts_key = (
            (secrets.get("gemini_tts_keys") or "").strip().splitlines()[0].strip()
            or (secrets.get("gemini_api_keys") or "").strip().splitlines()[0].strip()
            or (secrets.get("gemini_api_key") or "").strip()
        )
    except Exception:  # noqa: BLE001
        pass

    segments_src = [("hook", script.get("hook", ""))]
    for i, b in enumerate(script.get("beats", [])):
        segments_src.append((f"beat-{i}", b.get("narration", "")))
    segments_src.append(("cta", script.get("cta", "")))

    segments = []
    used_provider = "edge"
    for idx, (name, text) in enumerate(segments_src):
        text = sanitize(text) or "Thank you for watching."
        out = audio_dir / f"seg-{idx:02d}.mp3"
        prov = "local-tone"
        try:
            if provider == "ai33pro" and ai33_pool and voice_id:
                # Priority 1: AI33 Pro (paid, highest quality)
                _ai33_segment(ai33_pool, voice_id, text, out, logger)
                prov = "ai33pro"
            elif provider in ("gemini-tts", "gemini") and gemini_tts_key:
                # Priority 2: Gemini TTS free tier (human-sounding, $0.00)
                real_out = _gemini_tts_segment(
                    gemini_tts_key, voice_id, text, out, logger)
                out = Path(real_out)  # path may differ (wav vs mp3)
                prov = "gemini-tts"
            else:
                # Priority 3: Edge TTS (free, robotic fallback)
                _edge_segment(voice_id, text, out, logger)
                prov = "edge"
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.log(f"    voice [{provider}] failed on {name}: {e}")
            # Try Edge TTS as emergency fallback before tone
            # IMPORTANT: only pass voice_id to Edge if the channel uses edge provider
            # Never pass Gemini/AI33 voice IDs to Edge TTS — they're incompatible
            edge_vid = (voice_id or "") if provider == "edge" else edgevoice.DEFAULT_FEMALE
            try:
                _edge_segment(edge_vid, text, out, logger)
                prov = "edge"
            except Exception as e2:  # noqa: BLE001
                if logger:
                    logger.log(f"    voice [edge] also failed: {e2} — tone fallback")
                out = Path(_tone_track(out, _expected_seconds(text), logger))
                prov = "local-tone"
        dur = ffmpeg.probe(out)["duration"] or _expected_seconds(text)
        segments.append({"name": name, "file": str(out),
                         "duration": round(dur, 2), "provider": prov,
                         "text": text})
        used_provider = prov if idx == 0 else used_provider

    # verify first ~10s: first segment exists and is non-silent (warning only)
    try:
        first = segments[0]["file"] if segments else ""
        if not Path(first).exists():
            if logger:
                logger.log("    WARNING: first voiceover segment missing")
        elif not _non_silent(first, logger):
            if logger:
                logger.log("    WARNING: first voiceover segment seems silent")
    except Exception:  # noqa: BLE001
        pass

    # concat -> voiceover audio (re-encode for container safety)
    enc, voiceover = ffmpeg.audio_track_args(str(audio_dir / "voiceover"))
    voiceover = Path(voiceover)
    try:
        inputs = []
        for s in segments:
            inputs += ["-i", s["file"]]
        n = len(segments)
        filt = "".join(f"[{i}:a]" for i in range(n)) + \
            f"concat=n={n}:v=0:a=1[a]"
        rc, _so, _se = ffmpeg.run(
            ["-y"] + inputs + ["-filter_complex", filt, "-map", "[a]",
                              "-c:a", enc, "-ar", "44100", str(voiceover)],
            timeout=300)
        if rc != 0 or not voiceover.exists():
            raise RuntimeError("concat failed")
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    WARNING: voiceover concat failed ({e}); "
                       "using first segment as voiceover track")
        try:
            import shutil
            if segments:
                shutil.copy(segments[0]["file"], voiceover)
        except Exception:  # noqa: BLE001
            pass

    return {"segments": segments, "voiceover": str(voiceover),
            "provider": used_provider}
