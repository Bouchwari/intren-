"""
src/ui/work_pipeline_screen.py
يوم العمل — the day's paperwork at a glance: status of the 3 daily
documents (contact sheet, absence sheet, daily report) for a selected
date, with a one-click jump to fix anything missing, and a single
"generate everything" action that can auto-fill missing numbers and
export combined PDFs for one day or a whole range at once.
"""
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont, QPageLayout
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_PAPER, COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION, FONT_TITLE,
)
from core.contact_counts import count_students
from core.document_pipeline import (
    DOC_ABSENCE, DOC_CONTACT, DOC_ORDER_LETTER, DOC_RECEPTION, DOC_REPORT,
    PipelineItem, get_daily_pipeline_status,
)
from data.database import (
    get_all_holidays, get_all_students, get_recent_absences, get_recent_contacts, get_school_settings,
)
from ui.batch_export import _summarize_combined_pdf, pick_date_range, write_combined_pdf
from ui.daily_absence_screen import build_absence_pdf_page, generate_and_save_absence_for_date
from ui.daily_contact_screen import build_contact_pdf_page, generate_and_save_contact_for_date
from ui.daily_reception_screen import build_reception_pdf_page
from ui.daily_report_screen import build_report_pdf_page
from ui.order_letter_screen import build_order_letter_pdf_page
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE = "يوم العمل"
_SUBTITLE = "حالة وثائق اليوم — وتوليدها كلها بضغطة واحدة"
_BTN_TODAY = "اليوم"
_BTN_PREV = "اليوم السابق"
_BTN_NEXT = "اليوم التالي"
_BTN_GENERATE_ALL = "توليد شامل لعدة أيام"
_BTN_GENERATE_ALL_ICON = "🗂"
_LBL_DATE = "التاريخ:"
_CHIP_READY = "جاهز"
_CHIP_NEEDS_ACTION = "بحاجة لإدخال"
_BTN_FIX = "فتح الوثيقة"
_TOAST_NO_STUDENTS = "لا يوجد تلاميذ في اللائحة — استورد اللائحة أولاً من صفحة التلاميذ."
_TOAST_NO_CLASSIFIED_STUDENTS = (
    "لم يتم التعرف على قسم أي تلميذ — تأكد من ملء حقل \"القسم\" في لائحة التلاميذ."
)

# key -> (icon, screen index to jump to when not ready)
_DOC_ICON = {
    DOC_CONTACT: "📋", DOC_ABSENCE: "📉", DOC_REPORT: "📄",
    DOC_ORDER_LETTER: "✉️", DOC_RECEPTION: "🧾",
}
_DOC_TARGET_SCREEN = {
    DOC_CONTACT: 4, DOC_ABSENCE: 5, DOC_ORDER_LETTER: 6, DOC_REPORT: 7, DOC_RECEPTION: 8,
}
_DOC_PDF_NAME = {
    DOC_CONTACT: "ورقة_الاتصال_اليومية",
    DOC_ABSENCE: "ورقة_الغياب_اليومية",
    DOC_REPORT: "التقرير_اليومي",
    DOC_ORDER_LETTER: "رسالة_الطلبية",
    DOC_RECEPTION: "محضر_تسليم_الخدمة_اليومي",
}
_DOC_ORIENTATION = {
    DOC_CONTACT: QPageLayout.Orientation.Portrait,
    DOC_ABSENCE: QPageLayout.Orientation.Portrait,
    DOC_REPORT: QPageLayout.Orientation.Landscape,
    DOC_ORDER_LETTER: QPageLayout.Orientation.Portrait,
    DOC_RECEPTION: QPageLayout.Orientation.Portrait,
}


class _PipelineCard(QFrame):
    """One document's status row — icon, name, status chip, detail line,
    and a jump-to-fix button when it still needs data."""

    def __init__(self, item: PipelineItem, on_fix: Callable[[], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: white;
                border: 1px solid {COLOR_SUCCESS if item.ready else COLOR_BORDER};
                border-radius: 12px;
            }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        icon = QLabel(_DOC_ICON.get(item.key, "📄"))
        icon.setStyleSheet("font-size: 22px; background: transparent; border: none;")
        row.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(item.label)
        name_font = QFont(); name_font.setPointSize(FONT_BODY); name_font.setBold(True)
        name.setFont(name_font)
        name.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;")
        detail = QLabel(item.detail)
        detail.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px; background:transparent; border:none;"
        )
        detail.setWordWrap(True)
        text_col.addWidget(name)
        text_col.addWidget(detail)
        row.addLayout(text_col, 1)

        chip = QLabel(_CHIP_READY if item.ready else _CHIP_NEEDS_ACTION)
        chip_bg = COLOR_SUCCESS if item.ready else "#D97706"
        chip.setStyleSheet(
            f"background:{chip_bg}; color:white; font-size:{FONT_CAPTION}px; font-weight:bold;"
            "border-radius:10px; padding:4px 12px;"
        )
        row.addWidget(chip)

        if not item.ready:
            fix_btn = IconButton(
                _BTN_FIX, bg=COLOR_ACCENT, text_color="white",
                border_radius=8, padding_h=12, font_size=12, bold=False, min_height=30,
            )
            fix_btn.clicked.connect(lambda _checked=False: on_fix())
            row.addWidget(fix_btn)


