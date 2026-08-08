"""
src/ui/order_letter_screen.py
Order letter (رسالة الطلبية) — formal supplier request with live letter preview.
Editable meal quantities, auto-fill from student counts, saved history.
"""
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QIntValidator, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextOption,
)
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_PANEL, COLOR_PANEL_ALT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
    EXPORT_FORMAT_PDF,
    FONT_BODY, FONT_LABEL, FONT_SECTION, FONT_TITLE,
)
from core.models import DailyContact, OrderItem, OrderLetter
from data.database import (
    delete_order_letter, get_all_order_letters, get_contacts_between, get_day_contacts,
    get_next_order_letter_number, get_order_items, get_school_settings, save_order_letter,
)
from ui.batch_export import draw_placeholder_pdf_page
from ui.daily_contact_screen import (
    _normalize_template_name, _set_cell_text, _set_docx_text, _template_dirs,
    _WORD_NS, _W_NS,
)
from ui.document_header import (
    ask_export_format, draw_official_pdf_footer, draw_official_pdf_header,
    register_docx_namespaces,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE         = "رسالة الطلبية"
_SUBTITLE      = "طلبية المواد الغذائية الموجهة للمورد"
_BTN_AUTOFILL  = "تعبئة تلقائية من ورقة الاتصال"
_BTN_AUTOFILL_ICON = "⚡"
_BTN_PREVIEW   = "معاينة الرسالة"
_BTN_PREVIEW_ICON = "👁"
_BTN_SAVE      = "حفظ الرسالة"
_BTN_SAVE_ICON = "💾"
_BTN_NEW       = "رسالة جديدة"
_BTN_NEW_ICON  = "➕"
_BTN_DELETE    = "حذف"
_BTN_DELETE_ICON = "🗑️"
_BTN_EXPORT    = "تصدير"
_BTN_EXPORT_ICON = "📄"
_PDF_DIALOG_TITLE = "تصدير رسالة الطلبية"
_PDF_DEFAULT_NAME = "رسالة_الطلبية"
_PDF_FILTER = "PDF (*.pdf)"
_PDF_SAVED_OK = "تم تصدير رسالة الطلبية بنجاح."
_PDF_SAVE_ERROR = "تعذر تصدير رسالة الطلبية:"
_DOCX_DIALOG_TITLE = "تصدير رسالة الطلبية"
_DOCX_DEFAULT_NAME = "رسالة_الطلبية"
_WORD_FILTER = "Word (*.docx)"
_DOCX_SAVED_OK = "تم تصدير رسالة الطلبية بنجاح."
_DOCX_SAVE_ERROR = "تعذر تصدير رسالة الطلبية:"
_LBL_NUMBER    = "رقم الوثيقة:"
_NUMBER_HINT   = "رقم مقترح تلقائيًا — يمكن تعديله قبل الحفظ."
_LBL_DATE      = "تاريخ الرسالة:"
_LBL_FROM      = "من:"
_LBL_TO        = "إلى:"
_LBL_HIST      = "الرسائل المحفوظة"
_LBL_NOTES     = "ملاحظات إضافية (اختياري):"
_SAVED_OK      = "تم حفظ الرسالة بنجاح."
_DEL_CONFIRM   = "هل تريد حذف هذه الرسالة نهائياً؟"
_TOAST_NO_CONTACT_DATA = (
    "لا توجد بيانات محفوظة في ورقة الاتصال لهذه الفترة."
    " يُرجى تسجيل ورقة الاتصال اليومية أولاً، أو تعديل الفترة."
)

_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]
_MEAL_COLORS = {
    MEAL_FTOUR: "#f59e0b",
    MEAL_GHADA: COLOR_ACCENT,
    MEAL_ASHA:  "#7c3aed",
}
_PAGE_BG = COLOR_SURFACE
_PANEL_BG = COLOR_PANEL
_PANEL_BORDER = COLOR_BORDER
_INK = COLOR_TEXT_PRIMARY


def _spin(val: int = 0) -> QSpinBox:
    s = QSpinBox()
    s.setRange(0, 9999)
    s.setValue(val)
    s.setMinimumHeight(32)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    s.setStyleSheet(
        f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
        f"padding:2px 6px; font-size:{FONT_BODY}px;"
    )
    return s


def _btn(label: str, color: str, *, icon: str | None = None) -> QPushButton:
    return IconButton(
        label, icon=icon, bg=color, text_color="white",
        border_radius=12, padding_h=14, font_size=13, bold=False, min_height=36,
    )


# ── Meal quantity card ────────────────────────────────────────────────────────

