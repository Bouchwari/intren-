"""Explicit review of the supplied annual calendar; no date guesses for Hijri holidays."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QScrollArea, QTableWidget, QVBoxLayout,
)

from config.settings import COLOR_ACCENT, COLOR_BORDER, COLOR_TEXT_PRIMARY, RESOURCE_DIR
from core.holiday_calendar import calendar_days, pending_hijri, validate_calendar_rows
from data.holiday_calendar_repo import get_calendar_state, save_reviewed_calendar
from ui.dialogs import _button


class HolidayCalendarDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("مراجعة لائحة العطل 2026/2027")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(870, 660)
        self.setMinimumSize(640, 460)
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background:white; color:{COLOR_TEXT_PRIMARY}; }}
            QLabel {{ background:transparent; border:0; }}
            QLineEdit, QTableWidget {{ background:white; border:1px solid {COLOR_BORDER}; }}
            QLineEdit {{ padding:4px; }}
            QHeaderView::section {{ background:#edf3f0; color:{COLOR_TEXT_PRIMARY}; padding:6px; border:0; }}
        """)
        self.original = get_calendar_state()["rows"]
        root = QVBoxLayout(self)
        self.table = QTableWidget(len(self.original), 4)
        self.table.setHorizontalHeaderLabels(["اعتماد", "العطلة", "من", "إلى"])
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 68)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, 140)
        self.editors = []
        for index, row in enumerate(self.original):
            enabled = QCheckBox()
            enabled.setAccessibleName(row["label"])
            enabled.setChecked(row["enabled"])
            label = QLabel(row["label"] + ("\n" + row["hijri"] if row["hijri"] else ""))
            label.setWordWrap(True)
            label.setMargin(6)
            first, last = QLineEdit(row["start"]), QLineEdit(row["end"])
            for widget in (first, last):
                widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                widget.setPlaceholderText("YYYY-MM-DD")
                widget.setAccessibleName(row["label"] + (" من" if widget is first else " إلى"))
                widget.textChanged.connect(self._refresh_summary)
            enabled.toggled.connect(self._refresh_summary)
            for col, widget in enumerate((enabled, label, first, last)):
                self.table.setCellWidget(index, col, widget)
            self.editors.append((enabled, first, last))
        header.sectionResized.connect(lambda *_: self._fit_rows())
        root.addWidget(self.table, 1)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.confirm = QCheckBox("راجعت التواريخ وأؤكد إغلاق المطعمة في الأيام المختارة")
        root.addWidget(self.confirm)
        actions = QHBoxLayout()
        self.apply_button = _button("اعتماد اللائحة", primary=True)
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply)
        self.confirm.toggled.connect(self._refresh_summary)
        cancel = _button("إلغاء")
        cancel.clicked.connect(self.reject)
        source = _button("عرض اللائحة الأصلية")
        source.clicked.connect(self._show_source)
        for button in (self.apply_button, cancel, source):
            actions.addWidget(button)
        root.addLayout(actions)
        self._refresh_summary()

    def rows(self) -> list[dict]:
        return [dict(row, enabled=enabled.isChecked(), start=first.text().strip(), end=last.text().strip())
                for row, (enabled, first, last) in zip(self.original, self.editors)]

    def _fit_rows(self) -> None:
        for row in range(self.table.rowCount()):
            label = self.table.cellWidget(row, 1)
            self.table.setRowHeight(row, max(54, label.heightForWidth(self.table.columnWidth(1)) + 8))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_rows()

    def _refresh_summary(self, *_args) -> None:
        if not hasattr(self, "summary"):
            return
        try:
            rows = validate_calendar_rows(self.rows())
            self.summary.setText(f"الأيام المختارة: {len(calendar_days(rows))} | "
                                 f"عطل هجرية دون تاريخ ميلادي مؤكد: {len(pending_hijri(rows))}")
            self.apply_button.setEnabled(self.confirm.isChecked())
        except ValueError as exc:
            self.summary.setText(str(exc))
            self.apply_button.setEnabled(False)
        active = self.apply_button.isEnabled()
        self.apply_button.set_style(bg=COLOR_ACCENT if active else "#e6ebe8",
                                    text_color="white" if active else "#66766f")

    def _apply(self) -> None:
        if not self.confirm.isChecked():
            return
        try:
            added, kept = save_reviewed_calendar(self.rows())
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Cannot apply holiday calendar")
            QMessageBox.warning(self, "خطأ", "تعذر اعتماد اللائحة. لم يتم حفظ التغييرات.")
            return
        QMessageBox.information(self, "تم", f"أضيفت {added} أيام. احتُفظ بـ {kept} أيام موجودة. "
                                "تبقى العطل الهجرية غير المؤكدة قيد المراجعة.")
        self.accept()

    def _show_source(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("اللائحة الأصلية 2026/2027")
        dialog.resize(780, 650)
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        label = QLabel()
        pixmap = QPixmap(str(RESOURCE_DIR / "assets" / "holidays_2026_2027.webp"))
        label.setPixmap(pixmap.scaledToWidth(720, Qt.TransformationMode.SmoothTransformation))
        scroll.setWidget(label)
        layout.addWidget(scroll)
        dialog.exec()
