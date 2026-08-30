"""
src/ui/daily_reception_screen.py
Daily reception record (محضر تسليم الخدمة اليومي) — confirms a day's
delivered meals were received and accepted, signed by STEWARD/HEADMASTER/
CONTRACTOR. Quantities default from that date's ورقة الاتصال totals but
are their own editable, saved snapshot — see core.models.DailyReceptionRecord.
"""
import unicodedata
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
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_IFTAR, MEAL_SHOUR, MEAL_LABELS,
    FONT_BODY, FONT_LABEL, FONT_SECTION,
)
from core.models import DailyReceptionRecord, SchoolSettings
from data.database import (
    get_daily_reception_record, get_day_absences, get_day_contacts,
    get_school_settings, save_daily_reception_record,
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

_RAMADAN_MEAL_ORDER = [
    (MEAL_IFTAR, MEAL_LABELS[MEAL_IFTAR]),
    (MEAL_SHOUR, MEAL_LABELS[MEAL_SHOUR]),
]

_ALL_MEAL_ORDER = _MEAL_ORDER + _RAMADAN_MEAL_ORDER


def _meals_for_document(date_str: str):
    """The meals this date served — Ramadan's two or the normal three — so
    the record confirms delivery of what was actually served."""
    from core.ramadan import meals_for_date
    from data.database import get_ramadan_overrides
    active = meals_for_date(date_str, get_school_settings(), get_ramadan_overrides())
    labels = dict(_ALL_MEAL_ORDER)
    return [(key, labels.get(key, key)) for key in active]


def _record_quantities(record, meals) -> list:
    """Each meal's stored quantity, in the given meal order."""
    return [getattr(record, _MEAL_QTY_FIELD[key], 0) for key, _label in meals]

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
# Only used by the hand-drawn PDF path now — the DOCX fill no longer
# overwrites the template's own role-label cells (see
# _fill_reception_document_xml), so this only needs to mirror the real
# template's CURRENT wording for the PDF to visually match it.
# The marché's objet, as it reads on this document. Was a Settings field
# until 2026-08-29; it was blank in the real database, so every export
# already printed exactly this — the user asked for the field to go.
_CONTRACT_OBJECT_FR = "PRESTATION DE RESTAURATION AU PROFIT DE L’INTERNAT DU"

_SIGNER_ROLES_FR   = ["CHEF D'ÉTABLISSEMENT", "Gestionnaire des services matériels et financiers"]
_ITEMS_COLUMNS_FR  = ["N°Article", "Désignation des Articles", "Unité", "Quantité"]
_MEAL_DESIGNATION_FR = {
    MEAL_FTOUR: "Le petit-déjeuner",
    MEAL_GHADA: "Le déjeuner",
    MEAL_ASHA:  "Le dîner",
    # The quarterly attestation template names the Ramadan meals FTOUR and
    # SHOUR, so the reception record uses the same French wording.
    MEAL_IFTAR: "Le Ftour",
    MEAL_SHOUR: "Le Shour",
}

# The DB column holding each meal's quantity on a reception record.
_MEAL_QTY_FIELD = {
    MEAL_FTOUR: "ftour_qty",
    MEAL_GHADA: "ghada_qty",
    MEAL_ASHA: "asha_qty",
    MEAL_IFTAR: "ftour_ramadan_qty",
    MEAL_SHOUR: "shour_qty",
}
_UNIT_FR = "Unité"
# The template's own footer text reads, left to right: Directeur, then
# gestionnaire (STEWARD), then prestataire (CONTRACTOR). But
# draw_official_pdf_footer places roles[0] at the RIGHTMOST column (it's
# built for this app's Arabic right-to-left documents) — so matching the
# template's true left-to-right reading order means listing them here in
# the OPPOSITE order: last-to-appear-on-the-right first.
_FOOTER_ROLES_FR = ["Le prestataire de service", "Le gestionnaire", "Le Directeur"]


def _quantities_from_contacts(date_str: str) -> Dict[str, int]:
    """Per-meal quantities a fresh محضر التسلم starts from:
    ورقة الاتصال MINUS ورقة الغياب for that date.

    The reception record confirms what was actually DELIVERED, so an ordered
    meal a student did not turn up for must not be counted as received —
    "(daily contact numbers - absence) = the PV daily", the user's own rule.
    Floored at zero: a day whose absence sheet somehow exceeds its contact
    sheet is bad data, not a negative delivery.
    """
    contacts = {c.meal_type: c for c in get_day_contacts(date_str)}
    absences = {a.meal_type: a for a in get_day_absences(date_str)}
    quantities: Dict[str, int] = {}
    for meal_key, _label in _ALL_MEAL_ORDER:
        ordered = contacts[meal_key].grand_total if meal_key in contacts else 0
        absent = absences[meal_key].grand_total if meal_key in absences else 0
        quantities[meal_key] = max(0, ordered - absent)
    return quantities


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
    fields = {_MEAL_QTY_FIELD[key]: quantities.get(key, 0)
              for key, _label in _meals_for_document(date_str)}
    return DailyReceptionRecord(date=date_str, **fields)


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
    painter: QPainter, *, top: float, left: float, content_w: float,
    settings: Optional[SchoolSettings],
) -> float:
    """The template's "Nous soussignons :" name/role table — prefilled
    with the configured director/gestionnaire names (the user asked for
    this explicitly rather than leaving the cells blank for handwriting).
    French content reads left-to-right (NOM ET PRENOM first/left, FONCTION
    second/right), same order the template's own table uses — drawn
    left-to-right here to match, not this app's usual RTL-first column
    order. Returns the Y position after the table."""
    ltr = Qt.LayoutDirection.LeftToRight
    s = settings
    signer_names = [
        ((s.director if s else "") or "").strip(),
        ((s.gestionnaire if s else "") or "").strip(),
    ]
    y = top
    _draw_reception_pdf_text(
        painter, QRectF(left, y, content_w, 20), _SIGNER_LABEL_FR,
        size=11, color=COLOR_TEXT_PRIMARY, direction=ltr,
        align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute,
    )
    y += 24

    columns = ["NOM ET PRENOM", "FONCTION"]
    col_widths = [content_w * 0.55, content_w * 0.45]
    header_h = 26.0
    row_h = 28.0

    current_left = left
    for col_label, col_w in zip(columns, col_widths):
        rect = QRectF(current_left, y, col_w, header_h)
        _draw_reception_pdf_cell(
            painter, rect, background="white", border="#000000",
            text=col_label, text_color="#000000", size=9, bold=True, direction=ltr,
        )
        current_left = rect.right()

    row_y = y + header_h
    for role, name in zip(_SIGNER_ROLES_FR, signer_names):
        current_left = left
        for index, (value, col_w) in enumerate(zip([name, role], col_widths)):
            rect = QRectF(current_left, row_y, col_w, row_h)
            _draw_reception_pdf_cell(
                painter, rect, background="white", border="#000000",
                text=value, text_color="#000000", size=9, direction=ltr,
            )
            current_left = rect.right()
        row_y += row_h

    return row_y + 14


