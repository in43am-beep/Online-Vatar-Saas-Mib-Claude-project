"""mib/stages/assemble.py — final.mp4: intro + per-beat image segments.

The avatar's spoken slices (intro + rejoins) are CUT OUT of the beat
audio, so the story continues through every appearance — the same words
are never heard twice. Each avatar appearance speaks NEW, continuing
script, like the reference pattern (avatar returns several times, always
with fresh lines). Never raises.
"""
from pathlib import Path
import re

from .. import ffmpeg


def _beat_segment(image, audio, out_path, duration, logger=None):
    try:
        duration = max(1.0, float(duration))
        rc, _so, se = ffmpeg.run([
            "-y",
            "-framerate", "30", "-loop", "1", "-t", f"{duration:.2f}",
            "-i", image,
            "-i", audio,
            "-filter_complex",
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            "zoompan=z='min(1+0.0007*on,1.10)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "d=1:s=1920x1080:fps=30[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{duration:.2f}",
            str(out_path),
        ], timeout=900)
        ok = rc == 0 and Path(out_path).is_file()
        if not ok and logger:
            logger.log(f"    assemble: beat segment failed: {(se or '')[-200:]}")
        return ok
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    assemble: beat segment error: {e}")
        return False


def _srt_time(s):
    s = max(0.0, float(s))
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def _sentences(text):
    """Split narration into sentences for progressive caption reveal."""
    try:
        parts = re.split(r"(?<=[.!?…])\s+", (text or "").strip())
        return [p.strip() for p in parts if p.strip()]
    except Exception:  # noqa: BLE001
        return [(text or "").strip()]


def _build_srt_entries(timeline):
    """Progressive-reveal caption entries.

    The reference burns captions in 100% of the time: bold white text on a
    black box, lower-third, growing word-by-word within each sentence and
    then clearing for the next. Each entry therefore shows the *cumulative*
    words of its sentence so far. Returns a list of SRT blocks.
    Never raises.
    """
    try:
        blocks, idx = [], 1
        for start, dur, text in timeline:
            text = (text or "").strip()
            if not text or dur <= 0:
                continue
            words_total = len(text.split())
            if not words_total:
                continue
            t = float(start)
            for sent in _sentences(text):
                words = sent.split()
                if not words:
                    continue
                # time share of this sentence, proportional to its words
                sent_dur = dur * len(words) / words_total
                group, shown = 4, []
                n_groups = max(1, (len(words) + group - 1) // group)
                per = max(0.4, sent_dur / n_groups)
                for g in range(n_groups):
                    shown = words[: (g + 1) * group]
                    # wrap to at most 3 lines (~40 chars each)
                    lines, cur = [], ""
                    for w in shown:
                        if len(cur) + len(w) > 40 and cur:
                            lines.append(cur)
                            cur = w
                        else:
                            cur = (cur + " " + w).strip()
                    if cur:
                        lines.append(cur)
                    lines = lines[-3:]
                    blocks.append(f"{idx}\n{_srt_time(t)} --> "
                                  f"{_srt_time(t + per)}\n"
                                  + "\n".join(lines) + "\n")
                    idx += 1
                    t += per
        return blocks
    except Exception:  # noqa: BLE001
        return []


def _burn_subtitles(job_dir, final_mp4, timeline, logger=None):
    """Burn reference-style captions into a copy of final_mp4 (best effort).

    Bold white text on a solid black box, bottom-centre, growing
    word-by-word — the reference's only on-screen text system.
    timeline: [(start_s, duration_s, text)].
    Returns the subtitled path, or final_mp4 unchanged on any failure.
    """
    try:
        job = Path(job_dir)
        lines = _build_srt_entries(timeline)
        if not lines:
            return str(final_mp4)
        srt = job / "subs.srt"
        srt.write_text("\n".join(lines), encoding="utf-8")
        subbed = job / "final_subtitled.mp4"
        filt = ("subtitles=" + srt.as_posix().replace(":", "\\:")
                .replace("'", "\\'") +
                ":force_style='FontSize=30,Bold=1,"
                "PrimaryColour=&HFFFFFF&,BorderStyle=3,"
                "BackColour=&HA0000000&,Alignment=2,MarginV=54'")
        rc, _so, se = ffmpeg.run([
            "-y", "-i", str(final_mp4), "-vf", filt,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "copy", str(subbed),
        ], timeout=1200)
        if rc == 0 and subbed.is_file():
            if logger:
                logger.log("    captions burned in (white on black box, "
                           "word-by-word)")
            return str(subbed)
        if logger:
            logger.log(f"    captions skipped (filter unavailable): "
                       f"{(se or '')[-120:]}")
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    captions skipped: {e}")
    return str(final_mp4)


def _overlay_bell(job_dir, final_mp4, logger=None):
    """Overlay the small gold subscribe-bell, bottom-right (best effort).

    The reference carries a persistent gold bell watermark in the
    bottom-right corner of nearly every shot. Returns the watermarked
    path, or final_mp4 unchanged on any failure.
    """
    try:
        from ..config import BUNDLE_DIR, ROOT
        bell = BUNDLE_DIR / "assets" / "bell.png"
        if not bell.is_file():
            bell = ROOT / "assets" / "bell.png"
        if not bell.is_file():
            return str(final_mp4)
        job = Path(job_dir)
        out = job / "final_bell.mp4"
        rc, _so, se = ffmpeg.run([
            "-y", "-i", str(final_mp4), "-i", str(bell),
            "-filter_complex",
            "[1:v]scale=92:92[b];[0:v][b]overlay=W-w-30:H-h-30:format=auto[v]",
            "-map", "[v]", "-map", "0:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "copy", str(out),
        ], timeout=1200)
        if rc == 0 and out.is_file():
            if logger:
                logger.log("    bell watermark overlaid (bottom-right)")
            return str(out)
        if logger:
            logger.log(f"    bell watermark skipped: {(se or '')[-120:]}")
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    bell watermark skipped: {e}")
    return str(final_mp4)


def _cut_piece(src, start, duration, out_stem, logger=None):
    """Cut [start, start+duration) from an audio file. Returns path or ''."""
    try:
        enc, out_path = ffmpeg.audio_track_args(str(out_stem))
        rc, _so, _se = ffmpeg.run([
            "-y", "-ss", f"{max(0.0, start):.2f}", "-t", f"{duration:.2f}",
            "-i", src, "-c:a", enc, "-ar", "44100", "-ac", "2", out_path,
        ], timeout=300)
        if rc == 0 and Path(out_path).is_file():
            return out_path
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _subtract(iv_start, iv_end, cuts):
    """Remove sorted (s, e) cut intervals from [iv_start, iv_end).

    Returns the remaining [(a, b)] pieces. Never raises.
    """
    pieces, cur = [], iv_start
    for s, e in sorted(cuts):
        if e <= cur or s >= iv_end:
            continue
        if s > cur:
            pieces.append((cur, min(s, iv_end)))
        cur = max(cur, e)
        if cur >= iv_end:
            break
    if cur < iv_end:
        pieces.append((cur, iv_end))
    return [(a, b) for a, b in pieces if b - a > 0.05]


def run(job_dir, segments, images, avatar_result, logger=None,
        subtitles=False, script=None, bell=True):
    """Assemble final.mp4. Returns (path, duration). Never raises."""
    job = Path(job_dir)
    seg_dir = job / "segments"
    try:
        seg_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    avatar_result = avatar_result or {}
    intro = avatar_result.get("intro") or ""
    mids = sorted(avatar_result.get("mids") or [],
                  key=lambda m: m.get("at", 0))

    # voiceover-time start of each beat
    vstarts, cum = [], 0.0
    for seg in segments:
        vstarts.append(cum)
        cum += seg.get("duration") or 0.0

    # avatar-spoken intervals in voiceover time: (start, end, clip_path)
    spoken = []
    if intro and Path(intro).is_file():
        d = ffmpeg.probe(intro)["duration"] or 0.0
        if d > 0.05:
            spoken.append((0.0, d, intro))
    for m in mids:
        p = m.get("file") or ""
        if p and Path(p).is_file():
            d = ffmpeg.probe(p)["duration"] or 0.0
            at = float(m.get("at") or 0.0)
            if d > 0.05:
                spoken.append((at, at + d, p))
    spoken.sort(key=lambda t: t[0])
    cuts = [(s, e) for s, e, _p in spoken]

    # merge: beat pieces (spoken slices removed) + avatar clips, in time order
    events = []  # (time, is_beat, payload)
    n = min(len(segments), len(images))
    for i in range(n):
        vs = vstarts[i]
        dur = segments[i].get("duration") or 0.0
        if dur <= 0:
            continue
        for a, b in _subtract(vs, vs + dur, cuts):
            events.append((a, True, (i, a - vs, b - a)))
    for s, _e, p in spoken:
        events.append((s, False, p))
    events.sort(key=lambda e: (e[0], 0 if e[1] else 1))

    hook_text = (script or {}).get("hook", "") if script else ""
    final_order, final_texts = [], []
    texted, piece_no = set(), 0
    for _t, is_beat, pay in events:
        if not is_beat:
            final_order.append(pay)
            final_texts.append(hook_text if pay == intro else None)
            continue
        i, off, dur = pay
        seg = segments[i]
        piece_audio = _cut_piece(seg["file"], off, dur,
                                 seg_dir / f"beat-{i:02d}-p{piece_no}")
        piece_no += 1
        if not piece_audio:
            if logger:
                logger.log(f"    assemble: skipping beat piece {i} "
                           f"(audio cut failed)")
            continue
        out = seg_dir / f"beat-{i:02d}-p{piece_no:02d}.mp4"
        if _beat_segment(images[i], piece_audio, out, dur, logger):
            final_order.append(str(out))
            if i in texted:
                final_texts.append(None)
            else:
                texted.add(i)
                final_texts.append(seg.get("text", ""))
        elif logger:
            logger.log(f"    assemble: skipping beat piece {i} "
                       f"(segment failed)")

    if not final_order:
        if logger:
            logger.log("    assemble: no segments — cannot build video")
        return "", 0.0

    # concat demuxer, stream copy
    lst = seg_dir / "concat.txt"
    try:
        with open(lst, "w", encoding="utf-8") as f:
            for p in final_order:
                f.write(f"file '{Path(p).as_posix()}'\n")
    except Exception:  # noqa: BLE001
        return "", 0.0

    final = job / "final.mp4"
    # Always re-encode — never stream-copy. Stream-copy silently produces
    # corrupt output when avatar clips (aac) and beat pieces (mp3) have
    # different codecs. Re-encoding is a little slower but never fails on
    # codec mismatch.
    rc, _so, se = ffmpeg.run([
        "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(final),
    ], timeout=1200)
    if rc != 0 or not final.is_file():
        if logger:
            logger.log(f"    assemble: FAILED to produce final.mp4: {(se or '')[-200:]}")
        return "", 0.0

    dur = ffmpeg.probe(final)["duration"]
    if logger:
        logger.log(f"    assemble: final.mp4 ({dur:.0f}s)")

    # reference-style burnt-in captions (per-channel toggle, default OFF)
    if subtitles:
        timeline = []
        t = 0.0
        for path, text in zip(final_order, final_texts):
            d = ffmpeg.probe(path)["duration"] or 0.0
            timeline.append((t, d, text))
            t += d
        final = Path(_burn_subtitles(job, final, timeline, logger))
        dur = ffmpeg.probe(final)["duration"] or dur

    # persistent gold bell watermark, bottom-right (reference mechanic)
    if bell:
        final = Path(_overlay_bell(job, final, logger))
        dur = ffmpeg.probe(final)["duration"] or dur

    return str(final), round(dur, 2)
