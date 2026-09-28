"""mib/stages/package.py — per-video output files (title/desc/tags/etc)."""
import json
from pathlib import Path

from .. import costs

AI_DISCLOSURE = ("Disclosure: This video uses AI-generated narration, "
                 "imagery and an AI presenter.")


def _tags_for(title, channel_name):
    words = [w.strip(".,!?;:\"'()").lower() for w in str(title).split()]
    tags = []
    for w in words:
        if len(w) > 3 and w not in tags:
            tags.append(w)
    tags += [channel_name.lower().replace(" ", ""), "storytime",
             "aiavatar", "faceless"]
    return tags[:15]


def _thumbnail_prompt(title, topic, channel_id=None):
    """Avatar-locked thumbnail prompt: 1 title = 1 thumbnail.

    Uses the channel's character sheet avatar when configured (via
    prompts.thumbnail.build_avatar_prompt), else the default template.
    Falls back to the old one-liner if the prompts module is missing.
    Never raises.
    """
    try:
        from ..prompts import thumbnail as _th
        if channel_id:
            return _th.build_avatar_prompt(title or "", channel_id,
                                           topic_visual=topic or "")
        return _th.build_prompt(title or "", topic_visual=topic or "")
    except Exception:  # noqa: BLE001
        pass
    return (f"YouTube thumbnail prompt: extreme close-up, emotional "
            f"eyes, warm cinematic light, scene of {topic}, "
            f"max 3 words of BIG text related to '{(title or '')[:40]}', "
            f"no watermark.")


def run(job_dir, script, channel_cfg, final_mp4, duration, provider_info,
        logger=None):
    """Write title.txt, description.txt, tags.txt, thumbnail-prompt.txt,
    costs.json, qc-report.json (qc fills the verdict). Never raises."""
    job = Path(job_dir)
    try:
        title = script.get("title", "")
        topic = script.get("topic", title)
        cname = (channel_cfg or {}).get("name", "")

        (job / "title.txt").write_text(title + "\n", encoding="utf-8")

        desc = (f"{title}\n\n{script.get('hook', '')}\n\n"
                f"{AI_DISCLOSURE}\n\n"
                f"Subscribe to {cname} for more stories.\n")
        (job / "description.txt").write_text(desc, encoding="utf-8")

        (job / "tags.txt").write_text(
            ", ".join(_tags_for(title, cname)) + "\n", encoding="utf-8")

        thumb = _thumbnail_prompt(title, topic,
                                    (channel_cfg or {}).get("id", ""))
        (job / "thumbnail-prompt.txt").write_text(thumb + "\n",
                                                  encoding="utf-8")

        cost_data = costs.job_cost(job_dir)
        (job / "costs.json").write_text(json.dumps(cost_data, indent=2),
                                        encoding="utf-8")

        qc_report = {
            "title": title,
            "channel": (channel_cfg or {}).get("name", ""),
            "final_mp4": str(final_mp4 or ""),
            "duration_s": duration,
            "est_minutes": script.get("est_minutes", 0),
            "words": script.get("words", 0),
            "providers": provider_info or {},
            "total_cost_usd": cost_data.get("total_usd", 0.0),
            "verdict": "pending",
            "reasons": [],
        }
        (job / "qc-report.json").write_text(json.dumps(qc_report, indent=2),
                                            encoding="utf-8")
        if logger:
            logger.log("    package: title/description/tags/thumbnail/costs written")
    except Exception as e:  # noqa: BLE001
        if logger:
            logger.log(f"    package WARNING: {e}")
    return str(job)


def render_thumbnail(job_dir, title, topic, channel_id, cfg, secrets,
                     logger=None):
    """Render exactly ONE thumbnail.jpg per video (1 title = 1 thumbnail).

    The thumbnail stars the channel's avatar from the character sheet:
    the identity-locked prompt goes to the image model and the sheet /
    reference images go as visual input (Gemini), so the same avatar
    appears in every thumbnail.

    When no image API key is configured the existing "prompt file only"
    behaviour is kept (thumbnail-prompt.txt was already written by run()).
    Never raises. Returns the jpg path or "".
    """
    job = Path(job_dir)
    try:
        prompt = _thumbnail_prompt(title, topic, channel_id)
        tp = job / "thumbnail-prompt.txt"
        try:
            if not tp.is_file():
                tp.write_text((prompt or "") + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        if not (prompt or "").strip():
            return ""

        # image keys configured? (else: prompt-file-only mode)
        try:
            from ..keypool import pool_from_secrets
            from .. import config as config_mod
            state_dir = config_mod.CONFIG_PATH.parent
            grok_pool = pool_from_secrets(
                "grok-image", secrets, "xai_api_key", "xai_api_keys",
                state_dir)
            gemini_pool = pool_from_secrets(
                "gemini-image", secrets, "gemini_api_key",
                "gemini_api_keys", state_dir)
        except Exception:  # noqa: BLE001
            grok_pool, gemini_pool = None, None
        if not grok_pool and not gemini_pool:
            if logger:
                try:
                    logger.log("    thumbnail: no image key — "
                               "prompt file only")
                except Exception:  # noqa: BLE001
                    pass
            return ""

        # avatar visual references (identity lock)
        ref_imgs = []
        try:
            from .. import character as charmod
            if charmod.has_character(channel_id):
                ref_imgs = charmod.ref_images(channel_id)
        except Exception:  # noqa: BLE001
            ref_imgs = []

        from ..providers import genimages
        out = job / "thumbnail.jpg"
        try:
            seed = abs(hash(str(title or ""))) % (10 ** 6)
        except Exception:  # noqa: BLE001
            seed = 0
        try:
            # identity lock is already inside `prompt`; ref images are the
            # visual lock for providers that accept them (Gemini).
            path, prov = genimages.make_image(
                prompt, title, "thumbnail", out, secrets, cfg,
                logger=logger, seed=seed,
                ref_images=ref_imgs or None, identity_text="")
            if logger:
                try:
                    logger.log(f"    thumbnail: 1 thumbnail rendered "
                               f"[{prov}] with channel avatar")
                except Exception:  # noqa: BLE001
                    pass
            return str(path)
        except Exception as e:  # noqa: BLE001
            if logger:
                try:
                    logger.log(f"    thumbnail WARNING: {e}")
                except Exception:  # noqa: BLE001
                    pass
            return ""
    except Exception:  # noqa: BLE001
        return ""
