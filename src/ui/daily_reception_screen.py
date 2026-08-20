"""
src/ui/daily_reception_screen.py
Daily reception record (محضر تسليم الخدمة اليومي) — confirms a day's
delivered meals were received and accepted, signed by STEWARD/HEADMASTER/
CONTRACTOR. Quantities default from that date's ورقة الاتصال totals but
are their own editable, saved snapshot — see core.models.DailyReceptionRecord.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextOption,
)
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_SUCCESS, COLOR_SURFACE,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    EXPORT_FORMAT_PDF,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
    FONT_BODY, FONT_LABEL, FONT_SECTION,
)
from core.models import DailyReceptionRecord, SchoolSettings
from data.database import (
    get_daily_reception_record, get_day_contacts, get_school_settings,
    save_daily_reception_record,
)
from ui.batch_export import draw_placeholder_pdf_page
from ui.daily_contact_screen import (
    _fill_contact_header_xml, _normalize_template_name, _set_cell_text,
    _set_docx_text, _template_dirs, _WORD_NS, _W_NS, _XML_SPACE,
)
from ui.document_header import (
    ask_export_format, draw_official_pdf_footer, draw_official_pdf_header,
    register_docx_namespaces,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "المحضر اليومي لتسلم الخدمة"
_TITLE_FR       = "PROCES VERBAL DE RECEPTION JOURNALIER"
_SUBTITLE       = "تأكيد استلام الوجبات المسلَّمة من طرف الشركة القائمة"
_BTN_PREV       = "اليوم السابق"
_BTN_PREV_ICON  = "→"
_BTN_NEXT       = "اليوم التالي"
_BTN_NEXT_ICON  = "←"
_BTN_TODAY      = "اليوم"
_BTN_RECOMPUTE      = "إعادة الحساب من ورقة الاتصال"
_BTN_RECOMPUTE_ICON = "🔄"
_LBL_DATE       = "التاريخ:"
_LBL_QUANTITIES = "الكميات المسلَّمة"
_LBL_NOTES      = "ملاحظات"
_NOTES_HINT     = "أدخل ملاحظاتك هنا..."
_BTN_SAVE       = "حفظ المحضر"
_BTN_SAVE_ICON  = "💾"
_BTN_EXPORT      = "تصدير"
_BTN_EXPORT_ICON = "📄"
_SAVED_OK       = "تم حفظ محضر التسليم بنجاح."
_PDF_DIALOG_TITLE = "تصدير محضر تسليم الخدمة اليومي"
_PDF_DEFAULT_NAME = "محضر_تسليم_الخدمة_اليومي"
_DOCX_FILTER    = "Word (*.docx)"
_PDF_FILTER     = "PDF (*.pdf)"
_EXPORT_ERROR   = "تعذر تصدير المحضر:"
_TEMPLATE_MISSING = "تعذر العثور على نموذج المحضر اليومي لتسلم الخدمة."

_MEAL_ORDER = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]

_TEMPLATE_FILE = "المحضر اليومي لتسلم الخدمة.docx"
# Exact field names as they appear in the real template's MERGEFIELD codes
# — the double underscore and the missing space before الغذاء are typos in
# the template itself, kept verbatim since these are literal match strings.
_MERGEFIELD_DATE   = "date"
_MERGEFIELD_FTOUR  = "عدد_المستفيدين__الفطور"
_MERGEFIELD_GHADA  = "عدد_المستفيدينالغذاء"

# The PDF is hand-drawn (not filled from the .docx template), but rebuilt
# to mirror the template's own real layout — including the parts of it
# that are in French, since the template itself is a bilingual FR/AR
# ministry document, not an Arabic-only one.
_SIGNER_LABEL_FR   = "Nous soussignons :"
_SIGNER_ROLES_FR   = ["CHEF DETABLISSEMENT", "ECONOME DE LYCEE"]
_ITEMS_COLUMNS_FR  = ["N°Article", "Désignation des Articles", "Unité", "Quantité"]
_MEAL_DESIGNATION_FR = {
    MEAL_FTOUR: "Le petit-déjeuner",
    MEAL_GHADA: "Le déjeuner",
    MEAL_ASHA:  "Le dîner",
}
_UNIT_FR = "Unité"
# Template order is Directeur, then gestionnaire (STEWARD), then
# prestataire (CONTRACTOR) — draw_official_pdf_footer places roles[0]
# first/rightmost, same convention every other table on this page uses,
# so listing them in that same template order puts Directeur first here too.
_FOOTER_ROLES_FR = ["Le Directeur", "Le gestionnaire", "Le prestataire de service"]


def _quantities_from_contacts(date_str: str) -> Dict[str, int]:
    """Per-meal totals from that date's ورقة الاتصال — the default a fresh
    reception record starts from."""
    contacts = {c.meal_type: c for c in get_day_contacts(date_str)}
    return {
        meal_key: (contacts[meal_key].grand_total if meal_key in contacts else 0)
        for meal_key, _ in _MEAL_ORDER
    }


def _reception_date_format(date_str: str) -> str:
    """The real template's own dates (e.g. "01/02/2026") read day/month/
    year — unlike the ISO "YYYY-MM-DD" this app stores, so a plain
    dash-to-slash swap would print the year first instead of last."""
    year, month, day = date_str.split("-")
    return f"{day}/{month}/{year}"


def _record_for_date(date_str: str) -> DailyReceptionRecord:
    """The DailyReceptionRecord for a date, independent of any live
    screen: the saved record if one exists, otherwise quantities freshly
    computed from that date's ورقة الاتصال. Used by batch export, which
    has no open screen to read live widget state from."""
    record = get_daily_reception_record(date_str)
    if record is not None:
        return record
    quantities = _quantities_from_contacts(date_str)
    return DailyReceptionRecord(
        date=date_str,
        ftour_qty=quantities[MEAL_FTOUR],
        ghada_qty=quantities[MEAL_GHADA],
        asha_qty=quantities[MEAL_ASHA],
    )


# ── PDF export — hand-drawn, matching the real template's field order ──────

def _draw_reception_pdf_text(
    painter: QPainter, rect: QRectF, text: str, *,
    size: int, color: str, bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
    direction: Qt.LayoutDirection = Qt.LayoutDirection.RightToLeft,
) -> None:
    font = QFont("Segoe UI")
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    option = QTextOption()
    option.setTextDirection(direction)
    option.setAlignment(align)
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    painter.drawText(rect, text, option)


def _draw_reception_pdf_cell(
    painter: QPainter, rect: QRectF, *,
    background: str, border: str, text: str, text_color: str,
    size: int, bold: bool = False,
    direction: Qt.LayoutDirection = Qt.LayoutDirection.RightToLeft,
) -> None:
    painter.setPen(QPen(QColor(border), 1))
    painter.setBrush(QColor(background))
    painter.drawRect(rect)
    _draw_reception_pdf_text(
        painter, rect.adjusted(4, 2, -4, -2), text,
        size=size, color=text_color, bold=bold, direction=direction,
    )


def _draw_reception_signer_table(
    painter: QPainter, *, top: float, right: float, content_w: float,
) -> float:
    """The template's "Nous soussignons :" name/role table — blank cells
    for the headmaster and steward to write their names in by hand, same
    as the real template. Returns the Y position after the table."""
    ltr = Qt.LayoutDirection.LeftToRight
    y = top
    _draw_reception_pdf_text(
        painter, QRectF(right - content_w, y, content_w, 20), _SIGNER_LABEL_FR,
        size=11, color=COLOR_TEXT_PRIMARY, direction=ltr,
    )
    y += 24

    columns = ["NOM ET PRENOM", "FONCTION"]
    col_widths = [content_w * 0.55, content_w * 0.45]
    header_h = 26.0
    row_h = 28.0

    current_right = right
    for col_label, col_w in zip(columns, col_widths):
        rect = QRectF(current_right - col_w, y, col_w, header_h)
        _draw_reception_pdf_cell(
            painter, rect, background="white", border="#000000",
            text=col_label, text_color="#000000", size=9, bold=True, direction=ltr,
        )
        current_right = rect.left()

    row_y = y + header_h
    for role in _SIGNER_ROLES_FR:
        current_right = right
        for index, (value, col_w) in enumerate(zip(["", role], col_widths)):
            rect = QRectF(current_right - col_w, row_y, col_w, row_h)
            _draw_reception_pdf_cell(
                painter, rect, background="white", border="#000000",
                text=value, text_color="#000000", size=9, direction=ltr,
            )
            current_right = rect.left()
        row_y += row_h

    return row_y + 14


def _draw_reception_pdf_page(
    painter: QPainter, page_w: float, page_h: float,
    settings: Optional[SchoolSettings], date_str: str, record: DailyReceptionRecord,
) -> None:
    """Draw one reception record onto an already-open page, mirroring
    templets/المحضر اليومي لتسلم الخدمة.docx's own real layout: bilingual
    title, signer-identification table, the legal attestation paragraph,
    a 4-column meal/quantity table, remarks, closing declaration, then
    HEADMASTER/STEWARD/CONTRACTOR signatures. Shared by
    _write_reception_pdf (standalone file) and build_reception_pdf_page
    (يوم العمل's combined batch PDF)."""
    s = settings
    company = ((s.company_name if s else "") or (s.supplier_name if s else "")) or "—"
    school_fr = ((s.school_name_fr if s else "") or (s.school_name if s else "")) or "—"
    contract_number = ((s.contract_number if s else "") or "").strip() or "—"
    contract_object = ((s.contract_object if s else "") or "").strip() or (
        "PRESTATION DE RESTAURATION AU PROFIT DE L’INTERNAT DU"
    )
    place = ((s.city if s else "") or "").strip() or "—"
    display_date = _reception_date_format(date_str)

    margin = 38.0
    content_w = page_w - (margin * 2)
    right = margin + content_w

    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=margin, top=18.0,
        settings=settings, title=_TITLE,
    )

    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 20), _TITLE_FR,
        size=12, color=COLOR_TEXT_SECONDARY, bold=True,
        direction=Qt.LayoutDirection.LeftToRight,
    )
    y += 26

    meta_lines = [f"بتاريخ : {display_date}", f"الشركة القائمة : {company}"]
    for line in meta_lines:
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 24), line,
            size=11, color=COLOR_TEXT_PRIMARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
        )
        y += 28
    y += 8

    legal_text = (
        f"Attestons que les prestations objet du marché N°{contract_number} "
        f"ayant pour objet : {contract_object} : {school_fr}.\n"
        f"Ont été réellement exécutées par la Sté : {company}, conformément "
        f"aux spécifications techniques exigées par le CPS, à hauteur des "
        f"quantités suivantes consommées le {display_date} :"
    )
    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 70), legal_text,
        size=9, color=COLOR_TEXT_PRIMARY,
        direction=Qt.LayoutDirection.LeftToRight,
    )
    y += 82

    y = _draw_reception_signer_table(painter, top=y, right=right, content_w=content_w)

    columns = _ITEMS_COLUMNS_FR
    col_widths = [content_w * 0.10, content_w * 0.45, content_w * 0.20, content_w * 0.25]
    header_h = 32.0
    row_h = 32.0
    table_h = header_h + (row_h * len(_MEAL_ORDER))
    ltr = Qt.LayoutDirection.LeftToRight

    current_right = right
    for col_label, col_w in zip(columns, col_widths):
        rect = QRectF(current_right - col_w, y, col_w, header_h)
        _draw_reception_pdf_cell(
            painter, rect, background="white", border="#000000",
            text=col_label, text_color="#000000", size=10, bold=True, direction=ltr,
        )
        current_right = rect.left()

    quantities = [record.ftour_qty, record.ghada_qty, record.asha_qty]
    row_y = y + header_h
    for row_number, ((meal_key, _), qty) in enumerate(zip(_MEAL_ORDER, quantities), start=1):
        values = [str(row_number), _MEAL_DESIGNATION_FR[meal_key], _UNIT_FR, str(qty)]
        current_right = right
        for index, (value, col_w) in enumerate(zip(values, col_widths)):
            rect = QRectF(current_right - col_w, row_y, col_w, row_h)
            _draw_reception_pdf_cell(
                painter, rect, background="white", border="#000000",
                text=value, text_color="#000000", size=10, bold=(index == 1), direction=ltr,
            )
            current_right = rect.left()
        row_y += row_h
    y += table_h + 16

    if record.remarks.strip():
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 34),
            f"ملاحظات: {record.remarks.strip()}",
            size=10, color=COLOR_TEXT_SECONDARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
        )
        y += 34

    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 20),
        f"FAIT A {place}. LE {display_date}",
        size=10, color=COLOR_TEXT_PRIMARY, bold=True,
        direction=Qt.LayoutDirection.LeftToRight,
    )

    footer_h = 90.0
    footer_y = page_h - margin - footer_h + 6
    draw_official_pdf_footer(
        painter, page_width=page_w, margin=margin, top=footer_y,
        settings=settings, roles=_FOOTER_ROLES_FR,
    )


