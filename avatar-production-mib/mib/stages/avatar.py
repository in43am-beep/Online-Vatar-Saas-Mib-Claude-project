"""mib/stages/avatar.py — presenter clips in the reference style.

Decoded from the frame-by-frame study of the reference video
(Elias Gardener, "The Secret Liquid That Melts Leaves Into Compost in
Just Days!", 22:11):

- Cold open: the video starts IMMEDIATELY on a full-screen tight face
  close-up of the presenter (no title card, no ident). The hook line
  begins at 0:00.
- Chapter openings get LONG presenter-led segments (30-70s): they open
  full-screen close-up, then cut to a 50/50 SPLIT-SCREEN with the
  presenter on the RIGHT and B-roll on the LEFT.
- Mid-chapter beats get SHORT split-screen interludes (~5-10s).
- The presenter returns roughly every 1-3 minutes; every appearance
  speaks NEW, continuing script (never repeats a line).
- ALL transitions between presenter shots are hard cuts — no fades,
  dissolves or slides.
- The presenter "set" is one static room; framing is a tight face
  close-up both full-screen and in the split-screen right half.

Never raises.
"""
from pathlib import Path

from .. import ffmpeg
from ..config import ROOT
try:
    from ..config import BUNDLE_DIR as _BUNDLE_DIR
except ImportError:
    _BUNDLE_DIR = ROOT

# reference-derived timing constants
CHAPTER_MAX_S = 45.0    # chapter segments never run longer than this
CHAPTER_CLOSEUP_S = 12.0  # full-screen close-up opens each chapter segment
INTERLUDE_S = 7.0       # short mid-chapter split-screen check-ins
GAP_TRIGGER_S = 110.0   # a gap this big between presenter spots gets an interlude
MIN_CHAPTER_S = 8.0     # beats shorter than this get no chapter segment


def _resolve_image(presenter):
    """Presenter image path -> existing PNG, else a generated placeholder.

    FIX (Bug 4): in a PyInstaller exe ROOT resolves to %APPDATA% but
    bundled images live under BUNDLE_DIR (the temp extract folder).
    We now check both locations so the presenter PNG is always found.
    """
    try:
        rel = (presenter or {}).get("image") or ""
        if rel:
            for base in (ROOT, _BUNDLE_DIR):
                p = base / rel
                if p.is_file():
                    return str(p)
    except Exception:  # noqa: BLE001
        pass
    # fallback: first placeholder that exists in either base dir
    try:
        for base in (ROOT, _BUNDLE_DIR):
            av = base / "assets" / "avatars"
            for cand in ("maria.png", "walter.png", "priya.png"):
                if (av / cand).is_file():
                    return str(av / cand)
            pngs = sorted(av.glob("*.png"))
            if pngs:
                return str(pngs[0])
    except Exception:  # noqa: BLE001
        pass
    return ""


def _closeup_clip(image_path, audio_path, out_path, duration, logger=None):
    """Full-screen tight face close-up (cold open / chapter openings).

    Slow push-in centred on the face (upper third), like the reference's
    forehead-to-beard framing. Returns True on success. Never raises.
    """
    try:
        duration = max(2.0, float(duration))
        rc, _so, se = ffmpeg.run([
            "-y",
            "-framerate", "30", "-loop", "1", "-t", f"{duration:.2f}",
            "-i", image_path,
            "-i", audio_path,
            "-filter_complex",
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "zoompan=z='min(1.30+0.0009*on,1.45)':"
            "x='iw/2-(iw/zoom/2)':y='ih*0.36-(ih/zoom/2)':"
            "d=1:s=1920x1080:fps=30[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{duration:.2f}",
            str(out_path),
        ], timeout=600)
        ok = rc == 0 and Path(out_path).is_file()
        if not ok and logger:
            logger.log(f"    avatar close-up failed: {(se or '')[-200:]}")
        return ok
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    avatar close-up error: {e}")
        return False


