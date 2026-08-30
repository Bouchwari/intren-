"""
src/ui/monthly_reception_screen.py
Monthly reception record (محضر التسلم الشهري) — the month's collected
reception confirmation, signed by STEWARD/HEADMASTER/CONTRACTOR and sent
to المديرية الإقليمية together with بيان المصاريف. Quantities default from
that month's summed محضر التسلم اليومي records but are their own editable,
saved snapshot — see core.models.MonthlyReceptionRecord.

Real template: templets/المحضر الشهري لتسلم الخدمة.docx — same bilingual
FR/AR shape as the daily record's own template (see
daily_reception_screen.py), no MERGEFIELDs, so the fill logic here is
adaptive from the start rather than relying on live fields. Several
generic OOXML helpers (header fill/fallback, margin-safety fixes, PDF
drawing primitives) are shared with that file via import rather than
duplicated — they don't depend on anything daily-specific.
"""
import datetime
import xml.etree.ElementTree as ET
import copy
from pathlib import Path
from typing import Dict, Optional
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_SUCCESS, COLOR_SURFACE,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    EXPORT_FORMAT_PDF,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_IFTAR, MEAL_SHOUR, MEAL_LABELS,
    FONT_BODY, FONT_LABEL,
)
from core.models import MonthlyReceptionRecord, SchoolSettings
from data.database import (
    get_monthly_reception_record, get_school_settings,
    save_monthly_reception_record, sum_daily_reception_for_month,
)
from ui.daily_contact_screen import (
    _fill_contact_header_xml, _normalize_template_name, _set_docx_text,
    _template_dirs, _WORD_NS, _W_NS, _XML_SPACE,
)
from ui.daily_reception_screen import (
    _add_reception_header_reliable_text, _blank_reception_header_dead_text,
    _compress_reception_blank_paragraph_spacing, _draw_reception_items_table,
    _draw_reception_pdf_cell, _draw_reception_pdf_text,
    _MEAL_DESIGNATION_FR, _record_quantities,
    _fix_reception_header_body_gap, _fix_reception_header_textbox_clearance,
    _normalize_for_match, _push_reception_title_box_down,
    _stack_reception_header_text_under_image,
    _reception_date_format, _set_empty_run_text,
    _set_paragraph_alignment, _shrink_reception_remarks_blank_row,
    _widen_reception_title_clearance_gap,
)
from ui.document_header import (
    ask_export_format, draw_official_pdf_footer, draw_official_pdf_header,
    register_docx_namespaces,
)
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "المحضر الشهري لتسلم الخدمة"
_TITLE_FR       = "PROCES VERBAL DE RECEPTION MENSUEL"
_SUBTITLE       = "تأكيد استلام الوجبات المسلَّمة خلال الشهر من طرف الشركة القائمة"
_LBL_MONTH      = "الشهر:"
_LBL_YEAR       = "السنة:"
_BTN_THIS_MONTH = "الشهر الحالي"
_BTN_RECOMPUTE      = "إعادة الحساب من محاضر التسليم اليومية"
_BTN_RECOMPUTE_ICON = "🔄"
_LBL_QUANTITIES = "الكميات المسلَّمة خلال الشهر"
_LBL_NOTES      = "ملاحظات"
_NOTES_HINT     = "أدخل ملاحظاتك هنا..."
_BTN_SAVE       = "حفظ المحضر"
_BTN_SAVE_ICON  = "💾"
_BTN_EXPORT      = "تصدير"
_BTN_EXPORT_ICON = "📄"
_SAVED_OK       = "تم حفظ المحضر الشهري بنجاح."
_PDF_DIALOG_TITLE = "تصدير المحضر الشهري لتسلم الخدمة"
_PDF_DEFAULT_NAME = "المحضر_الشهري_لتسلم_الخدمة"
_DOCX_FILTER    = "Word (*.docx)"
_PDF_FILTER     = "PDF (*.pdf)"
_EXPORT_ERROR   = "تعذر تصدير المحضر:"
_TEMPLATE_MISSING = "تعذر العثور على نموذج المحضر الشهري لتسلم الخدمة."

_ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر",
]
_FRENCH_MONTHS = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

_RAMADAN_MEAL_ORDER = [
    (MEAL_IFTAR, MEAL_LABELS[MEAL_IFTAR]),
    (MEAL_SHOUR, MEAL_LABELS[MEAL_SHOUR]),
]


def _meals_for_month(month: str):
    """A month containing Ramadan lists all five meals: Ramadan rarely
    covers a whole calendar month, so such a month genuinely has both
    normal and Ramadan days to confirm."""
    from core.ramadan import month_has_ramadan
    from data.database import get_ramadan_overrides
    meals = list(_MEAL_ORDER)
    if month_has_ramadan(month, get_school_settings(), get_ramadan_overrides()):
        meals += _RAMADAN_MEAL_ORDER
    return meals


_MEAL_ORDER = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]

_TEMPLATE_FILE = "المحضر الشهري لتسلم الخدمة.docx"

# The template's "Nous soussignons" table lists Gestionnaire (STEWARD)
# first, then Directeur (HEADMASTER) — matching the real template's own
# row order, not this app's usual director-then-gestionnaire order.
_SIGNER_LABEL_FR = "Nous soussignons :"
_SIGNER_ROLES_FR = ["Gestionnaire des services matériels et financiers", "Directeur"]
# The bottom signature-label row (a separate, later table in the real
# template) reads left-to-right: Directeur, Gestionnaire, Le prestataire
# de service. draw_official_pdf_footer places roles[0] at the RIGHTMOST
# column (built for this app's RTL documents) — listed here in the
# OPPOSITE order so the drawn footer matches the template's true
# left-to-right reading order, same convention daily_reception_screen.py
# uses for its own (structurally different — a repeating page footer,
# not an in-body table) 3-role signature block.
_FOOTER_ROLES_FR = ["Le prestataire de service", "Gestionnaire des services matériels et financiers", "Directeur"]


def _month_label_fr(month: str) -> str:
    """"2026-01" -> "Janvier 2026" — the template's own "au titre du
    mois : ..." wording."""
    year, month_num = month.split("-")
    return f"{_FRENCH_MONTHS[int(month_num) - 1]} {year}"


def _month_label_ar(month: str) -> str:
    year, month_num = month.split("-")
    return f"{_ARABIC_MONTHS[int(month_num) - 1]} {year}"


def _quantities_from_daily_receptions(month: str) -> Dict[str, int]:
    """Per-meal totals from that month's saved محاضر التسليم اليومية — the
    default a fresh monthly reception record starts from."""
    sums = sum_daily_reception_for_month(month)
    return {
        MEAL_FTOUR: sums["ftour"], MEAL_GHADA: sums["ghada"], MEAL_ASHA: sums["asha"],
        MEAL_IFTAR: sums["iftar"], MEAL_SHOUR: sums["shour"],
    }


def _record_for_month(month: str) -> MonthlyReceptionRecord:
    """The MonthlyReceptionRecord for a month, independent of any live
    screen: the saved record if one exists, otherwise quantities freshly
    summed from that month's daily reception records."""
    record = get_monthly_reception_record(month)
    if record is not None:
        return record
    quantities = _quantities_from_daily_receptions(month)
    return MonthlyReceptionRecord(
        month=month,
        ftour_qty=quantities[MEAL_FTOUR],
        ghada_qty=quantities[MEAL_GHADA],
        asha_qty=quantities[MEAL_ASHA],
        ftour_ramadan_qty=quantities[MEAL_IFTAR],
        shour_qty=quantities[MEAL_SHOUR],
    )


# ── PDF export — hand-drawn, matching the real template's field order ──────

