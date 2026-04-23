from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpacerItem, QStackedLayout, QTextEdit, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from md_generator import generate_markdown
from PySide6.QtGui import QPixmap

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
        self.preview_source_path = None
        self.focus_mode = "normal"
        self.group_rows = []
        self.group_index = 0

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
        self.image_wide_button = QPushButton("W")
        self.image_wide_button.setObjectName("TransportButton")
        self.image_wide_button.setFixedSize(30, 30)
        self.image_wide_button.setToolTip("Wide view")
        self.image_wide_button.clicked.connect(self.request_wide)
        self.image_fullscreen_button = QPushButton("F")
        self.image_fullscreen_button.setObjectName("TransportButton")
        self.image_fullscreen_button.setFixedSize(30, 30)
        self.image_fullscreen_button.setToolTip("Fullscreen")
        self.image_fullscreen_button.clicked.connect(self.request_fullscreen)
        image_controls_layout = QHBoxLayout()
        image_controls_layout.setContentsMargins(0, 0, 0, 0)
        image_controls_layout.addStretch(1)
        image_controls_layout.addWidget(self.image_wide_button)
        image_controls_layout.addWidget(self.image_fullscreen_button)
        self.image_controls = QWidget()
        self.image_controls.setLayout(image_controls_layout)
        self.image_controls.setVisible(False)

        self.hash_label = QLabel("No selection")
        self.hash_label.setWordWrap(True)
        self.hash_label.setObjectName("MutedLabel")
        self.group_counter = QLabel("")
        self.group_counter.setObjectName("MutedLabel")
        self.group_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_button = QPushButton("<")
        self.prev_button.clicked.connect(self.previous_group_item)
        self.next_button = QPushButton(">")
        self.next_button.clicked.connect(self.next_group_item)
        group_layout = QHBoxLayout()
        group_layout.addWidget(self.prev_button)
        group_layout.addWidget(self.group_counter, 1)
        group_layout.addWidget(self.next_button)
        self.group_nav = QWidget()
        self.group_nav.setLayout(group_layout)

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
        self.group_nav.setVisible(False)
        layout = QVBoxLayout(self)
        self.root_layout = layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(self.media_widget)
        layout.addWidget(self.image_controls)
        layout.addWidget(self.group_nav)
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
        self.preview_source_path = None
        self.mime_type = ""
        self.group_rows = []
        self.group_index = 0
        self.video_preview.stop()
        self.preview.clear()
        self.media_stack.setCurrentWidget(self.preview)
        self.image_controls.setVisible(False)
        self.hash_label.setText("No selection")
        self.group_counter.setText("")
        self.group_nav.setVisible(False)
        self.artist_input.clear()
        self.url_input.clear()
        self.topics_input.clear()
        self.platform_label.setText("Platform: Unknown")

    def load_item(self, item_hash: str):
        conn = init_database()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hash, file_extension, mime_type, source_url, platform, source_artist, topics FROM items WHERE hash = ?",
            (item_hash,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            self.clear()
            return
        source_url = (row[3] or "").strip()
        if source_url:
            cursor.execute(
                """
                SELECT hash, file_extension, mime_type, source_url, platform, source_artist, topics
                FROM items
                WHERE source_url = ?
                ORDER BY date_added ASC
                """,
                (source_url,),
            )
            self.group_rows = cursor.fetchall()
        else:
            self.group_rows = [row]
        conn.close()
        hashes = [str(group_row[0]) for group_row in self.group_rows]
        self.group_index = hashes.index(item_hash) if item_hash in hashes else 0
        self.load_group_index()

    def load_group_index(self):
        if not self.group_rows:
            self.clear()
            return

        item_hash, extension, mime_type, source_url, platform, artist, topics = self.group_rows[self.group_index]
        item_hash = str(item_hash)
        self.item_hash = item_hash
        self.mime_type = mime_type or ""
        asset_path = asset_path_for(item_hash, extension, mime_type)
        self.asset_path = asset_path
        if self.mime_type.startswith("video/") and asset_path.exists():
            self.preview_source_path = None
            self.video_preview.load(asset_path)
            self.media_stack.setCurrentWidget(self.video_preview)
            self.image_controls.setVisible(False)
        else:
            self.video_preview.stop()
            self.preview_source_path = asset_path if asset_path.exists() else None
            self.update_image_preview()
            self.media_stack.setCurrentWidget(self.preview)
            self.update_image_view_buttons()
        self.hash_label.setText(item_hash)
        self.artist_input.setText(artist or "")
        self.url_input.setText(source_url or "")
        self.topics_input.setPlainText(topics or "")
        self.platform_label.setText(f"Platform: {platform or 'Unknown'}")
        grouped = len(self.group_rows) > 1
        self.group_nav.setVisible(grouped)
        self.group_counter.setText(f"{self.group_index + 1} / {len(self.group_rows)}" if grouped else "")
        self.prev_button.setEnabled(grouped)
        self.next_button.setEnabled(grouped)
        log_ui("INFO", "Qt inspector loaded", hash=item_hash, asset_path=str(asset_path), exists=asset_path.exists())

    def previous_group_item(self):
        if len(self.group_rows) <= 1:
            return
        self.group_index = (self.group_index - 1) % len(self.group_rows)
        self.load_group_index()

    def next_group_item(self):
        if len(self.group_rows) <= 1:
            return
        self.group_index = (self.group_index + 1) % len(self.group_rows)
        self.load_group_index()

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
            self.image_controls,
            self.hash_label,
            self.group_nav,
            self.artist_input,
            self.url_input,
            self.topics_input,
            self.platform_label,
            self.save_button,
        ]:
            widget.setVisible(not focused)
        self.video_preview.update_view_buttons()
        self.update_image_view_buttons()
        self.update_image_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_preview()

    def update_image_preview(self):
        if self.media_stack.currentWidget() is not self.preview:
            return
        if self.preview_source_path and self.preview_source_path.exists():
            pixmap = QPixmap(str(self.preview_source_path))
            if not pixmap.isNull():
                target_size = self.media_widget.size()
                if target_size.width() > 0 and target_size.height() > 0:
                    pixmap = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview.setPixmap(pixmap)
                return
        if self.asset_path:
            self.preview.setPixmap(preview_pixmap(self.asset_path, self.item_hash, self.mime_type))

    def update_image_view_buttons(self):
        image_active = self.media_stack.currentWidget() is self.preview and self.asset_path is not None and self.asset_path.exists()
        self.image_controls.setVisible(image_active and self.focus_mode == "normal")
        self.image_wide_button.setText("X" if self.focus_mode == "wide" else "W")
        self.image_fullscreen_button.setText("X" if self.focus_mode == "fullscreen" else "F")

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
        target_hashes = [str(row[0]) for row in self.group_rows] if len(self.group_rows) > 1 else [self.item_hash]
        for target_hash in target_hashes:
            cursor.execute(
                "UPDATE items SET source_artist = ?, source_url = ?, topics = ? WHERE hash = ?",
                (artist, source_url, topics, target_hash),
            )
        conn.commit()
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        for target_hash in target_hashes:
            md_content = generate_markdown(conn, target_hash)
            if md_content:
                (NOTES_DIR / f"{target_hash}.md").write_text(md_content, encoding="utf-8")
        conn.close()
        log_ui("INFO", "Qt inspector saved", hash=self.item_hash, group_count=len(target_hashes))
        self.saved.emit()