def _write_reception_pdf(path: Path, settings, date_str: str, record: DailyReceptionRecord) -> None:
    """Render a single date's reception record as its own standalone PDF."""
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
        _draw_reception_pdf_page(painter, float(writer.width()), float(writer.height()), settings, date_str, record)
    finally:
        painter.end()


def build_reception_pdf_page(
    painter, page_w: float, page_h: float, date_str: str,
    holiday_labels: Dict[str, str], settings,
) -> str:
    """Draw one date's page for a combined batch PDF — real data, a
    holiday placeholder, or a no-data placeholder. Like رسالة الطلبية
    (and unlike absence/report), a "ready" day here saves a real record if
    none exists yet — a reception confirmation is meant to be a permanent
    signed snapshot of what was delivered, not a live recomputed view; a
    day already confirmed keeps its saved quantities exactly, even if
    ورقة الاتصال changes later. Used by ui/work_pipeline_screen.py's
    "generate everything" action. Returns "data"/"holiday"/"empty"."""
    if date_str in holiday_labels:
        label = holiday_labels[date_str] or "بدون سبب محدد"
        draw_placeholder_pdf_page(
            painter, page_w, page_h, f"{date_str} — يوم عطلة", f"📅 عطلة: {label}",
        )
        return "holiday"
    if not get_day_contacts(date_str):
        draw_placeholder_pdf_page(
            painter, page_w, page_h, f"{date_str} — لا توجد بيانات",
            "لم يتم تسجيل بيانات ورقة الاتصال لهذا اليوم بعد.",
        )
        return "empty"

    record = get_daily_reception_record(date_str)
    if record is None:
        quantities = _quantities_from_contacts(date_str)
        record = DailyReceptionRecord(
            date=date_str,
            ftour_qty=quantities[MEAL_FTOUR],
            ghada_qty=quantities[MEAL_GHADA],
            asha_qty=quantities[MEAL_ASHA],
        )
        save_daily_reception_record(record)
    _draw_reception_pdf_page(painter, page_w, page_h, settings, date_str, record)
    return "data"


