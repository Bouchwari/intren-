"""
src/ui/daily_report_screen.py
Daily report (التقرير اليومي) — auto-generated attendance/absence summary,
plus the مسير's inspection checklist (hygiene / meal quality / building) and
notes, matching the real accepted form.
"""
import datetime
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
)
from core.models import DailyContact, DailyAbsence, DailyReport
from data.database import (
    get_day_contacts, get_day_absences,
    get_dates_with_data, get_daily_report, get_school_settings,
    save_daily_report,
)
from ui.daily_contact_screen import (
    _academy_line, _normalize_template_name, _province_line,
    _set_cell_text, _set_docx_text, _template_dirs, _WORD_NS,
)

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "التقرير اليومي"
_SUBTITLE       = "التقرير اليومي للمصالح المادية والمالية"
_BTN_PREV       = "→  اليوم السابق"
_BTN_NEXT       = "اليوم التالي  ←"
_BTN_TODAY      = "اليوم"
_BTN_GENERATE   = "🔄  توليد التقرير"
_BTN_SAVE_NOTES = "💾  حفظ الملاحظات"
_LBL_DATE       = "التاريخ:"
_LBL_NOTES      = "ملاحظات المسير"
_NOTES_HINT     = "أدخل ملاحظاتك هنا..."
_NO_DATA        = "لا توجد بيانات لهذا اليوم.\nأدخل بيانات ورقة الاتصال أو الغياب أولاً."
_SAVED_OK       = "تم حفظ التقرير بنجاح."
_BTN_SAVE_REPORT = "💾  حفظ التقرير"
_BTN_EXPORT     = "📄  تصدير"
_DOCX_DIALOG_TITLE = "تصدير التقرير اليومي"
_DOCX_DEFAULT_NAME = "التقرير_اليومي"
_WORD_FILTER    = "Word (*.docx)"
_DOCX_SAVED_OK  = "تم تصدير التقرير اليومي بنجاح."
_DOCX_SAVE_ERROR = "تعذر تصدير التقرير اليومي:"
_DOCX_TEMPLATE_MISSING = "تعذر العثور على نموذج التقرير اليومي."

_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]

# ── Inspection checklist — item order and exact wording match the real
# accepted form (templets/التقرير اليومي للمصالح المادية والمالية.docx),
# not the ministry guide's blank annex. Each tuple is (DailyReport field
# name, Arabic item label). Index into the matching scale = rating value.

_NOT_RATED = "—"
_HYGIENE_SCALE = ["ضعيفة", "ناقصة", "متوسطة", "لا بأس بها", "حسنة", "جيدة"]
_THREE_SCALE = ["ناقصة", "لابأس بها", "جيدة"]

_LBL_HYGIENE = "1 — تتبع النظافة"
_HYGIENE_ITEMS: List[Tuple[str, str]] = [
    ("hygiene_staff", "نظافة وهندام المستخدمين"),
    ("hygiene_utensils", "نظافة الأواني وأدوات العمل"),
    ("hygiene_dining_hall", "نظافة أرضيات وأسطح قاعة الأكل"),
    ("hygiene_kitchen", "نظافة أرضيات وأسطح المطعم"),
    ("hygiene_storage", "نظافة المخازن والثلاجات"),
    ("hygiene_waste", "طريقة التخلص من بقايا الطعام"),
    ("hygiene_dorms", "نظافة المراقد"),
]

_LBL_BENEFICIARIES = "2 — تتبع المستفيدين من خدمة المطعمة"
_LBL_EXPECTED = "العدد المقترح"
_LBL_PRESENT  = "الحاضرون فعليا"

_LBL_QUALITY = "3 — تتبع الوجبات المقدمة"
_QUALITY_ITEMS: List[Tuple[str, str]] = [
    ("quality_supplies", "جودة السلع والتزود"),
    ("quality_storage", "ظروف التخزين"),
    ("quality_program", "احترام البرنامج الغذائي"),
    ("quality_quantities", "احترام الكميات المحددة"),
    ("quality_sample_kept", "الاحتفاظ بالوجبة الشاهد"),
    ("quality_prep", "ظروف وطريقة التحضير"),
    ("quality_serving", "طريقة تقديم الوجبات"),
]