class _MealQtyCard(QGroupBox):
    """Input card for one meal's quantity breakdown (إعدادي/تأهيلي/معلمون)."""

    def __init__(self, meal_key: str, meal_label: str, color: str) -> None:
        super().__init__(meal_label)
        self._meal_key = meal_key
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_SECTION}px; font-weight:bold; color:{color};
                background:{_PANEL_BG};
                border:1px solid {color}; border-radius:16px;
                margin-top:16px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 10px; right:14px;
            }}
        """)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        def row(label: str, spin: QSpinBox) -> QHBoxLayout:
            h = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px;")
            h.addWidget(lbl)
            h.addStretch()
            h.addWidget(spin)
            return h

        self._sp_coll = _spin()
        self._sp_qual = _spin()
        self._sp_mon  = _spin()
        self._total_lbl = QLabel("0")
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setPointSize(16); f.setBold(True)
        self._total_lbl.setFont(f)
        self._total_lbl.setStyleSheet(
            f"color:white; background:{_MEAL_COLORS.get(self._meal_key, COLOR_ACCENT)};"
            "border-radius:6px; padding:4px 10px;"
        )

        layout.addLayout(row("إعدادي",           self._sp_coll))
        layout.addLayout(row("تأهيلي",           self._sp_qual))
        layout.addLayout(row("معلمو الداخلية",   self._sp_mon))

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{COLOR_BORDER};")
        layout.addWidget(sep)

        tot_row = QHBoxLayout()
        tot_row.addWidget(QLabel("المجموع:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;"))
        tot_row.addStretch()
        tot_row.addWidget(self._total_lbl)
        layout.addLayout(tot_row)

        for sp in (self._sp_coll, self._sp_qual, self._sp_mon):
            sp.valueChanged.connect(self._update)

    def _update(self) -> None:
        self._total_lbl.setText(str(self._sp_coll.value() + self._sp_qual.value() + self._sp_mon.value()))

    def set_values(self, collegial: int, qualifying: int, monitors: int) -> None:
        self._sp_coll.setValue(collegial)
        self._sp_qual.setValue(qualifying)
        self._sp_mon.setValue(monitors)
        self._update()

    def to_item(self, letter_id: int) -> OrderItem:
        return OrderItem(
            letter_id=letter_id,
            meal_type=self._meal_key,
            collegial=self._sp_coll.value(),
            qualifying=self._sp_qual.value(),
            monitors=self._sp_mon.value(),
        )

    def total(self) -> int:
        return self._sp_coll.value() + self._sp_qual.value() + self._sp_mon.value()

    def collegial(self) -> int: return self._sp_coll.value()
    def qualifying(self) -> int: return self._sp_qual.value()
    def monitors(self) -> int: return self._sp_mon.value()


def _order_items_from_contacts(contacts: List[DailyContact]) -> Dict[str, OrderItem]:
    """Sum real ورقة الاتصال beneficiary totals per meal, across whatever
    dates/rows are given — one day's 3 rows or a whole range's worth.
    Shared by the screen's من/إلى auto-fill and the per-day batch
    generator on يوم العمل."""
    items = {meal_key: OrderItem(letter_id=0, meal_type=meal_key) for meal_key, _ in _MEAL_ORDER}
    for contact in contacts:
        item = items.get(contact.meal_type)
        if item is None:
            continue
        item.collegial += contact.collegial_total
        item.qualifying += contact.qualifying_total
        item.monitors += contact.monitors_total
    return items


# ── Letter preview generator ──────────────────────────────────────────────────

def _generate_letter_html(
    settings, letter_date: str, period_start: str, period_end: str,
    cards: Dict[str, _MealQtyCard], notes: str
) -> str:
    """Return an HTML string representing the formal order letter."""
    s = settings
    school_name  = s.school_name if s else "—"
    aref         = s.aref if s else "—"
    dir_prov     = s.direction_provinciale if s else "—"
    city         = s.city if s else "—"
    director     = s.director if s else "—"
    supplier     = s.supplier_name if s else "—"
    company      = s.company_name if s else "—"
    supplier_addr= s.supplier_address if s else "—"
    contract_num = s.contract_number if s else "—"
    school_year  = s.school_year if s else "—"

    # Matches templets/رسالة الطلبية.docx — the real form the directorate
    # accepts shows one aggregate count per meal, not a collegial/qualifying/
    # monitors breakdown. The meal cards still collect that breakdown on
    # screen (useful for planning); only the generated document is aggregate.
    meal_rows = ""
    grand_total = 0
    for meal_key, meal_label in _MEAL_ORDER:
        card = cards[meal_key]
        tot = card.total()
        grand_total += tot
        meal_rows += f"""
        <tr>
            <td style="padding:8px 14px; font-weight:bold; color:{_MEAL_COLORS[meal_key]};">
                {meal_label}</td>
            <td style="padding:8px 14px; text-align:center; font-weight:bold;">{tot}</td>
            <td style="padding:8px 14px;"></td>
        </tr>"""

    notes_block = (
        f"<p style='margin-top:16px;'><b>ملاحظات:</b><br>{notes}</p>"
        if notes.strip() else ""
    )

    return f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8">
<style>
  body {{ font-family: 'Arial', sans-serif; font-size: {FONT_BODY}px;
          margin: 24px; color: {COLOR_TEXT_PRIMARY}; direction: rtl; }}
  .header-box {{ border: 2px solid {COLOR_ACCENT}; border-radius: 10px;
                  padding: 14px 20px; margin-bottom: 20px;
                  background: {COLOR_PANEL_ALT}; }}
  .header-box h2 {{ margin:0; color:{COLOR_ACCENT}; font-size:{FONT_SECTION}px; }}
  .header-box p  {{ margin:4px 0; color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px; }}
  .meta  {{ font-size:{FONT_LABEL}px; color:{COLOR_TEXT_SECONDARY}; margin-bottom:6px; }}
  .subject {{ background:{COLOR_ACCENT}22; border-right:4px solid {COLOR_ACCENT};
              padding:10px 14px; border-radius:0 6px 6px 0; margin:14px 0;
              font-weight:bold; }}
  table {{ width:100%; border-collapse:collapse; margin:14px 0; }}
  th {{ background:{COLOR_ACCENT}; color:white; padding:9px 14px;
        text-align:center; font-size:{FONT_BODY}px; }}
  tr:nth-child(even) {{ background:{COLOR_PANEL_ALT}; }}
  .total-row {{ background:{COLOR_ACCENT_DEEP}; color:white; font-weight:bold; }}
  .total-row td {{ padding:9px 14px; text-align:center; }}
  .signature {{ margin-top:30px; display:flex;
                justify-content:space-between; }}
  .sig-block {{ text-align:center; min-width:180px; }}
  .sig-line {{ border-top:1px solid {COLOR_BORDER}; margin-top:40px;
               padding-top:6px; font-size:{FONT_LABEL}px; }}
  .greet {{ margin:14px 0; line-height:1.9; }}
</style>
</head>
<body>

<!-- Header -->
<div class="header-box">
  <h2>{school_name}</h2>
  <p>{aref} &nbsp;|&nbsp; {dir_prov}</p>
  <p>السنة الدراسية: {school_year}</p>
</div>

<!-- Date & address -->
<p class="meta">{city}، بتاريخ: <b>{letter_date}</b></p>
<p class="meta">إلى السيد/ة: <b>{supplier} — {company}</b></p>
<p class="meta">العنوان: {supplier_addr}</p>

<!-- Subject -->
<div class="subject">
  الموضوع: طلبية المواد الغذائية للفترة من <b>{period_start}</b> إلى <b>{period_end}</b>
  — في إطار الصفقة رقم <b>{contract_num}</b>
</div>

<!-- Greeting -->
<p class="greet">
  تحية طيبة وبعد،<br>
  يشرفني أن أطلب منكم التفضل بتزويد مؤسستنا بالمواد الغذائية الآتية:
</p>

<!-- Quantities table -->
<table>
  <thead>
    <tr>
      <th>الوجبة</th>
      <th>الأعداد</th>
      <th>ملاحظات</th>
    </tr>
  </thead>
  <tbody>
    {meal_rows}
    <tr class="total-row">
      <td>الإجمالي العام</td>
      <td style="background:{COLOR_ACCENT};">{grand_total}</td>
      <td></td>
    </tr>
  </tbody>
</table>

{notes_block}

<!-- Closing -->
<p class="greet">تفضلوا بقبول فائق الاحترام والتقدير.</p>

<!-- Signatures — matches templets/رسالة الطلبية.docx's signature line -->
<div class="signature">
  <div class="sig-block">
    <div class="sig-line">مسير المصالح المادية والمالية</div>
  </div>
  <div class="sig-block">
    <div class="sig-line">مدير المؤسسة<br><b>{director}</b></div>
  </div>
  <div class="sig-block">
    <div class="sig-line">ممثل الشركة النائلة</div>
  </div>
</div>

</body></html>"""


