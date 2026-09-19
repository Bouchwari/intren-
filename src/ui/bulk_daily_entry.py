"""Spreadsheet-style entry of real attendance and absence for many days."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    ARABIC_DAY_NAMES, COLOR_ACCENT, COLOR_BORDER, COLOR_PANEL,
    COLOR_PANEL_ALT, COLOR_PAPER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_SECTION, MEAL_LABELS,
)
from core.bulk_daily_entry import save_bulk_daily_entries
from core.models import (
    BulkDailyEntry, DailyAbsence, DailyContact, SchoolSettings,
)
from core.ramadan import meals_for_date
from data.database import (
    get_all_holidays, get_day_absences, get_day_contacts,
    get_ramadan_overrides, get_school_settings,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton


_TITLE = "إدخال الحضور والغياب لعدة أيام"
_SCOPE = "الإعدادي  •  منحة كاملة"
_HEADERS = ["التاريخ", "اليوم", "الوجبة", "الحضور", "الغياب", "الحالة"]
_COL_ATTENDANCE = 3
_COL_ABSENCE = 4
_EDITABLE_COLUMNS = {_COL_ATTENDANCE, _COL_ABSENCE}
_DEFAULT_DAYS = 15
_MAX_RANGE_DAYS = 62
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RowKey:
    date: str
    meal_type: str | None


class _PasteTable(QTableWidget):
    """QTableWidget with multi-cell paste for values copied from Excel."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_text(QApplication.clipboard().text())
            return
        super().keyPressEvent(event)

    def paste_text(
        self, text: str, start_row: int | None = None,
        start_column: int | None = None,
    ) -> None:
        row = self.currentRow() if start_row is None else start_row
        column = self.currentColumn() if start_column is None else start_column
        if row < 0 or column < 0:
            return
        lines = [line for line in text.splitlines() if line.strip()]
        for row_offset, line in enumerate(lines):
            for column_offset, value in enumerate(line.split("\t")):
                target_row = row + row_offset
                target_column = column + column_offset
                if target_row >= self.rowCount() or target_column >= self.columnCount():
                    continue
                item = self.item(target_row, target_column)
                if item is not None and item.flags() & Qt.ItemFlag.ItemIsEditable:
                    item.setText(value.strip())


