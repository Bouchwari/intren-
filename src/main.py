"""
نظام إدارة المطعمة - Matama System
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

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import Qt

from config.settings import APP_NAME
from data.database import init_database, get_school_settings
from ui.dialogs import install_dialog_overrides
from ui.main_window import MainWindow
from ui.setup_wizard import SetupWizard


def _global_app_stylesheet() -> str:
    """Keep editable controls readable regardless of the Windows theme."""
    return """
        QWidget {
            color: #0f172a;
        }
        QLineEdit,
        QTextEdit,
        QPlainTextEdit,
        QComboBox,
        QDateEdit,
        QSpinBox,
        QDoubleSpinBox,
        QAbstractSpinBox {
            background-color: #ffffff;
            color: #0f172a;
            selection-background-color: #5A5A40;
            selection-color: #ffffff;
        }
        QLineEdit::placeholder,
        QTextEdit::placeholder,
        QPlainTextEdit::placeholder {
            color: #94a3b8;
        }
        QCheckBox {
            color: #0f172a;
            spacing: 10px;
            min-height: 24px;
        }
        QLineEdit:disabled,
        QTextEdit:disabled,
        QPlainTextEdit:disabled,
        QComboBox:disabled,
        QDateEdit:disabled,
        QSpinBox:disabled,
        QDoubleSpinBox:disabled,
        QAbstractSpinBox:disabled {
            background-color: #f1f5f9;
            color: #64748b;
        }
        QAbstractItemView,
        QListView,
        QComboBox QAbstractItemView {
            background-color: #ffffff;
            color: #0f172a;
            selection-background-color: #5A5A40;
            selection-color: #ffffff;
            border: 1px solid #d6d6c8;
            outline: 0;
        }
        QAbstractItemView::item {
            min-height: 26px;
            padding: 6px 10px;
        }
        QAbstractItemView::item:hover,
        QAbstractItemView::item:selected {
            background-color: #5A5A40;
            color: #ffffff;
        }
        QComboBox::drop-down,
        QDateEdit::drop-down {
            width: 34px;
            border: none;
            border-left: 1px solid #d6d6c8;
            background: #f7f7ef;
            border-radius: 8px 0 0 8px;
        }
        QComboBox::down-arrow,
        QDateEdit::down-arrow {
            image: none;
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid #5A5A40;
            margin-top: 2px;
        }
        QCalendarWidget {
            background-color: #ffffff;
            color: #0f172a;
        }
        QCalendarWidget QWidget {
            background-color: #ffffff;
            color: #0f172a;
        }
        QCalendarWidget QToolButton {
            background-color: #f7f7ef;
            color: #0f172a;
            border: 1px solid #d6d6c8;
            border-radius: 8px;
            padding: 5px 8px;
            font-weight: 700;
        }
        QCalendarWidget QMenu {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #d6d6c8;
        }
        QCalendarWidget QSpinBox {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #d6d6c8;
            border-radius: 8px;
            padding: 4px 8px;
        }
        QCalendarWidget QAbstractItemView:enabled {
            background-color: #ffffff;
            color: #0f172a;
            selection-background-color: #5A5A40;
            selection-color: #ffffff;
        }
        QCalendarWidget QAbstractItemView:disabled {
            color: #94a3b8;
        }
        QDialog,
        QMessageBox {
            background-color: #f5f5f0;
            color: #0f172a;
        }
        QDialog QLabel,
        QMessageBox QLabel {
            color: #0f172a;
            background: transparent;
        }
        QMessageBox QPushButton {
            background-color: #5A5A40;
            color: #ffffff;
            border: none;
            border-radius: 9px;
            min-width: 82px;
            min-height: 30px;
            padding: 0 14px;
        }
        QScrollBar:vertical {
            background: #eeeede;
            width: 12px;
            margin: 0;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: #9a9a78;
            min-height: 28px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background: #5A5A40;
        }
        QScrollBar:horizontal {
            background: #eeeede;
            height: 12px;
            margin: 0;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal {
            background: #9a9a78;
            min-width: 28px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #5A5A40;
        }
        QScrollBar::add-line,
        QScrollBar::sub-line,
        QScrollBar::add-page,
        QScrollBar::sub-page {
            background: transparent;
            border: none;
        }
    """


def _apply_light_palette(app: QApplication) -> None:
    """Use a light Qt palette so Windows dark mode cannot invert popups."""
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f0"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f8fafc"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#E4E4D7"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#5A5A40"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#94a3b8"))
    app.setPalette(palette)


def main() -> int:
    init_database()

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setApplicationName(APP_NAME)
    _apply_light_palette(app)
    app.setStyleSheet(_global_app_stylesheet())
    install_dialog_overrides()

    # Show setup wizard the first time (no school settings saved yet)
    if get_school_settings() is None:
        wizard = SetupWizard()
        if wizard.exec() != SetupWizard.DialogCode.Accepted:
            return 0  # user closed wizard without finishing — exit cleanly

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
