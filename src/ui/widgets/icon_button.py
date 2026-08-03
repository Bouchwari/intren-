"""
src/ui/widgets/icon_button.py
Shared button widget — icon + text laid out manually instead of relying on
QPushButton's built-in icon/text placement.

Qt's `text-align` stylesheet property only shifts the *text* inside its own
box; it does not reposition the icon+text pair as a block. On a wide button
(sidebar nav, full-row actions) this leaves the icon+label group floating
near the left edge with a large empty gap on the right, even with
`Qt.LayoutDirection.RightToLeft` set everywhere. Building the icon and label
as two QLabels inside our own QHBoxLayout sidesteps that: Qt's layout
mirroring under RTL reliably pins the first-added widget to the right edge,
so icon+label always hugs the trailing (right) side, with a stretch
absorbing the leftover space on the left.
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from ui.widgets.icons import emoji_icon


class IconButton(QPushButton):
    """A QPushButton whose icon+text content is manually right-anchored."""

    def __init__(
        self,
        text: str = "",
        *,
        icon: str | None = None,
        bg: str = "transparent",
        text_color: str = "white",
        border: str | None = None,
        border_radius: int = 12,
        padding_h: int = 14,
        font_size: int = 13,
        bold: bool = True,
        min_height: int = 36,
        icon_size: int = 16,
        hover_bg: str | None = None,
        hover_text_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(min_height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # The internal layout's addStretch() (needed to right-anchor content)
        # makes Qt treat this widget as horizontally expanding when queried
        # by an outer layout, growing it past its content size. Fixed keeps
        # it sized to its own sizeHint like a normal button.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._bg = bg
        self._text_color = text_color
        self._border = border
        self._border_radius = border_radius
        self._font_size = font_size
        self._bold = bold
        self._hover_bg = hover_bg
        self._hover_text_color = hover_text_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(padding_h, 0, padding_h, 0)
        layout.setSpacing(6)

        self._icon_lbl: QLabel | None = None
        if icon:
            self._icon_lbl = QLabel(self)
            self._icon_lbl.setPixmap(emoji_icon(icon, size=icon_size * 2).pixmap(QSize(icon_size, icon_size)))
            self._icon_lbl.setStyleSheet("background: transparent; border: none;")
            self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(text, self)
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._text_lbl)

        layout.addStretch()
        self._apply_chrome()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        # QPushButton computes its own sizeHint from its (empty) native
        # text/icon, ignoring the manual child layout — without this
        # override, buttons get squeezed to near-zero width by any
        # container that isn't already sized to fit the content.
        hint = self.layout().sizeHint()
        return QSize(hint.width(), max(hint.height(), self.minimumHeight()))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.layout().minimumSize()

    def _apply_chrome(self) -> None:
        border_css = f"1px solid {self._border}" if self._border else "none"
        hover_rule = ""
        if self._hover_bg:
            hover_rule = f"QPushButton:hover {{ background:{self._hover_bg}; }}"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._bg};
                border: {border_css};
                border-radius: {self._border_radius}px;
            }}
            {hover_rule}
        """)
        weight = "bold" if self._bold else "normal"
        text_color = self._text_color
        self._text_lbl.setStyleSheet(
            f"color:{text_color}; background:transparent; border:none;"
            f"font-size:{self._font_size}px; font-weight:{weight};"
        )

    def set_style(self, *, bg: str | None = None, text_color: str | None = None,
                  border: str | None = None, hover_bg: str | None = None) -> None:
        """Restyle an already-built button (e.g. active/inactive toggle states)."""
        if bg is not None:
            self._bg = bg
        if text_color is not None:
            self._text_color = text_color
        if border is not None:
            self._border = border
        if hover_bg is not None:
            self._hover_bg = hover_bg
        self._apply_chrome()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt override
        self._text_lbl.setText(text)

    def text(self) -> str:  # noqa: N802 - Qt override
        return self._text_lbl.text()

    def set_icon_emoji(self, icon: str, size: int = 16) -> None:
        if self._icon_lbl is None:
            return
        self._icon_lbl.setPixmap(emoji_icon(icon, size=size * 2).pixmap(QSize(size, size)))