# ── Word export — fills the real MERGEFIELD-based template ─────────────────

def _find_reception_template() -> Optional[Path]:
    for directory in _template_dirs():
        exact = directory / _TEMPLATE_FILE
        if exact.exists():
            return exact
        if not directory.exists():
            continue
        for candidate in directory.glob("*.docx"):
            if "المحضراليوميلتسلمالخدمة" in _normalize_template_name(candidate.stem):
                return candidate
    return None


def _set_mergefield_value(root: ET.Element, field_name: str, value: str) -> None:
    """Word MERGEFIELD codes cache their displayed text in a run sitting
    between the field's `separate` and `end` markers, inside the SAME
    paragraph as other plain-text runs — this template's closing line is
    literally one paragraph containing "FAIT A TAGLEFT. LE " (a static
    label, its own run) followed immediately by the `date` field. Reusing
    _set_docx_text's "grab the first <w:t> in the container" approach
    would silently overwrite that label instead of the date. This walks
    the paragraph's runs in order from the matching instrText, skips past
    `separate`, and only touches the one cached-value run that follows —
    every other run in the paragraph is left untouched. Every occurrence
    of a repeated field name (this template has `date` twice) gets
    updated, since this scans the whole document, not just the first
    match."""
    parent_map = {child: parent for parent in root.iter() for child in parent}
    for instr in root.iter(f"{{{_W_NS}}}instrText"):
        if not instr.text or field_name not in instr.text:
            continue
        run = parent_map.get(instr)
        paragraph = parent_map.get(run) if run is not None else None
        if paragraph is None:
            continue
        runs = paragraph.findall("w:r", _WORD_NS)
        if run not in runs:
            continue
        in_result = False
        for later_run in runs[runs.index(run) + 1:]:
            fld = later_run.find("w:fldChar", _WORD_NS)
            if fld is not None:
                fld_type = fld.get(f"{{{_W_NS}}}fldCharType")
                if fld_type == "separate":
                    in_result = True
                    continue
                if fld_type == "end":
                    break
            if in_result:
                text_node = later_run.find("w:t", _WORD_NS)
                if text_node is not None:
                    text_node.text = value
                    text_node.set(_XML_SPACE, "preserve")
                    break


