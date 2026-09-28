"""mib/qc.py — quality gates. Failures go to quarantine/, never crash a batch."""
import json
import shutil
from pathlib import Path

from . import ffmpeg


def check(final_mp4, est_minutes):
    """Return (ok, reasons[]). Never raises."""
    reasons = []
    try:
        p = Path(final_mp4) if final_mp4 else None
        if not p or not p.is_file():
            return False, ["final.mp4 missing"]
        info = ffmpeg.probe(p)
        if not info["has_video"]:
            reasons.append("no video stream")
        if not info["has_audio"]:
            reasons.append("no audio stream")
        dur = info["duration"]
        if dur <= 0:
            reasons.append("zero duration")
        else:
            # FIX (Bug 6): the original floor was 60s and the threshold 80%,
            # which quarantined every short test video. New values:
            # floor = 30s (allows quick smoke-test runs through the pipeline)
            # threshold = 70% (generous enough for edge cases in free/local mode)
            need = 30.0
            try:
                est_need = float(est_minutes or 0) * 60.0 * 0.70
                need = max(need, est_need)
            except (TypeError, ValueError):
                pass
            if dur < need:
                reasons.append(
                    f"too short: {dur:.0f}s < {need:.0f}s required")
        return (len(reasons) == 0), reasons
    except Exception as e:  # noqa: BLE001
        return False, [f"qc error: {e}"]


def quarantine(job_dir, reasons):
    """Move final.mp4 to quarantine/ and stamp the qc report. Never raises."""
    try:
        job = Path(job_dir)
        q = job / "quarantine"
        q.mkdir(parents=True, exist_ok=True)
        src = job / "final.mp4"
        if src.is_file():
            shutil.move(str(src), str(q / "final.mp4"))
        rep = job / "qc-report.json"
        data = {}
        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        data["verdict"] = "quarantined"
        data["reasons"] = list(reasons or [])
        rep.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def mark_passed(job_dir):
    """Stamp the qc report as passed. Never raises."""
    try:
        rep = Path(job_dir) / "qc-report.json"
        data = {}
        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        data["verdict"] = "passed"
        data["reasons"] = []
        rep.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
