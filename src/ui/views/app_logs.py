import json

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from logs.logger import LOGS_DIR, log_ui


class AppLogsView(QWidget):
    def __init__(self):
        super().__init__()
        self.last_key = ""
        self.last_size = -1
        self.log_selector = QComboBox()
        self.log_selector.addItems(["system.log", "ui.log", "ingestion.log"])
        self.log_selector.currentTextChanged.connect(self.refresh_log)
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Normal", "Full"])
        self.mode_selector.currentTextChanged.connect(self.force_reload)
        self.reload_button = QPushButton("Reload")
        self.reload_button.clicked.connect(self.force_reload)
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_current)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(1200)

        top = QHBoxLayout()
        top.addWidget(self.log_selector)
        top.addWidget(self.mode_selector)
        top.addWidget(self.reload_button)
        top.addWidget(self.open_button)
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

    def open_current(self):
        path = self.log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if not opened:
            QMessageBox.warning(self, "Open Log", f"Could not open {path}.")
        log_ui("INFO", "Qt log opened externally", path=str(path), opened=opened)

    def refresh_log(self):
        path = self.log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        key = str(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        mode = self.mode_selector.currentText()
        mode_key = f"{key}:{mode}"
        if mode_key != self.last_key or len(text) != self.last_size:
            self.last_key = mode_key
            self.last_size = len(text)
            lines = text.splitlines()[-300:]
            if mode == "Full":
                rendered = "\n\n".join(lines)
            else:
                rendered = self.render_normal(lines)
            self.log_text.setPlainText(rendered)
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def render_normal(self, lines: list[str]) -> str:
        rendered = []
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                rendered.append(line)
                continue
            timestamp = str(item.get("timestamp", ""))[-8:]
            level = item.get("level", "")
            message = item.get("message", "")
            rendered.append(f"{timestamp}  {level:<7} {message}")
            details = self.render_details(item)
            if details:
                rendered.append(f"              {details}")
            rendered.append("")
        return "\n".join(rendered).rstrip()

    def render_details(self, item: dict) -> str:
        skip = {"timestamp", "level", "module", "message"}
        noisy = {"host_width", "host_height", "hint_width", "hint_height", "child_count", "item_count", "visible", "tags_wrap_width", "tags_wrap_height", "tags_wrap_hint_width", "tags_wrap_hint_height", "wd_panel_width", "wd_panel_height"}
        parts = []
        for key, value in item.items():
            if key in skip or key in noisy:
                continue
            if isinstance(value, str) and len(value) > 96:
                value = f"{value[:93]}..."
            parts.append(f"{key}={value}")
            if len(parts) >= 6:
                break
        return " | ".join(parts)
