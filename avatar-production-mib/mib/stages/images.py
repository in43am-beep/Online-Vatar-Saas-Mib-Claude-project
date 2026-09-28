"""mib/stages/images.py — per-beat scene images with sub-scene splitting.

UPGRADE v2: Bulk Gemini Image Prompt Generation
=================================================
When a channel has a master prompt / character sheet configured:
  Script beats → Gemini generates ONE rich cinematic prompt per sub-scene
  → Grok / Gemini image gen uses those prompts
  → Character visually consistent across all frames

Original sub-scene splitting is kept as fallback if Gemini unavailable.

Order: user PC images → grok → gemini → local Pillow fallback.
Character cameo: scenes tagged as cameos still lock the character sheet.
"""
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .. import character as charmod
from ..providers import genimages

# Words spoken per second at 140 wpm
_WPS = 140 / 60.0   # ≈ 2.33 words/second
# Target: one new image every N seconds
_IMAGE_EVERY_SECS = 45


def _split_subscenes(beat_name, narration, image_prompt, target_secs=_IMAGE_EVERY_SECS):
    """Split a beat's narration into sub-scenes of ~target_secs of speech.

    Returns a list of (sub_name, sub_text, sub_prompt) tuples.
    If the beat is short enough to fit in one image, returns a single item.
    """
    words = (narration or "").split()
    if not words:
        return [(beat_name, narration, image_prompt)]

    words_per_sub = max(60, int(_WPS * target_secs))
    subs = []
    for i in range(0, len(words), words_per_sub):
        chunk = " ".join(words[i: i + words_per_sub])
        # Build a focused image prompt from the sub-scene text
        # (use the beat's base prompt but add the first 120 chars of the chunk
        #  so Gemini generates something specific to those words)
        excerpt = " ".join(words[i: i + 25])  # ~25 words of context
        sub_prompt = f"{image_prompt} Scene: {excerpt}."
        subs.append((f"{beat_name}-sub{len(subs):02d}", chunk, sub_prompt))
    return subs if subs else [(beat_name, narration, image_prompt)]


def _gen_one(idx, sub_name, prompt, title, out, pool, secrets, cfg,
             is_cameo, ref_imgs, id_block, logger):
    """Generate a single sub-scene image. Returns (idx, path). Never raises."""
    if pool:
        try:
            src = pool[idx % len(pool)]
            shutil.copy(str(src), str(out))
            genimages.fit_1920x1080(out)
            if logger:
                logger.log(f"    image [pc-upload]: {src.name} -> {out.name}")
            return idx, str(out)
        except Exception:  # noqa: BLE001
            pass

    # Build prompt — inject identity block for cameo scenes
    final_prompt = prompt
    if is_cameo and id_block:
        final_prompt = (id_block + " Scene: " + prompt).strip()
        if logger:
            logger.log(f"    image: {out.name} = character cameo")

    try:
        path, _prov = genimages.make_image(
            final_prompt, title, sub_name, out, secrets, cfg,
            logger=logger, seed=idx,
            ref_images=ref_imgs if is_cameo else None,
            identity_text=id_block if is_cameo else "")
        return idx, str(path)
    except Exception:  # noqa: BLE001
        pass

    # Local Pillow fallback — cannot fail
    try:
        path = genimages.generate_local(title, sub_name, out, seed=idx)
        return idx, str(path)
    except Exception:  # noqa: BLE001
        from PIL import Image
        Image.new("RGB", (1920, 1080), (20, 22, 28)).save(out, "PNG")
        return idx, str(out)


