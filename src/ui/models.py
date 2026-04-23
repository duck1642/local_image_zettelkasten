from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt

from db.sqlite_operator import init_database
from logs.logger import log_ui
from ui.thumbnail_cache import asset_path_for, pixmap_for_item


@dataclass
class VaultItemData:
    item_hash: str
    extension: str
    mime_type: str
    original_name: str


class VaultRoles:
    ItemRole = Qt.ItemDataRole.UserRole + 1
    HashRole = Qt.ItemDataRole.UserRole + 2
    PixmapRole = Qt.ItemDataRole.UserRole + 3
    MissingRole = Qt.ItemDataRole.UserRole + 4
    VideoRole = Qt.ItemDataRole.UserRole + 5


class VaultModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.items: list[VaultItemData] = []
        self.pixmap_cache = {}

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.items):
            return None
        item = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.original_name or item.item_hash[:12]
        if role == VaultRoles.ItemRole:
            return item
        if role == VaultRoles.HashRole:
            return item.item_hash
        if role == VaultRoles.VideoRole:
            return item.mime_type.startswith("video/")
        if role == VaultRoles.MissingRole:
            return not asset_path_for(item.item_hash, item.extension, item.mime_type).exists()
        if role == VaultRoles.PixmapRole:
            key = (item.item_hash, item.extension, item.mime_type)
            if key not in self.pixmap_cache:
                self.pixmap_cache[key] = pixmap_for_item(item.item_hash, item.extension, item.mime_type)
            return self.pixmap_cache[key]
        return None

    def set_items(self, rows):
        self.beginResetModel()
        self.items = [VaultItemData(str(h), ext or "", mime or "", name or "") for h, ext, mime, name in rows]
        self.pixmap_cache.clear()
        self.endResetModel()
        log_ui("INFO", "Qt vault model updated", item_count=len(self.items))

    def refresh_from_db(self, field: str | None = None, value: str | None = None):
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
        rows = cursor.fetchall()
        conn.close()
        self.set_items(rows)

    def item_at(self, row: int) -> VaultItemData | None:
        if 0 <= row < len(self.items):
            return self.items[row]
        return None


class VaultDelegate:
    pass