def _draw_reception_items_table(
    painter: QPainter, *, top: float, left: float, content_w: float,
    ftour_qty: int = 0, ghada_qty: int = 0, asha_qty: int = 0,
    meals=None, quantities=None,
) -> float:
    """The template's 4-column N°Article/Désignation/Unité/Quantité table
    — identical shape in both the daily and monthly reception records
    (shared with monthly_reception_screen.py). French content reads
    left-to-right, matching the template's own table exactly. Returns the
    Y position after the table."""
    ltr = Qt.LayoutDirection.LeftToRight
    columns = _ITEMS_COLUMNS_FR
    col_widths = [content_w * 0.10, content_w * 0.45, content_w * 0.20, content_w * 0.25]
    header_h = 32.0
    row_h = 32.0
    # A Ramadan record lists two meals instead of three; callers that predate
    # Ramadan support still pass the three named quantities.
    meals = meals or _MEAL_ORDER
    if quantities is None:
        quantities = [ftour_qty, ghada_qty, asha_qty]
    table_h = header_h + (row_h * len(meals))

    y = top
    current_left = left
    for col_label, col_w in zip(columns, col_widths):
        rect = QRectF(current_left, y, col_w, header_h)
        _draw_reception_pdf_cell(
            painter, rect, background="white", border="#000000",
            text=col_label, text_color="#000000", size=10, bold=True, direction=ltr,
        )
        current_left = rect.right()

    row_y = y + header_h
    for row_number, ((meal_key, _), qty) in enumerate(zip(meals, quantities), start=1):
        values = [str(row_number), _MEAL_DESIGNATION_FR[meal_key], _UNIT_FR, str(qty)]
        current_left = left
        for index, (value, col_w) in enumerate(zip(values, col_widths)):
            rect = QRectF(current_left, row_y, col_w, row_h)
            _draw_reception_pdf_cell(
                painter, rect, background="white", border="#000000",
                text=value, text_color="#000000", size=10, bold=(index == 1), direction=ltr,
            )
            current_left = rect.right()
        row_y += row_h

    return row_y + 16


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
    (الصفحة الرئيسية's combined batch PDF)."""
    s = settings
    company = ((s.company_name if s else "") or "") or "—"
    school_fr = ((s.school_name_fr if s else "") or (s.school_name if s else "")) or "—"
    contract_number = ((s.contract_number if s else "") or "").strip() or "—"
    contract_object = _CONTRACT_OBJECT_FR
    place = ((s.city_fr if s else "") or (s.city if s else "") or "").strip() or "—"
    display_date = _reception_date_format(date_str)

    margin = 38.0
    content_w = page_w - (margin * 2)

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

    ltr = Qt.LayoutDirection.LeftToRight
    left_align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute

    meta_lines = [f"Date : {display_date}", f"Société : {company}"]
    for line in meta_lines:
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 24), line,
            size=11, color=COLOR_TEXT_PRIMARY, direction=ltr, align=left_align,
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
        size=9, color=COLOR_TEXT_PRIMARY, direction=ltr, align=left_align,
    )
    y += 82

    y = _draw_reception_signer_table(painter, top=y, left=margin, content_w=content_w, settings=settings)

    meals = _meals_for_document(record.date)
    y = _draw_reception_items_table(
        painter, top=y, left=margin, content_w=content_w,
        meals=meals, quantities=_record_quantities(record, meals),
    )

    if record.remarks.strip():
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 34),
            f"Remarques : {record.remarks.strip()}",
            size=10, color=COLOR_TEXT_SECONDARY, direction=ltr, align=left_align,
        )
        y += 34

    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 20),
        f"FAIT A {place}. LE {display_date}",
        size=10, color=COLOR_TEXT_PRIMARY, bold=True, direction=ltr, align=left_align,
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
        # Via _record_for_date so the day's OWN meals are stored: building the
        # record inline from ftour/ghada/asha only saved an all-zero record on
        # every Ramadan day, because those three are not what a Ramadan day
        # serves.
        record = _record_for_date(date_str)
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


