"""mib/thumbnail.py — Actual thumbnail generation (PNG, not just a text prompt).

Frontier generates real thumbnail images. This module does the same:
  1. Pillow template (free, always works): title text + gradient + presenter face
  2. Gemini image (paid): full AI-generated thumbnail from the prompt

Output: thumbnail.png (1280x720, YouTube standard)
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THUMB_W, THUMB_H = 1280, 720


def _font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "arial.ttf"] if bold \
        else ["DejaVuSans.ttf", "arial.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def _wrap(text, draw, font, max_w):
    """Word-wrap text to fit max_w pixels wide. Returns list of lines."""
    words = str(text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines[:4]  # max 4 lines


def generate_pillow_thumbnail(title, out_path, channel_name="",
                               presenter_image=None, seed=0):
    """Generate a YouTube-style thumbnail using Pillow.

    Layout:
      - Dark gradient background
      - Bold title text (large, left-aligned or centered)
      - Optional presenter face (right side)
      - Channel name watermark (small, bottom)
      - Gold accent bar

    Cost: $0.00 — free forever.
    Never raises.
    """
    try:
        rng = random.Random(seed)
        img = Image.new("RGB", (THUMB_W, THUMB_H))
        draw = ImageDraw.Draw(img)

        # Gradient background
        top_col = tuple(rng.randint(8, 25) for _ in range(3))
        bot_col = tuple(rng.randint(15, 40) for _ in range(3))
        for y in range(THUMB_H):
            t = y / THUMB_H
            col = tuple(int(top_col[i] + (bot_col[i] - top_col[i]) * t)
                        for i in range(3))
            draw.line([(0, y), (THUMB_W, y)], fill=col)

        # Vignette circles
        for _ in range(8):
            x = rng.randint(0, THUMB_W)
            y = rng.randint(0, THUMB_H)
            r = rng.randint(150, 500)
            shade = rng.randint(5, 20)
            draw.ellipse([x-r, y-r, x+r, y+r], fill=(shade, shade, shade+6))

        # Presenter face (right half)
        has_face = False
        text_max_w = THUMB_W - 60
        if presenter_image and Path(presenter_image).is_file():
            try:
                face = Image.open(presenter_image).convert("RGBA")
                # Fit to right half of thumbnail
                face_w = THUMB_W // 2
                face_h = THUMB_H
                face = face.resize((face_w, face_h), Image.LANCZOS)
                img.paste(face, (THUMB_W - face_w, 0),
                          face if face.mode == "RGBA" else None)
                text_max_w = THUMB_W // 2 - 40
                has_face = True
            except Exception:  # noqa: BLE001
                pass

        # Gold accent bar
        gold = (212, 162, 78)
        draw.rectangle([40, THUMB_H - 100, text_max_w, THUMB_H - 94],
                        fill=gold)

        # Title text
        fnt_title = _font(72, bold=True)
        lines = _wrap(title, draw, fnt_title, text_max_w - 40)
        y_text = max(120, THUMB_H // 2 - len(lines) * 80 // 2)
        for line in lines:
            # Shadow
            draw.text((42, y_text + 2), line, font=fnt_title,
                       fill=(0, 0, 0, 180))
            # Gold text
            draw.text((40, y_text), line, font=fnt_title, fill=gold)
            y_text += 84

        # Channel name watermark
        if channel_name:
            fnt_ch = _font(28)
            draw.text((44, THUMB_H - 56), channel_name.upper(),
                       font=fnt_ch, fill=(160, 155, 145))

        img.save(str(out_path), "PNG")
        return str(out_path)

    except Exception as e:  # noqa: BLE001
        # Absolute fallback: black frame
        try:
            Image.new("RGB", (THUMB_W, THUMB_H), (12, 14, 20)).save(
                str(out_path), "PNG")
        except Exception:  # noqa: BLE001
            pass
        return str(out_path)


def generate_thumbnail(job_dir, script, channel_id, cfg, secrets,
                        presenter_image=None, logger=None):
    """Main thumbnail generation entry point.

    Tries Gemini image API first (if key available), falls back to Pillow.
    Always writes thumbnail.png. Returns path. Never raises.
    """
    job = Path(job_dir)
    out = job / "thumbnail.png"
    title = script.get("title", "")
    channels = (cfg or {}).get("channels", {})
    channel = channels.get(channel_id, {})
    channel_name = channel.get("name", channel_id)
    img_prompt = script.get("thumbnail_prompt", "")

    # Try Gemini image for thumbnail (high quality)
    try:
        secrets = secrets or {}
        gemini_key = (
            (secrets.get("gemini_api_keys") or "").strip().splitlines()[0].strip()
            or (secrets.get("gemini_api_key") or "").strip()
        )
        if gemini_key and img_prompt:
            from .providers.genimages import generate_gemini
            thumb_prompt = (
                f"YouTube thumbnail, no text overlay, eye-catching: {img_prompt}. "
                "16:9 ratio, 1280x720 equivalent, high contrast, dramatic lighting."
            )
            generate_gemini(gemini_key, None, thumb_prompt, str(out))
            # Resize to exact thumbnail dimensions
            img = Image.open(out).convert("RGB")
            img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            img.save(str(out), "PNG")
            if logger:
                logger.log("    thumbnail: Gemini image generated")
            return str(out)
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    thumbnail: Gemini failed ({e}) — using Pillow")

    # Fallback: Pillow template (always works, free)
    path = generate_pillow_thumbnail(
        title, out,
        channel_name=channel_name,
        presenter_image=presenter_image,
        seed=abs(hash(title)) % 999999,
    )
    if logger:
        logger.log(f"    thumbnail: Pillow template generated — {out.name}")
    return path