def _draw_letter_pdf_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    *,
    size: int,
    color: str,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
) -> None:
    font = QFont("Segoe UI")
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    option = QTextOption()
    option.setTextDirection(Qt.LayoutDirection.RightToLeft)
    option.setAlignment(align)
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    painter.drawText(rect, text, option)


def _draw_letter_pdf_cell(
    painter: QPainter,
    rect: QRectF,
    *,
    background: str,
    border: str,
    text: str,
    text_color: str,
    size: int,
    bold: bool = False,
) -> None:
    painter.setPen(QPen(QColor(border), 1))
    painter.setBrush(QColor(background))
    painter.drawRect(rect)
    _draw_letter_pdf_text(
        painter,
        rect.adjusted(4, 2, -4, -2),
        text,
        size=size,
        color=text_color,
        bold=bold,
    )


def _draw_order_letter_pdf_page(
    painter: QPainter,
    page_w: float,
    page_h: float,
    settings,
    letter_date: str,
    number: str,
    items: Dict[str, OrderItem],
) -> None:
    """Draw one order letter onto an already-open page — matching the
    real, ministry-accepted templets/رسالة الطلبية.docx exactly: same
    fields, same order, same single-date framing (no period_start/
    period_end, no invented total row). Shared by _write_order_letter_pdf
    (one standalone file) and ui/work_pipeline_screen.py's "generate
    everything" (one page per date in a combined batch PDF). See
    _write_order_letter_docx, which fills the same fields into the
    actual template."""
    s = settings
    supplier = (s.supplier_name if s else "") or ""
    company = (s.company_name if s else "") or ""
    supplier_line = " — ".join(part for part in (supplier, company) if part) or "—"
    city = (s.city if s else "") or "—"
    school_year = (s.school_year if s else "") or "—"
    # "-" gets visually reordered inside RTL text by Qt's bidi algorithm;
    # "/" does not (same workaround as daily_contact_screen._format_doc_date).
    display_date = letter_date.replace("-", "/")

    margin = 38.0
    content_w = page_w - (margin * 2)

    # رقم goes inline in the title itself (matches the real template — the
    # title line there literally reads "رسالة الطلبية رقم:"), not repeated
    # again as a separate line below it.
    y = draw_official_pdf_header(
        painter,
        page_width=page_w,
        margin=margin,
        top=18.0,
        settings=settings,
        title=f"{_TITLE}  رقم: {number}",
    )

    # الموسم الدراسي sits on its own line, left-aligned — distinct from the
    # rest of the meta block below, which stays right-aligned like the
    # template.
    _draw_letter_pdf_text(
        painter,
        QRectF(margin, y, content_w, 24),
        f"الموسم الدراسي : {school_year}",
        size=11,
        color=COLOR_TEXT_PRIMARY,
        align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute,
    )
    y += 28

    meta_lines = [
        f"ليوم : {display_date}",
        f"صاحب الصفقة: {supplier_line}",
    ]
    for line in meta_lines:
        _draw_letter_pdf_text(
            painter,
            QRectF(margin, y, content_w, 24),
            line,
            size=11,
            color=COLOR_TEXT_PRIMARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
        )
        y += 28
    y += 12

    # Matches templets/رسالة الطلبية.docx — the real accepted form shows
    # one aggregate count per meal, not a collegial/qualifying/monitors
    # breakdown, and no total row. The on-screen cards still collect
    # that breakdown for planning; only the generated document is
    # aggregate.
    columns = ["الوجبة", "الأعداد", "ملاحظات"]
    col_widths = [content_w * 0.25, content_w * 0.20, content_w * 0.55]
    header_h = 32.0
    row_h = 40.0
    table_h = header_h + (row_h * len(_MEAL_ORDER))
    right = margin + content_w

    # Plain black-on-white, matching the real template's table exactly
    # — no colored fills, just borders and bold header text.
    current_right = right
    for col_label, col_w in zip(columns, col_widths):
        rect = QRectF(current_right - col_w, y, col_w, header_h)
        _draw_letter_pdf_cell(
            painter, rect,
            background="white", border="#000000",
            text=col_label, text_color="#000000", size=11, bold=True,
        )
        current_right = rect.left()

    row_y = y + header_h
    for meal_key, meal_label in _MEAL_ORDER:
        values = [meal_label, str(items[meal_key].total), ""]
        current_right = right
        for index, (value, col_w) in enumerate(zip(values, col_widths)):
            rect = QRectF(current_right - col_w, row_y, col_w, row_h)
            _draw_letter_pdf_cell(
                painter, rect,
                background="white", border="#000000",
                text=value, text_color="#000000",
                size=11, bold=(index == 0),
            )
            current_right = rect.left()
        row_y += row_h
    y += table_h + 18

    _draw_letter_pdf_text(
        painter,
        QRectF(margin, y, content_w, 24),
        f"حرر ب{city} بتاريخ : {display_date}",
        size=11,
        color=COLOR_TEXT_SECONDARY,
        align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
    )

    footer_h = 90.0
    footer_y = page_h - margin - footer_h + 6
    # STEWARD + HEADMASTER + CONTRACTOR — matches the signature line in
    # the real templets/رسالة الطلبية.docx form (templets/ wins over
    # documents.md's shorter STEWARD+HEADMASTER list where they differ).
    draw_official_pdf_footer(
        painter,
        page_width=page_w,
        margin=margin,
        top=footer_y,
        settings=settings,
        roles=["مسير المصالح المادية والمالية", "مدير المؤسسة", "ممثل الشركة النائلة"],
    )


