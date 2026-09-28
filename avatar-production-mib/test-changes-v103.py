"""Offscreen functional test for the two user-reported changes.

1. AI33 key persists: set key in SettingsDialog -> save() -> reopen dialog ->
   field must show the key (this was the reported bug: stale in-memory dict).
2. PC image upload: enable local_images for a channel with a temp folder of
   2 PNGs -> stages/images.run must produce scene PNGs copied from the pool
   (1920x1080), cycling in order.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from mib import config as config_mod  # noqa: E402
from mib.ui.settings import SettingsDialog  # noqa: E402
from mib.ui.wizard import WizardWindow  # noqa: E402
from mib.stages import images as st_images  # noqa: E402
from mib.providers import genimages  # noqa: E402

app = QApplication(sys.argv[:1])

# isolate config writes to a temp dir
tmp = Path(tempfile.mkdtemp(prefix="mib-test-"))
config_mod.ROOT = tmp
config_mod.CONFIG_PATH = tmp / "config" / "config.yaml"
config_mod.SECRETS_PATH = tmp / "config" / "secrets.yaml"
config_mod.SECRETS_EXAMPLE = tmp / "config" / "secrets.yaml.example"

cfg = config_mod.load_config()
secrets = config_mod.load_secrets()
assert secrets.get("ai33pro_api_key", "") == ""

win = WizardWindow(cfg, secrets)

# --- test 1: key persistence -------------------------------------------
dlg = SettingsDialog(win, win.cfg, win.secrets)
dlg.ai33_key.setText("test-key-123")
dlg.save()  # writes disk + pushes back into win.secrets
assert win.secrets.get("ai33pro_api_key") == "test-key-123", \
    f"win.secrets not updated: {win.secrets.get('ai33pro_api_key')!r}"
disk = config_mod.load_secrets()
assert disk.get("ai33pro_api_key") == "test-key-123", "not on disk"

# simulate what open_settings does on reopen
win.secrets.clear()
win.secrets.update(config_mod.load_secrets())
dlg2 = SettingsDialog(win, win.cfg, win.secrets)
assert dlg2.ai33_key.text() == "test-key-123", \
    f"reopened dialog shows: {dlg2.ai33_key.text()!r}"
print("TEST 1 OK: ai33 key persists across save + dialog reopen")

# --- test 2: pc image pool ----------------------------------------------
imgfolder = tmp / "my-images"
imgfolder.mkdir()
from PIL import Image
for i, color in enumerate([(200, 60, 60), (60, 200, 60)]):
    Image.new("RGB", (800, 600), color).save(imgfolder / f"pic{i}.jpg")

ch = win.cfg["channels"]["behind-the-hug"]
ch["local_images"] = {"enabled": True, "folder": str(imgfolder)}
pool = genimages.local_pool(win.cfg, "behind-the-hug")
assert len(pool) == 2, f"pool={pool}"
assert pool[0].name == "pic0.jpg" and pool[1].name == "pic1.jpg"

script = {"title": "T", "hook": "h",
          "beats": [{"name": "b1", "narration": "n1", "image_prompt": "p1"},
                    {"name": "b2", "narration": "n2", "image_prompt": "p2"},
                    {"name": "b3", "narration": "n3", "image_prompt": "p3"}],
          "cta": "c"}
job = tmp / "job1"
paths = st_images.run(job, script, "behind-the-hug", win.cfg, win.secrets,
                      logger=None)
assert len(paths) == 5, f"expected 5 scenes, got {len(paths)}"
for p in paths:
    im = Image.open(p)
    assert im.size == (1920, 1080), f"{p} size={im.size}"
# cycling order: pic0, pic1, pic0, pic1, pic0
import hashlib
h = [hashlib.md5(Image.open(p).tobytes()).hexdigest() for p in paths]
assert h[0] == h[2] == h[4] and h[1] == h[3] and h[0] != h[1], \
    "cycling order wrong"
print("TEST 2 OK: pc images used, 1920x1080, cycled in order")

# --- test 3: disabled -> AI flow still fine ------------------------------
ch["local_images"] = {"enabled": False, "folder": str(imgfolder)}
assert genimages.local_pool(win.cfg, "behind-the-hug") == []
job2 = tmp / "job2"
paths2 = st_images.run(job2, script, "behind-the-hug", win.cfg, win.secrets,
                       logger=None)
assert len(paths2) == 5 and all(Path(p).exists() for p in paths2)
print("TEST 3 OK: disabled -> falls back to AI/local flow")

print("ALL TESTS PASSED")
