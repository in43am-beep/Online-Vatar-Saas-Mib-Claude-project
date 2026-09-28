"""Quick pipeline test for the garlic beds title."""
import sys
from mib.config import load_config, load_secrets
from mib.pipeline import run_pipeline

cfg = load_config()
sec = load_secrets()

title      = "What I Always Put in My Garlic Beds: The Secret to Huge Bulbs"
channel_id = "kustorez-amish"   # avatar + amish gardening — perfect match

logs = []

def progress_cb(pct, msg):
    print(f"[{pct:3d}%] {msg}")

def log_cb(msg):
    print(f"       {msg}")
    logs.append(msg)

print(f"Title:   {title}")
print(f"Channel: {channel_id}")
print(f"Minutes: 3")
print("="*60)

result = run_pipeline(
    title, channel_id, cfg, sec,
    opts={"minutes_override": 3, "mode": "avatar"},
    progress_cb=progress_cb,
    log_cb=log_cb
)

print()
print("="*60)
print("RESULT:")
print("  ok:", result.get("ok"))
print("  error:", result.get("error"))
print("  final_mp4:", result.get("final_mp4"))
print("  duration_s:", result.get("duration_s"))
print("  cost_usd:", result.get("total_cost_usd"))
print("  qc_reasons:", result.get("qc_reasons"))