def _draw_monthly_signer_table(
    painter: QPainter, *, top: float, left: float, content_w: float,
    settings: Optional[SchoolSettings],
) -> float:
    """The template's "Nous soussignons :" name/role table — prefilled
    with the configured gestionnaire/director names, same as
    daily_reception_screen.py's own signer table, but in this template's
    own row order (Gestionnaire first, Directeur second)."""
    ltr = Qt.LayoutDirection.LeftToRight
    s = settings
    signer_names = [
        ((s.gestionnaire if s else "") or "").strip(),
        ((s.director if s else "") or "").strip(),
    ]
    y = top
    _draw_reception_pdf_text(
        painter, QRectF(left, y, content_w, 20), _SIGNER_LABEL_FR,
        size=11, color=COLOR_TEXT_PRIMARY, direction=ltr,
        align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute,
    )
    y += 24

    columns = ["NOM ET PRENOM", "FONCTION"]
    col_widths = [content_w * 0.45, content_w * 0.55]
    header_h = 26.0
    row_h = 32.0

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
        for value, col_w in zip([name, role], col_widths):
            rect = QRectF(current_left, row_y, col_w, row_h)
            _draw_reception_pdf_cell(
                painter, rect, background="white", border="#000000",
                text=value, text_color="#000000", size=9, direction=ltr,
            )
            current_left = rect.right()
        row_y += row_h

    return row_y + 14


def _draw_monthly_reception_pdf_page(
    painter: QPainter, page_w: float, page_h: float,
    settings: Optional[SchoolSettings], month: str, record: MonthlyReceptionRecord,
) -> None:
    """Draw one month's reception record onto an already-open page,
    mirroring templets/المحضر الشهري لتسلم الخدمة.docx's own real layout."""
    s = settings
    company = ((s.company_name if s else "") or "") or "—"
    school_fr = ((s.school_name_fr if s else "") or (s.school_name if s else "")) or "—"
    contract_number = ((s.contract_number if s else "") or "").strip() or "—"
    place = ((s.city_fr if s else "") or (s.city if s else "") or "").strip() or "—"
    month_label = _month_label_fr(month)
    signed_date = _reception_date_format(datetime.date.today().isoformat())

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

    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 24), f"Mois : {month_label}",
        size=11, color=COLOR_TEXT_PRIMARY, direction=ltr, align=left_align,
    )
    y += 28 + 8

    legal_text = (
        f"Attestons que les prestations objet du marché N° : {contract_number} "
        f"ayant pour objet la prestation de restauration au profit de l'internat "
        f"du : {school_fr}.\n"
        f"Ont été réellement exécutées par la société : {company} conformément "
        f"aux spécifications techniques exigées par le CPS au titre du mois : "
        f"{month_label}, à hauteur des quantités suivantes :"
    )
    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 70), legal_text,
        size=9, color=COLOR_TEXT_PRIMARY, direction=ltr, align=left_align,
    )
    y += 82

    y = _draw_monthly_signer_table(painter, top=y, left=margin, content_w=content_w, settings=settings)

    meals = _meals_for_month(month)
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
        f"Fait à {place} Le {signed_date}",
        size=10, color=COLOR_TEXT_PRIMARY, bold=True, direction=ltr, align=left_align,
    )

    footer_h = 90.0
    footer_y = page_h - margin - footer_h + 6
    draw_official_pdf_footer(
        painter, page_width=page_w, margin=margin, top=footer_y,
        settings=settings, roles=_FOOTER_ROLES_FR,
    )


def _write_monthly_reception_pdf(path: Path, settings, month: str, record: MonthlyReceptionRecord) -> None:
    """Render a single month's reception record as its own standalone PDF."""
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
        _draw_monthly_reception_pdf_page(painter, float(writer.width()), float(writer.height()), settings, month, record)
    finally:
        painter.end()


# ── Word export — fills the real template, no MERGEFIELDs ──────────────────

def _find_monthly_reception_template() -> Optional[Path]:
    for directory in _template_dirs():
        exact = directory / _TEMPLATE_FILE
        if exact.exists():
            return exact
        if not directory.exists():
            continue
        for candidate in directory.glob("*.docx"):
            if "المحضرالشهريلتسلمالخدمة" in _normalize_template_name(candidate.stem):
                return candidate
    return None