class _GenerateEverythingDialog(QDialog):
    """Range + which documents + whether to auto-fill missing numbers
    first — the one dialog behind "توليد شامل لعدة أيام"."""

    def __init__(self, default_date: QDate, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_BTN_GENERATE_ALL)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"QDialog {{ background:{COLOR_PAPER}; }} "
                            f"QLabel {{ color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px; }}")
        self._result: Optional[Tuple[QDate, QDate, List[str], bool]] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)
        root.addWidget(QLabel(_BTN_GENERATE_ALL))

        range_row = QHBoxLayout()
        self._from = DateInput()
        self._from.setDate(default_date)
        self._to = DateInput()
        self._to.setDate(default_date)
        for field in (self._from, self._to):
            field.setMinimumHeight(34)
            field.setStyleSheet(
                f"background:white; border:1px solid {COLOR_BORDER}; border-radius:8px;"
                f"padding:4px 10px; font-size:{FONT_BODY}px;"
            )
        range_row.addWidget(QLabel("من:"))
        range_row.addWidget(self._from)
        range_row.addWidget(QLabel("إلى:"))
        range_row.addWidget(self._to)
        root.addLayout(range_row)

        docs_label = QLabel("الوثائق:")
        docs_label.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-weight:bold;")
        root.addWidget(docs_label)

        self._doc_checks: Dict[str, QCheckBox] = {}
        for key, label in (
            (DOC_CONTACT, "ورقة الاتصال اليومية"),
            (DOC_ABSENCE, "ورقة الغياب اليومي"),
            (DOC_REPORT, "التقرير اليومي"),
            (DOC_ORDER_LETTER, "رسالة الطلبية — رسالة جديدة مرقّمة لكل يوم"),
            (DOC_RECEPTION, "محضر التسلم اليومي"),
        ):
            check = QCheckBox(label)
            check.setChecked(True)
            self._doc_checks[key] = check
            root.addWidget(check)

        self._auto_fill_check = QCheckBox("توليد الأرقام الناقصة تلقائيًا قبل التصدير")
        self._auto_fill_check.setChecked(True)
        root.addWidget(self._auto_fill_check)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("إلغاء")
        cancel_btn.clicked.connect(self.reject)
        next_btn = IconButton(
            "التالي — اختيار المجلد", bg=COLOR_ACCENT, text_color="white",
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
            QMessageBox.warning(self, "تنبيه", "تاريخ \"إلى\" يجب أن يكون بعد تاريخ \"من\".")
            return
        chosen = [key for key, check in self._doc_checks.items() if check.isChecked()]
        if not chosen:
            QMessageBox.warning(self, "تنبيه", "اختر وثيقة واحدة على الأقل.")
            return
        self._result = (start, end, chosen, self._auto_fill_check.isChecked())
        self.accept()

    def result_choice(self) -> Optional[Tuple[QDate, QDate, List[str], bool]]:
        return self._result


class WorkPipelineScreen(QWidget):
    """يوم العمل — the app's landing screen."""

    def __init__(self, navigate_to: Callable[[int], None]) -> None:
        super().__init__()
        self._navigate = navigate_to
        self.setStyleSheet(f"background:{COLOR_PAPER};")
        self._build_ui()
        self.refresh()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(16)

        header = QVBoxLayout()
        title = QLabel(_TITLE)
        title_font = QFont(); title_font.setPointSize(FONT_TITLE); title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        subtitle = QLabel(_SUBTITLE)
        subtitle.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        date_row = QHBoxLayout()
        date_row.setSpacing(8)
        date_row.addWidget(QLabel(_LBL_DATE, styleSheet=f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px;"))
        self._date_edit = DateInput()
        self._date_edit.setMinimumHeight(36)
        self._date_edit.setStyleSheet(
            f"background:white; border:1px solid {COLOR_BORDER}; border-radius:10px;"
            f"padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        self._date_edit.dateChanged.connect(lambda _d: self.refresh())
        date_row.addWidget(self._date_edit)

        prev_btn = self._nav_btn(_BTN_PREV)
        prev_btn.clicked.connect(self._go_prev)
        today_btn = self._nav_btn(_BTN_TODAY)
        today_btn.clicked.connect(self._go_today)
        next_btn = self._nav_btn(_BTN_NEXT)
        next_btn.clicked.connect(self._go_next)
        date_row.addWidget(next_btn)
        date_row.addWidget(today_btn)
        date_row.addWidget(prev_btn)
        date_row.addStretch()

        generate_btn = IconButton(
            _BTN_GENERATE_ALL, icon=_BTN_GENERATE_ALL_ICON, bg=COLOR_ACCENT, text_color="white",
            border_radius=10, padding_h=16, font_size=13, bold=True, min_height=40,
        )
        generate_btn.clicked.connect(self._on_generate_everything)
        date_row.addWidget(generate_btn)
        root.addLayout(date_row)

        self._cards_container = QVBoxLayout()
        self._cards_container.setSpacing(10)
        root.addLayout(self._cards_container)
        root.addStretch()

    def _nav_btn(self, label: str) -> QPushButton:
        return IconButton(
            label, bg=COLOR_TEXT_PRIMARY, text_color="white",
            border_radius=8, padding_h=12, font_size=12, bold=False, min_height=32,
        )

    # ── Date navigation ────────────────────────────────────────────────────

    def _go_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self.refresh()

    def _go_prev(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self.refresh()

    def _go_next(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self.refresh()

    # ── Refresh ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        while self._cards_container.count():
            item = self._cards_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # setParent(None) detaches (and hides) it immediately —
                # deleteLater() alone leaves it painting at its old
                # position until the event loop gets around to it, which
                # ghosts stale cards for a frame when refresh() fires
                # more than once in quick succession (e.g. clicking
                # through dates fast).
                widget.setParent(None)
                widget.deleteLater()

        date_str = self._date_edit.date().toString("yyyy-MM-dd")
        for pipeline_item in get_daily_pipeline_status(date_str):
            target = _DOC_TARGET_SCREEN[pipeline_item.key]
            card = _PipelineCard(pipeline_item, on_fix=lambda t=target: self._navigate(t))
            self._cards_container.addWidget(card)

    # ── Generate everything ────────────────────────────────────────────────

    def _on_generate_everything(self) -> None:
        dialog = _GenerateEverythingDialog(self._date_edit.date(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        choice = dialog.result_choice()
        if choice is None:
            return
        start, end, doc_keys, auto_fill = choice

        folder_str = QFileDialog.getExistingDirectory(self, "اختر مجلد حفظ الوثائق")
        if not folder_str:
            return
        folder = Path(folder_str)

        if auto_fill and (DOC_CONTACT in doc_keys or DOC_ABSENCE in doc_keys):
            self._auto_fill_range(start, end, doc_keys)

        settings = get_school_settings()
        summaries: List[str] = []
        for key in doc_keys:
            path = folder / (
                f"{_DOC_PDF_NAME[key]}_{start.toString('yyyy-MM-dd')}_إلى_{end.toString('yyyy-MM-dd')}.pdf"
            )
            build_page = self._page_builder(key, settings)
            counts, failed_dates = write_combined_pdf(path, start, end, _DOC_ORIENTATION[key], build_page)
            summaries.append(_summarize_combined_pdf(path, counts, failed_dates))

        self.refresh()
        QMessageBox.information(self, "تم", "\n\n".join(summaries))

    def _page_builder(self, key: str, settings) -> Callable:
        holiday_labels = {h.date: h.label for h in get_all_holidays()}

        if key == DOC_CONTACT:
            return lambda painter, w, h, d: build_contact_pdf_page(painter, w, h, d, holiday_labels, settings)
        if key == DOC_ABSENCE:
            return lambda painter, w, h, d: build_absence_pdf_page(painter, w, h, d, holiday_labels, settings)
        if key == DOC_ORDER_LETTER:
            return lambda painter, w, h, d: build_order_letter_pdf_page(painter, w, h, d, holiday_labels, settings)
        if key == DOC_RECEPTION:
            return lambda painter, w, h, d: build_reception_pdf_page(painter, w, h, d, holiday_labels, settings)
        return lambda painter, w, h, d: build_report_pdf_page(painter, w, h, d, holiday_labels, settings)

    def _auto_fill_range(self, start: QDate, end: QDate, doc_keys: List[str]) -> None:
        students = get_all_students()
        if not students:
            QMessageBox.information(self, "تنبيه", _TOAST_NO_STUDENTS)
            return
        roster = _flatten_counts(count_students(students))
        if sum(roster.values()) == 0:
            QMessageBox.information(self, "تنبيه", _TOAST_NO_CLASSIFIED_STUDENTS)
            return

        if DOC_CONTACT in doc_keys:
            history = get_recent_contacts(limit=900)
            date = start
            while date <= end:
                generate_and_save_contact_for_date(date.toString("yyyy-MM-dd"), roster, history)
                date = date.addDays(1)

        if DOC_ABSENCE in doc_keys:
            history = get_recent_absences(limit=900)
            date = start
            while date <= end:
                generate_and_save_absence_for_date(date.toString("yyyy-MM-dd"), roster, history)
                date = date.addDays(1)


def _flatten_counts(counts: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    return {
        f"{category}_{grant_kind}": count
        for category, grants in counts.items()
        for grant_kind, count in grants.items()
    }
