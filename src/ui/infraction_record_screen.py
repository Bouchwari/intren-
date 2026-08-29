"""
src/ui/infraction_record_screen.py
محضر المخالفة (PV de constat d'infraction) — the official record raised
against the catering company when a contractual breach is observed
(annex 5, p.93 of the ministry's procedural guide).

This is the only مخالفة document the app produces. A student-discipline
screen (دفتر المخالفات) used to sit beside it; the user confirmed on
2026-08-28 that no such document exists in their job — it came from a
misunderstanding when the project was first started — and it was deleted.

The subject is the CONTRACTOR breaching the صفقة, and it carries the four
official signatures — the company's representative plus the three-member
follow-up committee (الحارس العام، مسير المصالح المادية والمالية، مدير
المؤسسة).

**It records no money.** The document states what happened; any deduction
is decided elsewhere (see the matama skill's documents.md §7).

There is no .docx template for this form in templets/, so the PDF is
hand-drawn to match the guide's own page: title with the reference, the
contract paragraph, the date/meal/place lines, the infraction description
on dotted rules, then the signature blocks.
"""
import datetime
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter,
    QPen,
)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER, COLOR_DANGER,
    COLOR_PANEL_ALT, COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, MEAL_LABELS,
)
from core.models import InfractionRecord, SchoolSettings
from core.ramadan import meals_for_date
from data.database import (
    delete_infraction, get_all_infractions, get_next_infraction_number,
    get_ramadan_overrides, get_school_settings, save_infraction,
)
from ui.dialogs import ask_choice
from ui.document_header import ask_export_format, draw_official_pdf_header
from ui.infraction_docx import write_infraction_docx
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ──────────────────────────────────────────────────────────
_TITLE = "محضر المخالفة"
_SUBTITLE = ("يُحرر عند رصد خرق تعاقدي من الشركة النائلة — "
             "يوقعه ممثل الشركة ولجنة التتبع والمراقبة")
_LBL_NUMBER = "رقم المحضر:"
_LBL_YEAR = "السنة:"
_LBL_DATE = "تاريخ المخالفة:"
_LBL_MEAL = "وجبة المخالفة:"
_LBL_PLACE = "مكان المخالفة:"
_LBL_TYPE = "نوع المخالفة:"
_LBL_DESCRIPTION = "وصف المخالفة"
_LBL_REPORTED_BY = "عاين المخالفة:"
_LBL_WRITTEN = "حرر المحضر بتاريخ:"
_LBL_SAVED = "المحاضر المسجلة"

_BTN_NEW = "محضر جديد"
_BTN_NEW_ICON = "➕"
_BTN_SAVE = "حفظ المحضر"
_BTN_SAVE_ICON = "💾"
_BTN_EXPORT = "تصدير"
_BTN_EXPORT_ICON = "📄"
_BTN_DELETE = "🗑"

_MSG_SAVED = "تم حفظ محضر المخالفة بنجاح."
_MSG_TYPE_REQUIRED = "حدد نوع المخالفة أولاً — لا يمكن تحرير محضر بدون بيان الإخلال."
_MSG_DUPLICATE = ("رقم المحضر مستعمل من قبل في هذه السنة.\n"
                  "غيّر الرقم ثم أعد الحفظ.")
_MSG_NO_SETTINGS = ("أكمل بيانات المؤسسة والصفقة من «الإعدادات» أولاً — "
                    "المحضر يحتاج رقم الصفقة واسم الشركة.")
_MSG_EXPORT_SAVED = "تم تصدير المحضر إلى:\n"
_MSG_EXPORT_FAILED = "تعذر تصدير المحضر. تحقق من المكان المختار ثم أعد المحاولة."
_MSG_DELETE_CONFIRM = "حذف هذا المحضر نهائياً؟"
_MSG_SAVE_FIRST = "احفظ المحضر أولاً ثم صدّره."

# The guide's own wording, with the school/commune/contract filled in.
_BODY_TEMPLATE = (
    "طبقا لبنود الصفقة الاطار رقم {contract} المتعلقة بالتدبير المفوض لخدمة "
    "الإطعام المدرسي بالداخليات والمطاعم المدرسية بالتعليم الثانوي لفائدة "
    "{school} بالجماعة الترابية {commune}."
)
_LBL_HOLDER = "نائل الصفقة:"
_SIGN_COMPANY = "توقيع ممثل الشركة:"
_SIGN_COMMITTEE = "توقيعات لجنة التتبع والمراقبة:"
_SIGN_WARDEN = "الحارس(ة) العام(ة) للداخلية:"
_SIGN_STEWARD = "مسير المصالح المادية والمالية:"
_SIGN_DIRECTOR = "مدير(ة) المؤسسة التعليمية:"