def _set_paragraph_runs_with_emphasis(paragraph: ET.Element, spans: list) -> None:
    """Rebuilds a paragraph's runs from a list of (text, bold, italic)
    tuples — used where only PART of a legal sentence (the school name,
    the contractor name) needs bold+italic emphasis, not the whole
    boilerplate sentence around it. Preserves the paragraph's existing
    font (copied from its first existing run's rPr, if any) as a base,
    but explicitly drops any existing w:b/w:i from that copy first — the
    template's own original run was already bold, so blindly copying it
    made EVERY span bold, not just the ones this function meant to
    emphasize.

    Bold/italic are then set EXPLICITLY on every span — `w:val="1"` to
    turn on, `w:val="0"` to turn OFF. Simply omitting `w:b` is NOT
    enough to get plain text here: this template's `BodyText` paragraph
    style carries `<w:b/>` in its own rPr, so any run that doesn't say
    otherwise INHERITS bold from the style. That inheritance is exactly
    why an earlier version of this fix still rendered the whole
    paragraph bold even though the generated XML had no `w:b` on the
    plain runs — the XML looked right, the style overrode it. Always
    state both properties explicitly rather than relying on absence."""
    base_rPr = paragraph.find("w:r/w:rPr", _WORD_NS)
    for run in paragraph.findall("w:r", _WORD_NS):
        paragraph.remove(run)
    for text, bold, italic in spans:
        run = ET.SubElement(paragraph, f"{{{_W_NS}}}r")
        rPr = ET.SubElement(run, f"{{{_W_NS}}}rPr")
        if base_rPr is not None:
            for child in base_rPr:
                if child.tag in (f"{{{_W_NS}}}b", f"{{{_W_NS}}}i",
                                 f"{{{_W_NS}}}bCs", f"{{{_W_NS}}}iCs"):
                    continue  # set explicitly below, per span, never inherited
                rPr.append(ET.fromstring(ET.tostring(child)))
        # Both the Latin (w:b/w:i) and complex-script (w:bCs/w:iCs)
        # variants — this is a bilingual FR/AR document, and Word applies
        # the Cs variants to the Arabic runs.
        for tag, on in (("b", bold), ("i", italic), ("bCs", bold), ("iCs", italic)):
            el = ET.SubElement(rPr, f"{{{_W_NS}}}{tag}")
            el.set(f"{{{_W_NS}}}val", "1" if on else "0")
        t = ET.SubElement(run, f"{{{_W_NS}}}t")
        t.text = text
        t.set(_XML_SPACE, "preserve")


def _fill_monthly_reception_legal_paragraphs(root: ET.Element, settings: Optional[SchoolSettings], month: str, signed_date: str) -> None:
    """The template's French legal paragraphs (contract number, the
    school's own name, the contractor, the reported month, the closing
    place name) are all plain fixed text, not MERGEFIELDs — same
    adaptive-matching approach as daily_reception_screen.py's own
    _fill_reception_legal_paragraphs. The school name and contractor
    name print in bold+italic (per the user's explicit request) — the
    rest of the boilerplate legal text around them stays plain."""
    s = settings
    contract_number = ((s.contract_number if s else "") or "").strip() or "—"
    school_fr = ((s.school_name_fr if s else "") or (s.school_name if s else "") or "").strip() or "—"
    company = ((s.company_name if s else "") or "").strip() or "—"
    place = ((s.city_fr if s else "") or (s.city if s else "") or "").strip() or "—"
    month_label = _month_label_fr(month)

    attestons_prefix = (
        f"Attestons que les prestations objet du marché N° : {contract_number} "
        f"ayant pour objet la prestation de restauration au profit de l'internat du : "
    )
    ont_ete_prefix = " Ont été réellement exécutées par la société : "
    ont_ete_suffix = (
        f" conformément aux spécifications techniques exigées par le CPS au titre du mois : "
        f"{month_label}, à hauteur des quantités suivantes :"
    )

    # The user's hand-editing has, at different points, held this content
    # as 3 separate paragraphs (contract sentence / school name / company
    # sentence) and, currently, merged into ONE paragraph containing all
    # 3 concepts back to back. Handling both shapes: if a single
    # paragraph contains BOTH "Attestons que" and "Ont été réellement
    # exécutées", it's the merged case — rebuild the whole thing in one
    # go (the separate-paragraph branches below would otherwise only
    # ever see this merged paragraph via the FIRST matching branch,
    # silently wiping out the rest when _set_docx_text replaces the
    # whole paragraph's text).
    expect_school_name_next = False
    for paragraph in root.findall(".//w:p", _WORD_NS):
        if paragraph.findall(".//w:p", _WORD_NS):
            continue
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS))
        if text.startswith("Attestons que") and "Ont été réellement exécutées" in text:
            _set_paragraph_runs_with_emphasis(paragraph, [
                (attestons_prefix, False, False),
                (school_fr, True, True),
                (ont_ete_prefix, False, False),
                (company, True, True),
                (ont_ete_suffix, False, False),
            ])
            expect_school_name_next = False
        elif text.startswith("Attestons que"):
            _set_docx_text(paragraph, attestons_prefix.strip())
            expect_school_name_next = True
        elif "Lycée Qualifiant" in text or "LYCEE QUALIFIANT" in text.upper():
            _set_paragraph_runs_with_emphasis(paragraph, [(school_fr, True, True)])
            expect_school_name_next = False
        elif text.startswith("Ont été réellement exécutées"):
            _set_paragraph_runs_with_emphasis(paragraph, [
                (ont_ete_prefix.strip() + " ", False, False),
                (company, True, True),
                (ont_ete_suffix, False, False),
            ])
            expect_school_name_next = False
        elif expect_school_name_next and not text.strip():
            _set_paragraph_runs_with_emphasis(paragraph, [(school_fr, True, True)])
            expect_school_name_next = False
        elif text.strip().lower().startswith("fait"):
            _set_docx_text(paragraph, f"Fait à {place} Le {signed_date}")
            _set_paragraph_alignment(paragraph, "start")


