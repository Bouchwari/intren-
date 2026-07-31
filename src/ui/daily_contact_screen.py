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
    QApplication, QBoxLayout, QComboBox, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSizePolicy, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
)
from core.attendance_estimate import EstimateResult, estimate_attendance
from core.contact_counts import count_students, empty_counts
from core.models import DailyContact
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header
from data.database import (
    get_day_contacts,
    get_all_students,
    get_daily_contact_document_number_draft,
    get_next_daily_contact_document_number,
    get_recent_contacts,
    get_recent_daily_contact_documents,
    get_school_settings,
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
_BTN_LOAD       = "تحميل اليوم"
_BTN_SAVE       = "💾  حفظ وتسجيل"
_LBL_DATE       = "التاريخ:"
_LBL_NUMBER     = "رقم:"
_LBL_ACTIONS    = "الإجراء"
_LBL_DOCUMENT   = "بيانات الوثيقة"
_LBL_NAVIGATION = "التنقل"
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
_BTN_EXPORT_DOC = "🖨  طباعة وتسجيل"
_DOCX_DIALOG_TITLE = "تحميل ورقة الاتصال اليومية"
_DOCX_DEFAULT_NAME = "ورقة_الاتصال_اليومية"
_DOCX_SAVED_OK = "تم تحميل ورقة الاتصال اليومية بنجاح."
_DOCX_TEMPLATE_MISSING = "تعذر العثور على نموذج ورقة الاتصال اليومية."
_DOCX_SAVE_ERROR = "تعذر تحميل ورقة الاتصال اليومية:"
_BTN_EXPORT_PDF = "📄  تصدير PDF"
_PDF_DIALOG_TITLE = "تصدير ورقة الاتصال اليومية"
_PDF_DEFAULT_NAME = "ورقة_الاتصال_اليومية"
_PDF_FILTER = "PDF (*.pdf)"
_PDF_SAVED_OK = "تم تصدير ورقة الاتصال اليومية بنجاح."
_PDF_SAVE_ERROR = "تعذر تصدير ورقة الاتصال اليومية:"
_CONTACT_TEMPLATE_FILE = "ورقة الاتصال  اليومية.docx"
_WORD_FILTER = "Word (*.docx)"

# Maps DB meal_type key to display label (using MEAL_LABELS from settings)
_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]

# Card accent colors per meal
_MEAL_COLORS = {
    MEAL_FTOUR: "#f59e0b",   # amber
    MEAL_GHADA: COLOR_ACCENT,
    MEAL_ASHA:  "#7c3aed",   # purple
}
_PAGE_BG = "#f5f5f0"
_PANEL_BG = "#ffffff"
_PANEL_BORDER = "#dddccd"
_INK = "#5A5A40"
_HISTORY_COLUMN_WIDTHS = [100, 100, 92, 86, 86, 86, 92, 128]
_HISTORY_DATE_COLUMN = 1
_ACTION_LABELS = {
    "save": "حفظ",
    "print": "طباعة",
}
_MONTH_NAMES = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]
_WEEKDAY_HEADERS = ["ح", "ن", "ث", "ر", "خ", "ج", "س"]
_BTN_BACK = "رجوع"
_BTN_APPLY = "تطبيق"
_MODE_MANUAL = "إدخال يدوي"
_MODE_AUTO = "توليد تلقائي"
_MODE_MANUAL_LABEL = "وضع: إدخال يدوي 📝"
_MODE_AUTO_LABEL = "وضع: توليد تلقائي 🤖"
_TOAST_MANUAL = "تم التحويل إلى الإدخال اليدوي — يمكنك تعديل الأرقام"
_TOAST_AUTO = "اضغط تحميل اليوم لتوليد الأرقام تلقائياً"
_TOAST_NO_STUDENTS = "لا يوجد تلاميذ في اللائحة"
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
) -> None:
    template_path = _find_contact_template()
    if template_path is None:
        raise FileNotFoundError(_DOCX_TEMPLATE_MISSING)

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
                )
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


def _fill_contact_header_xml(
    root: ET.Element,
    *,
    academy: str,
    province: str,
    school_name: str,
) -> None:
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
            header_index += 1


