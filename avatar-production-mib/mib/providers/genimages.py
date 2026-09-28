"""mib/providers/genimages.py — AI image generation with free local fallback.

Provider order: grok -> gemini -> local (Pillow title card).
The pipeline must NEVER crash on a provider failure: every provider raises
ImageError on failure and make_image() falls through to the local fallback,
which cannot fail (Pillow only).

Cost: paid calls are logged via mib.costs (no-op safe).
"""
import base64
import io
import random
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .. import costs
from .. import config as config_mod
from ..keypool import (KeyExhausted as _KeyExhausted,
                       KeyRejected as _KeyRejected, pool_from_secrets)

W, H = 1920, 1080


class ImageError(Exception):
    """Clean, UI-safe error."""


class _PoolExhausted(_KeyExhausted, ImageError):
    """429/quota: the KeyPool rotates to the next key."""


class _PoolRejected(_KeyRejected, ImageError):
    """401/403: the KeyPool parks this key and tries the next."""


def _raise_for_status(who, resp):
    if resp.status_code == 429:
        raise _PoolExhausted(
            f"{who} rate limit / quota hit — trying next key.")
    if resp.status_code in (401, 403):
        raise _PoolRejected(
            f"{who} refused this key (HTTP {resp.status_code}) — "
            f"trying next key.")


# ------------------------------------------------------------------ grok

def generate_grok(api_key, model, prompt, out_path, aspect_ratio="16:9",
                  timeout=180):
    """xAI image generation. Always uses b64_json (xAI URLs are ephemeral)."""
    if not api_key or not str(api_key).strip():
        raise ImageError("Grok API key is empty (Settings → Images).")
    body = {"model": model or "grok-imagine-image",
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": "b64_json"}
    try:
        resp = requests.post("https://api.x.ai/v1/images/generations",
                             headers={"Authorization": f"Bearer {api_key.strip()}"},
                             json=body, timeout=timeout)
    except requests.RequestException as e:
        raise ImageError(f"Grok network error: {e}"[:200]) from e
    _raise_for_status("Grok", resp)
    if resp.status_code != 200:
        raise ImageError(f"Grok HTTP {resp.status_code}: "
                         f"{resp.text[:200]}")
    try:
        data = (resp.json().get("data") or [{}])[0]
        b64 = data.get("b64_json") or ""
        raw = base64.b64decode(b64)
    except Exception as e:  # noqa: BLE001
        raise ImageError(f"Grok returned no image data: {e}"[:200]) from e
    Path(out_path).write_bytes(raw)
    try:
        costs.log_call(costs.current_job_dir(), "grok-image", "image", 1,
                       note=f"grok {model}")
    except Exception:  # noqa: BLE001
        pass
    return str(out_path)


# ------------------------------------------------------------------ gemini

def generate_gemini(api_key, model, prompt, out_path, timeout=180,
                    ref_images=None):
    """Google Gemini image generation (same model family as Google Flow).

    ref_images: optional list of local image paths (character sheet /
    reference photos) sent as visual input so the model keeps the same
    character. Text-only prompts work exactly as before.
    """
    if not api_key or not str(api_key).strip():
        raise ImageError("Gemini API key is empty (Settings → Images).")
    model = model or "gemini-2.5-flash-image"
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    parts = []
    for rp in ref_images or []:
        try:
            import mimetypes
            raw = Path(rp).read_bytes()
            if not raw:
                continue
            mime, _enc = mimetypes.guess_type(str(rp))
            parts.append({"inlineData": {
                "mimeType": mime or "image/png",
                "data": base64.b64encode(raw).decode("ascii")}})
        except Exception:  # noqa: BLE001
            continue
    parts.append({"text": prompt})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}}
    try:
        resp = requests.post(url, headers={"x-goog-api-key": api_key.strip()},
                             json=body, timeout=timeout)
    except requests.RequestException as e:
        raise ImageError(f"Gemini network error: {e}"[:200]) from e
    _raise_for_status("Gemini", resp)
    if resp.status_code != 200:
        raise ImageError(f"Gemini HTTP {resp.status_code}: "
                         f"{resp.text[:200]}")
    try:
        cands = resp.json().get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts") or []
        b64 = ""
        for part in parts:
            inline = part.get("inlineData") or {}
            if inline.get("data"):
                b64 = inline["data"]
                break
            # FIX (Bug 5): Gemini returns a text block when content policy
            # blocks the image prompt. Without this check, b64 stays empty,
            # the decode below raises a generic exception, and the fallback
            # chain never fires cleanly. We now detect this explicitly and
            # raise a clear ImageError so make_image() falls through to the
            # local Pillow fallback as intended.
            if part.get("text"):
                blocked_msg = str(part["text"])[:120].replace("\n", " ")
                raise ImageError(f"Gemini blocked prompt: {blocked_msg}")
        if not b64:
            finish = (cands[0].get("finishReason") or "") if cands else ""
            raise ImageError(f"Gemini returned no image data "
                             f"(finishReason={finish!r})")
        raw = base64.b64decode(b64)
    except ImageError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ImageError(f"Gemini parse error: {e}"[:200]) from e
    Path(out_path).write_bytes(raw)
    try:
        costs.log_call(costs.current_job_dir(), "gemini-image", "image", 1,
                       note=f"gemini {model}")
    except Exception:  # noqa: BLE001
        pass
    return str(out_path)


