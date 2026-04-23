from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QStatusBar, QVBoxLayout, QWidget

from core import main as run_ingestion
from db.sqlite_operator import init_database
from logs.logger import log_ui
from processor import process_file
from ui.views.ingestion import IngestionView
from ui.views.inspector import InspectorView
from ui.views.modals import MetadataDialog
from ui.views.review import ReviewView
from ui.views.settings import SettingsView
from ui.views.vault import VaultView
from utils import QUEUES_DIR, get_config


class IngestionWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def run(self):
        try:
            run_ingestion()
            self.completed.emit("Ingestion pipeline complete.")
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LIZ - Management Center")
        self.config = get_config()
        self.prefixes = self.config.get("ui", {}).get("prefixes", {"command": ">", "platform": "@", "artist": "a:", "tag": "#"})
        self.worker = None
        self.video_mode = "normal"

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(f"Search (use {self.prefixes['artist']} for artist, {self.prefixes['command']} for cmd)...")
        self.search_input.returnPressed.connect(self.handle_search)
        self.add_button = QPushButton("Add Files")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.clicked.connect(self.add_files)
        self.vault_count_label = QLabel("Showing 0 items")
        self.vault_count_label.setObjectName("MutedLabel")

        self.nav_buttons = []
        nav_layout = QVBoxLayout()
        for label, index in [("Vault", 0), ("Review", 1), ("Ingestion", 2), ("Settings", 3)]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self.show_view(i))
            self.nav_buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)

        self.vault_view = VaultView()
        self.inspector = InspectorView()
        self.review_view = ReviewView()
        self.ingestion_view = IngestionView()
        self.settings_view = SettingsView()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.vault_view)
        self.stack.addWidget(self.review_view)
        self.stack.addWidget(self.ingestion_view)
        self.stack.addWidget(self.settings_view)

        self.vault_view.item_selected.connect(self.handle_item_selected)
        self.inspector.saved.connect(self.refresh_vault)
        self.inspector.wide_requested.connect(self.toggle_video_wide)
        self.inspector.fullscreen_requested.connect(self.toggle_video_fullscreen)
        self.review_view.changed.connect(self.refresh_vault)
        self.settings_view.saved.connect(self.reload_config)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.search_input, 1)
        top_layout.addWidget(self.add_button)
        top_layout.addWidget(self.vault_count_label)
        workspace_layout = QVBoxLayout()
        workspace_layout.addLayout(top_layout)
        workspace_layout.addWidget(self.stack, 1)

        self.nav_widget = QWidget()
        self.nav_widget.setFixedWidth(110)
        self.nav_widget.setLayout(nav_layout)
        self.workspace = QWidget()
        self.workspace.setLayout(workspace_layout)

        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(12, 12, 12, 0)
        root_layout.setSpacing(12)
        root_layout.addWidget(self.nav_widget)
        root_layout.addWidget(self.workspace, 3)
        root_layout.addWidget(self.inspector, 2)
        self.set_video_mode("normal")

        root = QWidget()
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
        self.video_mode = mode
        focused = mode != "normal"
        self.nav_widget.setVisible(not focused)
        self.workspace.setVisible(not focused)
        if hasattr(self, "status"):
            self.status.setVisible(mode != "fullscreen")
        if focused:
            self.inspector.setMinimumWidth(640)
            self.inspector.setMaximumWidth(16777215)
        else:
            self.inspector.setMinimumWidth(520)
            self.inspector.setMaximumWidth(520)
        if self.centralWidget() and self.centralWidget().layout():
            self.centralWidget().layout().setContentsMargins(0 if mode == "fullscreen" else 12, 0 if mode == "fullscreen" else 12, 0 if mode == "fullscreen" else 12, 0)
            self.centralWidget().layout().setSpacing(0 if mode == "fullscreen" else 12)
        self.inspector.set_focus_mode(mode)
        if mode == "fullscreen":
            self.showFullScreen()
        elif self.isFullScreen():
            self.showNormal()
        log_ui("INFO", "Qt video layout mode changed", mode=mode)

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
        super().keyPressEvent(event)

    def show_view(self, index: int):
        self.stack.setCurrentIndex(index)
        self.set_nav_checked(index)
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
            self.stack.setCurrentIndex(0)
            self.set_nav_checked(0)
            self.vault_view.filter_by("topics", text[len(self.prefixes["tag"]):].strip())
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
        self.worker = IngestionWorker()
        self.worker.completed.connect(self.ingestion_done)
        self.worker.failed.connect(self.ingestion_failed)
        self.worker.start()
        self.show_view(2)
        self.status.showMessage("Ingestion running...")
        log_ui("INFO", "Qt ingestion command started")

    def ingestion_done(self, message: str):
        QMessageBox.information(self, "Ingestion", message)
        self.refresh_vault()

    def ingestion_failed(self, message: str):
        QMessageBox.critical(self, "Ingestion Error", message)
        log_ui("ERROR", "Qt ingestion command failed", error=message)

    def retry_failed_links(self):
        failed_file = QUEUES_DIR / "failed_links.md"
        pending_file = QUEUES_DIR / "normal_pending_links.md"
        if not failed_file.exists():
            QMessageBox.information(self, "Retry", "No failed links file found.")
            return
        urls = []
        for line in failed_file.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "|" in line:
                line = line.split("|", 1)[0]
            if "]" in line:
                line = line.split("]", 1)[1]
            url = line.strip()
            if url:
                urls.append(url)
        if not urls:
            QMessageBox.information(self, "Retry", "No failed URLs found.")
            return
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pending_file, "a", encoding="utf-8") as handle:
            for url in urls:
                handle.write(f"{url}\n")
        failed_file.write_text("# LIZ Failed Links Log\n", encoding="utf-8")
        QMessageBox.information(self, "Retry", f"Queued {len(urls)} failed URLs.")
        log_ui("INFO", "Qt retry queued", count=len(urls))

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

    def reload_config(self):
        self.config = get_config()
        self.prefixes = self.config.get("ui", {}).get("prefixes", self.prefixes)
        QMessageBox.information(self, "Settings", "Settings saved.")
