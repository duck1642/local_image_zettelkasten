from PySide6.QtCore import QEvent, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedLayout, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from ui.thumbnail_cache import asset_path_for, pixmap_for_item
from ui.video_widgets import VideoPlayerWidget


class ThumbnailWorker(QRunnable):
    def __init__(self, item_hash, extension, mime_type, callback):
        super().__init__()
        self.item_hash = item_hash
        self.extension = extension
        self.mime_type = mime_type
        self.callback = callback

    def run(self):
        try:
            pixmap = pixmap_for_item(self.item_hash, self.extension, self.mime_type, 178, allow_generate=True)
            self.callback(self.item_hash, pixmap)
        except Exception as exc:
            log_ui("ERROR", "Background thumbnail generation failed", hash=self.item_hash, error=str(exc))


class VaultTile(QFrame):
    clicked = Signal(str)
    active_hover_tile = None

    @classmethod
    def stop_active_hover(cls):
        if cls.active_hover_tile:
            cls.active_hover_tile.force_stop_hover_preview()

    def __init__(self, item_hash: str, extension: str, mime_type: str, original_name: str):
        super().__init__()
        self.item_hash = item_hash
        self.extension = extension or ""
        self.mime_type = mime_type or ""
        self.original_name = original_name or ""
        self.asset_path = asset_path_for(self.item_hash, self.extension, self.mime_type)
        self.is_video = self.mime_type.startswith("video/")
        self.setObjectName("Panel")
        self.setFixedSize(210, 230)
        self.setMouseTracking(True)

        pixmap = pixmap_for_item(self.item_hash, self.extension, self.mime_type, 178, allow_generate=False)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedHeight(180)
        self.image.setPixmap(pixmap)
        
        if self.is_video and self.asset_path.exists():
            from ui.thumbnail_cache import THUMBNAIL_DIR
            thumb_path = THUMBNAIL_DIR / f"{self.item_hash}_video.jpg"
            if not thumb_path.exists():
                worker = ThumbnailWorker(self.item_hash, self.extension, self.mime_type, self.on_thumbnail_ready)
                QThreadPool.globalInstance().start(worker)

        self.video = None
        self.video_loaded = False
        self.hover_active = False

        self.media_widget = QWidget()
        self.media_stack = QStackedLayout(self.media_widget)
        self.media_stack.setContentsMargins(0, 0, 0, 0)
        self.media_stack.addWidget(self.image)

        missing = not self.asset_path.exists()
        label_text = "MISSING" if missing else self.item_hash[:12]
        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("MutedLabel")
        self.label.setToolTip(self.item_hash)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.media_widget)
        layout.addWidget(self.label)
        for widget in [self.image, self.video, self.media_widget, self.label]:
            if widget:
                widget.installEventFilter(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item_hash)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.start_hover_preview()
        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(80, self.stop_hover_preview_if_outside)
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Enter:
            self.start_hover_preview()
        elif event.type() == QEvent.Type.Leave:
            QTimer.singleShot(80, self.stop_hover_preview_if_outside)
        return super().eventFilter(watched, event)

    def start_hover_preview(self):
        if self.hover_active:
            return
        if not self.is_video or not self.asset_path.exists():
            return
        if VaultTile.active_hover_tile and VaultTile.active_hover_tile is not self:
            VaultTile.active_hover_tile.force_stop_hover_preview()
        if not self.video:
            self.video = VideoPlayerWidget(compact=True)
            self.video.setFixedHeight(180)
            self.video.installEventFilter(self)
            self.media_stack.addWidget(self.video)
        if not self.video_loaded:
            self.video.load(self.asset_path)
            self.video_loaded = True
        VaultTile.active_hover_tile = self
        self.media_stack.setCurrentWidget(self.video)
        self.hover_active = True
        self.video.play()
        log_ui("INFO", "Qt vault hover video started", hash=self.item_hash)

    def stop_hover_preview_if_outside(self):
        local_pos = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(local_pos):
            return
        self.force_stop_hover_preview()

    def force_stop_hover_preview(self):
        if self.video and self.hover_active:
            self.hover_active = False
            self.video.stop()
            self.media_stack.setCurrentWidget(self.image)
            if VaultTile.active_hover_tile is self:
                VaultTile.active_hover_tile = None
            log_ui("INFO", "Qt vault hover video stopped", hash=self.item_hash)

    def on_thumbnail_ready(self, item_hash, pixmap):
        if item_hash == self.item_hash:
            # Must update UI on main thread
            QTimer.singleShot(0, lambda: self.image.setPixmap(pixmap))