_LBL_BUILDING = "4 — مراقبة وصيانة التجهيزات والبنايات"
_BUILDING_ITEMS: List[Tuple[str, str]] = [
    ("building_condition", "حالة وصيانة البنايات"),
    ("equipment_condition", "حالة التجهيزات والأدوات"),
]

# Report table columns
_COL_MEAL     = "الوجبة"
_COL_SECTOR   = "القطاع"
_COL_GRANTED  = "ممنوح"
_COL_PAYING   = "مؤد"
_COL_COMPL    = "متمم"
_COL_TOTAL    = "المجموع"
_HEADERS = [_COL_MEAL, _COL_SECTOR, _COL_GRANTED, _COL_PAYING, _COL_COMPL, _COL_TOTAL]

# Sector row labels within each meal
_SECTOR_COLLEGIAL  = "إعدادي"
_SECTOR_QUALIFYING = "تأهيلي"
_SECTOR_MONITORS   = "معلمو الداخلية"
_SECTOR_TOTAL      = "مجموع الوجبة"
_GRAND_TOTAL       = "الإجمالي العام"


def _cell(text: str, bold: bool = False, align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
          bg: str = "", fg: str = "") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    f = QFont()
    f.setBold(bold)
    item.setFont(f)
    if bg:
        from PySide6.QtGui import QColor
        item.setBackground(QColor(bg))
    if fg:
        from PySide6.QtGui import QColor
        item.setForeground(QColor(fg))
    return item


def _section_title(text: str, color: str = "") -> QLabel:
    lbl = QLabel(text)
    f = QFont(); f.setPointSize(13); f.setBold(True)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color or COLOR_TEXT_PRIMARY}; padding: 4px 0;")
    return lbl


# ── Word export — fills the real template exactly ─────────────────────────────
# The template prints two identical copies on one page (نظيرين); every helper
# below matches by content/structure rather than fixed index, so it fills
# both copies without needing to know there even are two.

def _find_daily_report_template() -> Path | None:
    for directory in _template_dirs():
        if not directory.exists():
            continue
        for candidate in directory.glob("*.docx"):
            if "التقريراليوميللمصالحالماديةوالمالية" in _normalize_template_name(candidate.stem):
                return candidate
    return None


def _row_cells(row: ET.Element) -> List[ET.Element]:
    return row.findall("./w:tc", _WORD_NS)


def _mark_rating(cells: List[ET.Element], rating_range: range, rating: int) -> None:
    """Clear a block of rating cells, then mark the one matching `rating`
    (an index into the scale) with 'x'. rating=-1 (not rated) clears all."""
    for i in rating_range:
        if i >= len(cells):
            continue
        _set_cell_text(cells[i], "x" if (i - rating_range.start) == rating else "")