def run(job_dir, script, channel_id, cfg, secrets, logger=None):
    """Generate images/scene-NN.png for every sub-scene.

    If the channel has a master prompt / character sheet, uses Gemini to
    generate bulk cinematic image prompts (one per sub-scene) before
    calling the image API. Falls back to per-beat prompts if unavailable.

    Returns a flat list of image paths in timeline order.
    Also stores 'sub_scene_map' in script for assemble stage.
    Never raises.
    """
    job = Path(job_dir)
    img_dir = job / "images"
    try:
        img_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    title = script.get("title", "")
    channels = (cfg or {}).get("channels") or {}
    channel_cfg = channels.get(channel_id) or {}
    ch_prompts = channel_cfg.get("prompts") or {}
    has_master = bool(ch_prompts.get("master", "").strip())

    # ── BULK PROMPT GENERATION (when channel has master prompt) ──────────────
    bulk_prompt_map = {}   # scene_id → {"prompt": ..., "negative": ...}
    if has_master:
        try:
            from .image_prompts import generate_bulk_prompts
            bulk = generate_bulk_prompts(script, channel_cfg, secrets, logger)
            for item in bulk:
                bulk_prompt_map[item["scene_id"]] = item
            if logger and bulk:
                logger.log(f"    image prompts: {len(bulk)} Gemini prompts ready ✓")
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.log(f"    image prompts: bulk gen skipped ({e}) — using defaults")

    # ── BUILD SUB-SCENES ─────────────────────────────────────────────────────
    # Build the master items list: hook + beats + cta
    raw_items = [("hook", script.get("hook", ""), "Opening scene. ")]
    for i, b in enumerate(script.get("beats", [])):
        raw_items.append((
            b.get("name", f"beat-{i}"),
            b.get("narration", ""),
            b.get("image_prompt", ""),
        ))
    raw_items.append(("cta", script.get("cta", ""),
                      "Warm closing scene, hopeful light. "))

    # Expand each raw item into sub-scenes
    all_subs = []   # (global_idx, beat_idx, sub_name, sub_text, sub_prompt)
    global_idx = 0
    for beat_idx, (beat_name, narration, img_prompt) in enumerate(raw_items):
        subs = _split_subscenes(beat_name, narration, img_prompt)
        for sub_name, sub_text, sub_prompt in subs:
            # Override with Gemini bulk prompt if available
            if sub_name in bulk_prompt_map:
                sub_prompt = bulk_prompt_map[sub_name]["prompt"]
            all_subs.append((global_idx, beat_idx, sub_name, sub_text, sub_prompt))
            global_idx += 1

    total = len(all_subs)
    if logger:
        logger.log(f"    images: {total} sub-scenes "
                   f"(~1 image per {_IMAGE_EVERY_SECS}s of speech)")

    # Character cameo setup
    ch = charmod.load_character(channel_id)
    cameo_idxs = set()
    ref_imgs, id_block = [], ""
    if ch["cameo"] and charmod.has_character(channel_id):
        try:
            seed = abs(hash(title)) % (10 ** 6)
        except Exception:  # noqa: BLE001
            seed = 0
        cameo_idxs = set(charmod.pick_cameo_scenes(total, ch["cameo"], seed=seed))
        ref_imgs = charmod.ref_images(channel_id)
        id_block = charmod.identity_block(channel_id)

    pool = genimages.local_pool(cfg, channel_id)
    if pool and logger:
        logger.log(f"    image [pc-upload]: {len(pool)} PC image(s) cycling")

    # Build generation tasks
    tasks = []
    for g_idx, beat_idx, sub_name, sub_text, sub_prompt in all_subs:
        out = img_dir / f"scene-{g_idx:03d}.png"
        tasks.append(dict(
            idx=g_idx, sub_name=sub_name, prompt=sub_prompt,
            title=title, out=out, pool=pool, secrets=secrets, cfg=cfg,
            is_cameo=g_idx in cameo_idxs, ref_imgs=ref_imgs,
            id_block=id_block, logger=logger,
        ))

    # Generate in parallel — same API cost, ~4× faster
    results = [None] * total
    max_workers = min(5, total)
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(_gen_one, **t): t["idx"] for t in tasks
            }
            for future in as_completed(futures):
                try:
                    idx, path = future.result()
                    results[idx] = path
                except Exception as e:  # noqa: BLE001
                    i = futures[future]
                    if logger:
                        logger.log(f"    image {i} failed unexpectedly: {e}")
                    # generate local fallback synchronously
                    out = img_dir / f"scene-{i:03d}.png"
                    try:
                        results[i] = genimages.generate_local(title, f"sub{i}", out, seed=i)
                    except Exception:  # noqa: BLE001
                        from PIL import Image
                        Image.new("RGB", (1920, 1080), (20, 22, 28)).save(out, "PNG")
                        results[i] = str(out)
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    images: parallel generation error: {e}")
        # Sequential fallback
        for t in tasks:
            if results[t["idx"]] is None:
                _, path = _gen_one(**t)
                results[t["idx"]] = path

    # Fill any remaining None slots with a black frame
    for i, r in enumerate(results):
        if r is None:
            out = img_dir / f"scene-{i:03d}.png"
            try:
                from PIL import Image
                Image.new("RGB", (1920, 1080), (20, 22, 28)).save(out, "PNG")
            except Exception:  # noqa: BLE001
                pass
            results[i] = str(out)

    # Store sub-scene map back into script for assemble stage to use
    # (beat_idx → [global image indices]) for correct audio-image pairing
    sub_map = {}
    for g_idx, beat_idx, _, _, _ in all_subs:
        sub_map.setdefault(beat_idx, []).append(g_idx)
    try:
        script["_sub_scene_map"] = sub_map
        script["_total_sub_scenes"] = total
    except Exception:  # noqa: BLE001
        pass

    if logger:
        logger.log(f"    images: {total} images ready "
                   f"({sum(1 for r in results if r)} successful)")

    return [r for r in results if r]