def _split_clip(presenter_image, broll_image, audio_path, out_path,
                duration, logger=None):
    """50/50 split-screen: B-roll LEFT, presenter RIGHT (tight crop).

    Straight vertical divide, hard edges, presenter always on the right —
    the reference's only split layout. Returns True on success.
    Never raises.
    """
    try:
        duration = max(2.0, float(duration))
        rc, _so, se = ffmpeg.run([
            "-y",
            "-framerate", "30", "-loop", "1", "-t", f"{duration:.2f}",
            "-i", broll_image,
            "-framerate", "30", "-loop", "1", "-t", f"{duration:.2f}",
            "-i", presenter_image,
            "-i", audio_path,
            "-filter_complex",
            "[0:v]scale=960:1080:force_original_aspect_ratio=increase,"
            "crop=960:1080,"
            "zoompan=z='min(1+0.0007*on,1.10)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            "d=1:s=960x1080:fps=30[b];"
            "[1:v]scale=960:1080:force_original_aspect_ratio=increase,"
            "crop=960:1080,"
            "zoompan=z='min(1.30+0.0009*on,1.45)':"
            "x='iw/2-(iw/zoom/2)':y='ih*0.36-(ih/zoom/2)':"
            "d=1:s=960x1080:fps=30[p];"
            "[b][p]hstack=inputs=2[v]",
            "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-t", f"{duration:.2f}",
            str(out_path),
        ], timeout=600)
        ok = rc == 0 and Path(out_path).is_file()
        if not ok and logger:
            logger.log(f"    avatar split-screen failed: {(se or '')[-200:]}")
        return ok
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    avatar split-screen error: {e}")
        return False


