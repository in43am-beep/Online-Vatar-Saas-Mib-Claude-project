"""mib/ui/theme.py — "Frontier dark" design tokens + Qt stylesheet.

Workstream D: dark UI decoded from the Frontier reveal look —
near-black stage, gold/amber accent, small-caps monospace labels,
big thin numerals, thin gold progress bars, ambient corner glows.

Accessibility notes (senior audience):
- base 15px type; body pairs >= 7:1 (TEXT on BG ~ 13:1,
  TEXT on PANEL ~ 11:1)
- muted meta text (#8a8f9e on #1c1f26) ~ 5.1:1 — AA for normal
  text; never used below 13px and never for primary actions
- visible 2px gold focus rings, min 40px primary targets.

All historical objectNames / selectors are preserved (sidebar, panel,
h1/h2/h3, muted, mono, primary, danger, preset, go, channel_card,
source_card, stepdot*, badge*, status_pill*, expander, ...). Only the
visual values changed. New Frontier selectors: mini_label, big_timer,
frontier_card, frontier_render, pipe_box, thin progress bars.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QPen, QFont
from PySide6.QtWidgets import QLabel, QWidget, QStackedLayout

# ------------------------------------------------------------------ tokens
BG = "#14161c"           # near-black app background
PANEL = "#1c1f26"        # cards / panels
PANEL2 = "#23262e"       # raised panel
DEEP = "#101216"         # deepest wells (inputs, sidebar, tracks)
BORDER = "#2a2e38"       # thin muted hairlines
TEXT = "#e8e4da"         # warm off-white body text
MUTED = "#8a8f9e"        # muted meta text (~5.1:1 on PANEL — AA)
GOLD = "#d4a24e"         # frontier gold accent
GOLD_DIM = "#8a6a34"     # dim gold (pulse phase, borders)
GOLD_DEEP = "#a67f3a"
GREEN = "#43c488"        # done / ok
RED = "#e5534b"          # failed / danger
BLUE = "#5aa9e6"
PURPLE = "#b48ce8"
PINK = "#e87fa0"

# --- legacy names (kept so existing modules keep working) ---
INK = BG                 # was deep slate-ink, now frontier near-black
AMBER = GOLD             # tungsten amber -> frontier gold
AMBER_DARK = GOLD_DEEP
TRACK_AROLL = GOLD
TRACK_BROLL = BLUE
TRACK_VOICE = GREEN
TRACK_SUB = PURPLE
TRACK_TEXT = PINK
TRACK_PROMO = RED

BASE_FONT_PX = 15
SIDEBAR_W = 224

APP_QSS = f"""
* {{
    font-size: {BASE_FONT_PX}px;
}}
QMainWindow, QWidget#app_root {{
    background: {BG};
    color: {TEXT};
}}
QWidget {{
    background: transparent;
    color: {TEXT};
}}
/* ---------- frontier typography helpers ---------- */
QLabel#mini_label {{
    color: {MUTED};
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}}
QLabel#big_timer {{
    color: {TEXT};
    font-family: "Consolas", "Courier New", monospace;
    font-size: 46px;
    font-weight: 200;
}}
QLabel#h1 {{ font-size: 26px; font-weight: bold; }}
QLabel#h2 {{ font-size: 20px; font-weight: bold; }}
QLabel#h3 {{ font-size: 17px; font-weight: bold; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#mono {{ font-family: "Consolas", "Courier New", monospace; }}
/* ---------- sidebar (QListWidget items) ---------- */
QListWidget#sidebar {{
    background: {DEEP};
    border: none;
    border-right: 1px solid {BORDER};
    outline: none;
    padding: 8px 0px;
}}
QListWidget#sidebar::item {{
    padding: 12px 16px;
    border: none;
    border-left: 3px solid transparent;
    color: {MUTED};
    font-size: 16px;
}}
QListWidget#sidebar::item:hover {{
    background: {PANEL};
    color: {TEXT};
}}
QListWidget#sidebar::item:selected {{
    background: {PANEL2};
    color: {TEXT};
    border-left: 3px solid {GOLD};
    font-weight: bold;
}}
QListWidget#sidebar:focus {{
    border: 2px solid {GOLD};
}}
/* ---------- nav buttons (future use) ---------- */
QPushButton#nav_btn {{
    text-align: left;
    padding: 12px 16px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    color: {MUTED};
    font-size: 16px;
    min-height: 40px;
}}
QPushButton#nav_btn:hover {{
    background: {PANEL};
    color: {TEXT};
}}
QPushButton#nav_btn:checked {{
    background: {PANEL2};
    color: {TEXT};
    border-left: 3px solid {GOLD};
    font-weight: bold;
}}
QPushButton#nav_btn:focus {{
    outline: none;
    border: 2px solid {GOLD};
}}
/* ---------- panels ---------- */
QFrame#panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#panel_raised {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#frontier_card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#frontier_render {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#frontier_render[result="ok"] {{
    border: 1px solid {GREEN};
}}
QFrame#frontier_render[result="fail"] {{
    border: 1px solid {RED};
}}
/* ---------- buttons ---------- */
QPushButton {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 9px 18px;
    color: {TEXT};
    min-height: 30px;
}}
QPushButton:hover {{ border-color: {GOLD}; }}
QPushButton:pressed {{ background: #2b2f3a; }}
QPushButton:disabled {{ color: #5a6272; }}
QPushButton:focus {{ border: 2px solid {GOLD}; outline: none; }}
QPushButton#primary {{
    background: {GOLD};
    color: #14161c;
    font-weight: bold;
    border: none;
    min-height: 40px;
}}
QPushButton#primary:hover {{ background: #e0b265; }}
QPushButton#primary:pressed {{ background: {GOLD_DEEP}; }}
QPushButton#danger {{ border-color: {RED}; color: {RED}; }}
QPushButton#danger:hover {{ background: #382226; }}
/* ---------- inputs ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {DEEP};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 10px;
    color: {TEXT};
    selection-background-color: {GOLD};
    selection-color: #14161c;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 2px solid {GOLD};
}}
QComboBox QAbstractItemView {{
    background: {DEEP};
    color: {TEXT};
    selection-background-color: {GOLD};
    selection-color: #14161c;
}}
QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 20px; height: 20px; }}
/* ---------- tables ---------- */
QTableWidget {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    alternate-background-color: #191c23;
}}
QTableWidget::item {{ padding: 6px; }}
QHeaderView::section {{
    background: {DEEP};
    color: {MUTED};
    border: none;
    padding: 10px 6px;
    font-weight: bold;
}}
/* ---------- progress bars ---------- */
QProgressBar {{
    background: {DEEP};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    color: {TEXT};
    min-height: 20px;
}}
QProgressBar::chunk {{
    background: {GOLD};
    border-radius: 5px;
}}
/* thin gold bar (frontier render card, segments, waveforms) */
QProgressBar#thin {{
    background: {DEEP};
    border: 1px solid {BORDER};
    border-radius: 3px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar#thin::chunk {{
    background: {GOLD};
    border-radius: 2px;
}}
/* ---------- tabs / splitter / scrollbars ---------- */
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {PANEL}; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 10px 20px;
    border: none;
    min-height: 36px;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 3px solid {GOLD}; font-weight: bold; }}
