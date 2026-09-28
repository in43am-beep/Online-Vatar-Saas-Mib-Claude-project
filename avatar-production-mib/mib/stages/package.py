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

        thumb = (f"YouTube thumbnail prompt: extreme close-up, emotional "
                 f"eyes, warm cinematic light, scene of {topic}, "
                 f"max 3 words of BIG text related to '{title[:40]}', "
                 f"no watermark.")
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
