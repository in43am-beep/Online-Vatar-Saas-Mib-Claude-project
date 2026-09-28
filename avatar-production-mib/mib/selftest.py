"""mib/selftest.py — FULL headless pipeline test (all-free providers).

Run: python -m mib.selftest
Builds output/selftest/the-dog-who-waited-400-days/final.mp4 with local
script, edge-tts (falls back to local tone when offline), local images.
Asserts: final.mp4 exists, ffprobe shows video+audio, duration >= 60s.
Exit 0 on PASS, 1 on FAIL.

The whole run is isolated to a temp MIB config dir: the test channel and any
UI-triggered saves can never touch the user's real config.yaml.
"""
import os
import sys
import tempfile
from pathlib import Path

# Isolate FIRST, before any mib import: the whole selftest run (config,
# secrets, key-pool state, character sheets) lives in a temp dir and can
# never touch the user's real config.yaml.
os.environ.setdefault("MIB_CONFIG_DIR",
                      tempfile.mkdtemp(prefix="mib-selftest-"))

from . import config as config_mod
from . import ffmpeg
from .config import ROOT
from .pipeline import run_pipeline

TITLE = "The Dog Who Waited 400 Days"


def main():
    print("== MIB selftest: full headless pipeline (all-free providers) ==")
    return _run()


def _run():
    cfg = config_mod.load_config()
    secrets = config_mod.load_secrets()

    # test channel: 1-minute target so the run finishes fast
    cfg.setdefault("channels", {})["selftest"] = {
        "name": "Selftest",
        "niche": "Automated pipeline test.",
        "default_minutes": 1,
        "mode": "avatar",
        "presenter": (cfg.get("presenters") or [{}])[0].get("id", ""),
        "voice": {"provider": "edge", "voice_id": "en-US-AvaNeural"},
        "subtitles": False,
    }
    provs = cfg.setdefault("providers", {})
    provs["presenter_seconds"] = 4
    # appearances=3 exercises the new chapter/interlude presenter mechanics
    # (intro cold open + 2 chapter segments) end to end
    provs["appearances"] = 3

    opts = {"mode": "avatar", "minutes_override": 1,
            "presenter_seconds": 4, "appearances": 3}

    def _prog(p, m):
        print(f"  [{p:3d}%] {m}", flush=True)

    res = run_pipeline(TITLE, "selftest", cfg, secrets, opts,
                       progress_cb=_prog, log_cb=lambda l: print("  " + l))

    final = res.get("final_mp4", "")
    print(f"-- result: ok={res.get('ok')} final={final}")
    print(f"   duration={res.get('duration_s')}s "
          f"cost=${res.get('total_cost_usd', 0):.2f} "
          f"qc={res.get('qc_reasons')} err={res.get('error')}")

    failures = []
    if not res.get("ok"):
        failures.append(f"pipeline not ok: {res.get('error')}")
    p = Path(final)
    if not p.is_file():
        failures.append("final.mp4 missing")
    else:
        info = ffmpeg.probe(p)
        if not info["has_video"]:
            failures.append("no video stream")
        if not info["has_audio"]:
            failures.append("no audio stream")
        if info["duration"] < 60:
            failures.append(f"too short: {info['duration']:.1f}s < 60s")
        if info["width"] != 1920 or info["height"] != 1080:
            failures.append(f"wrong size: {info['width']}x{info['height']}")

    job = ROOT / "output" / "selftest" / "the-dog-who-waited-400-days"
    for f in ("script.json", "qc-report.json", "title.txt",
              "description.txt", "tags.txt", "thumbnail-prompt.txt"):
        if not (job / f).is_file():
            failures.append(f"missing packaged file: {f}")
    desc = (job / "description.txt").read_text(encoding="utf-8") \
        if (job / "description.txt").is_file() else ""
    if "AI-generated" not in desc:
        failures.append("AI disclosure missing from description.txt")

    if failures:
        print("SELFTEST FAILED:")
        for f_ in failures:
            print("  -", f_)
        return 1
    print("SELFTEST PASSED: real mp4, video+audio, >=60s, 1920x1080, "
          "packaged + disclosed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