def _set_empty_run_text(cell: ET.Element, value: str) -> None:
    """The dinner-quantity cell has one existing but TEXTLESS run that
    already carries the template's real 10pt sizing (w:sz=20 in its
    rPr). _set_docx_text's fallback for a text-less container creates a
    brand-new sibling run instead — one with no rPr at all, which Word
    then renders at its bigger default size. Reusing the existing run
    (just adding a <w:t> to it) keeps the same size as the breakfast/
    lunch cells instead."""
    run = cell.find(".//w:r", _WORD_NS)
    if run is None:
        _set_docx_text(cell, value)
        return
    text_node = run.find("w:t", _WORD_NS)
    if text_node is None:
        text_node = ET.SubElement(run, f"{{{_W_NS}}}t")
    text_node.text = value
    text_node.set(_XML_SPACE, "preserve")


def _set_paragraph_leading_static_text(paragraph: ET.Element, value: str) -> None:
    """Like _set_docx_text, but for a paragraph that ALSO contains a real
    MERGEFIELD later on (the closing "FAIT A TAGLEFT. LE [date]" line —
    the place name is a plain static run, the date right after it is a
    live field). Only touches runs BEFORE the first fldChar/instrText —
    stops there, so the field's own runs (and _set_mergefield_value's
    fill of them) are never disturbed."""
    for run in paragraph.findall("w:r", _WORD_NS):
        if run.find("w:fldChar", _WORD_NS) is not None or run.find("w:instrText", _WORD_NS) is not None:
            return
        text_node = run.find("w:t", _WORD_NS)
        if text_node is not None:
            text_node.text = value
            text_node.set(_XML_SPACE, "preserve")
            return


