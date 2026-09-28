"""mib/costs.py — paid-API cost tracker + per-minute estimates.

Copied from the proven factory/costs.py, extended with grok-image and
gemini-image unit prices (ESTIMATES) and estimate_per_minute() for the
wizard channel cards.

Every paid call the pipeline makes is appended to <job_dir>/costs.json.
Free providers log nothing: a free-mode run always stays $0.00.

Cost logging must NEVER break a run: every public function is internally
exception-proof, and callers additionally wrap hooks in try/except.
"""
import json
import time
from pathlib import Path

# ---------------------------------------------------------------- prices
# (service, kind) -> USD per unit. Unknown/absent key -> treated as $0.

UNIT_PRICES = {
    ("ai33pro", "tts_chars"): 0.00010,        # ESTIMATE (credit pricing varies)
    ("gemini-image", "image"): 0.039,         # ESTIMATE (~$30/1M output tokens)
    ("grok-image", "image"): 0.07,            # ESTIMATE (xAI imagine pricing;
                                             # verify on x.ai — placeholder)
    ("llm", "tokens_in"): 0.00000030,        # ESTIMATE (~$0.30 / 1M tokens)
    ("llm", "tokens_out"): 0.00000100,       # ESTIMATE (~$1.00 / 1M tokens)
    ("image", "cutout_local"): 0.0,          # local fallback: always free.
}

PRICE_NOTES = {
    "ai33pro:tts_chars": {
        "estimated": True,
        "note": "AI33 Pro bills in platform credits. Placeholder rate — check "
                "your balance in Settings (GET /v1/credits) and adjust "
                "UNIT_PRICES.",
    },
    "gemini-image:image": {
        "estimated": True,
        "note": "Estimate for gemini-2.5-flash-image (~$30/1M output tokens, "
                "~1290 tokens/image). Verify current pricing.",
    },
    "grok-image:image": {
        "estimated": True,
        "note": "Placeholder for xAI image generation — xAI prices move; "
                "verify on the xAI console before relying on estimates.",
    },
    "llm:tokens_in": {
        "estimated": True,
        "note": "Placeholder — real rates differ per provider. Local rules "
                "engine is free ($0, never logged).",
    },
    "llm:tokens_out": {
        "estimated": True,
        "note": "Placeholder — same caveat as tokens_in.",
    },
    "image:cutout_local": {
        "estimated": False,
        "note": "Local Pillow fallback image: $0.00 always.",
    },
}

# ---------------------------------------------------------------- job context
_CURRENT_JOB_DIR = None


def set_current_job_dir(path):
    """Mark the job directory paid calls should be logged to."""
    global _CURRENT_JOB_DIR
    _CURRENT_JOB_DIR = str(path) if path else None


def clear_current_job_dir():
    """Drop the active job context (call in the pipeline's finally block)."""
    global _CURRENT_JOB_DIR
    _CURRENT_JOB_DIR = None


def current_job_dir():
    """Return the active job directory, or None when no job is running."""
    return _CURRENT_JOB_DIR


# ---------------------------------------------------------------- ledger

def _path(job_dir):
    return Path(job_dir) / "costs.json"


def init_job(job_dir):
    """Create costs.json {"lines": [], "total_usd": 0.0} if missing. Never raises."""
    try:
        p = _path(job_dir)
        if not p.exists():
            p.write_text(json.dumps({"lines": [], "total_usd": 0.0},
                                    indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def log_call(job_dir, service, kind, units, note=""):
    """Append one paid call to <job_dir>/costs.json and update the total.

    NEVER raises, and no-ops when job_dir is None (no active job context).
    """
    try:
        if job_dir is None:
            return
        data = job_cost(job_dir)
        try:
            units = float(units or 0)
        except (TypeError, ValueError):
            units = 0.0
        price = UNIT_PRICES.get((service, kind), 0.0)
        data["lines"].append({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "service": str(service),
            "kind": str(kind),
            "units": round(units, 4),
            "unit_price_usd": price,
            "cost_usd": round(units * price, 6),
            "note": str(note or ""),
        })
        data["total_usd"] = round(
            sum(float(l.get("cost_usd", 0.0) or 0.0) for l in data["lines"]), 4)
        _path(job_dir).write_text(json.dumps(data, indent=2),
                                   encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def job_cost(job_dir):
    """Return {"total_usd": float, "lines": [...]} for one job.

    Missing/corrupt costs.json -> {"total_usd": 0.0, "lines": []}. Never raises.
    """
    try:
        data = json.loads(_path(job_dir).read_text(encoding="utf-8"))
        return {"total_usd": float(data.get("total_usd", 0.0) or 0.0),
                "lines": data.get("lines") or []}
    except Exception:  # noqa: BLE001
        return {"total_usd": 0.0, "lines": []}


def total_cost(outdir):
    """Sum costs.json totals across output/*/*/costs.json. Never raises."""
    total = 0.0
    try:
        root = Path(outdir)
        if not root.is_dir():
            return 0.0
        for p in root.glob("*/*/costs.json"):
            try:
                total += job_cost(p.parent)["total_usd"]
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return round(total, 4)


def fmt(usd):
    """Format a dollar amount: 0.42 -> "$0.42". Never raises."""
    try:
        return f"${float(usd or 0.0):,.2f}"
    except Exception:  # noqa: BLE001
        return "$0.00"


# ---------------------------------------------------------------- estimates
# Per-minute estimate for the wizard channel cards, from enabled providers.

_CHARS_PER_MIN = 700.0      # ~140 wpm spoken English
_IMAGES_PER_MIN = 2.0       # one scene image per ~30s


def estimate_per_minute(channel_cfg, secrets):
    """Estimate USD/minute for a channel from enabled (keyed) providers.

    Returns a float. Free pipeline -> 0.0. Never raises.
    """
    try:
        total = 0.0
        secrets = secrets or {}
        voice = (channel_cfg or {}).get("voice") or {}
        if voice.get("provider") == "ai33pro" and secrets.get("ai33pro_api_key"):
            total += _CHARS_PER_MIN * UNIT_PRICES[("ai33pro", "tts_chars")]
        provs = ((channel_cfg or {}).get("image_providers")
                 or ["grok", "gemini", "local"])
        if "grok" in provs and secrets.get("xai_api_key"):
            total += _IMAGES_PER_MIN * UNIT_PRICES[("grok-image", "image")]
        elif "gemini" in provs and secrets.get("gemini_api_key"):
            total += _IMAGES_PER_MIN * UNIT_PRICES[("gemini-image", "image")]
        return round(total, 2)
    except Exception:  # noqa: BLE001
        return 0.0


def estimate_label(channel_cfg, secrets):
    """Gold card label: '$0.05/min' or '$0.00/min (all local, free)'."""
    try:
        v = estimate_per_minute(channel_cfg, secrets)
        if v <= 0:
            return "$0.00/min (all local, free)"
        return f"${v:.2f}/min"
    except Exception:  # noqa: BLE001
        return "$0.00/min"
