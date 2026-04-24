from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from logs.logger import LOGS_DIR


class AppLogsView(QWidget):
    def __init__(self):
        super().__init__()
        self.last_key = ""
        self.last_size = -1
        self.log_selector = QComboBox()
        self.log_selector.addItems(["system.log", "ui.log", "ingestion.log"])
        self.log_selector.currentTextChanged.connect(self.refresh_log)
        self.reload_button = QPushButton("Reload")
        self.reload_button.clicked.connect(self.force_reload)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(1200)

        top = QHBoxLayout()
        top.addWidget(self.log_selector)
        top.addWidget(self.reload_button)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.log_text, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_log)
        self.timer.start(1000)
        self.refresh_log()

    def log_path(self):
        return LOGS_DIR / self.log_selector.currentText()

    def force_reload(self):
        self.last_size = -1
        self.refresh_log()

    def refresh_log(self):
        path = self.log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        key = str(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        if key != self.last_key or len(text) != self.last_size:
            self.last_key = key
            self.last_size = len(text)
            self.log_text.setPlainText("\n".join(text.splitlines()[-300:]))
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
