"""mib/stages/script.py — local rules-engine scriptwriter (free, offline).

title + target_minutes -> {hook, beats[{name, narration, image_prompt}],
cta, words, est_minutes}.

The *formula* comes from the channel's Pattern (mib/patterns.py): hook style,
beat map, rejoin transitions, CTA, image style. A channel with no custom
pattern gets the built-in "Classic Story" pattern.

Rules:
- hook: curiosity + emotion, <= ~18s (~40 words)
- beats: problem -> complication -> setback -> twist -> payoff -> landing
  (or whatever the channel's pattern defines)
- rejoins: mid-video avatar re-appearances each open with a transition line
  baked into that beat's narration (evenly spaced, never beat 0)
- CTA: subscribe + comment keyword
- narration ~140 wpm; TTS text sanitized (no headers/stage directions)
- image prompts: photorealistic, 16:9, no text, no watermarks
"""
import hashlib
import re

from ..patterns import (
    BEAT_DEFS,
    CTAS,
    DEFAULT_TRANSITIONS,
    HOOKS,
    IMG_SUFFIX,
    get_pattern,
    normalize_pattern,
)

WPM = 140


def sanitize(text):
    """Strip anything that should never be spoken: headers, stage directions,
    markdown, bracketed cues. Never raises."""
    try:
        t = str(text or "")
        t = re.sub(r"\[.*?\]", " ", t)          # [pause], [beat], ...
        t = re.sub(r"\(.*?\)", " ", t)          # (softly), ...
        t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)  # markdown headers
        t = re.sub(r"[*_~`>]", "", t)           # markdown chars
        t = re.sub(r"\s+", " ", t).strip()
        return t
    except Exception:  # noqa: BLE001
        return str(text or "")[:2000]


def _topic(title):
    t = sanitize(title)
    t = re.sub(r"^\d+\s*[-–:.]?\s*", "", t)
    return t or "this story"


def _pick(items, title, salt):
    h = int(hashlib.md5(f"{salt}:{title}".encode()).hexdigest(), 16)
    return items[h % len(items)]


def _fill(sentences, target_words, topic, seed=0):
    """Fill to target_words without repeating sentences back-to-back.

    FIX (Bug 3): the original cycled the same small list in order, so the
    same sentence appeared 4-5 times per beat. Now we shuffle the pool
    before each full cycle so every sentence is used once before any is
    reused, and no two identical sentences ever appear consecutively.
    Extra guard: if the last sentence of one shuffle cycle matches the
    first of the next, we swap the first with a random other position.
    """
    import random
    if not sentences:
        return str(topic)
    rng = random.Random(seed)
    pool = list(sentences)
    out, words, cycle = [], 0, 0
    last_sentence = ""
    while words < target_words:
        if cycle % len(pool) == 0:
            rng.shuffle(pool)
            # Prevent last-of-prev-cycle == first-of-new-cycle duplicate
            if pool and pool[0] == last_sentence and len(pool) > 1:
                swap_idx = rng.randint(1, len(pool) - 1)
                pool[0], pool[swap_idx] = pool[swap_idx], pool[0]
        s = pool[cycle % len(pool)].format(topic=topic)
        out.append(s)
        last_sentence = s
        words += len(s.split())
        cycle += 1
        if cycle > 120:                 # hard safety guard
            break
    return " ".join(out)


def _rejoin_beat_indexes(n_beats, rejoins):
    """Beat indexes (never 0) where mid-video rejoins open with a transition.

    Evenly spaced across the beats; deduped; clamped to 1..n-1. Never raises.
    """
    try:
        n, r = int(n_beats), int(rejoins)
        if n < 2 or r < 1:
            return []
        idxs = []
        for i in range(r):
            j = round((i + 1) * n / (r + 1))
            j = max(1, min(n - 1, j))
            if j not in idxs:
                idxs.append(j)
        return sorted(idxs)
    except Exception:  # noqa: BLE001
        return []


