"""
src/ui/widgets/empty_state.py
Shared "nothing here yet" placeholder — icon + message, centered, styled as
a soft card instead of a plain label floating in blank space.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from config.settings import (
    COLOR_PANEL_ALT, COLOR_TEXT_SECONDARY, FONT_BODY, SPACE_SM, SPACE_XL,
)
from ui.widgets.icons import emoji_icon


class EmptyState(QWidget):
    """Centered icon + message for an empty table/list/report."""

    def __init__(self, message: str, *, icon: str = "📭", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACE_SM)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(emoji_icon(icon, size=64).pixmap(64, 64))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent;")

        text_lbl = QLabel(message)
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: {FONT_BODY}px; background: transparent;"
        )

        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl)
        self.setStyleSheet(f"background: {COLOR_PANEL_ALT}; border-radius: 16px;")
        layout.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
