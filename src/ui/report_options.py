"""Report preferences and explicit date-by-date edits before approval."""
import dataclasses
import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QMessageBox, QPushButton, QSlider, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT_PRIMARY
from core.report_defaults import REPORT_SCALES, default_report_preferences
from data.database import get_all_holidays, get_day_contacts, get_day_absences, get_daily_report
from data.settings_repo import get_report_preferences, save_report_preferences
from ui.daily_report_screen import (
    _HYGIENE_ITEMS, _QUALITY_ITEMS, _BUILDING_ITEMS, _HYGIENE_SCALE, _THREE_SCALE,
    _report_for_date,
)
from ui.dialogs import _button

_TITLE = "تفضيلات التقرير اليومي"
_REVIEW = "مراجعة التقارير اليومية"
_HEADERS = ["المؤشر", "التقييم المعتاد", "البديل الأول", "البديل الثاني"]
_VARIATION = "نسبة التنويع: {value}%"
_ALTERNATIVE_HINT = "عند التنويع، يتكرر البديل الأول ضعف البديل الثاني."
_SUGGESTION_HINT = "تقييمات مقترحة للمراجعة، وليست نتائج معاينة."
_MANUAL = "يدوي"
_NONE = "بدون"
_SAVE = "حفظ تفضيلات التقرير"
_RESET = "استعادة الافتراضي"
_SAVED = "تم حفظ تفضيلات التقرير."
_ERROR = "تعذر حفظ التفضيلات. حاول مرة أخرى."
_OK = "اعتماد التقارير"
_CANCEL = "إلغاء"
_NOTES = "ملاحظات اليوم"
_STATUS_SAVED = "محفوظ"
_STATUS_NEW = "جديد"
_PROTECTED = "تقرير محفوظ"
_DRAFT = "تقرير جديد"
_NO_DAYS = "لا توجد أيام لها بيانات داخل هذه المدة."
_RANGE_ERROR = "اختر مدة صحيحة لا تتجاوز 366 يوما."
_ITEMS = _HYGIENE_ITEMS + _QUALITY_ITEMS + _BUILDING_ITEMS
_LOGGER = logging.getLogger(__name__)


def _rating_combo(field: str, empty_label: str) -> QComboBox:
    combo = QComboBox()
    combo.addItem(empty_label, -1)
    scale = _HYGIENE_SCALE if REPORT_SCALES[field] == 6 else _THREE_SCALE
    for index, label in enumerate(scale):
        combo.addItem(label, index)
    combo.setMinimumHeight(32)
    combo.setMinimumWidth(130)
    return combo


def _indicator(table: QTableWidget, row: int, text: str) -> None:
    item = QTableWidgetItem()
    item.setData(Qt.ItemDataRole.AccessibleTextRole, text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, 0, item)
    label = QLabel(text)
    label.setWordWrap(True)
    label.setMargin(8)
    label.setToolTip(text)
    label.setStyleSheet(f"background:transparent; color:{COLOR_TEXT_PRIMARY}; border:0;")
    table.setCellWidget(row, 0, label)


def _fit_rating_rows(table: QTableWidget, width: int | None = None) -> None:
    # Labels wrap as the window changes; editors always retain their full height.
    for row in range(table.rowCount()):
        label = table.cellWidget(row, 0)
        editor_height = max(table.cellWidget(row, col).sizeHint().height() + 8
                            for col in range(1, table.columnCount()))
        label_width = width if width is not None else table.columnWidth(0)
        height = max(48, editor_height, label.heightForWidth(label_width))
        if table.rowHeight(row) != height:
            table.setRowHeight(row, height)