def _fill_daily_report_document_xml(
    root: ET.Element,
    *,
    academy: str,
    province: str,
    school_name: str,
    display_date: str,
    report: DailyReport,
) -> None:
    paragraphs = root.findall(".//w:p", _WORD_NS)
    n = len(paragraphs)
    i = 0
    while i < n:
        paragraph = paragraphs[i]
        if paragraph.findall(".//w:p", _WORD_NS):
            # Wrapper paragraph (e.g. a floating text box) — its .//w:t
            # search would pick up every nested paragraph's text combined,
            # so leave it alone and process the real nested paragraphs
            # individually as this loop reaches them.
            i += 1
            continue
        text = "".join(nd.text or "" for nd in paragraph.findall(".//w:t", _WORD_NS)).strip()
        if text.startswith("الأكاديمية") and i + 2 < n:
            _set_docx_text(paragraph, _academy_line(academy))
            _set_docx_text(paragraphs[i + 1], _province_line(province))
            _set_docx_text(paragraphs[i + 2], school_name.strip() or "اسم المؤسسة")
            i += 3
            continue
        if "ليوم:" in text:
            # NOT a bare "ليوم" check — that substring also occurs inside
            # "اليومي" in the document's own title ("التقرير اليومي..."),
            # which would wrongly overwrite the title paragraphs too.
            _set_docx_text(paragraph, f" الخاص بتتبع القسم الداخلي ليوم:  {display_date}")
        elif re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
            _set_docx_text(paragraph, display_date)
        elif "ملاحظات عامة واقتراحات" in text and report.notes.strip():
            for j in range(i + 1, min(i + 6, n)):
                candidate = paragraphs[j]
                candidate_text = "".join(
                    nd.text or "" for nd in candidate.findall(".//w:t", _WORD_NS)
                ).strip()
                if not candidate_text:
                    _set_docx_text(candidate, report.notes.strip())
                    break
        i += 1

    hygiene_ratings = [getattr(report, field) for field, _ in _HYGIENE_ITEMS]
    quality_ratings = [getattr(report, field) for field, _ in _QUALITY_ITEMS]
    building_ratings = [getattr(report, field) for field, _ in _BUILDING_ITEMS]
    beneficiary_rows = [
        (getattr(report, f"{key}_present"), getattr(report, f"{key}_expected"))
        for key, _ in _MEAL_ORDER
    ]

    for tbl in root.findall(".//w:tbl", _WORD_NS):
        rows = tbl.findall("./w:tr", _WORD_NS)
        if len(rows) < 2:
            continue
        header = tuple(
            "".join(nd.text or "" for nd in c.findall(".//w:t", _WORD_NS)).strip()
            for c in _row_cells(rows[0])
        )
        if not header:
            continue

        if header[0] == "ضعيفة":
            for row, rating in zip(rows[1:], hygiene_ratings):
                _mark_rating(_row_cells(row), range(0, 6), rating)

        elif header[0] == "ملاحظات" and len(header) >= 2 and header[1] == "الحاضرون فعليا":
            for row, (present, expected) in zip(rows[1:], beneficiary_rows):
                cells = _row_cells(row)
                if len(cells) >= 3:
                    _set_cell_text(cells[1], present)
                    _set_cell_text(cells[2], expected)

        elif header[0] == "ملاحظات" and len(rows) - 1 == len(_QUALITY_ITEMS):
            for row, rating in zip(rows[1:], quality_ratings):
                _mark_rating(_row_cells(row), range(1, 4), rating)

        elif header[0] == "ملاحظات" and len(rows) - 1 == len(_BUILDING_ITEMS):
            for row, rating in zip(rows[1:], building_ratings):
                _mark_rating(_row_cells(row), range(1, 4), rating)


def _write_daily_report_docx(
    path: Path,
    settings,
    date_str: str,
    report: DailyReport,
) -> None:
    """Fill the real daily-report template (templets/التقرير اليومي
    للمصالح المادية والمالية.docx) — the form the directorate accepts,
    printed in two identical copies on one page."""
    template_path = _find_daily_report_template()
    if template_path is None:
        raise FileNotFoundError(_DOCX_TEMPLATE_MISSING)

    path.parent.mkdir(parents=True, exist_ok=True)
    s = settings
    academy = s.aref if s else ""
    province = s.direction_provinciale if s else ""
    school_name = s.school_name if s else ""
    display_date = date_str.replace("-", "/")

    with ZipFile(template_path, "r") as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                root = ET.fromstring(data)
                _fill_daily_report_document_xml(
                    root,
                    academy=academy,
                    province=province,
                    school_name=school_name,
                    display_date=display_date,
                    report=report,
                )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(item, data)


