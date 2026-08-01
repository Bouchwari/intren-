"""
src/ui/daily_report_screen.py
Daily report (التقرير اليومي) — auto-generated attendance/absence summary,
plus the مسير's inspection checklist (hygiene / meal quality / building) and
notes, matching the real accepted form.
"""
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextOption,
)
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
from ui.daily_contact_screen import _academy_line, _province_line

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
_BTN_EXPORT     = "📄  تصدير PDF"
_PDF_DIALOG_TITLE = "تصدير التقرير اليومي"
_PDF_DEFAULT_NAME = "التقرير_اليومي"
_PDF_FILTER     = "PDF (*.pdf)"
_PDF_SAVED_OK   = "تم تصدير التقرير اليومي بنجاح."
_PDF_SAVE_ERROR = "تعذر تصدير التقرير اليومي:"

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


# ── PDF export — our own compact design ────────────────────────────────────
# Two full copies (نظيرين) stacked on one landscape sheet, not a filled copy
# of the real template: that template's layout doesn't cleanly split into
# two clean full-page copies (see git history for what was tried first). One
# sheet keeps paper use down and both signers can sign the same page.
#
# A Word version isn't built yet — deliberately left for later. Everything
# a renderer needs is already isolated in _report_copy_lines(), so a future
# _write_daily_report_docx can reuse the exact same rows without touching
# this file's PDF drawing code.