def _fill_reception_legal_paragraphs(root: ET.Element, settings: Optional[SchoolSettings]) -> None:
    """The template's French legal paragraphs (contract number, the
    school's own name, the contractor, the school year, the closing
    place name) are all plain fixed text in the template — not
    MERGEFIELDs — so they never change no matter what's configured in
    الإعدادات. Matches each by a stable substring and rewrites the whole
    line, the same approach _fill_contact_header_xml already uses for
    that screen's own template."""
    s = settings
    year = ((s.school_year if s else "") or "").strip() or "—"
    contract_number = ((s.contract_number if s else "") or "").strip() or "—"
    contract_object = ((s.contract_object if s else "") or "").strip() or (
        "PRESTATION DE RESTAURATION AU PROFIT DE L’INTERNAT DU"
    )
    school_fr = ((s.school_name_fr if s else "") or (s.school_name if s else "") or "").strip() or "—"
    company = ((s.company_name if s else "") or (s.supplier_name if s else "") or "").strip() or "—"
    place = ((s.city if s else "") or "").strip() or "—"

    for paragraph in root.findall(".//w:p", _WORD_NS):
        if paragraph.findall(".//w:p", _WORD_NS):
            continue
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS))
        if text.startswith("- السنة الدراسية"):
            _set_docx_text(paragraph, f"- السنة الدراسية:  {year}")
        elif text.startswith("Attestons que"):
            _set_docx_text(
                paragraph,
                f"Attestons que les prestations objet du marché N°{contract_number} "
                f"ayant pour objet : {contract_object} :",
            )
        elif "LYCEE QUALIFIANT" in text:
            _set_docx_text(paragraph, school_fr)
        elif text.startswith("Ont été réellement exécutées"):
            _set_docx_text(paragraph, f"Ont été réellement exécutées par la Sté : {company}.")
        elif text.startswith("FAIT A"):
            _set_paragraph_leading_static_text(paragraph, f"FAIT A {place}. LE ")


