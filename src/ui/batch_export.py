"""
src/ui/batch_export.py
Shared "generate for a range of days" flow: pick a date range, pick a
folder, then call a per-day export callback once for every date in the
range — used by daily_contact_screen.py and daily_report_screen.py's
"توليد لعدة أيام" buttons instead of exporting one date at a time.

Read-only: it only writes files. It never saves/records anything to the
database, so it can't advance a document-number counter or silently
overwrite a saved report — each date's export is built from whatever is
already saved for it.
"""
from pathlib import Path
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from config.settings import COLOR_ACCENT, COLOR_BORDER, COLOR_PAPER, COLOR_TEXT_PRIMARY, FONT_BODY
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

_TITLE = "توليد لعدة أيام"
_LBL_FROM = "من:"
_LBL_TO = "إلى:"
_BTN_NEXT = "التالي — اختيار المجلد"
_BTN_CANCEL = "إلغاء"
_FOLDER_DIALOG_TITLE = "اختر المجلد لحفظ الملفات"
_RANGE_ORDER_ERR = "تاريخ \"إلى\" يجب أن يكون بعد تاريخ \"من\"."
_RESULT_TITLE = "تم"
_NO_DAYS_MSG = "لا توجد بيانات محفوظة في هذا النطاق — لم يتم إنشاء أي ملف."


class _DateRangeDialog(QDialog):
    """Small من/إلى picker — first step of the batch-export flow."""

    def __init__(self, parent: Optional[QWidget]) -> None:
        super().__init__(parent)
        self.setWindowTitle(_TITLE)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"QDialog {{ background:{COLOR_PAPER}; }} "
                            f"QLabel {{ color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px; }}")
        self._range: Optional[Tuple[QDate, QDate]] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(16)
        root.addWidget(QLabel(_TITLE))

        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        self._from = DateInput()
        self._to = DateInput()
        for field in (self._from, self._to):
            field.setMinimumHeight(34)
            field.setStyleSheet(
                f"background:white; border:1px solid {COLOR_BORDER}; border-radius:8px;"
                f"padding:4px 10px; font-size:{FONT_BODY}px;"
            )
        picker_row.addWidget(QLabel(_LBL_FROM))
        picker_row.addWidget(self._from)
        picker_row.addWidget(QLabel(_LBL_TO))
        picker_row.addWidget(self._to)
        root.addLayout(picker_row)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton(_BTN_CANCEL)
        cancel_btn.clicked.connect(self.reject)
        next_btn = IconButton(
            _BTN_NEXT, bg=COLOR_ACCENT, text_color="white",
            border_radius=8, padding_h=14, font_size=13, bold=False, min_height=36,
        )
        next_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(next_btn)
        root.addLayout(btn_row)

    def _on_confirm(self) -> None:
        start, end = self._from.date(), self._to.date()
        if end < start:
            QMessageBox.warning(self, "تنبيه", _RANGE_ORDER_ERR)
            return
        self._range = (start, end)
        self.accept()

    def chosen_range(self) -> Optional[Tuple[QDate, QDate]]:
        return self._range


def run_batch_export(
    parent: QWidget,
    generate_day: Callable[[str, Path], bool],
) -> None:
    """Ask for a date range then a folder, then call generate_day(date_str,
    folder) once per date (inclusive). generate_day must return True if it
    wrote a file, False if that date had nothing to export — it should not
    raise for "no data", only for a real failure. Shows a summary at the
    end; a date that raises is counted as failed but doesn't stop the rest."""
    dialog = _DateRangeDialog(parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    date_range = dialog.chosen_range()
    if date_range is None:
        return
    start, end = date_range

    folder_str = QFileDialog.getExistingDirectory(parent, _FOLDER_DIALOG_TITLE)
    if not folder_str:
        return
    folder = Path(folder_str)

    total_days = start.daysTo(end) + 1
    done = 0
    failed_dates: list[str] = []
    date = start
    while date <= end:
        date_str = date.toString("yyyy-MM-dd")
        try:
            if generate_day(date_str, folder):
                done += 1
        except Exception:
            failed_dates.append(date_str)
        date = date.addDays(1)

    if done == 0 and not failed_dates:
        QMessageBox.information(parent, _RESULT_TITLE, _NO_DAYS_MSG)
        return

    skipped = total_days - done - len(failed_dates)
    lines = [f"تم إنشاء {done} ملف من أصل {total_days} يوم."]
    if skipped:
        lines.append(f"تم تجاوز {skipped} يوم بلا بيانات محفوظة.")
    if failed_dates:
        lines.append(f"تعذر إنشاء {len(failed_dates)} ملف: " + "، ".join(failed_dates))
    QMessageBox.information(parent, _RESULT_TITLE, "\n".join(lines))
