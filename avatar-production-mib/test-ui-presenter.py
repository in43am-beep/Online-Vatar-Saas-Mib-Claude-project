"""Offscreen UI test: presenter page still works after the mechanics update.

- presenter grid populates (never blank — the old test-pollution bug)
- Appearances buttons update the info label with chapter/interlude wording
- "+ Add presenter" adds a presenter and it appears in the grid
Run with QT_QPA_PLATFORM=offscreen and MIB_CONFIG_DIR=<tmpdir>.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MIB_CONFIG_DIR"] = tempfile.mkdtemp(prefix="mib-uitest-")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from mib import config as config_mod  # noqa: E402
from mib.ui.wizard import WizardWindow, PresenterPage  # noqa: E402

app = QApplication(sys.argv[:1])

cfg = config_mod.load_config()
secrets = config_mod.load_secrets()
assert cfg.get("presenters"), "presenters list is empty!"

win = WizardWindow(cfg, secrets)
page = win.presenter_page
assert isinstance(page, PresenterPage), "presenter_page missing"
page.refresh()

# grid populated
n_before = page.grid.count()
assert n_before > 0, "presenter grid is blank"
print(f"  ok   presenter grid populated ({n_before} widgets)")

# appearances info label
page.set_appear(3)
txt = page.appear_info.text()
assert "close-up" in txt and "split-screen" in txt, f"info text stale: {txt!r}"
print("  ok   appearances info describes chapter/interlude mechanics")

page.set_appear(1)
assert "without it" in page.appear_info.text()
print("  ok   intro-only info text")

# add presenter via the dialog-less path: simulate the add flow's data effect
n_presenters = len(win.cfg.get("presenters", []))
win.cfg.setdefault("presenters", []).append(
    {"id": "uitest", "name": "UITest", "image": "assets/avatars/maria.png",
     "gender": "f"})
page.refresh_grid()
assert page.grid.count() > n_before, "grid did not grow after add"
print("  ok   presenter grid grows after add")

# real config on disk untouched (isolation)
real_cfg = Path.home() / "workspace" / "avatar-production-mib" / "config" / "config.yaml"
if real_cfg.is_file():
    data = real_cfg.read_text(encoding="utf-8")
    assert "uitest" not in data and "ch1" not in data, "REAL CONFIG POLLUTED"
    print("  ok   real config.yaml untouched")

print("\nUI presenter tests passed")
