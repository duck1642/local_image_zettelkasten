import json

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMessageBox, QTextEdit, QPushButton, QVBoxLayout, QWidget, QCheckBox

from logs.logger import LOGS_DIR, log_ui
from ui.log_utils import render_log_html


class AppLogsView(QWidget):
    def __init__(self):
        super().__init__()
        self.last_key = ""
        self.log_file_offset = 0
        self.log_content = ""
        self.log_selector = QComboBox()
        self.log_selector.addItems(["system.log", "ui.log", "ingestion.log"])
        self.log_selector.currentIndexChanged.connect(self.force_reload)
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Normal", "Full"])
        self.mode_selector.currentIndexChanged.connect(self.force_reload)
        
        self.show_debug = QCheckBox("Show Debug")
        self.show_debug.setChecked(True)
        self.show_debug.stateChanged.connect(self.force_reload)

        self.reload_button = QPushButton("Reload")
        self.reload_button.clicked.connect(self.force_reload)
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_current)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # Use a fixed-width font for better log alignment
        self.log_text.setStyleSheet("font-family: 'Consolas', 'Monaco', 'monospace'; background: #161b22;")

        top = QHBoxLayout()
        top.addWidget(self.log_selector)
        top.addWidget(self.mode_selector)
        top.addWidget(self.show_debug)
        top.addWidget(self.reload_button)
        top.addWidget(self.open_button)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addSpacing(8)
        layout.addWidget(self.log_text, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_log)
        self.timer.start(1000)
        self.refresh_log()

    def log_path(self):
        return LOGS_DIR / self.log_selector.currentText()

    def force_reload(self):
        self.log_file_offset = 0
        self.log_content = ""
        self.last_key = ""
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
        # Skip refresh if user is interacting with selection menus to avoid "stealing" focus or closing popups
        if self.log_selector.view().isVisible() or self.mode_selector.view().isVisible():
            return

        path = self.log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        
        file_size = path.stat().st_size
        
        # If file shrunk or changed, reset
        key = str(path)
        mode = self.mode_selector.currentText()
        show_debug = self.show_debug.isChecked()
        mode_key = f"{key}:{mode}:{show_debug}"
        
        if mode_key != self.last_key or file_size < self.log_file_offset:
            self.log_file_offset = 0
            self.log_content = ""
            self.last_key = mode_key
            self.log_text.clear()

        if file_size == self.log_file_offset:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if self.log_file_offset == 0:
                    # Initial load: read only the last 64KB to avoid hanging on massive logs
                    chunk_size = 1024 * 64
                    if file_size > chunk_size:
                        f.seek(file_size - chunk_size)
                    new_data = f.read()
                else:
                    f.seek(self.log_file_offset)
                    new_data = f.read()
                
                self.log_file_offset = f.tell()
                
            if not new_data and self.log_file_offset > 0:
                return
                
            self.log_content += new_data
            
            lines = self.log_content.splitlines()
            # Render the last 400 lines for a smooth experience
            display_lines = lines[-400:]
            
            rendered_html = render_log_html(
                display_lines, 
                show_debug=show_debug, 
                mode=mode
            )
                
            self.log_text.setHtml(rendered_html)
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
            
        except Exception as exc:
            log_ui("ERROR", "Qt log refresh failed", path=str(path), error=str(exc))
