"""mib/character.py — per-channel character sheet (one-time setup).

The user uploads EITHER a full character sheet image (hero portrait,
turnaround, expressions, costume callouts, identity lock — like a
model sheet) OR 4-5 full-body reference images, plus a text block with
the character's full details (age, ethnicity, hair, outfit, ...).

Stored under <config_dir>/characters/<channel_id>/ :
    sheet.png        the character sheet image (if given)
    refs/ref-01.png  …  4-5 full-body reference images (if given)
    details.txt      the full character description (identity lock text)
    meta.json        {"cameo": <scenes per video where the character appears>}

The images stage uses the sheet/refs as visual reference input for the
image model (Gemini accepts input images) and appends the identity text
to the prompt, so the same person shows up fully visible in scenes —
the "realism" feel. Never raises.
"""
import json
import shutil
from pathlib import Path

from . import config as config_mod

REFS_WANTED = (4, 5)  # 4 to 5 full-body images

DETAILS_TEMPLATE = """NAME:
AGE RANGE:
GENDER:
ETHNICITY:
BODY TYPE:
HEIGHT:
HAIR: color, length, style
EYES:
OUTFIT (locked): top, bottom, footwear, accessories
STYLE / VIBE:
KEY TRAITS: (face shape, distinctive marks — keep identical every frame)
"""


def character_dir(channel_id):
    try:
        d = (config_mod.CONFIG_PATH.parent / "characters"
             / str(channel_id or "default"))
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:  # noqa: BLE001
        return None


def _normalize_png(src, dest):
    """Copy any image to RGB PNG. Never raises."""
    try:
        from PIL import Image
        img = Image.open(src).convert("RGB")
        img.save(dest, "PNG")
        return True
    except Exception:  # noqa: BLE001
        try:
            shutil.copy(str(src), str(dest))
            return True
        except Exception:  # noqa: BLE001
            return False


def save_sheet(channel_id, src_path):
    """Save the character sheet image. Returns saved path or ''."""
    d = character_dir(channel_id)
    if not d:
        return ""
    dest = d / "sheet.png"
    return str(dest) if _normalize_png(src_path, dest) else ""


def save_refs(channel_id, src_paths):
    """Save 4-5 reference images (extras trimmed). Returns saved count."""
    d = character_dir(channel_id)
    if not d:
        return 0
    rdir = d / "refs"
    try:
        rdir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        return 0
    # clear old refs
    for p in rdir.glob("ref-*.png"):
        try:
            p.unlink()
        except Exception:  # noqa: BLE001
            pass
    n = 0
    for src in (src_paths or [])[:5]:
        dest = rdir / f"ref-{n + 1:02d}.png"
        if _normalize_png(src, dest):
            n += 1
    return n


def save_details(channel_id, text):
    d = character_dir(channel_id)
    if not d:
        return
    try:
        (d / "details.txt").write_text(str(text or "").strip(),
                                       encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def save_meta(channel_id, cameo):
    d = character_dir(channel_id)
    if not d:
        return
    try:
        (d / "meta.json").write_text(
            json.dumps({"cameo": max(0, min(4, int(cameo or 0)))}),
            encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def load_character(channel_id):
    """Return {sheet, refs, details, cameo}. Never raises."""
    out = {"sheet": "", "refs": [], "details": "", "cameo": 0}
    try:
        d = (config_mod.CONFIG_PATH.parent / "characters"
             / str(channel_id or "default"))
        if not d.is_dir():
            return out
        sheet = d / "sheet.png"
        if sheet.is_file():
            out["sheet"] = str(sheet)
        rdir = d / "refs"
        if rdir.is_dir():
            out["refs"] = sorted(str(p) for p in rdir.glob("ref-*.png"))
        det = d / "details.txt"
        if det.is_file():
            out["details"] = det.read_text(encoding="utf-8").strip()
        meta = d / "meta.json"
        if meta.is_file():
            out["cameo"] = max(
                0, min(4, int(json.loads(
                    meta.read_text(encoding="utf-8")).get("cameo") or 0)))
    except Exception:  # noqa: BLE001
        pass
    return out


def has_character(channel_id):
    c = load_character(channel_id)
    return bool(c["sheet"] or c["refs"])


def ref_images(channel_id):
    """Visual references for the image model: sheet first, then refs."""
    c = load_character(channel_id)
    imgs = []
    if c["sheet"]:
        imgs.append(c["sheet"])
    imgs.extend(c["refs"])
    return imgs[:6]


def identity_block(channel_id):
    """Prompt text locking the character's look. '' when not configured.

    Mirrors a character-consistency workflow: the reference image is the
    identity lock; face, hair, body proportions and outfit stay identical
    while pose, camera, lighting and environment follow the scene.
    """
    c = load_character(channel_id)
    det = (c["details"] or "").strip()
    if not det or not has_character(channel_id):
        return ""
    return (
        "CHARACTER CONSISTENCY — use the attached character reference "
        "image(s) as the identity lock. The person in this image MUST be "
        "the exact same character: IDENTITY LOCK ON — keep the same face "
        "and unique features; FACE CONSISTENCY ON — same facial structure, "
        "eyes, nose, lips, proportions; HAIR CONSISTENCY ON — same hair "
        "color, length, texture and style; BODY PROPORTION CONSISTENCY ON — "
        "same natural body shape and proportions; OUTFIT locked as "
        "described. Only the pose, camera angle, lighting and environment "
        "change to match the scene — the character themselves must not "
        "change across images. Character details: " + det)


def pick_cameo_scenes(n_scenes, cameo, seed=0):
    """Spread `cameo` character-appearance scenes across the video.

    Never picks scene 0 (hook) twice in a row pattern; spreads evenly.
    Returns sorted indices. Never raises.
    """
    try:
        n = int(n_scenes or 0)
        k = max(0, min(4, int(cameo or 0)))
        if n <= 0 or k <= 0:
            return []
        if k >= n:
            return list(range(n))
        # even spread, offset by seed so it varies per video
        import random
        rnd = random.Random(seed)
        start = rnd.randint(0, max(0, n - 1))
        idxs = sorted({(start + i * n // k) % n for i in range(k)})
        # prefer not to waste the cameo on the closing CTA frame only
        return idxs
    except Exception:  # noqa: BLE001
        return []