class DailyReportScreen(QWidget):
    """Daily report screen — auto-generated from contact + absence data."""

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
        inner.addWidget(self._build_report_card())
        inner.addWidget(self._build_checklist_card())
        inner.addWidget(self._build_notes_section())
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
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;")
        col.addWidget(title)
        col.addWidget(sub)
        return col

    def _build_date_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel(_LBL_DATE,
                             styleSheet=f"font-size:13px; color:{COLOR_TEXT_PRIMARY};"))

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setMinimumHeight(36)
        self._date_edit.setMinimumWidth(150)
        self._date_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:4px 10px; font-size:13px;"
        )

        # Quick jump to dates that have data
        self._quick_combo = QComboBox()
        self._quick_combo.setMinimumHeight(36)
        self._quick_combo.setMinimumWidth(180)
        self._quick_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:4px 8px; font-size:13px;"
        )
        self._quick_combo.setPlaceholderText("الأيام التي لها بيانات")
        self._quick_combo.currentTextChanged.connect(self._on_quick_jump)

        row.addWidget(self._date_edit)

        for label, slot, color in [
            (_BTN_TODAY, self._load_today, "#475569"),
            (_BTN_PREV,  self._go_prev,   "#475569"),
            (_BTN_NEXT,  self._go_next,   "#475569"),
        ]:
            b = self._btn(label, color)
            b.clicked.connect(slot)
            row.addWidget(b)

        row.addSpacing(8)
        row.addWidget(self._quick_combo)
        row.addStretch()

        gen_btn = self._btn(_BTN_GENERATE, COLOR_ACCENT)
        gen_btn.clicked.connect(self._generate)
        row.addWidget(gen_btn)

        return row

    def _btn(self, label: str, color: str) -> QPushButton:
        b = QPushButton(label)
        b.setMinimumHeight(36)
        b.setStyleSheet(
            f"background:{color}; color:white; border-radius:6px;"
            "padding:0 12px; font-size:13px;"
        )
        return b

    def _build_report_card(self) -> QFrame:
        """The main report card — school header + two summary tables."""
        self._report_card = QFrame()
        self._report_card.setStyleSheet(
            "background:white; border-radius:12px;"
            f"border:1px solid {COLOR_BORDER};"
        )
        self._report_card_layout = QVBoxLayout(self._report_card)
        self._report_card_layout.setContentsMargins(24, 20, 24, 20)
        self._report_card_layout.setSpacing(16)

        # School header (top of card)
        self._school_header = QLabel()
        self._school_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._school_header.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};"
            f"border-bottom:2px solid {COLOR_ACCENT}; padding-bottom:10px;"
        )
        self._report_card_layout.addWidget(self._school_header)

        self._date_header = QLabel()
        self._date_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_header.setStyleSheet(
            f"font-size:13px; color:{COLOR_TEXT_SECONDARY}; padding-bottom:6px;"
        )
        self._report_card_layout.addWidget(self._date_header)

        # Placeholder until first generate
        self._no_data_lbl = QLabel(_NO_DATA)
        self._no_data_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_lbl.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:14px; padding:40px;"
        )
        self._report_card_layout.addWidget(self._no_data_lbl)

        # Tables (created dynamically in _generate)
        self._contact_table: Optional[QTableWidget] = None
        self._absence_table: Optional[QTableWidget] = None
        self._contact_title: Optional[QLabel] = None
        self._absence_title: Optional[QLabel] = None

        return self._report_card

    # ── Inspection checklist ──────────────────────────────────────────────

    def _checklist_group(self, title: str) -> Tuple[QGroupBox, QVBoxLayout]:
        grp = QGroupBox(title)
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:13px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                margin-top:10px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)
        layout.setSpacing(6)
        return grp, layout

    def _rating_combo(self, scale: List[str]) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(32)
        combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:2px 8px; font-size:12px;"
        )
        combo.addItem(_NOT_RATED, -1)
        for index, label in enumerate(scale):
            combo.addItem(label, index)
        return combo

    def _rating_row(self, layout: QVBoxLayout, label: str, combo: QComboBox) -> None:
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:12px;")
        row.addWidget(lbl, 1)
        row.addWidget(combo)
        layout.addLayout(row)

    def _build_checklist_card(self) -> QFrame:
        """Hygiene / beneficiary-count / meal-quality / building checklist —
        matches templets/التقرير اليومي للمصالح المادية والمالية.docx."""
        card = QFrame()
        card.setStyleSheet(
            "background:white; border-radius:12px;"
            f"border:1px solid {COLOR_BORDER};"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        left = QVBoxLayout()
        right = QVBoxLayout()
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        outer.addLayout(columns)

        # 1 — Hygiene
        hygiene_grp, hygiene_layout = self._checklist_group(_LBL_HYGIENE)
        self._hygiene_combos: Dict[str, QComboBox] = {}
        for field, label in _HYGIENE_ITEMS:
            combo = self._rating_combo(_HYGIENE_SCALE)
            self._hygiene_combos[field] = combo
            self._rating_row(hygiene_layout, label, combo)
        left.addWidget(hygiene_grp)

        # 2 — Beneficiaries (expected / actually present, per meal)
        ben_grp, ben_layout = self._checklist_group(_LBL_BENEFICIARIES)
        self._beneficiary_spins: Dict[str, Tuple[QSpinBox, QSpinBox]] = {}
        header = QHBoxLayout()
        header.addWidget(QLabel(""), 1)
        header.addWidget(QLabel(_LBL_EXPECTED, styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:11px;"))
        header.addWidget(QLabel(_LBL_PRESENT, styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:11px;"))
        ben_layout.addLayout(header)
        for meal_key, meal_label in _MEAL_ORDER:
            row = QHBoxLayout()
            lbl = QLabel(meal_label)
            lbl.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY}; font-size:12px;")
            expected = QSpinBox()
            present = QSpinBox()
            for spin in (expected, present):
                spin.setRange(0, 9999)
                spin.setMinimumHeight(30)
                spin.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                spin.setStyleSheet(
                    f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:2px 6px;"
                )
            self._beneficiary_spins[meal_key] = (expected, present)
            row.addWidget(lbl, 1)
            row.addWidget(expected)
            row.addWidget(present)
            ben_layout.addLayout(row)
        left.addWidget(ben_grp)

        # 3 — Meal quality
        quality_grp, quality_layout = self._checklist_group(_LBL_QUALITY)
        self._quality_combos: Dict[str, QComboBox] = {}
        for field, label in _QUALITY_ITEMS:
            combo = self._rating_combo(_THREE_SCALE)
            self._quality_combos[field] = combo
            self._rating_row(quality_layout, label, combo)
        right.addWidget(quality_grp)

        # 4 — Building & equipment
        building_grp, building_layout = self._checklist_group(_LBL_BUILDING)
        self._building_combos: Dict[str, QComboBox] = {}
        for field, label in _BUILDING_ITEMS:
            combo = self._rating_combo(_THREE_SCALE)
            self._building_combos[field] = combo
            self._rating_row(building_layout, label, combo)
        right.addWidget(building_grp)

        return card

    def _build_notes_section(self) -> QGroupBox:
        grp = QGroupBox(_LBL_NOTES)
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:13px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                margin-top:10px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText(_NOTES_HINT)
        self._notes_edit.setMinimumHeight(120)
        self._notes_edit.setMaximumHeight(200)
        self._notes_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:8px; font-size:13px;"
        )
        layout.addWidget(self._notes_edit)

        btn_row = QHBoxLayout()
        save_btn = self._btn(_BTN_SAVE_REPORT, COLOR_SUCCESS)
        save_btn.clicked.connect(self._on_save_report)
        save_btn.setMaximumWidth(200)
        export_btn = self._btn(_BTN_EXPORT, "#475569")
        export_btn.clicked.connect(self._on_export)
        export_btn.setMaximumWidth(160)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return grp

    # ── Table builder ──────────────────────────────────────────────────────

    def _make_report_table(self, data: Dict[str, DailyContact | DailyAbsence]) -> QTableWidget:
        """Build a structured report QTableWidget from a dict of meal→data."""
        # Rows: 4 per meal (إعدادي, تأهيلي, معلمون, مجموع الوجبة) × 3 + grand total = 13
        num_rows = len(_MEAL_ORDER) * 4 + 1
        table = QTableWidget(num_rows, len(_HEADERS))
        table.setHorizontalHeaderLabels(_HEADERS)
        table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setShowGrid(True)
        table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                font-size:13px; background:white;
                gridline-color: #e2e8f0;
            }}
            QHeaderView::section {{
                background:{COLOR_ACCENT}; color:white;
                padding:8px 10px; border:none; font-weight:bold; font-size:12px;
            }}
            QTableWidget::item {{ padding:6px 10px; }}
        """)

        row = 0
        grand_granted = grand_paying = grand_compl = grand_total = 0

        for meal_key, meal_label in _MEAL_ORDER:
            contact = data.get(meal_key)

            # Helper to safely read a contact/absence object
            def _g(obj: Optional[object], attr: str) -> int:
                return getattr(obj, attr, 0) or 0

            cg = _g(contact, "collegial_granted")
            cp = _g(contact, "collegial_paying")
            cc = _g(contact, "collegial_complement")
            qg = _g(contact, "qualifying_granted")
            qp = _g(contact, "qualifying_paying")
            qc = _g(contact, "qualifying_complement")
            mo = _g(contact, "monitors")
            ct = cg + cp + cc
            qt = qg + qp + qc
            meal_tot = ct + qt + mo

            # إعدادي row
            table.setItem(row, 0, _cell(meal_label, bold=True))
            table.setItem(row, 1, _cell(_SECTOR_COLLEGIAL))
            table.setItem(row, 2, _cell(str(cg)))
            table.setItem(row, 3, _cell(str(cp)))
            table.setItem(row, 4, _cell(str(cc)))
            table.setItem(row, 5, _cell(str(ct), bold=True))
            row += 1

            # تأهيلي row
            table.setItem(row, 0, _cell(""))
            table.setItem(row, 1, _cell(_SECTOR_QUALIFYING))
            table.setItem(row, 2, _cell(str(qg)))
            table.setItem(row, 3, _cell(str(qp)))
            table.setItem(row, 4, _cell(str(qc)))
            table.setItem(row, 5, _cell(str(qt), bold=True))
            row += 1

            # معلمون row (no ممنوح/مؤد/متمم breakdown)
            table.setItem(row, 0, _cell(""))
            table.setItem(row, 1, _cell(_SECTOR_MONITORS))
            table.setItem(row, 2, _cell("—"))
            table.setItem(row, 3, _cell("—"))
            table.setItem(row, 4, _cell("—"))
            table.setItem(row, 5, _cell(str(mo), bold=True))
            row += 1

            # مجموع الوجبة row
            table.setItem(row, 0, _cell(""))
            table.setItem(row, 1, _cell(_SECTOR_TOTAL, bold=True, bg="#f0f9ff"))
            table.setItem(row, 2, _cell(str(cg + qg), bold=True, bg="#f0f9ff"))
            table.setItem(row, 3, _cell(str(cp + qp), bold=True, bg="#f0f9ff"))
            table.setItem(row, 4, _cell(str(cc + qc), bold=True, bg="#f0f9ff"))
            table.setItem(row, 5, _cell(str(meal_tot), bold=True, bg="#dbeafe", fg="#1d4ed8"))
            row += 1

            grand_granted += cg + qg
            grand_paying  += cp + qp
            grand_compl   += cc + qc
            grand_total   += meal_tot

        # Grand total row
        table.setItem(row, 0, _cell(_GRAND_TOTAL, bold=True, bg="#0f172a", fg="white"))
        table.setItem(row, 1, _cell("", bg="#0f172a"))
        table.setItem(row, 2, _cell(str(grand_granted), bold=True, bg="#0f172a", fg="white"))
        table.setItem(row, 3, _cell(str(grand_paying),  bold=True, bg="#0f172a", fg="white"))
        table.setItem(row, 4, _cell(str(grand_compl),   bold=True, bg="#0f172a", fg="white"))
        table.setItem(row, 5, _cell(str(grand_total),   bold=True, bg=COLOR_ACCENT, fg="white"))

        table.setMaximumHeight(num_rows * 36 + 40)
        return table

    # ── Generate ───────────────────────────────────────────────────────────

    def _generate(self) -> None:
        """Pull data from DB and rebuild the report card."""
        date_str = self._date_edit.date().toString("yyyy-MM-dd")

        # School header
        settings = get_school_settings()
        school_name = settings.school_name if settings else "—"
        school_year = settings.school_year if settings else "—"
        self._school_header.setText(
            f"{school_name}  —  السنة الدراسية: {school_year}"
        )
        self._date_header.setText(
            f"{_SUBTITLE}  |  بتاريخ: {date_str}"
        )

        contacts = {c.meal_type: c for c in get_day_contacts(date_str)}
        absences = {a.meal_type: a for a in get_day_absences(date_str)}

        has_data = bool(contacts or absences)
        self._no_data_lbl.setVisible(not has_data)

        # Remove old tables if any
        if self._contact_table:
            self._report_card_layout.removeWidget(self._contact_table)
            self._contact_table.deleteLater()
            self._contact_table = None
        if self._absence_table:
            self._report_card_layout.removeWidget(self._absence_table)
            self._absence_table.deleteLater()
            self._absence_table = None
        if self._contact_title:
            self._report_card_layout.removeWidget(self._contact_title)
            self._contact_title.deleteLater()
            self._contact_title = None
        if self._absence_title:
            self._report_card_layout.removeWidget(self._absence_title)
            self._absence_title.deleteLater()
            self._absence_title = None

        if has_data:
            # Contact table
            self._contact_title = _section_title("أ — ورقة الاتصال (الحضور)", COLOR_ACCENT)
            self._report_card_layout.addWidget(self._contact_title)
            self._contact_table = self._make_report_table(contacts)  # type: ignore[arg-type]
            self._report_card_layout.addWidget(self._contact_table)

            # Absence table
            self._absence_title = _section_title("ب — ورقة الغياب", COLOR_DANGER)
            self._report_card_layout.addWidget(self._absence_title)
            self._absence_table = self._make_report_table(absences)  # type: ignore[arg-type]
            self._report_card_layout.addWidget(self._absence_table)

        # Load notes + checklist
        self._load_report_fields(date_str)

        # Refresh quick-jump combo
        self._refresh_quick_combo()

    # ── Date navigation ────────────────────────────────────────────────────

    def _load_today(self) -> None:
        self._date_edit.setDate(QDate.currentDate())
        self._generate()

    def _go_prev(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(-1))
        self._generate()

    def _go_next(self) -> None:
        self._date_edit.setDate(self._date_edit.date().addDays(1))
        self._generate()

    def _on_quick_jump(self, date_str: str) -> None:
        if not date_str or not QDate.fromString(date_str, "yyyy-MM-dd").isValid():
            return
        self._date_edit.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))
        self._generate()

    def _refresh_quick_combo(self) -> None:
        self._quick_combo.blockSignals(True)
        self._quick_combo.clear()
        for d in get_dates_with_data():
            self._quick_combo.addItem(d)
        self._quick_combo.blockSignals(False)

    # ── Checklist load / save / export ────────────────────────────────────

    def _load_report_fields(self, date_str: str) -> None:
        """Populate notes + every checklist widget from the saved report,
        or reset to defaults (not-rated / zero) if none exists yet."""
        report = get_daily_report(date_str) or DailyReport(date=date_str)

        self._notes_edit.setPlainText(report.notes)

        for field, combo in self._hygiene_combos.items():
            combo.setCurrentIndex(combo.findData(getattr(report, field)))
        for field, combo in self._quality_combos.items():
            combo.setCurrentIndex(combo.findData(getattr(report, field)))
        for field, combo in self._building_combos.items():
            combo.setCurrentIndex(combo.findData(getattr(report, field)))

        for meal_key, (expected, present) in self._beneficiary_spins.items():
            expected.setValue(getattr(report, f"{meal_key}_expected"))
            present.setValue(getattr(report, f"{meal_key}_present"))

    def _current_report(self) -> DailyReport:
        """Build a DailyReport from every checklist widget's current value."""
        date_str = self._date_edit.date().toString("yyyy-MM-dd")
        fields = {"date": date_str, "notes": self._notes_edit.toPlainText().strip()}
        for field, combo in self._hygiene_combos.items():
            fields[field] = combo.currentData()
        for field, combo in self._quality_combos.items():
            fields[field] = combo.currentData()
        for field, combo in self._building_combos.items():
            fields[field] = combo.currentData()
        for meal_key, (expected, present) in self._beneficiary_spins.items():
            fields[f"{meal_key}_expected"] = expected.value()
            fields[f"{meal_key}_present"] = present.value()
        return DailyReport(**fields)

    def _on_save_report(self) -> None:
        try:
            save_daily_report(self._current_report())
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_export(self) -> None:
        date_str = self._date_edit.date().toString("yyyy-MM-dd")
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            _DOCX_DIALOG_TITLE,
            f"{_DOCX_DEFAULT_NAME}_{date_str}.docx",
            _WORD_FILTER,
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".docx":
            path = path.with_suffix(".docx")

        try:
            report = self._current_report()
            save_daily_report(report)
            settings = get_school_settings()
            _write_daily_report_docx(
                path,
                settings,
                date_str,
                report,
            )
            QMessageBox.information(self, "تم", _DOCX_SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_DOCX_SAVE_ERROR}\n{exc}")
