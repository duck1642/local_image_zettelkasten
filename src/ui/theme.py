APP_STYLESHEET = """
QWidget {
    color: #c9d1d9;
    font-family: Segoe UI;
    font-size: 9pt;
}
QMainWindow, QDialog {
    background: #0d1117;
}
QWidget#AppSurface {
    background: #0d1117;
}
QLineEdit, QTextEdit, QPlainTextEdit {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px;
    color: #c9d1d9;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #58a6ff;
}
QCheckBox {
    spacing: 8px;
    color: #c9d1d9;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30363d;
    border-radius: 4px;
    background: #161b22;
}
QCheckBox::indicator:hover {
    border-color: #58a6ff;
    background: #21262d;
}
QCheckBox::indicator:checked {
    background: #a371f7;
    border-color: #bc8cff;
}
QCheckBox::indicator:checked:hover {
    background: #bc8cff;
    border-color: #d2a8ff;
}
QCheckBox::indicator:disabled {
    background: #0d1117;
    border-color: #21262d;
}
QPushButton {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 12px;
    color: #c9d1d9;
}
QPushButton:hover {
    border-color: #58a6ff;
}
QPushButton:checked {
    background: #1f6feb;
    border-color: #58a6ff;
    color: white;
}
QPushButton#PrimaryButton {
    background: #238636;
    border-color: #238636;
    color: white;
    font-weight: 600;
}
QPushButton#DirtyButton {
    background: #9a6700;
    border-color: #d29922;
    color: white;
    font-weight: 600;
}
QPushButton#DangerButton {
    background: #da3633;
    border-color: #da3633;
    color: white;
}
QPushButton#TransportButton {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 0;
    color: #c9d1d9;
    font-weight: 600;
}
QPushButton#TransportButton:hover {
    background: #21262d;
    border-color: #58a6ff;
}
QPushButton#TransportButton:pressed {
    background: #30363d;
}
QPushButton#CarouselButton {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 0;
    color: #c9d1d9;
    font-weight: 700;
}
QPushButton#CarouselButton:hover {
    background: #21262d;
    border-color: #58a6ff;
}
QSlider::groove:horizontal {
    background: #8b949e;
    height: 3px;
    border-radius: 1px;
}
QSlider::handle:horizontal {
    background: #8b949e;
    border: 2px solid #30363d;
    width: 12px;
    height: 12px;
    margin: -6px 0;
    border-radius: 6px;
}
QSlider::handle:horizontal:hover {
    background: #c9d1d9;
}
QSlider::sub-page:horizontal {
    background: #a371f7;
    height: 3px;
    border-radius: 1px;
}
QLabel#MutedLabel {
    color: #8b949e;
}
QLabel#SavedLabel {
    color: #8b949e;
    font-weight: 600;
}
QLabel#DirtyLabel {
    color: #d29922;
    font-weight: 700;
}
QLabel#SectionLabel {
    color: #8b949e;
    font-size: 8.5pt;
    font-weight: 600;
}
QLabel#InfoValue {
    color: #f0f6fc;
    font-size: 9pt;
    font-weight: 600;
}
QLineEdit#InfoField {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
    color: #f0f6fc;
    font-size: 9pt;
    font-weight: 600;
}
QLineEdit#InfoField:focus {
    border-color: #30363d;
}
QWidget#TransparentContainer, QWidget[role="TransparentContainer"] {
    background-color: transparent;
    border: none;
}
QWidget#MediaPanel {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QLabel#TitleLabel {
    color: #f0f6fc;
    font-weight: 700;
    font-size: 11pt;
}
QLabel#OverlayBadge {
    background: transparent;
    border: none;
    color: #c9d1d9;
    padding: 0;
    font-size: 7.5pt;
    font-weight: 600;
}
QFrame#Panel {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QFrame#Inspector {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QFrame#InspectorHost {
    background: transparent;
    border: none;
}
QPushButton#EditableChip, QPushButton#SuggestionChip, QPushButton#RatingChip {
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 8.5pt;
}
QPushButton#EditableChip {
    background: #21262d;
    border: 1px solid #484f58;
    color: #c9d1d9;
}
QPushButton#EditableChip:hover {
    background: #30363d;
    border-color: #8b949e;
}
QPushButton#SuggestionChip {
    background: #21262d;
    border: 1px solid #30363d;
    color: #c9d1d9;
}
QPushButton#SuggestionChip:hover {
    background: #30363d;
    border-color: #58a6ff;
}
QPushButton#RatingChip {
    background: #2d1f1f;
    border: 1px solid #6e4040;
    color: #ffb3ad;
}
QPushButton#RatingChip:hover {
    background: #3a2727;
    border-color: #a35b5b;
}
QListView {
    background: #0d1117;
    border: none;
    outline: none;
}
QScrollBar:vertical {
    background: #0d1117;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 42px;
}
QScrollBar::handle:vertical:hover {
    background: #484f58;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
    border: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: #0d1117;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 4px;
    min-width: 42px;
}
QScrollBar::handle:horizontal:hover {
    background: #484f58;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: transparent;
    border: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QTabWidget::pane {
    border: none;
}
QStatusBar {
    background: #010409;
    color: #8b949e;
}
"""
