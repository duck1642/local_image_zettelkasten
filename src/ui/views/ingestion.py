from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget

from logs.logger import LOGS_DIR, log_ui
from queue_service import QUEUE_LABELS, append_urls, clear_failed, move_failed_urls, parse_urls, queue_counts, read_queue, write_queue


class IngestionView(QWidget):
    start_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.log_file = LOGS_DIR / "system.log"
        self.last_size = 0
        self.current_queue = "normal"
        self.dirty = False
        self.running = False

        self.queue_buttons = {}
        self.normal_button = self.queue_button("normal")
        self.force_button = self.queue_button("force")
        self.failed_button = self.queue_button("failed")
        self.ready_label = QLabel("Ready: 0")
        self.ready_label.setObjectName("MutedLabel")

        self.reload_button = QPushButton("Reload")
        self.reload_button.clicked.connect(self.reload_current)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_current)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.request_start)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Edit queue markdown here...")
        self.editor.textChanged.connect(self.mark_dirty)

        self.append_button = QPushButton("Append URLs")
        self.append_button.clicked.connect(self.append_urls_dialog)
        self.retry_button = QPushButton("Retry Failed")
        self.retry_button.clicked.connect(self.retry_failed_dialog)
        self.clear_failed_button = QPushButton("Clear Failed")
        self.clear_failed_button.clicked.connect(self.clear_failed_dialog)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(800)

        top = QHBoxLayout()
        top.addWidget(self.normal_button)
        top.addWidget(self.force_button)
        top.addWidget(self.failed_button)
        top.addWidget(self.ready_label)
        top.addStretch(1)
        top.addWidget(self.reload_button)
        top.addWidget(self.save_button)
        top.addWidget(self.start_button)

        actions = QHBoxLayout()
        actions.addWidget(self.append_button)
        actions.addWidget(self.retry_button)
        actions.addWidget(self.clear_failed_button)
        actions.addStretch(1)

        editor_frame = QFrame()
        editor_frame.setObjectName("Panel")
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(10, 10, 10, 10)
        editor_layout.addLayout(top)
        editor_layout.addWidget(self.editor, 1)
        editor_layout.addLayout(actions)

        log_frame = QFrame()
        log_frame.setObjectName("Panel")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.addWidget(self.log_text)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.addWidget(editor_frame)
        splitter.addWidget(log_frame)
        splitter.setSizes([520, 240])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_log)
        self.timer.start(1000)
        self.load_queue("normal", force=True)
        self.refresh_log()

    def queue_button(self, queue: str) -> QPushButton:
        button = QPushButton(QUEUE_LABELS[queue])
        button.setCheckable(True)
        button.clicked.connect(lambda checked=False, value=queue: self.load_queue(value))
        self.queue_buttons[queue] = button
        return button

    def mark_dirty(self):
        self.dirty = True
        self.update_controls()

    def maybe_save_before_switch(self) -> bool:
        if not self.dirty:
            return True
        response = QMessageBox.question(
            self,
            "Unsaved Queue",
            "Save changes before switching queues?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if response == QMessageBox.StandardButton.Cancel:
            return False
        if response == QMessageBox.StandardButton.Save:
            self.save_current()
        return True

    def load_queue(self, queue: str, force: bool = False):
        if not force and queue != self.current_queue and not self.maybe_save_before_switch():
            self.update_controls()
            return
        self.current_queue = queue
        self.editor.blockSignals(True)
        self.editor.setPlainText(read_queue(queue))
        self.editor.blockSignals(False)
        self.dirty = False
        self.update_controls()
        log_ui("INFO", "Qt queue loaded", queue=queue)

    def reload_current(self):
        if self.dirty and not self.maybe_save_before_switch():
            return
        self.load_queue(self.current_queue, force=True)

    def save_current(self):
        write_queue(self.current_queue, self.editor.toPlainText())
        self.dirty = False
        self.update_controls()
        log_ui("INFO", "Qt queue saved", queue=self.current_queue)

    def request_start(self):
        if self.current_queue == "failed":
            QMessageBox.information(self, "Ingestion", "Failed queue cannot be started directly. Use Retry Failed.")
            return
        self.save_current()
        self.start_requested.emit(self.current_queue)

    def append_urls_dialog(self):
        if self.dirty and not self.maybe_save_before_switch():
            return
        text, ok = QInputDialog.getMultiLineText(self, "Append URLs", "URLs:")
        if not ok:
            return
        urls = parse_urls(text)
        if not urls:
            QMessageBox.information(self, "Append URLs", "No URLs found.")
            return
        append_urls(self.current_queue, urls)
        self.load_queue(self.current_queue, force=True)
        log_ui("INFO", "Qt queue URLs appended", queue=self.current_queue, count=len(urls))

    def retry_failed_dialog(self):
        if self.dirty and not self.maybe_save_before_switch():
            return
        counts = queue_counts()
        failed_count = counts.get("failed", 0)
        if not failed_count:
            QMessageBox.information(self, "Retry Failed", "No failed URLs found.")
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Retry Failed")
        dialog.setText(f"Retry {failed_count} failed URLs?")
        normal_button = dialog.addButton("Move to Normal", QMessageBox.ButtonRole.AcceptRole)
        force_button = dialog.addButton("Move to Force", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked not in {normal_button, force_button}:
            return
        target = "normal" if clicked is normal_button else "force"
        moved = move_failed_urls(target)
        self.load_queue(self.current_queue, force=True)
        QMessageBox.information(self, "Retry Failed", f"Moved {moved} URLs to {QUEUE_LABELS[target]}.")
        log_ui("INFO", "Qt failed URLs moved", target=target, count=moved)

    def clear_failed_dialog(self):
        if self.dirty and not self.maybe_save_before_switch():
            return
        counts = queue_counts()
        if not counts.get("failed", 0):
            QMessageBox.information(self, "Clear Failed", "No failed URLs found.")
            return
        response = QMessageBox.question(self, "Clear Failed", "Clear failed_links.md?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if response != QMessageBox.StandardButton.Yes:
            return
        clear_failed()
        self.load_queue(self.current_queue, force=True)
        log_ui("INFO", "Qt failed queue cleared")

    def set_running(self, running: bool):
        self.running = running
        self.update_controls()

    def update_controls(self):
        counts = queue_counts()
        if self.dirty:
            counts[self.current_queue] = len(parse_urls(self.editor.toPlainText()))
        for queue, button in self.queue_buttons.items():
            button.setText(f"{QUEUE_LABELS[queue]} {counts.get(queue, 0)}")
            button.setChecked(queue == self.current_queue)
        ready = counts.get("normal", 0) + counts.get("force", 0)
        self.ready_label.setText(f"Ready: {ready}")
        self.start_button.setEnabled(not self.running and self.current_queue in {"normal", "force"})
        self.retry_button.setEnabled(not self.running and counts.get("failed", 0) > 0)
        self.clear_failed_button.setEnabled(not self.running and counts.get("failed", 0) > 0)
        self.reload_button.setEnabled(not self.running)
        self.save_button.setEnabled(not self.running and self.dirty)
        self.append_button.setEnabled(not self.running)
        for button in self.queue_buttons.values():
            button.setEnabled(not self.running)

    def refresh_log(self):
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
        text = self.log_file.read_text(encoding="utf-8", errors="replace")
        if len(text) != self.last_size:
            self.last_size = len(text)
            self.log_text.setPlainText("--- Ingestion Monitor Active ---\n" + "\n".join(text.splitlines()[-120:]))
            self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        self.update_controls()