def _write_order_letter_pdf(
    path: Path,
    settings,
    letter_date: str,
    number: str,
    items: Dict[str, OrderItem],
) -> None:
    """Render a single order letter as its own standalone PDF file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TITLE)

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        _draw_order_letter_pdf_page(
            painter, float(writer.width()), float(writer.height()),
            settings, letter_date, number, items,
        )
    finally:
        painter.end()


def build_order_letter_pdf_page(
    painter: QPainter,
    page_w: float,
    page_h: float,
    date_str: str,
    holiday_labels: Dict[str, str],
    settings,
) -> str:
    """Draw one date's page for a combined batch PDF — real data, a
    holiday placeholder, or a no-data placeholder. Unlike the other 3
    daily documents, a "ready" day here means creating and permanently
    saving a brand-new numbered letter for that date — letters are never
    silently overwritten, so re-running the same range assigns fresh
    numbers again rather than reusing the old ones. Used by
    ui/work_pipeline_screen.py's "generate everything" action. Returns
    "data" / "holiday" / "empty" for the caller's summary."""
    if date_str in holiday_labels:
        label = holiday_labels[date_str] or "بدون سبب محدد"
        draw_placeholder_pdf_page(
            painter, page_w, page_h, f"{date_str} — يوم عطلة", f"📅 عطلة: {label}",
        )
        return "holiday"
    contacts = get_day_contacts(date_str)
    if not contacts:
        draw_placeholder_pdf_page(
            painter, page_w, page_h, f"{date_str} — لا توجد بيانات",
            "لم يتم تسجيل بيانات ورقة الاتصال لهذا اليوم بعد.",
        )
        return "empty"

    items = _order_items_from_contacts(contacts)
    document_number = get_next_order_letter_number()
    letter = OrderLetter(
        letter_date=date_str, period_start=date_str, period_end=date_str,
        document_number=document_number,
    )
    save_order_letter(letter, list(items.values()))
    _draw_order_letter_pdf_page(
        painter, page_w, page_h, settings, date_str, str(document_number), items,
    )
    return "data"


