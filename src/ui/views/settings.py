import yaml
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from logs.logger import log_ui
from utils import CONFIG_PATH, get_config


class SettingsView(QWidget):
    saved = Signal()

    def __init__(self):
        super().__init__()
        self.config = get_config()

        prefixes = self.config.get("ui", {}).get("prefixes", {})
        self.cmd_prefix = QLineEdit(prefixes.get("command", ">"))
        self.artist_prefix = QLineEdit(prefixes.get("artist", "a:"))
        self.tag_prefix = QLineEdit(prefixes.get("tag", "#"))
        self.platform_prefix = QLineEdit(prefixes.get("platform", "@"))
        self.flatten_transparency = QCheckBox("Flatten Transparency")
        self.flatten_transparency.setChecked(self.config.get("processing", {}).get("flatten_transparency", True))

        form = QFormLayout()
        form.addRow("Command Prefix", self.cmd_prefix)
        form.addRow("Artist Prefix", self.artist_prefix)
        form.addRow("Tag Prefix", self.tag_prefix)
        form.addRow("Platform Prefix", self.platform_prefix)
        form.addRow("", self.flatten_transparency)

        self.save_button = QPushButton("Save Settings")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_settings)

        layout = QVBoxLayout(self)
        title = QLabel("System Settings")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addStretch(1)

    def save_settings(self):
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
        data = data or {}
        data.setdefault("ui", {})
        data.setdefault("processing", {})
        data["ui"]["prefixes"] = {
            "command": self.cmd_prefix.text(),
            "artist": self.artist_prefix.text(),
            "tag": self.tag_prefix.text(),
            "platform": self.platform_prefix.text(),
        }
        data["processing"]["flatten_transparency"] = self.flatten_transparency.isChecked()
        CONFIG_PATH.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
        log_ui("INFO", "Qt settings saved")
        self.saved.emit()