def _fill_monthly_reception_document_xml(root: ET.Element, month: str, record: MonthlyReceptionRecord, settings: Optional[SchoolSettings] = None) -> None:
    signed_date = _reception_date_format(datetime.date.today().isoformat())
    _fill_monthly_reception_legal_paragraphs(root, settings, month, signed_date)
    _fix_reception_header_body_gap(root)
    _push_reception_title_box_down(root)
    _widen_reception_title_clearance_gap(root)
    _compress_reception_blank_paragraph_spacing(root)
    _shrink_reception_remarks_blank_row(root)

    # The real template has multiple SEPARATE <w:tbl> elements — the
    # "Nous soussignons" signer table, the items table, the remarks
    # table, and a final signature-label row — not one table with extra
    # rows. The signature-label row is intentionally left untouched (pure
    # labels, same as daily_reception_screen.py's own repeating footer —
    # never filled with names).
    meals = _meals_for_month(month)
    quantities = _record_quantities(record, meals)

    for table in root.findall(".//w:tbl", _WORD_NS):
        rows = table.findall("w:tr", _WORD_NS)
        row_texts = ["".join(node.text or "" for node in row.findall(".//w:t", _WORD_NS)) for row in rows]

        meal_rows: list = []

        for index, row_text in enumerate(row_texts):
            normalized_row = _normalize_for_match(row_text)
            cells = rows[index].findall("w:tc", _WORD_NS)
            # The bottom signature-label row (Directeur / Gestionnaire /
            # Le prestataire de service, all 3 in ONE row) also contains
            # "GESTIONNAIRE"/"DIRECTEUR" once every cell's text is
            # concatenated — without this cell-count guard it would match
            # here too and overwrite that row's own "Directeur" label with
            # a name. Only the top "Nous soussignons" table's rows are the
            # real target: exactly 2 cells (name, role).
            if len(cells) == 2 and "GESTIONNAIRE" in normalized_row:
                if settings:
                    _set_empty_run_text(cells[0], (settings.gestionnaire or "").strip())
            elif len(cells) == 2 and "DIRECTEUR" in normalized_row:
                if settings:
                    _set_empty_run_text(cells[0], (settings.director or "").strip())
            elif "PETIT-DEJEUNER" in normalized_row:
                meal_rows.append(index)
            elif "DEJEUNER" in normalized_row:  # matches "Le déjeuner" but NOT "petit-déjeuner" (handled above first)
                meal_rows.append(index)
            elif "DINER" in normalized_row:
                meal_rows.append(index)
            elif "REMARQUES" in normalized_row and record.remarks.strip():
                if index + 1 < len(rows):
                    next_cells = rows[index + 1].findall("w:tc", _WORD_NS)
                    if next_cells:
                        _set_docx_text(next_cells[0], record.remarks.strip())

        # Fill the meal rows in the MONTH's own meal order. A month that
        # CONTAINS Ramadan serves five meal types (the three normal ones on
        # its ordinary days plus إفطار/سحور on its Ramadan days) while the
        # template prints only three rows — so the surplus meals get a cloned
        # row each. Filling by fixed label left both Ramadan quantities off
        # the official document entirely.
        if meal_rows:
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

            # Clone a row for every meal the template has no row for.
            last_row = rows[meal_rows[-1]]
            insert_at = list(table).index(last_row) + 1
            for position in range(len(meal_rows), len(meals)):
                clone = copy.deepcopy(last_row)
                cells = clone.findall("w:tc", _WORD_NS)
                if not cells:
                    continue
                _set_docx_text(cells[-1], str(quantities[position]))
                if len(cells) >= 2:
                    _set_docx_text(cells[1], _MEAL_DESIGNATION_FR[meals[position][0]])
                if len(cells) >= 3:
                    # N° d'article — keep the template's own numbering going.
                    _set_docx_text(cells[0], str(position + 1))
                table.insert(insert_at, clone)
                insert_at += 1


