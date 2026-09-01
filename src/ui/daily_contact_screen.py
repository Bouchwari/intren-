"""
src/ui/daily_contact_screen.py
Daily contact sheet (ورقة الاتصال اليومية) — count beneficiaries per meal per day.
Layout: date picker → 3 meal cards (فطور/غداء/عشاء) → history table.
"""
import datetime
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QDate, QEvent, QMarginsF, QPoint, QRectF, QTimer, Signal, Qt
from PySide6.QtGui import (
    QColor, QFont, QIntValidator, QPageLayout, QPageSize, QPainter, QPdfWriter,
    QPen, QTextOption,
)
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QComboBox, QFileDialog, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSizePolicy, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_PANEL, COLOR_PANEL_ALT,
    COLOR_PAPER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_IFTAR, MEAL_SHOUR, MEAL_LABELS,
    EXPORT_FORMAT_ASK, EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.attendance_estimate import EstimateResult, estimate_attendance
from core.active_cycles import visible_cycles
from core.contact_counts import (
    CATEGORY_COLLEGIAL, CATEGORY_PRIMARY, CATEGORY_QUALIFYING,
    count_students, empty_counts,
)
from core.models import DailyContact
from ui.document_header import (
    ask_export_format, draw_official_pdf_footer, draw_official_pdf_header,
    register_docx_namespaces,
)
from ui.batch_export import draw_placeholder_pdf_page
from ui.theme import body_font_family
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton
from core.ramadan import meals_for_date
from data.database import (
    get_day_contacts,
    get_all_students,
    get_daily_contact_document_number_draft,
    get_document_export_format,
    get_document_number_for_date,
    get_last_contacts_before,
    get_next_daily_contact_document_number,
    get_recent_contacts,
    get_recent_daily_contact_documents,
    get_school_settings,
    get_ramadan_overrides,
    is_holiday,
    record_daily_contact_document,
    save_daily_contact_document_number_draft,
    save_daily_contact,
)

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "ورقة الاتصال اليومية"
_SUBTITLE       = "عدد المستفيدين من خدمة الإطعام المدرسي"
_BTN_PREV       = "اليوم السابق"
_BTN_NEXT       = "اليوم التالي"
_BTN_TODAY      = "اليوم"
_BTN_LOAD       = "تحميل"
_TOAST_COPY_OK  = "تم نسخ بيانات {date} — يمكنك تعديلها قبل الحفظ"
_TOAST_COPY_NONE = "لا توجد بيانات سابقة لنسخها"
_BTN_SAVE       = "حفظ وتسجيل"
_BTN_SAVE_ICON  = "💾"
_LBL_DATE       = "التاريخ:"
_LBL_NUMBER     = "رقم:"
_LBL_ACTIONS    = "الإجراء"
_LBL_DOCUMENT   = "بيانات الوثيقة"
_LBL_FILL_MODE  = "تعبئة الأرقام"
_NUMBER_HINT    = "يتغير الرقم تلقائياً بعد الحفظ أو الطباعة، ويمكن تعديله يدوياً."
_LBL_PRIMARY    = "الابتدائي"
_LBL_COLLEGIAL  = "إعدادي"
_LBL_QUALIFYING = "تأهيلي"
_LBL_MONITORS   = "معلمو الداخلية"
_LBL_GRANTED    = "كاملة"
_LBL_COMPLEMENT = "وجبة غذاء"
_LBL_TOTAL      = "المجموع"
_LBL_GRAND_TOT  = "الإجمالي العام"
_HDR_HISTORY    = ["رقم الوثيقة", "التاريخ", "العملية", "الفطور", "الغداء", "العشاء", "الإجمالي", "وقت التسجيل"]
_SAVED_OK       = "تم حفظ ورقة الاتصال بنجاح."
_BTN_EXPORT_DOC = "طباعة وتسجيل"
_BTN_EXPORT_DOC_ICON = "🖨"
_DOCX_DIALOG_TITLE = "تحميل ورقة الاتصال اليومية"
_DOCX_DEFAULT_NAME = "ورقة_الاتصال_اليومية"
_DOCX_SAVED_OK = "تم تحميل ورقة الاتصال اليومية بنجاح."
_DOCX_TEMPLATE_MISSING = "تعذر العثور على نموذج ورقة الاتصال اليومية."
_DOCX_SAVE_ERROR = "تعذر تحميل ورقة الاتصال اليومية:"
_PDF_DIALOG_TITLE = "تصدير ورقة الاتصال اليومية"
_PDF_DEFAULT_NAME = "ورقة_الاتصال_اليومية"
_PDF_FILTER = "PDF (*.pdf)"
_PDF_SAVED_OK = "تم تصدير ورقة الاتصال اليومية بنجاح."
_PDF_SAVE_ERROR = "تعذر تصدير ورقة الاتصال اليومية:"
_CONTACT_TEMPLATE_FILE = "ورقة الاتصال  اليومية.docx"
_WORD_FILTER = "Word (*.docx)"

# Maps DB meal_type key to display label (using MEAL_LABELS from settings)
# _MEAL_ORDER stays the three normal meals: the official ورقة الاتصال Word
# template has exactly three meal columns and must not be restructured.
# _CARD_MEAL_ORDER adds the two Ramadan meals, which the SCREEN offers on a
# Ramadan day so the counts can be recorded even though the printed sheet
# keeps its own fixed layout.
_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]

_RAMADAN_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_IFTAR, MEAL_LABELS[MEAL_IFTAR]),
    (MEAL_SHOUR, MEAL_LABELS[MEAL_SHOUR]),
]

# Every meal gets a card; only the ones the selected date actually serves are
# visible, so switching to a Ramadan day swaps the three normal cards for the
# two Ramadan ones without rebuilding the layout.
_CARD_MEAL_ORDER: List[Tuple[str, str]] = _MEAL_ORDER + _RAMADAN_MEAL_ORDER

# Card accent colors per meal — same amber/teal/navy convention as the meal
# program table (ui_design.md's per-meal accents), not this page's own guess.
_MEAL_COLORS = {
    MEAL_FTOUR: "#EF9F27",   # amber
    MEAL_GHADA: COLOR_ACCENT,
    MEAL_ASHA:  "#534AB7",   # navy
    MEAL_IFTAR: "#C2703D",   # clay — matches meal_program_screen's Ramadan accent
    MEAL_SHOUR: COLOR_ACCENT,
}
_PAGE_BG = COLOR_PAPER
_PANEL_BG = COLOR_PANEL
_PANEL_BORDER = COLOR_BORDER
_INK = COLOR_TEXT_PRIMARY
_HISTORY_COLUMN_WIDTHS = [100, 100, 92, 86, 86, 86, 92, 128]
_HISTORY_DATE_COLUMN = 1
_ACTION_LABELS = {
    "save": "حفظ",
    "print": "طباعة",
    "batch_export": "توليد لعدة أيام",
}
_MODE_MANUAL = "إدخال يدوي"
_MODE_AUTO = "توليد تلقائي"
_MODE_MANUAL_LABEL = "وضع: إدخال يدوي 📝"
_MODE_AUTO_LABEL = "وضع: توليد تلقائي 🤖"
# Short forms for the 3-way segmented selector — the descriptive labels
# above are too long to sit 3-across in one small pill row.
_FILL_SEG_MANUAL = "يدوي"
_FILL_SEG_AUTO = "تلقائي"
_FILL_SEG_COPY = "نسخ الأمس"
_TOAST_MANUAL = "تم التحويل إلى الإدخال اليدوي — يمكنك تعديل الأرقام"
_TOAST_AUTO = "اضغط تحميل اليوم لتوليد الأرقام تلقائياً"
_TOAST_NO_STUDENTS = "لا يوجد تلاميذ في اللائحة"
_TOAST_NO_CLASSIFIED_STUDENTS = (
    "لم يتم التعرف على قسم أي تلميذ — تأكد من ملء حقل \"القسم\" في لائحة"
    " التلاميذ، وإلا فسيتم توليد أرقام صفرية."
)
_ESTIMATE_HISTORY_LIMIT = 900
_CONFIDENCE_LABELS = {"low": "منخفضة", "medium": "متوسطة", "high": "عالية"}
_ESTIMATE_NOTE_LOW = (
    "⚠️ لا يوجد سجل كافٍ لتقدير الحضور (متوفر {records} من 3 أيام على الأقل لنفس اليوم والوجبة)"
    " — تم عرض العدد الكامل للائحة، يرجى المراجعة يدوياً."
)
_ESTIMATE_NOTE_ESTIMATED = (
    "🧮 أعداد مُقدَّرة اعتماداً على {records} يوم سابق لنفس اليوم والوجبة — مستوى الثقة: {confidence}."
)
_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_W_NS = _WORD_NS["w"]