def _find_order_letter_template() -> Path | None:
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for candidate in directory.glob("*.docx"):
            if "رسالةالطلبية" in _normalize_template_name(candidate.stem):
                return candidate
    return None


_DOCX_BODY_FONT_SIZE = "32"  # half-points (16pt) — matches the template's other meta lines


def _normalize_run_font_size(paragraph: ET.Element, size: str) -> None:
    """Force every run in this paragraph to one font size.

    The "حرر ب...بتاريخ" line in the real template opens with an
    invisible run of leading spaces (used to right-align it) sized at
    6pt, while the visible text after it is 16pt. _set_docx_text() always
    writes replacement text into the FIRST <w:t> node — that tiny leading
    run — so the whole line rendered at 6pt after filling. Normalizing
    every run's size after filling sidesteps that regardless of which
    run ends up holding the text."""
    for run in paragraph.findall(".//w:r", _WORD_NS):
        rpr = run.find("w:rPr", _WORD_NS)
        if rpr is None:
            rpr = ET.Element(f"{{{_W_NS}}}rPr")
            run.insert(0, rpr)
        for tag in ("w:sz", "w:szCs"):
            el = rpr.find(tag, _WORD_NS)
            if el is None:
                el = ET.SubElement(rpr, f"{{{_W_NS}}}{tag.split(':')[1]}")
            el.set(f"{{{_W_NS}}}val", size)


def _fill_order_letter_document_xml(
    root: ET.Element,
    *,
    school_year: str,
    number: str,
    display_date: str,
    supplier_line: str,
    place: str,
    items: Dict[str, OrderItem],
) -> None:
    for paragraph in root.findall(".//w:p", _WORD_NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS))
        stripped = text.strip()
        if stripped.startswith("الموسم الدراسي"):
            _set_docx_text(paragraph, f"الموسم الدراسي  :  {school_year}")
        elif stripped.startswith("رسالة الطلبية رقم"):
            _set_docx_text(paragraph, f"رسالة الطلبية رقم: {number}")
        elif stripped.startswith("ليوم"):
            _set_docx_text(paragraph, f"ليوم : {display_date}")
        elif stripped.startswith("صاحب الصفقة"):
            _set_docx_text(paragraph, f"صاحب الصفقة:   {supplier_line}")
        elif "حرر ب" in stripped:
            _set_docx_text(paragraph, f"حرر ب{place} بتاريخ : {display_date}")
            _normalize_run_font_size(paragraph, _DOCX_BODY_FONT_SIZE)

    tables = root.findall(".//w:tbl", _WORD_NS)
    if not tables:
        return
    rows = tables[0].findall("./w:tr", _WORD_NS)
    for row_index, (meal_key, _) in enumerate(_MEAL_ORDER, start=1):
        if row_index >= len(rows):
            break
        cells = rows[row_index].findall("./w:tc", _WORD_NS)
        if len(cells) >= 2:
            _set_cell_text(cells[1], items[meal_key].total)