def _fill_contact_document_xml(
    root: ET.Element,
    display_date: str,
    contact_by_meal: Dict[str, DailyContact],
    *,
    document_number: str,
    place: str,
) -> None:
    number_text = document_number.strip() or "...."
    place_text = place.strip() or "..............."
    for paragraph in root.findall(".//w:p", _WORD_NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS)).strip()
        if text.startswith("ورقة الاتصال اليومية"):
            _set_docx_text(paragraph, f"ورقة الاتصال اليومية  رقم: {number_text} ليوم : {display_date}")
        elif text.startswith("حرر ب"):
            _set_docx_text(paragraph, f"حرر ب{place_text} بتاريخ {display_date}")

    tables = root.findall(".//w:tbl", _WORD_NS)
    if not tables:
        return
    rows = tables[0].findall("./w:tr", _WORD_NS)
    if len(rows) < 8:
        return

    primary_cells = rows[3].findall("./w:tc", _WORD_NS)
    collegial_cells = rows[4].findall("./w:tc", _WORD_NS)
    qualifying_cells = rows[5].findall("./w:tc", _WORD_NS)
    monitors_cells = rows[6].findall("./w:tc", _WORD_NS)
    total_cells = rows[7].findall("./w:tc", _WORD_NS)

    for meal_index, (meal_key, _) in enumerate(_MEAL_ORDER):
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
    """Render the daily contact sheet as an official PDF, using the same
    header/footer helpers already proven on the meal program PDF export.
    academy/province/school_name are not accepted here (unlike the DOCX
    writer) because draw_official_pdf_header reads them straight off the
    SchoolSettings row instead of taking them as separate strings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    contact_by_meal = {contact.meal_type: contact for contact in contacts}
    display_date = _format_doc_date(date_str)
    place_text = place.strip() or "..............."

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
        _draw_contact_pdf_text(
            painter,
            QRectF(margin, table_y, content_w, 18),
            f"حرر ب{place_text} بتاريخ {display_date}",
            size=10,
            color=COLOR_TEXT_SECONDARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
        )
        table_y += 24

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
        row_h = (table_h - header_rows_h) / n_data_rows
        label_w = 130.0
        meal_w = (table_w - label_w) / len(_MEAL_ORDER)
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
        for _, meal_label in _MEAL_ORDER:
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
        for _ in _MEAL_ORDER:
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
            for meal_key, _ in _MEAL_ORDER:
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
        for meal_key, _ in _MEAL_ORDER:
            contact = contact_by_meal.get(meal_key) or DailyContact(date="", meal_type=meal_key)
            rect = QRectF(current_right - meal_w, total_y, meal_w, row_h)
            _draw_contact_pdf_cell(
                painter, rect,
                background="#F8F9FA", border=COLOR_BORDER,
                text=str(contact.grand_total), text_color=COLOR_TEXT_PRIMARY, size=11, bold=True,
            )
            current_right = rect.left()

        footer_y = page_h - margin - footer_h + 6
        # WARDEN + HEADMASTER — the signers documents.md lists for contact_sheet.
        draw_official_pdf_footer(
            painter,
            page_width=page_w,
            margin=margin,
            top=footer_y,
            settings=settings,
            roles=["الحارس العام للداخلية", "مدير المؤسسة"],
        )
    finally:
        painter.end()


def _spin_style(read_only: bool = False) -> str:
    background = "#f5f5f5" if read_only else "white"
    color = "#64748b" if read_only else "#000000"
    return (
        "QSpinBox {"
        "width:55px; height:26px; font-size:13px;"
        "padding:2px 4px; text-align:center;"
        "border:1px solid #ccc; border-radius:4px;"
        "box-sizing:border-box;"
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


class _CalendarDayButton(QPushButton):
    """Circular day cell with hover, selected state, and today dot."""

    def __init__(self, date: QDate, selected: bool, parent: QWidget | None = None) -> None:
        super().__init__(str(date.day()), parent)
        self._date = date
        self._selected = selected
        self._hovered = False
        self._today = date == QDate.currentDate()
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setStyleSheet("border:none; background:transparent;")

    @property
    def date(self) -> QDate:
        return self._date

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        circle = QRectF(0, 0, 36, 36)
        if self._selected:
            painter.setBrush(QColor("#e53935"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(circle)
        elif self._hovered:
            painter.setBrush(QColor("#fce4e4"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(circle)

        painter.setPen(QColor("white" if self._selected else "#111111"))
        painter.drawText(QRectF(0, 3, 36, 23), Qt.AlignmentFlag.AlignCenter, self.text())

        if self._today:
            painter.setBrush(QColor("white" if self._selected else "#e53935"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(16, 29, 4, 4))


class _CalendarPopup(QFrame):
    """Small custom Arabic calendar popup for _DateInput."""

    dateSelected = Signal(QDate)

    def __init__(self, selected_date: QDate, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("contactCalendarPopup")
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setFixedWidth(300)
        self._draft_date = selected_date if selected_date.isValid() else QDate.currentDate()
        self._day_buttons: list[_CalendarDayButton] = []
        self._building = False

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 38))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet("""
            QFrame#contactCalendarPopup {
                background: white;
                border-radius: 12px;
                padding: 16px;
            }
            QComboBox {
                border-radius: 20px;
                padding: 6px 14px;
                border: 1px solid #ddd;
                font-size: 14px;
                background: white;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QLabel#weekdayHeader {
                color: #999;
                font-size: 12px;
            }
            QPushButton#backButton {
                border: 1px solid #ccc;
                background: white;
                border-radius: 20px;
                padding: 8px 24px;
                color: #333;
            }
            QPushButton#applyButton {
                border: none;
                background: #1a73e8;
                color: white;
                border-radius: 20px;
                padding: 8px 24px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._month_combo = QComboBox()
        self._month_combo.addItems(_MONTH_NAMES)
        self._year_combo = QComboBox()
        self._year_combo.addItems([str(year) for year in range(2000, 2101)])
        top.addWidget(self._month_combo, 1)
        top.addWidget(self._year_combo, 1)
        root.addLayout(top)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(4)
        root.addLayout(self._grid)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        back_btn = QPushButton(_BTN_BACK)
        back_btn.setObjectName("backButton")
        apply_btn = QPushButton(_BTN_APPLY)
        apply_btn.setObjectName("applyButton")
        back_btn.clicked.connect(self.close)
        apply_btn.clicked.connect(self._apply)
        footer.addWidget(back_btn)
        footer.addStretch()
        footer.addWidget(apply_btn)
        root.addLayout(footer)

        self._month_combo.currentIndexChanged.connect(self._on_month_changed)
        self._year_combo.currentIndexChanged.connect(self._on_year_changed)
        self._sync_selects()
        self._build_grid()

    def showEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        super().showEvent(event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.MouseButtonPress:
            if self._month_combo.view().isVisible() or self._year_combo.view().isVisible():
                return super().eventFilter(obj, event)
            global_pos = event.globalPosition().toPoint()
            if not self.geometry().contains(global_pos):
                self.close()
        return super().eventFilter(obj, event)

    def _sync_selects(self) -> None:
        self._building = True
        self._month_combo.setCurrentIndex(self._draft_date.month() - 1)
        year_index = max(0, self._draft_date.year() - 2000)
        self._year_combo.setCurrentIndex(min(year_index, self._year_combo.count() - 1))
        self._building = False

    def _on_month_changed(self, index: int) -> None:
        if self._building or index < 0:
            return
        self._set_year_month(self._draft_date.year(), index + 1)

    def _on_year_changed(self, index: int) -> None:
        if self._building or index < 0:
            return
        self._set_year_month(2000 + index, self._draft_date.month())

    def _set_year_month(self, year: int, month: int) -> None:
        first_day = QDate(year, month, 1)
        day = min(self._draft_date.day(), first_day.daysInMonth())
        self._draft_date = QDate(year, month, day)
        self._build_grid()

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_grid(self) -> None:
        self._clear_grid()
        self._day_buttons.clear()

        for col, text in enumerate(_WEEKDAY_HEADERS):
            label = QLabel(text)
            label.setObjectName("weekdayHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(label, 0, col)

        year = self._draft_date.year()
        month = self._draft_date.month()
        first_day = QDate(year, month, 1)
        start_col = first_day.dayOfWeek() % 7
        for day in range(1, first_day.daysInMonth() + 1):
            date = QDate(year, month, day)
            position = start_col + day - 1
            row = (position // 7) + 1
            col = position % 7
            button = _CalendarDayButton(date, date == self._draft_date)
            button.clicked.connect(lambda checked=False, btn=button: self._select_day(btn.date))
            self._day_buttons.append(button)
            self._grid.addWidget(button, row, col)

    def _select_day(self, date: QDate) -> None:
        self._draft_date = date
        for button in self._day_buttons:
            button.set_selected(button.date == date)

    def _apply(self) -> None:
        self.dateSelected.emit(self._draft_date)
        self.close()


class _DateInput(QLineEdit):
    """Read-only date input that opens the custom calendar popup."""

    dateChanged = Signal(QDate)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._date = QDate.currentDate()
        self._popup: _CalendarPopup | None = None
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self._date.toString("dd-MM-yyyy"))

    def date(self) -> QDate:
        return self._date

    def setDate(self, date: QDate) -> None:
        if not date.isValid() or date == self._date:
            return
        self._date = date
        self.setText(date.toString("dd-MM-yyyy"))
        self.dateChanged.emit(date)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self._show_calendar()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._show_calendar()
            return
        super().keyPressEvent(event)

    def _show_calendar(self) -> None:
        if self._popup is not None:
            self._popup.close()
        self._popup = _CalendarPopup(self._date, self)
        self._popup.dateSelected.connect(self.setDate)
        below_right = self.mapToGlobal(QPoint(self.width(), self.height() + 6))
        x = below_right.x() - self._popup.width()
        y = below_right.y()
        self._popup.move(max(0, x), y)
        self._popup.show()
        self._popup.raise_()


class _ModeToggle(QFrame):
    """Compact two-state switch for manual versus generated counts."""

    modeChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auto = False
        self.setObjectName("modeToggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)
        self.setMinimumWidth(265)
        self.setStyleSheet(f"""
            QFrame#modeToggle {{
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
        self._state_label.setStyleSheet(f"color:{_INK}; font-weight:bold; font-size:11px;")
        root.addWidget(self._state_label)

        row = QHBoxLayout()
        row.setDirection(QBoxLayout.Direction.LeftToRight)
        row.setSpacing(6)
        self._manual_label = QLabel(_MODE_MANUAL)
        self._track_label = QLabel()
        self._auto_label = QLabel(_MODE_AUTO)
        for label in (self._manual_label, self._track_label, self._auto_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self._manual_label)
        row.addWidget(self._track_label)
        row.addWidget(self._auto_label)
        root.addLayout(row)
        self._update_style()

    def is_auto(self) -> bool:
        return self._auto

    def set_auto(self, auto: bool) -> None:
        if self._auto == auto:
            return
        self._auto = auto
        self._update_style()
        self.modeChanged.emit(auto)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.set_auto(not self._auto)
        super().mousePressEvent(event)

    def _update_style(self) -> None:
        pill = "border-radius:10px; padding:3px 8px; font-size:11px; font-weight:bold;"
        active = "background:#1fa37a; color:white;"
        inactive = "background:#eef7f2; color:#5A5A40;"
        self._state_label.setText(_MODE_AUTO_LABEL if self._auto else _MODE_MANUAL_LABEL)
        self._manual_label.setStyleSheet(pill + (inactive if self._auto else active))
        self._auto_label.setStyleSheet(pill + (active if self._auto else inactive))
        self._track_label.setText("────●" if self._auto else "●────")
        self._track_label.setStyleSheet("color:#5A5A40; font-size:13px; font-weight:bold;")


# ── Meal card widget ──────────────────────────────────────────────────────────

class _MealCard(QGroupBox):
    """Compact form card for one meal's beneficiary counts."""

    def __init__(self, meal_key: str, meal_label: str, color: str) -> None:
        super().__init__(meal_label)
        self._meal_key = meal_key
        self._color = color
        self._read_only = False
        self.setMinimumWidth(335)
        self.setMaximumWidth(360)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-size: 15px; font-weight: bold;
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
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
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
                f"color: {self._color}; font-weight: bold; font-size: 14px;"
            )

        rows = [
            (_LBL_PRIMARY, self._pg, self._pc, self._pt_lbl),
            (_LBL_COLLEGIAL, self._cg, self._cc, self._ct_lbl),
            (_LBL_QUALIFYING, self._qg, self._qc, self._qt_lbl),
            (_LBL_MONITORS, self._mo, self._mc, self._mt_lbl),
        ]
        for row, (label, full_spin, lunch_spin, total_label) in enumerate(rows):
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
        gt_title.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:13px;")
        self._gt_lbl.setStyleSheet(
            f"color:white; background:{self._color}; font-weight:bold; font-size:15px;"
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
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;")
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
        row.setDirection(QBoxLayout.Direction.RightToLeft)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        actions = self._toolbar_group(_LBL_ACTIONS)
        actions_row = QHBoxLayout()
        actions_row.setDirection(QBoxLayout.Direction.RightToLeft)
        actions_row.setSpacing(8)
        save_btn = self._btn(_BTN_SAVE, COLOR_SUCCESS)
        save_btn.clicked.connect(self._on_save)
        export_btn = self._btn(_BTN_EXPORT_DOC, _INK)
        export_btn.clicked.connect(self._on_export_docx)
        export_pdf_btn = self._btn(_BTN_EXPORT_PDF, _INK)
        export_pdf_btn.clicked.connect(self._on_export_pdf)
        actions_row.addWidget(save_btn)
        actions_row.addWidget(export_btn)
        actions_row.addWidget(export_pdf_btn)
        actions.layout().addLayout(actions_row)

        document = self._toolbar_group(_LBL_DOCUMENT)
        document.setMinimumWidth(390)
        fields = QHBoxLayout()
        fields.setDirection(QBoxLayout.Direction.RightToLeft)
        fields.setSpacing(8)

        self._date_edit = _DateInput()
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setMinimumHeight(36)
        self._date_edit.setMinimumWidth(170)
        self._date_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            "padding:4px 10px; font-size:13px;"
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
            "padding:4px 10px; font-size:13px;"
        )
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFixedHeight(28)
        separator.setStyleSheet(f"color:{_PANEL_BORDER};")
        fields.addWidget(QLabel(_LBL_DATE, styleSheet=f"font-size:13px; color:{COLOR_TEXT_PRIMARY};"))
        fields.addWidget(self._date_edit)
        fields.addWidget(separator)
        fields.addWidget(QLabel(_LBL_NUMBER, styleSheet=f"font-size:13px; color:{COLOR_TEXT_PRIMARY};"))
        fields.addWidget(self._number_edit)
        document.layout().addLayout(fields)

        navigation = self._toolbar_group(_LBL_NAVIGATION)
        automation_row = QHBoxLayout()
        automation_row.setDirection(QBoxLayout.Direction.RightToLeft)
        automation_row.setSpacing(8)
        load_btn = self._btn(_BTN_LOAD, COLOR_ACCENT, compact=True)
        load_btn.setMinimumWidth(112)
        self._mode_toggle = _ModeToggle()
        automation_row.addWidget(load_btn)
        automation_row.addWidget(self._mode_toggle)

        nav_row = QHBoxLayout()
        nav_row.setDirection(QBoxLayout.Direction.RightToLeft)
        nav_row.setSpacing(10)
        today_btn = self._btn(_BTN_TODAY, _INK, compact=True)
        prev_btn = self._btn(_BTN_PREV, _INK, compact=True)
        next_btn = self._btn(_BTN_NEXT, _INK, compact=True)
        for button, width in (
            (next_btn, 112),
            (prev_btn, 122),
            (today_btn, 72),
        ):
            button.setMinimumWidth(width)

        today_btn.clicked.connect(self._load_today)
        prev_btn.clicked.connect(self._go_prev)
        next_btn.clicked.connect(self._go_next)
        load_btn.clicked.connect(self._on_load_today_clicked)
        self._mode_toggle.modeChanged.connect(self._on_mode_changed)

        nav_row.addWidget(prev_btn)
        nav_row.addWidget(today_btn)
        nav_row.addWidget(next_btn)
        navigation.layout().addLayout(automation_row)
        navigation.layout().addLayout(nav_row)

        row.addWidget(actions, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(document, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(navigation, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)

        self._sync_document_number(force=True)
        self._date_edit.dateChanged.connect(self._sync_document_number)
        self._number_edit.textChanged.connect(self._remember_document_number)
        return panel

    def _build_estimate_note(self) -> QLabel:
        label = QLabel("")
        label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color:{_INK}; background:#fbf6e3; border:1px solid #e6d68a;"
            "border-radius:10px; padding:6px 12px; font-size:12px;"
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
        label.setStyleSheet(f"color:{_INK}; font-weight:bold; font-size:12px; border:none; background:transparent;")
        layout.addWidget(label)
        return frame

    def _btn(self, label: str, color: str, *, compact: bool = False) -> QPushButton:
        b = QPushButton(label)
        b.setMinimumHeight(36)
        b.setStyleSheet(
            f"background:{color}; color:white; border-radius:12px;"
            f"padding:0 {'10' if compact else '14'}px; font-size:13px;"
        )
        return b

    def _build_cards_row(self) -> QGridLayout:
        row = QGridLayout()
        row.setSpacing(12)
        row.setHorizontalSpacing(12)
        row.setVerticalSpacing(12)
        row.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        for index, (meal_key, meal_label) in enumerate(_MEAL_ORDER):
            card = _MealCard(meal_key, meal_label, _MEAL_COLORS[meal_key])
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
                font-size:13px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
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
        self._history_table.horizontalHeader().setStretchLastSection(False)
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(_HISTORY_COLUMN_WIDTHS):
            self._history_table.setColumnWidth(col, width)
        self._history_table.setMinimumHeight(206)
        self._history_table.setMaximumHeight(210)
        self._history_table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {_PANEL_BORDER}; border-radius:12px;
                background:white; alternate-background-color:#f8fafc;
                font-size:12px;
            }}
            QHeaderView::section {{
                background:#E4E4D7; color:{_INK};
                padding:4px 8px; border:none;
                border-bottom:1px solid {_PANEL_BORDER};
                font-weight:bold; font-size:12px;
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

    def _current_contacts(self) -> List[DailyContact]:
        date_str = self._selected_date_str()
        return [card.to_contact(date_str) for _, card in self._cards.items()]

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

    def _generate_today_counts(self) -> None:
        students = get_all_students()
        if not students:
            self._apply_generated_counts(empty_counts())
            self._set_estimate_note(None)
            self._show_toast(_TOAST_NO_STUDENTS)
            return

        active_roster = self._flatten_counts(count_students(students))
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

    def _show_toast(self, message: str) -> None:
        parent = self.window() or self
        if self._toast is not None:
            self._toast.deleteLater()
        toast = QLabel(message, parent)
        toast.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setStyleSheet(
            "background:#323232; color:white; border-radius:8px;"
            "padding:10px 20px; font-size:13px;"
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
                    int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                )
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

    def _on_export_docx(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            _DOCX_DIALOG_TITLE,
            self._default_docx_name(),
            _WORD_FILTER,
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".docx":
            path = path.with_suffix(".docx")

        try:
            settings = get_school_settings()
            date_str = self._selected_date_str()
            contacts = self._current_contacts()
            document_number = self._document_number_int()
            _write_daily_contact_docx(
                path,
                date_str,
                contacts,
                document_number=str(document_number),
                place=settings.city if settings else "",
                academy=settings.aref if settings else "",
                province=settings.direction_provinciale if settings else "",
                school_name=settings.school_name if settings else "",
            )
            for contact in contacts:
                save_daily_contact(contact)
            record_daily_contact_document(date_str, document_number, "print", contacts, str(path))
            self._advance_document_number(document_number)
            self._refresh_history()
            QMessageBox.information(self, "تم", _DOCX_SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_DOCX_SAVE_ERROR}\n{exc}")

    def _on_export_pdf(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            _PDF_DIALOG_TITLE,
            self._default_pdf_name(),
            _PDF_FILTER,
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        try:
            settings = get_school_settings()
            date_str = self._selected_date_str()
            contacts = self._current_contacts()
            document_number = self._document_number_int()
            _write_daily_contact_pdf(
                path,
                date_str,
                contacts,
                document_number=str(document_number),
                place=settings.city if settings else "",
            )
            for contact in contacts:
                save_daily_contact(contact)
            record_daily_contact_document(date_str, document_number, "print", contacts, str(path))
            self._advance_document_number(document_number)
            self._refresh_history()
            QMessageBox.information(self, "تم", _PDF_SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_PDF_SAVE_ERROR}\n{exc}")

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