def _fill_reception_document_xml(root: ET.Element, date_str: str, record: DailyReceptionRecord, settings: Optional[SchoolSettings] = None) -> None:
    display_date = _reception_date_format(date_str)
    _set_mergefield_value(root, _MERGEFIELD_DATE, display_date)
    _set_mergefield_value(root, _MERGEFIELD_FTOUR, str(record.ftour_qty))
    _set_mergefield_value(root, _MERGEFIELD_GHADA, str(record.ghada_qty))
    _fill_reception_legal_paragraphs(root, settings)

    # The real template has 3 SEPARATE <w:tbl> elements — signer table,
    # items table, remarks table — not one table with extra rows. Picking
    # "the first table" (or assuming Remarques is a row inside the items
    # table) silently fills the wrong cell.
    for table in root.findall(".//w:tbl", _WORD_NS):
        rows = table.findall("w:tr", _WORD_NS)
        row_texts = ["".join(node.text or "" for node in row.findall(".//w:t", _WORD_NS)) for row in rows]

        for index, row_text in enumerate(row_texts):
            if "dîner" in row_text:
                # The dinner row's quantity cell has no MERGEFIELD at all
                # in the real template — it's the row's last (empty) cell.
                cells = rows[index].findall("w:tc", _WORD_NS)
                if cells:
                    _set_empty_run_text(cells[-1], str(record.asha_qty))
            elif "Remarques" in row_text and record.remarks.strip():
                # The blank cell for remarks is the table's NEXT row, not
                # part of this one.
                if index + 1 < len(rows):
                    next_cells = rows[index + 1].findall("w:tc", _WORD_NS)
                    if next_cells:
                        _set_docx_text(next_cells[0], record.remarks.strip())


def _write_reception_docx(path: Path, date_str: str, record: DailyReceptionRecord, settings: Optional[SchoolSettings] = None) -> None:
    """Fill the real templets/المحضر اليومي لتسلم الخدمة.docx template."""
    template_path = _find_reception_template()
    if template_path is None:
        raise FileNotFoundError(_TEMPLATE_MISSING)

    register_docx_namespaces()
    path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(template_path, "r") as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                root = ET.fromstring(data)
                _fill_reception_document_xml(root, date_str, record, settings)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            elif item.filename.startswith("word/header") and item.filename.endswith(".xml"):
                root = ET.fromstring(data)
                _fill_contact_header_xml(
                    root,
                    academy=settings.aref if settings else "",
                    province=settings.direction_provinciale if settings else "",
                    school_name=settings.school_name if settings else "",
                )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)


# ── Main screen ──────────────────────────────────────────────────────────────

