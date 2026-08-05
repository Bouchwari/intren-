"""
src/ui/batch_export.py
Shared "do this for a range of days" flow. Entry points share the same
من/إلى date picker and per-day loop:

- run_batch_combined_pdf(): pick a range, then ONE output PDF file, then
  draw one page per date onto a single shared writer — like a mail merge:
  one document to print, not a folder of separate files. Every date in
  the range gets a page — build_page() decides whether that's real data,
  a "holiday" placeholder, or a "no data entered" placeholder, so a gap
  is explained instead of silently missing. Used by the "توليد لعدة أيام"
  export buttons.
- run_batch_generate_data(): pick a range, then call a callback once per
  date that fills in and SAVES real numbers (e.g. the same estimator
  behind "توليد تلقائي", just run over many days) — used by the
  "توليد الأرقام لعدة أيام" buttons. No file step, since nothing is
  written to disk, only saved to the database.
"""
from pathlib import Path
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextOption
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_PAPER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, FONT_BODY,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

_TITLE = "توليد لعدة أيام"
_LBL_FROM = "من:"
_LBL_TO = "إلى:"
_BTN_NEXT = "التالي — اختيار الملف"
_BTN_CANCEL = "إلغاء"
_SAVE_DIALOG_TITLE = "حفظ المستند المجمّع"
_PDF_FILTER = "PDF (*.pdf)"
_RANGE_ORDER_ERR = "تاريخ \"إلى\" يجب أن يكون بعد تاريخ \"من\"."
_RESULT_TITLE = "تم"
_NO_DAYS_GENERATED_MSG = "لم يتم توليد أي يوم — كل الأيام في هذا النطاق إما بها بيانات مسبقًا أو أيام عطل."
_PAGE_LABEL_HOLIDAY = "يوم عطلة"
_PAGE_MSG_HOLIDAY = "📅 عطلة: {label}"
_PAGE_MSG_HOLIDAY_NO_LABEL = "📅 يوم عطلة"
_PAGE_LABEL_EMPTY = "لا توجد بيانات"
_PAGE_MSG_EMPTY = "لم يتم تسجيل بيانات لهذا اليوم بعد."


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


def draw_placeholder_pdf_page(
    painter: QPainter, page_w: float, page_h: float, heading: str, message: str,
) -> None:
    """A simple centered notice page — used for a date with nothing real
    to show (a holiday, or just nothing entered yet) inside a combined
    batch document, so a gap in the range is explained on its own page
    instead of silently missing from the file."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 38.0
    content_w = page_w - (margin * 2)

    heading_font = QFont()
    heading_font.setPointSize(16)
    heading_font.setBold(True)
    painter.setFont(heading_font)
    painter.setPen(QColor(COLOR_TEXT_PRIMARY))
    heading_option = QTextOption()
    heading_option.setTextDirection(Qt.LayoutDirection.RightToLeft)
    heading_option.setAlignment(Qt.AlignmentFlag.AlignCenter)
    painter.drawText(QRectF(margin, page_h / 2 - 70, content_w, 40), heading, heading_option)

    message_font = QFont()
    message_font.setPointSize(12)
    painter.setFont(message_font)
    painter.setPen(QColor(COLOR_TEXT_SECONDARY))
    message_option = QTextOption()
    message_option.setTextDirection(Qt.LayoutDirection.RightToLeft)
    message_option.setAlignment(Qt.AlignmentFlag.AlignCenter)
    message_option.setWrapMode(QTextOption.WrapMode.WordWrap)
    painter.drawText(QRectF(margin, page_h / 2 - 20, content_w, 60), message, message_option)


def run_batch_combined_pdf(
    parent: QWidget,
    default_filename: str,
    orientation: QPageLayout.Orientation,
    build_page: Callable[[QPainter, float, float, str], str],
) -> None:
    """Ask for a date range, then ONE output PDF path, then draw one page
    per date (inclusive) onto a single shared writer — one document, not
    a folder of files. build_page(painter, page_w, page_h, date_str) must
    draw that date's page (real data, or a placeholder — see
    draw_placeholder_pdf_page) and return a category string used only for
    the closing summary: "data", "holiday", or "empty". Every date gets a
    page; nothing is silently skipped. A date whose build_page raises gets
    a blank page but doesn't stop the rest of the batch."""
    date_range = pick_date_range(parent)
    if date_range is None:
        return
    start, end = date_range

    suggested = f"{default_filename}_{start.toString('yyyy-MM-dd')}_إلى_{end.toString('yyyy-MM-dd')}.pdf"
    path_str, _ = QFileDialog.getSaveFileName(parent, _SAVE_DIALOG_TITLE, suggested, _PDF_FILTER)
    if not path_str:
        return
    path = Path(path_str)
    if path.suffix.lower() != ".pdf":
        path = path.with_suffix(".pdf")
    path.parent.mkdir(parents=True, exist_ok=True)

    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(orientation)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)

    counts: dict = {}
    failed_dates: list = []
    painter = QPainter(writer)
    try:
        page_w, page_h = float(writer.width()), float(writer.height())
        date = start
        first = True
        while date <= end:
            date_str = date.toString("yyyy-MM-dd")
            if not first:
                writer.newPage()
            first = False
            try:
                category = build_page(painter, page_w, page_h, date_str)
                counts[category] = counts.get(category, 0) + 1
            except Exception:
                failed_dates.append(date_str)
            date = date.addDays(1)
    finally:
        painter.end()

    lines = [f"تم إنشاء المستند: {path.name}"]
    if counts.get("data"):
        lines.append(f"{counts['data']} يوم ببيانات فعلية.")
    if counts.get("holiday"):
        lines.append(f"{counts['holiday']} يوم عطلة.")
    if counts.get("empty"):
        lines.append(f"{counts['empty']} يوم بلا بيانات مسجلة.")
    if failed_dates:
        lines.append(f"تعذر رسم {len(failed_dates)} يوم: " + "، ".join(failed_dates))
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