class BulkDailyEntryDialog(QDialog):
    def __init__(self, default_date: QDate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row_keys: list[_RowKey] = []
        self._saved_count = 0
        self.setWindowTitle(_TITLE)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        self.resize(940, 680)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(f"QDialog {{ background: {COLOR_PAPER}; }}")
        self._build_ui(default_date)
        self._load_rows()

    @property
    def saved_count(self) -> int:
        return self._saved_count

    def _build_ui(self, default_date: QDate) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)
        root.addLayout(self._title_row())
        root.addWidget(self._range_panel(default_date))

        self._table = _PasteTable(0, len(_HEADERS))
        self._configure_table()
        root.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        root.addWidget(self._summary)
        root.addLayout(self._action_row())

    def _title_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title = QLabel(_TITLE)
        font = QFont()
        font.setPointSize(FONT_SECTION)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        scope = QLabel(_SCOPE)
        scope.setStyleSheet(
            f"background:{COLOR_PANEL_ALT}; color:{COLOR_TEXT_PRIMARY};"
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:6px 12px; font-size:{FONT_BODY}px; font-weight:bold;")
        row.addWidget(title)
        row.addStretch()
        row.addWidget(scope)
        return row

    def _range_panel(self, default_date: QDate) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background:{COLOR_PANEL}; border:1px solid {COLOR_BORDER};"
            " border-radius:6px; }} QLabel { border:none; background:transparent; }")
        row = QHBoxLayout(panel)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        self._from = DateInput()
        self._from.setDate(default_date.addDays(-(_DEFAULT_DAYS - 1)))
        self._to = DateInput()
        self._to.setDate(default_date)
        row.addWidget(QLabel("من:"))
        row.addWidget(self._from)
        row.addWidget(QLabel("إلى:"))
        row.addWidget(self._to)
        refresh = IconButton(
            "عرض الأيام", bg=COLOR_ACCENT, text_color="white",
            border_radius=6, padding_h=14, font_size=12, bold=True,
            min_height=36,
        )
        refresh.clicked.connect(self._load_rows)
        row.addWidget(refresh)
        row.addStretch()
        return panel

    def _configure_table(self) -> None:
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background:{COLOR_PANEL}; alternate-background-color:#f7faf9;
                color:{COLOR_TEXT_PRIMARY}; border:1px solid {COLOR_BORDER};
                border-radius:6px; gridline-color:{COLOR_BORDER};
            }}
            QTableWidget::item {{ padding:6px 10px; }}
            QHeaderView::section {{
                background:{COLOR_PANEL_ALT}; color:{COLOR_TEXT_PRIMARY};
                border:none; border-bottom:1px solid {COLOR_BORDER};
                padding:8px 10px; font-weight:bold;
            }}
        """)

    def _action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(self.reject)
        save = IconButton(
            "حفظ الأرقام", bg=COLOR_ACCENT, text_color="white",
            border_radius=6, padding_h=18, font_size=13, bold=True,
            min_height=40,
        )
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addStretch()
        row.addWidget(save)
        return row

    def _load_rows(self) -> None:
        start, end = self._from.date(), self._to.date()
        if end < start:
            QMessageBox.warning(self, "تنبيه", "تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return
        day_count = start.daysTo(end) + 1
        if day_count > _MAX_RANGE_DAYS:
            QMessageBox.warning(
                self, "تنبيه", f"اختر مدة لا تتجاوز {_MAX_RANGE_DAYS} يوماً في كل مرة.")
            return

        self._table.setRowCount(0)
        self._row_keys.clear()
        holiday_labels = {holiday.date: holiday.label for holiday in get_all_holidays()}
        settings = get_school_settings()
        overrides = get_ramadan_overrides()
        day = start
        while day <= end:
            date_str = day.toString("yyyy-MM-dd")
            if date_str in holiday_labels:
                self._append_holiday(day, holiday_labels[date_str])
            else:
                self._append_meals(day, settings, overrides)
            day = day.addDays(1)
        meal_rows = sum(key.meal_type is not None for key in self._row_keys)
        self._summary.setText(f"{day_count} يوم  •  {meal_rows} وجبة")

    def _append_holiday(self, day: QDate, label: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_keys.append(_RowKey(day.toString("yyyy-MM-dd"), None))
        values = [
            day.toString("yyyy-MM-dd"), self._day_name(day),
            f"عطلة: {label}", "", "", "عطلة",
        ]
        for column, value in enumerate(values):
            item = self._item(value, editable=False)
            item.setBackground(Qt.GlobalColor.lightGray)
            self._table.setItem(row, column, item)

    def _append_meals(
        self, day: QDate, settings: SchoolSettings | None,
        overrides: dict[str, bool],
    ) -> None:
        date_str = day.toString("yyyy-MM-dd")
        contacts = {item.meal_type: item for item in get_day_contacts(date_str)}
        absences = {item.meal_type: item for item in get_day_absences(date_str)}
        for meal_type in meals_for_date(date_str, settings, overrides):
            self._append_meal_row(day, meal_type, contacts.get(meal_type), absences.get(meal_type))

    def _append_meal_row(
        self, day: QDate, meal_type: str,
        contact: DailyContact | None, absence: DailyAbsence | None,
    ) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_keys.append(_RowKey(day.toString("yyyy-MM-dd"), meal_type))
        attendance_text = str(contact.collegial_granted) if contact else ""
        absence_text = str(absence.collegial_granted) if absence else ""
        status = "محفوظ" if contact and absence else ("غير مكتمل" if contact or absence else "جديد")
        values = [
            day.toString("yyyy-MM-dd"), self._day_name(day),
            MEAL_LABELS.get(meal_type, meal_type), attendance_text,
            absence_text, status,
        ]
        for column, value in enumerate(values):
            self._table.setItem(
                row, column, self._item(value, editable=column in _EDITABLE_COLUMNS))

    @staticmethod
    def _day_name(day: QDate) -> str:
        return ARABIC_DAY_NAMES[day.dayOfWeek() - 1]

    @staticmethod
    def _item(text: str, *, editable: bool) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _save(self) -> None:
        entries = self._entries_from_table()
        if entries is None:
            return
        if not entries:
            QMessageBox.information(self, "تنبيه", "لم يتم إدخال أي أرقام للحفظ.")
            return
        try:
            save_bulk_daily_entries(entries)
        except Exception as exc:
            _LOGGER.exception("Bulk daily entry save failed")
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ الأرقام:\n{exc}")
            return
        self._saved_count = len(entries)
        QMessageBox.information(
            self, "تم", f"تم حفظ الحضور والغياب لـ {self._saved_count} وجبة بنجاح.")
        self.accept()

    def _entries_from_table(self) -> list[BulkDailyEntry] | None:
        entries: list[BulkDailyEntry] = []
        for row, key in enumerate(self._row_keys):
            if key.meal_type is None:
                continue
            attendance_text = self._table.item(row, _COL_ATTENDANCE).text().strip()
            absence_text = self._table.item(row, _COL_ABSENCE).text().strip()
            if not attendance_text and not absence_text:
                continue
            if not attendance_text or not absence_text:
                missing_column = _COL_ATTENDANCE if not attendance_text else _COL_ABSENCE
                return self._invalid_row(row, missing_column, "أدخل الحضور والغياب معاً لهذه الوجبة.")
            try:
                attendance = int(attendance_text)
                absence = int(absence_text)
            except ValueError:
                return self._invalid_row(row, _COL_ATTENDANCE, "يجب إدخال أعداد صحيحة فقط.")
            if attendance < 0 or absence < 0:
                return self._invalid_row(row, _COL_ATTENDANCE, "لا يمكن إدخال عدد سالب.")
            if absence > attendance:
                return self._invalid_row(row, _COL_ABSENCE, "لا يمكن أن يتجاوز الغياب عدد الحضور.")
            entries.append(BulkDailyEntry(key.date, key.meal_type, attendance, absence))
        return entries

    def _invalid_row(
        self, row: int, column: int, message: str,
    ) -> None:
        self._table.setCurrentCell(row, column)
        self._table.scrollToItem(self._table.item(row, column))
        QMessageBox.warning(self, "تنبيه", message)
        return None