def build_script(title, target_minutes=5, channel=None, pattern=None,
                 rejoins=0, channel_id=None):
    """Build the full script dict. Never raises.

    pattern: a pattern dict (see mib/patterns.py); falls back to the
    channel's pattern (or the built-in preset for channel_id), then to
    the default.
    rejoins: number of mid-video avatar re-appearances; each gets a
    transition line baked into its beat's narration.
    """
    try:
        target_minutes = max(1, int(target_minutes or 5))
    except (TypeError, ValueError):
        target_minutes = 5
    pat = normalize_pattern(
        pattern if isinstance(pattern, dict) else get_pattern(channel, channel_id))
    hooks = pat.get("hook_templates") or HOOKS
    beats_def = pat.get("beats") or [
        {"name": n, "lines": list(lines), "scene": scene}
        for n, lines, scene in BEAT_DEFS]
    ctas = pat.get("cta_templates") or CTAS
    transitions = pat.get("rejoin_transitions") or DEFAULT_TRANSITIONS
    img_style = pat.get("image_style") or IMG_SUFFIX
    soft_promo = str(pat.get("soft_promo_line") or "").strip()

    topic = _topic(title)
    total_words = target_minutes * 145  # slight margin over 140 wpm
    hook_words = min(45, int(total_words * 0.12))
    cta_words = min(40, int(total_words * 0.08))
    n_beats = max(1, len(beats_def))
    beat_words = max(20, (total_words - hook_words - cta_words) // n_beats)

    hook = sanitize(_pick(hooks, title, "hook").format(topic=topic))
    # trim hook to word budget
    hw = hook.split()
    if len(hw) > hook_words + 10:
        hook = " ".join(hw[:hook_words + 10])

    rejoin_idxs = _rejoin_beat_indexes(n_beats, rejoins)
    rejoin_line = {idx: transitions[k % len(transitions)]
                   for k, idx in enumerate(rejoin_idxs)} if transitions else {}
    beats = []
    for idx, bdef in enumerate(beats_def):
        lines = bdef.get("lines") or []
        scene = bdef.get("scene") or ""
        narration = sanitize(_fill(lines, beat_words, topic))
        if idx in rejoin_line:
            narration = f"{sanitize(rejoin_line[idx])} {narration}"
        beats.append({
            "name": bdef.get("name") or f"beat-{idx+1}",
            "narration": narration,
            "image_prompt": f"{scene} illustrating: {topic}. {img_style}",
            "rejoin": idx in rejoin_line,
        })

    cta = sanitize(_fill([_pick(ctas, title, "cta")], cta_words, topic))

    # soft promo: one spoken line mid-video (audio + captions only, never
    # on-screen text) — the reference's affiliate/description-link mention.
    # Pattern-driven; empty by default so channels opt in deliberately.
    if soft_promo:
        try:
            pi = max(1, min(len(beats) - 1, len(beats) // 4))
            nar = beats[pi]["narration"]
            parts = re.split(r"(?<=[.!?])\s+", nar, maxsplit=1)
            if len(parts) == 2:
                beats[pi]["narration"] = (f"{parts[0]} {soft_promo} "
                                          f"{parts[1]}")
            else:
                beats[pi]["narration"] = f"{nar} {soft_promo}"
        except Exception:  # noqa: BLE001
            pass

    words = len(hook.split()) + sum(len(b["narration"].split()) for b in beats) \
        + len(cta.split())
    return {
        "title": sanitize(title),
        "topic": topic,
        "pattern_name": pat.get("name", ""),
        "hook": hook,
        "beats": beats,
        "cta": cta,
        "words": words,
        "est_minutes": round(words / WPM, 2),
    }


def save_script(job_dir, script):
    """Write script.json. Never raises (returns path or '')."""
    try:
        from pathlib import Path
        import json
        p = Path(job_dir) / "script.json"
        p.write_text(json.dumps(script, indent=2, ensure_ascii=False),
                     encoding="utf-8")
        return str(p)
    except Exception:  # noqa: BLE001
        return ""
