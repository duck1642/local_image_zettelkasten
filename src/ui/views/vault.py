from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QScrollArea, QStackedLayout, QVBoxLayout, QWidget

from db.sqlite_operator import init_database
from logs.logger import log_ui
from ui.thumbnail_cache import asset_path_for, pixmap_for_item
from ui.video_widgets import VideoPlayerWidget


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

        pixmap = pixmap_for_item(self.item_hash, self.extension, self.mime_type, 178)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedHeight(180)
        self.image.setPixmap(pixmap)
        self.video = None
        self.video_loaded = False
        self.hover_active = False

        self.media_widget = QWidget()
        self.media_stack = QStackedLayout(self.media_widget)
        self.media_stack.setContentsMargins(0, 0, 0, 0)
        self.media_stack.addWidget(self.image)

        missing = not self.asset_path.exists()
        label_text = "MISSING" if missing else "VIDEO" if self.is_video else self.item_hash[:8]
        self.label = QLabel(label_text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setObjectName("MutedLabel")

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


class VaultView(QScrollArea):
    item_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.items = []
        self.tiles = []
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
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
        allowed = {"source_artist", "platform", "original_filename", "topics"}
        conn = init_database()
        cursor = conn.cursor()
        if field and value and field in allowed:
            cursor.execute(
                f"SELECT hash, file_extension, mime_type, original_filename FROM items WHERE {field} LIKE ? ORDER BY date_added DESC LIMIT 300",
                (f"%{value}%",),
            )
        else:
            cursor.execute("SELECT hash, file_extension, mime_type, original_filename FROM items ORDER BY date_added DESC LIMIT 300")
        self.items = cursor.fetchall()
        conn.close()
        log_ui("INFO", "Qt vault widget grid loaded", item_count=len(self.items))

    def render_items(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.tiles = []
        columns = self.column_count()
        for index, row in enumerate(self.items):
            item_hash, extension, mime_type, original_name = row
            tile = VaultTile(str(item_hash), extension or "", mime_type or "", original_name or "")
            tile.clicked.connect(self.item_selected.emit)
            self.tiles.append(tile)
            self.grid.addWidget(tile, index // columns, index % columns)
        self.grid.setRowStretch((len(self.items) + columns - 1) // columns, 1)
        log_ui("INFO", "Qt vault widget grid rendered", item_count=len(self.items), tile_count=len(self.tiles), columns=columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        old_positions = [(self.grid.indexOf(tile), tile) for tile in self.tiles]
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
