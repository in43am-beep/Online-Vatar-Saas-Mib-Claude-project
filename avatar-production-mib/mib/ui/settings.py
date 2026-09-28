"""mib/ui/settings.py — provider options (the user's explicit requirements).

Every provider: enable toggle (key present), status dot, Test button.
Free default always works with zero keys.
"""
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTabWidget, QWidget, QFormLayout, QComboBox, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QSpinBox, QCheckBox, QDialogButtonBox,
    QTextEdit, QScrollArea, QTableWidget, QTableWidgetItem, QApplication,
    QProgressBar, QSplitter,
)

from .. import costs
from .. import config as config_mod
from ..config import save_config, save_secrets
from ..keypool import (KeyExhausted, KeyRejected, pool_from_secrets)
from ..patterns import (
    builtin_pattern_name, default_pattern, fetch_video_info, get_pattern,
    normalize_pattern,
)
from ..providers import ai33voice, edgevoice
from . import theme

GOLD = theme.GOLD


def status_dot(ok):
    lbl = QLabel("●")
    lbl.setStyleSheet(
        f"color: {'#43c488' if ok else '#5a6272'}; font-size: 18px;")
    return lbl


class VoicePickerDialog(QDialog):
    """Pick a voice -> (provider, voice_id, name)."""

    def __init__(self, parent, cfg, secrets):
        super().__init__(parent)
        self.cfg = cfg
        self.secrets = secrets
        self.result = None
        self.setWindowTitle("Pick a voice")
        self.resize(560, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Free Edge voices (no key needed):"))
        self.edge_list = QListWidget()
        self.edge_list.itemDoubleClicked.connect(self.accept_edge)
        lay.addWidget(self.edge_list)
        for v in edgevoice.list_voices():
            QListWidgetItem(f"{v['name']}  [{v['id']}]", self.edge_list)
        if not self.edge_list.count():
            QListWidgetItem("(offline — type an Edge voice id manually)",
                            self.edge_list)

        row = QHBoxLayout()
        row.addWidget(QLabel("…or type any voice id:"))
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("en-US-AvaNeural or clone_123 …")
        row.addWidget(self.manual)
        lay.addLayout(row)

        key = (secrets.get("ai33pro_api_key") or "").strip()
        if key:
            b = QPushButton("Load AI33 Pro voices…")
            b.clicked.connect(lambda: self.load_ai33(key))
            lay.addWidget(b)
            self.ai33_list = QListWidget()
            self.ai33_list.itemDoubleClicked.connect(self.accept_ai33)
            lay.addWidget(self.ai33_list)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept_manual)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        row2 = QHBoxLayout()
        upl = QPushButton("Upload voice sample from PC…")
        upl.setToolTip("Pick a 1–3 min mp3/wav of the voice from your PC. "
                       "It is copied into the app's own folder so it stays "
                       "even if the original file is moved, then handed to "
                       "the Voice Clone tab.")
        upl.clicked.connect(self.upload_sample)
        row2.addWidget(upl)
        row2.addStretch(1)
        lay.addLayout(row2)

    def upload_sample(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Voice sample", "",
            "Audio (*.mp3 *.wav *.m4a *.ogg *.flac)")
        if not p:
            return
        stored = config_mod.store_voice_sample(p)
        self.result = ("pc-sample", stored, Path(p).name)
        self.accept()

    def accept_edge(self, item):
        txt = item.text()
        vid = txt.split("[")[-1].rstrip("]") if "[" in txt else txt
        name = txt.split("[")[0].strip()
        self.result = ("edge", vid, name)
        self.accept()

    def accept_manual(self):
        vid = self.manual.text().strip()
        if not vid:
            # fall back to first edge selection
            it = self.edge_list.currentItem()
            if it:
                self.accept_edge(it)
                return
            QMessageBox.warning(self, "Voice", "Pick or type a voice id.")
            return
        prov = "ai33pro" if vid.startswith(
            ("clone_", "elevenlabs_", "minimax_", "kokoro_", "vbee_",
             "fishaudio_", "edge_")) else "edge"
        self.result = (prov, vid, vid)
        self.accept()

    def load_ai33(self, key):
        self.ai33_list.clear()
        try:
            for v in ai33voice.list_voices(key, page_size=50):
                QListWidgetItem(
                    f"{v['name']}  [{v['provider_label']}]  <{v['id']}>",
                    self.ai33_list)
        except ai33voice.AI33Error as e:
            QMessageBox.warning(self, "AI33 Pro", str(e))

    def accept_ai33(self, item):
        txt = item.text()
        vid = txt.split("<")[-1].rstrip(">")
        name = txt.split("[")[0].strip()
        self.result = ("ai33pro", vid, name)
        self.accept()