_PLACES = ["المطبخ", "المخزن", "المطعم", "قاعة الأكل", "الثلاجات", "مكان آخر"]
_INFRACTION_TYPES = [
    "عدم احترام النظافة",
    "نقص في كمية الوجبة",
    "عدم مطابقة الوجبة للبرنامج الغذائي",
    "تأخر في تقديم الوجبة",
    "رداءة جودة المواد الغذائية",
    "عدم احترام سلسلة التبريد",
    "عدم الاحتفاظ بعينة من الوجبة",
    "نقص في الأطر أو التجهيزات",
    "مخالفة أخرى",
]

_TABLE_HEADERS = ["الرقم", "تاريخ المخالفة", "الوجبة", "المكان", "نوع المخالفة", ""]
_DOTTED = "." * 90

# This document prints in plain black ink, not the app's olive/green house
# colour: it is a formal notice served on the contractor, and the user asked
# for it to read like the ministry's own black-and-white form.
_INK = "#000000"
_LINE_GAP = 34.0        # vertical step between field lines
_BODY_SIZE = 12         # a size up from the app default — easier to read

_LOGGER = logging.getLogger(__name__)


def _meal_choices(date_str: str) -> List[tuple]:
    """(key, label) for the meals served on that date — Ramadan's two or the
    normal three, so a Ramadan-day breach can name إفطار/سحور."""
    active = meals_for_date(date_str, get_school_settings(), get_ramadan_overrides())
    return [(key, MEAL_LABELS.get(key, key)) for key in active]


# ── PDF export — hand-drawn to match the guide's own page ──────────────────

def _text(painter: QPainter, rect: QRectF, value: str, *, size: int = _BODY_SIZE,
          bold: bool = False, color: str = _INK,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
          underline: bool = False) -> float:
    """Draw wrapped text and return the height it actually needed.

    QPainter.drawText(QRectF, ...) CLIPS to the rect it is given, so a
    caller passing a guessed height silently loses the tail of any longer
    line — which is exactly how a long school name or description made this
    document print half-finished. The rect is grown to the measured height
    before drawing, and the real height is returned so the caller can
    advance by it instead of by a constant.
    """
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    font.setUnderline(underline)
    painter.setFont(font)
    painter.setPen(QColor(color))

    flags = int(align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)
    metrics = QFontMetricsF(font)
    needed = metrics.boundingRect(
        QRectF(rect.left(), rect.top(), rect.width(), 10000.0), flags, value)
    height = max(rect.height(), needed.height())
    painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), height),
                     flags, value)
    return height


def _filled_line(label: str, value: str, dots: int = 30) -> str:
    """"تاريخ المخالفة : 02/03/2026" — falls back to the blank form's dotted
    rule when the field was left empty, exactly like the printed guide."""
    return f"{label} {value.strip() or ('.' * dots)}"


