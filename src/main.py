"""
تدبير الداخلية المدرسية - Tadbir Internat
Entry point of the application.
"""
import sys
from pathlib import Path

# Add src/ so that ui/, core/, data/ are importable.
# Add project root so that config/ is importable.
if getattr(sys, 'frozen', False):
    _ROOT_DIR = Path(sys._MEIPASS)  # type: ignore
    _SRC_DIR = _ROOT_DIR / "src"
else:
    _SRC_DIR = Path(__file__).resolve().parent
    _ROOT_DIR = _SRC_DIR.parent

sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_ROOT_DIR))

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import QTimer, Qt

from config.settings import (
    APP_ICON_PATH, APP_NAME, APP_NAME_LATIN,
    COLOR_ACCENT, COLOR_OLIVE, COLOR_PANEL, COLOR_PAPER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
)
from data.database import init_database, get_school_settings
from ui.dialogs import install_dialog_overrides
from ui.main_window import MainWindow
from ui.setup_wizard import SetupWizard
from ui.theme import build_stylesheet, load_fonts


def _apply_light_palette(app: QApplication) -> None:
    """Use a light Qt palette so Windows dark mode cannot invert popups."""
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLOR_PAPER))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLOR_PANEL))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_PAPER))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLOR_PANEL))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLOR_ACCENT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_OLIVE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLOR_TEXT_SECONDARY))
    app.setPalette(palette)


def needs_initial_setup() -> bool:
    """Treat missing or incomplete school identity as an unfinished setup."""
    settings = get_school_settings()
    return settings is None or not all((
        settings.school_name.strip(),
        settings.school_year.strip(),
        settings.director.strip(),
    ))


def main() -> int:
    init_database()

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME_LATIN)
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    _apply_light_palette(app)
    load_fonts()
    app.setStyleSheet(build_stylesheet())
    install_dialog_overrides()

    # Show setup wizard the first time (no school settings saved yet)
    if needs_initial_setup():
        wizard = SetupWizard()
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            return 0  # user closed wizard without finishing — exit cleanly

    window = MainWindow()
    window.show()
    QTimer.singleShot(1_500, window.check_for_updates)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