def _template_dirs() -> List[Path]:
    """Template locations for source runs and PyInstaller builds."""
    base_dir = Path(__file__).resolve().parents[2]
    dirs = [
        Path.cwd() / "templets",
        base_dir / "templets",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.extend([
            exe_dir / "templets",
            exe_dir / "_internal" / "templets",
        ])
    runtime_dir = getattr(sys, "_MEIPASS", None)
    if runtime_dir:
        dirs.append(Path(runtime_dir) / "templets")
    return dirs


def _normalize_template_name(value: str) -> str:
    return (
        value.replace("إ", "ا")
        .replace("أ", "ا")
        .replace("آ", "ا")
        .replace(" ", "")
    )


def _find_contact_template() -> Path | None:
    for directory in _template_dirs():
        exact = directory / _CONTACT_TEMPLATE_FILE
        if exact.exists():
            return exact
        if not directory.exists():
            continue
        for candidate in directory.glob("*.docx"):
            normalized = _normalize_template_name(candidate.stem)
            if "ورقةالاتصالاليومية" in normalized:
                return candidate
    return None


def _set_docx_text(container: ET.Element, value: str) -> None:
    text_nodes = container.findall(".//w:t", _WORD_NS)
    if not text_nodes:
        paragraph = container.find(".//w:p", _WORD_NS)
        if paragraph is None:
            paragraph = ET.SubElement(container, f"{{{_W_NS}}}p")
        run = ET.SubElement(paragraph, f"{{{_W_NS}}}r")
        text = ET.SubElement(run, f"{{{_W_NS}}}t")
        text.text = value
        text.set(_XML_SPACE, "preserve")
        return
    text_nodes[0].text = value
    text_nodes[0].set(_XML_SPACE, "preserve")
    for node in text_nodes[1:]:
        node.text = ""


def _cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.findall(".//w:t", _WORD_NS)).strip()


def _set_cell_text(cell: ET.Element, value: int | str) -> None:
    _set_docx_text(cell, str(value))


def _format_doc_date(date_str: str) -> str:
    return date_str.replace("-", "/")


def _academy_line(value: str) -> str:
    value = value.strip()
    if not value:
        return "الأكاديمية الجهوية للتربية والتكوين"
    if "الأكاديمية" in value:
        return value
    return f"الأكاديمية الجهوية للتربية والتكوين لجهة {value}"


def _province_line(value: str) -> str:
    value = value.strip()
    if not value:
        return "المديرية الإقليمية"
    if "المديرية" in value:
        return value
    return f"المديرية الإقليمية {value}"


def _write_daily_contact_docx(
    path: Path,
    date_str: str,
    contacts: List[DailyContact],
    *,
    document_number: str = "",
    place: str = "",
    academy: str = "",
    province: str = "",
    school_name: str = "",
    school_year: str = "",
) -> None:
    template_path = _find_contact_template()
    if template_path is None:
        raise FileNotFoundError(_DOCX_TEMPLATE_MISSING)

    register_docx_namespaces()
    path.parent.mkdir(parents=True, exist_ok=True)
    contact_by_meal = {contact.meal_type: contact for contact in contacts}
    display_date = _format_doc_date(date_str)

    with ZipFile(template_path, "r") as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                root = ET.fromstring(data)
                _fill_contact_document_xml(
                    root,
                    display_date,
                    contact_by_meal,
                    document_number=document_number,
                    place=place,
                    school_year=school_year,
                    meals=_meals_for_document(date_str),
                )
                _fix_contact_header_body_gap(root)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif item.filename.startswith("word/header") and item.filename.endswith(".xml"):
                root = ET.fromstring(data)
                _fill_contact_header_xml(
                    root,
                    academy=academy,
                    province=province,
                    school_name=school_name,
                )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)


def _force_arabswell_font(paragraph: ET.Element) -> None:
    """The header's academy/directorate/school identity lines must
    always render in "arabswell" (arabswell_1 — the real internal family
    name of the bundled templets/maghribi-font 1.ttf, the project's own
    official Arabic display font) — an explicit standing instruction
    from the user, not just whatever font a hand-edited template
    paragraph happens to currently carry."""
    for run in paragraph.findall(".//w:r", _WORD_NS):
        rPr = run.find("w:rPr", _WORD_NS)
        if rPr is None:
            rPr = ET.Element(f"{{{_W_NS}}}rPr")
            run.insert(0, rPr)
        rFonts = rPr.find("w:rFonts", _WORD_NS)
        if rFonts is None:
            rFonts = ET.SubElement(rPr, f"{{{_W_NS}}}rFonts")
        rFonts.set(f"{{{_W_NS}}}cs", "arabswell_1")
        rFonts.set(f"{{{_W_NS}}}hint", "cs")


def _fill_contact_header_xml(
    root: ET.Element,
    *,
    academy: str,
    province: str,
    school_name: str,
) -> int:
    """Returns how many header paragraphs were actually matched and
    filled — callers that have their own fallback for "nothing matched"
    (see daily_reception_screen.py's _write_reception_docx) use this to
    only apply that fallback when it's actually needed, instead of
    always overwriting whatever this function just filled."""
    identity_lines = [
        _academy_line(academy),
        _province_line(province),
        school_name.strip() or "اسم المؤسسة",
    ]
    header_index = 0
    for paragraph in root.findall(".//w:p", _WORD_NS):
        if paragraph.findall(".//w:p", _WORD_NS):
            continue
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS)).strip()
        if not text:
            continue
        if text.startswith("الأكاديمية") or text.startswith("المديرية") or "الثانوية" in text or "المؤسسة" in text:
            _set_docx_text(paragraph, identity_lines[header_index % len(identity_lines)])
            _force_arabswell_font(paragraph)
            header_index += 1
    return header_index


def _fix_contact_header_body_gap(root: ET.Element) -> None:
    """Same fix as the one built for محضر التسلم اليومي's template
    (see daily_reception_screen.py's _fix_reception_header_body_gap for
    the full investigation) — this template's own page margins leave the
    header zone (pgMar/@header, 1928 twentieths-of-a-pt) starting AFTER
    the body zone (pgMar/@top, 1417) even begins — a NEGATIVE gap, worse
    than reception's ~3pt one. The header's own academy/directorate/
    school block still needs ~45-50pt to lay out. A pre-existing
    template design issue, not something this app's data-filling
    touched before — likely stayed unnoticed while the header's `pic:`
    namespace bug (see `register_docx_namespaces()`, fixed) made that
    header content fail to render at all; now that it renders, it needs
    real room. Only raises the margin, never lowers an already-generous
    one."""
    pgMar = root.find(".//w:sectPr/w:pgMar", _WORD_NS)
    if pgMar is None:
        return
    header_attr = f"{{{_W_NS}}}header"
    top_attr = f"{{{_W_NS}}}top"
    header_dist = pgMar.get(header_attr)
    if header_dist is None:
        return
    needed_top = int(header_dist) + 1000  # ~50pt of room for the header's 3 text lines
    current_top = int(pgMar.get(top_attr, "0"))
    if current_top < needed_top:
        pgMar.set(top_attr, str(needed_top))



def _meals_for_document(date_str: str) -> List[Tuple[str, str]]:
    """(meal key, Arabic label) for a document's own date — Ramadan's two or
    the normal three. Both the Word and PDF writers call this so a printed
    sheet always matches what the screen collected for that day."""
    active = meals_for_date(date_str, get_school_settings(), get_ramadan_overrides())
    labels = dict(_CARD_MEAL_ORDER)
    return [(key, labels.get(key, key)) for key in active]