def draw_infraction_pdf_page(
    painter: QPainter, page_w: float, page_h: float,
    record: InfractionRecord, settings: Optional[SchoolSettings],
) -> None:
    """Draw one محضر مخالفة onto an already-open painter."""
    margin = 46.0
    content_w = page_w - (margin * 2)

    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=margin, top=16.0,
        settings=settings, title=f"{_TITLE} رقم: {record.reference}",
        title_color=_INK,
    )
    y += 18

    contract = (settings.contract_number if settings else "") or "." * 25
    school = (settings.school_name if settings else "") or "." * 25
    commune = (settings.city if settings else "") or "." * 20
    y += _text(painter, QRectF(margin, y, content_w, 56),
               _BODY_TEMPLATE.format(
                   contract=contract, school=school, commune=commune)) + 22

    holder = (settings.company_name if settings else "") or (
        settings.supplier_name if settings else "") or "." * 30
    _text(painter, QRectF(margin, y, content_w, 24),
          _filled_line(_LBL_HOLDER, holder))
    y += _LINE_GAP

    meal_label = MEAL_LABELS.get(record.meal_type, record.meal_type)
    half = content_w / 2
    _text(painter, QRectF(margin + half, y, half, 24),
          _filled_line(_LBL_DATE, _display_date(record.date), 18))
    _text(painter, QRectF(margin, y, half, 24),
          _filled_line(_LBL_MEAL, meal_label, 14))
    y += _LINE_GAP

    _text(painter, QRectF(margin, y, content_w, 24),
          _filled_line(_LBL_PLACE, record.place, 24))
    y += _LINE_GAP

    _text(painter, QRectF(margin, y, content_w, 24),
          _filled_line(_LBL_TYPE, record.infraction_type, 40))
    y += 28

    # Description sits on its own, indented under نوع المخالفة, with the
    # guide's dotted rules when nothing was written.
    description = record.description.strip()
    if description:
        y += _text(painter, QRectF(margin, y, content_w, 28), description) + 26
    else:
        for _ in range(3):
            _text(painter, QRectF(margin, y, content_w, 24), _DOTTED,
                  color=COLOR_TEXT_SECONDARY)
            y += 26
        y += 8

    _text(painter, QRectF(margin, y, content_w, 24),
          _filled_line(_LBL_REPORTED_BY, record.reported_by, 30))
    y += _LINE_GAP

    _text(painter, QRectF(margin, y, content_w, 24),
          _filled_line(_LBL_WRITTEN, _display_date(record.written_date), 22))
    y += _LINE_GAP + 10

    # ── Signatures — real space to actually sign in ────────────────────────
    _text(painter, QRectF(margin, y, content_w, 24), _SIGN_COMPANY,
          bold=True, underline=True)
    y += 96

    _text(painter, QRectF(margin, y, content_w, 24), _SIGN_COMMITTEE,
          bold=True, underline=True)
    y += 40

    _text(painter, QRectF(margin + half, y, half, 24), _SIGN_WARDEN, underline=True)
    _text(painter, QRectF(margin, y, half, 24), _SIGN_STEWARD, underline=True)
    y += 104

    _text(painter, QRectF(margin, y, content_w, 24), _SIGN_DIRECTOR,
          underline=True, align=Qt.AlignmentFlag.AlignHCenter)


def _display_date(date_str: str) -> str:
    """ISO → the day/month/year order the printed form uses."""
    if not date_str or len(date_str) != 10:
        return ""
    year, month, day = date_str.split("-")
    return f"{day}/{month}/{year}"


def _docx_strings(record: InfractionRecord,
                  settings: Optional[SchoolSettings]) -> dict:
    """Every Arabic line the Word version prints, built from the same
    constants and the same fallbacks the PDF uses — so the two exports of
    one record can never say different things."""
    contract = (settings.contract_number if settings else "") or "." * 25
    school = (settings.school_name if settings else "") or "." * 25
    commune = (settings.city if settings else "") or "." * 20
    holder = (settings.company_name if settings else "") or (
        settings.supplier_name if settings else "") or "." * 30
    meal_label = MEAL_LABELS.get(record.meal_type, record.meal_type)
    return {
        "title": _TITLE,
        "body": _BODY_TEMPLATE.format(
            contract=contract, school=school, commune=commune),
        "holder": _filled_line(_LBL_HOLDER, holder),
        "date_and_meal": (
            f"{_filled_line(_LBL_DATE, _display_date(record.date), 18)}"
            f"        {_filled_line(_LBL_MEAL, meal_label, 14)}"),
        "place": _filled_line(_LBL_PLACE, record.place, 24),
        "infraction_type": _filled_line(_LBL_TYPE, record.infraction_type, 40),
        "description": record.description.strip(),
        "dotted": _DOTTED,
        "reported_by": _filled_line(_LBL_REPORTED_BY, record.reported_by, 30),
        "written": _filled_line(
            _LBL_WRITTEN, _display_date(record.written_date), 22),
        "sign_company": _SIGN_COMPANY,
        "sign_committee": _SIGN_COMMITTEE,
        "sign_warden": _SIGN_WARDEN,
        "sign_steward": _SIGN_STEWARD,
        "sign_director": _SIGN_DIRECTOR,
    }