class VaultGroupTile(QFrame):
    clicked = Signal(str)

    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.current_index = 0
        self.setObjectName("Panel")
        self.setFixedSize(210, 230)
        self.setMouseTracking(True)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedHeight(188)

        self.counter = QLabel()
        self.counter.setObjectName("OverlayBadge")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter.setFixedHeight(14)

        self.prev_button = QPushButton("<")
        self.prev_button.setObjectName("CarouselButton")
        self.prev_button.setFixedSize(34, 34)
        self.prev_button.clicked.connect(self.previous_item)
        self.prev_button.hide()
        self.next_button = QPushButton(">")
        self.next_button.setObjectName("CarouselButton")
        self.next_button.setFixedSize(34, 34)
        self.next_button.clicked.connect(self.next_item)
        self.next_button.hide()

        self.media_widget = QWidget()
        self.media_stack = QStackedLayout(self.media_widget)
        self.media_stack.setContentsMargins(0, 0, 0, 0)
        self.media_stack.addWidget(self.image)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("MutedLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(3)
        layout.addWidget(self.media_widget)
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.counter, 1)
        nav_layout.addWidget(self.next_button)
        layout.addLayout(nav_layout)
        layout.addWidget(self.label)

        for widget in [self.image, self.media_widget, self.counter, self.prev_button, self.next_button, self.label]:
            widget.installEventFilter(self)
        self.update_item()

    def current_row(self):
        return self.rows[self.current_index]

    def update_item(self):
        item_hash, extension, mime_type, original_name, source_url = self.current_row()
        item_hash = str(item_hash)
        pixmap = pixmap_for_item(item_hash, extension or "", mime_type or "", 178, allow_generate=False)
        self.image.setPixmap(pixmap)
        
        if (mime_type or "").startswith("video/"):
            from ui.thumbnail_cache import THUMBNAIL_DIR
            thumb_path = THUMBNAIL_DIR / f"{item_hash}_video.jpg"
            if not thumb_path.exists():
                worker = ThumbnailWorker(item_hash, extension or "", mime_type or "", self.on_thumbnail_ready)
                QThreadPool.globalInstance().start(worker)

        self.counter.setText(f"{self.current_index + 1} / {len(self.rows)}")
        self.label.setText(item_hash[:12])
        self.label.setToolTip(item_hash)

    def on_thumbnail_ready(self, item_hash, pixmap):
        if item_hash == str(self.current_row()[0]):
            QTimer.singleShot(0, lambda: self.image.setPixmap(pixmap))

    def previous_item(self):
        self.current_index = (self.current_index - 1) % len(self.rows)
        self.update_item()

    def next_item(self):
        self.current_index = (self.current_index + 1) % len(self.rows)
        self.update_item()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(str(self.current_row()[0]))
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.prev_button.show()
        self.next_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        QTimer.singleShot(80, self.hide_buttons_if_outside)
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Enter:
            self.prev_button.show()
            self.next_button.show()
        elif event.type() == QEvent.Type.Leave:
            QTimer.singleShot(80, self.hide_buttons_if_outside)
        return super().eventFilter(watched, event)

    def hide_buttons_if_outside(self):
        local_pos = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(local_pos):
            return
        self.prev_button.hide()
        self.next_button.hide()


class VaultView(QScrollArea):
    item_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.items = []
        self.tiles = []
        self.last_columns = 0
        self.last_item_count = 0
        self.setObjectName("AppSurface")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container.setObjectName("AppSurface")
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.viewport().setObjectName("AppSurface")
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.setWidget(self.container)
        self.refresh()

    def refresh(self):
        self.load_items()
        self.render_items()

    def filter_by(self, field: str | None, value: str | None):
        self.load_items(field, value)
        self.render_items()

    def load_items(self, field: str | None = None, value: str | None = None):
        allowed = {"source_artist", "platform", "original_filename"}
        conn = init_database()
        cursor = conn.cursor()
        if field and value and field in allowed:
            cursor.execute(
                f"SELECT hash, file_extension, mime_type, original_filename, source_url FROM items WHERE {field} LIKE ? ORDER BY date_added ASC LIMIT 300",
                (f"%{value}%",),
            )
        else:
            cursor.execute("SELECT hash, file_extension, mime_type, original_filename, source_url FROM items ORDER BY date_added ASC LIMIT 300")
        self.items = cursor.fetchall()
        conn.close()
        log_ui("INFO", "Qt vault widget grid loaded", item_count=len(self.items))

    def display_groups(self):
        grouped = {}
        ordered = []
        for row in self.items:
            source_url = (row[4] or "").strip()
            key = source_url if source_url else f"hash:{row[0]}"
            if key not in grouped:
                grouped[key] = []
                ordered.append(key)
            grouped[key].append(row)
        return [grouped[key] for key in ordered]

    def render_items(self):
        # GUARD: Wait for real geometry if we are currently hidden or collapsed
        if self.viewport().width() < 50:
            return

        columns = self.column_count()
        item_count = len(self.items)
        
        # Lazy Update: Only re-render if the layout structure or data count actually changed
        if columns == self.last_columns and item_count == self.last_item_count:
            return
            
        self.last_columns = columns
        self.last_item_count = item_count

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.tiles = []
        columns = self.column_count()
        groups = self.display_groups()
        for index, rows in enumerate(groups):
            if len(rows) > 1:
                tile = VaultGroupTile(rows)
            else:
                item_hash, extension, mime_type, original_name, source_url = rows[0]
                tile = VaultTile(str(item_hash), extension or "", mime_type or "", original_name or "")
            tile.clicked.connect(self.item_selected.emit)
            self.tiles.append(tile)
            self.grid.addWidget(tile, index // columns, index % columns)
        self.grid.setRowStretch((len(groups) + columns - 1) // columns, 1)
        log_ui("INFO", "Qt vault widget grid rendered", item_count=len(self.items), tile_count=len(self.tiles), columns=columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.tiles:
            return
        columns = self.column_count()
        for index, tile in enumerate(self.tiles):
            self.grid.addWidget(tile, index // columns, index % columns)

    def column_count(self) -> int:
        width = max(1, self.viewport().width())
        return max(1, width // 220)

    def item_count(self) -> int:
        return len(self.items)