def _write_order_letter_docx(
    path: Path,
    settings,
    letter_date: str,
    number: str,
    items: Dict[str, OrderItem],
) -> None:
    """Fill the real order-letter template (templets/رسالة الطلبية.docx) —
    the form the directorate actually accepts. Unlike the PDF/HTML preview,
    the template has no period_start/period_end or free-notes fields, only
    a single date and one aggregate count per meal — matched exactly rather
    than invented, per PLAN's 'templets/ wins' rule."""
    template_path = _find_order_letter_template()
    if template_path is None:
        raise FileNotFoundError("تعذر العثور على نموذج رسالة الطلبية.")

    register_docx_namespaces()
    path.parent.mkdir(parents=True, exist_ok=True)
    s = settings
    school_year = (s.school_year if s else "") or "—"
    supplier = (s.supplier_name if s else "") or ""
    company = (s.company_name if s else "") or ""
    supplier_line = " — ".join(part for part in (supplier, company) if part) or "—"
    place = (s.city if s else "") or "—"
    display_date = letter_date.replace("-", "/")

    with ZipFile(template_path, "r") as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                root = ET.fromstring(data)
                _fill_order_letter_document_xml(
                    root,
                    school_year=school_year,
                    number=number,
                    display_date=display_date,
                    supplier_line=supplier_line,
                    place=place,
                    items=items,
                )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)


# ── Main screen ───────────────────────────────────────────────────────────────