def _trim_contact_table_to_meals(
    table: ET.Element, meals: List[Tuple[str, str]]
) -> None:
    """Reshape the template's meal table to the day's actual meals.

    The template is built for three meals: 7 grid columns — a label column
    plus 3 × (كاملة, وجبة غذاء). A Ramadan day has two meals, so the user
    asked for the same document with two columns instead of three. Extra
    column pairs are removed from every row and from the table grid, and the
    meal captions are rewritten to the day's own meals.
    """
    rows = table.findall("./w:tr", _WORD_NS)
    if len(rows) < 8:
        return

    meal_count = len(meals)
    data_columns = 1 + (meal_count * 2)   # label column + 2 per meal
    span_attr = f"{{{_W_NS}}}val"

    def drop_extra(row: ET.Element, keep: int) -> None:
        cells = row.findall("./w:tc", _WORD_NS)
        for extra in cells[keep:]:
            row.remove(extra)

    # Row 0 is one merged banner cell spanning the whole table.
    banner = rows[0].find("./w:tc/w:tcPr/w:gridSpan", _WORD_NS)
    if banner is not None:
        banner.set(span_attr, str(data_columns))

    # Row 1 holds the meal captions, one cell per meal (each spanning 2).
    caption_cells = rows[1].findall("./w:tc", _WORD_NS)
    for index, (_key, label) in enumerate(meals, start=1):
        if index < len(caption_cells):
            _set_cell_text(caption_cells[index], label)
    drop_extra(rows[1], 1 + meal_count)

    for row in rows[2:7]:                 # نوع المنحة + the four cycle rows
        drop_extra(row, data_columns)
    drop_extra(rows[7], 1 + meal_count)   # المجموع row mirrors the captions

    grid = table.find("./w:tblGrid", _WORD_NS)
    if grid is not None:
        for extra in grid.findall("./w:gridCol", _WORD_NS)[data_columns:]:
            grid.remove(extra)


def _fill_contact_document_xml(
    root: ET.Element,
    display_date: str,
    contact_by_meal: Dict[str, DailyContact],
    *,
    document_number: str,
    place: str,
    school_year: str = "",
    meals: Optional[List[Tuple[str, str]]] = None,
) -> None:
    number_text = document_number.strip() or "...."
    place_text = place.strip() or "..............."
    year_text = school_year.strip() or "—"
    for paragraph in root.findall(".//w:p", _WORD_NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS)).strip()
        if text.startswith("ورقة الاتصال اليومية"):
            _set_docx_text(paragraph, f"ورقة الاتصال اليومية  رقم: {number_text} ليوم : {display_date}")
        elif text.startswith("حرر ب"):
            _set_docx_text(paragraph, f"حرر ب{place_text} بتاريخ {display_date}")
        elif text.startswith("الموسم الدراسي"):
            _set_docx_text(paragraph, f"الموسم الدراسي {year_text}")

    tables = root.findall(".//w:tbl", _WORD_NS)
    if not tables:
        return
    rows = tables[0].findall("./w:tr", _WORD_NS)
    if len(rows) < 8:
        return

    meals = meals or _MEAL_ORDER
    if len(meals) != len(_MEAL_ORDER):
        _trim_contact_table_to_meals(tables[0], meals)
        rows = tables[0].findall("./w:tr", _WORD_NS)
    else:
        caption_cells = rows[1].findall("./w:tc", _WORD_NS)
        for index, (_key, label) in enumerate(meals, start=1):
            if index < len(caption_cells):
                _set_cell_text(caption_cells[index], label)

    primary_cells = rows[3].findall("./w:tc", _WORD_NS)
    collegial_cells = rows[4].findall("./w:tc", _WORD_NS)
    qualifying_cells = rows[5].findall("./w:tc", _WORD_NS)
    monitors_cells = rows[6].findall("./w:tc", _WORD_NS)
    total_cells = rows[7].findall("./w:tc", _WORD_NS)

    for meal_index, (meal_key, _) in enumerate(meals):
        contact = contact_by_meal.get(meal_key) or DailyContact(date="", meal_type=meal_key)
        first_col = 1 + (meal_index * 2)
        second_col = first_col + 1

        for cells, first_value, second_value in (
            (primary_cells, contact.primary_granted, contact.primary_complement),
            (collegial_cells, contact.collegial_granted + contact.collegial_paying, contact.collegial_complement),
            (qualifying_cells, contact.qualifying_granted + contact.qualifying_paying, contact.qualifying_complement),
            (monitors_cells, contact.monitors, contact.monitors_complement),
        ):
            if second_col < len(cells):
                _set_cell_text(cells[first_col], first_value)
                _set_cell_text(cells[second_col], second_value)

        total_index = meal_index + 1
        if total_index < len(total_cells):
            _set_cell_text(total_cells[total_index], contact.grand_total)


def _draw_contact_pdf_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    *,
    size: int,
    color: str,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
) -> None:
    # "Segoe UI" is Windows-only — on a system without it, Qt substitutes a
    # fallback that has dropped diacritics like hamza (إ -> ا) in testing.
    # body_font_family() is the app's own bundled Cairo font, verified to
    # render Arabic correctly everywhere else in the app.
    font = QFont(body_font_family())
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    option = QTextOption()
    option.setTextDirection(Qt.LayoutDirection.RightToLeft)
    option.setAlignment(align)
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    painter.drawText(rect, text, option)