class CharacterSheetDialog(QDialog):
    """One-time character setup per channel: sheet image OR 4-5 full-body
    refs + full character details + how many scenes per video show them."""

    def __init__(self, parent, channel_id, channel_name=""):
        super().__init__(parent)
        from .. import character as charmod
        self.charmod = charmod
        self.channel_id = channel_id
        self.setWindowTitle(
            f"Character sheet — {channel_name or channel_id}")
        self.resize(560, 640)
        lay = QVBoxLayout(self)
        info = QLabel(
            "One-time setup for this channel. Upload <b>either</b> a full "
            "character sheet image (portrait + turnaround + expressions + "
            "outfit details, like a model sheet) <b>or</b> 4–5 full-body "
            "reference photos — then fill in the character's full details "
            "below. Every scene where the character appears will use this "
            "as the identity lock, so they look identical in all 30 "
            "minutes.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        b1 = QPushButton("Upload character sheet image…")
        b1.clicked.connect(self.pick_sheet)
        b2 = QPushButton("Upload 4–5 full-body images…")
        b2.clicked.connect(self.pick_refs)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)
        lay.addWidget(QLabel("Character details (full — used as prompt "
                             "reference):"))
        self.details = QTextEdit()
        self.details.setPlaceholderText(charmod.DETAILS_TEMPLATE)
        lay.addWidget(self.details, 1)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Character appears in how many scenes "
                              "per video:"))
        self.cameo = QSpinBox()
        self.cameo.setRange(0, 4)
        crow.addWidget(self.cameo)
        crow.addStretch(1)
        lay.addLayout(crow)
        btns = QDialogButtonBox(QDialogButtonBox.Save
                                | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self._pending_sheet = ""
        self._pending_refs = []
        self.refresh()

    def refresh(self):
        c = self.charmod.load_character(self.channel_id)
        parts = []
        if self._pending_sheet or c["sheet"]:
            parts.append("sheet image: set ✓")
        if self._pending_refs or c["refs"]:
            n = len(self._pending_refs or c["refs"])
            parts.append(f"reference images: {n} ✓")
        if not parts:
            parts.append("no character set yet")
        self.status.setText("Current: " + " · ".join(parts))
        if not self.details.toPlainText().strip():
            self.details.setPlainText(
                c["details"] or self.charmod.DETAILS_TEMPLATE)
        self.cameo.setValue(c["cameo"])

    def pick_sheet(self):
        path, _f = QFileDialog.getOpenFileName(
            self, "Character sheet image", "",
            "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self._pending_sheet = path
            self._pending_refs = []
            self.refresh()

    def pick_refs(self):
        paths, _f = QFileDialog.getOpenFileNames(
            self, "4–5 full-body reference images", "",
            "Images (*.png *.jpg *.jpeg *.webp)")
        if paths:
            self._pending_refs = paths[:5]
            self._pending_sheet = ""
            self.refresh()

    def save(self):
        if self._pending_sheet:
            saved = self.charmod.save_sheet(self.channel_id,
                                            self._pending_sheet)
            if not saved:
                QMessageBox.warning(self, "Character sheet",
                                    "Could not read that image.")
                return
        if self._pending_refs:
            n = self.charmod.save_refs(self.channel_id, self._pending_refs)
            if not n:
                QMessageBox.warning(self, "Character sheet",
                                    "Could not read those images.")
                return
        self.charmod.save_details(self.channel_id,
                                  self.details.toPlainText())
        self.charmod.save_meta(self.channel_id, self.cameo.value())
        self.accept()


class _VerifyWorker(QThread):
    """Verify EVERY key of one service in the background, one by one.

    Emits sig_key(last4, ok, note) per key and sig_done() at the end.
    A 429 (rate limit) counts as VERIFIED — the key is valid, just busy.
    """
    sig_key = Signal(str, bool, str)
    sig_done = Signal()

    def __init__(self, svc, keys, ping, state_dir):
        super().__init__()
        self.svc = svc
        self.keys = list(keys)
        self.ping = ping
        self.state_dir = state_dir

    def run(self):
        from ..keypool import KeyPool, KeyExhausted, _last4
        pool = KeyPool(self.svc, self.keys, state_dir=self.state_dir)
        for k in self.keys:
            last4 = _last4(k)
            try:
                note = self.ping(k)
                note = note if isinstance(note, str) else "ok"
                pool.mark_verified(last4, True)
                self.sig_key.emit(last4, True, note[:120])
            except KeyExhausted as e:
                # valid key, just rate-limited right now
                pool.mark_verified(last4, True)
                self.sig_key.emit(
                    last4, True, f"valid, rate-limited ({e})"[:120])
            except Exception as e:  # noqa: BLE001
                pool.mark_verified(last4, False)
                self.sig_key.emit(last4, False, str(e)[:120])
        self.sig_done.emit()


class SettingsDialog(QDialog):
    def __init__(self, parent, cfg, secrets):
        super().__init__(parent)
        self.cfg = cfg
        self.secrets = dict(secrets)
        # Keep a handle on the caller's dict: on Save we write the fresh
        # secrets back into it, otherwise the main window keeps serving the
        # stale (pre-save) copy and the key looks "gone" until restart.
        self._secrets_src = secrets
        self.setWindowTitle("Settings -- providers & channels")
        self.resize(800, 640)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        tabs = self.tabs
        tabs.addTab(self._voice_tab(), "Voiceover")
        tabs.addTab(self._script_tab(), "Script")
        tabs.addTab(self._clone_tab(), "Voice Clone")
        tabs.addTab(self._images_tab(), "Images")
        tabs.addTab(self._keys_tab(), "API Keys")
        tabs.addTab(self._channels_tab(), "Channels")
        tabs.addTab(self._pattern_tab(), "Pattern")
        tabs.addTab(self._gdrive_tab(), "Google Drive")
        tabs.addTab(self._competitors_tab(), "Competitors")
        lay.addWidget(tabs)
        row = QHBoxLayout()
        self.save_msg = QLabel("")
        self.save_msg.setObjectName("muted")
        row.addWidget(self.save_msg, 1)
        row.addStretch(1)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(close)
        lay.addLayout(row)

    # ------------------------------------------------ voiceover
    def _voice_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        # ── FREE SECTION ──────────────────────────────────────────────
        free_lbl = QLabel("\U0001f7e2  FREE Voice — No subscription needed")
        free_lbl.setStyleSheet(
            "color: #43c488; font-size: 13px; font-weight: bold; "
            "padding: 6px 10px; background: #0d2b1d; border-radius: 6px;")
        lay.addWidget(free_lbl)

        # Gemini TTS — primary free option (human quality)
        lay.addWidget(QLabel(
            "<b>Option 1: Gemini TTS</b>  —  Human-quality voice, 1,500 req/day free"))
        grow = QHBoxLayout()
        self.gemini_tts_key = QLineEdit()
        self.gemini_tts_key.setEchoMode(QLineEdit.Password)
        gtts_val = ""
        try:
            saved = self.secrets.get("gemini_tts_keys") or ""
            if isinstance(saved, list):
                saved = "\n".join(str(k).strip() for k in saved if str(k).strip())
            if not str(saved).strip():
                saved = self.secrets.get("gemini_api_key") or ""
            lines = str(saved).strip().splitlines()
            gtts_val = lines[0].strip() if lines else ""
        except Exception:  # noqa: BLE001
            pass
        self.gemini_tts_key.setText(gtts_val)
        self.gemini_tts_key.setPlaceholderText(
            "Paste Gemini API key (same key as Google AI / images)…")
        self.gemini_tts_dot = status_dot(bool(gtts_val))
        gtts_test = QPushButton("Test")
        gtts_test.clicked.connect(self.test_gemini_tts)
        self.gemini_tts_msg = QLabel("")
        self.gemini_tts_msg.setObjectName("muted")
        grow.addWidget(self.gemini_tts_dot)
        grow.addWidget(self.gemini_tts_key, 1)
        grow.addWidget(gtts_test)
        lay.addLayout(grow)
        lay.addWidget(self.gemini_tts_msg)

        # Show available voices
        from ..providers import geminitts as _gtts
        voices_text = "  |  ".join(
            f"{v['id']} ({v['gender']})" for v in _gtts.VOICES)
        vtts_lbl = QLabel(f"Voices: {voices_text}")
        vtts_lbl.setObjectName("muted")
        vtts_lbl.setWordWrap(True)
        lay.addWidget(vtts_lbl)

        # Edge TTS — robotic but free fallback
        lay.addWidget(QLabel(
            "<b>Option 2: Edge TTS</b>  —  Free fallback, no key needed (auto-used if Gemini fails)"))
        lay.addSpacing(10)

        # ── PAID SECTION ───────────────────────────────────────────────
        paid_lbl = QLabel("\U0001f4b0  PAID Voice — Premium quality (API key required)")
        paid_lbl.setStyleSheet(
            f"color: {GOLD}; font-size: 13px; font-weight: bold; "
            f"padding: 6px 10px; background: #2d1f0d; border-radius: 6px;")
        lay.addWidget(paid_lbl)

        lay.addWidget(QLabel(
            "<b>AI33 Pro</b>  —  ElevenLabs, MiniMax, Kokoro, Fish Audio, "
            "Voice Clone  (ai33.pro — one key covers all models)"))
        row = QHBoxLayout()
        self.ai33_key = QLineEdit()
        self.ai33_key.setEchoMode(QLineEdit.Password)
        self.ai33_key.setText(self.secrets.get("ai33pro_api_key", ""))
        self.ai33_key.setPlaceholderText("paste ai33.pro key…")
        self.ai33_dot = status_dot(bool(self.ai33_key.text().strip()))
        test = QPushButton("Test")
        test.clicked.connect(self.test_ai33)
        self.ai33_msg = QLabel("")
        self.ai33_msg.setObjectName("muted")
        row.addWidget(self.ai33_dot)
        row.addWidget(self.ai33_key, 1)
        row.addWidget(test)
        lay.addLayout(row)
        lay.addWidget(self.ai33_msg)
        browse = QPushButton("Browse AI33 voices (ElevenLabs / MiniMax / Kokoro / Fish Audio)…")
        browse.clicked.connect(self.browse_ai33)
        lay.addWidget(browse)

        lay.addStretch(1)
        info = QLabel(
            "Voice is set per channel in the Channels tab. "
            "Gemini TTS is the recommended default — human quality at $0.00 cost. "
            "Use the same Gemini key here as in Settings \u2192 API Keys.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        lay.addWidget(info)
        return w

    def test_gemini_tts(self):
        """Test Gemini TTS key by synthesizing a short phrase."""
        key = self.gemini_tts_key.text().strip()
        if not key:
            self.gemini_tts_msg.setText("Paste a Gemini API key first.")
            self.gemini_tts_dot.setStyleSheet("color: #5a6272; font-size: 18px;")
            return
        self.gemini_tts_msg.setText("Testing\u2026 (synthesizing short phrase)")
        from ..providers import geminitts
        import tempfile
        import os
        try:
            tmp = tempfile.mktemp(suffix=".wav")
            geminitts.synthesize(key, "Hello, this works.", voice="Charon",
                                 out_path=tmp, timeout=30)
            size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            if size > 1000:
                self.gemini_tts_msg.setText(
                    f"\u2713 Gemini TTS working \u2014 {size // 1024} KB audio returned.")
                self.gemini_tts_dot.setStyleSheet("color: #43c488; font-size: 18px;")
            else:
                self.gemini_tts_msg.setText("Key accepted but no audio returned.")
                self.gemini_tts_dot.setStyleSheet("color: #e0a23c; font-size: 18px;")
            try:
                os.remove(tmp)
            except Exception:  # noqa: BLE001
                pass
        except geminitts.GeminiTTSError as e:
            self.gemini_tts_msg.setText(str(e)[:200])
            self.gemini_tts_dot.setStyleSheet("color: #e5534b; font-size: 18px;")

    def test_ai33(self):
        key = self.ai33_key.text().strip()
        if not key:
            self.ai33_msg.setText("Paste a key first.")
            self.ai33_dot.setStyleSheet("color: #5a6272; font-size: 18px;")
            return
        try:
            bal = ai33voice.get_credits(key)
            self.ai33_msg.setText(f"OK — credit balance: {bal}")
            self.ai33_dot.setStyleSheet("color: #43c488; font-size: 18px;")
        except ai33voice.AI33Error as e:
            self.ai33_msg.setText(str(e))
            self.ai33_dot.setStyleSheet("color: #e5534b; font-size: 18px;")

    def browse_ai33(self):
        key = self.ai33_key.text().strip()
        if not key:
            QMessageBox.warning(self, "AI33 Pro", "Paste the API key first.")
            return
        dlg = VoicePickerDialog(self, self.cfg, {"ai33pro_api_key": key})
        if hasattr(dlg, "ai33_list"):
            dlg.load_ai33(key)
        dlg.exec()  # pick for preview only; locking happens in Channels tab

    # ------------------------------------------------ script
    def _script_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Script writer"))
        provs = self.cfg.get("providers") or {}
        self.script_provider = QComboBox()
        self.script_provider.addItems(["local", "gemini", "ai33pro"])
        cur = provs.get("script_provider", "local")
        self.script_provider.setCurrentText(
            cur if cur in ("local", "gemini", "ai33pro") else "local")
        lay.addWidget(QLabel("Provider:"))
        lay.addWidget(self.script_provider)
        form = QFormLayout()
        self.llm_base = QLineEdit(provs.get("ai33pro_llm_base_url", ""))
        self.llm_base.setPlaceholderText("https://api.ai33.pro/v1 (OpenAI-compatible)")
        self.llm_model = QLineEdit(provs.get("ai33pro_llm_model", ""))
        self.llm_model.setPlaceholderText("model id, e.g. gpt-4o-mini")
        form.addRow("AI33 base URL:", self.llm_base)
        form.addRow("AI33 model:", self.llm_model)
        self.gemini_llm_model = QLineEdit(
            provs.get("gemini_llm_model", "gemini-2.5-flash"))
        self.gemini_llm_model.setPlaceholderText("gemini-2.5-flash")
        form.addRow("Gemini script model:", self.gemini_llm_model)
        lay.addLayout(form)
        self.llm_msg = QLabel("")
        self.llm_msg.setObjectName("muted")
        self.llm_msg.setWordWrap(True)
        test = QPushButton("Test")
        test.clicked.connect(self.test_llm)
        lay.addWidget(test)
        lay.addWidget(self.llm_msg)
        # --- Claude review ---
        lay.addWidget(QLabel("<b>Claude review</b> (strict mistake check)"))
        self.claude_review = QCheckBox(
            "Claude proofreads every script and auto-applies fixes")
        self.claude_review.setChecked(bool(provs.get("claude_review")))
        lay.addWidget(self.claude_review)
        cform = QFormLayout()
        self.claude_base = QLineEdit(
            provs.get("claude_base_url", "https://api.anthropic.com"))
        self.claude_base.setPlaceholderText(
            "https://api.anthropic.com  (or your Antigravity endpoint)")
        self.claude_model = QLineEdit(provs.get("claude_model", ""))
        self.claude_model.setPlaceholderText(
            "model id from your endpoint, e.g. claude-sonnet-4-5")
        cform.addRow("Claude base URL:", self.claude_base)
        cform.addRow("Claude model:", self.claude_model)
        lay.addLayout(cform)
        lay.addStretch(1)
        info = QLabel("Gemini writes the script (competitor-level, your "
                      "channel pattern, never copied). Claude then checks it "
                      "for mistakes — grammar, repetition, contradictions — "
                      "and fixes them before voiceover. Claude keys live in "
                      "Settings → API Keys. Any LLM failure falls back to the "
                      "free local rules engine.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        lay.addWidget(info)
        return w

    def test_llm(self):
        from ..providers import scriptllm
        key = self.ai33_key.text().strip()
        try:
            scr = scriptllm.generate("The dog who waited 400 days", 1, key,
                                     self.llm_base.text().strip(),
                                     self.llm_model.text().strip(),
                                     timeout=120)
            self.llm_msg.setText(f"OK — {scr['words']} words returned.")
        except Exception as e:  # noqa: BLE001
            self.llm_msg.setText(str(e)[:300])

    # ------------------------------------------------ clone
    def _clone_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Clone a voice, lock it to a channel's avatar"))
        form = QFormLayout()
        self.clone_channel = QComboBox()
        for cid, ch in (self.cfg.get("channels") or {}).items():
            self.clone_channel.addItem(ch.get("name", cid), cid)
        self.clone_name = QLineEdit()
        self.clone_name.setPlaceholderText("e.g. Maria warm")
        srow = QHBoxLayout()
        self.clone_sample = QLineEdit()
        self.clone_sample.setPlaceholderText("1–3 min mp3/wav, clear speech, no music…")
        self.clone_sample.setReadOnly(True)
        pick = QPushButton("Choose file…")
        pick.clicked.connect(self.pick_sample)
        srow.addWidget(self.clone_sample, 1)
        srow.addWidget(pick)
        form.addRow("Channel:", self.clone_channel)
        form.addRow("Clone name:", self.clone_name)
        form.addRow("Sample:", srow)
        lay.addLayout(form)
        create = QPushButton("Create clone")
        create.setObjectName("primary")
        create.clicked.connect(self.create_clone)
        lay.addWidget(create)
        self.clone_msg = QLabel("")
        self.clone_msg.setObjectName("muted")
        self.clone_msg.setWordWrap(True)
        lay.addWidget(self.clone_msg)
        lay.addWidget(QLabel("Existing clones:"))
        self.clone_list = QListWidget()
        lay.addWidget(self.clone_list)
        drow = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_clones)
        delete = QPushButton("Delete selected")
        delete.setObjectName("danger")
        delete.clicked.connect(self.delete_clone)
        drow.addWidget(refresh)
        drow.addWidget(delete)
        drow.addStretch(1)
        lay.addLayout(drow)
        self.refresh_clones()
        return w

    def pick_sample(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Voice sample", "",
            "Audio (*.mp3 *.wav *.m4a *.ogg *.flac)")
        if p:
            # copy into the app's own folder so the sample stays even if
            # the original PC file is moved or deleted
            self.clone_sample.setText(config_mod.store_voice_sample(p))

    def _key_or_warn(self):
        key = self.ai33_key.text().strip() if hasattr(self, "ai33_key") \
            else self.secrets.get("ai33pro_api_key", "").strip()
        if not key:
            QMessageBox.warning(self, "AI33 Pro",
                                "Paste the AI33 Pro key on the Voiceover tab first. "
                                "The sample stays selected until then.")
        return key

    def create_clone(self):
        key = self._key_or_warn()
        if not key:
            return
        sample = self.clone_sample.text().strip()
        name = self.clone_name.text().strip()
        if not sample or not Path(sample).is_file():
            QMessageBox.warning(self, "Clone", "Choose a sample audio file first.")
            return
        try:
            vid = ai33voice.clone_voice(key, name or "My clone", sample)
        except ai33voice.AI33Error as e:
            self.clone_msg.setText(f"Clone failed: {e}")
            return
        # auto-lock to the channel's avatar
        cid = self.clone_channel.currentData()
        ch = (self.cfg.get("channels") or {}).get(cid) or {}
        ch["voice"] = {"provider": "ai33pro", "voice_id": vid,
                       "name": name or vid}
        save_config(self.cfg)
        self.clone_msg.setText(
            f"Cloned → {vid}. Locked to channel "
            f"'{ch.get('name', cid)}': every video for this channel now "
            f"uses this voice.")
        self.refresh_clones()

    def refresh_clones(self):
        self.clone_list.clear()
        key = self.secrets.get("ai33pro_api_key", "").strip()
        if not key and hasattr(self, "ai33_key"):
            key = self.ai33_key.text().strip()
        if not key:
            QListWidgetItem("(paste the AI33 Pro key to list clones)",
                            self.clone_list)
            return
        try:
            clones = ai33voice.list_clones(key)
        except ai33voice.AI33Error as e:
            QListWidgetItem(f"(could not list: {e})", self.clone_list)
            return
        if not clones:
            QListWidgetItem("(no cloned voices yet)", self.clone_list)
        for v in clones:
            QListWidgetItem(f"{v['name']}  <{v['id']}>", self.clone_list)

    def delete_clone(self):
        item = self.clone_list.currentItem()
        if not item or "<" not in item.text():
            return
        vid = item.text().split("<")[-1].rstrip(">")
        key = self.secrets.get("ai33pro_api_key", "").strip()
        if hasattr(self, "ai33_key") and self.ai33_key.text().strip():
            key = self.ai33_key.text().strip()
        try:
            ai33voice.delete_clone(key, vid)
        except ai33voice.AI33Error as e:
            QMessageBox.warning(self, "Delete clone", str(e))
            return
        # unlock channels that used it
        for ch in (self.cfg.get("channels") or {}).values():
            v = ch.get("voice") or {}
            if v.get("voice_id") == vid:
                ch["voice"] = {"provider": "edge",
                               "voice_id": "en-US-AvaNeural"}
        save_config(self.cfg)
        self.refresh_clones()

    # ------------------------------------------------ images
    def _images_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Own AI images instead of paid stock footage. "
                             "Order tried: your PC images (when enabled below) "
                             "→ Grok → Gemini → free local."))
        # gemini
        lay.addWidget(QLabel("Google AI (Gemini) — same model family as Google Flow"))
        grow = QHBoxLayout()
        self.gem_key = QLineEdit()
        self.gem_key.setEchoMode(QLineEdit.Password)
        self.gem_key.setText(self.secrets.get("gemini_api_key", ""))
        self.gem_model = QComboBox()
        self.gem_model.setEditable(True)
        self.gem_model.addItems(["gemini-2.5-flash-image",
                                 "gemini-2.0-flash-preview-image-generation"])
        self.gem_model.setCurrentText(
            (self.cfg.get("providers") or {}).get("gemini_model",
                                                  "gemini-2.5-flash-image"))
        gtest = QPushButton("Test")
        gtest.clicked.connect(self.test_gemini)
        grow.addWidget(QLabel("Key:"))
        grow.addWidget(self.gem_key, 1)
        grow.addWidget(QLabel("Model:"))
        grow.addWidget(self.gem_model)
        grow.addWidget(gtest)
        lay.addLayout(grow)
        self.gem_msg = QLabel("")
        self.gem_msg.setObjectName("muted")
        lay.addWidget(self.gem_msg)
        # grok
        lay.addWidget(QLabel("Grok (xAI)"))
        xrow = QHBoxLayout()
        self.grok_key = QLineEdit()
        self.grok_key.setEchoMode(QLineEdit.Password)
        self.grok_key.setText(self.secrets.get("xai_api_key", ""))
        self.grok_model = QComboBox()
        self.grok_model.setEditable(True)
        self.grok_model.addItems(["grok-imagine-image", "grok-2-image"])
        self.grok_model.setCurrentText(
            (self.cfg.get("providers") or {}).get("grok_model",
                                                  "grok-imagine-image"))
        xtest = QPushButton("Test")
        xtest.clicked.connect(self.test_grok)
        xrow.addWidget(QLabel("Key:"))
        xrow.addWidget(self.grok_key, 1)
        xrow.addWidget(QLabel("Model:"))
        xrow.addWidget(self.grok_model)
        xrow.addWidget(xtest)
        lay.addLayout(xrow)
        self.grok_msg = QLabel("")
        self.grok_msg.setObjectName("muted")
        lay.addWidget(self.grok_msg)
        # ---- your own images from PC ----
        lay.addWidget(QLabel("Your own images (upload from PC)"))
        pc_info_top = QLabel("Pick a folder of images on your PC — the video "
                             "will use THESE for its scenes (in alphabetical "
                             "order, cycled if scenes outnumber images) "
                             "instead of AI-generated ones.")
        pc_info_top.setObjectName("muted")
        pc_info_top.setWordWrap(True)
        lay.addWidget(pc_info_top)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Channel:"))
        self.pc_channel = QComboBox()
        for cid, ch in (self.cfg.get("channels") or {}).items():
            self.pc_channel.addItem(ch.get("name", cid), cid)
        self.pc_channel.currentIndexChanged.connect(self.load_pc_images)
        prow.addWidget(self.pc_channel, 1)
        lay.addLayout(prow)
        self.pc_enabled = QCheckBox(
            "Use my PC images instead of AI images for this channel")
        lay.addWidget(self.pc_enabled)
        frow = QHBoxLayout()
        self.pc_folder = QLineEdit()
        self.pc_folder.setReadOnly(True)
        self.pc_folder.setPlaceholderText("No folder chosen…")
        choose = QPushButton("Choose folder…")
        choose.clicked.connect(self.pick_pc_folder)
        frow.addWidget(self.pc_folder, 1)
        frow.addWidget(choose)
        lay.addLayout(frow)
        self.pc_count = QLabel("")
        self.pc_count.setObjectName("muted")
        lay.addWidget(self.pc_count)
        apply_pc = QPushButton("Apply to channel")
        apply_pc.setObjectName("primary")
        apply_pc.clicked.connect(self.apply_pc_images)
        lay.addWidget(apply_pc)
        self.load_pc_images()
        lay.addStretch(1)
        return w

    def test_gemini(self):
        import requests
        key = self.gem_key.text().strip()
        if not key:
            self.gem_msg.setText("Paste a key first.")
            return
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.gem_model.currentText()}:generateContent",
                headers={"x-goog-api-key": key},
                json={"contents": [{"parts": [{"text": "Reply with: OK"}]}]},
                timeout=30)
            if r.status_code == 200:
                self.gem_msg.setText("OK — Gemini key works.")
            else:
                self.gem_msg.setText(f"HTTP {r.status_code}: {r.text[:160]}")
        except Exception as e:  # noqa: BLE001
            self.gem_msg.setText(f"Failed: {e}"[:200])

    def test_grok(self):
        import requests
        key = self.grok_key.text().strip()
        if not key:
            self.grok_msg.setText("Paste a key first.")
            return
        try:
            r = requests.get("https://api.x.ai/v1/models",
                             headers={"Authorization": f"Bearer {key}"},
                             timeout=30)
            if r.status_code == 200:
                self.grok_msg.setText("OK — xAI key works.")
            else:
                self.grok_msg.setText(f"HTTP {r.status_code}: {r.text[:160]}")
        except Exception as e:  # noqa: BLE001
            self.grok_msg.setText(f"Failed: {e}"[:200])

    # ------------------------------------------------ pc images
    def _pc_channel_cfg(self):
        cid = self.pc_channel.currentData()
        ch = (self.cfg.get("channels") or {}).get(cid) or {}
        return cid, ch

    def load_pc_images(self):
        cid, ch = self._pc_channel_cfg()
        li = ch.get("local_images") or {}
        self.pc_enabled.setChecked(bool(li.get("enabled")))
        self.pc_folder.setText(li.get("folder") or "")
        self._update_pc_count()

    def pick_pc_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose image folder")
        if d:
            self.pc_folder.setText(d)
            self._update_pc_count()

    def _update_pc_count(self):
        folder = Path(self.pc_folder.text().strip())
        n = 0
        if folder.is_dir():
            exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
            try:
                n = sum(1 for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in exts)
            except Exception:  # noqa: BLE001
                n = 0
        self.pc_count.setText(
            f"{n} image(s) found — scenes will cycle through them in order."
            if n else "No images found in this folder yet.")

    def apply_pc_images(self):
        cid, ch = self._pc_channel_cfg()
        ch["local_images"] = {
            "enabled": self.pc_enabled.isChecked(),
            "folder": self.pc_folder.text().strip(),
        }
        save_config(self.cfg)
        self._update_pc_count()
        QMessageBox.information(
            self, "Images",
            f"Saved for '{ch.get('name', cid)}': "
            + ("your PC images will be used." if ch["local_images"]["enabled"]
               else "AI images will be used."))

    # ------------------------------------------------ API keys (rotation pools)
    KEY_SERVICES = (
        ("gemini-image", "Google Gemini — image generation (Pro accounts)",
         "gemini_api_keys", "gemini_api_key"),
        ("ai33-voice", "AI33 Pro — voiceover + script LLM (6M+ tokens)",
         "ai33pro_api_keys", "ai33pro_api_key"),
        ("grok-image", "Grok / xAI — image generation",
         "xai_api_keys", "xai_api_key"),
        ("claude-review", "Claude — script review (mistake check)",
         "claude_api_keys", "claude_api_key"),
    )
    # op tags recorded by KeyPool.run -> column labels in the status board
    KEY_OP_COLS = (("image", "Images"), ("voice", "Voice"),
                   ("script", "Script"), ("avatar", "Avatar"))
    KEY_DOT = {"ready": "#43c488", "cooling": "#e0a23c",
               "parked": "#e05252"}
    KEY_STATUS_TXT = {"ready": "● Live", "cooling": "◐ Cooling",
                      "parked": "● Parked"}

    def _keys_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(
            "Paste <b>as many API keys as you want — no limit</b>, one per "
            "line, then Save. <b>Verify all keys</b> checks every key live "
            "against its provider: green ✓ = working, red ✗ = dead. "
            "The engine uses the keys in order: the moment a key hits its "
            "rate limit or quota, the backend logs a message and the next "
            "key takes over automatically. The tired key rests for an hour "
            "(amber dot); dead keys are parked for 24 hours (red dot). "
            "Green dot = live.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.key_edits = {}
        self.key_stat_labels = {}
        self.key_tables = {}
        self._verify_workers = {}
        for svc, title, multi_name, _single in self.KEY_SERVICES:
            lay.addWidget(QLabel(f"<b>{title}</b>"))
            ed = QTextEdit()
            ed.setMaximumHeight(72)
            ed.setPlaceholderText("one key per line — unlimited…")
            saved = self.secrets.get(multi_name) or []
            if isinstance(saved, str):
                saved = [saved]
            ed.setPlainText("\n".join(str(k).strip() for k in saved
                                      if str(k).strip()))
            lay.addWidget(ed)
            self.key_edits[svc] = (ed, multi_name)
            # live status board: one row per key
            tbl = QTableWidget(0, 5 + len(self.KEY_OP_COLS) + 1)
            headers = (["", "Key", "Status", "Verified", "Used total"]
                       + [lbl for _op, lbl in self.KEY_OP_COLS]
                       + ["Last used"])
            tbl.setHorizontalHeaderLabels(headers)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            tbl.verticalHeader().setVisible(False)
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.setMaximumHeight(150)
            lay.addWidget(tbl)
            self.key_tables[svc] = tbl
            row = QHBoxLayout()
            save_b = QPushButton("Save keys")
            save_b.clicked.connect(
                lambda _=False, s=svc: self._keys_save(s))
            test_b = QPushButton("Test")
            test_b.clicked.connect(
                lambda _=False, s=svc: self._keys_test(s))
            ver_b = QPushButton("Verify all keys")
            ver_b.setToolTip("Check EVERY key live against its provider — "
                             "green ✓ working, red ✗ dead.")
            ver_b.clicked.connect(
                lambda _=False, s=svc: self._keys_verify(s))
            ref_b = QPushButton("Refresh")
            ref_b.clicked.connect(
                lambda _=False, s=svc: self._keys_refresh_stat(s))
            rep_b = QPushButton("Usage report")
            rep_b.clicked.connect(
                lambda _=False, s=svc: self._keys_report(s))
            stat = QLabel("")
            stat.setObjectName("muted")
            stat.setWordWrap(True)
            self.key_stat_labels[svc] = stat
            for b in (save_b, test_b, ver_b, ref_b, rep_b):
                row.addWidget(b)
            row.addWidget(stat, 1)
            lay.addLayout(row)
            self._keys_refresh_stat(svc)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(w)
        return scroll

    def _keys_list_from_edit(self, svc):
        ed, _multi = self.key_edits[svc]
        return [ln.strip() for ln in ed.toPlainText().splitlines()
                if ln.strip()]

    def _keys_pool(self, svc):
        from ..keypool import KeyPool
        return KeyPool(svc, self._keys_list_from_edit(svc),
                       state_dir=config_mod.CONFIG_PATH.parent)

    def _keys_save(self, svc):
        try:
            keys = self._keys_list_from_edit(svc)
            _ed, multi_name = self.key_edits[svc]
            single_name = next(sg for s, _t, _m, sg in self.KEY_SERVICES
                               if s == svc)
            self.secrets[multi_name] = keys
            if keys:
                self.secrets[single_name] = keys[0]
            save_secrets(self.secrets)
            # keep the single-key fields on the other tabs in sync
            if svc == "gemini-image" and hasattr(self, "gem_key") and keys:
                self.gem_key.setText(keys[0])
            if svc == "grok-image" and hasattr(self, "grok_key") and keys:
                self.grok_key.setText(keys[0])
            if svc == "ai33-voice" and hasattr(self, "ai33_key") and keys:
                self.ai33_key.setText(keys[0])
            self.key_stat_labels[svc].setText(
                f"Saved {len(keys)} key(s).")
            self._keys_refresh_stat(svc)
        except Exception as e:  # noqa: BLE001
            self.key_stat_labels[svc].setText(f"Could not save: {e}")

    def _keys_refresh_stat(self, svc):
        """Rebuild the live status board (green/amber/red dots per key)."""
        try:
            pool = self._keys_pool(svc)
            stats = pool.stats()
            tbl = self.key_tables[svc]
            tbl.setRowCount(0)
            for st in stats:
                r = tbl.rowCount()
                tbl.insertRow(r)
                dot = QTableWidgetItem("●")
                dot.setForeground(QColor(self.KEY_DOT[st["status"]]))
                dot.setTextAlignment(Qt.AlignCenter)
                fnt = dot.font()
                fnt.setPointSize(14)
                dot.setFont(fnt)
                tbl.setItem(r, 0, dot)
                key_it = QTableWidgetItem(st["last4"])
                key_it.setToolTip(
                    "Key ending " + st["last4"] +
                    (f"\nLast event: {st['last_event']}"
                     if st["last_event"] else ""))
                tbl.setItem(r, 1, key_it)
                status_txt = self.KEY_STATUS_TXT[st["status"]]
                if st["status"] == "cooling":
                    status_txt += f" ~{st['cool_min']}m"
                tbl.setItem(r, 2, QTableWidgetItem(status_txt))
                # Verified column: green ✓ / red ✗ / gray — (not checked)
                ver = st.get("verified")
                ver_it = QTableWidgetItem(
                    "✓" if ver is True else ("✗" if ver is False else "—"))
                ver_it.setForeground(QColor(
                    "#43c488" if ver is True
                    else ("#e05555" if ver is False else "#5a6272")))
                ver_it.setTextAlignment(Qt.AlignCenter)
                fnt2 = ver_it.font()
                fnt2.setPointSize(14)
                ver_it.setFont(fnt2)
                if st.get("verified_at"):
                    ver_it.setToolTip(
                        "Checked " + time.strftime(
                            "%d-%b %H:%M",
                            time.localtime(st["verified_at"])))
                tbl.setItem(r, 3, ver_it)
                tbl.setItem(r, 4, QTableWidgetItem(str(st["uses"])))
                for c, (op, _lbl) in enumerate(self.KEY_OP_COLS):
                    n = st["by_op"].get(op, 0)
                    it = QTableWidgetItem(str(n) if n else "—")
                    it.setTextAlignment(Qt.AlignCenter)
                    tbl.setItem(r, 5 + c, it)
                last = (time.strftime("%d-%b %H:%M",
                                      time.localtime(st["last_used"]))
                        if st["last_used"] else "—")
                tbl.setItem(r, 5 + len(self.KEY_OP_COLS),
                            QTableWidgetItem(last))
            tbl.resizeColumnsToContents()
            s = pool.summary()
            self.key_stat_labels[svc].setText(
                f"{s['total']} key(s) · {s['live']} live · "
                f"{s['cooling']} cooling · {s['parked']} parked · "
                f"{s['uses']} total uses · ✓ {s['verified_ok']} verified"
                + (f" · ✗ {s['verified_bad']} failed"
                   if s["verified_bad"] else ""))
        except Exception:  # noqa: BLE001
            pass

    def _keys_report(self, svc):
        """Per-key usage report dialog: what each key did, when it died."""
        from ..keypool import _now_str
        try:
            pool = self._keys_pool(svc)
            stats = pool.stats()
            title = next(t for s, t, _m, _sg in self.KEY_SERVICES if s == svc)
            lines = [f"USAGE REPORT — {title}",
                     f"Generated {_now_str()}", ""]
            if not stats:
                lines.append("No keys saved for this service yet.")
            for n, st in enumerate(stats, 1):
                lines.append(f"Key {n}: {st['last4']} — "
                             f"{self.KEY_STATUS_TXT[st['status']]}"
                             + (f" (~{st['cool_min']}m left)"
                                if st["status"] == "cooling" else ""))
                lines.append(f"  Total uses: {st['uses']}   "
                             f"Failures: {st['fails']}")
                ops = "  ".join(
                    f"{lbl}: {st['by_op'].get(op, 0)}"
                    for op, lbl in self.KEY_OP_COLS)
                lines.append(f"  What it did →  {ops}")
                if st["last_used"]:
                    lines.append("  Last used: " + time.strftime(
                        "%d-%b %Y %H:%M", time.localtime(st["last_used"])))
                if st["last_event"]:
                    lines.append(f"  Last event: {st['last_event']}")
                lines.append("")
            s = pool.summary()
            lines.append(f"TOTAL: {s['total']} keys · {s['live']} live · "
                         f"{s['cooling']} cooling · {s['parked']} parked · "
                         f"{s['uses']} uses")
            dlg = QDialog(self)
            dlg.setWindowTitle("API key usage report")
            dlg.resize(520, 420)
            lay = QVBoxLayout(dlg)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setPlainText("\n".join(lines))
            lay.addWidget(txt)
            btns = QDialogButtonBox(QDialogButtonBox.Close)
            copy_b = QPushButton("Copy")
            copy_b.clicked.connect(
                lambda: QApplication.clipboard().setText(txt.toPlainText()))
            btns.addButton(copy_b, QDialogButtonBox.ActionRole)
            btns.rejected.connect(dlg.reject)
            lay.addWidget(btns)
            dlg.exec()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Report", f"Could not build: {e}"[:200])

    def _ping_for(self, svc):
        """Return fn(key)->str that live-checks ONE key for a service.

        Shared by Test (one key via pool failover) and Verify all keys
        (every key, in the background). The cfg providers are snapshotted
        here so the worker thread never touches the UI-side config.
        """
        from ..keypool import KeyExhausted, KeyRejected
        import requests as _rq
        provs = dict(self.cfg.get("providers") or {})

        def _gemini_ping(k):
            r = _rq.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": k.strip()}, timeout=20)
            if r.status_code == 429:
                raise KeyExhausted("gemini rate limit")
            if r.status_code in (401, 403):
                raise KeyRejected(f"gemini HTTP {r.status_code}")
            r.raise_for_status()
            return True

        def _ai33_ping(k):
            from ..providers import ai33voice as _a
            bal = _a.get_credits(k)
            return f"credits: {bal}"

        def _grok_ping(k):
            k = k.strip()
            if not (k.startswith("xai-") or len(k) > 20):
                raise KeyRejected("does not look like an xAI key")
            return "format ok (no free ping endpoint)"

        def _claude_ping(k):
            from ..providers import claudereview as _c
            base = (provs.get("claude_base_url", "")
                    or _c.DEFAULT_BASE_URL).strip().rstrip("/")
            model = (provs.get("claude_model", "") or "").strip()
            if not model:
                raise KeyRejected("set the Claude model first "
                                  "(Script tab)")
            r = _rq.post(
                base + "/v1/messages",
                headers={"x-api-key": k.strip(),
                         "anthropic-version": _c.API_VERSION,
                         "Content-Type": "application/json"},
                json={"model": model, "max_tokens": 5,
                      "messages": [{"role": "user",
                                    "content": "Reply with: ok"}]},
                timeout=25)
            if r.status_code == 429:
                raise KeyExhausted("claude rate limit")
            if r.status_code in (401, 403):
                raise KeyRejected(f"claude HTTP {r.status_code}")
            r.raise_for_status()
            return "ok"

        return {"gemini-image": _gemini_ping,
                "ai33-voice": _ai33_ping,
                "grok-image": _grok_ping,
                "claude-review": _claude_ping}[svc]

    def _keys_test(self, svc):
        lbl = self.key_stat_labels[svc]
        try:
            from ..keypool import KeyPool
            keys = self._keys_list_from_edit(svc)
            pool = KeyPool(svc, keys,
                           state_dir=config_mod.CONFIG_PATH.parent)
            res = pool.run(self._ping_for(svc), op="test")
            lbl.setText(f"Test OK via pool ({res if isinstance(res, str) else 'ok'}).")
            self._keys_refresh_stat(svc)
        except Exception as e:  # noqa: BLE001
            lbl.setText(f"Test failed: {e}")

    def _keys_verify(self, svc):
        """Verify EVERY key live in the background: green ✓ / red ✗."""
        keys = self._keys_list_from_edit(svc)
        lbl = self.key_stat_labels[svc]
        if not keys:
            lbl.setText("Paste at least one key first.")
            return
        lbl.setText(f"Verifying {len(keys)} key(s)…")
        worker = _VerifyWorker(svc, keys, self._ping_for(svc),
                               config_mod.CONFIG_PATH.parent)
        worker.sig_key.connect(
            lambda _l4, _ok, _n, s=svc: self._keys_refresh_stat(s))
        worker.sig_done.connect(
            lambda s=svc: self._on_verify_done(s))
        self._verify_workers[svc] = worker
        worker.start()

    def _on_verify_done(self, svc):
        self._keys_refresh_stat(svc)
        try:
            pool = self._keys_pool(svc)
            s = pool.summary()
            self.key_stat_labels[svc].setText(
                f"✓ {s['verified_ok']} of {s['total']} keys verified"
                + (f" · ✗ {s['verified_bad']} failed"
                   if s["verified_bad"] else "")
                + " — green ✓ = working, red ✗ = dead.")
        except Exception:  # noqa: BLE001
            pass
        self._verify_workers.pop(svc, None)

    # ------------------------------------------------ channels
    def _channels_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("One-time voice, presenter & avatar mode per channel"))
        form = QFormLayout()
        self.ch_pick = QComboBox()
        for cid, ch in (self.cfg.get("channels") or {}).items():
            self.ch_pick.addItem(ch.get("name", cid), cid)
        self.ch_pick.currentIndexChanged.connect(self.load_channel)
        self.ch_voice_provider = QComboBox()
        self.ch_voice_provider.addItems(["gemini-tts", "edge", "ai33pro"])
        self.ch_voice_id = QLineEdit()
        browse = QPushButton("Browse voices...")
        browse.clicked.connect(self.browse_for_channel)
        vrow = QHBoxLayout()
        vrow.addWidget(self.ch_voice_id, 1)
        vrow.addWidget(browse)
        self.ch_presenter = QComboBox()
        for p in self.cfg.get("presenters") or []:
            self.ch_presenter.addItem(p.get("name", p.get("id")),
                                      p.get("id"))
        self.ch_minutes = QSpinBox()
        self.ch_minutes.setRange(1, 120)
        self.ch_subs = QCheckBox("Burn subtitles into the video (default OFF)")
        form.addRow("Channel:", self.ch_pick)
        form.addRow("Voice provider:", self.ch_voice_provider)
        form.addRow("Voice id:", vrow)
        form.addRow("Presenter:", self.ch_presenter)
        form.addRow("Default minutes:", self.ch_minutes)
        form.addRow("", self.ch_subs)
        lay.addLayout(form)

        # Avatar Clip Mode (3 options, backend-locked per channel)
        lay.addSpacing(10)
        clip_lbl = QLabel("Avatar Clip Mode -- locked per channel")
        clip_lbl.setStyleSheet(
            f"color: {GOLD}; font-size: 13px; font-weight: bold;")
        lay.addWidget(clip_lbl)
        self.ch_clip_mode = QComboBox()
        self.ch_clip_mode.addItem(
            "Option 1 -- Static PNG + Ken Burns zoom (free, no extra API)",
            "static")
        self.ch_clip_mode.addItem(
            "Option 2 -- Character Lock Card (visual ID sheet overlay on video)",
            "card")
        self.ch_clip_mode.addItem(
            "Option 3 -- AI Video Clips (5-15s natural talking avatar, Gemini Veo API)",
            "video")
        lay.addWidget(self.ch_clip_mode)
        self._clip_descs = [
            "Option 1: Static presenter image with slow zoom-in. Current default, "
            "completely free. Works with any PNG avatar image. No extra API needed.",
            "Option 2: Character sheet is rendered as a visual ID card (name, "
            "details, style) overlaid on the intro clip. Works without extra API. "
            "Upload character sheet in 'Character sheet...' button below.",
            "Option 3: Gemini Veo or compatible AI generates 5-15s natural talking "
            "clips. Script length determines duration. Add Gemini key in API Keys tab. "
            "Most realistic -- same face, natural talking motion, scene-based visuals.",
        ]
        self.ch_clip_desc = QLabel(self._clip_descs[0])
        self.ch_clip_desc.setObjectName("muted")
        self.ch_clip_desc.setWordWrap(True)
        lay.addWidget(self.ch_clip_desc)
        self.ch_clip_mode.currentIndexChanged.connect(
            lambda i: self.ch_clip_desc.setText(self._clip_descs[i]))
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Clip duration (seconds, for options 2 & 3):"))
        self.ch_clip_secs = QSpinBox()
        self.ch_clip_secs.setRange(5, 15)
        self.ch_clip_secs.setValue(8)
        self.ch_clip_secs.setToolTip(
            "Duration of each avatar clip appearance (5-15 seconds).")
        srow.addWidget(self.ch_clip_secs)
        srow.addStretch(1)
        lay.addLayout(srow)

        apply = QPushButton("Apply to channel")
        apply.setObjectName("primary")
        apply.clicked.connect(self.apply_channel)
        lay.addWidget(apply)
        char_btn = QPushButton("Character sheet... (one-time per channel)")
        char_btn.setToolTip(
            "Upload a character sheet image or 4-5 full-body photos + "
            "full character details. Scenes with the character use it as "
            "the identity lock so they look identical every time.")
        char_btn.clicked.connect(self.open_character_sheet)
        lay.addWidget(char_btn)
        self.ch_msg = QLabel("")
        self.ch_msg.setObjectName("muted")
        lay.addWidget(self.ch_msg)
        lay.addStretch(1)
        self.load_channel()
        return w

    def load_channel(self):
        cid = self.ch_pick.currentData()
        ch = (self.cfg.get("channels") or {}).get(cid) or {}
        v = ch.get("voice") or {}
        prov = v.get("provider", "gemini-tts")
        pidx = self.ch_voice_provider.findText(prov)
        if pidx >= 0:
            self.ch_voice_provider.setCurrentIndex(pidx)
        self.ch_voice_id.setText(v.get("voice_id", ""))
        idx = self.ch_presenter.findData(ch.get("presenter"))
        if idx >= 0:
            self.ch_presenter.setCurrentIndex(idx)
        self.ch_minutes.setValue(int(ch.get("default_minutes", 5)))
        self.ch_subs.setChecked(bool(ch.get("subtitles")))
        # sync avatar clip mode
        try:
            clip_mode = ch.get("avatar_clip_mode", "static")
            ci = self.ch_clip_mode.findData(clip_mode)
            if ci >= 0:
                self.ch_clip_mode.setCurrentIndex(ci)
            secs = int(ch.get("avatar_clip_secs") or
                       (self.cfg.get("providers") or {}).get(
                           "presenter_seconds", 8))
            self.ch_clip_secs.setValue(max(5, min(15, secs)))
        except Exception:  # noqa: BLE001
            pass

    def browse_for_channel(self):
        dlg = VoicePickerDialog(self, self.cfg, self.secrets)
        if dlg.exec() == QDialog.Accepted and dlg.result:
            provider, vid, _name = dlg.result
            if provider == "pc-sample":
                # hand the uploaded sample to the Voice Clone tab so the
                # user can create the clone from it in one step
                self.clone_sample.setText(vid)
                self.clone_msg.setText(
                    "Sample uploaded and stored in the app's folder. Give "
                    "it a name above and click 'Create clone' — the new "
                    "voice locks to the channel automatically.")
                self.tabs.setCurrentIndex(2)  # Voice Clone tab
                return
            self.ch_voice_provider.setCurrentText(provider)
            self.ch_voice_id.setText(vid)

    def apply_channel(self):
        cid = self.ch_pick.currentData()
        ch = (self.cfg.get("channels") or {}).get(cid) or {}
        ch["voice"] = {"provider": self.ch_voice_provider.currentText(),
                       "voice_id": self.ch_voice_id.text().strip()}
        ch["presenter"] = self.ch_presenter.currentData()
        ch["default_minutes"] = self.ch_minutes.value()
        ch["subtitles"] = self.ch_subs.isChecked()
        # save avatar clip mode
        try:
            ch["avatar_clip_mode"] = self.ch_clip_mode.currentData() or "static"
            ch["avatar_clip_secs"] = self.ch_clip_secs.value()
        except Exception:  # noqa: BLE001
            pass
        save_config(self.cfg)
        clip_mode = ch.get("avatar_clip_mode", "static")
        mode_name = {"static": "Static PNG", "card": "Character Card",
                     "video": "AI Video Clips"}.get(clip_mode, clip_mode)
        self.ch_msg.setText(
            f"Saved -- '{ch.get('name', cid)}' locked: "
            f"voice={ch['voice']['provider']}, "
            f"avatar={mode_name}, {ch.get('avatar_clip_secs', 8)}s clips.")

    def open_character_sheet(self):
        cid = self.ch_pick.currentData()
        ch = (self.cfg.get("channels") or {}).get(cid) or {}
        dlg = CharacterSheetDialog(self, cid, ch.get("name", cid))
        if dlg.exec() == QDialog.Accepted:
            from .. import character as charmod
            c = charmod.load_character(cid)
            bits = []
            if c["sheet"]:
                bits.append("sheet ✓")
            if c["refs"]:
                bits.append(f"{len(c['refs'])} refs ✓")
            self.ch_msg.setText(
                "Character saved (" + ", ".join(bits) + ") — "
                f"appears in {c['cameo']} scene(s) per video.")

    # ------------------------------------------------ pattern
    @staticmethod
    def _split_blocks(text):
        return [b.strip() for b in (text or "").split("\n\n") if b.strip()]

    @staticmethod
    def _join_blocks(items):
        return "\n\n".join(items or [])

    def _pattern_tab(self):
        outer = QWidget()
        ol = QVBoxLayout(outer)
        ol.addWidget(QLabel(
            "Each channel follows its own content formula — hook style, story "
            "beats, avatar re-entry lines, CTA. Study a competitor once, save "
            "their pattern here, and every video on this channel follows it."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        lay = QVBoxLayout(w)

        form = QFormLayout()
        self.pt_pick = QComboBox()
        for cid, ch in (self.cfg.get("channels") or {}).items():
            self.pt_pick.addItem(ch.get("name", cid), cid)
        self.pt_pick.currentIndexChanged.connect(self.pt_load)
        form.addRow("Channel:", self.pt_pick)
        self.pt_name = QLineEdit()
        form.addRow("Pattern name:", self.pt_name)
        lay.addLayout(form)

        # reference video
        ref_row = QHBoxLayout()
        self.pt_ref_url = QLineEdit()
        self.pt_ref_url.setPlaceholderText(
            "Paste a competitor video YouTube URL to decode their pattern...")
        ref_btn = QPushButton("Fetch title")
        ref_btn.clicked.connect(self.pt_fetch_ref)
        ai_decode_btn = QPushButton("AI Auto-Decode")
        ai_decode_btn.setObjectName("primary")
        ai_decode_btn.setToolTip(
            "Uses Gemini AI to decode the competitor video's hook style, "
            "beats, CTA, and image style — and auto-fills all pattern fields.")
        ai_decode_btn.clicked.connect(self.pt_ai_decode)
        ref_row.addWidget(self.pt_ref_url, 1)
        ref_row.addWidget(ref_btn)
        ref_row.addWidget(ai_decode_btn)
        lay.addLayout(ref_row)
        self.pt_ref_info = QLabel("")
        self.pt_ref_info.setObjectName("muted")
        self.pt_ref_info.setWordWrap(True)
        lay.addWidget(self.pt_ref_info)


        lay.addWidget(QLabel("Hook templates (blank line between each, "
                             "use {topic} for the title's topic):"))
        self.pt_hooks = QTextEdit()
        self.pt_hooks.setMaximumHeight(110)
        lay.addWidget(self.pt_hooks)

        lay.addWidget(QLabel("Story beats (the script's sections, in order):"))
        beats_row = QHBoxLayout()
        self.pt_beats = QListWidget()
        self.pt_beats.setMaximumWidth(170)
        self.pt_beats.currentRowChanged.connect(self.pt_beat_selected)
        beats_row.addWidget(self.pt_beats)
        bright = QVBoxLayout()
        bform = QFormLayout()
        self.pt_beat_name = QLineEdit()
        self.pt_beat_lines = QTextEdit()
        self.pt_beat_lines.setMaximumHeight(90)
        self.pt_beat_lines.setPlaceholderText(
            "Template sentences, one per line. Use {topic} for the title's topic.")
        self.pt_beat_scene = QLineEdit()
        self.pt_beat_scene.setPlaceholderText("Image scene description…")
        bform.addRow("Name:", self.pt_beat_name)
        bform.addRow("Lines:", self.pt_beat_lines)
        bform.addRow("Scene:", self.pt_beat_scene)
        bright.addLayout(bform)
        brow = QHBoxLayout()
        add_b = QPushButton("Add beat")
        add_b.clicked.connect(self.pt_beat_add)
        upd_b = QPushButton("Update beat")
        upd_b.clicked.connect(self.pt_beat_update)
        del_b = QPushButton("Remove beat")
        del_b.clicked.connect(self.pt_beat_remove)
        brow.addWidget(add_b)
        brow.addWidget(upd_b)
        brow.addWidget(del_b)
        bright.addLayout(brow)
        bright.addStretch(1)
        beats_row.addLayout(bright, 1)
        lay.addLayout(beats_row)

        lay.addWidget(QLabel(
            "Avatar re-entry lines (one per line — the avatar opens with one "
            "of these each time it re-appears mid-video):"))
        self.pt_trans = QTextEdit()
        self.pt_trans.setMaximumHeight(80)
        lay.addWidget(self.pt_trans)

        lay.addWidget(QLabel("CTA templates (blank line between each):"))
        self.pt_ctas = QTextEdit()
        self.pt_ctas.setMaximumHeight(80)
        lay.addWidget(self.pt_ctas)

        iform = QFormLayout()
        self.pt_imgstyle = QLineEdit()
        iform.addRow("Image style:", self.pt_imgstyle)
        lay.addLayout(iform)
        lay.addWidget(QLabel("Style notes (vocabulary / tone for the writer):"))
        self.pt_notes = QTextEdit()
        self.pt_notes.setMaximumHeight(60)
        lay.addWidget(self.pt_notes)

        srow = QHBoxLayout()
        save_b = QPushButton("Save pattern to channel")
        save_b.setObjectName("primary")
        save_b.clicked.connect(self.pt_save)
        reset_b = QPushButton("Reset to default pattern")
        reset_b.clicked.connect(self.pt_reset)
        srow.addWidget(save_b)
        srow.addWidget(reset_b)
        srow.addStretch(1)
        lay.addLayout(srow)
        self.pt_msg = QLabel("")
        self.pt_msg.setObjectName("muted")
        self.pt_msg.setWordWrap(True)
        lay.addWidget(self.pt_msg)
        lay.addStretch(1)

        scroll.setWidget(w)
        ol.addWidget(scroll)
        self._pat = None
        self.pt_load()
        return outer

    def _pt_channel(self):
        cid = self.pt_pick.currentData()
        return (self.cfg.get("channels") or {}).get(cid) or {}

    def pt_load(self):
        try:
            cid = self.pt_pick.currentData()
            self._pat = get_pattern(self._pt_channel(), cid)
            self._pat_to_fields()
            ch = self._pt_channel() or {}
            if not (isinstance(ch.get("pattern"), dict)
                    and ch.get("pattern").get("beats")):
                bn = builtin_pattern_name(cid)
                if bn:
                    self.pt_msg.setText(
                        f"Showing built-in '{bn}' pattern — edit and Save to "
                        f"make it this channel's own.")
                    return
            self.pt_msg.setText("")
        except Exception:  # noqa: BLE001
            pass

    def _pat_to_fields(self):
        p = self._pat or default_pattern()
        self.pt_name.setText(p.get("name", ""))
        self.pt_ref_url.setText(p.get("reference_url", ""))
        rt = p.get("reference_title", "")
        self.pt_ref_info.setText(f"Reference: {rt}" if rt else "")
        self.pt_hooks.setPlainText(self._join_blocks(p.get("hook_templates")))
        self.pt_beats.clear()
        for b in p.get("beats") or []:
            self.pt_beats.addItem(b.get("name", "beat"))
        if self.pt_beats.count():
            self.pt_beats.setCurrentRow(0)
        else:
            self.pt_beat_selected(-1)
        self.pt_trans.setPlainText("\n".join(p.get("rejoin_transitions") or []))
        self.pt_ctas.setPlainText(self._join_blocks(p.get("cta_templates")))
        self.pt_imgstyle.setText(p.get("image_style", ""))
        self.pt_notes.setPlainText(p.get("style_notes", ""))

    def pt_beat_selected(self, row):
        try:
            beats = (self._pat or {}).get("beats") or []
            if 0 <= row < len(beats):
                b = beats[row]
                self.pt_beat_name.setText(b.get("name", ""))
                self.pt_beat_lines.setPlainText("\n".join(b.get("lines") or []))
                self.pt_beat_scene.setText(b.get("scene", ""))
            else:
                self.pt_beat_name.clear()
                self.pt_beat_lines.clear()
                self.pt_beat_scene.clear()
        except Exception:  # noqa: BLE001
            pass

    def _pt_gather_beat(self):
        lines = [ln.strip() for ln in
                 self.pt_beat_lines.toPlainText().splitlines() if ln.strip()]
        return {"name": self.pt_beat_name.text().strip() or "beat",
                "lines": lines or ["{topic}."],
                "scene": self.pt_beat_scene.text().strip()}

    def pt_beat_add(self):
        try:
            b = self._pt_gather_beat()
            beats = (self._pat.setdefault("beats", []))
            beats.append(b)
            self.pt_beats.addItem(b["name"])
            self.pt_beats.setCurrentRow(self.pt_beats.count() - 1)
        except Exception:  # noqa: BLE001
            pass

    def pt_beat_update(self):
        try:
            row = self.pt_beats.currentRow()
            beats = (self._pat or {}).get("beats") or []
            if 0 <= row < len(beats):
                b = self._pt_gather_beat()
                beats[row] = b
                self.pt_beats.item(row).setText(b["name"])
        except Exception:  # noqa: BLE001
            pass

    def pt_beat_remove(self):
        try:
            row = self.pt_beats.currentRow()
            beats = (self._pat or {}).get("beats") or []
            if 0 <= row < len(beats):
                beats.pop(row)
                self.pt_beats.takeItem(row)
                self.pt_beat_selected(self.pt_beats.currentRow())
        except Exception:  # noqa: BLE001
            pass

    def pt_fetch_ref(self):
        url = self.pt_ref_url.text().strip()
        if not url:
            return
        info = fetch_video_info(url)
        title = info.get("title", "")
        author = info.get("author", "")
        if title:
            label = f"Reference: {title}" + (f" -- {author}" if author else "")
            self.pt_ref_info.setText(label)
            if isinstance(self._pat, dict):
                self._pat["reference_title"] = title
            self.pt_msg.setText("Title fetched -- remember to click "
                                "'Save pattern to channel'.")
        else:
            self.pt_ref_info.setText("Could not fetch -- check the URL / "
                                     "your connection.")
            self.pt_msg.setText("")

    def pt_ai_decode(self):
        """Run Gemini AI competitor analysis and auto-fill all pattern fields."""
        url = self.pt_ref_url.text().strip()
        if not url:
            self.pt_ref_info.setText(
                "Paste a YouTube URL first, then click AI Auto-Decode.")
            return
        if "youtube" not in url and "youtu.be" not in url:
            self.pt_ref_info.setText(
                "Only YouTube URLs are supported for AI decode.")
            return

        # Get Gemini API key
        api_key = (self.secrets.get("gemini_api_key") or
                   self.secrets.get("gemini_tts_keys") or "")
        if isinstance(api_key, list):
            api_key = api_key[0] if api_key else ""
        if not api_key:
            self.pt_ref_info.setText(
                "Gemini API key needed. Set it in Voiceover or API Keys tab.")
            return

        self.pt_ref_info.setText("Decoding competitor pattern with AI...")
        self.pt_msg.setText("AI analysis running -- this takes ~15-30 seconds...")

        import threading
        from PySide6.QtCore import QTimer
        from ..patterns import fetch_competitor_pattern

        result_box = [None, ""]  # [pat, logs]

        def _run():
            logs = []
            pat = fetch_competitor_pattern(
                url, api_key,
                model=self.cfg.get("providers", {}).get(
                    "gemini_model", "gemini-2.0-flash"),
                logger=logs.append)
            result_box[0] = pat
            result_box[1] = "\n".join(logs)
            # Schedule UI update on the main thread
            QTimer.singleShot(0, lambda: self._pt_ai_apply(
                result_box[0], result_box[1]))

        threading.Thread(target=_run, daemon=True).start()

    def _pt_ai_apply(self, pat, logs):
        """Called on main thread after AI decode finishes."""
        try:
            err = pat.get("error", "") if isinstance(pat, dict) else ""
            if not pat or err:
                self.pt_ref_info.setText(
                    f"AI decode failed: {err or 'No result returned.'}")
                self.pt_msg.setText(logs[:300] if logs else "")
                return

            # Merge decoded pattern and refresh all fields
            if not isinstance(self._pat, dict):
                self._pat = {}
            self._pat.update(pat)
            self._pat_to_fields()

            title = pat.get("reference_title", "")
            self.pt_ref_info.setText(
                f"AI decoded: \"{title}\"  |  "
                f"{len(pat.get('beats', []))} beats  |  "
                f"{len(pat.get('hook_templates', []))} hooks  |  "
                f"style: {pat.get('image_style', '')[:50]}")
            self.pt_msg.setText(
                "All fields auto-filled! Review, edit if needed, "
                "then click 'Save pattern to channel'.")
        except Exception as e:  # noqa: BLE001
            self.pt_ref_info.setText(f"Error applying result: {e}")

    def pt_reset(self):
        self._pat = default_pattern()
        self._pat_to_fields()
        self.pt_msg.setText("Reset to the built-in pattern — click "
                            "'Save pattern to channel' to keep it.")

    def pt_save(self):
        try:
            p = self._pat if isinstance(self._pat, dict) else {}
            p["name"] = self.pt_name.text().strip() or "Custom Pattern"
            p["reference_url"] = self.pt_ref_url.text().strip()
            p["hook_templates"] = self._split_blocks(
                self.pt_hooks.toPlainText()) or p.get("hook_templates")
            p["rejoin_transitions"] = [
                ln.strip() for ln in self.pt_trans.toPlainText().splitlines()
                if ln.strip()] or p.get("rejoin_transitions")
            p["cta_templates"] = self._split_blocks(
                self.pt_ctas.toPlainText()) or p.get("cta_templates")
            p["image_style"] = self.pt_imgstyle.text().strip()
            p["style_notes"] = self.pt_notes.toPlainText().strip()
            # beats already live in self._pat via the beat editor
            if not p.get("beats"):
                p["beats"] = default_pattern()["beats"]
            p = normalize_pattern(p)
            ch = self._pt_channel()
            ch["pattern"] = p
            save_config(self.cfg)
            self._pat = p
            cname = ch.get("name") or self.pt_pick.currentData()
            self.pt_msg.setText(
                f"Saved -- '{cname}' videos now follow the '{p['name']}' pattern.")
        except Exception as e:  # noqa: BLE001
            self.pt_msg.setText(f"Could not save: {e}")

    # ------------------------------------------------ google drive
    def _gdrive_tab(self):
        from .. import config as config_mod
        from .. import gdrive as _gd
        _gd.init(config_mod.CONFIG_PATH.parent)

        w = QWidget()
        lay = QVBoxLayout(w)

        hdr = QLabel("Google Drive -- Auto-upload finished videos")
        hdr.setStyleSheet(
            "color: #43c488; font-size: 14px; font-weight: bold; "
            "padding: 6px 10px; background: #0d2b1d; border-radius: 6px;")
        lay.addWidget(hdr)

        info = QLabel(
            "Connect your Google account once. After that every finished video "
            "is uploaded automatically to:\n"
            "  Your Drive / Channel Name / YYYY-MM-DD / Video Title /\n"
            "    video.mp4   title.txt   description.txt   tags.txt   "
            "thumbnail-prompt.txt   metadata.docx\n\n"
            "To connect you need a credentials file (client_secret_*.json) "
            "from Google Cloud Console (APIs & Services -> Credentials -> "
            "OAuth 2.0 Client IDs -> Download JSON).")
        info.setWordWrap(True)
        info.setObjectName("muted")
        lay.addWidget(info)

        # credentials file picker
        creds_row = QHBoxLayout()
        creds_row.addWidget(QLabel("Credentials file:"))
        self.gdrive_creds_path = QLineEdit()
        self.gdrive_creds_path.setPlaceholderText(
            "client_secret_*.json (leave blank if already in config folder)")
        self.gdrive_creds_path.setReadOnly(True)
        pick_creds = QPushButton("Choose file...")
        pick_creds.clicked.connect(self._gdrive_pick_creds)
        creds_row.addWidget(self.gdrive_creds_path, 1)
        creds_row.addWidget(pick_creds)
        lay.addLayout(creds_row)

        btn_row = QHBoxLayout()
        self.gdrive_connect_btn = QPushButton("Connect Google Drive account")
        self.gdrive_connect_btn.setObjectName("primary")
        self.gdrive_connect_btn.clicked.connect(self._gdrive_connect)
        refresh_btn = QPushButton("Refresh status")
        refresh_btn.clicked.connect(self._gdrive_refresh)
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.setObjectName("danger")
        disconnect_btn.clicked.connect(self._gdrive_disconnect)
        btn_row.addWidget(self.gdrive_connect_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(disconnect_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.gdrive_status = QLabel("")
        self.gdrive_status.setObjectName("muted")
        self.gdrive_status.setWordWrap(True)
        lay.addWidget(self.gdrive_status)

        self.gdrive_auto = QCheckBox(
            "Auto-upload each finished video to Google Drive")
        lay.addWidget(self.gdrive_auto)
        # load saved preference
        try:
            self.gdrive_auto.setChecked(
                bool(self.cfg.get("providers", {}).get("gdrive_auto_upload")))
        except Exception:  # noqa: BLE001
            pass
        self.gdrive_auto.toggled.connect(self._gdrive_save_pref)

        lay.addStretch(1)
        tip = QLabel(
            "python-docx is needed for the Word metadata file: "
            "pip install google-auth google-auth-oauthlib "
            "google-api-python-client python-docx")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self._gdrive_refresh()
        return w

    def _gdrive_pick_creds(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose credentials file", "",
            "JSON (*.json)")
        if path:
            self.gdrive_creds_path.setText(path)

    def _gdrive_connect(self):
        from .. import config as config_mod
        from .. import gdrive as _gd
        _gd.init(config_mod.CONFIG_PATH.parent)
        creds_path = self.gdrive_creds_path.text().strip() or None
        self.gdrive_status.setText("Connecting... (a browser window will open)")
        try:
            email = _gd.connect_drive(creds_path)
            self.gdrive_status.setText(
                f"Connected as: {email}   Drive is ready.")
        except _gd.DriveError as e:
            self.gdrive_status.setText(f"Connection failed: {e}")
        except Exception as e:  # noqa: BLE001
            self.gdrive_status.setText(f"Unexpected error: {e}")

    def _gdrive_refresh(self):
        try:
            from .. import config as config_mod
            from .. import gdrive as _gd
            _gd.init(config_mod.CONFIG_PATH.parent)
            if not _gd.is_configured():
                self.gdrive_status.setText(
                    "Not connected. Click 'Connect Google Drive account'.")
                return
            info = _gd.account_info()
            if info:
                self.gdrive_status.setText(
                    f"Connected: {info.get('email', '')}  |  "
                    f"Storage: {info.get('used_gb', 0)} GB / "
                    f"{info.get('total_gb', 0)} GB "
                    f"({info.get('percent', 0)}% used)")
            else:
                self.gdrive_status.setText(
                    "Token found but could not fetch account info. "
                    "Try reconnecting.")
        except Exception as e:  # noqa: BLE001
            self.gdrive_status.setText(f"Status check failed: {e}")

    def _gdrive_disconnect(self):
        try:
            from .. import config as config_mod
            from .. import gdrive as _gd
            _gd.init(config_mod.CONFIG_PATH.parent)
            tp = _gd._token_path()
            if tp and tp.is_file():
                tp.unlink()
            self.gdrive_status.setText("Disconnected.")
        except Exception as e:  # noqa: BLE001
            self.gdrive_status.setText(f"Error: {e}")

    def _gdrive_save_pref(self, checked):
        provs = self.cfg.setdefault("providers", {})
        provs["gdrive_auto_upload"] = checked
        try:
            from .. import config as config_mod
            config_mod.save_config(self.cfg)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------ competitors
    def _competitors_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        hdr = QLabel("Competitor Intelligence  --  Auto-decode channel patterns")
        hdr.setStyleSheet(
            "color: #e0a23c; font-size: 14px; font-weight: bold;"
            " padding: 6px 10px; background: #2d1f0d; border-radius: 6px;")
        lay.addWidget(hdr)

        info = QLabel(
            "93 competitor channels loaded.  Click 'Start Full Scrape' to fetch "
            "top 7 outlier videos from each channel and decode their patterns "
            "with Gemini AI.  Scrape is resumable -- already-done channels are "
            "skipped automatically.  Each decoded pattern can be applied to "
            "any of your channels as their content formula.")
        info.setWordWrap(True)
        info.setObjectName("muted")
        lay.addWidget(info)

        # Controls row
        ctrl = QHBoxLayout()
        self.comp_scrape_btn = QPushButton("Start Full Scrape (93 channels)")
        self.comp_scrape_btn.setObjectName("primary")
        self.comp_scrape_btn.clicked.connect(self._comp_scrape_start)
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self._comp_scrape_stop)
        refresh_btn = QPushButton("Refresh table")
        refresh_btn.clicked.connect(self._comp_refresh_table)
        ctrl.addWidget(self.comp_scrape_btn)
        ctrl.addWidget(stop_btn)
        ctrl.addWidget(refresh_btn)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        # Progress bar
        self.comp_progress = QProgressBar()
        self.comp_progress.setRange(0, 100)
        self.comp_progress.setValue(0)
        self.comp_progress.setFormat("%p%  %v / 100")
        lay.addWidget(self.comp_progress)

        self.comp_status = QLabel("Ready -- load existing results or start scrape.")
        self.comp_status.setObjectName("muted")
        self.comp_status.setWordWrap(True)
        lay.addWidget(self.comp_status)

        # Results table
        self.comp_table = QTableWidget(0, 5)
        self.comp_table.setHorizontalHeaderLabels(
            ["Channel", "Niche", "Videos decoded", "Status", ""])
        self.comp_table.horizontalHeader().setStretchLastSection(True)
        self.comp_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.comp_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.comp_table.setMinimumHeight(300)
        lay.addWidget(self.comp_table)

        # Action row for selected pattern
        act = QHBoxLayout()
        self.comp_use_btn = QPushButton("Apply pattern to Pattern tab")
        self.comp_use_btn.setObjectName("primary")
        self.comp_use_btn.clicked.connect(self._comp_use_pattern)
        self.comp_link_btn = QPushButton("Link to active channel")
        self.comp_link_btn.clicked.connect(self._comp_link_to_channel)
        act.addWidget(self.comp_use_btn)
        act.addWidget(self.comp_link_btn)
        act.addStretch(1)
        lay.addLayout(act)

        # Scrape thread placeholder
        self._comp_thread = None
        self._comp_stop_flag = [False]

        # Load existing results
        self._comp_refresh_table()
        return w

    def _comp_refresh_table(self):
        try:
            from .. import competitor as comp_mod
            patterns = comp_mod.get_all_master_patterns()
            self.comp_table.setRowCount(0)
            for row_data in patterns:
                r = self.comp_table.rowCount()
                self.comp_table.insertRow(r)
                self.comp_table.setItem(r, 0, QTableWidgetItem(
                    row_data.get("handle", "")))
                self.comp_table.setItem(r, 1, QTableWidgetItem(
                    row_data.get("niche", "?")))
                self.comp_table.setItem(r, 2, QTableWidgetItem(
                    str(row_data.get("decoded", 0))))
                status = row_data.get("status", "?")
                self.comp_table.setItem(r, 3, QTableWidgetItem(status))
                view_btn = QPushButton("View videos")
                view_btn.clicked.connect(
                    lambda _, rd=row_data: self._comp_show_videos(rd))
                self.comp_table.setCellWidget(r, 4, view_btn)
            total = len(patterns)
            done  = sum(1 for p in patterns if p.get("status") == "done")
            self.comp_status.setText(
                f"{total} channels in database  |  {done} fully decoded")
        except Exception as e:  # noqa: BLE001
            self.comp_status.setText(f"Refresh error: {e}")

    def _comp_scrape_start(self):
        api_key = (self.secrets.get("gemini_api_key") or
                   self.secrets.get("gemini_tts_keys") or "")
        if isinstance(api_key, list):
            api_key = api_key[0] if api_key else ""
        if not api_key:
            self.comp_status.setText(
                "Gemini API key required. Set it in Voiceover or API Keys tab.")
            return

        self._comp_stop_flag = [False]
        self.comp_scrape_btn.setEnabled(False)
        self.comp_status.setText("Scrape started...")
        self.comp_progress.setValue(0)

        import threading
        from PySide6.QtCore import QTimer
        from .. import competitor as comp_mod

        result_box = [None]
        logs       = []

        def _run():
            def _progress(pct, msg):
                if self._comp_stop_flag[0]:
                    raise InterruptedError("stopped")
                result_box.append((pct, msg))
                QTimer.singleShot(0, lambda: self._comp_tick(result_box))

            result_box[0] = comp_mod.run_full_scrape(
                api_key,
                n_videos=7,
                model=self.cfg.get("providers", {}).get(
                    "gemini_model", "gemini-2.0-flash"),
                progress_cb=_progress,
                logger=logs.append,
                resume=True)
            QTimer.singleShot(0, lambda: self._comp_done(result_box[0], logs))

        self._comp_thread = threading.Thread(target=_run, daemon=True)
        self._comp_thread.start()

    def _comp_tick(self, result_box):
        try:
            while len(result_box) > 1:
                item = result_box.pop(1)
                if isinstance(item, tuple):
                    pct, msg = item
                    self.comp_progress.setValue(int(pct))
                    self.comp_status.setText(msg[:120])
        except Exception:  # noqa: BLE001
            pass

    def _comp_done(self, summary, logs):
        self.comp_scrape_btn.setEnabled(True)
        if not summary:
            self.comp_status.setText("Scrape failed or was stopped.")
            return
        done    = summary.get("done", 0)
        skipped = summary.get("skipped", 0)
        failed  = summary.get("failed", 0)
        self.comp_progress.setValue(100)
        self.comp_status.setText(
            f"Scrape complete:  {done} decoded,  {skipped} skipped,  "
            f"{failed} failed  --  patterns saved to config/competitor_patterns.json")
        self._comp_refresh_table()

    def _comp_scrape_stop(self):
        self._comp_stop_flag[0] = True
        self.comp_scrape_btn.setEnabled(True)
        self.comp_status.setText("Stop requested -- current channel will finish.")

    def _comp_show_videos(self, row_data):
        videos = row_data.get("videos", [])
        if not videos:
            QMessageBox.information(self, "No videos",
                                    "No video data for this channel.")
            return
        lines = []
        for v in videos:
            decoded = "OK" if v.get("decoded") else "FAIL"
            views   = v.get("views", 0)
            lines.append(f"[{decoded}]  {v.get('title','')[:60]}"
                         f"  ({views:,} views)\n  {v.get('url','')}")
        QMessageBox.information(
            self,
            f"Videos  --  {row_data.get('handle','')}",
            "\n\n".join(lines)[:3000])

    def _comp_use_pattern(self):
        row = self.comp_table.currentRow()
        if row < 0:
            self.comp_status.setText("Select a channel row first.")
            return
        try:
            from .. import competitor as comp_mod
            patterns = comp_mod.get_all_master_patterns()
            if row >= len(patterns):
                return
            rd  = patterns[row]
            mp  = rd.get("pattern", {})
            if not mp:
                self.comp_status.setText("No pattern data for this channel.")
                return
            # Switch to Pattern tab and fill fields
            from ..patterns import normalize_pattern
            mp = normalize_pattern(mp)
            mp["name"] = mp.get("name") or f"Pattern from {rd['handle']}"
            # Find pattern tab index and switch
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == "Pattern":
                    self.tabs.setCurrentIndex(i)
                    break
            self._pat = mp
            self._pat_to_fields()
            self.comp_status.setText(
                f"Pattern from {rd['handle']} loaded into Pattern tab. "
                "Review and click 'Save pattern to channel'.")
        except Exception as e:  # noqa: BLE001
            self.comp_status.setText(f"Error: {e}")

    def _comp_link_to_channel(self):
        row = self.comp_table.currentRow()
        if row < 0:
            self.comp_status.setText("Select a channel row first.")
            return
        try:
            from .. import competitor as comp_mod
            from ..patterns import normalize_pattern, save_pattern
            patterns = comp_mod.get_all_master_patterns()
            if row >= len(patterns):
                return
            rd  = patterns[row]
            mp  = normalize_pattern(rd.get("pattern", {}))
            if not mp:
                self.comp_status.setText("No pattern data for this channel.")
                return
            # Ask which channel to link to
            channels = list((self.cfg.get("channels") or {}).keys())
            if not channels:
                self.comp_status.setText("No channels configured yet.")
                return
            # Use simple dialog
            dlg = QDialog(self)
            dlg.setWindowTitle("Link pattern to channel")
            fl  = QFormLayout(dlg)
            pick = QComboBox()
            pick.addItems(channels)
            fl.addRow("Channel:", pick)
            btns = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            fl.addRow(btns)
            if dlg.exec() != QDialog.Accepted:
                return
            cid = pick.currentText()
            mp["name"] = mp.get("name") or f"Pattern from {rd['handle']}"
            save_pattern(cid, mp, self.cfg)
            save_config(self.cfg)
            self.comp_status.setText(
                f"Pattern from {rd['handle']} linked to channel '{cid}' and saved.")
        except Exception as e:  # noqa: BLE001
            self.comp_status.setText(f"Error: {e}")

    # ------------------------------------------------ save
    def save(self):

        self.secrets["ai33pro_api_key"] = self.ai33_key.text().strip()
        self.secrets["gemini_api_key"] = self.gem_key.text().strip()
        self.secrets["xai_api_key"] = self.grok_key.text().strip()
        # save Gemini TTS key (shared with image key, stored separately too)
        if hasattr(self, "gemini_tts_key"):
            gtts_key = self.gemini_tts_key.text().strip()
            if gtts_key:
                self.secrets["gemini_tts_keys"] = [gtts_key]
                # also keep gemini_api_key in sync if it was empty
                if not self.secrets.get("gemini_api_key"):
                    self.secrets["gemini_api_key"] = gtts_key
        if hasattr(self, "key_edits"):
            for _svc, (ed, multi_name) in self.key_edits.items():
                self.secrets[multi_name] = [
                    ln.strip() for ln in ed.toPlainText().splitlines()
                    if ln.strip()]
            claude_keys = self.secrets.get("claude_api_keys") or []
            if claude_keys:
                self.secrets["claude_api_key"] = claude_keys[0]
        provs = self.cfg.setdefault("providers", {})
        provs["gemini_model"] = self.gem_model.currentText().strip()
        provs["grok_model"] = self.grok_model.currentText().strip()
        provs["script_provider"] = self.script_provider.currentText()
        provs["ai33pro_llm_base_url"] = self.llm_base.text().strip()
        provs["ai33pro_llm_model"] = self.llm_model.text().strip()
        provs["gemini_llm_model"] = self.gemini_llm_model.text().strip()
        provs["claude_review"] = self.claude_review.isChecked()
        provs["claude_base_url"] = self.claude_base.text().strip()
        provs["claude_model"] = self.claude_model.text().strip()
        # persist the PC-images section too (in case Apply wasn't clicked)
        if hasattr(self, "pc_channel"):
            cid = self.pc_channel.currentData()
            ch = (self.cfg.get("channels") or {}).get(cid)
            if ch is not None:
                ch["local_images"] = {
                    "enabled": self.pc_enabled.isChecked(),
                    "folder": self.pc_folder.text().strip(),
                }
        save_secrets(self.secrets)
        save_config(self.cfg)
        # Push the saved secrets back into the caller's dict so the main
        # window (and any already-queued jobs) see the new keys immediately.
        try:
            if isinstance(self._secrets_src, dict):
                self._secrets_src.clear()
                self._secrets_src.update(self.secrets)
        except Exception:  # noqa: BLE001
            pass
        # The window stays OPEN after Save — the user closes it himself.
        self.save_msg.setText("Saved ✓ — window stays open, "
                              "close it yourself when done.")