def _write_monthly_reception_docx(path: Path, month: str, record: MonthlyReceptionRecord, settings: Optional[SchoolSettings] = None) -> None:
    """Fill the real templets/المحضر الشهري لتسلم الخدمة.docx template."""
    template_path = _find_monthly_reception_template()
    if template_path is None:
        raise FileNotFoundError(_TEMPLATE_MISSING)

    register_docx_namespaces()
    path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(template_path, "r") as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                root = ET.fromstring(data)
                _fill_monthly_reception_document_xml(root, month, record, settings)
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
                    _blank_reception_header_dead_text(root)
                    _add_reception_header_reliable_text(root, academy, province, school_name)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)


# ── Main screen ──────────────────────────────────────────────────────────────

class MonthlyReceptionScreen(QWidget):
    """محضر تسليم الخدمة الشهري screen — 3 delivered-quantity fields
    prefilled from summed محاضر التسليم اليومية, remarks, save + export."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._build_ui()
        self._load_current_month()

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
        inner.addLayout(self._build_month_bar())
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

    def _build_month_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        combo_style = (
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:4px 8px; font-size:{FONT_BODY}px;"
        )

        row.addWidget(QLabel(_LBL_MONTH, styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))
        self._month_combo = QComboBox()
        self._month_combo.setMinimumHeight(36)
        self._month_combo.setMinimumWidth(130)
        for m in _ARABIC_MONTHS:
            self._month_combo.addItem(m)
        self._month_combo.setStyleSheet(combo_style)
        self._month_combo.currentIndexChanged.connect(self._generate)
        row.addWidget(self._month_combo)

        row.addWidget(QLabel(_LBL_YEAR, styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))
        self._year_combo = QComboBox()
        self._year_combo.setMinimumHeight(36)
        self._year_combo.setMinimumWidth(90)
        current_year = datetime.date.today().year
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_combo.addItem(str(y))
        self._year_combo.setStyleSheet(combo_style)
        self._year_combo.currentIndexChanged.connect(self._generate)
        row.addWidget(self._year_combo)

        this_month_btn = self._btn(_BTN_THIS_MONTH, COLOR_TEXT_PRIMARY)
        this_month_btn.clicked.connect(self._load_current_month)
        row.addWidget(this_month_btn)

        row.addStretch()

        recompute_btn = self._btn(_BTN_RECOMPUTE, COLOR_ACCENT, icon=_BTN_RECOMPUTE_ICON)
        recompute_btn.clicked.connect(self._recompute_from_daily_receptions)
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
        for meal_key, meal_label in _MEAL_ORDER + _RAMADAN_MEAL_ORDER:
            row_host = QWidget()
            row = QHBoxLayout(row_host)
            row.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(meal_label)
            lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px;")
            spin = QSpinBox()
            spin.setRange(0, 999999)
            spin.setMinimumHeight(32)
            spin.setMinimumWidth(120)
            spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            spin.setStyleSheet(
                f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:2px 8px;"
            )
            self._quantity_spins[meal_key] = spin
            row.addWidget(lbl, 1)
            row.addWidget(spin)
            self._quantity_rows[meal_key] = row_host
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

    # ── Month navigation / generate ─────────────────────────────────────────

    def _selected_month_str(self) -> str:
        year = self._year_combo.currentText()
        month = str(self._month_combo.currentIndex() + 1).zfill(2)
        return f"{year}-{month}"

    def _load_current_month(self) -> None:
        now = datetime.date.today()
        self._month_combo.blockSignals(True)
        self._year_combo.blockSignals(True)
        self._month_combo.setCurrentIndex(now.month - 1)
        self._year_combo.setCurrentText(str(now.year))
        self._month_combo.blockSignals(False)
        self._year_combo.blockSignals(False)
        self._generate()

    def _generate(self) -> None:
        """Load the saved record for this month, or prefill quantities
        from that month's daily reception records if none exists yet —
        never silently overwrites an already-saved record (use إعادة
        الحساب for that explicitly)."""
        month = self._selected_month_str()
        # Only meals this month actually served are editable — the Ramadan
        # pair appears only for a month the Ramadan period touches.
        active = {key for key, _l in _meals_for_month(month)}
        for meal_key, row_host in getattr(self, "_quantity_rows", {}).items():
            row_host.setVisible(meal_key in active)
        record = get_monthly_reception_record(month)
        if record is not None:
            self._quantity_spins[MEAL_FTOUR].setValue(record.ftour_qty)
            self._quantity_spins[MEAL_GHADA].setValue(record.ghada_qty)
            self._quantity_spins[MEAL_ASHA].setValue(record.asha_qty)
            self._quantity_spins[MEAL_IFTAR].setValue(record.ftour_ramadan_qty)
            self._quantity_spins[MEAL_SHOUR].setValue(record.shour_qty)
            self._remarks_edit.setPlainText(record.remarks)
        else:
            self._recompute_from_daily_receptions()
            self._remarks_edit.setPlainText("")

    def _recompute_from_daily_receptions(self) -> None:
        """Force-refill quantities from that month's saved daily reception
        records, overwriting whatever is currently in the spinboxes. Only
        triggered by an explicit user click when a saved record already
        exists — see _generate."""
        quantities = _quantities_from_daily_receptions(self._selected_month_str())
        for meal_key, spin in self._quantity_spins.items():
            spin.setValue(quantities[meal_key])

    # ── Save / export ────────────────────────────────────────────────────────

    def _current_record(self) -> MonthlyReceptionRecord:
        return MonthlyReceptionRecord(
            month=self._selected_month_str(),
            ftour_qty=self._quantity_spins[MEAL_FTOUR].value(),
            ghada_qty=self._quantity_spins[MEAL_GHADA].value(),
            asha_qty=self._quantity_spins[MEAL_ASHA].value(),
            ftour_ramadan_qty=self._quantity_spins[MEAL_IFTAR].value(),
            shour_qty=self._quantity_spins[MEAL_SHOUR].value(),
            remarks=self._remarks_edit.toPlainText().strip(),
        )

    def _on_save(self) -> None:
        try:
            save_monthly_reception_record(self._current_record())
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_export(self) -> None:
        export_format = ask_export_format(self)
        if export_format is None or export_format == "cancel":
            return

        month = self._selected_month_str()
        default_name = f"{_PDF_DEFAULT_NAME}_{month}"
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
            save_monthly_reception_record(record)
            settings = get_school_settings()
            if is_pdf:
                _write_monthly_reception_pdf(path, settings, month, record)
            else:
                _write_monthly_reception_docx(path, month, record, settings)
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_EXPORT_ERROR}\n{exc}")
