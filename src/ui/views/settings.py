import yaml
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

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
        
        self.vault_layout = QComboBox()
        self.vault_layout.addItems(["grid", "masonry"])
        self.vault_layout.setCurrentText(self.config.get("ui", {}).get("vault_layout", "grid"))
        
        self.flatten_transparency = QCheckBox("Flatten Transparency")
        self.flatten_transparency.setChecked(self.config.get("processing", {}).get("flatten_transparency", True))
        tagging = self.config.get("tagging", {})
        self.tagging_enabled = QCheckBox("Enable Tagging")
        self.tagging_enabled.setChecked(tagging.get("enabled", True))
        self.tagging_model_repo = QLineEdit(tagging.get("model_repo", "SmilingWolf/wd-vit-tagger-v3"))
        self.tagging_device = QComboBox()
        self.tagging_device.addItems(["auto", "cpu", "cuda"])
        self.tagging_device.setCurrentText(tagging.get("device", "auto"))
        self.tagging_display_source = QComboBox()
        self.tagging_display_source.addItems(["yaml", "json"])
        self.tagging_display_source.setCurrentText(tagging.get("display_source", "yaml"))
        self.tagging_threshold = QDoubleSpinBox()
        self.tagging_threshold.setRange(0.0, 1.0)
        self.tagging_threshold.setDecimals(2)
        self.tagging_threshold.setSingleStep(0.05)
        self.tagging_threshold.setValue(float(tagging.get("threshold", 0.35)))
        self.tagging_max_tags = QSpinBox()
        self.tagging_max_tags.setRange(1, 200)
        self.tagging_max_tags.setValue(int(tagging.get("max_tags", 30)))
        self.fail_ingestion_on_error = QCheckBox("Fail Ingestion On Tag Error")
        self.fail_ingestion_on_error.setChecked(tagging.get("fail_ingestion_on_error", False))

        form = QFormLayout()
        form.addRow("Command Prefix", self.cmd_prefix)
        form.addRow("Artist Prefix", self.artist_prefix)
        form.addRow("Tag Prefix", self.tag_prefix)
        form.addRow("Platform Prefix", self.platform_prefix)
        form.addRow("Vault Layout", self.vault_layout)
        form.addRow("", self.flatten_transparency)
        form.addRow("", self.tagging_enabled)
        form.addRow("Tag Model Repo", self.tagging_model_repo)
        form.addRow("Tag Device", self.tagging_device)
        form.addRow("Tag Display Source", self.tagging_display_source)
        form.addRow("Tag Threshold", self.tagging_threshold)
        form.addRow("Tag Max Tags", self.tagging_max_tags)
        form.addRow("", self.fail_ingestion_on_error)

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
        data.setdefault("tagging", {})
        data["ui"]["prefixes"] = {
            "command": self.cmd_prefix.text(),
            "artist": self.artist_prefix.text(),
            "tag": self.tag_prefix.text(),
            "platform": self.platform_prefix.text(),
        }
        data["ui"]["vault_layout"] = self.vault_layout.currentText()
        data["processing"]["flatten_transparency"] = self.flatten_transparency.isChecked()
        tagging = data.get("tagging", {})
        tagging.update({
            "enabled": self.tagging_enabled.isChecked(),
            "model_repo": self.tagging_model_repo.text().strip() or "SmilingWolf/wd-vit-tagger-v3",
            "device": self.tagging_device.currentText(),
            "display_source": self.tagging_display_source.currentText(),
            "threshold": round(float(self.tagging_threshold.value()), 2),
            "max_tags": int(self.tagging_max_tags.value()),
            "fail_ingestion_on_error": self.fail_ingestion_on_error.isChecked(),
        })
        data["tagging"] = tagging
        CONFIG_PATH.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding="utf-8")
        log_ui("INFO", "Qt settings saved")
        self.saved.emit()
