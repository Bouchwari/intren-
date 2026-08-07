"""
src/ui/theme.py
Bundled font loading + the app's global stylesheet (Stage 2 design system).
See .claude/skills/matama/references/ui_design.md for the token rationale.
"""
import logging

from PySide6.QtGui import QFontDatabase

from config.settings import (
    CHECK_ICON_PATH,
    COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER, COLOR_PANEL,
    COLOR_PANEL_ALT, COLOR_PAPER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONTS_DIR, SPACE_MD, SPACE_SM,
)

logger = logging.getLogger(__name__)

_FALLBACK_BODY_FONT = "Segoe UI"
_FALLBACK_TITLE_FONT = "Segoe UI"

_body_font_family: str | None = None
_title_font_family: str | None = None


def load_fonts() -> None:
    """Register every bundled .ttf in assets/fonts/ so the app never depends
    on a font being installed on Windows. Safe to call more than once."""
    global _body_font_family, _title_font_family

    if not FONTS_DIR.exists():
        logger.warning("Fonts folder not found: %s", FONTS_DIR)
        return

    for font_path in sorted(FONTS_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            logger.warning("Failed to load font: %s", font_path.name)
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        logger.info("Loaded font: %s -> %s", font_path.name, families)
        if not families:
            continue
        name_lower = font_path.name.lower()
        if name_lower.startswith("cairo") and _body_font_family is None:
            _body_font_family = families[0]
        elif "maghribi" in name_lower and _title_font_family is None:
            _title_font_family = families[0]


def body_font_family() -> str:
    """Cairo, or Segoe UI if it failed to load — the everyday UI face."""
    return _body_font_family or _FALLBACK_BODY_FONT


def official_font_family() -> str:
    """The bundled Maghribi face — official/title use only, sparingly."""
    return _title_font_family or _FALLBACK_TITLE_FONT


def build_stylesheet() -> str:
    """Generate the whole app's QSS from config/settings.py tokens. No hex
    value may appear here directly — everything is read from settings."""
    body_font = body_font_family()

    return f"""
        QMainWindow, QWidget {{
            background: {COLOR_PAPER};
            color: {COLOR_TEXT_PRIMARY};
            font-family: '{body_font}';
            font-size: {FONT_BODY}px;
        }}

        QLabel {{
            background: transparent;
            color: {COLOR_TEXT_PRIMARY};
        }}

        QPushButton {{
            background: {COLOR_ACCENT};
            color: white;
            border: none;
            border-radius: 8px;
            padding: {SPACE_SM}px {SPACE_MD}px;
        }}
        QPushButton:hover {{
            background: {COLOR_ACCENT_DEEP};
        }}
        QPushButton:pressed {{
            background: {COLOR_ACCENT_DEEP};
            padding-top: {SPACE_SM + 1}px;
        }}
        QPushButton:disabled {{
            background: {COLOR_BORDER};
            color: {COLOR_TEXT_SECONDARY};
        }}

        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit,
        QSpinBox, QDoubleSpinBox, QAbstractSpinBox {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: {SPACE_SM - 2}px {SPACE_SM}px;
            selection-background-color: {COLOR_ACCENT};
            selection-color: white;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
        QDoubleSpinBox:focus {{
            border: 1px solid {COLOR_ACCENT};
        }}
        QLineEdit::placeholder, QTextEdit::placeholder,
        QPlainTextEdit::placeholder {{
            color: {COLOR_TEXT_SECONDARY};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
        QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled,
        QDoubleSpinBox:disabled, QAbstractSpinBox:disabled {{
            background: {COLOR_PANEL_ALT};
            color: {COLOR_TEXT_SECONDARY};
        }}

        QComboBox::drop-down, QDateEdit::drop-down {{
            width: 28px;
            border: none;
            border-left: 1px solid {COLOR_BORDER};
            background: {COLOR_PANEL_ALT};
            border-radius: 0 6px 6px 0;
        }}
        QComboBox::down-arrow, QDateEdit::down-arrow {{
            image: none;
            width: 0;
            height: 0;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {COLOR_ACCENT};
            margin-top: 2px;
        }}

        QAbstractItemView, QListView, QComboBox QAbstractItemView {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            selection-background-color: {COLOR_ACCENT};
            selection-color: white;
            border: 1px solid {COLOR_BORDER};
            outline: 0;
        }}
        QAbstractItemView::item {{
            min-height: 26px;
            padding: {SPACE_SM - 2}px {SPACE_SM}px;
        }}
        QAbstractItemView::item:hover, QAbstractItemView::item:selected {{
            background: {COLOR_ACCENT};
            color: white;
        }}

        QCheckBox {{
            color: {COLOR_TEXT_PRIMARY};
            spacing: {SPACE_SM + 2}px;
            min-height: 24px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {COLOR_BORDER};
            border-radius: 5px;
            background: {COLOR_PANEL};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {COLOR_ACCENT};
        }}
        QCheckBox::indicator:checked {{
            background: {COLOR_ACCENT};
            border: 1px solid {COLOR_ACCENT};
            image: url({CHECK_ICON_PATH.as_posix()});
        }}

        QTabWidget::pane {{
            border: 1px solid {COLOR_BORDER};
            border-radius: 12px;
            background: {COLOR_PANEL};
            top: -1px;
        }}
        QTabBar::tab {{
            background: {COLOR_PANEL_ALT};
            color: {COLOR_TEXT_SECONDARY};
            border: 1px solid {COLOR_BORDER};
            border-bottom: none;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            padding: {SPACE_SM}px {SPACE_MD + SPACE_SM}px;
            margin-left: 3px;
            font-weight: bold;
        }}
        QTabBar::tab:selected {{
            background: {COLOR_PANEL};
            color: {COLOR_ACCENT_DEEP};
            border-color: {COLOR_BORDER};
        }}
        QTabBar::tab:!selected:hover {{
            color: {COLOR_TEXT_PRIMARY};
        }}

        QCalendarWidget {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QCalendarWidget QWidget {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QCalendarWidget QToolButton {{
            background: {COLOR_PANEL_ALT};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: {SPACE_SM - 3}px {SPACE_SM}px;
            font-weight: bold;
        }}
        QCalendarWidget QMenu {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            selection-background-color: {COLOR_ACCENT};
            selection-color: white;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {COLOR_TEXT_SECONDARY};
        }}

        QDialog, QMessageBox {{
            background: {COLOR_PAPER};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QDialog QLabel, QMessageBox QLabel {{
            color: {COLOR_TEXT_PRIMARY};
            background: transparent;
        }}
        QMessageBox QPushButton {{
            min-width: 82px;
            min-height: 30px;
        }}

        QTableView {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            gridline-color: {COLOR_BORDER};
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            selection-background-color: {COLOR_ACCENT};
            selection-color: white;
        }}
        QHeaderView::section {{
            background: {COLOR_ACCENT};
            color: white;
            border: none;
            padding: {SPACE_SM - 2}px {SPACE_SM}px;
            font-weight: bold;
        }}

        QScrollBar:vertical {{
            background: {COLOR_PAPER};
            width: 12px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_BORDER};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {COLOR_TEXT_SECONDARY};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: {COLOR_PAPER};
            height: 12px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {COLOR_BORDER};
            border-radius: 5px;
            min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        QGroupBox {{
            background: {COLOR_PANEL};
            border: 1px solid {COLOR_BORDER};
            border-radius: 10px;
            margin-top: {SPACE_MD}px;
            padding-top: {SPACE_MD}px;
            font-weight: bold;
            color: {COLOR_TEXT_PRIMARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top right;
            padding: 0 {SPACE_SM}px;
        }}
    """
