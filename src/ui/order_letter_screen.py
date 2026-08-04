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
    QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextOption,
)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QSplitter, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_PANEL_ALT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
    EXPORT_FORMAT_ASK, EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF,
    FONT_BODY, FONT_LABEL, FONT_SECTION,
)
from core.models import OrderItem, OrderLetter
from data.database import (
    delete_order_letter, get_all_order_letters, get_document_export_format,
    get_order_items, get_school_settings, get_student_counts, save_order_letter,
)
from ui.daily_contact_screen import (
    _normalize_template_name, _set_cell_text, _set_docx_text, _template_dirs,
    _WORD_NS,
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
_BTN_AUTOFILL  = "تعبئة تلقائية من لائحة التلاميذ"
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
_LBL_DATE      = "تاريخ الرسالة:"
_LBL_FROM      = "من:"
_LBL_TO        = "إلى:"
_LBL_HIST      = "الرسائل المحفوظة"
_LBL_NOTES     = "ملاحظات إضافية (اختياري):"
_SAVED_OK      = "تم حفظ الرسالة بنجاح."
_DEL_CONFIRM   = "هل تريد حذف هذه الرسالة نهائياً؟"

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
_PAGE_BG = "#f5f5f0"
_PANEL_BG = "#ffffff"
_PANEL_BORDER = "#dddccd"
_INK = "#5A5A40"


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


def _write_order_letter_pdf(
    path: Path,
    settings,
    letter_date: str,
    period_start: str,
    period_end: str,
    cards: Dict[str, "_MealQtyCard"],
    notes: str,
) -> None:
    """Render the order letter as an official PDF, using the same
    header/footer helpers already proven on the meal program PDF export.
    Mirrors _generate_letter_html's fields exactly, just on a printable page
    instead of an HTML preview."""
    s = settings
    supplier = (s.supplier_name if s else "") or "—"
    company = (s.company_name if s else "") or "—"
    supplier_addr = (s.supplier_address if s else "") or "—"
    contract_num = (s.contract_number if s else "") or "—"
    city = (s.city if s else "") or "—"
    director = (s.director if s else "") or "—"
    # "-" gets visually reordered inside RTL text by Qt's bidi algorithm;
    # "/" does not (same workaround as daily_contact_screen._format_doc_date).
    letter_date = letter_date.replace("-", "/")
    period_start = period_start.replace("-", "/")
    period_end = period_end.replace("-", "/")

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
        page_w = float(writer.width())
        page_h = float(writer.height())
        margin = 38.0
        content_w = page_w - (margin * 2)

        y = draw_official_pdf_header(
            painter,
            page_width=page_w,
            margin=margin,
            top=18.0,
            settings=settings,
            title=_TITLE,
        )

        meta_lines = [
            f"{city}، بتاريخ: {letter_date}",
            f"إلى السيد/ة: {supplier} — {company}",
            f"العنوان: {supplier_addr}",
            f"الموضوع: طلبية المواد الغذائية للفترة من {period_start} إلى {period_end} "
            f"— في إطار الصفقة رقم {contract_num}",
        ]
        for line in meta_lines:
            _draw_letter_pdf_text(
                painter,
                QRectF(margin, y, content_w, 18),
                line,
                size=10,
                color=COLOR_TEXT_SECONDARY,
                align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
            )
            y += 20
        y += 10

        # Matches templets/رسالة الطلبية.docx — the real accepted form shows
        # one aggregate count per meal, not a collegial/qualifying/monitors
        # breakdown. The on-screen cards still collect that breakdown for
        # planning; only the generated document is aggregate.
        columns = ["الوجبة", "الأعداد", "ملاحظات"]
        col_widths = [content_w * 0.25, content_w * 0.20, content_w * 0.55]
        header_h = 32.0
        row_h = 40.0
        n_rows = len(_MEAL_ORDER) + 1  # + total row
        table_h = header_h + (row_h * n_rows)
        right = margin + content_w

        current_right = right
        for col_label, col_w in zip(columns, col_widths):
            rect = QRectF(current_right - col_w, y, col_w, header_h)
            _draw_letter_pdf_cell(
                painter, rect,
                background=COLOR_ACCENT, border=COLOR_ACCENT,
                text=col_label, text_color="white", size=11, bold=True,
            )
            current_right = rect.left()

        row_y = y + header_h
        grand_total = 0
        for meal_key, meal_label in _MEAL_ORDER:
            card = cards[meal_key]
            tot = card.total()
            grand_total += tot
            values = [meal_label, str(tot), ""]
            current_right = right
            for index, (value, col_w) in enumerate(zip(values, col_widths)):
                rect = QRectF(current_right - col_w, row_y, col_w, row_h)
                _draw_letter_pdf_cell(
                    painter, rect,
                    background="#F8F9FA" if index == 0 else "white",
                    border=COLOR_BORDER,
                    text=value,
                    text_color=_MEAL_COLORS.get(meal_key, COLOR_TEXT_PRIMARY) if index == 0 else COLOR_TEXT_PRIMARY,
                    size=11, bold=(index == 0),
                )
                current_right = rect.left()
            row_y += row_h

        total_rect = QRectF(right - sum(col_widths), row_y, sum(col_widths), row_h)
        _draw_letter_pdf_cell(
            painter, total_rect,
            background=COLOR_ACCENT_DEEP, border=COLOR_ACCENT_DEEP,
            text=f"الإجمالي العام: {grand_total}", text_color="white", size=12, bold=True,
        )
        y += table_h + 16

        if notes.strip():
            _draw_letter_pdf_text(
                painter,
                QRectF(margin, y, content_w, 18),
                f"ملاحظات: {notes.strip()}",
                size=10,
                color=COLOR_TEXT_PRIMARY,
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
    finally:
        painter.end()


def _find_order_letter_template() -> Path | None:
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for candidate in directory.glob("*.docx"):
            if "رسالةالطلبية" in _normalize_template_name(candidate.stem):
                return candidate
    return None


def _fill_order_letter_document_xml(
    root: ET.Element,
    *,
    school_year: str,
    number: str,
    display_date: str,
    supplier_line: str,
    place: str,
    cards: Dict[str, "_MealQtyCard"],
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

    tables = root.findall(".//w:tbl", _WORD_NS)
    if not tables:
        return
    rows = tables[0].findall("./w:tr", _WORD_NS)
    for row_index, (meal_key, _) in enumerate(_MEAL_ORDER, start=1):
        if row_index >= len(rows):
            break
        cells = rows[row_index].findall("./w:tc", _WORD_NS)
        if len(cells) >= 2:
            _set_cell_text(cells[1], cards[meal_key].total())


def _write_order_letter_docx(
    path: Path,
    settings,
    letter_date: str,
    cards: Dict[str, "_MealQtyCard"],
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
                    number="....",
                    display_date=display_date,
                    supplier_line=supplier_line,
                    place=place,
                    cards=cards,
                )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)


# ── Main screen ───────────────────────────────────────────────────────────────

class OrderLetterScreen(QWidget):
    """Order letter screen — form + live preview + history."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._cards: Dict[str, _MealQtyCard] = {}
        self._notes_edit: Optional[QTextEdit] = None  # set during _build_form_panel
        self._build_ui()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # Title
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(17); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color:{_INK};")
        sub = QLabel(_SUBTITLE)
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        root.addWidget(title)
        root.addWidget(sub)

        # Toolbar
        root.addLayout(self._build_toolbar())

        # Splitter: form (right) | preview (left)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            "QSplitter::handle { background:#d6d6c8; border-radius:4px; }"
        )

        splitter.addWidget(self._build_preview_panel())   # left = preview
        splitter.addWidget(self._build_form_panel())      # right = form
        splitter.setSizes([520, 320])
        root.addWidget(splitter, 1)

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        new_btn    = _btn(_BTN_NEW,     "#16a34a", icon=_BTN_NEW_ICON)
        save_btn   = _btn(_BTN_SAVE,    COLOR_ACCENT, icon=_BTN_SAVE_ICON)
        delete_btn = _btn(_BTN_DELETE,  COLOR_DANGER, icon=_BTN_DELETE_ICON)
        preview_btn= _btn(_BTN_PREVIEW, _INK, icon=_BTN_PREVIEW_ICON)
        export_btn = _btn(_BTN_EXPORT,  _INK, icon=_BTN_EXPORT_ICON)

        new_btn.clicked.connect(self._on_new)
        save_btn.clicked.connect(self._on_save)
        delete_btn.clicked.connect(self._on_delete)
        preview_btn.clicked.connect(self._update_preview)
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

    def _build_form_panel(self) -> QWidget:
        """Right panel: dates, auto-fill, meal cards, notes."""
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 0, 4, 10)
        layout.setSpacing(12)

        # Date inputs
        date_grp = QGroupBox("معلومات الرسالة")
        date_grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        date_grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                background:{_PANEL_BG};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:10px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        date_form = QVBoxLayout(date_grp)

        def _date_row(label: str, edit: DateInput) -> QHBoxLayout:
            h = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px;")
            h.addWidget(lbl)
            h.addStretch()
            h.addWidget(edit)
            return h

        def _date_edit() -> DateInput:
            d = DateInput(display_format="yyyy-MM-dd")
            d.setDate(QDate.currentDate())
            d.setMinimumHeight(34)
            d.setMinimumWidth(128)
            d.setStyleSheet(
                f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
                f"padding:4px 8px; font-size:{FONT_BODY}px;"
            )
            d.dateChanged.connect(self._update_preview)
            return d

        self._letter_date  = _date_edit()
        self._period_start = _date_edit()
        self._period_end   = _date_edit()
        # Default period: today → 7 days
        self._period_end.setDate(QDate.currentDate().addDays(6))

        date_form.addLayout(_date_row(_LBL_DATE, self._letter_date))
        date_form.addLayout(_date_row(_LBL_FROM, self._period_start))
        date_form.addLayout(_date_row(_LBL_TO,   self._period_end))

        autofill_btn = _btn(_BTN_AUTOFILL, "#0891b2", icon=_BTN_AUTOFILL_ICON)
        autofill_btn.clicked.connect(self._auto_fill)
        date_form.addWidget(autofill_btn)

        layout.addWidget(date_grp)

        # Meal cards
        for meal_key, meal_label in _MEAL_ORDER:
            card = _MealQtyCard(meal_key, meal_label, _MEAL_COLORS[meal_key])
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # Live update preview when any spin changes
            for sp in (card._sp_coll, card._sp_qual, card._sp_mon):
                sp.valueChanged.connect(self._update_preview)
            self._cards[meal_key] = card
            layout.addWidget(card)

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
        self._notes_edit.textChanged.connect(self._update_preview)
        layout.addWidget(self._notes_edit)
        layout.addStretch()

        panel.setWidget(content)
        return panel

    def _build_preview_panel(self) -> QWidget:
        """Left panel: HTML letter preview."""
        panel = QFrame()
        panel.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:16px;"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        hdr = QLabel("معاينة الرسالة")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.setStyleSheet(
            f"background:{_INK}; color:white; font-size:{FONT_BODY}px;"
            "font-weight:bold; padding:10px; border-radius:16px 16px 0 0;"
        )
        layout.addWidget(hdr)

        self._preview = QTextBrowser()
        self._preview.setOpenExternalLinks(False)
        self._preview.setStyleSheet(
            f"border:none; background:white; font-size:{FONT_BODY}px; padding:8px;"
        )
        layout.addWidget(self._preview)
        return panel

    # ── Helpers ────────────────────────────────────────────────────────────

    def _update_preview(self) -> None:
        if self._notes_edit is None:
            return
        settings = get_school_settings()
        html = _generate_letter_html(
            settings,
            letter_date=self._letter_date.date().toString("yyyy-MM-dd"),
            period_start=self._period_start.date().toString("yyyy-MM-dd"),
            period_end=self._period_end.date().toString("yyyy-MM-dd"),
            cards=self._cards,
            notes=self._notes_edit.toPlainText(),
        )
        self._preview.setHtml(html)

    def _on_export(self) -> None:
        fmt = get_document_export_format()
        if fmt == EXPORT_FORMAT_ASK:
            fmt = ask_export_format(self)
            if fmt is None:
                return
        is_pdf = fmt == EXPORT_FORMAT_PDF
        letter_date = self._letter_date.date().toString("yyyy-MM-dd")

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
            if is_pdf:
                _write_order_letter_pdf(
                    path,
                    settings,
                    letter_date=letter_date,
                    period_start=self._period_start.date().toString("yyyy-MM-dd"),
                    period_end=self._period_end.date().toString("yyyy-MM-dd"),
                    cards=self._cards,
                    notes=self._notes_edit.toPlainText() if self._notes_edit else "",
                )
            else:
                _write_order_letter_docx(path, settings, letter_date, self._cards)
            QMessageBox.information(self, "تم", _PDF_SAVED_OK if is_pdf else _DOCX_SAVED_OK)
        except Exception as exc:
            error_prefix = _PDF_SAVE_ERROR if is_pdf else _DOCX_SAVE_ERROR
            QMessageBox.critical(self, "خطأ", f"{error_prefix}\n{exc}")

    def _auto_fill(self) -> None:
        """Fill all three cards with the current student counts."""
        counts = get_student_counts()
        if counts.get("total", 0) == 0:
            QMessageBox.information(self, "تنبيه", "لا يوجد تلاميذ مسجلين في قاعدة البيانات. يُرجى إضافة تلاميذ أولاً.")
            return
            
        # إعدادي = internat, تأهيلي = cantine − monitors, معلمون = monitors
        internat = counts.get("internat", 0)
        monitors = counts.get("monitors", 0)
        cantine  = max(0, counts.get("cantine", 0) - monitors)

        for card in self._cards.values():
            card.set_values(internat, cantine, monitors)
        self._update_preview()

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
        self._update_preview()

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
        self._update_preview()

    def _on_save(self) -> None:
        letter = OrderLetter(
            letter_date=self._letter_date.date().toString("yyyy-MM-dd"),
            period_start=self._period_start.date().toString("yyyy-MM-dd"),
            period_end=self._period_end.date().toString("yyyy-MM-dd"),
            notes=self._notes_edit.toPlainText().strip(),
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
        """Refresh history and preview when the screen becomes visible."""
        super().showEvent(event)
        self._refresh_history()
        self._update_preview()
