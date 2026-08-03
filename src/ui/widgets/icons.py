"""
src/ui/widgets/icons.py
Shared emoji-to-QIcon rendering — extracted from main_window.py so every
screen can give its buttons a real QIcon instead of embedding the emoji as a
text prefix. QPushButton.setIcon() + setText() are separate properties Qt
positions according to layoutDirection() — unlike a literal emoji character
inside the text string, which does not reliably land on the correct side
under RTL.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap


def emoji_icon(emoji: str, size: int = 20) -> QIcon:
    """Render an emoji glyph to a QIcon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont()
    font.setPointSize(int(size * 0.62))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    painter.end()
    return QIcon(pixmap)