class OrderLetterScreen(QWidget):
    """Order letter screen — single-column form + on-demand preview dialog + history."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._cards: Dict[str, _MealQtyCard] = {}
        self._notes_edit: Optional[QTextEdit] = None  # set during _build_body
        self._build_ui()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # Title
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(FONT_TITLE); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color:{_INK};")
        sub = QLabel(_SUBTITLE)
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        root.addWidget(title)
        root.addWidget(sub)

        # Toolbar
        root.addLayout(self._build_toolbar())

        # Single-column body: date info, meal cards, notes.
        root.addWidget(self._build_body(), 1)

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        new_btn    = _btn(_BTN_NEW,     COLOR_SUCCESS, icon=_BTN_NEW_ICON)
        save_btn   = _btn(_BTN_SAVE,    COLOR_ACCENT, icon=_BTN_SAVE_ICON)
        delete_btn = _btn(_BTN_DELETE,  COLOR_DANGER, icon=_BTN_DELETE_ICON)
        preview_btn= _btn(_BTN_PREVIEW, _INK, icon=_BTN_PREVIEW_ICON)
        export_btn = _btn(_BTN_EXPORT,  _INK, icon=_BTN_EXPORT_ICON)

        new_btn.clicked.connect(self._on_new)
        save_btn.clicked.connect(self._on_save)
        delete_btn.clicked.connect(self._on_delete)
        preview_btn.clicked.connect(self._show_preview_dialog)
        export_btn.clicked.connect(self._on_export)

        row.addWidget(new_btn)
        row.addWidget(save_btn)
        row.addWidget(delete_btn)
        row.addSpacing(12)
        row.addWidget(preview_btn)
        row.addWidget(export_btn)
        row.addStretch()

        # History selector
        row.addWidget(QLabel(_LBL_HIST,
                             styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;"))
        self._history_combo = QComboBox()
        self._history_combo.setMinimumHeight(36)
        self._history_combo.setMinimumWidth(190)
        self._history_combo.setPlaceholderText("الرسائل المحفوظة")
        self._history_combo.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            f"padding:4px 8px; font-size:{FONT_BODY}px;"
        )
        self._history_combo.currentIndexChanged.connect(self._on_load_history)
        row.addWidget(self._history_combo)

        return row

    def _build_body(self) -> QWidget:
        """Single-column body: date info, meal cards side by side, notes."""
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(2, 0, 2, 10)
        layout.setSpacing(14)

        # Date inputs — one row: تاريخ الرسالة / من / إلى / تعبئة تلقائية
        date_grp = QGroupBox("معلومات الرسالة")
        date_grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        date_grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                background:{_PANEL_BG};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:10px; padding:14px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        date_row = QHBoxLayout(date_grp)
        date_row.setSpacing(18)

        def _date_field(label: str, edit: DateInput) -> QVBoxLayout:
            v = QVBoxLayout()
            v.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
            v.addWidget(lbl)
            v.addWidget(edit)
            return v

        def _date_edit() -> DateInput:
            d = DateInput(display_format="yyyy-MM-dd")
            d.setDate(QDate.currentDate())
            d.setMinimumHeight(34)
            d.setMinimumWidth(128)
            d.setStyleSheet(
                f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
                f"padding:4px 8px; font-size:{FONT_BODY}px;"
            )
            return d

        self._letter_date  = _date_edit()
        self._period_start = _date_edit()
        self._period_end   = _date_edit()
        # Default period: today → 7 days
        self._period_end.setDate(QDate.currentDate().addDays(6))

        number_col = QVBoxLayout()
        number_col.setSpacing(4)
        number_lbl = QLabel(_LBL_NUMBER)
        number_lbl.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        self._number_edit = QLineEdit()
        self._number_edit.setValidator(QIntValidator(1, 999999, self))
        self._number_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._number_edit.setMinimumHeight(34)
        self._number_edit.setMaximumWidth(90)
        self._number_edit.setToolTip(_NUMBER_HINT)
        self._number_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            f"padding:4px 8px; font-size:{FONT_BODY}px; font-weight:bold;"
        )
        self._number_edit.setText(str(get_next_order_letter_number()))
        number_col.addWidget(number_lbl)
        number_col.addWidget(self._number_edit)
        date_row.addLayout(number_col)

        date_row.addLayout(_date_field(_LBL_DATE, self._letter_date))
        date_row.addLayout(_date_field(_LBL_FROM, self._period_start))
        date_row.addLayout(_date_field(_LBL_TO,   self._period_end))
        date_row.addStretch()

        autofill_btn = _btn(_BTN_AUTOFILL, "#0891b2", icon=_BTN_AUTOFILL_ICON)
        autofill_btn.clicked.connect(self._auto_fill)
        date_row.addWidget(autofill_btn)

        layout.addWidget(date_grp)

        # Meal cards — side by side (فطور | غداء | عشاء), matching the
        # 3-meal-column convention used across the app's other screens.
        meals_row = QHBoxLayout()
        meals_row.setSpacing(14)
        for meal_key, meal_label in _MEAL_ORDER:
            card = _MealQtyCard(meal_key, meal_label, _MEAL_COLORS[meal_key])
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._cards[meal_key] = card
            meals_row.addWidget(card)
        layout.addLayout(meals_row)

        # Notes
        notes_lbl = QLabel(_LBL_NOTES)
        notes_lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px; font-weight:bold;")
        layout.addWidget(notes_lbl)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("اختياري — تُضاف في نهاية الرسالة")
        self._notes_edit.setMaximumHeight(86)
        self._notes_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:12px;"
            f"padding:6px; font-size:{FONT_BODY}px;"
        )
        layout.addWidget(self._notes_edit)
        layout.addStretch()

        panel.setWidget(content)
        return panel

    # ── Helpers ────────────────────────────────────────────────────────────

    def _current_letter_html(self) -> str:
        settings = get_school_settings()
        return _generate_letter_html(
            settings,
            letter_date=self._letter_date.date().toString("yyyy-MM-dd"),
            period_start=self._period_start.date().toString("yyyy-MM-dd"),
            period_end=self._period_end.date().toString("yyyy-MM-dd"),
            cards=self._cards,
            notes=self._notes_edit.toPlainText() if self._notes_edit else "",
        )

    def _show_preview_dialog(self) -> None:
        """Opens the letter preview on demand instead of keeping a permanent
        live-updating pane — the form is the working surface; the preview is
        just a look-before-you-export check."""
        dialog = QDialog(self)
        dialog.setWindowTitle(_BTN_PREVIEW)
        dialog.resize(680, 760)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet(f"border:none; background:white; font-size:{FONT_BODY}px; padding:8px;")
        browser.setHtml(self._current_letter_html())
        layout.addWidget(browser, 1)

        close_row = QHBoxLayout()
        close_row.setContentsMargins(14, 10, 14, 14)
        close_btn = _btn("إغلاق", _INK)
        close_btn.clicked.connect(dialog.accept)
        close_row.addStretch()
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        dialog.exec()

    def _on_export(self) -> None:
        # Always ask PDF-or-Word here, regardless of the app-wide export
        # preference — a letter goes out to a supplier and the مسير wants
        # to pick deliberately each time, not rely on a forgotten default.
        fmt = ask_export_format(self)
        if fmt is None:
            return
        is_pdf = fmt == EXPORT_FORMAT_PDF
        letter_date = self._letter_date.date().toString("yyyy-MM-dd")
        number = self._number_edit.text().strip() or "...."

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            _PDF_DIALOG_TITLE if is_pdf else _DOCX_DIALOG_TITLE,
            f"{_PDF_DEFAULT_NAME if is_pdf else _DOCX_DEFAULT_NAME}_{letter_date}."
            f"{'pdf' if is_pdf else 'docx'}",
            _PDF_FILTER if is_pdf else _WORD_FILTER,
        )
        if not path_str:
            return

        path = Path(path_str)
        suffix = ".pdf" if is_pdf else ".docx"
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)

        try:
            settings = get_school_settings()
            items = {key: card.to_item(0) for key, card in self._cards.items()}
            if is_pdf:
                _write_order_letter_pdf(
                    path,
                    settings,
                    letter_date=letter_date,
                    number=number,
                    items=items,
                )
            else:
                _write_order_letter_docx(path, settings, letter_date, number, items)
            QMessageBox.information(self, "تم", _PDF_SAVED_OK if is_pdf else _DOCX_SAVED_OK)
        except Exception as exc:
            error_prefix = _PDF_SAVE_ERROR if is_pdf else _DOCX_SAVE_ERROR
            QMessageBox.critical(self, "خطأ", f"{error_prefix}\n{exc}")

    def _auto_fill(self) -> None:
        """Fill each meal card with the REAL beneficiary totals saved in
        ورقة الاتصال for every date in [period_start, period_end] — not a
        flat roster guess, since فطور/غداء/عشاء legitimately differ."""
        start = self._period_start.date().toString("yyyy-MM-dd")
        end = self._period_end.date().toString("yyyy-MM-dd")
        contacts = get_contacts_between(start, end)
        if not contacts:
            QMessageBox.information(self, "تنبيه", _TOAST_NO_CONTACT_DATA)
            return

        items = _order_items_from_contacts(contacts)
        for meal_key, card in self._cards.items():
            item = items[meal_key]
            card.set_values(item.collegial, item.qualifying, item.monitors)

    def _refresh_history(self) -> None:
        letters = get_all_order_letters()
        self._history_combo.blockSignals(True)
        self._history_combo.clear()
        for lt in letters:
            self._history_combo.addItem(
                f"{lt.letter_date}  ({lt.period_start} → {lt.period_end})", lt
            )
        self._history_combo.blockSignals(False)
        self._history_letters = letters

    def _on_load_history(self, idx: int) -> None:
        letter = self._history_combo.itemData(idx)
        if not isinstance(letter, OrderLetter):
            return
        lt = letter
        self._letter_date.setDate(QDate.fromString(lt.letter_date, "yyyy-MM-dd"))
        self._period_start.setDate(QDate.fromString(lt.period_start, "yyyy-MM-dd"))
        self._period_end.setDate(QDate.fromString(lt.period_end, "yyyy-MM-dd"))
        self._notes_edit.setPlainText(lt.notes)
        items = {it.meal_type: it for it in get_order_items(lt.id)}  # type: ignore[arg-type]
        for meal_key, card in self._cards.items():
            it = items.get(meal_key)
            if it:
                card.set_values(it.collegial, it.qualifying, it.monitors)
            else:
                card.set_values(0, 0, 0)
        self._number_edit.setText(
            str(lt.document_number) if lt.document_number is not None else str(get_next_order_letter_number())
        )

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_new(self) -> None:
        today = QDate.currentDate()
        self._letter_date.setDate(today)
        self._period_start.setDate(today)
        self._period_end.setDate(today.addDays(6))
        self._notes_edit.clear()
        for card in self._cards.values():
            card.set_values(0, 0, 0)
        self._history_combo.blockSignals(True)
        self._history_combo.setCurrentIndex(-1)
        self._history_combo.blockSignals(False)
        self._number_edit.setText(str(get_next_order_letter_number()))

    def _on_save(self) -> None:
        try:
            document_number = int(self._number_edit.text().strip())
        except ValueError:
            document_number = get_next_order_letter_number()
            self._number_edit.setText(str(document_number))
        letter = OrderLetter(
            letter_date=self._letter_date.date().toString("yyyy-MM-dd"),
            period_start=self._period_start.date().toString("yyyy-MM-dd"),
            period_end=self._period_end.date().toString("yyyy-MM-dd"),
            notes=self._notes_edit.toPlainText().strip(),
            document_number=document_number,
        )
        items = [card.to_item(0) for card in self._cards.values()]
        try:
            save_order_letter(letter, items)
            self._refresh_history()
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_delete(self) -> None:
        idx = self._history_combo.currentIndex()
        letter = self._history_combo.itemData(idx)
        if not isinstance(letter, OrderLetter):
            QMessageBox.information(self, "تنبيه", "اختر رسالة من القائمة أولاً.")
            return
        reply = QMessageBox.question(
            self, "تأكيد الحذف", _DEL_CONFIRM,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_order_letter(letter.id)  # type: ignore[arg-type]
                self._refresh_history()
                self._on_new()
            except Exception as exc:
                QMessageBox.critical(self, "خطأ", str(exc))

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Refresh the saved-letters history when the screen becomes visible."""
        super().showEvent(event)
        self._refresh_history()
