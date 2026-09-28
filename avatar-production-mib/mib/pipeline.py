"""mib/pipeline.py — orchestrates the per-title pipeline.

output/<channel>/<slug>/ per video. Stages:
  script -> voiceover -> images -> avatar -> assemble -> package -> qc

run_pipeline() NEVER raises: any failure is captured into the result dict
and the job is quarantined with a reason.
"""
import json
import re
import unicodedata
from pathlib import Path

from . import costs, qc
from .config import ROOT
from .log import JobLogger
from .stages import script as st_script
from .stages import voiceover as st_voice
from .stages import images as st_images
from .stages import avatar as st_avatar
from .stages import assemble as st_assemble
from .stages import package as st_package


def slugify(title):
    """Title -> filesystem-safe slug. Never raises."""
    try:
        t = unicodedata.normalize("NFKD", str(title or "untitled"))
        t = t.encode("ascii", "ignore").decode("ascii")
        t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
        return t[:80] or "untitled"
    except Exception:  # noqa: BLE001
        return "untitled"


def _progress(cb, pct, msg):
    try:
        if cb:
            cb(pct, msg)
    except Exception:  # noqa: BLE001
        pass


def run_pipeline(title, channel_id, cfg, secrets, opts=None,
                 progress_cb=None, log_cb=None):
    """Run the full pipeline for one title.

    opts: {minutes_override, mode ("avatar"|"frontier"),
           presenter_seconds, appearances}
    Returns {"ok", "title", "job_dir", "final_mp4", "duration_s",
             "total_cost_usd", "qc_reasons", "error"}. Never raises.
    """
    opts = opts or {}
    cfg = cfg or {}
    secrets = secrets or {}
    channels = cfg.get("channels") or {}
    channel = channels.get(channel_id) or {}
    slug = slugify(title)
    job_dir = ROOT / "output" / channel_id / slug

    logger = JobLogger(job_dir, callback=log_cb)
    result = {"ok": False, "title": title, "job_dir": str(job_dir),
              "final_mp4": "", "duration_s": 0.0, "total_cost_usd": 0.0,
              "qc_reasons": [], "error": ""}

    try:
        job_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"cannot create job dir: {e}"
        return result

    costs.set_current_job_dir(job_dir)
    costs.init_job(job_dir)
    try:
        mode = (opts.get("mode")
                or channel.get("mode") or "avatar").lower()
        try:
            minutes = int(opts.get("minutes_override")
                          or channel.get("default_minutes") or 5)
        except (TypeError, ValueError):
            minutes = 5

        logger.log(f"=== {title}")
        logger.log(f"channel={channel_id} mode={mode} target={minutes}min")

        # 1. script
        _progress(progress_cb, 5, "Writing script…")
        logger.log("[1/6] script…")
        scr = None
        provs = cfg.get("providers") or {}
        script_provider = provs.get("script_provider") or "local"
        if script_provider in ("ai33pro", "gemini"):
            try:
                from .keypool import pool_from_secrets
                from .config import CONFIG_PATH
                if script_provider == "gemini":
                    from .providers import geminillm
                    llm_pool = pool_from_secrets(
                        "gemini-image", secrets,
                        "gemini_api_key", "gemini_api_keys",
                        CONFIG_PATH.parent)
                    if llm_pool is None:
                        raise geminillm.LLMError(
                            "Gemini API key is empty.")
                    try:
                        from .patterns import get_pattern, describe
                        pat_notes = describe(
                            get_pattern(channel, channel_id)) or ""
                    except Exception:  # noqa: BLE001
                        pat_notes = ""
                    scr = llm_pool.run(
                        lambda k: geminillm.generate(
                            title, minutes, k,
                            provs.get("gemini_llm_model", ""),
                            channel_name=channel.get("name", ""),
                            pattern_notes=pat_notes),
                        logger, op="script")
                    logger.log("    script [gemini-llm]")
                else:
                    from .providers import scriptllm
                    llm_pool = pool_from_secrets(
                        "ai33-voice", secrets,
                        "ai33pro_api_key", "ai33pro_api_keys",
                        CONFIG_PATH.parent)
                    if llm_pool is None:
                        raise scriptllm.LLMError("AI33 Pro API key is empty.")
                    scr = llm_pool.run(
                        lambda k: scriptllm.generate(
                            title, minutes, k,
                            provs.get("ai33pro_llm_base_url", ""),
                            provs.get("ai33pro_llm_model", "")),
                        logger, op="script")
                    logger.log("    script [ai33pro-llm]")
            except Exception as e:  # noqa: BLE001
                logger.log(f"    script [{script_provider}-llm] failed: {e} — "
                           "local rules fallback")
                scr = None
        if scr is None:
            try:
                rejoins = max(
                    0, int(opts.get("appearances")
                           or provs.get("appearances", 1)) - 1)
            except (TypeError, ValueError):
                rejoins = 0
            scr = st_script.build_script(title, minutes, channel,
                                         rejoins=rejoins,
                                         channel_id=channel_id)
            logger.log("    script [local rules]")
        # 1b. Claude review — strict mistake check, auto-applies fixes
        if scr and provs.get("claude_review"):
            try:
                from .keypool import pool_from_secrets
                from .config import CONFIG_PATH
                from .providers import claudereview
                claude_pool = pool_from_secrets(
                    "claude-review", secrets,
                    "claude_api_key", "claude_api_keys",
                    CONFIG_PATH.parent)
                if claude_pool is None:
                    raise claudereview.ClaudeError(
                        "Claude API key is empty.")
                issues, fixed = claude_pool.run(
                    lambda k: claudereview.review(
                        title, scr, k,
                        provs.get("claude_base_url", ""),
                        provs.get("claude_model", "")),
                    logger, op="review")
                if issues:
                    logger.log(f"    claude review: {len(issues)} issue(s) "
                               f"found")
                    for iss in issues[:5]:
                        where = str(iss.get("where", "?"))[:30]
                        prob = str(iss.get("problem", ""))[:120]
                        logger.log(f"      • [{where}] {prob}")
                else:
                    logger.log("    claude review: no mistakes found ✓")
                if fixed:
                    from .stages.script import sanitize as _san
                    try:
                        fixed["hook"] = _san(fixed.get("hook", ""))
                        fixed["cta"] = _san(fixed.get("cta", ""))
                        for b in fixed.get("beats") or []:
                            b["narration"] = _san(b.get("narration", ""))
                        fixed["words"] = (
                            len(fixed["hook"].split())
                            + sum(len(b["narration"].split())
                                  for b in fixed["beats"])
                            + len(fixed["cta"].split()))
                        from .stages.script import WPM as _WPM
                        fixed["est_minutes"] = round(
                            fixed["words"] / _WPM, 2)
                        scr = fixed
                        logger.log("    claude review: fixes applied ✓")
                    except Exception:  # noqa: BLE001
                        logger.log("    claude review: fix invalid — "
                                   "keeping original script")
            except Exception as e:  # noqa: BLE001
                logger.log(f"    claude review skipped: {e} — "
                           "keeping original script")
        st_script.save_script(job_dir, scr)
        logger.log(f"    {scr['words']} words ≈ {scr['est_minutes']} min")

        # 2. voiceover
        _progress(progress_cb, 20, "Synthesizing voiceover…")
        logger.log("[2/6] voiceover…")
        voice = st_voice.run(job_dir, scr, channel.get("voice"),
                             secrets, logger)
        total_vo = sum(s["duration"] for s in voice["segments"])

        # 3. images
        _progress(progress_cb, 40, "Generating images…")
        logger.log("[3/6] images…")
        imgs = st_images.run(job_dir, scr, channel_id, cfg, secrets, logger)

        # 4. avatar intro
        _progress(progress_cb, 60, "Rendering presenter...")
        logger.log("[4/6] presenter...")
        avatar_res = {"intro": "", "mids": []}
        if mode == "avatar":
            presenter = _find_presenter(cfg, channel.get("presenter"))
            # Read per-channel avatar clip mode (backend-locked)
            clip_mode = channel.get("avatar_clip_mode", "static")
            clip_secs = int(channel.get("avatar_clip_secs")
                            or (cfg.get("providers") or {}).get(
                                "presenter_seconds", 6))
            clip_secs = max(5, min(15, clip_secs))
            appearances = int(opts.get("appearances")
                              or (cfg.get("providers") or {}).get(
                                  "appearances", 1))

            if clip_mode == "video":
                # Option 3: AI Video Clips via Gemini Veo
                try:
                    from .stages.avatar_veo import run as run_veo
                    avatar_res = run_veo(
                        job_dir, voice["voiceover"], presenter,
                        seconds=clip_secs, appearances=appearances,
                        total_duration=total_vo, logger=logger,
                        voice_segments=voice["segments"], script=scr,
                        images=imgs, secrets=secrets, cfg=cfg)
                    logger.log(f"    avatar [Option 3 - AI video clips, {clip_secs}s]")
                except ImportError:
                    logger.log("    avatar: veo module not found, fallback to static")
                    avatar_res = st_avatar.run(
                        job_dir, voice["voiceover"], presenter,
                        seconds=clip_secs, appearances=appearances,
                        total_duration=total_vo, logger=logger,
                        voice_segments=voice["segments"], script=scr, images=imgs)
                except Exception as e:  # noqa: BLE001
                    logger.log(f"    avatar veo failed: {e} -- fallback static")
                    avatar_res = st_avatar.run(
                        job_dir, voice["voiceover"], presenter,
                        seconds=clip_secs, appearances=appearances,
                        total_duration=total_vo, logger=logger,
                        voice_segments=voice["segments"], script=scr, images=imgs)

            elif clip_mode == "card":
                # Option 2: Character Lock Card overlay
                try:
                    from .stages.avatar_card import run as run_card
                    avatar_res = run_card(
                        job_dir, voice["voiceover"], presenter,
                        channel_id=channel_id, cfg=cfg,
                        seconds=clip_secs, appearances=appearances,
                        total_duration=total_vo, logger=logger,
                        voice_segments=voice["segments"], script=scr, images=imgs)
                    logger.log(f"    avatar [Option 2 - character card, {clip_secs}s]")
                except ImportError:
                    logger.log("    avatar: card module not found, fallback to static")
                    avatar_res = st_avatar.run(
                        job_dir, voice["voiceover"], presenter,
                        seconds=clip_secs, appearances=appearances,
                        total_duration=total_vo, logger=logger,
                        voice_segments=voice["segments"], script=scr, images=imgs)
                except Exception as e:  # noqa: BLE001
                    logger.log(f"    avatar card failed: {e} -- fallback static")
                    avatar_res = st_avatar.run(
                        job_dir, voice["voiceover"], presenter,
                        seconds=clip_secs, appearances=appearances,
                        total_duration=total_vo, logger=logger,
                        voice_segments=voice["segments"], script=scr, images=imgs)

            else:
                # Option 1: Static PNG + Ken Burns (default, always works)
                avatar_res = st_avatar.run(
                    job_dir, voice["voiceover"], presenter,
                    seconds=clip_secs, appearances=appearances,
                    total_duration=total_vo, logger=logger,
                    voice_segments=voice["segments"], script=scr, images=imgs)
                logger.log(f"    avatar [Option 1 - static PNG, {clip_secs}s]")
        else:
            logger.log("    frontier mode: no presenter intro")

        # 5. assemble
        _progress(progress_cb, 78, "Assembling video…")
        logger.log("[5/6] assemble…")
        final, duration = st_assemble.run(
            job_dir, voice["segments"], imgs, avatar_res, logger,
            subtitles=bool(channel.get("subtitles")),
            script=scr,
            bell=bool((cfg.get("providers") or {}).get(
                "presenter_watermark", True)))
        result["final_mp4"] = final
        result["duration_s"] = duration

        # 5b. SFX sound design (whooshes/hits/risers at scene changes)
        providers_cfg = cfg.get("providers") or {}
        sfx_enabled = (channel.get("sfx", False)
                       or providers_cfg.get("sfx_enabled", False))
        if sfx_enabled and final:
            try:
                from .sfx import mix_sfx_into_video, detect_scene_cuts, create_sample_sfx
                # Generate synthetic SFX if none exist yet
                create_sample_sfx(ROOT / "assets", logger)
                scene_cuts = detect_scene_cuts(final, logger=logger)
                if scene_cuts:
                    mixed = mix_sfx_into_video(
                        job_dir, final, scene_cuts, cfg, logger)
                    if mixed and mixed != str(final):
                        final = mixed
                        duration = (
                            __import__("mib.ffmpeg", fromlist=["ffmpeg"])
                        )
                        from . import ffmpeg as _ffmpeg
                        duration = _ffmpeg.probe(final)["duration"] or duration
            except Exception as e:  # noqa: BLE001
                logger.log(f"    sfx: skipped: {e}")

        # 5c. Actual thumbnail PNG (not just a text prompt)
        try:
            from .thumbnail import generate_thumbnail
            presenter_img = None
            try:
                presenter_id = (channel.get("presenter") or "")
                p_list = cfg.get("presenters") or []
                p_data = next(
                    (p for p in p_list if p.get("id") == presenter_id), {})
                rel = p_data.get("image", "")
                if rel:
                    from .config import ROOT as _ROOT, BUNDLE_DIR as _BDIR
                    for base in (_ROOT, _BDIR):
                        cand = base / rel
                        if cand.is_file():
                            presenter_img = str(cand)
                            break
            except Exception:  # noqa: BLE001
                pass
            generate_thumbnail(job_dir, scr, channel_id, cfg, secrets,
                                presenter_image=presenter_img, logger=logger)
        except Exception as e:  # noqa: BLE001
            logger.log(f"    thumbnail: skipped: {e}")

        # 6. package
        _progress(progress_cb, 90, "Packaging…")
        logger.log("[6/6] package…")
        st_package.run(job_dir, scr, channel, final, duration,
                       {"voice": voice["provider"],
                        "mode": mode,
                        "presenter": avatar_res.get("presenter", "")},
                       logger)

        # 7. qc
        _progress(progress_cb, 96, "Quality check…")
        ok, reasons = qc.check(final, scr["est_minutes"])
        result["qc_reasons"] = reasons
        if ok:
            qc.mark_passed(job_dir)
            result["ok"] = True
            logger.log(f"QC PASSED ({duration:.0f}s)")
        else:
            qc.quarantine(job_dir, reasons)
            result["error"] = "; ".join(reasons)
            logger.log(f"QC FAILED → quarantine: {result['error']}")

        result["total_cost_usd"] = costs.job_cost(job_dir)["total_usd"]
        _progress(progress_cb, 100,
                  "Done" if result["ok"] else "Failed (quarantined)")

        # 8. Google Drive auto-upload (if enabled)
        try:
            if (cfg.get("providers", {}).get("gdrive_auto_upload")
                    and result["ok"]):
                from . import gdrive as _gd
                from .config import CONFIG_PATH as _CP
                _gd.init(_CP.parent)
                if _gd.is_configured():
                    _progress(progress_cb, 100, "Uploading to Google Drive...")
                    logger.log("[8] Google Drive upload...")
                    ch_name = channel.get("name", channel_id)
                    drive_res = _gd.upload_job(
                        job_dir, ch_name, title,
                        final_mp4=result.get("final_mp4"),
                        logger=logger.log)
                    if drive_res.get("folder_url"):
                        result["drive_folder_url"] = drive_res["folder_url"]
                        logger.log(
                            f"    Drive upload complete -> {drive_res['folder_url']}")
        except Exception as e:  # noqa: BLE001
            logger.log(f"    gdrive: skipped (not critical): {e}")

        # 9. Windows notification (video ready)
        try:
            _notify_done(title, result["ok"],
                         result.get("drive_folder_url", ""))
        except Exception:  # noqa: BLE001
            pass

        return result
    except Exception as e:  # noqa: BLE001
        msg = f"pipeline crashed: {e}"
        logger.log(msg)
        try:
            qc.quarantine(job_dir, [msg])
        except Exception:  # noqa: BLE001
            pass
        result["error"] = msg[:500]
        result["total_cost_usd"] = costs.job_cost(job_dir)["total_usd"]
        _progress(progress_cb, 100, "Failed (quarantined)")
        return result
    finally:
        costs.clear_current_job_dir()


def _find_presenter(cfg, presenter_id):
    for p in cfg.get("presenters") or []:
        if p.get("id") == presenter_id:
            return p
    presenters = cfg.get("presenters") or []
    return presenters[0] if presenters else {}


def _notify_done(title, ok, drive_url=""):
    """Send a Windows desktop notification when a video finishes.

    Uses plyer (pip install plyer) if available.
    Falls back to a simple print if not installed.
    Never raises.
    """
    try:
        status = "Video ready!" if ok else "Video failed (check log)"
        msg_parts = [f'"{title}"', status]
        if drive_url:
            msg_parts.append("Uploaded to Google Drive.")
        message = "  ".join(msg_parts)
        try:
            from plyer import notification as _notif
            _notif.notify(
                title="Avatar Production by MIB",
                message=message[:256],
                app_name="MIB",
                timeout=10,
            )
        except ImportError:
            # plyer not installed — silent, no crash
            pass
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
