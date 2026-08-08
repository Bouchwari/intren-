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
from core.models import DailyReceptionRecord
from data.database import (
    get_daily_reception_record, get_day_contacts, get_school_settings,
    save_daily_reception_record,
)
from ui.batch_export import draw_placeholder_pdf_page
from ui.daily_contact_screen import (
    _normalize_template_name, _set_cell_text, _set_docx_text, _template_dirs,
    _WORD_NS, _W_NS, _XML_SPACE,
)
from ui.document_header import (
    ask_export_format, draw_official_pdf_footer, draw_official_pdf_header,
    register_docx_namespaces,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "محضر تسليم الخدمة اليومي"
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
_ROLES = ["مسير المصالح المادية والمالية", "مدير المؤسسة", "ممثل الشركة النائلة"]


def _quantities_from_contacts(date_str: str) -> Dict[str, int]:
    """Per-meal totals from that date's ورقة الاتصال — the default a fresh
    reception record starts from."""
    contacts = {c.meal_type: c for c in get_day_contacts(date_str)}
    return {
        meal_key: (contacts[meal_key].grand_total if meal_key in contacts else 0)
        for meal_key, _ in _MEAL_ORDER
    }


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


def _draw_reception_pdf_cell(
    painter: QPainter, rect: QRectF, *,
    background: str, border: str, text: str, text_color: str,
    size: int, bold: bool = False,
) -> None:
    painter.setPen(QPen(QColor(border), 1))
    painter.setBrush(QColor(background))
    painter.drawRect(rect)
    _draw_reception_pdf_text(
        painter, rect.adjusted(4, 2, -4, -2), text,
        size=size, color=text_color, bold=bold,
    )


def _draw_reception_pdf_page(
    painter: QPainter, page_w: float, page_h: float,
    settings, date_str: str, record: DailyReceptionRecord,
) -> None:
    """Draw one reception record onto an already-open page — same field
    order as templets/المحضر اليومي لتسلم الخدمة.docx: date, contractor,
    a 3-row meal/quantity table, remarks, then STEWARD/HEADMASTER/
    CONTRACTOR signatures. Shared by _write_reception_pdf (standalone
    file) and build_reception_pdf_page (يوم العمل's combined batch PDF)."""
    s = settings
    company = ((s.company_name if s else "") or (s.supplier_name if s else "")) or "—"
    display_date = date_str.replace("-", "/")

    margin = 38.0
    content_w = page_w - (margin * 2)

    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=margin, top=18.0,
        settings=settings, title=_TITLE,
    )

    meta_lines = [f"بتاريخ : {display_date}", f"الشركة القائمة : {company}"]
    for line in meta_lines:
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 24), line,
            size=11, color=COLOR_TEXT_PRIMARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
        )
        y += 28
    y += 12

    columns = ["الوجبة", "الوحدة", "الكمية"]
    col_widths = [content_w * 0.4, content_w * 0.3, content_w * 0.3]
    header_h = 32.0
    row_h = 38.0
    table_h = header_h + (row_h * len(_MEAL_ORDER))
    right = margin + content_w

    current_right = right
    for col_label, col_w in zip(columns, col_widths):
        rect = QRectF(current_right - col_w, y, col_w, header_h)
        _draw_reception_pdf_cell(
            painter, rect, background="white", border="#000000",
            text=col_label, text_color="#000000", size=11, bold=True,
        )
        current_right = rect.left()

    quantities = [record.ftour_qty, record.ghada_qty, record.asha_qty]
    row_y = y + header_h
    for (meal_key, meal_label), qty in zip(_MEAL_ORDER, quantities):
        values = [meal_label, "وحدة", str(qty)]
        current_right = right
        for index, (value, col_w) in enumerate(zip(values, col_widths)):
            rect = QRectF(current_right - col_w, row_y, col_w, row_h)
            _draw_reception_pdf_cell(
                painter, rect, background="white", border="#000000",
                text=value, text_color="#000000", size=11, bold=(index == 0),
            )
            current_right = rect.left()
        row_y += row_h
    y += table_h + 18

    if record.remarks.strip():
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 40),
            f"ملاحظات: {record.remarks.strip()}",
            size=10, color=COLOR_TEXT_SECONDARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
        )

    footer_h = 90.0
    footer_y = page_h - margin - footer_h + 6
    draw_official_pdf_footer(
        painter, page_width=page_w, margin=margin, top=footer_y,
        settings=settings, roles=_ROLES,
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


def _fill_reception_document_xml(root: ET.Element, date_str: str, record: DailyReceptionRecord) -> None:
    display_date = date_str.replace("-", "/")
    _set_mergefield_value(root, _MERGEFIELD_DATE, display_date)
    _set_mergefield_value(root, _MERGEFIELD_FTOUR, str(record.ftour_qty))
    _set_mergefield_value(root, _MERGEFIELD_GHADA, str(record.ghada_qty))

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
                    _set_docx_text(cells[-1], str(record.asha_qty))
            elif "Remarques" in row_text and record.remarks.strip():
                # The blank cell for remarks is the table's NEXT row, not
                # part of this one.
                if index + 1 < len(rows):
                    next_cells = rows[index + 1].findall("w:tc", _WORD_NS)
                    if next_cells:
                        _set_docx_text(next_cells[0], record.remarks.strip())


def _write_reception_docx(path: Path, date_str: str, record: DailyReceptionRecord) -> None:
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
                _fill_reception_document_xml(root, date_str, record)
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
            if is_pdf:
                settings = get_school_settings()
                _write_reception_pdf(path, settings, date_str, record)
            else:
                _write_reception_docx(path, date_str, record)
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_EXPORT_ERROR}\n{exc}")