class DailyReceptionScreen(QWidget):
    """محضر تسليم الخدمة اليومي screen — 3 delivered-quantity fields
    prefilled from ورقة الاتصال, remarks, save + export."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._build_ui()
        self._load_today()

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
        inner.setSpacing(20)

        inner.addLayout(self._build_header())
        inner.addLayout(self._build_date_bar())
        inner.addWidget(self._build_quantities_card())
        inner.addWidget(self._build_remarks_section())
        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(17); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        sub = QLabel(_SUBTITLE)
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        col.addWidget(title)
        col.addWidget(sub)
        return col

    def _btn(self, label: str, color: str, *, icon: str | None = None) -> QPushButton:
        return IconButton(
            label, icon=icon, bg=color, text_color="white",
            border_radius=6, padding_h=12, font_size=13, bold=False, min_height=36,
        )

    def _build_date_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel(_LBL_DATE, styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))

        self._date_edit = DateInput(display_format="yyyy-MM-dd")
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setMinimumHeight(36)
        self._date_edit.setMinimumWidth(150)
        self._date_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        row.addWidget(self._date_edit)

        for label, icon, slot in [
            (_BTN_TODAY, None,          self._load_today),
            (_BTN_PREV,  _BTN_PREV_ICON, self._go_prev),
            (_BTN_NEXT,  _BTN_NEXT_ICON, self._go_next),
        ]:
            b = self._btn(label, COLOR_TEXT_PRIMARY, icon=icon)
            b.clicked.connect(slot)
            row.addWidget(b)

        row.addStretch()

        recompute_btn = self._btn(_BTN_RECOMPUTE, COLOR_ACCENT, icon=_BTN_RECOMPUTE_ICON)
        recompute_btn.clicked.connect(self._recompute_from_contacts)
        row.addWidget(recompute_btn)

        return row

    def _build_quantities_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "background:white; border-radius:12px;"
            f"border:1px solid {COLOR_BORDER};"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel(_LBL_QUANTITIES)
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color:{COLOR_ACCENT}; padding-bottom:4px;")
        layout.addWidget(title)

        self._quantity_spins: Dict[str, QSpinBox] = {}
        for meal_key, meal_label in _MEAL_ORDER:
            row = QHBoxLayout()
            lbl = QLabel(meal_label)
            lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px;")
            spin = QSpinBox()
            spin.setRange(0, 9999)
            spin.setMinimumHeight(32)
            spin.setMinimumWidth(120)
            spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            spin.setStyleSheet(
                f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:2px 8px;"
            )
            self._quantity_spins[meal_key] = spin
            row.addWidget(lbl, 1)
            row.addWidget(spin)
            layout.addLayout(row)

        return card

    def _build_remarks_section(self) -> QGroupBox:
        grp = QGroupBox(_LBL_NOTES)
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
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
        layout = QVBoxLayout(grp)

        self._remarks_edit = QTextEdit()
        self._remarks_edit.setPlaceholderText(_NOTES_HINT)
        self._remarks_edit.setMinimumHeight(100)
        self._remarks_edit.setMaximumHeight(160)
        self._remarks_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:8px; font-size:{FONT_BODY}px;"
        )
        layout.addWidget(self._remarks_edit)

        btn_row = QHBoxLayout()
        save_btn = self._btn(_BTN_SAVE, COLOR_SUCCESS, icon=_BTN_SAVE_ICON)
        save_btn.clicked.connect(self._on_save)
        save_btn.setMaximumWidth(200)
        export_btn = self._btn(_BTN_EXPORT, COLOR_TEXT_PRIMARY, icon=_BTN_EXPORT_ICON)
        export_btn.clicked.connect(self._on_export)
        export_btn.setMaximumWidth(160)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return grp

    # ── Date navigation / generate ──────────────────────────────────────────

    def _selected_date_str(self) -> str:
        return self._date_edit.date().toString("yyyy-MM-dd")

    def _load_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self._generate()

    def _go_prev(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self._generate()

    def _go_next(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self._generate()

    def _generate(self) -> None:
        """Load the saved record for this date, or prefill quantities
        from ورقة الاتصال if none exists yet — never silently overwrites
        an already-saved record (use إعادة الحساب for that explicitly)."""
        date_str = self._selected_date_str()
        record = get_daily_reception_record(date_str)
        if record is not None:
            self._quantity_spins[MEAL_FTOUR].setValue(record.ftour_qty)
            self._quantity_spins[MEAL_GHADA].setValue(record.ghada_qty)
            self._quantity_spins[MEAL_ASHA].setValue(record.asha_qty)
            self._remarks_edit.setPlainText(record.remarks)
        else:
            self._recompute_from_contacts()
            self._remarks_edit.setPlainText("")

    def _recompute_from_contacts(self) -> None:
        """Force-refill quantities from ورقة الاتصال, overwriting whatever
        is currently in the spinboxes. Only triggered by an explicit user
        click when a saved record already exists — see _generate."""
        quantities = _quantities_from_contacts(self._selected_date_str())
        for meal_key, spin in self._quantity_spins.items():
            spin.setValue(quantities[meal_key])

    # ── Save / export ────────────────────────────────────────────────────────

    def _current_record(self) -> DailyReceptionRecord:
        return DailyReceptionRecord(
            date=self._selected_date_str(),
            ftour_qty=self._quantity_spins[MEAL_FTOUR].value(),
            ghada_qty=self._quantity_spins[MEAL_GHADA].value(),
            asha_qty=self._quantity_spins[MEAL_ASHA].value(),
            remarks=self._remarks_edit.toPlainText().strip(),
        )

    def _on_save(self) -> None:
        try:
            save_daily_reception_record(self._current_record())
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_export(self) -> None:
        export_format = ask_export_format(self)
        if export_format is None or export_format == "cancel":
            return

        date_str = self._selected_date_str()
        default_name = f"{_PDF_DEFAULT_NAME}_{date_str}"
        is_pdf = export_format == EXPORT_FORMAT_PDF
        path_str, _ = QFileDialog.getSaveFileName(
            self, _PDF_DIALOG_TITLE,
            f"{default_name}.{'pdf' if is_pdf else 'docx'}",
            _PDF_FILTER if is_pdf else _DOCX_FILTER,
        )
        if not path_str:
            return

        path = Path(path_str)
        suffix = ".pdf" if is_pdf else ".docx"
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)

        try:
            record = self._current_record()
            save_daily_reception_record(record)
            settings = get_school_settings()
            if is_pdf:
                _write_reception_pdf(path, settings, date_str, record)
            else:
                _write_reception_docx(path, date_str, record, settings)
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_EXPORT_ERROR}\n{exc}")
