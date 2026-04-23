from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from ui.thumbnail_cache import preview_pixmap


class MetadataDialog(QDialog):
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.setWindowTitle("Manual Ingestion")
        self.setMinimumWidth(420)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(180)
        if self.file_path.exists() and self.file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            pixmap = preview_pixmap(self.file_path, self.file_path.stem, "image/jpeg", 360, 180)
            self.preview.setPixmap(pixmap)
        else:
            self.preview.setText(self.file_path.name)

        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Source URL")
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.artist_input.textChanged.connect(self.update_state)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"File: {self.file_path.name}"))
        layout.addWidget(self.preview)
        layout.addWidget(self.artist_input)
        layout.addWidget(self.url_input)
        layout.addWidget(self.buttons)
        self.update_state()

    def update_state(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.artist_input.text().strip()))

    def metadata(self):
        return {
            "artist": self.artist_input.text().strip(),
            "source_url": self.url_input.text().strip(),
            "platform": "Manual",
        }
