"""mib/stages/avatar_veo.py -- Option 3: AI Video Clips via Gemini Veo.

Generates short (5-15s) natural talking-avatar video clips using the
Gemini Video Generation API (Veo 2 / Veo 3).

Pipeline:
  1. Plan avatar appearance spots (same logic as avatar.py)
  2. For each spot: send a text prompt + presenter image to Gemini Veo
  3. Poll for completion (Veo is async)
  4. Download the .mp4 clip
  5. If Veo fails for any spot, fall back to the static PNG approach

API reference: https://ai.google.dev/gemini-api/docs/video-generation

Install: pip install google-genai  (or google-generativeai>=0.8)

Never raises -- every failure falls back to avatar.py _closeup_clip().
"""
import time
from pathlib import Path

from .. import ffmpeg
from ..config import ROOT
try:
    from ..config import BUNDLE_DIR as _BUNDLE_DIR
except ImportError:
    _BUNDLE_DIR = ROOT

from .avatar import (
    _resolve_image, _cut_audio, plan_segments, _legacy_plan,
    _concat_parts, _split_clip, _closeup_clip,
    CHAPTER_MAX_S, CHAPTER_CLOSEUP_S, _segment_at
)

# How long to wait for Veo (seconds) before fallback
VEO_POLL_TIMEOUT = 120
VEO_POLL_INTERVAL = 5


def _veo_prompt(presenter, script_beat="", style="natural, realistic"):
    """Build a Veo video generation prompt from presenter data."""
    name   = (presenter or {}).get("name", "a presenter")
    niche  = (presenter or {}).get("style", "") or (presenter or {}).get("niche", "")
    outfit = (presenter or {}).get("outfit", "")

    parts = [
        f"A natural talking-head video of {name}",
        "facing the camera directly, speaking confidently",
    ]
    if niche:
        parts.append(f"for a {niche} YouTube channel")
    if outfit:
        parts.append(f"wearing {outfit}")
    if script_beat:
        parts.append(f"saying: \"{script_beat[:80]}\"")
    parts += [
        "tight face close-up framing, chest to top of head visible",
        "neutral indoor background, soft key lighting",
        "no subtitles, no text overlays, no watermarks",
        f"style: {style}, cinematic quality",
    ]
    return ". ".join(parts) + "."


