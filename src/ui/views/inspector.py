import re

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpacerItem, QStackedLayout, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from md_generator import generate_markdown, load_note_topics
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
        self.preview.setMinimumSize(0, 0)
        self.preview.setMinimumHeight(220)
        self.preview.setMaximumHeight(240)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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

        self.group_counter = QLabel("")
        self.group_counter.setObjectName("MutedLabel")
        self.group_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_button = QPushButton("<")
        self.prev_button.setObjectName("TransportButton")
        self.prev_button.setFixedSize(34, 34)
        self.prev_button.clicked.connect(self.previous_group_item)
        self.next_button = QPushButton(">")
        self.next_button.setObjectName("TransportButton")
        self.next_button.setFixedSize(34, 34)
        self.next_button.clicked.connect(self.next_group_item)
        self.group_counter.setMinimumWidth(86)
        self.media_controls = QWidget()
        self.media_controls.setObjectName("TransparentContainer")
        self.media_controls.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        media_controls_layout = QHBoxLayout(self.media_controls)
        media_controls_layout.setContentsMargins(0, 0, 0, 0)
        media_controls_layout.setSpacing(8)
        media_controls_layout.addWidget(self.prev_button)
        media_controls_layout.addWidget(self.group_counter)
        media_controls_layout.addWidget(self.next_button)
        media_controls_layout.addStretch(1)
        media_controls_layout.addWidget(self.image_wide_button)
        media_controls_layout.addWidget(self.image_fullscreen_button)

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
        self.hash_value.setMinimumHeight(30)
        self.hash_value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.hash_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.hash_value.setCursorPosition(0)
        self.platform_value = QLabel("Unknown")
        self.platform_value.setObjectName("InfoValue")
        self.platform_value.setMinimumHeight(30)
        self.platform_value.setMinimumWidth(52)
        self.platform_value.setMaximumWidth(72)
        self.platform_title = QLabel("Platform")
        self.platform_title.setObjectName("SectionLabel")
        self.hash_title = QLabel("Hash")
        self.hash_title.setObjectName("SectionLabel")
        self.copy_hash_button = QPushButton("Copy")
        self.copy_hash_button.setObjectName("TransportButton")
        self.copy_hash_button.setFixedHeight(30)
        self.copy_hash_button.setFixedWidth(42)
        self.copy_hash_button.setToolTip("Copy hash")
        self.copy_hash_button.clicked.connect(self.copy_hash)
        self.summary_panel = QFrame()
        self.summary_panel.setObjectName("Panel")
        summary_layout = QGridLayout(self.summary_panel)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setHorizontalSpacing(10)
        summary_layout.setVerticalSpacing(4)
        summary_layout.addWidget(self.platform_title, 0, 0)
        summary_layout.addWidget(self.hash_title, 0, 1)
        summary_layout.addWidget(self.platform_value, 1, 0)
        summary_layout.addWidget(self.hash_value, 1, 1)
        summary_layout.addWidget(self.copy_hash_button, 1, 2)
        summary_layout.setColumnMinimumWidth(0, 52)
        summary_layout.setColumnStretch(1, 1)

        self.topics_panel = QFrame()
        self.topics_panel.setObjectName("Panel")
        topics_layout = QVBoxLayout(self.topics_panel)
        topics_layout.setContentsMargins(10, 10, 10, 10)
        topics_layout.setSpacing(8)
        self.topics_title = QLabel("My Topics")
        self.topics_title.setObjectName("SectionLabel")
        self.topics_wrap = QWidget()
        self.topics_wrap.setObjectName("TopicsWrap")
        self.topics_wrap.setProperty("role", "TransparentContainer")
        self.topics_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.topics_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.topics_flow = FlowLayout(self.topics_wrap, spacing=6)
        self.topics_wrap.setLayout(self.topics_flow)
        self.topics_empty = QLabel("No topics")
        self.topics_empty.setObjectName("MutedLabel")
        topics_layout.addWidget(self.topics_title)
        topics_layout.addWidget(self.topics_wrap)
        topics_layout.addWidget(self.topics_empty)

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
        self.rating_wrap.setObjectName("RatingWrap")
        self.rating_wrap.setProperty("role", "TransparentContainer")
        self.rating_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.rating_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.rating_flow = FlowLayout(self.rating_wrap, spacing=6)
        self.rating_wrap.setLayout(self.rating_flow)
        self.rating_empty = QLabel("No rating")
        self.rating_empty.setObjectName("MutedLabel")
        self.character_title = QLabel("Character Tags")
        self.character_title.setObjectName("MutedLabel")
        self.character_wrap = QWidget()
        self.character_wrap.setObjectName("CharacterWrap")
        self.character_wrap.setProperty("role", "TransparentContainer")
        self.character_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.character_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.character_flow = FlowLayout(self.character_wrap, spacing=6)
        self.character_wrap.setLayout(self.character_flow)
        self.character_empty = QLabel("No character tags")
        self.character_empty.setObjectName("MutedLabel")
        self.tags_title = QLabel("Visual Tags")
        self.tags_title.setObjectName("MutedLabel")
        self.tags_wrap = QWidget()
        self.tags_wrap.setObjectName("TagsWrap")
        self.tags_wrap.setProperty("role", "TransparentContainer")
        self.tags_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.tags_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
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
        self.actions.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        actions_layout = QHBoxLayout(self.actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.tag_button)
        actions_layout.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        self.root_layout = layout
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(self.media_widget)
        layout.addWidget(self.media_controls)
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
        self.hash_value.setText("No selection")
        self.hash_value.setCursorPosition(0)
        self.platform_value.setText("Unknown")
        self.copy_hash_button.setEnabled(False)
        self.group_counter.setText("1 / 1")
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.image_wide_button.setEnabled(False)
        self.image_fullscreen_button.setEnabled(False)
        self.artist_input.clear()
        self.url_input.clear()
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
            "SELECT hash, file_extension, mime_type, source_url, platform, source_artist FROM items WHERE hash = ?",
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
                SELECT hash, file_extension, mime_type, source_url, platform, source_artist
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
        log_ui(
            "INFO",
            "Qt inspector group resolved",
            selected_hash=item_hash,
            source_url=source_url,
            ordered_hashes=hashes,
            group_index=self.group_index,
        )
        self.load_group_index()

    def load_group_index(self):
        if not self.group_rows:
            self.clear()
            return

        item_hash, extension, mime_type, source_url, platform, artist = self.group_rows[self.group_index]
        item_hash = str(item_hash)
        self.item_hash = item_hash
        self.mime_type = mime_type or ""
        self.reset_wd_suggestions()
        asset_path = asset_path_for(item_hash, extension, mime_type)
        self.asset_path = asset_path
        if self.mime_type.startswith("video/") and asset_path.exists():
            self.preview_source_path = None
            self.video_preview.load(asset_path)
            self.media_stack.setCurrentWidget(self.video_preview)
        else:
            self.video_preview.stop()
            self.preview_source_path = asset_path if asset_path.exists() else None
            self.media_stack.setCurrentWidget(self.preview)
            self.update_image_preview()
        self.hash_value.setText(item_hash)
        self.hash_value.setCursorPosition(0)
        self.platform_value.setText(platform or "Unknown")
        self.copy_hash_button.setEnabled(True)
        self.artist_input.setText(artist or "")
        self.url_input.setText(source_url or "")
        self.set_topics(load_note_topics(item_hash))
        self.load_tag_suggestions(item_hash)
        self.update_tag_button()
        grouped = len(self.group_rows) > 1
        self.group_counter.setText(f"{self.group_index + 1} / {len(self.group_rows)}" if grouped else "1 / 1")
        self.prev_button.setEnabled(grouped)
        self.next_button.setEnabled(grouped)
        self.update_image_view_buttons()
        self.log_inspector_state("after_load_group_index")
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
        self.media_widget.setMinimumWidth(0)
        self.video_preview.setMinimumHeight(0 if fullscreen else 520 if focused else 220)
        self.video_preview.setMaximumHeight(16777215 if focused else 260)
        self.video_preview.setMinimumWidth(0)
        self.preview.setMinimumHeight(520 if focused else 220)
        self.preview.setMaximumHeight(16777215 if focused else 240)
        self.preview.setMinimumWidth(0)
        self.media_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding if focused else QSizePolicy.Policy.Fixed)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding if focused else QSizePolicy.Policy.Expanding)
        for widget in [
            self.meta_panel,
            self.summary_panel,
            self.topics_panel,
            self.wd_panel,
            self.actions,
        ]:
            widget.setVisible(not focused)
        self.video_preview.update_view_buttons()
        self.update_image_view_buttons()
        self.media_widget.updateGeometry()
        self.preview.updateGeometry()
        self.update_image_preview()
        QTimer.singleShot(0, self.update_image_preview)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_preview()

    def update_image_preview(self):
        if self.media_stack.currentWidget() is not self.preview:
            return
        if self.preview_source_path and self.preview_source_path.exists():
            pixmap = QPixmap(str(self.preview_source_path))
            if not pixmap.isNull():
                target_size = self.preview.size()
                if target_size.width() <= 0 or target_size.height() <= 0:
                    target_size = self.media_widget.size()
                if target_size.width() > 0 and target_size.height() > 0:
                    pixmap = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview.setPixmap(pixmap)
                self.log_preview_geometry("image_preview_updated")
                return
        if self.asset_path:
            self.preview.setPixmap(preview_pixmap(self.asset_path, self.item_hash, self.mime_type))
            self.log_preview_geometry("image_preview_fallback")

    def update_image_view_buttons(self):
        previewable = self.asset_path is not None and self.asset_path.exists()
        image_active = self.media_stack.currentWidget() is self.preview and previewable
        self.media_controls.setVisible(image_active)
        self.image_wide_button.setEnabled(image_active)
        self.image_fullscreen_button.setEnabled(image_active)
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
            normalized = _normalize_topic(topic)
            if not normalized or normalized in self.topic_values:
                continue
            self.topic_values.append(normalized)
            button = QPushButton(_display_topic(normalized))
            button.setObjectName("SuggestionChip")
            button.setToolTip(normalized)
            button.setCursor(Qt.CursorShape.ArrowCursor)
            self.topics_flow.addWidget(button)
        self.refresh_empty_states()

    def update_tag_button(self):
        enabled = bool(self.item_hash and self.asset_path and self.asset_path.exists() and not self.mime_type.startswith("video/"))
        self.tag_button.setEnabled(enabled)

    def set_tagging_busy(self, busy: bool):
        self.tag_button.setEnabled(not busy and bool(self.item_hash and self.asset_path and self.asset_path.exists() and not self.mime_type.startswith("video/")))
        self.tag_button.setText("Tagging..." if busy else "Tag Image")

    def load_tag_suggestions(self, item_hash: str):
        data = load_tag_cache(item_hash)
        log_ui(
            "INFO",
            "Qt tag suggestions load start",
            hash=item_hash,
            cache_status=(data or {}).get("status", "missing"),
            rating_count=1 if (data or {}).get("rating") else 0,
            character_count=len((data or {}).get("character_tags") or []),
            tag_count=len((data or {}).get("tags") or []),
        )
        if not data or data.get("status") != "ok":
            self.populate_flow(self.rating_flow, [], "rating")
            self.populate_flow(self.character_flow, [], "suggest")
            self.populate_flow(self.tags_flow, [], "suggest")
            self.refresh_empty_states()
            self.log_inspector_state("after_load_tag_suggestions_empty")
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
        self.log_inspector_state("after_load_tag_suggestions")

    def reset_wd_suggestions(self):
        self.clear_flow(self.rating_flow)
        self.clear_flow(self.character_flow)
        self.clear_flow(self.tags_flow)
        self.refresh_empty_states()
        self.log_inspector_state("after_reset_wd_suggestions")

    def populate_flow(self, flow: FlowLayout, items: list[dict], variant: str):
        self.log_flow_state("populate_flow_before", flow)
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
        self.refresh_flow_host(flow)
        self.log_flow_state("populate_flow_after", flow)

    def clear_flow(self, flow: FlowLayout):
        self.log_flow_state("clear_flow_before", flow)
        while flow.count():
            item = flow.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.refresh_flow_host(flow)
        self.log_flow_state("clear_flow_after", flow)

    def refresh_flow_host(self, flow: FlowLayout):
        flow.invalidate()
        host = flow.parentWidget()
        if host:
            host.updateGeometry()
            host.adjustSize()
            host.update()
        self.log_flow_state("refresh_flow_host", flow)

    def refresh_empty_states(self):
        topics_empty = not self.topic_values
        rating_empty = self.rating_flow.count() == 0
        character_empty = self.character_flow.count() == 0
        tags_empty = self.tags_flow.count() == 0
        self.topics_empty.setVisible(topics_empty)
        self.topics_wrap.setVisible(not topics_empty)
        self.rating_empty.setVisible(rating_empty)
        self.rating_wrap.setVisible(not rating_empty)
        self.character_empty.setVisible(character_empty)
        self.character_wrap.setVisible(not character_empty)
        self.tags_empty.setVisible(tags_empty)
        self.tags_wrap.setVisible(not tags_empty)
        self.log_inspector_state("refresh_empty_states")

    def log_flow_state(self, stage: str, flow: FlowLayout):
        host = flow.parentWidget()
        if not host:
            return
        geometry = host.geometry()
        size_hint = host.sizeHint()
        log_ui(
            "INFO",
            "Qt inspector flow state",
            stage=stage,
            hash=self.item_hash or "",
            host=host.objectName() or host.__class__.__name__,
            visible=host.isVisible(),
            item_count=flow.count(),
            child_count=sum(1 for child in host.children() if isinstance(child, QPushButton)),
            host_width=geometry.width(),
            host_height=geometry.height(),
            hint_width=size_hint.width(),
            hint_height=size_hint.height(),
        )

    def log_inspector_state(self, stage: str):
        log_ui(
            "INFO",
            "Qt inspector state",
            stage=stage,
            hash=self.item_hash or "",
            topics_visible=self.topics_wrap.isVisible(),
            rating_visible=self.rating_wrap.isVisible(),
            characters_visible=self.character_wrap.isVisible(),
            tags_visible=self.tags_wrap.isVisible(),
            topics_count=self.topics_flow.count(),
            rating_count=self.rating_flow.count(),
            character_count=self.character_flow.count(),
            tag_count=self.tags_flow.count(),
            wd_panel_width=self.wd_panel.geometry().width(),
            wd_panel_height=self.wd_panel.geometry().height(),
            tags_wrap_width=self.tags_wrap.geometry().width(),
            tags_wrap_height=self.tags_wrap.geometry().height(),
            tags_wrap_hint_width=self.tags_wrap.sizeHint().width(),
            tags_wrap_hint_height=self.tags_wrap.sizeHint().height(),
        )

    def log_preview_geometry(self, stage: str):
        preview_geometry = self.preview.geometry()
        media_geometry = self.media_widget.geometry()
        pixmap = self.preview.pixmap()
        log_ui(
            "INFO",
            "Qt inspector preview geometry",
            stage=stage,
            hash=self.item_hash or "",
            mode=self.focus_mode,
            media_width=media_geometry.width(),
            media_height=media_geometry.height(),
            preview_width=preview_geometry.width(),
            preview_height=preview_geometry.height(),
            pixmap_width=(pixmap.width() if pixmap else 0),
            pixmap_height=(pixmap.height() if pixmap else 0),
        )

    def has_active_video(self) -> bool:
        return self.media_stack.currentWidget() is self.video_preview and self.asset_path is not None

    def save_metadata(self):
        if not self.item_hash:
            return
        artist = self.artist_input.text().strip()
        source_url = self.url_input.text().strip()
        conn = init_database()
        cursor = conn.cursor()
        target_hashes = [str(row[0]) for row in self.group_rows] if len(self.group_rows) > 1 else [self.item_hash]
        for target_hash in target_hashes:
            cursor.execute(
                "UPDATE items SET source_artist = ?, source_url = ? WHERE hash = ?",
                (artist, source_url, target_hash),
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
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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


def _display_topic(topic: str) -> str:
    match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", topic.strip())
    if match:
        return match.group(1).strip() or topic
    return topic


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