def _concat_parts(parts, out_path, logger=None):
    """Hard-cut concat of rendered parts (stream copy). Never raises."""
    try:
        lst = Path(str(out_path) + ".txt")
        with open(lst, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{Path(p).as_posix()}'\n")
        rc, _so, se = ffmpeg.run([
            "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c", "copy", str(out_path),
        ], timeout=300)
        ok = rc == 0 and Path(out_path).is_file()
        if not ok and logger:
            logger.log(f"    avatar concat failed: {(se or '')[-200:]}")
        return ok
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    avatar concat error: {e}")
        return False


def _cut_audio(src, start, duration, out_stem):
    """Cut a slice of the voiceover. Returns the output path or ''."""
    try:
        enc, out_path = ffmpeg.audio_track_args(str(out_stem))
        rc, _so, _se = ffmpeg.run([
            "-y", "-ss", f"{max(0.0, start):.2f}", "-t", f"{duration:.2f}",
            "-i", src, "-c:a", enc, "-ar", "44100", "-ac", "2",
            out_path,
        ], timeout=300)
        if rc == 0 and Path(out_path).is_file():
            return out_path
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _segment_at(t, starts, durs):
    """Index of the voice segment containing voiceover-time t."""
    try:
        for i, (s, d) in enumerate(zip(starts, durs)):
            if s <= t < s + d:
                return i
        return len(starts) - 1 if starts else 0
    except Exception:  # noqa: BLE001
        return 0


def plan_segments(total, seg_starts, seg_durs, rejoin_seg_idxs,
                  seconds=6, appearances=1):
    """Decide where the presenter appears. Pure function (unit-testable).

    Returns a list of dicts, each:
      {kind: "intro"|"chapter"|"interlude", at, dur, closeup_s, seg_idx}
    - intro: cold open at 0.0, full-screen close-up, `seconds` long.
    - chapter: at each rejoin beat's start; opens full-screen close-up for
      `closeup_s`, then split-screen for the rest (up to CHAPTER_MAX_S).
    - interlude: short split-screen check-ins dropped into gaps > 110s.
    Total mid-video spots are capped at appearances-1 (intro always kept).
    Never raises.
    """
    try:
        total = max(1.0, float(total or 0))
        seconds = min(15.0, max(2.0, float(seconds or 6)))
        appearances = max(1, int(appearances or 1))
    except (TypeError, ValueError):
        return [{"kind": "intro", "at": 0.0, "dur": 6.0,
                 "closeup_s": 6.0, "seg_idx": 0}]

    plan = [{
        "kind": "intro", "at": 0.0,
        "dur": min(seconds, total * 0.6),
        "closeup_s": min(seconds, total * 0.6),
        "seg_idx": 0,
    }]

    # chapter segments at rejoin beats
    for si in sorted(set(rejoin_seg_idxs or [])):
        try:
            si = int(si)
        except (TypeError, ValueError):
            continue
        if si < 1 or si >= len(seg_durs):
            continue
        start = float(seg_starts[si])
        if start < plan[0]["dur"] - 0.5:
            continue  # never overlap the cold open
        dur = min(CHAPTER_MAX_S, float(seg_durs[si] or 0))
        if dur < MIN_CHAPTER_S:
            continue
        closeup = min(CHAPTER_CLOSEUP_S, dur * 0.4)
        plan.append({"kind": "chapter", "at": round(start, 2),
                     "dur": round(dur, 2), "closeup_s": round(closeup, 2),
                     "seg_idx": si})

    plan.sort(key=lambda p: p["at"])

    # interludes: fill big gaps so the presenter returns every 1-3 min
    if appearances > 1:
        placed = sorted(plan, key=lambda p: p["at"])
        bounds = [(p["at"], p["at"] + p["dur"]) for p in placed]
        bounds.append((total, total))  # tail gap check
        extras = []
        prev_end = bounds[0][1]
        for s, e in bounds[1:]:
            gap = s - prev_end
            if gap > GAP_TRIGGER_S:
                mid = prev_end + gap / 2.0
                at = max(prev_end + 1.0, mid - INTERLUDE_S / 2.0)
                if at + INTERLUDE_S < s - 1.0:
                    extras.append({
                        "kind": "interlude", "at": round(at, 2),
                        "dur": INTERLUDE_S, "closeup_s": 0.0,
                        "seg_idx": _segment_at(mid, seg_starts, seg_durs),
                    })
            prev_end = max(prev_end, e)
        plan.extend(extras)
        plan.sort(key=lambda p: p["at"])

    # cap mid-video spots at appearances-1; intro is always kept.
    # Chapters (real content boundaries) win over gap-fill interludes.
    chapters = [p for p in plan if p["kind"] == "chapter"]
    interludes = [p for p in plan if p["kind"] == "interlude"]
    slots = max(0, appearances - 1)
    mids = chapters[:slots]
    mids += interludes[:max(0, slots - len(mids))]
    plan = [plan[0]] + sorted(mids, key=lambda p: p["at"])
    return plan


def _legacy_plan(total, seconds, appearances):
    """Fallback when no script/segment map is available (old behaviour)."""
    plan = [{
        "kind": "intro", "at": 0.0,
        "dur": min(seconds, total * 0.6),
        "closeup_s": min(seconds, total * 0.6),
        "seg_idx": 0,
    }]
    if appearances > 1 and total > seconds * 2:
        for i in range(1, appearances):
            start = (i / appearances) * total
            plan.append({"kind": "interlude", "at": round(start, 2),
                         "dur": seconds, "closeup_s": 0.0, "seg_idx": 0})
    return plan


def run(job_dir, voiceover_path, presenter, seconds=6, appearances=1,
        total_duration=0.0, logger=None,
        voice_segments=None, script=None, images=None):
    """Build presenter clips. Returns dict. Never raises.

    voice_segments: voiceover stage segments [{name, duration, ...}]
    script: script dict (beats carry rejoin flags)
    images: per-segment B-roll image paths (for split-screen left halves)
    """
    job = Path(job_dir)
    avatar_dir = job / "avatar"
    try:
        avatar_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    image = _resolve_image(presenter)
    if not image:
        if logger:
            logger.log("    avatar: no presenter image found — skipping intro")
        return {"intro": "", "mids": [],
                "presenter": (presenter or {}).get("name", "")}

    try:
        seconds = min(15.0, max(2.0, float(seconds or 6)))
    except (TypeError, ValueError):
        seconds = 6.0
    try:
        appearances = int(appearances or 1)
    except (TypeError, ValueError):
        appearances = 1
    appearances = max(1, min(6, appearances))
    total = max(1.0, float(total_duration or 0))

    name = (presenter or {}).get("name", "presenter")
    result = {"intro": "", "mids": [], "presenter": name}
    images = list(images or [])

    # build the voiceover-time map when we have the real data
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
            # voice segments: [hook, beat-0..beat-(n-1), cta]
            rejoin_idxs = [i + 1 for i, b in enumerate(beats)
                           if b.get("rejoin")]
            plan = plan_segments(total or cum, starts, durs, rejoin_idxs,
                                 seconds=seconds, appearances=appearances)
    except Exception:  # noqa: BLE001
        plan = None
    if not plan:
        plan = _legacy_plan(total, seconds, appearances)

    def broll_for(seg_idx):
        try:
            if 0 <= seg_idx < len(images) and Path(images[seg_idx]).is_file():
                return images[seg_idx]
        except Exception:  # noqa: BLE001
            pass
        return ""

    # Build render tasks for parallel execution (3× speed improvement)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _render_spot(n, spot):
        """Render one avatar spot. Returns (n, kind, at, out_path_or_empty)."""
        kind, at, dur = spot["kind"], spot["at"], spot["dur"]
        closeup_s = spot.get("closeup_s") or 0.0
        tag = "intro" if kind == "intro" else f"{kind}-{n}"
        audio = _cut_audio(voiceover_path, at, dur,
                           avatar_dir / f"{tag}-audio")
        if not audio:
            return n, kind, at, ""
        out = avatar_dir / f"{tag}.mp4"
        ok = False
        if kind == "intro" or (kind == "chapter" and closeup_s >= dur - 0.5):
            ok = _closeup_clip(image, audio, out, dur, logger)
        elif kind == "chapter":
            split_s = max(2.0, dur - closeup_s)
            a1 = _cut_audio(voiceover_path, at, closeup_s,
                            avatar_dir / f"{tag}-a1")
            a2 = _cut_audio(voiceover_path, at + closeup_s, split_s,
                            avatar_dir / f"{tag}-a2")
            p1, p2 = avatar_dir / f"{tag}-p1.mp4", avatar_dir / f"{tag}-p2.mp4"
            broll = broll_for(spot.get("seg_idx", 0)) or image
            if a1 and a2 \
                    and _closeup_clip(image, a1, p1, closeup_s, logger) \
                    and _split_clip(image, broll, a2, p2, split_s, logger):
                ok = _concat_parts([p1, p2], out, logger)
        else:
            broll = broll_for(spot.get("seg_idx", 0)) or image
            ok = _split_clip(image, broll, audio, out, dur, logger)
        return n, kind, at, str(out) if ok else ""

    # Render all spots in parallel — max 3 FFmpeg workers at once
    rendered = {}
    try:
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {
                ex.submit(_render_spot, n, spot): n
                for n, spot in enumerate(plan)
            }
            for future in as_completed(futures):
                try:
                    n, kind, at, out_path = future.result()
                    rendered[n] = (kind, at, out_path)
                except Exception as e:  # noqa: BLE001
                    nn = futures[future]
                    if logger:
                        logger.log(f"    avatar spot {nn} raised: {e}")
                    rendered[nn] = ("unknown", 0.0, "")
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    avatar: parallel render error: {e} — "
                       "falling back to sequential")
        for n, spot in enumerate(plan):
            try:
                n2, kind, at, out_path = _render_spot(n, spot)
                rendered[n] = (kind, at, out_path)
            except Exception:  # noqa: BLE001
                rendered[n] = ("unknown", 0.0, "")

    # Collect results in plan order
    for n in sorted(rendered):
        kind, at, out_path = rendered[n]
        if not out_path:
            if logger:
                logger.log(f"    avatar: spot {n} render failed — skipping")
            continue
        entry = {"file": out_path, "at": round(at, 2), "kind": kind}
        if kind == "intro":
            result["intro"] = out_path
            if logger:
                spot = plan[n]
                logger.log(f"    avatar intro: {name} "
                           f"({spot['dur']:.0f}s, close-up cold open)")
        else:
            result["mids"].append(entry)
            if logger:
                spot = plan[n]
                if kind == "chapter":
                    logger.log(f"    avatar chapter at {at:.0f}s "
                               f"({spot['dur']:.0f}s: close-up → split-screen)")
                else:
                    logger.log(f"    avatar interlude at {at:.0f}s "
                               f"({spot['dur']:.0f}s split-screen)")

    result["mids"].sort(key=lambda m: m.get("at", 0))
    return result
