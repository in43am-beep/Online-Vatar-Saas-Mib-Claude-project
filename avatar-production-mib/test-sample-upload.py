"""Offscreen UI test: PC voice-sample upload option.

- store_voice_sample() copies a picked file into the app's own
  assets/voice_samples/ folder and returns the stored path
- VoicePickerDialog.upload_sample() -> result ("pc-sample", stored, name)
- SettingsDialog.browse_for_channel() with a pc-sample result switches to
  the Voice Clone tab and pre-fills the sample field
Run with QT_QPA_PLATFORM=offscreen and MIB_CONFIG_DIR=<tmpdir>.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MIB_CONFIG_DIR"] = tempfile.mkdtemp(prefix="mib-uitest-")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

from mib import config as config_mod  # noqa: E402
from mib.ui import settings as settings_mod  # noqa: E402
from mib.ui.settings import (  # noqa: E402
    SettingsDialog, VoicePickerDialog)
from mib.ui.wizard import WizardWindow  # noqa: E402

app = QApplication(sys.argv[:1])

# 1. store_voice_sample copies into the app's folder
src = Path(tempfile.mkdtemp(prefix="mib-src-")) / "my voice.WAV"
src.write_bytes(b"RIFF....fake-audio")
stored = config_mod.store_voice_sample(str(src))
assert stored != str(src), "should copy, not keep the original path"
sp = Path(stored)
assert sp.exists(), "stored sample file missing"
assert sp.parent == config_mod.SAMPLES_DIR, "not in the app samples dir"
assert sp.suffix == ".wav", "suffix should be normalized lowercase"
print("1. store_voice_sample copies into assets/voice_samples: OK")

cfg = config_mod.load_config()
secrets = config_mod.load_secrets()
win = WizardWindow(cfg, secrets)

# 2. picker upload_sample() sets the pc-sample result
dlg = VoicePickerDialog(win, cfg, secrets)
with patch.object(settings_mod.QFileDialog, "getOpenFileName",
                  return_value=(str(src), "")):
    dlg.upload_sample()
assert dlg.result is not None, "upload_sample did not set a result"
prov, vid, name = dlg.result
assert prov == "pc-sample", f"expected pc-sample, got {prov}"
assert Path(vid).exists(), "stored sample missing after upload"
assert name == "my voice.WAV"
print("2. VoicePickerDialog upload -> pc-sample result: OK")

# 3. browse_for_channel hands the sample to the Voice Clone tab
sdlg = SettingsDialog(win, cfg, secrets)
fake = VoicePickerDialog(sdlg, cfg, secrets)
fake.result = ("pc-sample", vid, name)
with patch.object(settings_mod, "VoicePickerDialog",
                  return_value=fake):
    fake.exec = lambda: QDialog.Accepted
    sdlg.browse_for_channel()
assert sdlg.clone_sample.text() == vid, "clone sample field not filled"
assert sdlg.tabs.currentIndex() == 2, "did not switch to Voice Clone tab"
print("3. browse_for_channel -> Voice Clone tab with sample: OK")

# 4. clone tab Choose file also stores into the app folder
with patch.object(settings_mod.QFileDialog, "getOpenFileName",
                  return_value=(str(src), "")):
    sdlg.pick_sample()
picked = sdlg.clone_sample.text()
assert Path(picked).parent == config_mod.SAMPLES_DIR, \
    "clone tab did not store into the app folder"
print("4. clone tab Choose file stores into app folder: OK")

# cleanup the samples created by this test
for p in config_mod.SAMPLES_DIR.glob("*"):
    try:
        p.unlink()
    except Exception:
        pass
print("ALL SAMPLE-UPLOAD CHECKS PASSED")
