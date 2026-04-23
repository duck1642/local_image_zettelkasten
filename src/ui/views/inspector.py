from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpacerItem, QStackedLayout, QTextEdit, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from md_generator import generate_markdown
from ui.thumbnail_cache import asset_path_for, preview_pixmap
from ui.video_widgets import VideoPlayerWidget
from utils import NOTES_DIR


class InspectorView(QFrame):
    saved = Signal()
    wide_requested = Signal()
    fullscreen_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Inspector")
        self.item_hash = ""
        self.mime_type = ""
        self.asset_path = None
        self.focus_mode = "normal"

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        self.preview.setMaximumHeight(240)
        self.video_preview = VideoPlayerWidget()
        self.video_preview.set_view_callbacks(self.request_wide, self.request_fullscreen, lambda: self.focus_mode)
        self.video_preview.setMinimumHeight(220)
        self.video_preview.setMaximumHeight(260)
        self.media_widget = QWidget()
        self.media_stack = QStackedLayout(self.media_widget)
        self.media_stack.setContentsMargins(0, 0, 0, 0)
        self.media_stack.addWidget(self.preview)
        self.media_stack.addWidget(self.video_preview)

        self.hash_label = QLabel("No selection")
        self.hash_label.setWordWrap(True)
        self.hash_label.setObjectName("MutedLabel")

        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Source URL")
        self.topics_input = QTextEdit()
        self.topics_input.setPlaceholderText("Topics")
        self.topics_input.setMaximumHeight(90)
        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setObjectName("MutedLabel")

        self.save_button = QPushButton("Save Changes")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_metadata)
        layout = QVBoxLayout(self)
        self.root_layout = layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(self.media_widget)
        layout.addWidget(self.hash_label)
        layout.addWidget(self.artist_input)
        layout.addWidget(self.url_input)
        layout.addWidget(self.topics_input)
        layout.addWidget(self.platform_label)
        layout.addWidget(self.save_button)
        self.bottom_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        layout.addItem(self.bottom_spacer)

    def clear(self):
        self.item_hash = ""
        self.asset_path = None
        self.mime_type = ""
        self.video_preview.stop()
        self.preview.clear()
        self.media_stack.setCurrentWidget(self.preview)
        self.hash_label.setText("No selection")
        self.artist_input.clear()
        self.url_input.clear()
        self.topics_input.clear()
        self.platform_label.setText("Platform: Unknown")

    def load_item(self, item_hash: str):
        self.item_hash = item_hash
        conn = init_database()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file_extension, mime_type, source_url, platform, source_artist, topics FROM items WHERE hash = ?",
            (item_hash,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            self.clear()
            return

        extension, mime_type, source_url, platform, artist, topics = row
        self.mime_type = mime_type or ""
        asset_path = asset_path_for(item_hash, extension, mime_type)
        self.asset_path = asset_path
        if self.mime_type.startswith("video/") and asset_path.exists():
            self.video_preview.load(asset_path)
            self.media_stack.setCurrentWidget(self.video_preview)
        else:
            self.video_preview.stop()
            pixmap = preview_pixmap(asset_path, item_hash, mime_type)
            self.preview.setPixmap(pixmap)
            self.media_stack.setCurrentWidget(self.preview)
        self.hash_label.setText(item_hash)
        self.artist_input.setText(artist or "")
        self.url_input.setText(source_url or "")
        self.topics_input.setPlainText(topics or "")
        self.platform_label.setText(f"Platform: {platform or 'Unknown'}")
        log_ui("INFO", "Qt inspector loaded", hash=item_hash, asset_path=str(asset_path), exists=asset_path.exists())

    def request_wide(self):
        if not self.asset_path or not self.asset_path.exists():
            return
        self.wide_requested.emit()

    def request_fullscreen(self):
        if not self.asset_path or not self.asset_path.exists():
            return
        self.fullscreen_requested.emit()

    def set_focus_mode(self, mode: str):
        self.focus_mode = mode
        focused = mode != "normal"
        fullscreen = mode == "fullscreen"
        self.root_layout.setContentsMargins(0 if fullscreen else 18, 0 if fullscreen else 18, 0 if fullscreen else 18, 0 if fullscreen else 18)
        self.root_layout.setSpacing(0 if fullscreen else 12)
        self.bottom_spacer.changeSize(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed if focused else QSizePolicy.Policy.Expanding)
        self.media_widget.setMinimumHeight(0 if fullscreen else 520 if focused else 260)
        self.media_widget.setMaximumHeight(16777215 if focused else 300)
        self.video_preview.setMinimumHeight(0 if fullscreen else 520 if focused else 220)
        self.video_preview.setMaximumHeight(16777215 if focused else 260)
        self.preview.setMinimumHeight(520 if focused else 220)
        self.preview.setMaximumHeight(16777215 if focused else 240)
        self.media_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding if focused else QSizePolicy.Policy.Fixed)
        for widget in [
            self.hash_label,
            self.artist_input,
            self.url_input,
            self.topics_input,
            self.platform_label,
            self.save_button,
        ]:
            widget.setVisible(not focused)
        self.video_preview.update_view_buttons()

    def has_active_video(self) -> bool:
        return self.media_stack.currentWidget() is self.video_preview and self.asset_path is not None

    def save_metadata(self):
        if not self.item_hash:
            return
        artist = self.artist_input.text().strip()
        source_url = self.url_input.text().strip()
        topics = self.topics_input.toPlainText().strip()
        conn = init_database()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE items SET source_artist = ?, source_url = ?, topics = ? WHERE hash = ?",
            (artist, source_url, topics, self.item_hash),
        )
        conn.commit()
        md_content = generate_markdown(conn, self.item_hash)
        if md_content:
            NOTES_DIR.mkdir(parents=True, exist_ok=True)
            (NOTES_DIR / f"{self.item_hash}.md").write_text(md_content, encoding="utf-8")
        conn.close()
        log_ui("INFO", "Qt inspector saved", hash=self.item_hash)
        self.saved.emit()