def _set_mergefield_value(root: ET.Element, field_name: str, value: str, *, align: Optional[str] = None) -> None:
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
    match. `align` (e.g. "start") overrides that paragraph's inherited
    style alignment — both this template's date paragraphs use the
    BodyText style, whose default is centered, with no per-paragraph
    override of their own."""
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
        if align is not None:
            _set_paragraph_alignment(paragraph, align)
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


def _set_paragraph_alignment(paragraph: ET.Element, align: str) -> None:
    """Force a paragraph's alignment, overriding whatever it inherits
    from its style (see _set_mergefield_value's `align` docstring)."""
    pPr = paragraph.find("w:pPr", _WORD_NS)
    if pPr is None:
        pPr = ET.Element(f"{{{_W_NS}}}pPr")
        paragraph.insert(0, pPr)
    jc = pPr.find("w:jc", _WORD_NS)
    if jc is None:
        jc = ET.SubElement(pPr, f"{{{_W_NS}}}jc")
    jc.set(f"{{{_W_NS}}}val", align)


def _normalize_for_match(text: str) -> str:
    """Strips accents and uppercases before matching template row/cell
    text. The signer table's role labels have been hand-edited enough
    times that plain "ETABLISSEMENT"/"ECONOME" checks started missing a
    later edit that added accents ("ÉTABLISSEMENT", "ÉCONOME") and a
    curly apostrophe — normalizing both sides means the next accent-only
    spelling change won't silently break the match again."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.upper()


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


def _fill_reception_legal_paragraphs(root: ET.Element, settings: Optional[SchoolSettings], display_date: str) -> None:
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
    contract_object = _CONTRACT_OBJECT_FR
    school_fr = ((s.school_name_fr if s else "") or (s.school_name if s else "") or "").strip() or "—"
    company = ((s.company_name if s else "") or "").strip() or "—"
    place = ((s.city_fr if s else "") or (s.city if s else "") or "").strip() or "—"

    # The paragraph that used to hold the school name ("LYCEE QUALIFIANT
    # ...") was deleted by the user's own hand-editing — no matchable
    # text is left there, just a blank paragraph sitting between
    # "Attestons que..." and "Ont été réellement exécutées...". Track
    # that position instead: the first blank leaf paragraph seen right
    # after "Attestons que..." is where the school name goes.
    expect_school_name_next = False
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
                f"ayant pour objet : {contract_object} :",
            )
            expect_school_name_next = True
        elif "LYCEE QUALIFIANT" in text:
            _set_docx_text(paragraph, school_fr)
            expect_school_name_next = False
        elif text.startswith("Ont été réellement exécutées"):
            _set_docx_text(paragraph, f"Ont été réellement exécutées par la Sté : {company}.")
            expect_school_name_next = False
        elif expect_school_name_next and not text.strip():
            _set_docx_text(paragraph, school_fr)
            expect_school_name_next = False
        elif text.strip().lower().startswith("fait a"):
            has_live_field = paragraph.find(".//w:instrText", _WORD_NS) is not None
            if has_live_field:
                # A real MERGEFIELD still shares this paragraph — only
                # touch the static label, let _set_mergefield_value fill
                # the date field itself (same paragraph, separate run).
                _set_paragraph_leading_static_text(paragraph, f"FAIT A {place}. LE ")
            else:
                # No field left to preserve (the user's hand-edited
                # template no longer has one here) — the date has nowhere
                # else to go, so write it directly into the whole line.
                # Still needs the same explicit left-alignment override
                # _set_mergefield_value(align=...) gives the field-based
                # path — this paragraph inherits a centered style
                # otherwise (see _set_paragraph_alignment's docstring).
                _set_docx_text(paragraph, f"FAIT A {place}. LE {display_date}")
                _set_paragraph_alignment(paragraph, "start")


_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def _fix_reception_header_body_gap(root: ET.Element) -> None:
    """Small, cheap safety margin: the template's page margins leave
    almost no vertical gap between where the header zone starts
    (`pgMar/@w:header`) and where the body starts (`pgMar/@w:top`) — 2098
    vs 2155 twentieths-of-a-point in the real template, about 3pt. Only
    raises `top` a modest amount (never lowers an already-generous one)
    — kept small specifically to avoid pushing body content onto a
    second page, which a larger version of this fix did. The real,
    targeted fix for the header text itself is
    _fix_reception_header_textbox_clearance below; this is a secondary
    hedge, not the primary mechanism."""
    pgMar = root.find(".//w:sectPr/w:pgMar", _WORD_NS)
    if pgMar is None:
        return
    header_attr = f"{{{_W_NS}}}header"
    top_attr = f"{{{_W_NS}}}top"
    header_dist = pgMar.get(header_attr)
    if header_dist is None:
        return
    needed_top = int(header_dist) + 400  # ~20pt — modest, won't force a 2nd page
    current_top = int(pgMar.get(top_attr, "0"))
    if current_top < needed_top:
        pgMar.set(top_attr, str(needed_top))


def _compress_reception_blank_paragraph_spacing(root: ET.Element) -> None:
    """The body has several purely-blank paragraphs — spacers left over
    from the user's own hand-editing — that each inherit the Normal
    style's default 8pt after-paragraph spacing. With 11 of them in the
    current template that alone adds up to roughly 90pt of pure
    whitespace, which is enough on its own to push the closing "FAIT
    A...LE" line onto a second page. Caps (never removes outright) each
    blank paragraph's own `after` spacing at a small value — applied at
    OUTPUT time only, the template FILE itself is never touched — and
    only to direct body paragraphs with no visible text, so no visible
    content shifts or shrinks, only the redundant gap between blank
    lines does."""
    body = root.find(f"{{{_W_NS}}}body")
    if body is None:
        return
    max_after = 40  # ~2pt — trims the excess without collapsing the gap entirely
    for paragraph in body.findall(f"{{{_W_NS}}}p"):
        text = "".join(t.text or "" for t in paragraph.iter(f"{{{_W_NS}}}t"))
        if text.strip():
            continue
        pPr = paragraph.find(f"{{{_W_NS}}}pPr")
        if pPr is None:
            pPr = ET.Element(f"{{{_W_NS}}}pPr")
            paragraph.insert(0, pPr)
        spacing = pPr.find(f"{{{_W_NS}}}spacing")
        if spacing is None:
            spacing = ET.SubElement(pPr, f"{{{_W_NS}}}spacing")
        after_attr = f"{{{_W_NS}}}after"
        current_after = spacing.get(after_attr)
        current_val = int(current_after) if current_after is not None else 160  # Normal style default
        if current_val > max_after:
            spacing.set(after_attr, str(max_after))


def _shrink_reception_remarks_blank_row(root: ET.Element) -> None:
    """The remarks table's 2nd row (the blank cell reserved for a
    handwritten or typed remark) declares trHeight=1921 twentieths
    (~96pt / ~3.4cm) for a SINGLE EMPTY CELL — by far the single largest
    row height anywhere in the document's 3 tables, and on its own
    bigger than the entire estimated page-2 overflow. Since every row in
    this table uses hRule="atLeast" (a minimum, never a hard cap),
    shrinking the declared value cannot clip real remarks text — Word
    always renders at least the content's own natural height regardless
    of what's declared here. Caps it at a still-generous ~47pt (enough
    for 1-2 lines of handwriting), never raises it. Applied at OUTPUT
    time only — the template file itself is never touched."""
    max_height = 950  # ~47.5pt — still generous handwriting space
    for table in root.findall(f".//{{{_W_NS}}}tbl"):
        rows = table.findall(f"{{{_W_NS}}}tr")
        row_texts = ["".join(t.text or "" for t in row.iter(f"{{{_W_NS}}}t")) for row in rows]
        if not any("Remarques" in text for text in row_texts):
            continue
        for row in rows:
            trPr = row.find(f"{{{_W_NS}}}trPr")
            if trPr is None:
                continue
            trHeight = trPr.find(f"{{{_W_NS}}}trHeight")
            if trHeight is None:
                continue
            val_attr = f"{{{_W_NS}}}val"
            current = trHeight.get(val_attr)
            if current is not None and int(current) > max_height:
                trHeight.set(val_attr, str(max_height))


def _fix_reception_header_textbox_clearance(root: ET.Element) -> None:
    """The header's academy/directorate/school text does NOT live in a
    plain paragraph — it's inside a floating DrawingML "Group" shape
    (image + a separate text box, grouped) anchored to the page margin:
    `wp:positionV relativeFrom="margin"` with a NEGATIVE `wp:posOffset`
    exactly equal to the group's own total height, meaning the group's
    bottom edge — and the text box inside it, whose own local height
    reaches almost that same bottom edge — sits flush against the page
    margin line (where body content starts), with no clearance at all.
    This is very likely why the text renders invisible/collided for the
    user despite being verified byte-correct three separate times.
    Pushes the WHOLE floating group further above the margin line (more
    negative offset) so its content has real breathing room before the
    body starts — a targeted fix to the actual floating shape's own
    position, independent of body pagination (so it can't push content
    onto a second page the way widening pgMar/top did)."""
    for offset in root.iter(f"{{{_WP_NS}}}posOffset"):
        parent_map = {c: p for p in root.iter() for c in p}
        parent = parent_map.get(offset)
        if parent is None or parent.tag != f"{{{_WP_NS}}}positionV":
            continue
        try:
            current = int(offset.text or "0")
        except ValueError:
            continue
        if current >= 0:
            continue  # only adjust shapes anchored upward-of-margin like this one
        offset.text = str(current - 254000)  # push ~20pt further above the margin line


def _push_reception_title_box_down(root: ET.Element) -> None:
    """The bilingual title box (a floating rounded-rectangle shape,
    `wp:anchor relativeFrom="paragraph"`) sits close to its own anchor
    paragraph's top — as little as ~11pt in the monthly template's
    current hand-edited state, vs ~29pt in the daily one — close enough
    to visibly collide with whatever the header's own floating content
    renders just above it (a real user-reported overlap in the monthly
    export). Pushes any SMALL positive `positionV/posOffset` (the title
    box's own small vertical anchor offset) further down for real
    clearance. Scoped to small positive values only (a few points) so it
    never touches an already-generous offset like the daily template's
    own — safe, harmless no-op there — nor a large/negative one, which
    would be some other, unrelated shape. Call on document.xml's root,
    not the header's.

    Kept modest (not the ~24pt a first attempt used) on purpose: the raw
    template's own flow height between the title paragraph and whatever
    comes right after it (measured from real BodyText style line
    heights, not a guess) leaves only ~8pt of natural clearance below
    the box already — a bigger push ate through that AND overlapped the
    next real content, a real regression the user caught. Paired with
    _widen_reception_title_clearance_gap below, which grows that window
    instead of just shuffling the box within it."""
    for offset in root.iter(f"{{{_WP_NS}}}posOffset"):
        parent_map = {c: p for p in root.iter() for c in p}
        parent = parent_map.get(offset)
        if parent is None or parent.tag != f"{{{_WP_NS}}}positionV":
            continue
        try:
            current = int(offset.text or "0")
        except ValueError:
            continue
        if not (0 <= current < 200000):  # a few points at most, positive only
            continue
        offset.text = str(current + 150000)  # ~12pt more clearance, not ~24pt


def _widen_reception_title_clearance_gap(root: ET.Element) -> None:
    """Grows the flow-height window between the title paragraph (body
    index 0 — the one holding the floating title-box drawing) and the
    next real text, instead of only moving the title box within a
    window that's barely bigger than the box itself. Adds a modest,
    fixed amount to each blank paragraph's own line-height in that gap —
    computed to add roughly +5-6pt per paragraph (~25-30pt total across
    a typical 5-paragraph gap), enough to comfortably cover the box's
    own ~76pt height plus _push_reception_title_box_down's own push,
    with a real safety margin either way — NOT doubled, which was tried
    first and added ~60-70pt, enough to risk pushing the whole document
    onto a 2nd page (this document's total content height is already
    close to its one-page budget, same as the daily template's own
    history of 2-page regressions from over-generous spacing fixes).
    Only touches body-level blank paragraphs between index 0 and the
    first text-bearing one, so it can't affect spacing anywhere else in
    the document (e.g. where _compress_reception_blank_paragraph_spacing
    is deliberately trying to SAVE space for page-fit) — these two fixes
    work in different regions of the same document, not against each
    other."""
    body = root.find(f"{{{_W_NS}}}body")
    if body is None:
        return
    paragraphs = body.findall(f"{{{_W_NS}}}p")
    if not paragraphs:
        return
    extra_line = 100  # ~+5-6pt per paragraph at this document's 12.5pt BodyText size
    for paragraph in paragraphs[1:]:
        text = "".join(t.text or "" for t in paragraph.iter(f"{{{_W_NS}}}t"))
        if text.strip():
            break  # reached the next real content — stop widening
        pPr = paragraph.find(f"{{{_W_NS}}}pPr")
        if pPr is None:
            pPr = ET.Element(f"{{{_W_NS}}}pPr")
            paragraph.insert(0, pPr)
        spacing = pPr.find(f"{{{_W_NS}}}spacing")
        if spacing is None:
            spacing = ET.SubElement(pPr, f"{{{_W_NS}}}spacing")
        line_attr = f"{{{_W_NS}}}line"
        rule_attr = f"{{{_W_NS}}}lineRule"
        current_line = spacing.get(line_attr)
        base = int(current_line) if current_line is not None else 240  # BodyText style default
        spacing.set(rule_attr, "auto")
        spacing.set(line_attr, str(base + extra_line))


_WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
_V_NS = "urn:schemas-microsoft-com:vml"
_PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"

_HEADER_IMAGE_TEXT_GAP_EMU = 254000  # 20pt — how far below the image to place the text
# WHEN a fix is actually needed. A first version used 6pt here, which is real and
# non-negative on paper (verified via direct XML inspection) but the user still reported
# the text reading as touching/overlapping the image after testing it — 6pt is thin
# enough that a small discrepancy between this app's positioning model and Word/
# LibreOffice's own layout engine could plausibly eat it entirely, or it's just too
# subtle to read as "clearly separated" at normal zoom. 20pt gives real margin against
# either explanation.
_HEADER_IMAGE_TEXT_OVERLAP_THRESHOLD_EMU = 0  # trigger point: genuine overlap only.
# Deliberately NOT the same value as the gap above — the daily template's own text
# already sits 8pt clear of its image (real, positive, no reported problem there). If
# the trigger used the same 20pt target, 8pt would count as "not clear enough" too and
# this fix would start moving daily's already-confirmed-good header as a side effect of
# raising monthly's target. Only an actual overlap (zero or negative clearance) triggers
# a move; a template that's already positively clear, by any amount, is left exactly
# where it is.


def _stack_reception_header_text_under_image(root: ET.Element) -> None:
    """Put the header's academy/directorate/school lines fully UNDER the
    ministry crest image and centered, instead of colliding with it —
    and grow the decorative border frame drawn around the whole header
    so it still fully encloses everything after the text moves.

    Measured cause (real numbers from the monthly template): the crest
    image spans -102.0pt..-53.1pt and is `behindDoc="0"` (it paints ON
    TOP), while the identity text box starts at -55.9pt with
    `bodyPr anchor="t"`/`tIns="0"` — so its FIRST line begins 2.75pt
    ABOVE the image's bottom edge and the image paints over it, hiding
    the middle of that line. The daily template's own text box starts at
    -38.1pt vs an image bottom of -46.1pt — already 8pt clear, which is
    why only the monthly one ever showed this.

    Pushing the text down (below the image) without also resizing the
    frame just traded one overlap for another: the frame ("Frame4")
    currently ends at -2.2pt, but the repositioned text now runs to
    +6.8pt — 9pt of text spilling out below the frame's own bottom
    border. Grown here to enclose the union of the image's and the
    (moved) text's real bounds, plus a small margin, rather than left at
    its original fixed size.

    Self-limiting on purpose: only moves a text box that actually
    overlaps, and only grows the frame when text was actually moved — a
    verified no-op on the daily template (whose header has no such empty
    frame shape at all), safe to share by both documents."""
    image_bounds: list = []
    text_anchors: list = []
    frame_anchors: list = []
    for anchor in root.iter(f"{{{_WP_NS}}}anchor"):
        offset_el = anchor.find(f"{{{_WP_NS}}}positionV/{{{_WP_NS}}}posOffset")
        extent = anchor.find(f"{{{_WP_NS}}}extent")
        if offset_el is None or extent is None:
            continue
        try:
            top = int(offset_el.text or "0")
            height = int(extent.get("cy") or "0")
        except (TypeError, ValueError):
            continue
        if anchor.find(f".//{{{_PIC_NS}}}pic") is not None:
            image_bounds.append((top, top + height))
            continue
        has_text = "".join(t.text or "" for t in anchor.iter(f"{{{_W_NS}}}t")).strip()
        if has_text:
            text_anchors.append((anchor, offset_el, extent, top, height))
        else:
            frame_anchors.append((anchor, offset_el, extent, top, height))

    if not image_bounds or not text_anchors:
        return
    image_bottom = max(bottom for _, bottom in image_bounds)
    image_top = min(top for top, _ in image_bounds)
    overlap_cutoff = image_bottom + _HEADER_IMAGE_TEXT_OVERLAP_THRESHOLD_EMU
    target_top = image_bottom + _HEADER_IMAGE_TEXT_GAP_EMU

    moved = False
    new_text_bottom = None
    for anchor, offset_el, extent, top, height in text_anchors:
        if top >= overlap_cutoff:
            new_text_bottom = max(new_text_bottom or 0, top + height)
            continue  # already clear of the image — leave it alone
        offset_el.text = str(target_top)
        _center_anchor_horizontally(anchor)
        _shift_vml_text_rect(root, moved_by_emu=target_top - top)
        moved = True
        new_text_bottom = max(new_text_bottom or 0, target_top + height)

    if not moved or new_text_bottom is None:
        return

    margin = _HEADER_IMAGE_TEXT_GAP_EMU // 2  # ~3pt breathing room inside the frame's own border
    enclosed_top = min(image_top, target_top) - margin
    enclosed_bottom = new_text_bottom + margin
    for anchor, offset_el, extent, top, height in frame_anchors:
        if top <= enclosed_top and top + height >= enclosed_bottom:
            continue  # already big enough
        offset_el.text = str(enclosed_top)
        extent.set("cy", str(enclosed_bottom - enclosed_top))
        _resize_vml_frame_rect(root, new_top_emu=enclosed_top, new_height_emu=enclosed_bottom - enclosed_top)


def _center_anchor_horizontally(anchor: ET.Element) -> None:
    """Centre a floating shape on the page margin via `wp:align`, rather
    than a hardcoded `wp:posOffset` — survives any later change to the
    shape's own width or the template's margins, which a fixed offset
    would not."""
    position_h = anchor.find(f"{{{_WP_NS}}}positionH")
    if position_h is None:
        return
    position_h.set("relativeFrom", "margin")
    for child in list(position_h):
        position_h.remove(child)
    align = ET.SubElement(position_h, f"{{{_WP_NS}}}align")
    align.text = "center"


def _shift_vml_text_rect(root: ET.Element, *, moved_by_emu: int) -> None:
    """The header wraps its shapes in `mc:AlternateContent`: a modern
    DrawingML `Choice` branch and a legacy VML `Fallback` branch, each
    holding its own independent copy of the same shape. Renderers pick
    ONE — so a fix applied only to the DrawingML copy silently does
    nothing wherever the Fallback is the branch that renders. Applies
    the same vertical shift (and horizontal centering) to the VML text
    rectangle, matched by having a `v:textbox` with real text so the
    empty decorative border rect is left alone."""
    shift_pt = moved_by_emu / 12700.0
    for rect in root.iter(f"{{{_V_NS}}}rect"):
        textbox = rect.find(f".//{{{_V_NS}}}textbox")
        if textbox is None:
            continue
        if not "".join(t.text or "" for t in rect.iter(f"{{{_W_NS}}}t")).strip():
            continue  # the empty decorative frame — must not move
        style = rect.get("style") or ""
        parts = []
        for part in style.split(";"):
            key, _, value = part.partition(":")
            key = key.strip()
            if key == "margin-top":
                try:
                    parts.append(f"margin-top:{float(value.strip().replace('pt', '')) + shift_pt:.2f}pt")
                    continue
                except ValueError:
                    pass
            elif key in ("margin-left", "mso-position-horizontal", "mso-position-horizontal-relative"):
                continue  # replaced by the explicit centering below
            if part.strip():
                parts.append(part.strip())
        parts.extend(["mso-position-horizontal:center", "mso-position-horizontal-relative:margin"])
        rect.set("style", ";".join(parts))


def _resize_vml_frame_rect(root: ET.Element, *, new_top_emu: int, new_height_emu: int) -> None:
    """VML twin of the frame-growing half of
    _stack_reception_header_text_under_image — same
    mc:Choice/mc:Fallback reasoning as _shift_vml_text_rect: whichever
    branch a given renderer actually uses must both be fixed, or the fix
    only works in one of Word/LibreOffice. Matched as the `v:rect` with
    NO text in its textbox — the empty decorative border, as opposed to
    the one holding the identity lines."""
    top_pt = new_top_emu / 12700.0
    height_pt = new_height_emu / 12700.0
    for rect in root.iter(f"{{{_V_NS}}}rect"):
        if "".join(t.text or "" for t in rect.iter(f"{{{_W_NS}}}t")).strip():
            continue  # holds real text — the identity box, not the frame
        style = rect.get("style") or ""
        parts = []
        for part in style.split(";"):
            key, _, value = part.partition(":")
            key = key.strip()
            if key == "margin-top":
                parts.append(f"margin-top:{top_pt:.2f}pt")
            elif key == "height":
                parts.append(f"height:{height_pt:.2f}pt")
            elif part.strip():
                parts.append(part.strip())
        rect.set("style", ";".join(parts))


def _blank_reception_header_dead_text(root: ET.Element) -> None:
    """The header's floating image+textbox Group has TWO separate text
    box shapes — a modern DrawingML one (`wps:wsp`, in the Choice branch)
    and a legacy VML one (`v:rect` wrapping a `v:textbox`, in the
    Fallback branch) — both holding a copy of the academy/directorate/
    school text, neither of which ever actually renders for the user
    (confirmed — see _add_reception_header_reliable_text, whose plain-
    paragraph replacement IS confirmed showing).

    Blanks the text (not just visually empty — actually confirmed
    rendering nothing) and, for the VML `v:rect` specifically, strips
    its contradictory `<v:stroke>` child (marked `stroked="f"`/no-border
    on the shape itself, but with an explicit stroke color+weight child
    anyway — some renderers draw the border despite the "f", which is
    very likely why a bordered box showed up unexpectedly).

    Does NOT delete either shape outright — an earlier version of this
    fix did, and it had a real, confirmed side effect: with the text-box
    shape gone, the group's remaining image shape rendered visibly
    LARGER and started overlapping the header's other text, almost
    certainly because the group's own bounding-box math depends on
    having both original child shapes present. Keeping the (now
    text-less, border-less) shapes in place preserves that layout math
    while still fully solving what the user actually cares about: no
    visible leftover text, no visible leftover border."""
    parent_map = {c: p for p in root.iter() for c in p}

    def _has_floating_ancestor(el: ET.Element) -> bool:
        # The target paragraphs are DESCENDANTS of w:drawing/w:pict (deeply
        # nested inside the shape's own txbxContent) — not containers of
        # one. Must walk up the tree, not search down into the paragraph.
        cur = el
        while cur in parent_map:
            cur = parent_map[cur]
            if cur.tag in (f"{{{_W_NS}}}drawing", f"{{{_W_NS}}}pict"):
                return True
        return False

    for p in root.findall(f".//{{{_W_NS}}}p"):
        if p.findall(f".//{{{_W_NS}}}p"):
            continue  # a wrapper, not a leaf
        if not _has_floating_ancestor(p):
            continue  # one of the new plain paragraphs, or something else — leave alone
        for t in p.iter(f"{{{_W_NS}}}t"):
            t.text = ""

    for rect in root.findall(f".//{{{_V_NS}}}rect"):
        if rect.find(f".//{{{_V_NS}}}textbox") is None:
            continue  # some other rect shape, not the text box — leave it alone
        for stroke in rect.findall(f"{{{_V_NS}}}stroke"):
            rect.remove(stroke)


def _add_reception_header_reliable_text(root: ET.Element, academy: str, province: str, school_name: str) -> None:
    """Three separate attempts to fix the header's academy/directorate/
    school text in place (namespace, page margin, floating-shape
    position) were each individually verified byte-correct and STILL
    didn't fix it for the user — meaning something about that floating
    DrawingML/VML Group (image + text box, absolutely positioned,
    behindDoc) isn't rendering its text reliably in their Word/
    LibreOffice, for a reason none of that XML-level analysis could
    pin down further without actually seeing it render.

    Rather than keep guessing at that fragile structure, this adds a
    completely separate, plain, ordinary paragraph directly in the
    header's normal flow — no floating anchor, no group, no text box,
    just a standard Word paragraph the way virtually every renderer
    handles correctly. Placed right after the existing image/group
    paragraph. The original floating text is left untouched (harmless
    if it happens to render on some systems — just redundant text)."""
    identity_lines = [academy.strip() or "—", province.strip() or "—", school_name.strip() or "—"]
    children = list(root)
    insert_at = 1
    for i, child in enumerate(children):
        if child.tag == f"{{{_W_NS}}}p":
            insert_at = i + 1
            break

    for offset, line in enumerate(identity_lines):
        p = ET.Element(f"{{{_W_NS}}}p")
        pPr = ET.SubElement(p, f"{{{_W_NS}}}pPr")
        ET.SubElement(pPr, f"{{{_W_NS}}}bidi").set(f"{{{_W_NS}}}val", "1")
        # Same tight spacing as the original (non-rendering) text box's
        # own paragraphs, so this doesn't look more spread-out than the
        # template's own intended 3-line block.
        spacing = ET.SubElement(pPr, f"{{{_W_NS}}}spacing")
        spacing.set(f"{{{_W_NS}}}lineRule", "auto")
        spacing.set(f"{{{_W_NS}}}line", "240")
        spacing.set(f"{{{_W_NS}}}before", "0")
        spacing.set(f"{{{_W_NS}}}after", "0")
        ET.SubElement(pPr, f"{{{_W_NS}}}jc").set(f"{{{_W_NS}}}val", "center")
        run = ET.SubElement(p, f"{{{_W_NS}}}r")
        rPr = ET.SubElement(run, f"{{{_W_NS}}}rPr")
        # The project's own official Arabic display font (bundled as
        # templets/maghribi-font 1.ttf) — its real internal family name
        # is "arabswell_1", same reference the original template's own
        # (non-rendering) header text used.
        ET.SubElement(rPr, f"{{{_W_NS}}}rFonts").set(f"{{{_W_NS}}}cs", "arabswell_1")
        ET.SubElement(rPr, f"{{{_W_NS}}}rtl").set(f"{{{_W_NS}}}val", "true")
        sz = ET.SubElement(rPr, f"{{{_W_NS}}}sz")
        sz.set(f"{{{_W_NS}}}val", "21")
        szCs = ET.SubElement(rPr, f"{{{_W_NS}}}szCs")
        szCs.set(f"{{{_W_NS}}}val", "21")
        t = ET.SubElement(run, f"{{{_W_NS}}}t")
        t.text = line
        t.set(_XML_SPACE, "preserve")
        root.insert(insert_at + offset, p)


def _fill_reception_document_xml(root: ET.Element, date_str: str, record: DailyReceptionRecord, settings: Optional[SchoolSettings] = None) -> None:
    display_date = _reception_date_format(date_str)
    _set_mergefield_value(root, _MERGEFIELD_DATE, display_date, align="start")
    _set_mergefield_value(root, _MERGEFIELD_FTOUR, str(record.ftour_qty))
    _set_mergefield_value(root, _MERGEFIELD_GHADA, str(record.ghada_qty))
    _fill_reception_legal_paragraphs(root, settings, display_date)
    _fix_reception_header_body_gap(root)
    _push_reception_title_box_down(root)
    _compress_reception_blank_paragraph_spacing(root)
    _shrink_reception_remarks_blank_row(root)

    # A Ramadan day serves two meals, so the template's three meal rows are
    # relabelled and the surplus row removed — the same "same document,
    # fewer rows" rule the user gave for ورقة الاتصال.
    meals = _meals_for_document(record.date)
    quantities = _record_quantities(record, meals)

    # The real template has 3 SEPARATE <w:tbl> elements — signer table,
    # items table, remarks table — not one table with extra rows. Picking
    # "the first table" (or assuming Remarques is a row inside the items
    # table) silently fills the wrong cell.
    for table in root.findall(".//w:tbl", _WORD_NS):
        rows = table.findall("w:tr", _WORD_NS)
        row_texts = ["".join(node.text or "" for node in row.findall(".//w:t", _WORD_NS)) for row in rows]

        meal_rows: List[int] = []
        for index, row_text in enumerate(row_texts):
            # Matched on a normalized (accent-stripped, uppercased) form
            # rather than the exact original template spelling — the
            # template has been hand-edited enough times this session
            # that "ETABLISSEMENT"/"ECONOME" have gone from typo'd
            # ("DETABLISSEMENT", no apostrophe) to corrected
            # ("D'ETABLISSEMENT") to accented ("D'ÉTABLISSEMENT",
            # "ÉCONOME"), and the gestionnaire role's own wording has since
            # changed entirely to "Gestionnaire des services matériels et
            # financiers" (matching monthly_reception_screen.py's own
            # template) — matched here via the loose "GESTIONNAIRE"
            # keyword rather than the old "ECONOME"+"ETABLISSEMENT" pair,
            # which no longer appears at all. The role-label cell itself
            # (cells[1]) is intentionally left untouched now, not
            # overwritten with a hardcoded constant — a previous version
            # of this code silently reverted the user's own accent
            # correction back to plain ASCII every export; only the name
            # cell (cells[0]) is ever written.
            normalized_row = _normalize_for_match(row_text)
            if "CHEF" in normalized_row and "ETABLISSEMENT" in normalized_row:
                cells = rows[index].findall("w:tc", _WORD_NS)
                if cells and settings:
                    _set_empty_run_text(cells[0], (settings.director or "").strip())
            elif ("ECONOME" in normalized_row and "ETABLISSEMENT" in normalized_row) or "GESTIONNAIRE" in normalized_row:
                cells = rows[index].findall("w:tc", _WORD_NS)
                if cells and settings:
                    _set_empty_run_text(cells[0], (settings.gestionnaire or "").strip())
            elif "PETIT-DEJEUNER" in normalized_row:
                meal_rows.append(index)
            elif "DEJEUNER" in normalized_row:  # matches "Le déjeuner" but NOT "petit-déjeuner" (handled above first)
                meal_rows.append(index)
            elif "DINER" in normalized_row:
                # The meal rows' quantity cells have no MERGEFIELD in the
                # real template — the value goes in each row's last (empty)
                # cell. _set_mergefield_value above stays as a harmless
                # fallback for a from-scratch template that still has them.
                meal_rows.append(index)
            elif "REMARQUES" in normalized_row and record.remarks.strip():
                # The blank cell for remarks is the table's NEXT row, not
                # part of this one.
                if index + 1 < len(rows):
                    next_cells = rows[index + 1].findall("w:tc", _WORD_NS)
                    if next_cells:
                        _set_docx_text(next_cells[0], record.remarks.strip())

        # Fill the meal rows this table actually has, in the day's own meal
        # order, then drop any row the day doesn't serve (Ramadan has two
        # meals where the template prints three).
        for position, row_index in enumerate(meal_rows):
            cells = rows[row_index].findall("w:tc", _WORD_NS)
            if not cells:
                continue
            if position < len(meals):
                _set_empty_run_text(cells[-1], str(quantities[position]))
                if len(cells) >= 2:
                    _set_docx_text(cells[1], _MEAL_DESIGNATION_FR[meals[position][0]])
            else:
                table.remove(rows[row_index])


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
                academy = settings.aref if settings else ""
                province = settings.direction_provinciale if settings else ""
                school_name = settings.school_name if settings else ""
                filled = _fill_contact_header_xml(root, academy=academy, province=province, school_name=school_name)
                _fix_reception_header_textbox_clearance(root)
                _stack_reception_header_text_under_image(root)
                if filled == 0:
                    # The template's own header text box has nothing
                    # matchable in it (e.g. a from-scratch/empty template)
                    # — fall back to a separate, always-visible paragraph
                    # instead of leaving the header blank. When the box
                    # DOES have matchable text, _fill_contact_header_xml
                    # above already filled it correctly — do not blank it
                    # or add a redundant second copy on top of it.
                    _blank_reception_header_dead_text(root)
                    _add_reception_header_reliable_text(root, academy, province, school_name)
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
        # Picking a date from the calendar must load THAT date. Without this
        # the numbers stayed on whatever day was loaded before, and an
        # export then produced a document stamped with the new date but
        # carrying the previous day's figures. Connected last, so it never
        # fires while the widgets are still being built.
        self._date_edit.dateChanged.connect(self._generate)

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
        self._quantity_rows: Dict[str, QWidget] = {}
        for meal_key, meal_label in _ALL_MEAL_ORDER:
            row_host = QWidget()
            row = QHBoxLayout(row_host)
            row.setContentsMargins(0, 0, 0, 0)
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
            self._quantity_rows[meal_key] = row_host
            row.addWidget(lbl, 1)
            row.addWidget(spin)
            layout.addWidget(row_host)

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
        self._apply_meal_visibility()
        if record is not None:
            for meal_key, field in _MEAL_QTY_FIELD.items():
                if meal_key in self._quantity_spins:
                    self._quantity_spins[meal_key].setValue(getattr(record, field, 0))
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
            spin.setValue(quantities.get(meal_key, 0))

    # ── Save / export ────────────────────────────────────────────────────────

    def _apply_meal_visibility(self) -> None:
        """Only the selected date's meals are editable — a Ramadan day
        confirms إفطار/سحور, a normal day the usual three."""
        active = {key for key, _l in _meals_for_document(self._selected_date_str())}
        for meal_key, row_host in getattr(self, "_quantity_rows", {}).items():
            row_host.setVisible(meal_key in active)

    def _current_record(self) -> DailyReceptionRecord:
        """Only the day's own meals are stored, so a normal day never writes
        Ramadan quantities and vice versa."""
        active = {key for key, _l in _meals_for_document(self._selected_date_str())}
        fields = {_MEAL_QTY_FIELD[key]: spin.value()
                  for key, spin in self._quantity_spins.items() if key in active}
        return DailyReceptionRecord(
            date=self._selected_date_str(),
            remarks=self._remarks_edit.toPlainText().strip(),
            **fields,
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