def _report_copy_lines(report: DailyReport) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Return (hygiene_lines, quality_lines, building_lines), each a list of
    (item label, rating text or '—' if not yet rated) — the same shape any
    future renderer (PDF or Word) would draw from."""
    def _lines(items: List[Tuple[str, str]], scale: List[str]) -> List[Tuple[str, str]]:
        result = []
        for field, label in items:
            rating = getattr(report, field)
            result.append((label, scale[rating] if 0 <= rating < len(scale) else _NOT_RATED))
        return result

    return (
        _lines(_HYGIENE_ITEMS, _HYGIENE_SCALE),
        _lines(_QUALITY_ITEMS, _THREE_SCALE),
        _lines(_BUILDING_ITEMS, _THREE_SCALE),
    )


def _draw_report_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    *,
    size: int,
    color: str,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
) -> None:
    font = QFont("Segoe UI")
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    # AlignAbsolute forces true visual left/right — under RTL text direction,
    # plain AlignRight/AlignLeft are direction-relative and land reversed.
    if align in (Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft):
        align = align | Qt.AlignmentFlag.AlignAbsolute
    option = QTextOption()
    option.setTextDirection(Qt.LayoutDirection.RightToLeft)
    option.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    painter.drawText(rect, text, option)


def _draw_report_section(
    painter: QPainter,
    *,
    x: float,
    y: float,
    width: float,
    title: str,
    lines: List[Tuple[str, str]],
    row_h: float,
) -> float:
    """Draw a compact 'label — rating' list section, return the Y below it."""
    _draw_report_text(
        painter, QRectF(x, y, width, row_h), title,
        size=8, color=COLOR_ACCENT, bold=True,
    )
    y += row_h
    label_w = width * 0.72
    for label, value in lines:
        painter.setPen(QPen(QColor(COLOR_BORDER), 0.5))
        painter.drawLine(int(x), int(y + row_h), int(x + width), int(y + row_h))
        _draw_report_text(
            painter, QRectF(x + width - label_w, y, label_w, row_h), label,
            size=7, color=COLOR_TEXT_PRIMARY,
        )
        _draw_report_text(
            painter, QRectF(x, y, width - label_w - 4, row_h), value,
            size=7, color=COLOR_TEXT_SECONDARY, bold=True,
            align=Qt.AlignmentFlag.AlignLeft,
        )
        y += row_h
    return y


def _draw_report_copy(
    painter: QPainter,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    settings,
    date_str: str,
    report: DailyReport,
) -> None:
    """Draw one complete, compact copy of the report inside the given box."""
    display_date = date_str.replace("-", "/")
    s = settings
    academy = _academy_line(s.aref if s else "")
    province = _province_line(s.direction_provinciale if s else "")
    school_name = (s.school_name if s else "").strip() or "اسم المؤسسة"

    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.drawRect(QRectF(x, y, width, height))

    header_h = 16.0
    _draw_report_text(
        painter, QRectF(x + 8, y + 4, width - 16, header_h),
        f"{school_name}  —  {academy}  —  {province}",
        size=9, color=COLOR_TEXT_PRIMARY, bold=True, align=Qt.AlignmentFlag.AlignCenter,
    )
    _draw_report_text(
        painter, QRectF(x + 8, y + 4 + header_h, width - 16, header_h),
        f"{_SUBTITLE}  —  بتاريخ: {display_date}",
        size=8, color=COLOR_ACCENT, bold=True, align=Qt.AlignmentFlag.AlignCenter,
    )

    body_y = y + 4 + (header_h * 2) + 6
    body_h = height - (body_y - y) - 30  # reserve room for signatures
    col_gap = 10.0
    col_w = (width - 16 - col_gap) / 2
    left_x = x + 8
    right_x = left_x + col_w + col_gap
    row_h = min(11.0, body_h / 13)

    hygiene_lines, quality_lines, building_lines = _report_copy_lines(report)

    ly = _draw_report_section(
        painter, x=left_x, y=body_y, width=col_w,
        title=_LBL_HYGIENE, lines=hygiene_lines, row_h=row_h,
    )
    beneficiary_lines = [
        (meal_label, f"{getattr(report, f'{key}_present')}/{getattr(report, f'{key}_expected')}")
        for key, meal_label in _MEAL_ORDER
    ]
    _draw_report_section(
        painter, x=left_x, y=ly + 4, width=col_w,
        title=f"{_LBL_BENEFICIARIES} ({_LBL_PRESENT}/{_LBL_EXPECTED})",
        lines=beneficiary_lines, row_h=row_h,
    )

    ry = _draw_report_section(
        painter, x=right_x, y=body_y, width=col_w,
        title=_LBL_QUALITY, lines=quality_lines, row_h=row_h,
    )
    ry = _draw_report_section(
        painter, x=right_x, y=ry + 4, width=col_w,
        title=_LBL_BUILDING, lines=building_lines, row_h=row_h,
    )
    if report.notes.strip():
        _draw_report_text(
            painter, QRectF(right_x, ry + 4, col_w, row_h * 2),
            f"ملاحظات: {report.notes.strip()}",
            size=7, color=COLOR_TEXT_PRIMARY,
        )

    sig_y = y + height - 26
    sig_w = (width - 16) / 2
    for index, role in enumerate(("مسير المصالح المادية والمالية", "مدير المؤسسة")):
        rx = x + 8 + (index * sig_w)
        _draw_report_text(
            painter, QRectF(rx, sig_y, sig_w, 12), role,
            size=8, color=COLOR_TEXT_PRIMARY, bold=True, align=Qt.AlignmentFlag.AlignCenter,
        )
        painter.setPen(QPen(QColor("#9CA3AF"), 1))
        painter.drawLine(int(rx + 20), int(sig_y + 22), int(rx + sig_w - 20), int(sig_y + 22))


def _write_daily_report_pdf(
    path: Path,
    settings,
    date_str: str,
    report: DailyReport,
) -> None:
    """Render two compact copies of the report stacked on one landscape
    sheet — one for the مسير, one for the مدير, one sheet of paper."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_SUBTITLE)

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        page_w = float(writer.width())
        page_h = float(writer.height())
        margin = 24.0
        gap = 14.0
        copy_h = (page_h - (margin * 2) - gap) / 2
        copy_w = page_w - (margin * 2)

        _draw_report_copy(
            painter, x=margin, y=margin, width=copy_w, height=copy_h,
            settings=settings, date_str=date_str, report=report,
        )
        painter.setPen(QPen(QColor(COLOR_BORDER), 1, Qt.PenStyle.DashLine))
        cut_y = margin + copy_h + (gap / 2)
        painter.drawLine(int(margin), int(cut_y), int(page_w - margin), int(cut_y))
        _draw_report_copy(
            painter, x=margin, y=margin + copy_h + gap, width=copy_w, height=copy_h,
            settings=settings, date_str=date_str, report=report,
        )
    finally:
        painter.end()


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
            _PDF_DIALOG_TITLE,
            f"{_PDF_DEFAULT_NAME}_{date_str}.pdf",
            _PDF_FILTER,
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        try:
            report = self._current_report()
            save_daily_report(report)
            settings = get_school_settings()
            _write_daily_report_pdf(
                path,
                settings,
                date_str,
                report,
            )
            QMessageBox.information(self, "تم", _PDF_SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_PDF_SAVE_ERROR}\n{exc}")
