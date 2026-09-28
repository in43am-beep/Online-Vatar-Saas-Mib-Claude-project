"""mib/ui/logviewer.py — "Stuck? Read the log" viewer dialog."""
from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit


class LogViewerDialog(QDialog):
    def __init__(self, parent, log_path):
        super().__init__(parent)
        self.setWindowTitle("Run log")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        if log_path and Path(log_path).is_file():
            lay.addWidget(QLabel(str(log_path)))
            try:
                text = Path(log_path).read_text(encoding="utf-8",
                                                errors="replace")
                lines = text.splitlines()[-800:]
            except Exception:  # noqa: BLE001
                lines = ["(could not read log)"]
        else:
            lay.addWidget(QLabel("No run.log yet — generate a video first."))
            lines = []
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText("\n".join(lines))
        lay.addWidget(view)