# ------------------------------------------------------------------ avatar
def avatar_prompt(description):
    """Build a locked-presenter portrait prompt from a short description."""
    d = str(description or "").strip().rstrip(".")
    return (
        "Photorealistic portrait photograph, head and shoulders, "
        f"{d}, facing the camera, calm warm expression, soft natural "
        "window light, plain softly blurred indoor background, vertical "
        "portrait composition, no text, no watermark, no logo.")


def generate_avatar_image(pool, model, description, out_path, logger=None):
    """Generate a presenter portrait via the Gemini key pool.

    Saves a normalized RGB PNG to out_path. Raises on total failure
    (pool exhausted etc.). Never writes partial files silently.
    """
    if pool is None:
        raise ImageError("No Gemini API keys configured "
                         "(Settings → API Keys).")
    pool.run(lambda k: generate_gemini(
        k, model or "gemini-2.5-flash-image",
        avatar_prompt(description), str(out_path)), logger, op="avatar")
    try:
        Image.open(out_path).convert("RGB").save(out_path, "PNG")
    except Exception as e:  # noqa: BLE001
        raise ImageError(f"Generated avatar is not a valid image: {e}"[:200])
    return str(out_path)


# ------------------------------------------------------------------ local

def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def generate_local(title, beat_name, out_path, seed=0):
    """Free Pillow fallback: cinematic gradient + title text card. 1920x1080.

    Cannot fail on missing fonts/data — Pillow only. Never raises for
    expected inputs (wraps everything defensively anyway).
    """
    rnd = random.Random(seed)
    # dark cinematic gradient (deep blue-charcoal -> warm dark)
    top = (rnd.randint(18, 30), rnd.randint(22, 36), rnd.randint(34, 52))
    bot = (rnd.randint(8, 14), rnd.randint(10, 16), rnd.randint(18, 26))
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    d = ImageDraw.Draw(img)
    # vignette-ish soft circles for depth
    for _ in range(14):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        rad = rnd.randint(120, 420)
        shade = rnd.randint(6, 22)
        d.ellipse([x - rad, y - rad, x + rad, y + rad],
                  fill=(shade, shade, shade + 8))
    # gold rule lines
    gold = (212, 162, 78)
    d.rectangle([120, 470, W - 120, 476], fill=gold)
    d.rectangle([120, 640, W - 120, 646], fill=gold)
    # title text, wrapped
    words = str(title or "").split()
    lines, cur = [], ""
    fnt = _font(72)
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if d.textlength(trial, font=fnt) > W - 320 and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lines = lines[:3]
    y = 500
    for line in lines:
        tw_ = d.textlength(line, font=fnt)
        d.text(((W - tw_) / 2, y), line, font=fnt, fill=(232, 228, 218))
        y += 92
    # beat label, small
    fnt2 = _font(34)
    label = str(beat_name or "").upper()
    if label:
        tw_ = d.textlength(label, font=fnt2)
        d.text(((W - tw_) / 2, 690), label, font=fnt2, fill=(138, 143, 158))
    img.save(out_path, "PNG")
    return str(out_path)


