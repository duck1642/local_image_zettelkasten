import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from logs.logger import log_ui
from processor import process_file
from ui.thumbnail_cache import placeholder_pixmap, preview_pixmap
from utils import ASSETS_DIR, REVIEW_DIR, get_config


class ReviewView(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.items: list[Path] = []
        self.current_index = 0

        self.left_label = QLabel()
        self.left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_caption = QLabel()
        self.left_caption.setObjectName("MutedLabel")
        self.right_label = QLabel()
        self.right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.right_caption = QLabel()
        self.right_caption.setObjectName("MutedLabel")
        self.info_label = QLabel()
        self.info_label.setObjectName("MutedLabel")
        self.nav_label = QLabel()
        self.nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.keep_button = QPushButton("Keep")
        self.keep_button.setObjectName("PrimaryButton")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("DangerButton")
        self.variant_button = QPushButton("Save as Variant")
        self.prev_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")

        self.keep_button.clicked.connect(lambda: self.handle_action("keep"))
        self.delete_button.clicked.connect(lambda: self.handle_action("delete"))
        self.variant_button.clicked.connect(lambda: self.handle_action("variant"))
        self.prev_button.clicked.connect(self.prev_item)
        self.next_button.clicked.connect(self.next_item)

        left = QVBoxLayout()
        left.addWidget(QLabel("NEW ITEM"))
        left.addWidget(self.left_label)
        left.addWidget(self.left_caption)
        right = QVBoxLayout()
        right.addWidget(QLabel("BEST MATCH IN VAULT"))
        right.addWidget(self.right_label)
        right.addWidget(self.right_caption)
        previews = QHBoxLayout()
        previews.addLayout(left, 1)
        previews.addLayout(right, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.keep_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.variant_button)
        nav = QHBoxLayout()
        nav.addWidget(self.prev_button)
        nav.addWidget(self.nav_label)
        nav.addWidget(self.next_button)

        layout = QVBoxLayout(self)
        layout.addLayout(previews)
        layout.addWidget(self.info_label)
        layout.addLayout(actions)
        layout.addLayout(nav)
        layout.addStretch(1)
        self.load_items()

    def load_items(self):
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        self.items = sorted([p for p in REVIEW_DIR.iterdir() if p.is_file() and p.suffix.lower() != ".json"])
        self.current_index = 0
        self.update_ui()

    def update_ui(self):
        if not self.items:
            self.left_label.setText("Review folder is empty.")
            self.left_label.setPixmap(QPixmap())
            self.right_label.clear()
            self.left_caption.clear()
            self.right_caption.clear()
            self.info_label.clear()
            self.nav_label.setText("Item 0 of 0")
            self.set_actions_enabled(False)
            return

        self.set_actions_enabled(True)
        item_path = self.items[self.current_index]
        metadata = self.load_metadata(item_path)
        best_match = metadata.get("best_match", "")
        match_type = metadata.get("match_type", "Unknown")
        distance = metadata.get("distance", "?")
        similarity = metadata.get("similarity", "?")

        self.left_label.setPixmap(self.path_pixmap(item_path))
        self.left_caption.setText(item_path.name)
        self.right_label.setPixmap(self.vault_pixmap(best_match))
        self.right_caption.setText(f"Hash: {best_match[:12]}..." if best_match else "No match")
        self.info_label.setText(f"Match Type: {match_type} | Distance: {distance} | Similarity: {similarity}")
        self.nav_label.setText(f"Item {self.current_index + 1} of {len(self.items)}")
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.items) - 1)

    def set_actions_enabled(self, enabled: bool):
        for button in [self.keep_button, self.delete_button, self.variant_button, self.prev_button, self.next_button]:
            button.setEnabled(enabled)

    def load_metadata(self, item_path: Path):
        json_path = item_path.with_suffix(".json")
        if not json_path.exists():
            return {}
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log_ui("ERROR", "Qt review metadata read failed", path=str(json_path), error=str(exc))
            return {}

    def path_pixmap(self, path: Path):
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            pixmap = QPixmap(str(path))
            return pixmap.scaled(420, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return placeholder_pixmap("VIDEO", QColor("#8b949e"), 260)

    def vault_pixmap(self, item_hash: str):
        if not item_hash:
            return placeholder_pixmap("NO MATCH", QColor("#8b949e"), 260)
        asset_dir = ASSETS_DIR / item_hash[:2]
        matches = list(asset_dir.glob(f"{item_hash}.*"))
        if not matches:
            return placeholder_pixmap("MISSING", QColor("#f85149"), 260)
        mime = "video/mp4" if matches[0].suffix.lower() in {".mp4", ".webm", ".ogv"} else "image/jpeg"
        return preview_pixmap(matches[0], item_hash, mime, 420, 320)

    def handle_action(self, action: str):
        if not self.items:
            return
        item_path = self.items[self.current_index]
        json_path = item_path.with_suffix(".json")
        try:
            if action == "delete":
                item_path.unlink(missing_ok=True)
                json_path.unlink(missing_ok=True)
                message = f"Deleted: {item_path.name}"
            else:
                success, process_msg, _ = process_file(item_path, get_config(), delete_source=True, skip_similarity=True)
                if success:
                    json_path.unlink(missing_ok=True)
                    message = f"Approved: {item_path.name}"
                else:
                    message = f"Error: {process_msg}"
            log_ui("INFO", "Qt review action", action=action, item=str(item_path), message=message)
            QMessageBox.information(self, "Review", message)
        except Exception as exc:
            log_ui("ERROR", "Qt review action failed", action=action, item=str(item_path), error=str(exc))
            QMessageBox.critical(self, "Review Error", str(exc))
        self.load_items()
        self.changed.emit()

    def next_item(self):
        if self.current_index < len(self.items) - 1:
            self.current_index += 1
            self.update_ui()

    def prev_item(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_ui()