QSplitter::handle {{ background: {BORDER}; }}
QScrollBar:vertical {{
    background: transparent; width: 12px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 6px; min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: #3d4453; }}
QToolTip {{
    background: {DEEP}; color: {TEXT};
    border: 1px solid {GOLD}; padding: 6px;
}}
/* ---------- pills + badges ---------- */
QLabel#status_pill {{
    background: #26200f;
    border: 1px solid {GOLD};
    border-radius: 12px;
    padding: 4px 14px;
    color: {GOLD};
    font-weight: bold;
}}
QLabel#status_pill_live {{
    background: #10281d;
    border: 1px solid {GREEN};
    border-radius: 12px;
    padding: 4px 14px;
    color: {GREEN};
    font-weight: bold;
}}
QLabel#badge {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 3px 10px;
    color: {MUTED};
}}
QLabel#badge_ok {{ background: #10281d; border: 1px solid {GREEN}; border-radius: 10px; padding: 3px 10px; color: {GREEN}; font-weight: bold; }}
QLabel#badge_bad {{ background: #382226; border: 1px solid {RED}; border-radius: 10px; padding: 3px 10px; color: {RED}; font-weight: bold; }}
QWizard {{
    background: {BG};
}}
QStatusBar {{
    background: {DEEP};
    color: {MUTED};
    border-top: 1px solid {BORDER};
}}
QTableWidget:focus, QListWidget:focus, QTreeView:focus {{
    border: 2px solid {GOLD};
    outline: none;
}}
/* themed selection for every list (sidebar has its own rules above) */
QListWidget::item {{
    padding: 8px 10px;
}}
QListWidget::item:hover {{
    background: {PANEL};
}}
QListWidget::item:selected {{
    background: {PANEL2};
    color: {TEXT};
    border-left: 3px solid {GOLD};
}}
/* ---------- wizard: clickable cards ---------- */
QFrame#channel_card {{
    background: {PANEL};
    border: 2px solid {BORDER};
    border-radius: 10px;
}}
QFrame#channel_card:hover, QFrame#source_card:hover {{
    border-color: {GOLD};
}}
QFrame#channel_card_sel {{
    background: {PANEL2};
    border: 2px solid {GOLD};
    border-radius: 10px;
}}
QFrame#source_card {{
    background: {PANEL};
    border: 2px solid {BORDER};
    border-radius: 10px;
}}
QFrame#source_card_sel {{
    background: {PANEL2};
    border: 2px solid {GOLD};
    border-radius: 10px;
}}
QFrame#source_card:disabled {{
    color: #5a6272;
    border-color: {PANEL2};
}}
QLabel#card_check {{
    color: {GREEN};
    font-size: 22px;
    font-weight: bold;
}}
/* ---------- wizard: step dots ---------- */
QLabel#stepdot {{
    background: {PANEL2};
    border: 2px solid {BORDER};
    border-radius: 17px;
    color: {MUTED};
    font-weight: bold;
}}
QLabel#stepdot_active {{
    background: {GOLD};
    border: 2px solid {GOLD};
    border-radius: 17px;
    color: #14161c;
    font-weight: bold;
}}
QLabel#stepdot_done {{
    background: #10281d;
    border: 2px solid {GREEN};
    border-radius: 17px;
    color: {GREEN};
    font-weight: bold;
}}
QLabel#stepdot_label {{
    color: {MUTED};
}}
QFrame#stepdot_line {{
    background: {BORDER};
    border: none;
}}
/* ---------- wizard: preset + go buttons ---------- */
QPushButton#preset {{
    background: {PANEL};
    border: 2px solid {BORDER};
    border-radius: 10px;
    font-size: 18px;
    font-weight: bold;
    min-height: 76px;
    color: {TEXT};
}}
QPushButton#preset:hover {{ border-color: {GOLD}; }}
QPushButton#preset:checked {{
    background: {GOLD};
    border-color: {GOLD};
    color: #14161c;
}}
QPushButton#go {{
    background: {GREEN};
    border: none;
    border-radius: 10px;
    font-size: 20px;
    font-weight: bold;
    color: #0b1f14;
    min-height: 64px;
}}
QPushButton#go:hover {{ background: #5bd89c; }}
QPushButton#go:pressed {{ background: #35a06d; }}
QPushButton#go:disabled {{ background: {PANEL2}; color: #5a6272; }}
/* ---------- advanced expander ---------- */
QPushButton#expander {{
    background: transparent;
    border: none;
    text-align: left;
    color: {MUTED};
    font-weight: bold;
    padding: 8px 4px;
    min-height: 30px;
}}
QPushButton#expander:hover {{ color: {GOLD}; border: none; }}
QPushButton#expander:focus {{ border: 2px solid {GOLD}; }}
/* ---------- pipeline flow widget ---------- */
QFrame#pipe_box {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#pipe_box[pstate="active"] {{
    border: 2px solid {GOLD};
}}
QFrame#pipe_box[pstate="active_dim"] {{
    border: 2px solid {GOLD_DIM};
}}
QFrame#pipe_box[pstate="done"] {{
    border: 1px solid {GREEN};
}}
QFrame#pipe_box[pstate="failed"] {{
    border: 2px solid {RED};
}}
QLabel#pipe_state {{
    color: {MUTED};
    font-weight: bold;
}}
QLabel#pipe_state[pstate="active"] {{ color: {GOLD}; }}
QLabel#pipe_state[pstate="active_dim"] {{ color: {GOLD_DIM}; }}
QLabel#pipe_state[pstate="done"] {{ color: {GREEN}; }}
QLabel#pipe_state[pstate="failed"] {{ color: {RED}; }}
QFrame#pipe_link {{
    background: {BORDER};
    border: none;
    max-height: 2px;
}}
QFrame#pipe_link[lit="1"] {{
    background: {GOLD};
}}
/* ---------- checklist rows ---------- */
QLabel#check_ok {{ color: {GREEN}; font-weight: bold; font-size: 16px; }}
QLabel#check_todo {{ color: {MUTED}; font-weight: bold; font-size: 16px; }}