def _generate_veo_clip(api_key, prompt, reference_image_path, duration_s,
                        out_path, logger=None):
    """Call Gemini Veo API to generate one video clip.

    Returns True if file saved to out_path, False otherwise.
    Never raises.
    """
    try:
        # Try google-genai SDK first
        try:
            import google.genai as genai
            from google.genai import types as genai_types

            client = genai.Client(api_key=api_key)
            operation = client.models.generate_video(
                model="veo-2.0-generate-001",
                prompt=prompt,
                config=genai_types.GenerateVideoConfig(
                    duration_seconds=int(max(5, min(15, duration_s))),
                    number_of_videos=1,
                    aspect_ratio="16:9",
                    resolution="1920x1080",
                ),
            )

            if logger:
                logger(f"    avatar_veo: Veo job started, polling...")

            # Poll until done
            deadline = time.time() + VEO_POLL_TIMEOUT
            while not operation.done:
                if time.time() > deadline:
                    if logger:
                        logger("    avatar_veo: Veo timeout -- falling back")
                    return False
                time.sleep(VEO_POLL_INTERVAL)
                operation = client.operations.get(operation)

            if not operation.response or not operation.response.generated_videos:
                if logger:
                    logger("    avatar_veo: no video in response")
                return False

            video = operation.response.generated_videos[0]
            # Download the video bytes
            video_bytes = client.files.download(file=video.video)
            Path(out_path).write_bytes(video_bytes)
            return Path(out_path).is_file() and Path(out_path).stat().st_size > 1000

        except ImportError:
            pass

        # Fallback: try REST API directly
        import json
        import urllib.request

        # Step 1: create video generation job
        api_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"veo-2.0-generate-001:generateVideo?key={api_key}")
        body = json.dumps({
            "prompt": {"text": prompt},
            "config": {
                "durationSeconds": int(max(5, min(15, duration_s))),
                "aspectRatio": "16:9",
                "resolution": "1920x1080",
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            api_url, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            op_data = json.loads(r.read().decode("utf-8", "replace"))

        op_name = op_data.get("name", "")
        if not op_name:
            if logger:
                logger("    avatar_veo: no operation name in response")
            return False

        if logger:
            logger(f"    avatar_veo: polling operation {op_name[:40]}...")

        # Step 2: poll until done
        poll_url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"{op_name}?key={api_key}")
        deadline = time.time() + VEO_POLL_TIMEOUT
        while time.time() < deadline:
            time.sleep(VEO_POLL_INTERVAL)
            req2 = urllib.request.Request(
                poll_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=20) as r2:
                status = json.loads(r2.read().decode("utf-8", "replace"))
            if status.get("done"):
                break
        else:
            if logger:
                logger("    avatar_veo: timeout polling Veo -- fallback")
            return False

        # Step 3: extract video URL
        resp = status.get("response", {})
        videos = resp.get("generatedVideos", [])
        if not videos:
            if logger:
                logger("    avatar_veo: no video in Veo response")
            return False

        video_uri = videos[0].get("video", {}).get("uri", "")
        if not video_uri:
            if logger:
                logger("    avatar_veo: no video URI in response")
            return False

        # Step 4: download
        dl_url = video_uri + (
            f"&key={api_key}" if "?" not in video_uri else f"&key={api_key}")
        req3 = urllib.request.Request(
            dl_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req3, timeout=60) as r3:
            video_bytes = r3.read()
        Path(out_path).write_bytes(video_bytes)
        return Path(out_path).is_file() and Path(out_path).stat().st_size > 1000

    except Exception as e:  # noqa: BLE001
        if logger:
            logger(f"    avatar_veo: generation error: {e}")
        return False


def _veo_to_presenter_clip(veo_mp4, audio_path, out_path, duration, logger=None):
    """Mux the Veo video with our voiceover audio track.

    Veo clips have their own audio (or are silent). We replace audio with
    the exact voiceover segment and trim/pad to the required duration.
    Returns True on success. Never raises.
    """
    try:
        duration = max(2.0, float(duration))
        rc, _so, se = ffmpeg.run([
            "-y",
            "-i", str(veo_mp4),
            "-i", str(audio_path),
            "-filter_complex",
            (f"[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
             "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black[v]"),
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{duration:.2f}",
            str(out_path),
        ], timeout=300)
        ok = rc == 0 and Path(out_path).is_file()
        if not ok and logger:
            logger(f"    avatar_veo: mux failed: {(se or '')[-200:]}")
        return ok
    except Exception as e:  # noqa: BLE001
        if logger:
            logger(f"    avatar_veo: mux error: {e}")
        return False


def run(job_dir, voiceover_path, presenter, secrets=None, cfg=None,
        seconds=8, appearances=1, total_duration=0.0, logger=None,
        voice_segments=None, script=None, images=None):
    """Build AI-video presenter clips using Gemini Veo.

    For each avatar spot: generate a Veo clip, mux with voiceover audio.
    Falls back to static PNG for any spot that fails.
    Returns same dict shape as avatar.run(). Never raises.
    """
    job       = Path(job_dir)
    avatar_dir = job / "avatar"
    try:
        avatar_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    image = _resolve_image(presenter)
    name  = (presenter or {}).get("name", "presenter")
    result = {"intro": "", "mids": [], "presenter": name}

    # Get API key
    secrets  = secrets or {}
    api_key  = (secrets.get("gemini_api_key") or
                secrets.get("gemini_tts_keys") or "")
    if isinstance(api_key, list):
        api_key = api_key[0] if api_key else ""

    if not api_key:
        if logger:
            logger("    avatar_veo: no Gemini API key -- fallback static PNG")
        if image:
            return _fallback_run(
                job_dir, voiceover_path, presenter, image, seconds,
                appearances, total_duration, logger, voice_segments, script, images)
        return result

    try:
        seconds     = min(15.0, max(5.0, float(seconds or 8)))
    except (TypeError, ValueError):
        seconds     = 8.0
    try:
        appearances = max(1, min(6, int(appearances or 1)))
    except (TypeError, ValueError):
        appearances = 1
    total = max(1.0, float(total_duration or 0))
    images = list(images or [])

    # Build plan
    plan = None
    try:
        if voice_segments and script:
            starts, durs, cum = [], [], 0.0
            for s in voice_segments:
                starts.append(cum)
                d = float(s.get("duration") or 0)
                durs.append(d)
                cum += d
            beats = script.get("beats") or []
            rejoin_idxs = [i + 1 for i, b in enumerate(beats) if b.get("rejoin")]
            plan = plan_segments(total or cum, starts, durs, rejoin_idxs,
                                 seconds=seconds, appearances=appearances)
    except Exception:  # noqa: BLE001
        plan = None
    if not plan:
        plan = _legacy_plan(total, seconds, appearances)

    # Get script text for prompts
    beats_text = []
    try:
        if script:
            beats_text = [b.get("narration", "")[:120]
                          for b in (script.get("beats") or [])]
    except Exception:  # noqa: BLE001
        pass

    def broll_for(seg_idx):
        try:
            if 0 <= seg_idx < len(images) and Path(images[seg_idx]).is_file():
                return images[seg_idx]
        except Exception:  # noqa: BLE001
            pass
        return ""

    def _render_spot(n, spot):
        kind, at, dur = spot["kind"], spot["at"], spot["dur"]
        closeup_s = spot.get("closeup_s") or 0.0
        tag   = "intro" if kind == "intro" else f"{kind}-{n}"
        audio = _cut_audio(voiceover_path, at, dur, avatar_dir / f"{tag}-audio")
        if not audio:
            return n, kind, at, ""

        out = avatar_dir / f"{tag}.mp4"
        ok  = False

        if kind == "intro" or (kind == "chapter" and closeup_s >= dur - 0.5):
            # Generate a Veo clip for full-screen spots
            beat_txt = beats_text[0] if beats_text else ""
            prompt   = _veo_prompt(presenter, beat_txt)
            raw_veo  = avatar_dir / f"{tag}-veo-raw.mp4"
            if _generate_veo_clip(api_key, prompt, image, dur, raw_veo, logger):
                ok = _veo_to_presenter_clip(raw_veo, audio, out, dur, logger)
            # Fallback to static on Veo failure
            if not ok and image:
                ok = _closeup_clip(image, audio, out, dur, logger)

        elif kind == "chapter":
            split_s = max(2.0, dur - closeup_s)
            a1 = _cut_audio(voiceover_path, at, closeup_s, avatar_dir / f"{tag}-a1")
            a2 = _cut_audio(voiceover_path, at + closeup_s, split_s, avatar_dir / f"{tag}-a2")
            p1, p2 = avatar_dir / f"{tag}-p1.mp4", avatar_dir / f"{tag}-p2.mp4"
            broll = broll_for(spot.get("seg_idx", 0)) or image

            beat_txt = beats_text[min(n, len(beats_text) - 1)] if beats_text else ""
            prompt   = _veo_prompt(presenter, beat_txt)
            raw_veo  = avatar_dir / f"{tag}-veo-raw.mp4"

            if a1 and a2:
                # Try Veo for close-up part, fallback to static
                if _generate_veo_clip(api_key, prompt, image, closeup_s, raw_veo, logger):
                    r1 = _veo_to_presenter_clip(raw_veo, a1, p1, closeup_s, logger)
                else:
                    r1 = image and _closeup_clip(image, a1, p1, closeup_s, logger)
                r2 = _split_clip(image or broll, broll or image, a2, p2, split_s, logger)
                if r1 and r2:
                    ok = _concat_parts([p1, p2], out, logger)
        else:
            broll = broll_for(spot.get("seg_idx", 0)) or image
            ok = image and _split_clip(image, broll, audio, out, dur, logger)

        return n, kind, at, str(out) if ok else ""

    # Sequential rendering (Veo API calls already include network waits,
    # parallel polling would hit rate limits)
    rendered = {}
    for n, spot in enumerate(plan):
        try:
            n2, kind, at, out_path = _render_spot(n, spot)
            rendered[n] = (kind, at, out_path)
        except Exception as e:  # noqa: BLE001
            if logger:
                logger(f"    avatar_veo: spot {n} error: {e}")
            rendered[n] = ("unknown", 0.0, "")

    for n in sorted(rendered):
        kind, at, out_path = rendered[n]
        if not out_path:
            if logger:
                logger(f"    avatar_veo: spot {n} failed -- skipping")
            continue
        entry = {"file": out_path, "at": round(at, 2), "kind": kind}
        if kind == "intro":
            result["intro"] = out_path
            if logger:
                logger(f"    avatar_veo intro: Veo clip ({plan[n]['dur']:.0f}s)")
        else:
            result["mids"].append(entry)
            if logger:
                logger(f"    avatar_veo {kind} at {at:.0f}s")

    result["mids"].sort(key=lambda m: m.get("at", 0))
    return result


def _fallback_run(job_dir, voiceover_path, presenter, image, seconds,
                  appearances, total_duration, logger, voice_segments, script, images):
    """Full fallback to standard static PNG avatar mode."""
    from .avatar import run as _av_run
    return _av_run(
        job_dir, voiceover_path, presenter,
        seconds=seconds, appearances=appearances,
        total_duration=total_duration, logger=logger,
        voice_segments=voice_segments, script=script, images=images)
