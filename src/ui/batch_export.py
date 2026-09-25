"""
src/ui/batch_export.py
Shared "do this for a range of days" pieces used to build الصفحة الرئيسية's
"توليد شامل لعدة أيام" flow (see ui/work_pipeline_screen.py):

- pick_date_range(): shows the shared من/إلى dialog, returns the chosen
  (start, end) inclusive range or None if cancelled.
- write_combined_pdf(): draw one page per date in a range onto a single
  shared PDF writer — like a mail merge: one document, not a folder of
  separate files. build_page() decides whether that's real data, a
  "holiday" placeholder, or a "no data entered" placeholder, so a gap is
  explained instead of silently missing.
- draw_placeholder_pdf_page(): the shared placeholder-page drawer used by
  each screen's own build_page() for a holiday or empty date.
- _summarize_combined_pdf(): turns write_combined_pdf()'s (counts,
  failed_dates) result into the Arabic summary message.
"""
from pathlib import Path
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextOption
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
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
_RANGE_ORDER_ERR = "تاريخ \"إلى\" يجب أن يكون بعد تاريخ \"من\"."
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


def write_combined_pdf(
    path: Path,
    start: QDate,
    end: QDate,
    orientation: QPageLayout.Orientation,
    build_page: Callable[[QPainter, float, float, str], str],
    *, print_layout: str = "standard",
) -> Tuple[dict, list]:
    """Core writer, no dialogs: draw one page per date in [start, end]
    (inclusive) onto a single shared QPdfWriter at path — one document,
    not a folder of files. build_page(painter, page_w, page_h, date_str)
    must draw that date's page (real data, or a placeholder — see
    draw_placeholder_pdf_page) and return a category string: "data",
    "holiday", or "empty". Every date gets a page; nothing is silently
    skipped. A date whose build_page raises gets a blank page but doesn't
    stop the rest. Returns (category -> count, failed_dates) for the
    caller to build its own summary — see _summarize_combined_pdf, or
    ui/work_pipeline_screen.py's "generate everything", which drives this
    directly with its own range and writes several documents into one
    chosen folder."""
    if print_layout == "three_copies":
        from ui.pdf_layout import write_copy_sheets

        dates = (start.addDays(i).toString("yyyy-MM-dd")
                 for i in range(start.daysTo(end) + 1))
        return write_copy_sheets(path, dates, build_page)

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

    return counts, failed_dates


def _summarize_combined_pdf(path: Path, counts: dict, failed_dates: list) -> str:
    lines = [f"تم إنشاء المستند: {path.name}"]
    if counts.get("data"):
        lines.append(f"{counts['data']} يوم ببيانات فعلية.")
    if counts.get("holiday"):
        lines.append(f"{counts['holiday']} يوم عطلة.")
    if counts.get("empty"):
        lines.append(f"{counts['empty']} يوم بلا بيانات مسجلة.")
    if failed_dates:
        lines.append(f"تعذر رسم {len(failed_dates)} يوم: " + "، ".join(failed_dates))
    return "\n".join(lines)