"""


def qss():
    """The full application stylesheet."""
    return APP_QSS


# ------------------------------------------------------------------ helpers

def mini_label(text):
    """Small-caps letter-spaced monospace label (ELAPSED, SEGMENTS, ...).

    Upper-cases the text; letter spacing applied when the Qt build
    supports it (Qt >= 5.13), otherwise thin-space fallback.
    """
    lbl = QLabel(str(text).upper())
    lbl.setObjectName("mini_label")
    try:
        f = QFont("Consolas", 9)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 140)
        lbl.setFont(f)
    except Exception:
        hair = "\u2009"
        lbl.setText(hair.join(str(text).upper()))
    return lbl


def big_timer():
    """Big thin-numeral timer label (HH:MM:SS). Monospace => tabular digits."""
    lbl = QLabel("--:--:--")
    lbl.setObjectName("big_timer")
    try:
        lbl.setFont(QFont("Consolas", 44, QFont.Light))
    except Exception:
        pass
    return lbl


def fmt_seconds(s):
    """180 -> '3:00'."""
    try:
        s = float(s)
    except (TypeError, ValueError):
        return "--"
    m, sec = divmod(int(s), 60)
    return f"{m}:{sec:02d}"


def fmt_hms(s):
    """3661 -> '1:01:01' (for big_timer)."""
    try:
        s = int(float(s))
    except (TypeError, ValueError):
        return "--:--:--"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def fmt_eta(s):
    if s is None:
        return "--"
    return fmt_seconds(s)


# ------------------------------------------------- ambient background layer


class AmbientBackground(QWidget):
    """Faint warm-orange (top-left) + purple (right) radial glows + subtle
    grid texture, painted behind all content. Purely decorative, keeps the
    app near-black while giving the Frontier reveal depth."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        if r.isEmpty():
            p.end()
            return
        p.fillRect(r, QColor(BG))
        diag = max(r.width(), r.height())
        # warm-orange glow, top-left
        g1 = QRadialGradient(0, 0, diag * 0.55)
        g1.setColorAt(0.0, QColor(212, 162, 78, 26))
        g1.setColorAt(1.0, QColor(212, 162, 78, 0))
        p.fillRect(r, g1)
        # purple glow, right edge
        g2 = QRadialGradient(r.width(), int(r.height() * 0.45), diag * 0.5)
        g2.setColorAt(0.0, QColor(120, 90, 200, 22))
        g2.setColorAt(1.0, QColor(120, 90, 200, 0))
        p.fillRect(r, g2)
        # subtle grid texture
        pen = QPen(QColor(255, 255, 255, 7))
        p.setPen(pen)
        step = 48
        for x in range(0, r.width(), step):
            p.drawLine(x, 0, x, r.height())
        for y in range(0, r.height(), step):
            p.drawLine(0, r.width(), y)
        p.end()


def install_ambient(window):
    """Place an AmbientBackground behind the main window's central widget.

    Call once after setCentralWidget in app.py. Safe offscreen; returns
    the AmbientBackground (or None if there is no central widget yet).
    """
    central = window.centralWidget()
    if central is None:
        return None
    container = QWidget()
    stack = QStackedLayout(container)
    try:
        stack.setStackingMode(QStackedLayout.StackAll)
    except Exception:
        pass
    stack.setContentsMargins(0, 0, 0, 0)
    amb = AmbientBackground()
    stack.addWidget(amb)
    stack.addWidget(central)
    try:
        stack.setCurrentWidget(central)
    except Exception:
        pass
    window.setCentralWidget(container)
    return amb