def _draw_contact_pdf_cell(
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
    _draw_contact_pdf_text(
        painter,
        rect.adjusted(4, 2, -4, -2),
        text,
        size=size,
        color=text_color,
        bold=bold,
    )


def _write_daily_contact_pdf(
    path: Path,
    date_str: str,
    contacts: List[DailyContact],
    *,
    document_number: str = "",
    place: str = "",
) -> None:
    """Render the daily contact sheet as a single-page official PDF. Thin
    wrapper around _draw_daily_contact_pdf_page — batch export uses that
    directly to draw many days onto one shared writer instead of opening
    a new file per day."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TITLE)

    painter = QPainter(writer)
    try:
        _draw_daily_contact_pdf_page(
            painter, float(writer.width()), float(writer.height()),
            date_str, contacts, document_number=document_number, place=place,
        )
    finally:
        painter.end()


def _draw_daily_contact_pdf_page(
    painter: QPainter,
    page_w: float,
    page_h: float,
    date_str: str,
    contacts: List[DailyContact],
    *,
    document_number: str = "",
    place: str = "",
) -> None:
    """Draw one contact-sheet page into an already-open painter — the same
    header/footer helpers already proven on the meal program PDF export.
    academy/province/school_name are not accepted here (unlike the DOCX
    writer) because draw_official_pdf_header reads them straight off the
    SchoolSettings row instead of taking them as separate strings."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    contact_by_meal = {contact.meal_type: contact for contact in contacts}
    display_date = _format_doc_date(date_str)
    # A Ramadan day prints two meal columns instead of three — same sheet,
    # fewer columns, matching what the screen collected for that date.
    meals = _meals_for_document(date_str)
    place_text = place.strip() or "..............."
    margin = 38.0
    content_w = page_w - (margin * 2)
    settings = get_school_settings()

    title = f"{_TITLE}  رقم: {document_number or '....'} ليوم: {display_date}"
    table_y = draw_official_pdf_header(
        painter,
        page_width=page_w,
        margin=margin,
        top=18.0,
        settings=settings,
        title=title,
    )
    table_y += 4

    rows_data = [
        (_LBL_PRIMARY, "primary_granted", "primary_complement"),
        (_LBL_COLLEGIAL, "collegial_granted", "collegial_complement"),
        (_LBL_QUALIFYING, "qualifying_granted", "qualifying_complement"),
        (_LBL_MONITORS, "monitors", "monitors_complement"),
    ]

    footer_h = 90.0
    table_x = margin
    table_w = content_w
    header_rows_h = 62.0
    n_data_rows = len(rows_data) + 1  # + total row
    table_h = page_h - table_y - footer_h - margin
    # Cap row height instead of always stretching to fill the page —
    # with only 5 rows on a portrait A4 page, stretching to the footer
    # made each row balloon to ~140pt for a single centered number.
    row_h = min(46.0, (table_h - header_rows_h) / n_data_rows)
    label_w = 130.0
    meal_w = (table_w - label_w) / len(meals)
    sub_w = meal_w / 2
    right = table_x + table_w

    # Header row 1: label column + one cell per meal name
    label_header = QRectF(right - label_w, table_y, label_w, header_rows_h / 2)
    _draw_contact_pdf_cell(
        painter, label_header,
        background=COLOR_ACCENT, border=COLOR_ACCENT,
        text="", text_color="white", size=11, bold=True,
    )
    current_right = label_header.left()
    for _, meal_label in meals:
        rect = QRectF(current_right - meal_w, table_y, meal_w, header_rows_h / 2)
        _draw_contact_pdf_cell(
            painter, rect,
            background=COLOR_ACCENT, border=COLOR_ACCENT,
            text=meal_label, text_color="white", size=12, bold=True,
        )
        current_right = rect.left()

    # Header row 2: granted / complement sub-labels under each meal
    sub_y = table_y + (header_rows_h / 2)
    label_subheader = QRectF(right - label_w, sub_y, label_w, header_rows_h / 2)
    _draw_contact_pdf_cell(
        painter, label_subheader,
        background=COLOR_ACCENT, border="white",
        text="الفئة", text_color="white", size=10, bold=True,
    )
    current_right = label_subheader.left()
    for _ in meals:
        for sub_label in (_LBL_GRANTED, _LBL_COMPLEMENT):
            rect = QRectF(current_right - sub_w, sub_y, sub_w, header_rows_h / 2)
            _draw_contact_pdf_cell(
                painter, rect,
                background=COLOR_ACCENT, border="white",
                text=sub_label, text_color="white", size=9,
            )
            current_right = rect.left()

    # Data rows
    for row_index, (row_label, granted_field, complement_field) in enumerate(rows_data):
        row_y = table_y + header_rows_h + (row_index * row_h)
        label_rect = QRectF(right - label_w, row_y, label_w, row_h)
        _draw_contact_pdf_cell(
            painter, label_rect,
            background="#F8F9FA", border=COLOR_BORDER,
            text=row_label, text_color=COLOR_TEXT_PRIMARY, size=11, bold=True,
        )
        current_right = label_rect.left()
        for meal_key, _ in meals:
            contact = contact_by_meal.get(meal_key) or DailyContact(date="", meal_type=meal_key)
            for field_name in (granted_field, complement_field):
                rect = QRectF(current_right - sub_w, row_y, sub_w, row_h)
                _draw_contact_pdf_cell(
                    painter, rect,
                    background="white", border=COLOR_BORDER,
                    text=str(getattr(contact, field_name)), text_color=COLOR_TEXT_PRIMARY, size=11,
                )
                current_right = rect.left()

    # Total row
    total_y = table_y + header_rows_h + (len(rows_data) * row_h)
    total_label_rect = QRectF(right - label_w, total_y, label_w, row_h)
    _draw_contact_pdf_cell(
        painter, total_label_rect,
        background=COLOR_ACCENT, border=COLOR_ACCENT,
        text=_LBL_TOTAL, text_color="white", size=11, bold=True,
    )
    current_right = total_label_rect.left()
    for meal_key, _ in meals:
        contact = contact_by_meal.get(meal_key) or DailyContact(date="", meal_type=meal_key)
        rect = QRectF(current_right - meal_w, total_y, meal_w, row_h)
        _draw_contact_pdf_cell(
            painter, rect,
            background="#F8F9FA", border=COLOR_BORDER,
            text=str(contact.grand_total), text_color=COLOR_TEXT_PRIMARY, size=11, bold=True,
        )
        current_right = rect.left()

    # Below the table, not above it — matches the real accepted template
    # (templets/ورقة الاتصال  اليومية.docx has this line right before
    # التوقيعات, not right after the title).
    _draw_contact_pdf_text(
        painter,
        QRectF(margin, total_y + row_h + 18, content_w, 24),
        f"حرر ب{place_text} بتاريخ {display_date}",
        size=11,
        color=COLOR_TEXT_SECONDARY,
        align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
    )

    footer_y = page_h - margin - footer_h + 6
    # HEADMASTER + STEWARD + WARDEN — matches the real accepted template
    # (templets/ورقة الاتصال  اليومية.docx has all 3 signature lines;
    # documents.md's "WARDEN, HEADMASTER" was missing STEWARD).
    draw_official_pdf_footer(
        painter,
        page_width=page_w,
        margin=margin,
        top=footer_y,
        settings=settings,
        roles=["رئيس المؤسسة", "مسير المصالح المادية والمالية", "الحارس العام للداخلية"],
    )


def _spin_style(read_only: bool = False) -> str:
    background = "#f5f5f5" if read_only else "white"
    color = "#64748b" if read_only else "#000000"
    return (
        "QSpinBox {"
        f"width:55px; height:26px; font-size:{FONT_BODY}px;"
        "padding:2px 4px; text-align:center;"
        "border:1px solid #ccc; border-radius:4px;"
        f"background:{background}; color:{color};"
        "}"
    )


def _spin() -> QSpinBox:
    """Styled spin box for count input (0 – 9999)."""
    s = QSpinBox()
    s.setRange(0, 9999)
    s.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    s.setFixedSize(55, 26)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    s.setStyleSheet(_spin_style(False))
    return s


def _bold_label(text: str, size: int = 13) -> QLabel:
    lbl = QLabel(text)
    f = QFont(); f.setPointSize(size); f.setBold(True)
    lbl.setFont(f)
    return lbl


class _FillModeSelector(QFrame):
    """Three-way pick for how a day's numbers get filled in: type them by
    hand, auto-estimate from student history, or copy the last saved day
    outright. Only يدوي/تلقائي are real persistent modes (is_auto/set_auto,
    same API the old 2-state _ModeToggle exposed) — نسخ الأمس is a one-shot
    action: picking it fires copyRequested immediately and the selector
    settles back on يدوي right after, matching what actually happens to
    the data (see DailyContactScreen._on_copy_previous_clicked)."""

    modeChanged = Signal(bool)
    copyRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auto = False
        self.setObjectName("fillModeSelector")
        self.setMinimumWidth(210)
        self.setStyleSheet(f"""
            QFrame#fillModeSelector {{
                background:#ffffff;
                border:1px solid {_PANEL_BORDER};
                border-radius:16px;
            }}
            QLabel {{
                border:none;
                background:transparent;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 6)
        root.setSpacing(4)

        self._state_label = QLabel()
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_label.setStyleSheet(f"color:{_INK}; font-weight:bold; font-size:{FONT_CAPTION}px;")
        root.addWidget(self._state_label)

        row = QHBoxLayout()
        row.setSpacing(4)
        self._manual_btn = self._segment(_FILL_SEG_MANUAL)
        self._auto_btn = self._segment(_FILL_SEG_AUTO)
        self._copy_btn = self._segment(_FILL_SEG_COPY)
        self._manual_btn.clicked.connect(lambda: self.set_auto(False))
        self._auto_btn.clicked.connect(lambda: self.set_auto(True))
        self._copy_btn.clicked.connect(self.copyRequested.emit)
        row.addWidget(self._manual_btn)
        row.addWidget(self._auto_btn)
        row.addWidget(self._copy_btn)
        root.addLayout(row)
        self._update_style()

    def _segment(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFlat(True)
        return btn

    def is_auto(self) -> bool:
        return self._auto

    def set_auto(self, auto: bool) -> None:
        if self._auto == auto:
            return
        self._auto = auto
        self._update_style()
        self.modeChanged.emit(auto)

    def _update_style(self) -> None:
        pill = f"border:none; border-radius:10px; padding:4px 8px; font-size:{FONT_CAPTION}px; font-weight:bold;"
        active = "background:#1fa37a; color:white;"
        inactive = "background:#eef7f2; color:#5A5A40;"
        self._state_label.setText(_MODE_AUTO_LABEL if self._auto else _MODE_MANUAL_LABEL)
        self._manual_btn.setStyleSheet(pill + (inactive if self._auto else active))
        self._auto_btn.setStyleSheet(pill + (active if self._auto else inactive))
        self._copy_btn.setStyleSheet(pill + inactive)  # a one-shot action, never "active"


# ── Meal card widget ──────────────────────────────────────────────────────────

class _MealCard(QGroupBox):
    """Compact form card for one meal's beneficiary counts."""

    def __init__(self, meal_key: str, meal_label: str, color: str,
                 visible: tuple = ()) -> None:
        super().__init__(meal_label)
        self._meal_key = meal_key
        self._color = color
        self._read_only = False
        # Empty = show every cycle, which is what a school that never opened
        # the المستويات المستعملة screen must keep seeing.
        self._visible_cycles = tuple(visible)
        self.setMinimumWidth(335)
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-size: {FONT_SECTION}px; font-weight: bold;
                color: {color};
                background: {_PANEL_BG};
                border: 1px solid {color};
                border-radius: 16px;
                margin-top: 12px; padding: 10px 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top right;
                padding: 0 10px; right: 14px;
            }}
        """)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(14, 10, 14, 10)

        # Column headers
        hdr = QGridLayout()
        hdr.setColumnMinimumWidth(0, 108)
        hdr.setColumnMinimumWidth(1, 58)
        hdr.setColumnMinimumWidth(2, 68)
        hdr.setColumnMinimumWidth(3, 58)
        for col, lbl in enumerate(["", _LBL_GRANTED, _LBL_COMPLEMENT, _LBL_TOTAL]):
            h = QLabel(lbl)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: {FONT_CAPTION}px; font-weight: bold;"
            )
            hdr.addWidget(h, 0, col)
        layout.addLayout(hdr)

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.Shape.HLine)
        self._sep.setStyleSheet(f"color: {COLOR_BORDER};")
        layout.addWidget(self._sep)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnMinimumWidth(0, 108)
        grid.setColumnMinimumWidth(1, 58)
        grid.setColumnMinimumWidth(2, 68)
        grid.setColumnMinimumWidth(3, 58)

        self._pg = _spin()
        self._pc = _spin()
        self._cg = _spin()
        self._cc = _spin()
        self._qg = _spin()
        self._qc = _spin()
        self._mo = _spin()
        self._mc = _spin()

        self._pt_lbl = QLabel("0")
        self._ct_lbl = QLabel("0")
        self._qt_lbl = QLabel("0")
        self._mt_lbl = QLabel("0")
        self._gt_lbl = QLabel("0")

        for lbl in (self._pt_lbl, self._ct_lbl, self._qt_lbl, self._mt_lbl, self._gt_lbl):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {self._color}; font-weight: bold; font-size: {FONT_SECTION}px;"
            )

        # A cycle this school does not run is left off the FORM — see
        # core/active_cycles.py. معلمو الداخلية always stays: they are staff,
        # not a cycle. The PRINTED document is untouched and still carries
        # every row its ministry template has.
        rows = [
            (CATEGORY_PRIMARY, _LBL_PRIMARY, self._pg, self._pc, self._pt_lbl),
            (CATEGORY_COLLEGIAL, _LBL_COLLEGIAL, self._cg, self._cc, self._ct_lbl),
            (CATEGORY_QUALIFYING, _LBL_QUALIFYING, self._qg, self._qc, self._qt_lbl),
            (None, _LBL_MONITORS, self._mo, self._mc, self._mt_lbl),
        ]
        if self._visible_cycles:
            rows = [row for row in rows
                    if row[0] is None or row[0] in self._visible_cycles]
        for row, (_cycle, label, full_spin, lunch_spin, total_label) in enumerate(rows):
            row_label = QLabel(label)
            row_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(row_label, row, 0)
            grid.addWidget(full_spin, row, 1, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lunch_spin, row, 2, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(total_label, row, 3, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(grid)

        # Grand total bar
        gt_row = QHBoxLayout()
        gt_row.addStretch()
        gt_title = QLabel(f"{_LBL_GRAND_TOT}:")
        gt_title.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_BODY}px;")
        self._gt_lbl.setStyleSheet(
            f"color:white; background:{self._color}; font-weight:bold; font-size:{FONT_SECTION}px;"
            "border-radius:6px; padding:4px 12px;"
        )
        gt_row.addWidget(gt_title)
        gt_row.addWidget(self._gt_lbl)
        layout.addLayout(gt_row)

        for sp in (self._pg, self._pc, self._cg, self._cc, self._qg, self._qc, self._mo, self._mc):
            sp.installEventFilter(self)
            sp.valueChanged.connect(self._update_totals)

    def _spins(self) -> Tuple[QSpinBox, ...]:
        return (self._pg, self._pc, self._cg, self._cc, self._qg, self._qc, self._mo, self._mc)

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = read_only
        cursor = Qt.CursorShape.ForbiddenCursor if read_only else Qt.CursorShape.IBeamCursor
        focus_policy = Qt.FocusPolicy.NoFocus if read_only else Qt.FocusPolicy.StrongFocus
        for sp in self._spins():
            sp.setReadOnly(read_only)
            sp.setFocusPolicy(focus_policy)
            sp.setCursor(cursor)
            sp.setStyleSheet(_spin_style(read_only))

    def set_counts(
        self,
        primary_full: int,
        primary_lunch: int,
        collegial_full: int,
        collegial_lunch: int,
        qualifying_full: int,
        qualifying_lunch: int,
        monitors_full: int,
        monitors_lunch: int,
    ) -> None:
        values = (
            (self._pg, primary_full),
            (self._pc, primary_lunch),
            (self._cg, collegial_full),
            (self._cc, collegial_lunch),
            (self._qg, qualifying_full),
            (self._qc, qualifying_lunch),
            (self._mo, monitors_full),
            (self._mc, monitors_lunch),
        )
        for spin, value in values:
            try:
                safe_value = max(0, int(value))
            except (TypeError, ValueError):
                safe_value = 0
            spin.setValue(safe_value)
        self._update_totals()

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if self._read_only and obj in self._spins() and event.type() in (
            QEvent.Type.KeyPress,
            QEvent.Type.Wheel,
        ):
            return True
        return super().eventFilter(obj, event)

    def _update_totals(self) -> None:
        contact = self.to_contact("")
        self._pt_lbl.setText(str(contact.primary_total))
        self._ct_lbl.setText(str(contact.collegial_total))
        self._qt_lbl.setText(str(contact.qualifying_total))
        self._mt_lbl.setText(str(contact.monitors_total))
        self._gt_lbl.setText(str(contact.grand_total))

    # Public API
    def load(self, contact: Optional[DailyContact]) -> None:
        """Populate from a DailyContact (or clear if None)."""
        if contact is None:
            for sp in (self._pg, self._pc, self._cg, self._cc, self._qg, self._qc, self._mo, self._mc):
                sp.setValue(0)
        else:
            self._pg.setValue(contact.primary_granted)
            self._pc.setValue(contact.primary_complement)
            self._cg.setValue(contact.collegial_granted + contact.collegial_paying)
            self._cc.setValue(contact.collegial_complement)
            self._qg.setValue(contact.qualifying_granted + contact.qualifying_paying)
            self._qc.setValue(contact.qualifying_complement)
            self._mo.setValue(contact.monitors)
            self._mc.setValue(contact.monitors_complement)
        self._update_totals()

    def to_contact(self, date: str) -> DailyContact:
        return DailyContact(
            date=date,
            meal_type=self._meal_key,
            primary_granted=self._pg.value(),
            primary_complement=self._pc.value(),
            collegial_granted=self._cg.value(),
            collegial_paying=0,
            collegial_complement=self._cc.value(),
            qualifying_granted=self._qg.value(),
            qualifying_paying=0,
            qualifying_complement=self._qc.value(),
            monitors=self._mo.value(),
            monitors_complement=self._mc.value(),
        )


def _counts_to_contacts(date_str: str, counts: Dict[str, Dict[str, int]]) -> List[DailyContact]:
    """Same per-meal mapping DailyContactScreen._apply_generated_counts uses
    to fill the live cards, but building DailyContact rows to save directly
    instead — used by batch data generation, which has no open cards to
    write into."""
    primary = counts.get("primary", {})
    collegial = counts.get("collegial", {})
    qualifying = counts.get("qualifying", {})
    monitors = counts.get("monitors", {})
    # Only the day's own meals are saved — a normal day must not get Ramadan
    # rows, and a Ramadan day must not get normal ones.
    active = {key for key, _label in _meals_for_document(date_str)}
    rows = [
        DailyContact(
            date=date_str, meal_type=MEAL_FTOUR,
            primary_granted=primary.get("full", 0),
            collegial_granted=collegial.get("full", 0),
            qualifying_granted=qualifying.get("full", 0),
            monitors=monitors.get("full", 0),
        ),
        DailyContact(
            date=date_str, meal_type=MEAL_GHADA,
            primary_granted=primary.get("full", 0), primary_complement=primary.get("lunch", 0),
            collegial_granted=collegial.get("full", 0), collegial_complement=collegial.get("lunch", 0),
            qualifying_granted=qualifying.get("full", 0), qualifying_complement=qualifying.get("lunch", 0),
            monitors=monitors.get("full", 0), monitors_complement=monitors.get("lunch", 0),
        ),
        DailyContact(
            date=date_str, meal_type=MEAL_ASHA,
            primary_granted=primary.get("full", 0),
            collegial_granted=collegial.get("full", 0),
            qualifying_granted=qualifying.get("full", 0),
            monitors=monitors.get("full", 0),
        ),
        # Ramadan. إفطار carries the وجبة غذاء students too: during Ramadan
        # there is no غداء, and إفطار is the single meal those students get.
        DailyContact(
            date=date_str, meal_type=MEAL_IFTAR,
            primary_granted=primary.get("full", 0), primary_complement=primary.get("lunch", 0),
            collegial_granted=collegial.get("full", 0), collegial_complement=collegial.get("lunch", 0),
            qualifying_granted=qualifying.get("full", 0), qualifying_complement=qualifying.get("lunch", 0),
            monitors=monitors.get("full", 0), monitors_complement=monitors.get("lunch", 0),
        ),
        DailyContact(
            date=date_str, meal_type=MEAL_SHOUR,
            primary_granted=primary.get("full", 0),
            collegial_granted=collegial.get("full", 0),
            qualifying_granted=qualifying.get("full", 0),
            monitors=monitors.get("full", 0),
        ),
    ]
    return [row for row in rows if row.meal_type in active]


def _unflatten_counts(roster: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    counts = empty_counts()
    for key, value in roster.items():
        category, grant_kind = key.rsplit("_", 1)
        counts[category][grant_kind] = value
    return counts


def generate_and_save_contact_for_date(
    date_str: str, active_roster: Dict[str, int], history: List[DailyContact],
) -> bool:
    """Auto-fill AND SAVE real contact numbers for one date using the same
    estimator as "توليد تلقائي" — shared by the batch-generate button and
    ui/work_pipeline_screen.py. Returns False (no-op) for a real holiday
    or a date that already has saved data, never overwriting it."""
    if is_holiday(date_str) or get_day_contacts(date_str):
        return False
    target_date = datetime.date.fromisoformat(date_str)
    result = estimate_attendance(active_roster, history, target_date, MEAL_GHADA)
    for contact in _counts_to_contacts(date_str, _unflatten_counts(result.counts)):
        save_daily_contact(contact)
    return True


def build_contact_pdf_page(
    painter, page_w: float, page_h: float, date_str: str,
    holiday_labels: Dict[str, str], settings,
) -> str:
    """Draw one date's page for a combined batch PDF — real data, a
    holiday placeholder, or a no-data placeholder — and assign/record a
    real رقم الوثيقة for a date that never had one. Used by
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
    document_number = get_document_number_for_date(date_str)
    if document_number is None:
        document_number = get_next_daily_contact_document_number()
        record_daily_contact_document(date_str, document_number, "batch_export", contacts)
    _draw_daily_contact_pdf_page(
        painter, page_w, page_h, date_str, contacts,
        document_number=str(document_number), place=settings.city if settings else "",
    )
    return "data"