# ------------------------------------------------------------------ pc upload

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def local_pool(cfg, channel_id):
    """The user's own PC images for a channel, sorted by name.

    Returns [] when the option is off, the folder is missing, or it holds
    no images. Never raises.
    """
    try:
        ch = ((cfg or {}).get("channels") or {}).get(channel_id) or {}
        li = ch.get("local_images") or {}
        if not li.get("enabled"):
            return []
        folder = Path(str(li.get("folder") or "").strip())
        if not folder.is_dir():
            return []
        return sorted(p for p in folder.iterdir()
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ router

def fit_1920x1080(path):
    """Resize/crop any image to exactly 1920x1080. Never raises."""
    try:
        from PIL import ImageOps
        img = Image.open(path).convert("RGB")
        img = ImageOps.fit(img, (W, H), Image.LANCZOS)
        img.save(path, "PNG")
    except Exception:  # noqa: BLE001
        pass
    return str(path)


def make_image(prompt, title, beat_name, out_path, secrets, cfg,
               logger=None, seed=0, ref_images=None, identity_text=""):
    """Try providers in order; always returns a valid 1920x1080 PNG path.

    ref_images: local reference images (character sheet) — passed to
    Gemini as visual input. identity_text: prepended to the text prompt
    for text-only providers (Grok). Returns (path, provider_used).
    Never raises.
    """
    secrets = secrets or {}
    order = ((cfg or {}).get("providers") or {}).get("image_order") \
        or ["grok", "gemini", "local"]
    models = (cfg or {}).get("providers") or {}
    state_dir = config_mod.CONFIG_PATH.parent
    grok_pool = pool_from_secrets("grok-image", secrets,
                                  "xai_api_key", "xai_api_keys", state_dir)
    gemini_pool = pool_from_secrets("gemini-image", secrets,
                                    "gemini_api_key", "gemini_api_keys",
                                    state_dir)
    idt = (identity_text or "").strip()
    last_err = ""
    for prov in order:
        try:
            if prov == "grok":
                gprompt = (idt + " " + prompt).strip() if idt else prompt
                if grok_pool:
                    grok_pool.run(
                        lambda k: generate_grok(
                            k, models.get("grok_model"), gprompt, out_path),
                        logger, op="image")
                else:
                    generate_grok(secrets.get("xai_api_key"),
                                  models.get("grok_model"), gprompt, out_path)
            elif prov == "gemini":
                if gemini_pool:
                    gemini_pool.run(
                        lambda k: generate_gemini(
                            k, models.get("gemini_model"), prompt, out_path,
                            ref_images=ref_images),
                        logger, op="image")
                else:
                    generate_gemini(secrets.get("gemini_api_key"),
                                    models.get("gemini_model"), prompt,
                                    out_path, ref_images=ref_images)
            elif prov == "local":
                generate_local(title, beat_name, out_path, seed=seed)
            else:
                continue
            fit_1920x1080(out_path)
            if logger:
                logger.log(f"    image [{prov}]: {Path(out_path).name}")
            return str(out_path), prov
        except ImageError as e:
            last_err = str(e)
            if logger:
                logger.log(f"    image [{prov}] failed: {e} — trying next")
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            if logger:
                logger.log(f"    image [{prov}] failed: {e} — trying next")
    # Absolute last resort: local card (cannot fail).
    try:
        generate_local(title, beat_name, out_path, seed=seed)
        fit_1920x1080(out_path)
    except Exception:  # noqa: BLE001
        Image.new("RGB", (W, H), (20, 22, 28)).save(out_path, "PNG")
    if logger:
        logger.log(f"    image [local-fallback]: {Path(out_path).name}"
                   + (f" (last error: {last_err})" if last_err else ""))
    return str(out_path), "local"