class ReportPreferencesWidget(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(_TITLE, parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMaximumWidth(1120)
        self.setStyleSheet(f"""
            QGroupBox {{ background:white; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:6px; margin-top:12px; }}
            QGroupBox::title {{ subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; background:white; }}
            QLabel {{ background:white; color:{COLOR_TEXT_PRIMARY}; border:0; }}
            QTableWidget {{ background:white; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; gridline-color:{COLOR_BORDER}; }}
            QHeaderView::section {{ background:#f0f3f2; color:{COLOR_TEXT_PRIMARY};
                border:0; border-bottom:1px solid {COLOR_BORDER}; padding:6px; }}
            QComboBox {{ background:white; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:3px; padding:2px 6px; }}
            QComboBox:disabled {{ color:#758078; background:#f0f3f2; }}
            QComboBox QAbstractItemView {{ background:white; color:{COLOR_TEXT_PRIMARY};
                selection-background-color:{COLOR_ACCENT}; selection-color:white; }}
            QSlider::groove:horizontal {{ height:6px; background:#d7dfdc; border-radius:3px; }}
            QSlider::handle:horizontal {{ background:{COLOR_ACCENT}; width:18px;
                margin:-6px 0; border-radius:9px; }}
            QPushButton {{ background:white; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:4px; padding:7px 12px; }}
            QPushButton:hover {{ background:#edf5f1; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 24, 16, 16)
        slider_row = QHBoxLayout()
        self.variation_label = QLabel()
        self.variation = QSlider(Qt.Orientation.Horizontal)
        self.variation.setRange(0, 100)
        self.variation.setSingleStep(5)
        self.variation.setAccessibleName(_TITLE)
        self.variation.setToolTip(_SUGGESTION_HINT)
        self.variation.valueChanged.connect(
            lambda value: self.variation_label.setText(_VARIATION.format(value=value)))
        slider_row.addWidget(self.variation_label)
        slider_row.addWidget(self.variation, 1)
        root.addLayout(slider_row)
        self.table = QTableWidget(len(_ITEMS), 4)
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().hide()
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.horizontalHeader().setMinimumSectionSize(140)
        self.table.setMinimumHeight(300)
        self.table.setMaximumHeight(410)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.combos = {}
        for column in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for row, (field, label) in enumerate(_ITEMS):
            _indicator(self.table, row, label)
            combos = [_rating_combo(field, _MANUAL), _rating_combo(field, _NONE),
                      _rating_combo(field, _NONE)]
            self.combos[field] = combos
            for col, combo in enumerate(combos, 1):
                self.table.setCellWidget(row, col, combo)
                combo.setToolTip(_ALTERNATIVE_HINT if col > 1 else _SUGGESTION_HINT)
            combos[0].currentIndexChanged.connect(
                lambda _index, field=field: self._update_alternatives(field))
        root.addWidget(self.table)
        actions = QHBoxLayout()
        save = QPushButton(_SAVE)
        save.clicked.connect(self.save)
        reset = QPushButton(_RESET)
        reset.clicked.connect(lambda: self.set_preferences(default_report_preferences()))
        actions.addWidget(save)
        actions.addWidget(reset)
        actions.addStretch()
        root.addLayout(actions)
        self.table.horizontalHeader().sectionResized.connect(
            lambda column, _old, width: _fit_rating_rows(self.table, width)
            if column == 0 else None)
        self.reload()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Measure after the real app and parent styles have been applied.
        _fit_rating_rows(self.table)

    def _update_alternatives(self, field: str) -> None:
        base, *alternatives = self.combos[field]
        for combo in alternatives:
            combo.setEnabled(base.currentData() != -1)

    def reload(self) -> None:
        self.set_preferences(get_report_preferences())

    def set_preferences(self, prefs: dict) -> None:
        self.variation.setValue(prefs["variation"])
        self.variation_label.setText(_VARIATION.format(value=prefs["variation"]))
        for field, combos in self.combos.items():
            rule = prefs["rules"][field]
            values = [rule["base"], *(rule["alternatives"] + [-1, -1])[:2]]
            for combo, value in zip(combos, values):
                combo.setCurrentIndex(combo.findData(value))
            self._update_alternatives(field)

    def preferences(self) -> dict:
        return {"variation": self.variation.value(), "rules": {
            field: {"base": combos[0].currentData(),
                    "alternatives": [combo.currentData() for combo in combos[1:]
                                     if combo.currentData() != -1]}
            for field, combos in self.combos.items()}}

    def save(self) -> None:
        try:
            save_report_preferences(self.preferences())
        except Exception:
            _LOGGER.exception("Cannot save daily report preferences")
            QMessageBox.warning(self, _TITLE, _ERROR)
            return
        QMessageBox.information(self, _TITLE, _SAVED)


class ReportReviewDialog(QDialog):
    def __init__(self, dates: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_REVIEW)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(940, 650)
        self.setMinimumSize(640, 460)
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background:white; color:{COLOR_TEXT_PRIMARY}; }}
            QTableWidget, QListWidget, QTextEdit {{ background:white;
                color:{COLOR_TEXT_PRIMARY}; border:1px solid {COLOR_BORDER}; }}
            QComboBox {{ background:white; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; padding:2px 6px; border-radius:3px; }}
            QComboBox:disabled {{ background:#f0f3f2; color:{COLOR_TEXT_PRIMARY}; }}
            QListWidget::item:selected {{ background:{COLOR_ACCENT}; color:white; }}
            QHeaderView::section {{ background:#f0f3f2; color:{COLOR_TEXT_PRIMARY};
                padding:6px; border:0; border-bottom:1px solid {COLOR_BORDER}; }}
        """)
        self._dates = dates
        self._drafts = {day: _report_for_date(day) for day in dates}
        self._originals = dict(self._drafts)
        self._current = None
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.days = QListWidget()
        self.days.setMinimumWidth(150)
        self.days.setMaximumWidth(230)
        for day in dates:
            status = _STATUS_SAVED if self._drafts[day].id is not None else _STATUS_NEW
            self.days.addItem(f"{day}  {status}")
        split.addWidget(self.days)
        detail = QWidget()
        form = QVBoxLayout(detail)
        self.status = QLabel()
        form.addWidget(self.status)
        self.table = QTableWidget(len(_ITEMS), 2)
        self.table.setHorizontalHeaderLabels([_HEADERS[0], _HEADERS[1]])
        self.table.verticalHeader().hide()
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.horizontalHeader().setMinimumSectionSize(140)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.combos = {}
        for row, (field, label) in enumerate(_ITEMS):
            _indicator(self.table, row, label)
            self.combos[field] = _rating_combo(field, _MANUAL)
            self.table.setCellWidget(row, 1, self.combos[field])
        form.addWidget(self.table, 1)
        form.addWidget(QLabel(_NOTES))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(100)
        form.addWidget(self.notes)
        split.addWidget(detail)
        split.setStretchFactor(1, 1)
        root.addWidget(split, 1)
        actions = QHBoxLayout()
        approve = _button(_OK, primary=True)
        approve.setAccessibleName(_OK)
        approve.clicked.connect(self.accept)
        cancel = _button(_CANCEL)
        cancel.setObjectName("reportReviewCancel")
        cancel.setAccessibleName(_CANCEL)
        cancel.set_style(hover_bg="#d1e8dd")
        cancel.clicked.connect(self.reject)
        actions.addWidget(approve)
        actions.addWidget(cancel)
        actions.addStretch()
        root.addLayout(actions)
        self.table.horizontalHeader().sectionResized.connect(
            lambda column, _old, width: _fit_rating_rows(self.table, width)
            if column == 0 else None)
        self.days.currentRowChanged.connect(self._select_day)
        if dates:
            self.days.setCurrentRow(0)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        _fit_rating_rows(self.table)

    def _stash(self) -> None:
        if self._current is None:
            return
        values = {field: combo.currentData() for field, combo in self.combos.items()}
        self._drafts[self._current] = dataclasses.replace(
            self._drafts[self._current], notes=self.notes.toPlainText(), **values)

    def _select_day(self, row: int) -> None:
        self._stash()
        if row < 0:
            return
        self._current = self._dates[row]
        report = self._drafts[self._current]
        saved = report.id is not None
        self.status.setText(f"{self._current}  |  {_PROTECTED if saved else _DRAFT}")
        for field, combo in self.combos.items():
            combo.setCurrentIndex(combo.findData(getattr(report, field)))
            combo.setEnabled(True)
        self.notes.setPlainText(report.notes)
        self.notes.setReadOnly(False)

    def overrides(self) -> dict[str, dict]:
        self._stash()
        result = {}
        for day, report in self._drafts.items():
            values = {field: getattr(report, field) for field in (*REPORT_SCALES, "notes")
                      if report.id is None or getattr(report, field) != getattr(self._originals[day], field)}
            if values:
                result[day] = values
        return result


def review_report_range(parent: QWidget, start: QDate, end: QDate,
                        *, include_empty: bool = False) -> dict[str, dict] | None:
    if not start.isValid() or not end.isValid() or not 0 <= start.daysTo(end) < 366:
        QMessageBox.warning(parent, _REVIEW, _RANGE_ERROR)
        return None
    holidays = {item.date for item in get_all_holidays()}
    dates = []
    for offset in range(start.daysTo(end) + 1):
        day = start.addDays(offset).toString("yyyy-MM-dd")
        if day not in holidays and (include_empty or get_daily_report(day) or get_day_contacts(day) or get_day_absences(day)):
            dates.append(day)
    if not dates:
        if not include_empty:
            QMessageBox.information(parent, _REVIEW, _NO_DAYS)
        return {}
    dialog = ReportReviewDialog(dates, parent)
    return dialog.overrides() if dialog.exec() == QDialog.DialogCode.Accepted else None
