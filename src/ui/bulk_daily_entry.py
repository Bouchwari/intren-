"""Small export/import dialog for multi-day Excel entry."""
from __future__ import annotations

from datetime import date
import logging
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_PANEL, COLOR_PANEL_ALT, COLOR_PAPER,
    COLOR_TEXT_PRIMARY, FONT_BODY, FONT_SECTION,
)
from core.bulk_daily_entry import save_bulk_daily_entries
from ui.bulk_daily_excel import create_bulk_workbook, load_bulk_workbook
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton


_TITLE = "الإدخال اليومي عبر Excel"
_SCOPE = "الإعدادي  •  منحة كاملة"
_NOTICE = (
    "خانة الغياب اختيارية: إذا تركتها فارغة فسيعتبرها البرنامج 0، "
    "ويمكنك تغييرها لاحقاً."
)
_DEFAULT_DAYS = 15
_MAX_RANGE_DAYS = 62
_LOGGER = logging.getLogger(__name__)


class BulkDailyEntryDialog(QDialog):
    def __init__(self, default_date: QDate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._saved_count = 0
        self.setWindowTitle(_TITLE)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        self.setFixedWidth(680)
        self.setStyleSheet(f"QDialog {{ background: {COLOR_PAPER}; }}")
        self._build_ui(default_date)

    @property
    def saved_count(self) -> int:
        return self._saved_count

    def _build_ui(self, default_date: QDate) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(16)
        root.addLayout(self._title_row())
        root.addWidget(self._notice_panel())
        root.addWidget(self._range_panel(default_date))
        root.addLayout(self._workflow_actions())

        close_row = QHBoxLayout()
        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(self.reject)
        close_row.addWidget(close_button)
        close_row.addStretch()
        root.addLayout(close_row)

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

    def _notice_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background:#FFF7ED; border:1px solid #F59E0B;"
            " border-radius:6px; } QLabel { color:#9A3412; border:none;"
            " background:transparent; font-weight:bold; }")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        notice = QLabel(_NOTICE)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        return panel

    def _range_panel(self, default_date: QDate) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background:{COLOR_PANEL}; border:1px solid {COLOR_BORDER};"
            " border-radius:6px; }} QLabel { border:none; background:transparent; }")
        row = QHBoxLayout(panel)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(10)
        self._from = DateInput()
        self._from.setDate(default_date.addDays(-(_DEFAULT_DAYS - 1)))
        self._to = DateInput()
        self._to.setDate(default_date)
        row.addWidget(QLabel("من:"))
        row.addWidget(self._from)
        row.addWidget(QLabel("إلى:"))
        row.addWidget(self._to)
        row.addStretch()
        return panel

    def _workflow_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        export_button = IconButton(
            "إنشاء نموذج Excel", bg=COLOR_ACCENT, text_color="white",
            border_radius=6, padding_h=18, font_size=13, bold=True,
            min_height=44,
        )
        import_button = IconButton(
            "استيراد Excel وحفظ الأرقام", bg=COLOR_TEXT_PRIMARY,
            text_color="white", border_radius=6, padding_h=18,
            font_size=13, bold=True, min_height=44,
        )
        export_button.clicked.connect(self._export_workbook)
        import_button.clicked.connect(self._import_workbook)
        row.addWidget(export_button)
        row.addWidget(import_button)
        row.addStretch()
        return row

    def _selected_range(self) -> tuple[date, date] | None:
        start_qdate, end_qdate = self._from.date(), self._to.date()
        if end_qdate < start_qdate:
            QMessageBox.warning(self, "تنبيه", "تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
            return None
        if start_qdate.daysTo(end_qdate) + 1 > _MAX_RANGE_DAYS:
            QMessageBox.warning(
                self, "تنبيه", f"اختر مدة لا تتجاوز {_MAX_RANGE_DAYS} يوماً في كل مرة.")
            return None
        return self._python_date(start_qdate), self._python_date(end_qdate)

    @staticmethod
    def _python_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    def _export_workbook(self) -> None:
        selected = self._selected_range()
        if selected is None:
            return
        start, end = selected
        default_name = f"الحضور_والغياب_{start.isoformat()}_إلى_{end.isoformat()}.xlsx"
        path_text, _filter = QFileDialog.getSaveFileName(
            self, "إنشاء نموذج Excel", default_name, "Excel (*.xlsx)")
        if not path_text:
            return
        path = Path(path_text)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        try:
            meal_count = create_bulk_workbook(path, start, end)
        except Exception as exc:
            _LOGGER.exception("Bulk Excel export failed")
            QMessageBox.critical(self, "خطأ", f"تعذر إنشاء ملف Excel:\n{exc}")
            return
        QMessageBox.information(
            self, "تم", f"تم إنشاء نموذج Excel ويحتوي على {meal_count} وجبة.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _import_workbook(self) -> None:
        path_text, _filter = QFileDialog.getOpenFileName(
            self, "استيراد ملف Excel", "", "Excel (*.xlsx)")
        if not path_text:
            return
        try:
            imported = load_bulk_workbook(Path(path_text))
        except Exception as exc:
            _LOGGER.exception("Bulk Excel import failed")
            QMessageBox.critical(self, "خطأ", f"تعذر قراءة ملف Excel:\n{exc}")
            return
        if not imported.entries:
            QMessageBox.information(self, "تنبيه", "لم يتم العثور على أرقام حضور للحفظ.")
            return

        blank_note = (
            f"\nخانات الغياب الفارغة التي ستُحفظ بقيمة 0: {imported.blank_absence_count}"
            if imported.blank_absence_count else ""
        )
        message = (
            f"سيتم حفظ {len(imported.entries)} وجبة من {imported.first_date} "
            f"إلى {imported.last_date}.{blank_note}\n\nهل تريد المتابعة؟"
        )
        answer = QMessageBox.question(
            self, "تأكيد الاستيراد", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            save_bulk_daily_entries(imported.entries)
        except Exception as exc:
            _LOGGER.exception("Bulk Excel save failed")
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ الأرقام:\n{exc}")
            return
        self._saved_count = len(imported.entries)
        QMessageBox.information(
            self, "تم", f"تم حفظ الحضور والغياب لـ {self._saved_count} وجبة بنجاح.")
        self.accept()
