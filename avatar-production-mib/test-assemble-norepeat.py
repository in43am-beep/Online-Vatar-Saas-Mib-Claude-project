"""Integration test: assemble must not repeat avatar-spoken script.

3 beats x 10s, each a distinct tone (300/400/500 Hz). Avatar: intro 4s
(800 Hz, covers [0,4]) + mid at 15s, 4s (900 Hz, covers [15,19]).

Expected final timeline (30s = voiceover total, nothing duplicated):
  intro[0-4] beat0[4-10] beat1[10-15] mid[15-19] beat1[19-20] beat2[20-30]
We probe the dominant frequency at sample timestamps to prove each slice
is heard exactly once, in order, with no repeats.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mib.stages import assemble as st_assemble  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="asm-test-"))
(job := tmp / "job").mkdir()


def tone(freq, dur, out):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"sine=frequency={freq}:duration={dur}",
                    "-ar", "44100", "-ac", "2", str(out)],
                   check=True)


def img(out):
    from PIL import Image
    Image.new("RGB", (640, 360), (30, 30, 40)).save(out)


# beats: 300/400/500 Hz, 10s each
segments, images = [], []
for i, f in enumerate([300, 400, 500]):
    a = job / f"beat{i}.wav"
    tone(f, 10, a)
    im = job / f"img{i}.png"
    img(im)
    segments.append({"file": str(a), "duration": 10.0, "text": f"beat {i}"})
    images.append(str(im))

# avatar clips: intro 800 Hz 4s, mid 900 Hz 4s at voiceover-time 15
intro = job / "intro.mp4"
tone(800, 4, tmp / "intro.wav")
img(tmp / "av.png")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30",
                "-loop", "1", "-t", "4", "-i", str(tmp / "av.png"),
                "-i", str(tmp / "intro.wav"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(intro)], check=True)
mid = job / "mid.mp4"
tone(900, 4, tmp / "mid.wav")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "30",
                "-loop", "1", "-t", "4", "-i", str(tmp / "av.png"),
                "-i", str(tmp / "mid.wav"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(mid)], check=True)

avatar_result = {"intro": str(intro),
                 "mids": [{"file": str(mid), "at": 15.0}],
                 "presenter": "Test"}

final, dur = st_assemble.run(job, segments, images, avatar_result,
                             logger=None, subtitles=False,
                             script={"hook": "hook text"})
print("final duration:", dur)
assert abs(dur - 30.0) < 0.6, f"expected ~30s (no duplication), got {dur}"


def dom_freq(at):
    raw = tmp / "s.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(at), "-t", "1",
                    "-i", str(final), "-ar", "44100", "-ac", "1", str(raw)],
                   check=True)
    import wave
    w = wave.open(str(raw))
    data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    spec = np.abs(np.fft.rfft(data))
    freqs = np.fft.rfftfreq(len(data), 1 / 44100)
    return freqs[np.argmax(spec[1:]) + 1]


# (timestamp, expected dominant freq, label)
checks = [(2, 800, "intro speaks"),
          (5, 300, "beat0 continues (NOT repeated intro)"),
          (12, 400, "beat1 part 1"),
          (16, 900, "mid rejoin speaks NEW slice"),
          (19.4, 400, "beat1 resumes after mid (no repeat)"),
          (25, 500, "beat2")]
for at, exp, label in checks:
    got = dom_freq(at)
    ok = abs(got - exp) < 40
    print(f"  t={at:5.1f}s -> {got:6.1f} Hz (expect ~{exp}) {'OK' if ok else 'FAIL'} {label}")
    assert ok, f"{label}: got {got}, expected {exp}"

print("ASSEMBLE NO-REPEAT TEST PASSED")
