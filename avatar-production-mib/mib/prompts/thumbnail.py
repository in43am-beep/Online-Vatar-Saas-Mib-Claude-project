"""mib/prompts/thumbnail.py — THUMBNAIL PROMPT TEMPLATE.

Implements the user's THUMBNAIL prompt verbatim in spirit: the locked
Amish character (same face every time), farmhouse interior, 40/60
composition, max-3-word overlay text auto-derived from the video title.

Pure functions — no network, no keys.
"""
import re

CHARACTER_SPEC = (
    "MAIN CHARACTER: a close-up portrait of an Amish man looking "
    "directly into the camera with a neutral expression. He has thick "
    "dark eyebrows, brown eyes, and a long full salt-and-pepper beard "
    "without a mustache. He wears a wide-brimmed straw hat with a black "
    "band, a white collared shirt, and black suspenders."
)

BACKGROUND_SPEC = (
    "BACKGROUND: rustic Amish farmhouse interior with white walls, "
    "wooden window frames, sheer curtains, a vintage Singer treadle "
    "sewing machine, a wooden dresser with oil lamps, and hanging "
    "wooden kitchen tools."
)

STYLE_SPEC = (
    "STYLE: photorealistic, cinematic lighting, extremely detailed "
    "face, high contrast, HDR, professional YouTube thumbnail, vibrant "
    "colours, sharp focus, 8K quality."
)

COMPOSITION_SPEC = (
    "COMPOSITION: the character occupies 40% of the frame; the problem "
    "or solution occupies the remaining 60% of the frame. Large clear "
    "visual storytelling, no clutter, strong visual hierarchy."
)

TEXT_RULE = (
    "TEXT: maximum 3 words of large bold yellow or white letters, easy "
    "to read on mobile."
)

_STOPWORDS = frozenset(
    "the a an and or but of to in on for with from at by is are was were "
    "be been being it its this that these those as we you they he she him "
    "her them us our your their my me do does did not no yes if then than "
    "so such just only how why what when where who which will would can "
    "could should there here out up down over under again very much more "
    "most into like get without".split())

_EXPRESSION_KEYWORDS = [
    ("concerned", ("kill", "dead", "warning", "danger", "snake", "rat",
                   "rodent", "infest", "emergency", "mistake")),
    ("surprised", ("secret", "shocked", "nobody", "ancient", "forgotten",
                   "hidden", "truth", "never knew")),
    ("serious", ("never", "stop", "wrong", "lies", "myth", "scam",
                 "waste")),
]


def derive_overlay_text(title):
    """Derive thumbnail overlay text: <=3 words, UPPERCASE, from the title.

    Drops stopwords, keeps the meatiest content words in order. Never
    raises; never returns more than 3 words.
    """
    try:
        words = re.findall(r"[A-Za-z$][A-Za-z$']*", str(title or ""))
        picked = []
        for w in words:
            wl = w.lower().strip("'")
            if len(wl) < 3 or wl in _STOPWORDS:
                continue
            if wl not in (p.lower() for p in picked):
                picked.append(w.upper().strip("'"))
            if len(picked) == 3:
                break
        if not picked:
            # fallback: first 3 raw words, uppercased
            picked = [w.upper() for w in words[:3]]
        return " ".join(picked[:3])
    except Exception:  # noqa: BLE001
        return ""


def detect_expression(title):
    """Pick the character expression from the title topic.

    Returns one of: concerned, surprised, serious, confident.
    Never raises.
    """
    try:
        t = str(title or "").lower()
        for expr, keys in _EXPRESSION_KEYWORDS:
            if any(k in t for k in keys):
                return expr
        return "confident"
    except Exception:  # noqa: BLE001
        return "confident"


def build_prompt(title, topic_visual="", expression=""):
    """Build the full thumbnail prompt. Never raises."""
    try:
        expr = (expression or detect_expression(title)).strip() or "confident"
        overlay = derive_overlay_text(title)
        visual = (topic_visual or "").strip()
        problem = (f"PROBLEM/SOLUTION VISUAL (60% of frame): {visual}. "
                   if visual else
                   "PROBLEM/SOLUTION VISUAL (60% of frame): a clear "
                   "dramatic visual of the video's problem or solution "
                   "beside the character. ")
        return (
            "Create an ultra-realistic YouTube thumbnail.\n"
            f"{CHARACTER_SPEC}\n"
            f"{BACKGROUND_SPEC}\n"
            f"{STYLE_SPEC}\n"
            f"{COMPOSITION_SPEC}\n"
            f"{problem}"
            f"EXPRESSION: {expr}.\n"
            f"{TEXT_RULE} Overlay text: \"{overlay}\".\n"
            "The thumbnail must instantly communicate curiosity and a "
            "hidden secret."
        )
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Channel-avatar thumbnails: 1 title = 1 thumbnail, starring the user's avatar.
# ---------------------------------------------------------------------------

AVATAR_COMPOSITION_SPEC = (
    "COMPOSITION: the channel avatar is the hero of the thumbnail — "
    "large in the foreground, head and shoulders clearly visible, "
    "looking directly into the camera. The video's problem/solution "
    "visual sits beside or behind the avatar, smaller, supporting the "
    "story — never competing with the avatar. No clutter, strong "
    "visual hierarchy, instant readability at small mobile size."
)


def build_avatar_prompt(title, channel_id, topic_visual="", expression=""):
    """Build ONE thumbnail prompt for ONE title, starring the channel avatar.

    Uses the channel's character sheet (Settings → Channels → Character
    sheet… — the exact avatar the user put in the pipeline) as the
    identity lock, instead of the hardcoded default character in
    build_prompt().

    Rule: 1 title → exactly 1 thumbnail. This function always returns a
    single prompt string; the pipeline calls it once per video.

    Falls back to build_prompt() when the channel has no character sheet
    (default behaviour unchanged). Never raises.
    """
    try:
        from .. import character as charmod
        id_block = charmod.identity_block(channel_id or "")
    except Exception:  # noqa: BLE001
        id_block = ""
    try:
        if not (id_block or "").strip():
            return build_prompt(title, topic_visual, expression)
        expr = ((expression or detect_expression(title)).strip()
                or "confident")
        overlay = derive_overlay_text(title)
        visual = (topic_visual or "").strip()
        problem = (f"PROBLEM/SOLUTION VISUAL: {visual}, placed beside or "
                   f"behind the avatar. "
                   if visual else
                   "PROBLEM/SOLUTION VISUAL: a clear dramatic visual of "
                   "the video's problem or solution beside/behind the "
                   "avatar. ")
        return (
            "Create an ultra-realistic YouTube thumbnail, 16:9.\n"
            f"{id_block}\n"
            "AVATAR STAGING: the channel avatar is fully visible — head "
            "and shoulders, facing the camera, with a "
            f"{expr} expression that matches the video's emotion. The "
            "avatar must look like the identical person from the "
            "character reference in every thumbnail.\n"
            f"{AVATAR_COMPOSITION_SPEC}\n"
            f"{STYLE_SPEC}\n"
            f"{problem}"
            f"{TEXT_RULE} Overlay text: \"{overlay}\".\n"
            "The thumbnail must instantly communicate curiosity and a "
            "hidden secret, with the avatar as the recognisable face of "
            "the channel."
        )
    except Exception:  # noqa: BLE001
        return build_prompt(title, topic_visual, expression)