# ── Main screen ───────────────────────────────────────────────────────────────

class DailyContactScreen(QWidget):
    """Full daily contact sheet screen."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._cards: Dict[str, _MealCard] = {}
        self._loaded_once = False
        self._last_auto_number = ""
        self._syncing_number = False
        self._auto_mode = False
        self._toast: QLabel | None = None
        self._build_ui()
        # Picking a date from the calendar must load THAT date. Without this
        # the numbers stayed on whatever day was loaded before, and an
        # export then produced a document stamped with the new date but
        # carrying the previous day's figures. Connected last, so it never
        # fires while the widgets are still being built.
        self._date_edit.dateChanged.connect(self._load_selected)

    def refresh(self) -> None:
        if not getattr(self, "_loaded_once", False):
            self._load_today()
            self._loaded_once = True
        else:
            self._load_selected()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(18, 8, 18, 12)
        inner.setSpacing(12)

        inner.addLayout(self._build_header())
        inner.addWidget(self._build_date_bar())
        inner.addWidget(self._build_estimate_note())
        inner.addLayout(self._build_cards_row())
        inner.addWidget(self._build_history())
        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(17); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color:{_INK};")
        sub = QLabel(_SUBTITLE)
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        col.addWidget(title)
        col.addWidget(sub)
        return col

    def _build_date_bar(self) -> QFrame:
        panel = QFrame()
        panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        panel.setStyleSheet(f"""
            QFrame {{
                background:transparent;
                border:none;
            }}
        """)
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        actions = self._toolbar_group(_LBL_ACTIONS)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        save_btn = self._btn(_BTN_SAVE, COLOR_SUCCESS, icon=_BTN_SAVE_ICON)
        save_btn.clicked.connect(self._on_save)
        export_btn = self._btn(_BTN_EXPORT_DOC, _INK, icon=_BTN_EXPORT_DOC_ICON)
        export_btn.clicked.connect(self._on_export)
        actions_row.addWidget(save_btn)
        actions_row.addWidget(export_btn)
        actions.layout().addLayout(actions_row)

        document = self._toolbar_group(_LBL_DOCUMENT)
        fields = QHBoxLayout()
        fields.setSpacing(4)

        self._date_edit = DateInput()
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setMinimumHeight(36)
        self._date_edit.setFixedWidth(132)
        self._date_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            f"padding:4px 10px; font-size:{FONT_BODY}px;"
        )

        self._number_edit = QLineEdit()
        self._number_edit.setValidator(QIntValidator(1, 999999, self))
        self._number_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._number_edit.setMinimumHeight(36)
        self._number_edit.setMaximumWidth(98)
        self._number_edit.setPlaceholderText("....")
        self._number_edit.setToolTip(_NUMBER_HINT)
        self._number_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            f"padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFixedHeight(28)
        separator.setStyleSheet(f"color:{_PANEL_BORDER};")

        # → / ← step the date field itself instead of being 2 more full
        # buttons — reads as one control (like a calendar's own stepper),
        # not 2 more decisions. اليوم stays a small standalone link since
        # it's a jump, not a step, right after the stepper.
        prev_step_btn = self._step_btn("→", _BTN_PREV, self._go_prev)
        next_step_btn = self._step_btn("←", _BTN_NEXT, self._go_next)
        today_btn = self._btn_outline(_BTN_TODAY, compact=True, accent=True)
        today_btn.setMinimumWidth(56)
        today_btn.clicked.connect(self._load_today)

        fields.addWidget(QLabel(_LBL_DATE, styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))
        fields.addWidget(prev_step_btn)
        fields.addWidget(self._date_edit)
        fields.addWidget(next_step_btn)
        fields.addWidget(today_btn)
        fields.addWidget(separator)
        fields.addWidget(QLabel(_LBL_NUMBER, styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))
        fields.addWidget(self._number_edit)
        document.layout().addLayout(fields)

        # تعبئة الأرقام: one 3-way selector (يدوي / تلقائي / نسخ الأمس) plus
        # one action button that only makes sense — and only shows — in
        # تلقائي mode. Used to be 2 separate always-visible buttons
        # (تحميل اليوم, نسخ من اليوم السابق) plus a 2-state switch, all
        # sitting next to 3 more navigation buttons — 6 controls to scan
        # before doing anything. يدوي mode now shows *zero* buttons here,
        # matching that there's genuinely nothing to click in that mode.
        navigation = self._toolbar_group(_LBL_FILL_MODE)
        fill_row = QHBoxLayout()
        fill_row.setSpacing(6)
        self._mode_toggle = _FillModeSelector()
        self._load_btn = self._btn(_BTN_LOAD, COLOR_ACCENT, compact=True)
        self._load_btn.setMinimumWidth(76)
        self._load_btn.setVisible(False)
        fill_row.addWidget(self._mode_toggle)
        fill_row.addWidget(self._load_btn)
        navigation.layout().addLayout(fill_row)

        self._load_btn.clicked.connect(self._on_load_today_clicked)
        self._mode_toggle.modeChanged.connect(self._on_mode_changed)
        self._mode_toggle.modeChanged.connect(self._load_btn.setVisible)
        self._mode_toggle.copyRequested.connect(self._on_copy_previous_clicked)

        # RTL reading order: pick the day first (rightmost), then its
        # document info, then act on it (leftmost) — the natural right-to-
        # left task flow, not just mirrored left-to-right box placement.
        row.addWidget(navigation, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(document, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(actions, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        self._sync_document_number(force=True)
        self._date_edit.dateChanged.connect(self._sync_document_number)
        self._date_edit.dateChanged.connect(self._apply_meal_visibility)
        self._number_edit.textChanged.connect(self._remember_document_number)
        return panel

    def _build_estimate_note(self) -> QLabel:
        label = QLabel("")
        label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color:{_INK}; background:#fbf6e3; border:1px solid #e6d68a;"
            f"border-radius:10px; padding:6px 12px; font-size:{FONT_LABEL}px;"
        )
        label.setVisible(False)
        self._estimate_note = label
        return label

    def _set_estimate_note(self, result: EstimateResult | None) -> None:
        if result is None:
            self._estimate_note.setVisible(False)
            return
        if result.reason == "insufficient_history":
            text = _ESTIMATE_NOTE_LOW.format(records=result.records_used)
        else:
            text = _ESTIMATE_NOTE_ESTIMATED.format(
                records=result.records_used,
                confidence=_CONFIDENCE_LABELS[result.confidence],
            )
        self._estimate_note.setText(text)
        self._estimate_note.setVisible(True)

    def _toolbar_group(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background:#fbfbf7;
                border:1px solid {_PANEL_BORDER};
                border-radius:14px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(5)
        label = QLabel(title)
        label.setStyleSheet(f"color:{_INK}; font-weight:bold; font-size:{FONT_LABEL}px; border:none; background:transparent;")
        layout.addWidget(label)
        return frame

    def _btn(self, label: str, color: str, *, compact: bool = False, icon: str | None = None) -> QPushButton:
        return IconButton(
            label, icon=icon, bg=color, text_color="white",
            border_radius=12, padding_h=(10 if compact else 14),
            font_size=13, bold=False, min_height=36,
        )

    def _btn_outline(
        self, label: str, *, compact: bool = False, icon: str | None = None, accent: bool = False,
    ) -> QPushButton:
        """Light, bordered button for an action that shouldn't visually
        compete with a solid-fill primary action nearby — used for اليوم,
        the one still-standalone control worth calling out as a jump
        rather than a step (`accent=True` tints its border/text)."""
        color = COLOR_ACCENT if accent else _INK
        return IconButton(
            label, icon=icon, bg="white", text_color=color,
            border=color, hover_bg=COLOR_PANEL_ALT,
            border_radius=10, padding_h=(10 if compact else 14),
            font_size=13, bold=False, min_height=36,
        )

    def _step_btn(self, glyph: str, tooltip: str, on_click) -> QPushButton:
        """Tiny icon-only ← → button meant to sit directly against the
        date field, read as part of that one control rather than as its
        own separate decision — the well-worn date-stepper pattern, not a
        standalone action needing its own label (see IconButton for that
        default; a tooltip keeps the action discoverable without one)."""
        btn = QPushButton(glyph)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setFixedSize(32, 32)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:white; color:{_INK}; border:1px solid {_PANEL_BORDER};
                border-radius:8px; font-size:14px; font-weight:bold;
            }}
            QPushButton:hover {{ background:{COLOR_PANEL_ALT}; }}
        """)
        btn.clicked.connect(on_click)
        return btn

    def _build_cards_row(self) -> QGridLayout:
        # Read once for all five cards: it queries the database.
        visible = tuple(visible_cycles())
        row = QGridLayout()
        row.setSpacing(12)
        row.setHorizontalSpacing(12)
        row.setVerticalSpacing(12)
        # Plain AlignRight gets reinterpreted as leading/trailing under RTL
        # layoutDirection and lands physically LEFT — AlignAbsolute forces
        # true visual right (same fix ui_design.md documents for QPainter
        # text, it turns out it also applies to layout alignment flags).
        row.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignTop
        )
        for index, (meal_key, meal_label) in enumerate(_CARD_MEAL_ORDER):
            card = _MealCard(meal_key, meal_label, _MEAL_COLORS[meal_key],
                             visible)
            self._cards[meal_key] = card
            row.addWidget(
                card,
                0,
                index,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            )
        row.setColumnStretch(0, 0)
        row.setColumnStretch(1, 0)
        row.setColumnStretch(2, 0)
        return row

    def _build_history(self) -> QGroupBox:
        grp = QGroupBox("سجل الوثائق الأخيرة")
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                background:{_PANEL_BG};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:14px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)

        self._history_table = QTableWidget(0, len(_HDR_HISTORY))
        self._history_table.setHorizontalHeaderLabels(_HDR_HISTORY)
        self._history_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.verticalHeader().setDefaultSectionSize(32)
        self._history_table.horizontalHeader().setFixedHeight(32)
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(_HISTORY_COLUMN_WIDTHS):
            self._history_table.setColumnWidth(col, width)
        self._history_table.setMinimumHeight(206)
        self._history_table.setMaximumHeight(210)
        self._history_table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {_PANEL_BORDER}; border-radius:12px;
                background:white; alternate-background-color:{COLOR_PANEL_ALT};
                font-size:{FONT_LABEL}px;
            }}
            QHeaderView::section {{
                background:{COLOR_PANEL_ALT}; color:{_INK};
                padding:4px 8px; border:none;
                border-bottom:1px solid {_PANEL_BORDER};
                font-weight:bold; font-size:{FONT_LABEL}px;
            }}
            QTableWidget::item {{ padding:4px 8px; }}
        """)
        self._history_table.setAlternatingRowColors(True)
        # Double-click a history row → jump to that date
        self._history_table.doubleClicked.connect(self._on_history_click)
        layout.addWidget(self._history_table)
        return grp

    # ── Data helpers ────────────────────────────────────────────────────────

    def _selected_date_str(self) -> str:
        return self._date_edit.date().toString("yyyy-MM-dd")

    def _date_sequence_number(self) -> int:
        selected = self._date_edit.date()
        start_year = selected.year() if selected.month() >= 9 else selected.year() - 1
        school_year_start = QDate(start_year, 9, 1)
        return max(1, school_year_start.daysTo(selected) + 1)

    def _suggested_document_number(self) -> str:
        return str(get_next_daily_contact_document_number(1))

    def _saved_document_number(self) -> str | None:
        saved = get_daily_contact_document_number_draft(self._selected_date_str())
        return str(saved) if saved is not None else None

    def _set_document_number(self, value: str, *, auto: bool) -> None:
        self._syncing_number = True
        try:
            self._number_edit.setText(value)
        finally:
            self._syncing_number = False
        if auto:
            self._last_auto_number = value

    def _sync_document_number(self, *_: object, force: bool = False) -> None:
        current = self._number_edit.text().strip()
        if not force and current and current != self._last_auto_number:
            return
        suggested = self._saved_document_number() or self._suggested_document_number()
        self._set_document_number(suggested, auto=True)

    def _remember_document_number(self, text: str) -> None:
        if self._syncing_number:
            return
        text = text.strip()
        if not text:
            return
        try:
            number = int(text)
        except ValueError:
            return
        save_daily_contact_document_number_draft(self._selected_date_str(), number)

    def _document_number_text(self) -> str:
        return self._number_edit.text().strip() or self._saved_document_number() or self._suggested_document_number()

    def _document_number_int(self) -> int:
        try:
            return max(1, int(self._document_number_text()))
        except ValueError:
            return int(self._suggested_document_number())

    def _advance_document_number(self, used_number: int) -> None:
        next_number = get_next_daily_contact_document_number(used_number + 1)
        next_number_text = str(next_number)
        self._set_document_number(next_number_text, auto=True)
        save_daily_contact_document_number_draft(self._selected_date_str(), next_number)

    def _active_meals(self) -> List[str]:
        """The meal types the selected date actually serves — Ramadan's two
        or the normal three, decided centrally in core.ramadan so every
        screen and document agrees."""
        return meals_for_date(
            self._selected_date_str(), get_school_settings(), get_ramadan_overrides())

    def _apply_meal_visibility(self) -> None:
        """Show only the cards for the selected date's meals."""
        active = set(self._active_meals())
        for meal_key, card in self._cards.items():
            card.setVisible(meal_key in active)

    def _current_contacts(self) -> List[DailyContact]:
        """Only the day's own meals are saved — a normal day must not write
        empty Ramadan rows, and a Ramadan day must not write normal ones."""
        date_str = self._selected_date_str()
        active = set(self._active_meals())
        return [card.to_contact(date_str)
                for meal_key, card in self._cards.items() if meal_key in active]

    def _on_mode_changed(self, auto: bool) -> None:
        self._auto_mode = auto
        for card in self._cards.values():
            card.set_read_only(auto)
        if not auto:
            self._set_estimate_note(None)
        self._show_toast(_TOAST_AUTO if auto else _TOAST_MANUAL)

    def _on_load_today_clicked(self) -> None:
        if not self._auto_mode:
            return
        self._generate_today_counts()

    def _on_copy_previous_clicked(self) -> None:
        """Copy the most recent earlier day's saved counts into the form —
        most days barely change from one to the next, so this is usually
        faster than either typing or the auto-estimate."""
        previous = get_last_contacts_before(self._selected_date_str())
        if not previous:
            self._show_toast(_TOAST_COPY_NONE)
            return

        if self._auto_mode:
            self._mode_toggle.set_auto(False)

        contacts = {c.meal_type: c for c in previous}
        for meal_key, card in self._cards.items():
            card.load(contacts.get(meal_key))
        self._set_estimate_note(None)
        self._show_toast(_TOAST_COPY_OK.format(date=_format_doc_date(previous[0].date)))

    def _generate_today_counts(self) -> None:
        students = get_all_students()
        if not students:
            self._apply_generated_counts(empty_counts())
            self._set_estimate_note(None)
            self._show_toast(_TOAST_NO_STUDENTS)
            return

        active_roster = self._flatten_counts(count_students(students))
        if sum(active_roster.values()) == 0:
            self._apply_generated_counts(empty_counts())
            self._set_estimate_note(None)
            self._show_toast(_TOAST_NO_CLASSIFIED_STUDENTS)
            return

        target_date = self._date_edit.date().toPython()
        history = get_recent_contacts(limit=_ESTIMATE_HISTORY_LIMIT)

        # Same-weekday, same-meal history differs by meal (e.g. ghada carries
        # the وجبة غذاء attendance pattern; ftour/asha never do), but a single
        # generate action should still produce one set of numbers for the day
        # — matching the previous behavior of one roll applied to all 3 cards.
        result = estimate_attendance(active_roster, history, target_date, MEAL_GHADA)

        self._apply_generated_counts(self._unflatten_counts(result.counts))
        self._set_estimate_note(result)

    def _flatten_counts(self, counts: Dict[str, Dict[str, int]]) -> Dict[str, int]:
        """`{category: {grant_kind: count}}` -> `{category_grant_kind: count}`
        — the flat shape `estimate_attendance` scales its historical rates by."""
        return {
            f"{category}_{grant_kind}": count
            for category, grants in counts.items()
            for grant_kind, count in grants.items()
        }

    def _unflatten_counts(self, roster: Dict[str, int]) -> Dict[str, Dict[str, int]]:
        counts = empty_counts()
        for key, value in roster.items():
            category, grant_kind = key.rsplit("_", 1)
            counts[category][grant_kind] = value
        return counts

    def _apply_generated_counts(self, counts: Dict[str, Dict[str, int]]) -> None:
        primary = counts.get("primary", {})
        collegial = counts.get("collegial", {})
        qualifying = counts.get("qualifying", {})
        monitors = counts.get("monitors", {})

        self._cards[MEAL_FTOUR].set_counts(
            primary.get("full", 0), 0,
            collegial.get("full", 0), 0,
            qualifying.get("full", 0), 0,
            monitors.get("full", 0), 0,
        )
        self._cards[MEAL_GHADA].set_counts(
            primary.get("full", 0), primary.get("lunch", 0),
            collegial.get("full", 0), collegial.get("lunch", 0),
            qualifying.get("full", 0), qualifying.get("lunch", 0),
            monitors.get("full", 0), monitors.get("lunch", 0),
        )
        self._cards[MEAL_ASHA].set_counts(
            primary.get("full", 0), 0,
            collegial.get("full", 0), 0,
            qualifying.get("full", 0), 0,
            monitors.get("full", 0), 0,
        )
        # Ramadan cards — hidden on a normal day, but filled the same way so
        # "تلقائي" produces real numbers on a Ramadan day too.
        self._cards[MEAL_IFTAR].set_counts(
            primary.get("full", 0), primary.get("lunch", 0),
            collegial.get("full", 0), collegial.get("lunch", 0),
            qualifying.get("full", 0), qualifying.get("lunch", 0),
            monitors.get("full", 0), monitors.get("lunch", 0),
        )
        self._cards[MEAL_SHOUR].set_counts(
            primary.get("full", 0), 0,
            collegial.get("full", 0), 0,
            qualifying.get("full", 0), 0,
            monitors.get("full", 0), 0,
        )

    def _show_toast(self, message: str) -> None:
        parent = self.window() or self
        if self._toast is not None:
            self._toast.deleteLater()
        toast = QLabel(message, parent)
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setStyleSheet(
            "background:#323232; color:white; border-radius:8px;"
            f"padding:10px 20px; font-size:{FONT_BODY}px;"
        )
        toast.adjustSize()
        x = max(12, (parent.width() - toast.width()) // 2)
        y = max(12, parent.height() - toast.height() - 32)
        toast.move(x, y)
        toast.show()
        toast.raise_()
        self._toast = toast

        def clear_toast() -> None:
            if self._toast is toast:
                self._toast = None
            toast.deleteLater()

        QTimer.singleShot(3000, clear_toast)

    def _default_docx_name(self) -> str:
        return f"{_DOCX_DEFAULT_NAME}_{self._selected_date_str()}.docx"

    def _default_pdf_name(self) -> str:
        return f"{_PDF_DEFAULT_NAME}_{self._selected_date_str()}.pdf"

    def _load_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self._load_selected()

    def _go_prev(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self._load_selected()

    def _go_next(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self._load_selected()

    def _load_selected(self) -> None:
        """Load all 3 meal rows for the selected date into the cards."""
        date_str = self._selected_date_str()
        contacts = {c.meal_type: c for c in get_day_contacts(date_str)}
        for meal_key, card in self._cards.items():
            card.load(contacts.get(meal_key))
        self._refresh_history()

    def _refresh_history(self) -> None:
        recent = get_recent_daily_contact_documents(60)
        self._history_table.setRowCount(0)
        for entry in recent:
            r = self._history_table.rowCount()
            self._history_table.insertRow(r)
            self._history_table.setRowHeight(r, 32)
            values = [
                str(entry.document_number),
                entry.date,
                _ACTION_LABELS.get(entry.action, entry.action),
                str(entry.ftour_total),
                str(entry.ghada_total),
                str(entry.asha_total),
                str(entry.grand_total),
                entry.created_at,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                self._history_table.setItem(r, col, item)

    def _on_history_click(self) -> None:
        """Jump to the date of the double-clicked history row."""
        row = self._history_table.currentRow()
        if row < 0:
            return
        date_str = self._history_table.item(row, _HISTORY_DATE_COLUMN).text()
        self._date_edit.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))
        self._load_selected()

    # ── Save ────────────────────────────────────────────────────────────────

    def _save_current_contacts(self) -> List[DailyContact]:
        date_str = self._selected_date_str()
        contacts = self._current_contacts()
        for contact in contacts:
            save_daily_contact(contact)
        return contacts

    def _on_export(self) -> None:
        fmt = get_document_export_format()
        if fmt == EXPORT_FORMAT_ASK:
            fmt = ask_export_format(self)
            if fmt is None:
                return
        is_pdf = fmt == EXPORT_FORMAT_PDF

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            _PDF_DIALOG_TITLE if is_pdf else _DOCX_DIALOG_TITLE,
            self._default_pdf_name() if is_pdf else self._default_docx_name(),
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
            date_str = self._selected_date_str()
            contacts = self._current_contacts()
            document_number = self._document_number_int()
            if is_pdf:
                _write_daily_contact_pdf(
                    path,
                    date_str,
                    contacts,
                    document_number=str(document_number),
                    place=settings.city if settings else "",
                )
            else:
                _write_daily_contact_docx(
                    path,
                    date_str,
                    contacts,
                    document_number=str(document_number),
                    place=settings.city if settings else "",
                    academy=settings.aref if settings else "",
                    province=settings.direction_provinciale if settings else "",
                    school_name=settings.school_name if settings else "",
                    school_year=settings.school_year if settings else "",
                )
            for contact in contacts:
                save_daily_contact(contact)
            record_daily_contact_document(date_str, document_number, "print", contacts, str(path))
            self._advance_document_number(document_number)
            self._refresh_history()
            QMessageBox.information(self, "تم", _PDF_SAVED_OK if is_pdf else _DOCX_SAVED_OK)
        except Exception as exc:
            error_prefix = _PDF_SAVE_ERROR if is_pdf else _DOCX_SAVE_ERROR
            QMessageBox.critical(self, "خطأ", f"{error_prefix}\n{exc}")

    def _on_save(self) -> None:
        date_str = self._selected_date_str()
        try:
            document_number = self._document_number_int()
            contacts = self._save_current_contacts()
            record_daily_contact_document(date_str, document_number, "save", contacts)
            self._advance_document_number(document_number)
            self._refresh_history()
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")
