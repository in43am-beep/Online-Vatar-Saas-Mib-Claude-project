"""test-presenter-mechanics.py — unit + render tests for the reference-style
presenter mechanics (chapter openings, split-screen interludes, progressive
captions, bell watermark, soft promo). Run with MIB_CONFIG_DIR=<tmpdir>.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="mib-test-")
os.environ["MIB_CONFIG_DIR"] = TMP

sys.path.insert(0, os.path.expanduser("~/workspace/avatar-production-mib"))

from pathlib import Path  # noqa: E402

from mib.stages import avatar as st_avatar  # noqa: E402
from mib.stages import assemble as st_assemble  # noqa: E402
from mib.stages import script as st_script  # noqa: E402
from mib import ffmpeg  # noqa: E402
from mib.config import ROOT  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok  " if cond else "  FAIL") + f" {name} {extra}")


# --- 1. plan_segments -------------------------------------------------------
# fake 15-min video: hook 17s, 6 beats ~135s each, cta 20s
starts, durs, cum = [], [], 0.0
for d in [17.0] + [135.0] * 6 + [20.0]:
    starts.append(cum)
    durs.append(d)
    cum += d
total = cum  # 847s

p = st_avatar.plan_segments(total, starts, durs, [], seconds=6, appearances=1)
check("appearances=1 -> intro only", len(p) == 1 and p[0]["kind"] == "intro")

p = st_avatar.plan_segments(total, starts, durs, [3, 4, 5], seconds=6,
                            appearances=4)
mids = [x for x in p if x["kind"] != "intro"]
check("3 rejoin beats -> 3 chapters", len(mids) == 3
      and all(m["kind"] == "chapter" for m in mids),
      str([(m["at"], m["dur"]) for m in mids]))
check("chapter at beat start", abs(mids[0]["at"] - starts[3]) < 0.01)
check("chapter dur capped at 45s", all(m["dur"] <= 45.0 for m in mids))
check("chapter opens with close-up", all(m["closeup_s"] > 0 for m in mids))

p = st_avatar.plan_segments(total, starts, durs, [3, 4, 5], seconds=6,
                            appearances=2)
mids = [x for x in p if x["kind"] != "intro"]
check("cap respected (appearances=2 -> 1 mid)", len(mids) == 1)

p = st_avatar.plan_segments(total, starts, durs, [], seconds=6, appearances=3)
mids = [x for x in p if x["kind"] != "intro"]
check("big gap gets interlude", len(mids) >= 1
      and all(m["kind"] == "interlude" for m in mids),
      str([(m["at"], m["dur"]) for m in mids]))
check("interlude is short split-screen",
      all(m["dur"] == 7.0 and m["closeup_s"] == 0.0 for m in mids))

p = st_avatar.plan_segments(0, [], [], [], seconds=6, appearances=1)
check("never raises on empty input", isinstance(p, list) and len(p) >= 1)

# --- 2. progressive captions -------------------------------------------------
tl = [(0.0, 12.0, "One two three four five six seven eight. Short end.")]
blocks = st_assemble._build_srt_entries(tl)
texts = []
for b in blocks:
    lines = b.strip().split("\n")
    texts.append(" ".join(lines[2:]))
check("srt blocks produced", len(blocks) >= 3, f"n={len(blocks)}")
check("first block is the sentence start",
      texts[0].startswith("One two three four"))
# cumulative growth within the long sentence
long_blocks = [t for t in blocks]
grew = any(len(long_blocks[i + 1]) > len(long_blocks[i])
           for i in range(len(long_blocks) - 1))
check("captions grow word-by-word", grew)
check("no block exceeds 3 lines",
      all(len(b.strip().split("\n")) - 2 <= 3 for b in blocks))

# --- 3. soft promo ------------------------------------------------------------
pat = {"name": "t", "soft_promo_line": "Links are in the description below."}
scr = st_script.build_script("Test title here", 5, channel=None, pattern=pat)
hits = sum(1 for b in scr["beats"]
           if "Links are in the description below." in b["narration"])
check("soft promo inserted exactly once", hits == 1)
scr2 = st_script.build_script("Test title here", 5)
hits2 = sum(1 for b in scr2["beats"] if "description below" in b["narration"])
check("no promo when pattern has none", hits2 == 0)

# --- 4. real renders -----------------------------------------------------------
work = Path(TMP) / "renders"
work.mkdir(exist_ok=True)
maria = str(ROOT / "assets" / "avatars" / "maria.png")
walter = str(ROOT / "assets" / "avatars" / "walter.png")
tone = str(work / "tone.m4a")
ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=900",
            "-c:a", "aac", "-ar", "44100", tone], timeout=120)
short_tone = str(work / "short-tone.m4a")
ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-c:a", "aac", "-ar", "44100", short_tone], timeout=60)

cu = work / "closeup.mp4"
ok = st_avatar._closeup_clip(maria, short_tone, cu, 5.0)
pr = ffmpeg.probe(str(cu))
check("close-up clip renders 1920x1080", ok and pr["width"] == 1920
      and pr["height"] == 1080, str((pr["width"], pr["height"])))

sp = work / "split.mp4"
ok = st_avatar._split_clip(maria, walter, short_tone, sp, 5.0)
pr = ffmpeg.probe(str(sp))
check("split-screen renders 1920x1080", ok and pr["width"] == 1920
      and pr["height"] == 1080)

# full avatar.run with chapter plan (exercises concat of close-up + split)
segs = [{"name": "hook", "duration": 17.0}]
for i in range(6):
    segs.append({"name": f"beat-{i}", "duration": 135.0})
segs.append({"name": "cta", "duration": 20.0})
fake_script = {"beats": [{"narration": "x", "rejoin": i in (2, 3, 4)}
                         for i in range(6)]}
res = st_avatar.run(str(work / "job"), tone,
                    {"id": "maria", "name": "Maria",
                     "image": "assets/avatars/maria.png"},
                    seconds=6, appearances=4, total_duration=total,
                    voice_segments=segs, script=fake_script,
                    images=[walter] * 8)
check("avatar.run intro built", bool(res["intro"])
      and Path(res["intro"]).is_file())
check("avatar.run 3 chapter mids built",
      len(res["mids"]) == 3
      and all(Path(m["file"]).is_file() for m in res["mids"]),
      str([(m["kind"], m["at"]) for m in res["mids"]]))

# bell overlay on a real clip
belled = st_assemble._overlay_bell(work, str(cu))
check("bell watermark overlays", Path(belled).is_file()
      and belled.endswith("final_bell.mp4"), belled)

# caption burn (best effort — filter may be unavailable)
subbed = st_assemble._burn_subtitles(
    work, str(cu), [(0.0, 5.0, "One two three four five. Six seven.")])
check("caption burn returns a file", Path(subbed).is_file(), subbed)

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
