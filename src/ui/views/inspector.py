from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpacerItem, QStackedLayout, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from md_generator import generate_markdown
from tagging import load_tag_cache
from ui.flow_layout import FlowLayout
from ui.thumbnail_cache import asset_path_for, preview_pixmap
from ui.video_widgets import VideoPlayerWidget
from utils import NOTES_DIR


class InspectorView(QFrame):
    saved = Signal()
    tag_requested = Signal()
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
        self.topic_values = []

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
        self.image_controls.setObjectName("TransparentContainer")
        self.image_controls.setLayout(image_controls_layout)
        self.image_controls.setVisible(False)

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
        self.group_nav.setObjectName("TransparentContainer")
        self.group_nav.setLayout(group_layout)

        self.artist_label = QLabel("Artist")
        self.artist_label.setObjectName("SectionLabel")
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist")
        self.url_label = QLabel("Source URL")
        self.url_label.setObjectName("SectionLabel")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Source URL")

        self.meta_panel = QFrame()
        self.meta_panel.setObjectName("Panel")
        meta_layout = QVBoxLayout(self.meta_panel)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(8)
        meta_layout.addWidget(self.artist_label)
        meta_layout.addWidget(self.artist_input)
        meta_layout.addWidget(self.url_label)
        meta_layout.addWidget(self.url_input)

        self.hash_value = QLineEdit()
        self.hash_value.setObjectName("InfoField")
        self.hash_value.setReadOnly(True)
        self.hash_value.setText("No selection")
        self.platform_value = QLabel("Unknown")
        self.platform_value.setObjectName("InfoValue")
        self.copy_hash_button = QPushButton("Copy")
        self.copy_hash_button.setObjectName("TransportButton")
        self.copy_hash_button.setFixedHeight(28)
        self.copy_hash_button.setFixedWidth(42)
        self.copy_hash_button.setToolTip("Copy hash")
        self.copy_hash_button.clicked.connect(self.copy_hash)
        self.summary_panel = QFrame()
        self.summary_panel.setObjectName("Panel")
        summary_layout = QHBoxLayout(self.summary_panel)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(12)
        summary_layout.addWidget(_info_block("Platform", self.platform_value))
        summary_layout.addWidget(_info_block("Hash", self.hash_value), 1)
        summary_layout.addWidget(self.copy_hash_button)

        self.topics_panel = QFrame()
        self.topics_panel.setObjectName("Panel")
        topics_layout = QVBoxLayout(self.topics_panel)
        topics_layout.setContentsMargins(10, 10, 10, 10)
        topics_layout.setSpacing(8)
        self.topics_title = QLabel("My Topics")
        self.topics_title.setObjectName("SectionLabel")
        self.topics_wrap = QWidget()
        self.topics_wrap.setObjectName("TransparentContainer")
        self.topics_flow = FlowLayout(self.topics_wrap, spacing=6)
        self.topics_wrap.setLayout(self.topics_flow)
        self.topics_empty = QLabel("No topics")
        self.topics_empty.setObjectName("MutedLabel")
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Add topic and press Enter")
        self.topic_input.returnPressed.connect(self.add_topic_from_input)
        self.topic_add_button = QPushButton("Add")
        self.topic_add_button.setObjectName("TransportButton")
        self.topic_add_button.setFixedHeight(30)
        self.topic_add_button.clicked.connect(self.add_topic_from_input)
        topic_input_row = QHBoxLayout()
        topic_input_row.setContentsMargins(0, 0, 0, 0)
        topic_input_row.setSpacing(6)
        topic_input_row.addWidget(self.topic_input, 1)
        topic_input_row.addWidget(self.topic_add_button)
        topics_layout.addWidget(self.topics_title)
        topics_layout.addWidget(self.topics_wrap)
        topics_layout.addWidget(self.topics_empty)
        topics_layout.addLayout(topic_input_row)

        self.wd_panel = QFrame()
        self.wd_panel.setObjectName("Panel")
        wd_layout = QVBoxLayout(self.wd_panel)
        wd_layout.setContentsMargins(10, 10, 10, 10)
        wd_layout.setSpacing(8)
        self.wd_title = QLabel("WD Suggestions")
        self.wd_title.setObjectName("SectionLabel")
        self.rating_title = QLabel("Rating")
        self.rating_title.setObjectName("MutedLabel")
        self.rating_wrap = QWidget()
        self.rating_wrap.setObjectName("TransparentContainer")
        self.rating_flow = FlowLayout(self.rating_wrap, spacing=6)
        self.rating_wrap.setLayout(self.rating_flow)
        self.rating_empty = QLabel("No rating")
        self.rating_empty.setObjectName("MutedLabel")
        self.character_title = QLabel("Character Tags")
        self.character_title.setObjectName("MutedLabel")
        self.character_wrap = QWidget()
        self.character_wrap.setObjectName("TransparentContainer")
        self.character_flow = FlowLayout(self.character_wrap, spacing=6)
        self.character_wrap.setLayout(self.character_flow)
        self.character_empty = QLabel("No character tags")
        self.character_empty.setObjectName("MutedLabel")
        self.tags_title = QLabel("Visual Tags")
        self.tags_title.setObjectName("MutedLabel")
        self.tags_wrap = QWidget()
        self.tags_wrap.setObjectName("TransparentContainer")
        self.tags_flow = FlowLayout(self.tags_wrap, spacing=6)
        self.tags_wrap.setLayout(self.tags_flow)
        self.tags_empty = QLabel("No tags")
        self.tags_empty.setObjectName("MutedLabel")
        wd_layout.addWidget(self.wd_title)
        wd_layout.addWidget(self.rating_title)
        wd_layout.addWidget(self.rating_wrap)
        wd_layout.addWidget(self.rating_empty)
        wd_layout.addWidget(self.character_title)
        wd_layout.addWidget(self.character_wrap)
        wd_layout.addWidget(self.character_empty)
        wd_layout.addWidget(self.tags_title)
        wd_layout.addWidget(self.tags_wrap)
        wd_layout.addWidget(self.tags_empty)

        self.tag_button = QPushButton("Tag Image")
        self.tag_button.clicked.connect(self.tag_requested.emit)
        self.tag_button.setEnabled(False)
        self.save_button = QPushButton("Save Changes")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_metadata)
        self.actions = QWidget()
        self.actions.setObjectName("TransparentContainer")
        actions_layout = QHBoxLayout(self.actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.tag_button)
        actions_layout.addWidget(self.save_button)

        self.group_nav.setVisible(False)
        layout = QVBoxLayout(self)
        self.root_layout = layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(self.media_widget)
        layout.addWidget(self.image_controls)
        layout.addWidget(self.group_nav)
        layout.addWidget(self.meta_panel)
        layout.addWidget(self.summary_panel)
        layout.addWidget(self.topics_panel)
        layout.addWidget(self.wd_panel)
        layout.addWidget(self.actions)
        self.bottom_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        layout.addItem(self.bottom_spacer)
        self.clear()

    def clear(self):
        self.item_hash = ""
        self.asset_path = None
        self.preview_source_path = None
        self.mime_type = ""
        self.group_rows = []
        self.group_index = 0
        self.topic_values = []
        self.video_preview.stop()
        self.preview.clear()
        self.media_stack.setCurrentWidget(self.preview)
        self.image_controls.setVisible(False)
        self.hash_value.setText("No selection")
        self.platform_value.setText("Unknown")
        self.copy_hash_button.setEnabled(False)
        self.group_counter.setText("")
        self.group_nav.setVisible(False)
        self.artist_input.clear()
        self.url_input.clear()
        self.topic_input.clear()
        self.set_topics([])
        self.populate_flow(self.rating_flow, [], "rating")
        self.populate_flow(self.character_flow, [], "suggest")
        self.populate_flow(self.tags_flow, [], "suggest")
        self.refresh_empty_states()
        self.tag_button.setEnabled(False)
        self.tag_button.setText("Tag Image")

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
        self.hash_value.setText(item_hash)
        self.platform_value.setText(platform or "Unknown")
        self.copy_hash_button.setEnabled(True)
        self.artist_input.setText(artist or "")
        self.url_input.setText(source_url or "")
        self.topic_input.clear()
        self.set_topics(_parse_topics(topics))
        self.load_tag_suggestions(item_hash)
        self.update_tag_button()
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
        self.root_layout.setContentsMargins(
            0 if fullscreen else 18,
            0 if fullscreen else 18,
            0 if fullscreen else 18,
            0 if fullscreen else 18,
        )
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
            self.group_nav,
            self.meta_panel,
            self.summary_panel,
            self.topics_panel,
            self.wd_panel,
            self.actions,
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

    def copy_hash(self):
        if not self.item_hash:
            return
        QApplication.clipboard().setText(self.item_hash)
        log_ui("INFO", "Qt inspector copied hash", hash=self.item_hash)

    def set_topics(self, topics: list[str]):
        self.topic_values = []
        self.clear_flow(self.topics_flow)
        for topic in topics:
            self.add_topic_chip(topic)
        self.refresh_empty_states()

    def add_topic_from_input(self):
        self.add_topic_chip(self.topic_input.text().strip())
        self.topic_input.clear()

    def add_topic_chip(self, topic: str):
        normalized = _normalize_topic(topic)
        if not normalized or normalized in self.topic_values:
            self.refresh_empty_states()
            return
        self.topic_values.append(normalized)
        button = QPushButton(normalized)
        button.setObjectName("EditableChip")
        button.setToolTip("Click to remove")
        button.clicked.connect(lambda checked=False, value=normalized, widget=button: self.remove_topic_chip(value, widget))
        self.topics_flow.addWidget(button)
        self.refresh_empty_states()

    def remove_topic_chip(self, topic: str, widget: QWidget):
        if topic in self.topic_values:
            self.topic_values.remove(topic)
        widget.setParent(None)
        widget.deleteLater()
        self.refresh_empty_states()

    def update_tag_button(self):
        enabled = bool(self.item_hash and self.asset_path and self.asset_path.exists() and not self.mime_type.startswith("video/"))
        self.tag_button.setEnabled(enabled)

    def set_tagging_busy(self, busy: bool):
        self.tag_button.setEnabled(not busy and bool(self.item_hash and self.asset_path and self.asset_path.exists() and not self.mime_type.startswith("video/")))
        self.tag_button.setText("Tagging..." if busy else "Tag Image")

    def load_tag_suggestions(self, item_hash: str):
        data = load_tag_cache(item_hash)
        if not data or data.get("status") != "ok":
            self.populate_flow(self.rating_flow, [], "rating")
            self.populate_flow(self.character_flow, [], "suggest")
            self.populate_flow(self.tags_flow, [], "suggest")
            self.refresh_empty_states()
            return
        rating = data.get("rating") or {}
        characters = data.get("character_tags") or []
        tags = data.get("tags") or []
        rating_chip = []
        if rating:
            rating_chip = [{
                "text": str(rating.get("label") or rating.get("display_name") or rating.get("name") or ""),
                "tooltip": _score_tooltip(rating),
            }]
        self.populate_flow(self.rating_flow, rating_chip, "rating")
        self.populate_flow(self.character_flow, [{"text": _display_tag(tag), "tooltip": _score_tooltip(tag)} for tag in characters[:24]], "suggest")
        self.populate_flow(self.tags_flow, [{"text": _display_tag(tag), "tooltip": _score_tooltip(tag)} for tag in tags[:36]], "suggest")
        self.refresh_empty_states()

    def populate_flow(self, flow: FlowLayout, items: list[dict], variant: str):
        self.clear_flow(flow)
        for item in items:
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            button = QPushButton(text)
            button.setObjectName("RatingChip" if variant == "rating" else "SuggestionChip")
            button.setToolTip(item.get("tooltip") or text)
            button.setCursor(Qt.CursorShape.ArrowCursor)
            flow.addWidget(button)

    def clear_flow(self, flow: FlowLayout):
        while flow.count():
            item = flow.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def refresh_empty_states(self):
        self.topics_empty.setVisible(not self.topic_values)
        self.rating_empty.setVisible(self.rating_flow.count() == 0)
        self.character_empty.setVisible(self.character_flow.count() == 0)
        self.tags_empty.setVisible(self.tags_flow.count() == 0)

    def has_active_video(self) -> bool:
        return self.media_stack.currentWidget() is self.video_preview and self.asset_path is not None

    def save_metadata(self):
        if not self.item_hash:
            return
        artist = self.artist_input.text().strip()
        source_url = self.url_input.text().strip()
        topics = "\n".join(self.topic_values)
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
        log_ui("INFO", "Qt inspector saved", hash=self.item_hash, group_count=len(target_hashes), topic_count=len(self.topic_values))
        self.saved.emit()


def _info_block(label_text: str, value_widget: QWidget) -> QWidget:
    widget = QWidget()
    widget.setObjectName("TransparentContainer")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    label = QLabel(label_text)
    label.setObjectName("SectionLabel")
    layout.addWidget(label)
    layout.addWidget(value_widget)
    return widget


def _normalize_topic(topic: str) -> str:
    return " ".join(str(topic).replace(",", " ").split()).strip()


def _parse_topics(topics) -> list[str]:
    if not topics:
        return []
    if isinstance(topics, list):
        return [_normalize_topic(topic) for topic in topics if _normalize_topic(topic)]
    values = []
    for raw in str(topics).replace("\r", "\n").replace(",", "\n").split("\n"):
        normalized = _normalize_topic(raw)
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _display_tag(tag: dict) -> str:
    return str(tag.get("display_name") or tag.get("name") or "").strip()


def _score_tooltip(tag: dict) -> str:
    score = tag.get("score")
    if isinstance(score, int | float):
        return f"{_display_tag(tag) or tag.get('label', '')} ({float(score):.3f})"
    return _display_tag(tag) or str(tag.get("label") or "")
