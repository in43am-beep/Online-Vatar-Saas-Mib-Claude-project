"""mib/app.py — entry point.

Run:   python -m mib.app
Smoke: QT_QPA_PLATFORM=offscreen python -m mib.app --smoke
"""
import sys

from PySide6.QtWidgets import QApplication

from . import config as config_mod
from .ui import theme
from .ui.wizard import WizardWindow


def build_window():
    config_mod.seed_app_dir()  # frozen exe: first-run seeding, no-op in dev
    cfg = config_mod.load_config()
    config_mod.ensure_secrets_file()
    secrets = config_mod.load_secrets()
    win = WizardWindow(cfg, secrets)
    return win


def smoke():
    """Offscreen smoke: open the wizard, walk steps 0->3, exit 0."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet(theme.qss())
    win = build_window()
    win.show()
    app.processEvents()

    # walk steps 0 -> 3 programmatically
    win.select_mode("avatar")
    assert win.state["mode"] == "avatar", "mode not set"
    win.go_step(1)
    first_channel = next(iter(win.cfg.get("channels", {})), "")
    assert first_channel, "no channels in config"
    win.select_channel(first_channel)
    assert win.state["channel"] == first_channel, "channel not set"
    win.go_step(2)
    presenters = win.cfg.get("presenters") or []
    assert presenters, "no presenters in config"
    win.select_presenter(presenters[0]["id"])
    assert win.state["presenter"] == presenters[0]["id"], "presenter not set"
    win.go_step(3)
    win.set_titles(["The Dog Who Waited 400 Days"])
    assert win.title_page.titles() == ["The Dog Who Waited 400 Days"], \
        "titles not set"
    # channel + presenter pages must have built their widgets
    assert win.channel_page.grid.count() > 0, "channel grid empty"
    assert win.presenter_page.grid.count() > 0, "presenter grid empty"
    app.processEvents()
    print("SMOKE OK: wizard opened, steps 0->3 walked, no crash")
    return 0


def main(argv=None):
    argv = argv or sys.argv[1:]
    if "--smoke" in argv:
        return smoke()
    app = QApplication(argv)
    app.setStyleSheet(theme.qss())
    win = build_window()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
