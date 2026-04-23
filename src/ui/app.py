import os
import sys

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg=false;qt.multimedia.playbackengine.codec=false")

from PySide6.QtWidgets import QApplication

from logs.logger import log_system, log_ui
from ui.main_window import MainWindow
from ui.theme import APP_STYLESHEET
from utils import CONFIG_PATH, DB_PATH, PROJECT_ROOT, VAULT_DIR, setup_directories


def main():
    setup_directories()
    log_system("INFO", "GUI Startup", project_root=str(PROJECT_ROOT), vault_dir=str(VAULT_DIR), config_path=str(CONFIG_PATH))
    log_ui("INFO", "PySide6 GUI startup", project_root=str(PROJECT_ROOT), vault_dir=str(VAULT_DIR), db_path=str(DB_PATH))

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("LIZ Management Center")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
