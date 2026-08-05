"""
src/ui/widgets/date_input.py
Shared Google-Calendar-style date picker — extracted from
daily_contact_screen.py, which had already built and proven this pattern.
Every other screen was using QDateEdit.setCalendarPopup(True) instead, whose
native QCalendarWidget grid breaks under the app's RTL layout direction.
This widget sidesteps that specific bug by drawing its own day grid with a
plain QGridLayout instead of the native QCalendarWidget — QGridLayout (like
every other layout in this app) mirrors correctly under real RTL, so the
popup uses Qt.LayoutDirection.RightToLeft like the rest of the app instead
of forcing LTR.
"""
from PySide6.QtCore import QDate, QEvent, QPoint, QRectF, Signal, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGraphicsDropShadowEffect, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from config.settings import ARABIC_MONTHS, COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER

_MONTH_NAMES = ARABIC_MONTHS[1:]  # drop the index-0 "" placeholder
_WEEKDAY_HEADERS = ["ح", "ن", "ث", "ر", "خ", "ج", "س"]
_BTN_BACK = "رجوع"
_BTN_APPLY = "تطبيق"


class _CalendarDayButton(QPushButton):
    """Circular day cell with hover, selected state, and today dot."""

    def __init__(self, date: QDate, selected: bool, parent: QWidget | None = None) -> None:
        super().__init__(str(date.day()), parent)
        self._date = date
        self._selected = selected
        self._hovered = False
        self._today = date == QDate.currentDate()
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("border:none; background:transparent;")

    @property
    def date(self) -> QDate:
        return self._date

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        circle = QRectF(0, 0, 36, 36)
        if self._selected:
            painter.setBrush(QColor(COLOR_ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(circle)
        elif self._hovered:
            painter.setBrush(QColor(COLOR_BORDER))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(circle)

        painter.setPen(QColor("white" if self._selected else "#111111"))
        painter.drawText(QRectF(0, 3, 36, 23), Qt.AlignmentFlag.AlignCenter, self.text())

        if self._today:
            painter.setBrush(QColor("white" if self._selected else COLOR_ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(16, 29, 4, 4))


class _CalendarPopup(QFrame):
    """Small custom Arabic calendar popup for DateInput."""

    dateSelected = Signal(QDate)

    def __init__(self, selected_date: QDate, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("sharedCalendarPopup")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedWidth(300)
        self._draft_date = selected_date if selected_date.isValid() else QDate.currentDate()
        self._day_buttons: list[_CalendarDayButton] = []
        self._building = False

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 38))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(f"""
            QFrame#sharedCalendarPopup {{
                background: white;
                border-radius: 12px;
                padding: 16px;
            }}
            QComboBox {{
                border-radius: 20px;
                padding: 6px 14px;
                border: 1px solid {COLOR_BORDER};
                font-size: 14px;
                background: white;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QLabel#weekdayHeader {{
                color: #999;
                font-size: 12px;
            }}
            QPushButton#backButton {{
                border: 1px solid {COLOR_BORDER};
                background: white;
                border-radius: 20px;
                padding: 8px 24px;
                color: #333;
            }}
            QPushButton#applyButton {{
                border: none;
                background: {COLOR_ACCENT};
                color: white;
                border-radius: 20px;
                padding: 8px 24px;
            }}
            QPushButton#applyButton:hover {{
                background: {COLOR_ACCENT_DEEP};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._month_combo = QComboBox()
        self._month_combo.addItems(_MONTH_NAMES)
        self._year_combo = QComboBox()
        self._year_combo.addItems([str(year) for year in range(2000, 2101)])
        top.addWidget(self._month_combo, 1)
        top.addWidget(self._year_combo, 1)
        root.addLayout(top)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(4)
        root.addLayout(self._grid)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        back_btn = QPushButton(_BTN_BACK)
        back_btn.setObjectName("backButton")
        apply_btn = QPushButton(_BTN_APPLY)
        apply_btn.setObjectName("applyButton")
        back_btn.clicked.connect(self.close)
        apply_btn.clicked.connect(self._apply)
        footer.addWidget(back_btn)
        footer.addStretch()
        footer.addWidget(apply_btn)
        root.addLayout(footer)

        self._month_combo.currentIndexChanged.connect(self._on_month_changed)
        self._year_combo.currentIndexChanged.connect(self._on_year_changed)
        self._sync_selects()
        self._build_grid()

    def showEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.MouseButtonPress:
            if self._month_combo.view().isVisible() or self._year_combo.view().isVisible():
                return super().eventFilter(obj, event)
            global_pos = event.globalPosition().toPoint()
            if not self.geometry().contains(global_pos):
                self.close()
        return super().eventFilter(obj, event)

    def _sync_selects(self) -> None:
        self._building = True
        self._month_combo.setCurrentIndex(self._draft_date.month() - 1)
        year_index = max(0, self._draft_date.year() - 2000)
        self._year_combo.setCurrentIndex(min(year_index, self._year_combo.count() - 1))
        self._building = False

    def _on_month_changed(self, index: int) -> None:
        if self._building or index < 0:
            return
        self._set_year_month(self._draft_date.year(), index + 1)

    def _on_year_changed(self, index: int) -> None:
        if self._building or index < 0:
            return
        self._set_year_month(2000 + index, self._draft_date.month())

    def _set_year_month(self, year: int, month: int) -> None:
        first_day = QDate(year, month, 1)
        day = min(self._draft_date.day(), first_day.daysInMonth())
        self._draft_date = QDate(year, month, day)
        self._build_grid()

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_grid(self) -> None:
        self._clear_grid()
        self._day_buttons.clear()

        for col, text in enumerate(_WEEKDAY_HEADERS):
            label = QLabel(text)
            label.setObjectName("weekdayHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(label, 0, col)

        year = self._draft_date.year()
        month = self._draft_date.month()
        first_day = QDate(year, month, 1)
        start_col = first_day.dayOfWeek() % 7
        for day in range(1, first_day.daysInMonth() + 1):
            date = QDate(year, month, day)
            position = start_col + day - 1
            row = (position // 7) + 1
            col = position % 7
            button = _CalendarDayButton(date, date == self._draft_date)
            button.clicked.connect(lambda checked=False, btn=button: self._select_day(btn.date))
            self._day_buttons.append(button)
            self._grid.addWidget(button, row, col)

    def _select_day(self, date: QDate) -> None:
        self._draft_date = date
        for button in self._day_buttons:
            button.set_selected(button.date == date)

    def _apply(self) -> None:
        self.dateSelected.emit(self._draft_date)
        self.close()


class DateInput(QLineEdit):
    """Read-only date input that opens the custom calendar popup. Drop-in
    replacement for QDateEdit().setCalendarPopup(True) — same date()/
    setDate()/dateChanged surface, but never fights the app's RTL layout."""

    dateChanged = Signal(QDate)

    def __init__(self, parent: QWidget | None = None, display_format: str = "dd-MM-yyyy") -> None:
        super().__init__(parent)
        self._display_format = display_format
        self._date = QDate.currentDate()
        self._popup: _CalendarPopup | None = None
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self._date.toString(self._display_format))

    def date(self) -> QDate:
        return self._date

    def setDate(self, date: QDate) -> None:
        if not date.isValid() or date == self._date:
            return
        self._date = date
        self.setText(date.toString(self._display_format))
        self.dateChanged.emit(date)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._show_calendar()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._show_calendar()
            return
        super().keyPressEvent(event)

    def _show_calendar(self) -> None:
        if self._popup is not None:
            self._popup.close()
        self._popup = _CalendarPopup(self._date, self)
        self._popup.dateSelected.connect(self.setDate)
        below_right = self.mapToGlobal(QPoint(self.width(), self.height() + 6))
        x = below_right.x() - self._popup.width()
        y = below_right.y()
        self._popup.move(max(0, x), y)
        self._popup.show()
        self._popup.raise_()
