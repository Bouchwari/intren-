"""
src/ui/batch_export.py
Shared "do this for a range of days" flow. Two entry points share the
same من/إلى date picker and per-day loop:

- run_batch_export(): pick a range, then a folder, then write one file
  per date — used by the "توليد لعدة أيام" export buttons. Read-only: it
  only writes files, never saves/records to the database.
- run_batch_generate_data(): pick a range, then call a callback once per
  date that fills in and SAVES real numbers (e.g. the same estimator
  behind "توليد تلقائي", just run over many days) — used by the
  "توليد الأرقام لعدة أيام" buttons. No folder step, since nothing is
  written to disk.
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
_NO_DAYS_GENERATED_MSG = "لم يتم توليد أي يوم — كل الأيام في هذا النطاق إما بها بيانات مسبقًا أو أيام عطل."


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


def pick_date_range(parent: QWidget) -> Optional[Tuple[QDate, QDate]]:
    """Show the من/إلى dialog, return the chosen (start, end) inclusive
    range or None if cancelled. Shared first step of every batch action."""
    dialog = _DateRangeDialog(parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.chosen_range()


def _run_over_range(
    start: QDate, end: QDate, process_day: Callable[[str], bool]
) -> Tuple[int, list]:
    """Call process_day(date_str) once per date in [start, end] inclusive.
    Returns (done_count, failed_dates) — a date that raises counts as
    failed but doesn't stop the rest."""
    done = 0
    failed_dates: list = []
    date = start
    while date <= end:
        date_str = date.toString("yyyy-MM-dd")
        try:
            if process_day(date_str):
                done += 1
        except Exception:
            failed_dates.append(date_str)
        date = date.addDays(1)
    return done, failed_dates


def run_batch_export(
    parent: QWidget,
    generate_day: Callable[[str, Path], bool],
) -> None:
    """Ask for a date range then a folder, then call generate_day(date_str,
    folder) once per date (inclusive). generate_day must return True if it
    wrote a file, False if that date had nothing to export — it should not
    raise for "no data", only for a real failure. Shows a summary at the
    end; a date that raises is counted as failed but doesn't stop the rest."""
    date_range = pick_date_range(parent)
    if date_range is None:
        return
    start, end = date_range

    folder_str = QFileDialog.getExistingDirectory(parent, _FOLDER_DIALOG_TITLE)
    if not folder_str:
        return
    folder = Path(folder_str)

    total_days = start.daysTo(end) + 1
    done, failed_dates = _run_over_range(start, end, lambda date_str: generate_day(date_str, folder))

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


def run_batch_generate_data(
    parent: QWidget,
    generate_day: Callable[[str], bool],
) -> None:
    """Ask for a date range, then call generate_day(date_str) once per date
    (inclusive) — no folder step, since this saves numbers to the database
    instead of writing files. generate_day must return True if it filled
    in and saved that date, False if it was skipped (already has data, or
    a real holiday) — it should not raise for a normal skip, only for a
    real failure. Shows a summary at the end."""
    date_range = pick_date_range(parent)
    if date_range is None:
        return
    start, end = date_range

    total_days = start.daysTo(end) + 1
    done, failed_dates = _run_over_range(start, end, generate_day)

    if done == 0 and not failed_dates:
        QMessageBox.information(parent, _RESULT_TITLE, _NO_DAYS_GENERATED_MSG)
        return

    skipped = total_days - done - len(failed_dates)
    lines = [f"تم توليد أرقام {done} يوم من أصل {total_days} يوم."]
    if skipped:
        lines.append(f"تم تجاوز {skipped} يوم (بيانات محفوظة مسبقًا أو يوم عطلة).")
    if failed_dates:
        lines.append(f"تعذر توليد {len(failed_dates)} يوم: " + "، ".join(failed_dates))
    QMessageBox.information(parent, _RESULT_TITLE, "\n".join(lines))
