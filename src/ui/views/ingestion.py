from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from logs.logger import LOGS_DIR


class IngestionView(QWidget):
    def __init__(self):
        super().__init__()
        self.log_file = LOGS_DIR / "system.log"
        self.last_size = 0
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.log_text)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_log)
        self.timer.start(1000)
        self.refresh_log()

    def refresh_log(self):
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
        text = self.log_file.read_text(encoding="utf-8", errors="replace")
        if len(text) != self.last_size:
            self.last_size = len(text)
            self.log_text.setPlainText("--- Ingestion Monitor Active ---\n" + "\n".join(text.splitlines()[-120:]))
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