def write_infraction_pdf(
    path: Path, record: InfractionRecord, settings: Optional[SchoolSettings],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(f"{_TITLE} {record.reference}")

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_infraction_pdf_page(
            painter, float(writer.width()), float(writer.height()), record, settings)
    finally:
        painter.end()


class InfractionRecordScreen(QWidget):
    """محضر المخالفة — write, save and print one PV against the caterer."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._editing_id: Optional[int] = None
        self._build_ui()
        self._new_record()
        self._refresh_table()

    def refresh(self) -> None:
        """Re-read saved records when the user navigates back to this screen."""
        self._refresh_table()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(28, 22, 28, 28)
        inner.setSpacing(18)

        inner.addLayout(self._build_header())
        inner.addWidget(self._build_form())
        inner.addWidget(self._build_table_card())
        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QVBoxLayout:
        column = QVBoxLayout()
        title = QLabel(_TITLE)
        font = QFont(); font.setPointSize(17); font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        subtitle = QLabel(_SUBTITLE)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        column.addWidget(title)
        column.addWidget(subtitle)
        return column

    def _field_style(self) -> str:
        return (f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
                f"padding:4px 8px; font-size:{FONT_BODY}px; background:white;")

    def _build_form(self) -> QGroupBox:
        group = QGroupBox(_TITLE)
        group.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        group.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                margin-top:10px; padding:12px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        def label(text: str) -> QLabel:
            return QLabel(text, styleSheet=(
                f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))

        # Reference + dates
        top = QHBoxLayout(); top.setSpacing(8)
        top.addWidget(label(_LBL_NUMBER))
        self._number_spin = QSpinBox()
        self._number_spin.setRange(1, 999)
        self._number_spin.setMinimumHeight(34)
        self._number_spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._number_spin.setStyleSheet(self._field_style())
        top.addWidget(self._number_spin)

        top.addWidget(label(_LBL_YEAR))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2020, 2100)
        self._year_spin.setMinimumHeight(34)
        self._year_spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._year_spin.setStyleSheet(self._field_style())
        self._year_spin.valueChanged.connect(self._suggest_number)
        top.addWidget(self._year_spin)

        top.addWidget(label(_LBL_DATE))
        self._date_edit = DateInput(display_format="yyyy-MM-dd")
        self._date_edit.setMinimumHeight(34)
        self._date_edit.setStyleSheet(self._field_style())
        self._date_edit.dateChanged.connect(self._reload_meal_choices)
        top.addWidget(self._date_edit)
        top.addStretch()
        layout.addLayout(top)

        # Meal + place + type
        middle = QHBoxLayout(); middle.setSpacing(8)
        middle.addWidget(label(_LBL_MEAL))
        self._meal_combo = QComboBox()
        self._meal_combo.setMinimumHeight(34)
        self._meal_combo.setMinimumWidth(120)
        self._meal_combo.setStyleSheet(self._field_style())
        middle.addWidget(self._meal_combo)

        middle.addWidget(label(_LBL_PLACE))
        self._place_combo = QComboBox()
        self._place_combo.setEditable(True)
        self._place_combo.addItems(_PLACES)
        self._place_combo.setMinimumHeight(34)
        self._place_combo.setMinimumWidth(140)
        self._place_combo.setStyleSheet(self._field_style())
        middle.addWidget(self._place_combo)

        middle.addWidget(label(_LBL_TYPE))
        self._type_combo = QComboBox()
        self._type_combo.setEditable(True)
        self._type_combo.addItems(_INFRACTION_TYPES)
        self._type_combo.setMinimumHeight(34)
        self._type_combo.setMinimumWidth(240)
        self._type_combo.setStyleSheet(self._field_style())
        middle.addWidget(self._type_combo)
        middle.addStretch()
        layout.addLayout(middle)

        # Description
        layout.addWidget(label(_LBL_DESCRIPTION))
        self._description_edit = QTextEdit()
        self._description_edit.setMinimumHeight(90)
        self._description_edit.setStyleSheet(self._field_style())
        layout.addWidget(self._description_edit)

        # Reporter + written date
        bottom = QHBoxLayout(); bottom.setSpacing(8)
        bottom.addWidget(label(_LBL_REPORTED_BY))
        self._reporter_edit = QLineEdit()
        self._reporter_edit.setMinimumHeight(34)
        self._reporter_edit.setMinimumWidth(200)
        self._reporter_edit.setStyleSheet(self._field_style())
        bottom.addWidget(self._reporter_edit)

        bottom.addWidget(label(_LBL_WRITTEN))
        self._written_edit = DateInput(display_format="yyyy-MM-dd")
        self._written_edit.setMinimumHeight(34)
        self._written_edit.setStyleSheet(self._field_style())
        bottom.addWidget(self._written_edit)
        bottom.addStretch()

        new_btn = IconButton(
            _BTN_NEW, icon=_BTN_NEW_ICON, bg=COLOR_TEXT_SECONDARY,
            text_color="white", border_radius=7, padding_h=14, font_size=13,
            bold=True, min_height=38)
        new_btn.clicked.connect(self._new_record)
        bottom.addWidget(new_btn)

        save_btn = IconButton(
            _BTN_SAVE, icon=_BTN_SAVE_ICON, bg=COLOR_ACCENT, text_color="white",
            border_radius=7, padding_h=18, font_size=13, bold=True, min_height=38)
        save_btn.clicked.connect(self._on_save)
        bottom.addWidget(save_btn)

        export_btn = IconButton(
            _BTN_EXPORT, icon=_BTN_EXPORT_ICON, bg=COLOR_ACCENT_DEEP,
            text_color="white", border_radius=7, padding_h=14, font_size=13,
            bold=True, min_height=38)
        export_btn.clicked.connect(self._on_export)
        bottom.addWidget(export_btn)
        layout.addLayout(bottom)

        return group

    def _build_table_card(self) -> QGroupBox:
        group = QGroupBox(_LBL_SAVED)
        group.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        group.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                margin-top:10px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(group)
        self._table = QTableWidget(0, len(_TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # The delete button's column is a fixed narrow strip — stretching it
        # like the data columns turns the button into a huge red bar.
        header.setSectionResizeMode(
            len(_TABLE_HEADERS) - 1, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(len(_TABLE_HEADERS) - 1, 56)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                font-size:{FONT_LABEL}px; background:white;
                alternate-background-color:{COLOR_PANEL_ALT};
                gridline-color:{COLOR_BORDER};
            }}
            QHeaderView::section {{
                background:{COLOR_ACCENT}; color:white; padding:8px;
                border:none; font-weight:bold; font-size:{FONT_CAPTION}px;
            }}
            QTableWidget::item {{ padding:6px 8px; }}
        """)
        self._table.cellDoubleClicked.connect(self._on_row_activated)
        layout.addWidget(self._table)
        return group

    # ── Form state ─────────────────────────────────────────────────────────

    def _selected_date_str(self) -> str:
        return self._date_edit.date().toString("yyyy-MM-dd")

    def _reload_meal_choices(self) -> None:
        """Repopulate the meal list for the selected date, keeping the current
        choice when that meal is still served (a Ramadan day offers إفطار/سحور
        instead of the normal three)."""
        previous = self._meal_combo.currentData()
        self._meal_combo.blockSignals(True)
        self._meal_combo.clear()
        for key, label in _meal_choices(self._selected_date_str()):
            self._meal_combo.addItem(label, key)
        index = self._meal_combo.findData(previous)
        if index >= 0:
            self._meal_combo.setCurrentIndex(index)
        self._meal_combo.blockSignals(False)

    def _suggest_number(self) -> None:
        """Offer the next free number for the selected year — only while
        writing a NEW record, so editing a saved one keeps its reference."""
        if self._editing_id is not None:
            return
        self._number_spin.setValue(get_next_infraction_number(self._year_spin.value()))

    def _new_record(self) -> None:
        today = QDate.currentDate()
        self._editing_id = None
        self._date_edit.setDate(today)
        self._written_edit.setDate(today)
        self._year_spin.blockSignals(True)
        self._year_spin.setValue(today.year())
        self._year_spin.blockSignals(False)
        self._reload_meal_choices()
        self._place_combo.setCurrentIndex(0)
        self._type_combo.setCurrentIndex(0)
        self._description_edit.clear()
        settings = get_school_settings()
        self._reporter_edit.setText(
            (settings.surveillant_general if settings else "") or "")
        self._suggest_number()

    def _current_record(self) -> InfractionRecord:
        return InfractionRecord(
            id=self._editing_id,
            date=self._selected_date_str(),
            document_number=self._number_spin.value(),
            year=self._year_spin.value(),
            meal_type=self._meal_combo.currentData() or "",
            place=self._place_combo.currentText().strip(),
            infraction_type=self._type_combo.currentText().strip(),
            description=self._description_edit.toPlainText().strip(),
            reported_by=self._reporter_edit.text().strip(),
            written_date=self._written_edit.date().toString("yyyy-MM-dd"),
        )

    def _load_record(self, record: InfractionRecord) -> None:
        self._editing_id = record.id
        self._date_edit.setDate(QDate.fromString(record.date, "yyyy-MM-dd"))
        self._written_edit.setDate(
            QDate.fromString(record.written_date or record.date, "yyyy-MM-dd"))
        self._year_spin.blockSignals(True)
        self._year_spin.setValue(record.year)
        self._year_spin.blockSignals(False)
        self._number_spin.setValue(record.document_number)
        self._reload_meal_choices()
        index = self._meal_combo.findData(record.meal_type)
        if index >= 0:
            self._meal_combo.setCurrentIndex(index)
        self._place_combo.setCurrentText(record.place)
        self._type_combo.setCurrentText(record.infraction_type)
        self._description_edit.setPlainText(record.description)
        self._reporter_edit.setText(record.reported_by)

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        record = self._current_record()
        if not record.infraction_type:
            QMessageBox.warning(self, "تنبيه", _MSG_TYPE_REQUIRED)
            return
        try:
            self._editing_id = save_infraction(record)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "تنبيه", _MSG_DUPLICATE)
            return
        except Exception:
            _LOGGER.exception("Failed to save infraction record")
            QMessageBox.critical(self, "خطأ", _MSG_EXPORT_FAILED)
            return
        self._refresh_table()
        QMessageBox.information(self, "تم", _MSG_SAVED)

    def _on_export(self) -> None:
        record = self._current_record()
        if not record.infraction_type:
            QMessageBox.warning(self, "تنبيه", _MSG_TYPE_REQUIRED)
            return
        settings = get_school_settings()
        if settings is None or not (settings.contract_number or settings.company_name):
            QMessageBox.warning(self, "تنبيه", _MSG_NO_SETTINGS)
            return

        # PDF to print and sign, Word when the مسير wants to reword the
        # description before printing — the same chooser the other documents
        # use, so the two formats stay one decision rather than two buttons.
        chosen = ask_export_format(self)
        if chosen is None:
            return
        suffix = ".docx" if chosen == EXPORT_FORMAT_DOCX else ".pdf"
        file_filter = ("Word Files (*.docx)" if chosen == EXPORT_FORMAT_DOCX
                       else "PDF Files (*.pdf)")
        default_name = (
            f"محضر_مخالفة_{record.year}-{record.document_number:02d}{suffix}")
        path_str, _ = QFileDialog.getSaveFileName(
            self, _BTN_EXPORT, str(Path.home() / default_name), file_filter)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)
        try:
            if chosen == EXPORT_FORMAT_DOCX:
                write_infraction_docx(path, record, settings,
                                      _docx_strings(record, settings))
            else:
                write_infraction_pdf(path, record, settings)
            QMessageBox.information(self, "تم", f"{_MSG_EXPORT_SAVED}{path}")
        except Exception:
            _LOGGER.exception("Failed to export infraction record to %s", path)
            QMessageBox.critical(self, "خطأ", _MSG_EXPORT_FAILED)

    def _on_row_activated(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        if item is None:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)
        for record in get_all_infractions():
            if record.id == record_id:
                self._load_record(record)
                return

    def _on_delete(self, record_id: int) -> None:
        confirmed = ask_choice(
            self, "تأكيد الحذف", _MSG_DELETE_CONFIRM,
            [("حذف", "delete"), ("إلغاء", "cancel")])
        if confirmed != "delete":
            return
        delete_infraction(record_id)
        if self._editing_id == record_id:
            self._new_record()
        self._refresh_table()

    def _refresh_table(self) -> None:
        records = get_all_infractions()
        self._table.setRowCount(len(records))
        for row, record in enumerate(records):
            reference = QTableWidgetItem(record.reference)
            reference.setData(Qt.ItemDataRole.UserRole, record.id)
            values = [
                reference,
                QTableWidgetItem(_display_date(record.date)),
                QTableWidgetItem(MEAL_LABELS.get(record.meal_type, record.meal_type)),
                QTableWidgetItem(record.place),
                QTableWidgetItem(record.infraction_type),
            ]
            for column, item in enumerate(values):
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter))
                self._table.setItem(row, column, item)
            delete_btn = IconButton(
                _BTN_DELETE, bg=COLOR_DANGER, text_color="white",
                border_radius=6, padding_h=10, font_size=12, bold=True, min_height=28)
            delete_btn.clicked.connect(
                lambda _checked, rid=record.id: self._on_delete(rid))
            self._table.setCellWidget(row, len(values), delete_btn)
