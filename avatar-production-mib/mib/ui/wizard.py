"""mib/ui/wizard.py — the MAIN window: Mode -> Channel -> Presenter -> Title -> Generate.

Frontier dark+gold look, circled step rail with Hide/Show pills, gold nav.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QGridLayout, QSlider, QTextEdit, QPlainTextEdit,
    QProgressBar, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QSpinBox, QComboBox, QScrollArea, QFileDialog, QMessageBox, QCheckBox,
)

from .. import costs
from .. import config as config_mod
from ..config import ROOT, load_config, load_secrets, save_config
from ..pipeline import run_pipeline
from . import theme
from .logviewer import LogViewerDialog

GOLD = theme.GOLD

STEP_NAMES = ["Mode", "Channel", "Presenter", "Title", "Generate"]


class ClickFrame(QFrame):
    """QFrame that emits clicked on mouse press."""

    def __init__(self, on_click=None, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, ev):
        if self._on_click:
            self._on_click()
        super().mousePressEvent(ev)


def gold_label(text, size=15, bold=True):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {GOLD}; font-size: {size}px;"
        + ("font-weight: bold;" if bold else ""))
    return lbl


def h2(text):
    lbl = QLabel(text)
    lbl.setObjectName("h2")
    return lbl


def muted(text, wrap=True):
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(wrap)
    return lbl


# ---------------------------------------------------------------- pages

class ModePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setSpacing(18)
        lay.addWidget(h2("How should this video be made?"))
        row = QHBoxLayout()
        row.setSpacing(18)
        self.cards = {}
        for mode_id, title, desc in [
            ("frontier", "FRONTIER PRODUCTION",
             "Documentaries and edited videos: AI images, maps-style "
             "graphics, captions."),
            ("avatar", "AI AVATAR",
             "A real-looking presenter opens every video, then the "
             "pictures take over."),
        ]:
            card = ClickFrame(lambda m=mode_id: self.pick(m))
            card.setObjectName("channel_card")
            card.setMinimumSize(300, 190)
            cl = QVBoxLayout(card)
            t = QLabel(title)
            t.setObjectName("h3")
            cl.addWidget(t)
            cl.addWidget(muted(desc))
            cl.addStretch(1)
            row.addWidget(card)
            self.cards[mode_id] = card
        lay.addLayout(row)
        lay.addStretch(1)
        self.refresh()

    def pick(self, mode_id):
        self.win.state["mode"] = mode_id
        self.refresh()
        self.win.sync_rail()

    def refresh(self):
        for mid, card in self.cards.items():
            card.setObjectName("channel_card_sel"
                               if self.win.state["mode"] == mid
                               else "channel_card")
            card.style().unpolish(card)
            card.style().polish(card)


class ChannelPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        lay = QVBoxLayout(self)
        lay.addWidget(h2("Pick a channel"))
        lay.addWidget(muted("One channel, one niche. Costs are shown up "
                            "front — free pipeline means $0.00/min."))
        lay.addLayout(self.grid)
        lay.addStretch(1)
        self.refresh()

    def refresh(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        cfg, secrets = self.win.cfg, self.win.secrets
        channels = cfg.get("channels") or {}
        col = 0
        for cid, ch in channels.items():
            card = ClickFrame(lambda c=cid: self.pick(c))
            card.setObjectName("channel_card_sel"
                               if self.win.state["channel"] == cid
                               else "channel_card")
            card.setMinimumSize(280, 230)
            cl = QVBoxLayout(card)
            cl.addWidget(h2(ch.get("name", cid)))
            cl.addWidget(muted(ch.get("niche", "")))
            cl.addWidget(gold_label(
                costs.estimate_label(ch, secrets), size=16))

            # Avatar clip mode badge
            clip_mode = ch.get("avatar_clip_mode", "static")
            clip_secs = ch.get("avatar_clip_secs", 6)
            mode_label_txt = {
                "static": f"Option 1  Static PNG  {clip_secs}s",
                "card":   f"Option 2  Character Card  {clip_secs}s",
                "video":  f"Option 3  AI Video Clips  {clip_secs}s",
            }.get(clip_mode, f"Static  {clip_secs}s")
            mode_color = {
                "static": "#4a9eff",
                "card":   "#e0a23c",
                "video":  "#43c488",
            }.get(clip_mode, "#4a9eff")
            badge = QLabel(mode_label_txt)
            badge.setStyleSheet(
                f"color: {mode_color}; font-size: 11px; font-weight: bold;"
                f" padding: 2px 8px; background: {mode_color}22; border-radius: 4px;")
            cl.addWidget(badge)

            cl.addWidget(muted(
                f"{ch.get('default_minutes', 5)} min default  "
                f"{'avatar' if ch.get('mode') == 'avatar' else 'frontier'} mode"))

            # Drive status icon
            try:
                from .. import gdrive as _gd
                from ..config import CONFIG_PATH as _cp
                _gd.init(_cp.parent)
                drive_txt = ("Drive: auto-upload ON"
                             if (cfg.get("providers", {}).get("gdrive_auto_upload")
                                 and _gd.is_configured())
                             else "")
            except Exception:  # noqa: BLE001
                drive_txt = ""
            if drive_txt:
                d_lbl = QLabel(drive_txt)
                d_lbl.setStyleSheet(
                    "color: #43c488; font-size: 10px; padding: 2px 4px;")
                cl.addWidget(d_lbl)

            samp = ROOT / "output" / cid / "sample.mp4"
            if samp.is_file():
                b = QPushButton("Watch sample")
                b.clicked.connect(
                    lambda _=False, p=samp: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(p))))
                cl.addWidget(b)
            cl.addStretch(1)
            self.grid.addWidget(card, 0, col)
            col += 1
        # "+" add card
        add = ClickFrame(self.add_channel)
        add.setObjectName("channel_card")
        add.setMinimumSize(200, 210)
        al = QVBoxLayout(add)
        plus = QLabel("+")
        plus.setStyleSheet(f"color: {GOLD}; font-size: 48px;")
        plus.setAlignment(Qt.AlignCenter)
        al.addWidget(plus)
        al.addWidget(muted("Add channel", wrap=False))
        al.setAlignment(Qt.AlignCenter)
        self.grid.addWidget(add, 0, col)

    def pick(self, cid):
        self.win.state["channel"] = cid
        # keep presenter's channel default in sync
        ch = (self.win.cfg.get("channels") or {}).get(cid) or {}
        if ch.get("presenter"):
            self.win.state["presenter"] = ch["presenter"]
        self.refresh()
        self.win.sync_rail()
        self.win.presenter_page.refresh()

    def add_channel(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add channel")
        form = QFormLayout(dlg)
        name_e = QLineEdit()
        niche_e = QLineEdit()
        mins = QSpinBox()
        mins.setRange(1, 120)
        mins.setValue(10)
        form.addRow("Name:", name_e)
        form.addRow("Niche:", niche_e)
        form.addRow("Default minutes:", mins)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        name = name_e.text().strip() or "New Channel"
        cid = "".join(c.lower() if c.isalnum() else "-"
                      for c in name).strip("-") or "channel"
        cfg = self.win.cfg
        cfg.setdefault("channels", {})[cid] = {
            "name": name,
            "niche": niche_e.text().strip() or "A new niche.",
            "default_minutes": mins.value(),
            "mode": self.win.state.get("mode", "avatar"),
            "presenter": (cfg.get("presenters") or [{}])[0].get("id", ""),
            "voice": {"provider": "edge", "voice_id": "en-US-AvaNeural"},
            "subtitles": False,
        }
        save_config(cfg)
        self.refresh()


class PresenterPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.filter = "all"
        lay = QVBoxLayout(self)
        lay.addWidget(h2("Pick a presenter"))
        # filters
        frow = QHBoxLayout()
        frow.addWidget(muted("Show:"))
        self.filter_btns = {}
        for fid, fname in [("all", "All"), ("f", "Women"), ("m", "Men")]:
            b = QPushButton(fname)
            b.setCheckable(True)
            b.setChecked(fid == "all")
            b.clicked.connect(lambda _=False, f=fid: self.set_filter(f))
            frow.addWidget(b)
            self.filter_btns[fid] = b
        frow.addStretch(1)
        add_b = QPushButton("+ Add presenter")
        add_b.clicked.connect(self.add_presenter)
        frow.addWidget(add_b)
        lay.addLayout(frow)
        # grid
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        lay.addLayout(self.grid)
        # seconds + appearances
        lay.addWidget(h2("Presenter time"))
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Seconds of presenter:"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(2, 15)
        self.slider.setValue(self.win.state.get("seconds", 6))
        self.slider.setMinimumWidth(220)
        self.slider.valueChanged.connect(self.seconds_changed)
        srow.addWidget(self.slider)
        self.cost_lbl = gold_label("", size=15)
        srow.addWidget(self.cost_lbl)
        srow.addStretch(1)
        lay.addLayout(srow)
        arow = QHBoxLayout()
        arow.addWidget(QLabel("Appearances:"))
        self.appear_btns = {}
        for aid, aname in [(1, "Intro only"), (2, "Intro + 1"),
                           (3, "Intro + 2"), (4, "Intro + 3"),
                           (6, "Intro + 5")]:
            b = QPushButton(aname)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, a=aid: self.set_appear(a))
            arow.addWidget(b)
            self.appear_btns[aid] = b
        arow.addStretch(1)
        lay.addLayout(arow)
        self.appear_info = muted("")
        self.appear_info.setWordWrap(True)
        lay.addWidget(self.appear_info)
        # voice lock chip
        vrow = QHBoxLayout()
        self.voice_chip = QLabel()
        self.voice_chip.setObjectName("status_pill")
        chg = QPushButton("Change voice")
        chg.clicked.connect(self.change_voice)
        vrow.addWidget(self.voice_chip)
        vrow.addWidget(chg)
        vrow.addStretch(1)
        lay.addLayout(vrow)
        lay.addStretch(1)
        self.refresh()

    def set_filter(self, fid):
        self.filter = fid
        for k, b in self.filter_btns.items():
            b.setChecked(k == fid)
        self.refresh_grid()

    def set_appear(self, aid):
        self.win.state["appearances"] = aid
        for k, b in self.appear_btns.items():
            b.setChecked(k == aid)
        self.update_appear_info()

    def update_appear_info(self):
        """Plain-language explanation of where the avatar shows up."""
        a = self.win.state.get("appearances", 1)
        if a <= 1:
            self.appear_info.setText(
                "The avatar opens the video, then the story continues "
                "without it.")
            return
        self.appear_info.setText(
            f"The avatar opens the video on a full-screen close-up, then "
            f"comes back {a - 1} more time(s): longer chapter openings "
            f"(close-up, then split-screen with the avatar on the right) "
            f"and short split-screen check-ins between them, about every "
            f"1–3 minutes. Each time it speaks the script at that point, "
            f"so viewers stay connected.")

    def seconds_changed(self, v):
        self.win.state["seconds"] = v
        self.update_cost()

    def update_cost(self):
        # local presenter rendering is free
        s = self.win.state.get("seconds", 6)
        a = self.win.state.get("appearances", 1)
        self.cost_lbl.setText(
            f"≈ $0.00 · {s}s per appearance × {a} (local, free)")

    def pick(self, pid):
        dlg = QDialog(self)
        dlg.setWindowTitle("Presenter preview")
        lay = QVBoxLayout(dlg)
        pres = next((p for p in self.win.cfg.get("presenters", [])
                     if p.get("id") == pid), {})
        img = QLabel()

        def show_img():
            p = ROOT / (pres.get("image") or "")
            if p.is_file():
                img.setPixmap(QPixmap(str(p)).scaled(
                    420, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        show_img()
        img.setAlignment(Qt.AlignCenter)
        lay.addWidget(img)
        lay.addWidget(h2(pres.get("name", pid)))
        up = QPushButton("Upload avatar from PC…")
        up.clicked.connect(lambda: self.upload_avatar(pres, show_img))
        lay.addWidget(up)
        gen = QPushButton("Generate avatar with Gemini…")
        gen.clicked.connect(lambda: self.generate_avatar(pres, show_img))
        lay.addWidget(gen)
        use = QPushButton("Use this presenter")
        use.setObjectName("primary")
        use.clicked.connect(dlg.accept)
        lay.addWidget(use)
        if dlg.exec() == QDialog.Accepted:
            self.win.state["presenter"] = pid
            ch = (self.win.cfg.get("channels") or {}).get(
                self.win.state["channel"]) or {}
            ch["presenter"] = pid
            save_config(self.win.cfg)
            self.refresh_grid()

    def upload_avatar(self, pres, refresh_cb):
        """Let the user pick an avatar image from their PC (frozen-safe)."""
        fn, _ = QFileDialog.getOpenFileName(
            self, "Choose avatar image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not fn:
            return
        try:
            from PIL import Image
            dest = ROOT / "assets" / "avatars" / f"{pres.get('id')}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            Image.open(fn).convert("RGB").save(dest, "PNG")
            pres["image"] = f"assets/avatars/{dest.name}"
            save_config(self.win.cfg)
            refresh_cb()
            self.refresh_grid()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Avatar",
                                f"Could not use that image: {e}"[:300])

    def generate_avatar(self, pres, refresh_cb):
        """Generate the presenter's portrait with Gemini (key pool).

        The description the user types becomes a photorealistic head-and-
        shoulders portrait, saved as this presenter's locked avatar. The
        pipeline then pairs it with the channel's locked voice automatically.
        """
        from ..keypool import pool_from_secrets
        pool = pool_from_secrets("gemini-image", self.win.secrets,
                                 "gemini_api_key", "gemini_api_keys",
                                 config_mod.CONFIG_PATH.parent)
        if pool is None:
            QMessageBox.warning(
                self, "Avatar",
                "No Gemini API key yet — add your keys in Settings → API Keys "
                "first, then generate.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Generate avatar with Gemini")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Describe the presenter:"))
        desc = QTextEdit()
        desc.setMaximumHeight(80)
        desc.setPlaceholderText(
            "e.g. elderly Amish man with a long grey beard, plain dark "
            "shirt, kind eyes")
        lay.addWidget(desc)
        status = QLabel("")
        status.setObjectName("muted")
        status.setWordWrap(True)
        lay.addWidget(status)
        btns = QDialogButtonBox(QDialogButtonBox.Cancel)
        gen_b = QPushButton("Generate")
        gen_b.setObjectName("primary")
        btns.addButton(gen_b, QDialogButtonBox.AcceptRole)
        lay.addWidget(btns)
        btns.rejected.connect(dlg.reject)

        worker = {"thread": None}

        def on_generate():
            d = desc.toPlainText().strip()
            if not d:
                status.setText("Type a short description first.")
                return
            gen_b.setEnabled(False)
            status.setText("Asking Gemini… (this can take a minute)")
            dest = ROOT / "assets" / "avatars" / f"{pres.get('id')}.png"
            model = ((self.win.cfg.get("providers") or {})
                     .get("gemini_model") or "gemini-2.5-flash-image")
            description = d

            class _W(QThread):
                sig_done = Signal(bool, str)

                def __init__(self, pool, model, description, dest):
                    super().__init__()
                    self._pool, self._model = pool, model
                    self._description, self._dest = description, dest

                def run(self):  # noqa: D102
                    try:
                        from ..providers import genimages
                        genimages.generate_avatar_image(
                            self._pool, self._model,
                            self._description, self._dest)
                        self.sig_done.emit(True, str(self._dest))
                    except Exception as e:  # noqa: BLE001
                        self.sig_done.emit(False, str(e)[:300])

            w = _W(pool, model, description, dest)
            worker["thread"] = w

            def on_done(ok, msg):
                gen_b.setEnabled(True)
                if ok:
                    pres["image"] = f"assets/avatars/{dest.name}"
                    save_config(self.win.cfg)
                    refresh_cb()
                    self.refresh_grid()
                    dlg.accept()
                else:
                    status.setText(f"Gemini failed: {msg}")

            w.sig_done.connect(on_done)
            w.start()

        gen_b.clicked.connect(on_generate)
        dlg.exec()

    def change_voice(self):
        from .settings import VoicePickerDialog
        dlg = VoicePickerDialog(self, self.win.cfg, self.win.secrets)
        if dlg.exec() == QDialog.Accepted and dlg.result:
            provider, voice_id, vname = dlg.result
            if provider == "pc-sample":
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(
                    self,
                    "Voice sample uploaded",
                    "Your sample was saved in the app's folder.\n\n"
                    "To turn it into a voice, open Settings → Voice Clone, "
                    "give it a name and click 'Create clone' — the new "
                    "voice locks to the channel automatically.")
                return
            ch = (self.win.cfg.get("channels") or {}).get(
                self.win.state["channel"]) or {}
            ch["voice"] = {"provider": provider, "voice_id": voice_id,
                           "name": vname}
            save_config(self.win.cfg)
            self.refresh()

    def refresh(self):
        self.slider.setValue(self.win.state.get("seconds", 6))
        for k, b in self.appear_btns.items():
            b.setChecked(k == self.win.state.get("appearances", 1))
        self.update_cost()
        self.update_appear_info()
        ch = (self.win.cfg.get("channels") or {}).get(
            self.win.state["channel"]) or {}
        v = ch.get("voice") or {}
        vname = v.get("name") or v.get("voice_id") or "default"
        self.voice_chip.setText(f"🔒 Voice: {vname} ({v.get('provider', 'edge')})")
        self.refresh_grid()

    def refresh_grid(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        presenters = self.win.cfg.get("presenters") or []
        col = 0
        for pres in presenters:
            g = (pres.get("gender") or "").lower()
            if self.filter != "all" and g != self.filter:
                continue
            card = ClickFrame(lambda p=pres["id"]: self.pick(p))
            sel = self.win.state.get("presenter") == pres["id"]
            card.setObjectName("channel_card_sel" if sel else "channel_card")
            card.setMinimumSize(190, 240)
            cl = QVBoxLayout(card)
            img = QLabel()
            p = ROOT / (pres.get("image") or "")
            if p.is_file():
                img.setPixmap(QPixmap(str(p)).scaled(
                    160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            img.setAlignment(Qt.AlignCenter)
            cl.addWidget(img)
            nm = QLabel(pres.get("name", ""))
            nm.setAlignment(Qt.AlignCenter)
            cl.addWidget(nm)
            cl.addStretch(1)
            self.grid.addWidget(card, 0, col)
            col += 1

    def add_presenter(self):
        """Add a new presenter (name + gender + optional image)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Add presenter")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Name:"))
        name_e = QLineEdit()
        name_e.setPlaceholderText("e.g. Samuel")
        lay.addWidget(name_e)
        lay.addWidget(QLabel("Gender:"))
        gender_e = QComboBox()
        gender_e.addItems(["m", "f"])
        lay.addWidget(gender_e)
        img_path = {"path": ""}

        def choose_img():
            fn, _ = QFileDialog.getOpenFileName(
                self, "Choose presenter image", "",
                "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
            if fn:
                img_path["path"] = fn
                img_lbl.setText(Path(fn).name)

        irow = QHBoxLayout()
        img_btn = QPushButton("Choose image… (optional)")
        img_btn.clicked.connect(choose_img)
        img_lbl = QLabel("no image yet")
        img_lbl.setObjectName("muted")
        irow.addWidget(img_btn)
        irow.addWidget(img_lbl)
        irow.addStretch(1)
        lay.addLayout(irow)
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        name = name_e.text().strip() or "Presenter"
        pid = "".join(c.lower() if c.isalnum() else "-"
                      for c in name).strip("-") or "presenter"
        existing = {p.get("id") for p in
                    self.win.cfg.get("presenters") or []}
        base, n = pid, 2
        while pid in existing:
            pid = f"{base}-{n}"
            n += 1
        image_rel = ""
        if img_path["path"]:
            try:
                from PIL import Image
                dest = ROOT / "assets" / "avatars" / f"{pid}.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                Image.open(img_path["path"]).convert("RGB").save(dest, "PNG")
                image_rel = f"assets/avatars/{dest.name}"
            except Exception:  # noqa: BLE001
                image_rel = ""
        self.win.cfg.setdefault("presenters", []).append({
            "id": pid, "name": name,
            "image": image_rel,
            "gender": gender_e.currentText(),
        })
        save_config(self.win.cfg)
        self.win.state["presenter"] = pid
        self.refresh_grid()


class TitlePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(h2("Name your video"))
        lay.addWidget(muted("Type a title. One per line makes several."))
        self.edit = QTextEdit()
        self.edit.setPlaceholderText("The Dog Who Waited 400 Days\n"
                                     "A Second Chance at the Old Farm")
        self.edit.setMinimumHeight(220)
        lay.addWidget(self.edit)
        self.info = muted("")
        lay.addWidget(self.info)
        lay.addStretch(1)
        self.refresh()

    def refresh(self):
        ch = (self.win.cfg.get("channels") or {}).get(
            self.win.state["channel"]) or {}
        self.info.setText(
            f"Channel: {ch.get('name', '')} · "
            f"{ch.get('default_minutes', 5)} min default · "
            f"{'avatar' if self.win.state.get('mode') == 'avatar' else 'frontier'} mode")

    def titles(self):
        return [t.strip() for t in self.edit.toPlainText().splitlines()
                if t.strip()]


class GenWorker(QThread):
    sig_progress = Signal(str, int, str)
    sig_log = Signal(str)
    sig_done = Signal(str, dict)
    sig_all_done = Signal()

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs

    def run(self):
        for title, channel_id, cfg, secrets, opts in self.jobs:
            try:
                res = run_pipeline(
                    title, channel_id, cfg, secrets, opts,
                    progress_cb=lambda p, m, t=title:
                    self.sig_progress.emit(t, p, m),
                    log_cb=self.sig_log.emit)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "title": title, "job_dir": "",
                       "final_mp4": "", "duration_s": 0.0,
                       "total_cost_usd": 0.0, "qc_reasons": [],
                       "error": f"worker crashed: {e}"}
            self.sig_done.emit(title, res)
        self.sig_all_done.emit()


class GeneratePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(h2("Generate"))
        self.rows = QVBoxLayout()
        lay.addLayout(self.rows)
        lay.addWidget(theme.mini_label("live log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(220)
        lay.addWidget(self.log)
        lay.addStretch(1)
        self.worker = None
        self._row_widgets = {}

    def start(self, titles):
        # clear old rows
        while self.rows.count():
            it = self.rows.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._row_widgets = {}
        self.log.clear()
        for t in titles:
            frame = QFrame()
            frame.setObjectName("frontier_card")
            rl = QHBoxLayout(frame)
            name = QLabel(t)
            name.setWordWrap(True)
            name.setMinimumWidth(260)
            bar = QProgressBar()
            bar.setObjectName("thin")
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setMinimumWidth(200)
            status = QLabel("queued")
            status.setObjectName("muted")
            status.setMinimumWidth(220)
            openb = QPushButton("Open output folder")
            openb.setVisible(False)
            rl.addWidget(name, 2)
            rl.addWidget(bar, 2)
            rl.addWidget(status, 2)
            rl.addWidget(openb)
            self.rows.addWidget(frame)
            self._row_widgets[t] = (bar, status, openb)

        cfg, secrets = self.win.cfg, self.win.secrets
        ch = (cfg.get("channels") or {}).get(self.win.state["channel"]) or {}
        opts = {
            "mode": self.win.state.get("mode", "avatar"),
            "minutes_override": ch.get("default_minutes", 5),
            "presenter_seconds": self.win.state.get("seconds", 6),
            "appearances": self.win.state.get("appearances", 1),
        }
        jobs = [(t, self.win.state["channel"], cfg, secrets, opts)
                for t in titles]
        self.worker = GenWorker(jobs)
        self.worker.sig_progress.connect(self.on_progress)
        self.worker.sig_log.connect(self.on_log)
        self.worker.sig_done.connect(self.on_done)
        self.worker.sig_all_done.connect(self.on_all_done)
        self.worker.start()

    def on_progress(self, title, pct, msg):
        w = self._row_widgets.get(title)
        if w:
            w[0].setValue(pct)
            w[1].setText(msg)

    def on_log(self, line):
        self.log.appendPlainText(line)

    def on_done(self, title, res):
        w = self._row_widgets.get(title)
        if not w:
            return
        bar, status, openb = w
        bar.setValue(100)
        if res.get("ok"):
            status.setText(f"Done · {res.get('duration_s', 0):.0f}s · "
                           f"${res.get('total_cost_usd', 0):.2f}")
            status.setObjectName("check_ok")
            jd = res.get("job_dir", "")
            if jd:
                openb.setVisible(True)
                openb.clicked.connect(
                    lambda _=False, p=jd: QDesktopServices.openUrl(
                        QUrl.fromLocalFile(p)))
        else:
            status.setText("Failed → quarantine: "
                           + str(res.get("error", ""))[:80])
            status.setObjectName("check_todo")

    def on_all_done(self):
        self.log.appendPlainText("=== all videos finished ===")
        self.win.append_log("=== batch finished ===")


# ---------------------------------------------------------------- window

class WizardWindow(QMainWindow):
    # key-pool backend events arrive from worker threads -> queued to UI
    _key_event = Signal(str, str, str, str)

    def __init__(self, cfg, secrets):
        super().__init__()
        self.cfg = cfg
        self.secrets = secrets
        # surface key-pool failover messages in the app itself
        self._key_event.connect(self._on_key_event)
        try:
            from .. import keypool as _kp
            _kp.set_event_handler(
                lambda ev, svc, last4, detail:
                self._key_event.emit(ev, svc, last4, detail))
        except Exception:  # noqa: BLE001
            pass
        self.state = {
            "mode": "avatar",
            "channel": next(iter((cfg.get("channels") or {})), ""),
            "presenter": "",
            "seconds": (cfg.get("providers") or {}).get("presenter_seconds", 6),
            "appearances": (cfg.get("providers") or {}).get("appearances", 1),
            "titles": [],
        }
        ch = (cfg.get("channels") or {}).get(self.state["channel"]) or {}
        if ch.get("presenter"):
            self.state["presenter"] = ch["presenter"]
        elif cfg.get("presenters"):
            self.state["presenter"] = cfg["presenters"][0]["id"]

        self.setWindowTitle("Avatar Production by MIB")
        self.resize(1180, 780)
        root = QWidget()
        root.setObjectName("app_root")
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(28, 20, 28, 16)

        # header
        head = QHBoxLayout()
        title = QLabel("Avatar Production by MIB")
        title.setObjectName("h1")
        head.addWidget(title)
        head.addStretch(1)
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        head.addWidget(self.settings_btn)
        main.addLayout(head)
        sub = QLabel("Type a title. Get a finished video.")
        sub.setStyleSheet(f"color: {GOLD}; font-size: 17px;")
        main.addWidget(sub)

        # body: rail + pages
        body = QHBoxLayout()
        body.setSpacing(24)
        # rail
        rail_wrap = QVBoxLayout()
        self.rail_toggle = QPushButton("Hide ◀")
        self.rail_toggle.setCheckable(True)
        self.rail_toggle.clicked.connect(self.toggle_rail)
        rail_wrap.addWidget(self.rail_toggle)
        self.rail = QFrame()
        self.rail.setObjectName("panel")
        rl = QVBoxLayout(self.rail)
        rl.setSpacing(14)
        self.rail_rows = []
        for i, name in enumerate(STEP_NAMES):
            row = QHBoxLayout()
            dot = QLabel(str(i + 1))
            dot.setObjectName("stepdot")
            dot.setFixedSize(34, 34)
            dot.setAlignment(Qt.AlignCenter)
            lbl = QLabel(name)
            lbl.setObjectName("stepdot_label")
            row.addWidget(dot)
            row.addWidget(lbl)
            row.addStretch(1)
            rl.addLayout(row)
            self.rail_rows.append((dot, lbl))
        rl.addStretch(1)
        rail_wrap.addWidget(self.rail)
        rail_wrap.addStretch(1)
        body.addLayout(rail_wrap)

        # stacked pages
        self.stack = QStackedWidget()
        self.mode_page = ModePage(self)
        self.channel_page = ChannelPage(self)
        self.presenter_page = PresenterPage(self)
        self.title_page = TitlePage(self)
        self.generate_page = GeneratePage(self)
        for pg in (self.mode_page, self.channel_page, self.presenter_page,
                   self.title_page, self.generate_page):
            self.stack.addWidget(pg)
        body.addWidget(self.stack, 1)
        main.addLayout(body, 1)

        # nav
        nav = QHBoxLayout()
        nav.addStretch(1)
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn = QPushButton("Continue →")
        self.next_btn.setObjectName("primary")
        self.next_btn.setMinimumWidth(200)
        self.next_btn.clicked.connect(self.go_next)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        main.addLayout(nav)

        # help strip
        help_strip = QHBoxLayout()
        hs = QLabel("Stuck on anything? Read the log — it records every step.")
        hs.setObjectName("muted")
        help_strip.addWidget(hs)
        help_strip.addStretch(1)
        logb = QPushButton("Open log")
        logb.clicked.connect(self.open_log)
        help_strip.addWidget(logb)
        main.addLayout(help_strip)

        self.step = 0
        self.sync_rail()
        self.sync_nav()

    # -- rail ------------------------------------------------------
    def toggle_rail(self):
        hidden = self.rail_toggle.isChecked()
        self.rail.setVisible(not hidden)
        self.rail_toggle.setText("Show ▶" if hidden else "Hide ◀")

    def sync_rail(self):
        for i, (dot, _lbl) in enumerate(self.rail_rows):
            if i < self.step:
                dot.setObjectName("stepdot_done")
                dot.setText("✓")
            elif i == self.step:
                dot.setObjectName("stepdot_active")
                dot.setText(str(i + 1))
            else:
                dot.setObjectName("stepdot")
                dot.setText(str(i + 1))
            dot.style().unpolish(dot)
            dot.style().polish(dot)

    def sync_nav(self):
        self.back_btn.setEnabled(self.step > 0)
        if self.step == 4:
            self.next_btn.setText("Generate again")
        elif self.step == 3:
            self.next_btn.setText("Generate →")
        else:
            self.next_btn.setText("Continue →")

    # -- navigation ------------------------------------------------
    def go_back(self):
        if self.step > 0:
            self.step -= 1
            if self.step == 2 and self.state.get("mode") == "frontier":
                self.step = 1  # presenter skipped in frontier mode
            self.stack.setCurrentIndex(self.step)
            self.sync_rail()
            self.sync_nav()

    def go_next(self):
        if self.step == 0:
            self.step = 1
        elif self.step == 1:
            if not self.state.get("channel"):
                QMessageBox.warning(self, "Channel",
                                    "Pick a channel first.")
                return
            self.step = 3 if self.state.get("mode") == "frontier" else 2
            if self.step == 2:
                self.presenter_page.refresh()
        elif self.step == 2:
            if not self.state.get("presenter"):
                QMessageBox.warning(self, "Presenter",
                                    "Pick a presenter first.")
                return
            self.step = 3
            self.title_page.refresh()
        elif self.step == 3:
            titles = self.title_page.titles()
            if not titles:
                QMessageBox.warning(self, "Title",
                                    "Type at least one title.")
                return
            self.state["titles"] = titles
            self.step = 4
            self.stack.setCurrentIndex(4)
            self.sync_rail()
            self.sync_nav()
            self.generate_page.start(titles)
            return
        elif self.step == 4:
            # generate again
            self.generate_page.start(self.state.get("titles", []))
            return
        self.stack.setCurrentIndex(self.step)
        self.sync_rail()
        self.sync_nav()

    # -- programmatic API (smoke test) ------------------------------
    def select_mode(self, mode):
        self.mode_page.pick(mode)

    def select_channel(self, cid):
        self.channel_page.pick(cid)

    def select_presenter(self, pid):
        self.state["presenter"] = pid
        self.presenter_page.refresh_grid()

    def set_titles(self, titles):
        self.title_page.edit.setPlainText("\n".join(titles))

    def go_step(self, n):
        self.step = n
        self.stack.setCurrentIndex(n)
        self.sync_rail()
        self.sync_nav()

    # -- dialogs ----------------------------------------------------
    def open_settings(self):
        from .settings import SettingsDialog
        dlg = SettingsDialog(self, self.cfg, self.secrets)
        dlg.exec()

    def _on_key_event(self, event, service, last4, detail):
        """Backend key-pool message surfaced in the app status bar."""
        if event == "exhausted":
            msg = (f"⚠ {service}: key {last4} hit its limit — "
                   f"next key took over")
        elif event == "rejected":
            msg = (f"⛔ {service}: key {last4} rejected (dead?) — "
                   f"parked 24h, next key took over")
        elif event == "all_down":
            msg = f"⛔ {service}: ALL keys down — {detail}"[:160]
        elif event == "revived":
            msg = f"✓ {service}: key {last4} is back live"
        else:
            return
        try:
            self.statusBar().showMessage(msg, 10000)
        except Exception:  # noqa: BLE001
            pass
        # Reload from disk in place (dialog already wrote back into our
        # dicts, but a disk reload is the bulletproof path: keys the user
        # just saved are visible immediately, no restart needed).
        try:
            fresh_cfg = load_config()
            self.cfg.clear()
            self.cfg.update(fresh_cfg)
            fresh_sec = load_secrets()
            self.secrets.clear()
            self.secrets.update(fresh_sec)
        except Exception:  # noqa: BLE001
            pass
        self.channel_page.refresh()
        self.presenter_page.refresh()

    def open_log(self):
        # latest run.log under output/
        latest = None
        try:
            cands = sorted((ROOT / "output").rglob("run.log"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            latest = cands[0] if cands else None
        except Exception:  # noqa: BLE001
            latest = None
        LogViewerDialog(self, latest).exec()

    def append_log(self, line):
        pass  # reserved for a global log line
