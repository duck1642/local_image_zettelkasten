from pathlib import Path

from PySide6.QtCore import QThread, Qt, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QStatusBar, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from md_generator import generate_markdown
from processor import process_file
from queue_service import INGESTION_LOCK, QUEUE_LABELS, run_queue
from tagging import tag_media
from ui.views.app_logs import AppLogsView
from ui.views.ingestion import IngestionView
from ui.views.inspector import InspectorView
from ui.views.modals import MetadataDialog
from ui.views.review import ReviewView
from ui.views.settings import SettingsView
from ui.views.vault import VaultView
from utils import get_config, note_path_for


class IngestionWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, queue: str):
        super().__init__()
        self.queue = queue

    def run(self):
        try:
            stats = run_queue(self.queue)
            self.completed.emit(f"{QUEUE_LABELS[self.queue]} ingestion complete. Added: {stats['processed']} | Skipped: {stats.get('skipped', 0)} | Errors: {stats['errors']}")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            INGESTION_LOCK.release()


class TagWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, asset_path: Path, item_hash: str, config: dict):
        super().__init__()
        self.asset_path = Path(asset_path)
        self.item_hash = item_hash
        self.config = config

    def run(self):
        try:
            self.completed.emit(tag_media(self.asset_path, item_hash=self.item_hash, config=self.config))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LIZ - Management Center")
        self.config = get_config()
        self.prefixes = self.config.get("ui", {}).get("prefixes", {"command": ">", "platform": "@", "artist": "a:", "tag": "#"})
        self.worker = None
        self.tag_worker = None
        self.video_mode = "normal"

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(f"Search (use {self.prefixes['artist']} for artist, {self.prefixes['command']} for cmd)...")
        self.search_input.returnPressed.connect(self.handle_search)
        self.add_button = QPushButton("Add Files")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.clicked.connect(self.add_files)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ui)
        self.vault_count_label = QLabel("Showing 0 items")
        self.vault_count_label.setObjectName("MutedLabel")

        self.nav_buttons = []
        nav_layout = QVBoxLayout()
        for label, index in [("Vault", 0), ("Review", 1), ("Ingestion", 2), ("App Logs", 3), ("Settings", 4)]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.show_view(i))
            self.nav_buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)

        self.vault_view = VaultView()
        self.inspector = InspectorView()
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inspector_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.inspector_scroll.setWidget(self.inspector)
        self.inspector_host = QFrame()
        self.inspector_host.setObjectName("InspectorHost")
        inspector_host_layout = QVBoxLayout(self.inspector_host)
        inspector_host_layout.setContentsMargins(0, 0, 0, 0)
        inspector_host_layout.setSpacing(0)
        inspector_host_layout.addWidget(self.inspector_scroll)
        self.media_focus_host = QWidget()
        self.media_focus_host.setObjectName("AppSurface")
        self.media_focus_layout = QVBoxLayout(self.media_focus_host)
        self.media_focus_layout.setContentsMargins(0, 0, 0, 0)
        self.media_focus_layout.setSpacing(10)
        self.media_focus_host.setVisible(False)
        self.review_view = ReviewView()
        self.ingestion_view = IngestionView()
        self.app_logs_view = AppLogsView()
        self.settings_view = SettingsView()
        self.stack = QStackedWidget()
        self.stack.setObjectName("AppSurface")
        self.stack.addWidget(self.vault_view)
        self.stack.addWidget(self.review_view)
        self.stack.addWidget(self.ingestion_view)
        self.stack.addWidget(self.app_logs_view)
        self.stack.addWidget(self.settings_view)

        self.vault_view.item_selected.connect(self.handle_item_selected)
        self.inspector.saved.connect(self.refresh_vault)
        self.inspector.tag_requested.connect(self.tag_selected_image)
        self.inspector.wide_requested.connect(self.toggle_video_wide)
        self.inspector.fullscreen_requested.connect(self.toggle_video_fullscreen)
        self.review_view.changed.connect(self.refresh_vault)
        self.settings_view.saved.connect(self.reload_config)
        self.ingestion_view.start_requested.connect(self.run_ingestion_queue)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.search_input, 1)
        top_layout.addWidget(self.add_button)
        top_layout.addWidget(self.refresh_button)
        top_layout.addWidget(self.vault_count_label)
        workspace_layout = QVBoxLayout()
        workspace_layout.addLayout(top_layout)
        workspace_layout.addWidget(self.stack, 1)

        self.nav_widget = QWidget()
        self.nav_widget.setObjectName("AppSurface")
        self.nav_widget.setFixedWidth(110)
        self.nav_widget.setLayout(nav_layout)
        self.workspace = QWidget()
        self.workspace.setObjectName("AppSurface")
        self.workspace.setLayout(workspace_layout)
        self.workspace.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.inspector_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        root_layout = QHBoxLayout()
        self.root_layout_main = root_layout
        root_layout.setContentsMargins(12, 12, 12, 0)
        root_layout.setSpacing(12)
        root_layout.addWidget(self.nav_widget)
        root_layout.addWidget(self.workspace, 1)
        root_layout.addWidget(self.inspector_host, 0, Qt.AlignmentFlag.AlignRight)
        root_layout.addWidget(self.media_focus_host, 1)
        self.set_video_mode("normal")

        root = QWidget()
        root.setObjectName("AppSurface")
        root.setLayout(root_layout)
        self.setCentralWidget(root)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.show_view(0)
        self.update_stats()

    def toggle_video_wide(self):
        self.set_video_mode("normal" if self.video_mode == "wide" else "wide")

    def toggle_video_fullscreen(self):
        self.set_video_mode("normal" if self.video_mode == "fullscreen" else "fullscreen")

    def set_video_mode(self, mode: str):
        previous_mode = self.video_mode
        self.video_mode = mode
        focused = mode != "normal"
        self.nav_widget.setVisible(not focused)
        self.workspace.setVisible(not focused)
        self.inspector_host.setVisible(not focused and self.stack.currentIndex() == 0)
        self.media_focus_host.setVisible(focused)
        if focused:
            self.move_media_to_focus()
        else:
            self.restore_media_to_inspector()
        if hasattr(self, "status"):
            self.status.setVisible(mode != "fullscreen")
        self.inspector_host.setMinimumWidth(520)
        self.inspector_host.setMaximumWidth(520)
        self.inspector_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.inspector.setMinimumWidth(0)
        self.inspector.setMaximumWidth(16777215)
        if self.centralWidget() and self.centralWidget().layout():
            self.centralWidget().layout().setContentsMargins(0 if focused else 12, 0 if focused else 12, 0 if focused else 12, 0)
            self.centralWidget().layout().setSpacing(0 if focused else 12)
        self.inspector.set_focus_mode(mode)
        if mode == "fullscreen":
            self.showFullScreen()
        elif previous_mode == "fullscreen":
            self.exit_fullscreen_window_state()
        self.log_focus_layout("after_set_video_mode")
        log_ui("INFO", "Qt video layout mode changed", mode=mode)

    def exit_fullscreen_window_state(self):
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowFullScreen)
        self.showNormal()
        QTimer.singleShot(0, self.showNormal)
        QTimer.singleShot(50, lambda: self.setWindowState(self.windowState() & ~Qt.WindowState.WindowFullScreen))

    def move_media_to_focus(self):
        if self.media_focus_layout.indexOf(self.inspector.media_widget) == -1:
            self.inspector.root_layout.removeWidget(self.inspector.media_widget)
            self.media_focus_layout.addWidget(self.inspector.media_widget, 1)
        if self.media_focus_layout.indexOf(self.inspector.media_controls) == -1:
            self.inspector.root_layout.removeWidget(self.inspector.media_controls)
            self.media_focus_layout.addWidget(self.inspector.media_controls)

    def restore_media_to_inspector(self):
        if self.inspector.root_layout.indexOf(self.inspector.media_widget) == -1:
            self.media_focus_layout.removeWidget(self.inspector.media_widget)
            self.inspector.root_layout.insertWidget(0, self.inspector.media_widget)
        if self.inspector.root_layout.indexOf(self.inspector.media_controls) == -1:
            self.media_focus_layout.removeWidget(self.inspector.media_controls)
            self.inspector.root_layout.insertWidget(1, self.inspector.media_controls)

    def log_focus_layout(self, stage: str):
        inspector_host_geometry = self.inspector_host.geometry()
        focus_geometry = self.media_focus_host.geometry()
        inspector_geometry = self.inspector.geometry()
        media_geometry = self.inspector.media_widget.geometry()
        log_ui(
            "INFO",
            "Qt focus layout geometry",
            stage=stage,
            mode=self.video_mode,
            focus_visible=self.media_focus_host.isVisible(),
            inspector_host_visible=self.inspector_host.isVisible(),
            inspector_host_width=inspector_host_geometry.width(),
            inspector_host_height=inspector_host_geometry.height(),
            focus_width=focus_geometry.width(),
            focus_height=focus_geometry.height(),
            inspector_width=inspector_geometry.width(),
            inspector_height=inspector_geometry.height(),
            media_width=media_geometry.width(),
            media_height=media_geometry.height(),
        )

    def keyPressEvent(self, event):
        if self.inspector.has_active_video():
            player = self.inspector.video_preview
            if event.key() == Qt.Key.Key_Space:
                player.toggle_play()
                return
            if event.key() == Qt.Key.Key_Left:
                player.seek_relative(-5000)
                return
            if event.key() == Qt.Key.Key_Right:
                player.seek_relative(5000)
                return
            if event.key() == Qt.Key.Key_F:
                self.toggle_video_fullscreen()
                return
        if event.key() == Qt.Key.Key_Escape and self.video_mode != "normal":
            self.set_video_mode("normal")
            return
        if event.key() == Qt.Key.Key_F5:
            self.refresh_ui()
            return
        super().keyPressEvent(event)

    def show_view(self, index: int):
        self.stack.setCurrentIndex(index)
        self.set_nav_checked(index)
        if self.video_mode == "normal":
            self.inspector_host.setVisible(index == 0)
        if index == 0:
            self.vault_view.refresh()
        elif index == 1:
            self.review_view.load_items()
        self.update_stats()

    def set_nav_checked(self, index: int):
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def update_stats(self):
        conn = init_database()
        count = conn.cursor().execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
        self.vault_count_label.setText(f"Showing {self.vault_view.item_count()} of {count}")
        self.status.showMessage(f"Total Items: {count} | DB: WAL | LIZ Qt")
        log_ui("INFO", "Qt stats updated", item_count=count)

    def handle_item_selected(self, item_hash: str):
        self.inspector.load_item(item_hash)
        log_ui("INFO", "Qt item selected", hash=item_hash)

    def handle_search(self):
        text = self.search_input.text().strip()
        if not text:
            self.vault_view.refresh()
            self.update_stats()
            return
        if text.startswith(self.prefixes["command"]):
            command = text[len(self.prefixes["command"]):].strip().lower()
            if command == "ingest":
                self.run_ingestion_command()
            elif command == "retry":
                self.retry_failed_links()
            else:
                QMessageBox.information(self, "Command", f"Unknown command: {command}")
        elif text.startswith(self.prefixes["artist"]):
            self.stack.setCurrentIndex(0)
            self.set_nav_checked(0)
            self.vault_view.filter_by("source_artist", text[len(self.prefixes["artist"]):].strip())
        elif text.startswith(self.prefixes["platform"]):
            self.stack.setCurrentIndex(0)
            self.set_nav_checked(0)
            self.vault_view.filter_by("platform", text[len(self.prefixes["platform"]):].strip())
        elif text.startswith(self.prefixes["tag"]):
            QMessageBox.information(self, "Search", "Topic search now comes from note frontmatter and is not available in the DB-backed vault filter.")
        else:
            self.stack.setCurrentIndex(0)
            self.set_nav_checked(0)
            self.vault_view.filter_by("original_filename", text)
        self.search_input.clear()
        self.update_stats()

    def run_ingestion_command(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Ingestion", "Ingestion is already running.")
            return
        self.run_ingestion_queue(self.ingestion_view.current_queue if self.ingestion_view.current_queue in {"normal", "force"} else "normal")

    def run_ingestion_queue(self, queue: str):
        if queue not in {"normal", "force"}:
            QMessageBox.information(self, "Ingestion", "Failed queue cannot be started directly. Use Retry Failed.")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Ingestion", "Ingestion is already running.")
            return
        if self.ingestion_view.current_queue == queue and self.ingestion_view.dirty:
            self.ingestion_view.save_current()
        if not INGESTION_LOCK.acquire(blocking=False):
            QMessageBox.information(self, "Ingestion", "Another ingestion queue is already running.")
            return
        self.worker = IngestionWorker(queue)
        self.worker.completed.connect(self.ingestion_done)
        self.worker.failed.connect(self.ingestion_failed)
        self.worker.finished.connect(lambda: self.ingestion_view.set_running(False))
        self.ingestion_view.set_running(True)
        self.worker.start()
        self.show_view(2)
        self.status.showMessage(f"{QUEUE_LABELS[queue]} ingestion running...")
        log_ui("INFO", "Qt ingestion queue started", queue=queue)

    def ingestion_done(self, message: str):
        QMessageBox.information(self, "Ingestion", message)
        self.refresh_vault()
        self.ingestion_view.load_queue(self.ingestion_view.current_queue, force=True)

    def ingestion_failed(self, message: str):
        QMessageBox.critical(self, "Ingestion Error", message)
        log_ui("ERROR", "Qt ingestion command failed", error=message)

    def retry_failed_links(self):
        if not INGESTION_LOCK.acquire(blocking=False):
            QMessageBox.information(self, "Retry", "Ingestion is already running.")
            return
        try:
            self.show_view(2)
            self.ingestion_view.retry_failed_dialog()
        finally:
            INGESTION_LOCK.release()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to ingest")
        if not paths:
            return
        for raw_path in paths:
            file_path = Path(raw_path)
            dialog = MetadataDialog(file_path, self)
            if dialog.exec() != dialog.DialogCode.Accepted:
                continue
            try:
                success, message, _ = process_file(file_path, get_config(), metadata=dialog.metadata(), delete_source=False)
                if not success:
                    QMessageBox.warning(self, "Add Files", message)
                log_ui("INFO", "Qt add file processed", path=str(file_path), success=success, message=message)
            except Exception as exc:
                QMessageBox.critical(self, "Add Files Error", str(exc))
                log_ui("ERROR", "Qt add file failed", path=str(file_path), error=str(exc))
        self.refresh_vault()

    def refresh_vault(self):
        self.vault_view.refresh()
        self.update_stats()

    def refresh_ui(self):
        current_hash = self.inspector.item_hash
        self.vault_view.refresh()
        if current_hash:
            conn = init_database()
            exists = conn.cursor().execute("SELECT 1 FROM items WHERE hash = ?", (current_hash,)).fetchone()
            conn.close()
            if exists:
                self.inspector.load_item(current_hash)
            else:
                self.inspector.clear()
        self.update_stats()
        self.status.showMessage("UI refreshed.")
        log_ui("INFO", "Qt UI refreshed", hash=current_hash or "")

    def tag_selected_image(self):
        if self.tag_worker and self.tag_worker.isRunning():
            QMessageBox.information(self, "Tagging", "Tagging is already running.")
            return
        if not self.inspector.item_hash or not self.inspector.asset_path or not self.inspector.asset_path.exists():
            QMessageBox.information(self, "Tagging", "No local asset is selected.")
            return
        self.tag_worker = TagWorker(self.inspector.asset_path, self.inspector.item_hash, get_config())
        self.tag_worker.completed.connect(self.tagging_done)
        self.tag_worker.failed.connect(self.tagging_failed)
        self.inspector.set_tagging_busy(True)
        self.status.showMessage("Tagging selected media...")
        self.tag_worker.start()
        log_ui("INFO", "Qt tagging command started", hash=self.inspector.item_hash, path=str(self.inspector.asset_path))

    def tagging_done(self, result):
        self.inspector.set_tagging_busy(False)
        if result.status == "ok":
            self.rebuild_note(result.item_hash)
            self.refresh_ui()
            self.status.showMessage(f"Tagging complete: {result.item_hash}")
        else:
            self.refresh_ui()
            QMessageBox.warning(self, "Tagging", result.error or f"Tagging ended with status: {result.status}")
            self.status.showMessage(f"Tagging ended with status: {result.status}")
        log_ui("INFO", "Qt tagging command finished", hash=result.item_hash, status=result.status, error=result.error)

    def tagging_failed(self, message: str):
        self.inspector.set_tagging_busy(False)
        QMessageBox.critical(self, "Tagging Error", message)
        self.status.showMessage("Tagging failed.")
        log_ui("ERROR", "Qt tagging command failed", error=message)

    def rebuild_note(self, item_hash: str):
        conn = init_database()
        try:
            md_content = generate_markdown(conn, item_hash)
        finally:
            conn.close()
        if md_content:
            note_path = note_path_for(item_hash)
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(md_content, encoding="utf-8")

    def reload_config(self):
        self.config = get_config()
        self.prefixes = self.config.get("ui", {}).get("prefixes", self.prefixes)
        QMessageBox.information(self, "Settings", "Settings saved.")
