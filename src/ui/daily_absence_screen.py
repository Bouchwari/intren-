"""
src/ui/daily_absence_screen.py
Daily absence sheet (ورقة الغياب اليومي) — count absent beneficiaries per meal per day.
Parallel structure to daily_contact_screen but for absences (red theme).
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_BORDER, COLOR_DANGER, COLOR_PAPER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
import datetime

from core.attendance_estimate import EstimateResult, estimate_absence
from core.contact_counts import count_students
from core.models import DailyAbsence
from data.database import (
    get_all_holidays, get_all_students, get_day_absences, get_recent_absences, get_school_settings,
    is_holiday, save_daily_absence,
)
from ui.batch_export import draw_placeholder_pdf_page, run_batch_combined_pdf, run_batch_generate_data
from ui.daily_contact_screen import _draw_contact_pdf_cell, _draw_contact_pdf_text, _format_doc_date
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "ورقة الغياب اليومي"
_SUBTITLE       = "عدد الغائبين عن خدمة الإطعام المدرسي"
_BTN_PREV       = "اليوم السابق"
_BTN_PREV_ICON  = "→"
_BTN_NEXT       = "اليوم التالي"
_BTN_NEXT_ICON  = "←"
_BTN_TODAY      = "اليوم"
_BTN_LOAD       = "تحميل"
_BTN_LOAD_ICON  = "📂"
_BTN_AUTO       = "توليد تلقائي"
_BTN_AUTO_ICON  = "🧮"
_BTN_SAVE       = "حفظ اليوم"
_BTN_SAVE_ICON  = "💾"
_LBL_DATE       = "التاريخ:"
_LBL_PRIMARY    = "الابتدائي"
_LBL_COLLEGIAL  = "إعدادي"
_LBL_QUALIFYING = "تأهيلي"
_LBL_MONITORS   = "معلمو الداخلية"
_LBL_GRANTED    = "كاملة"
_LBL_COMPLEMENT = "متمم"
_LBL_GRAND_TOT  = "إجمالي الغياب"
_HDR_HISTORY    = ["التاريخ", "الوجبة",
                   "ابتدائي (ك)", "ابتدائي (مت)",
                   "إعدادي (ك)", "إعدادي (مت)",
                   "تأهيلي (ك)", "تأهيلي (مت)",
                   "معلمون (ك)", "معلمون (مت)", "الإجمالي"]
_SAVED_OK       = "تم حفظ ورقة الغياب بنجاح."
_TOAST_NO_STUDENTS = "لا يوجد تلاميذ في اللائحة — استورد اللائحة أولاً من صفحة التلاميذ."
_TOAST_NO_CLASSIFIED_STUDENTS = (
    "لم يتم التعرف على قسم أي تلميذ — تأكد من ملء حقل \"القسم\" في لائحة"
    " التلاميذ، وإلا فسيتم توليد أرقام صفرية."
)
_BTN_BATCH_GENERATE = "توليد الأرقام لعدة أيام"
_BTN_BATCH_GENERATE_ICON = "🎲"
_BTN_EXPORT      = "تصدير PDF"
_BTN_EXPORT_ICON = "📄"
_PDF_DIALOG_TITLE = "تصدير ورقة الغياب اليومي"
_PDF_DEFAULT_NAME = "ورقة_الغياب_اليومية"
_PDF_FILTER      = "PDF (*.pdf)"
_PDF_SAVED_OK    = "تم تصدير ورقة الغياب بنجاح."
_PDF_SAVE_ERROR  = "تعذر تصدير ورقة الغياب:"
_BTN_BATCH_EXPORT      = "توليد لعدة أيام"
_BTN_BATCH_EXPORT_ICON = "🗂"
_ESTIMATE_HISTORY_LIMIT = 900
_CONFIDENCE_LABELS = {"low": "منخفضة", "medium": "متوسطة", "high": "عالية"}
_ESTIMATE_NOTE_LOW = (
    "⚠️ لا يوجد سجل غياب كافٍ للتقدير (متوفر {records} من 3 أيام على الأقل لنفس اليوم والوجبة)"
    " — تم عرض 0 غياب، يرجى المراجعة يدوياً."
)
_ESTIMATE_NOTE_ESTIMATED = (
    "🧮 غياب مُقدَّر اعتماداً على {records} يوم سابق لنفس اليوم والوجبة — مستوى الثقة: {confidence}."
)

_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
]

# Red-toned palette for absences — visually distinct from contact sheet
_MEAL_COLORS = {
    MEAL_FTOUR: "#dc2626",   # red-600
    MEAL_GHADA: "#ea580c",   # orange-600
    MEAL_ASHA:  "#9f1239",   # rose-900
}
_PAGE_BG = COLOR_PAPER
_PANEL_BG = "#ffffff"
_PANEL_BORDER = "#dddccd"
_INK = COLOR_TEXT_PRIMARY
# Light red tint for chrome (table header) — matches this page's own red
# theme (_MEAL_COLORS, #fff5f5 alternate rows) rather than the app-wide
# COLOR_PANEL_ALT, which is teal and would clash here.
_HISTORY_HEADER_BG = "#FBEAEA"
_HISTORY_COLUMN_WIDTHS = [92, 78, 70, 70, 70, 70, 70, 70, 70, 70, 82]


def _spin() -> QSpinBox:
    s = QSpinBox()
    s.setRange(0, 9999)
    s.setMinimumHeight(34)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    s.setStyleSheet(
        f"border:1px solid {COLOR_BORDER}; border-radius:5px;"
        f"padding:2px 6px; font-size:{FONT_BODY}px;"
    )
    return s


# ── Absence meal card ─────────────────────────────────────────────────────────

class _AbsenceCard(QGroupBox):
    """Compact count card for one meal's absence numbers."""

    def __init__(self, meal_key: str, meal_label: str, color: str) -> None:
        super().__init__(meal_label)
        self._meal_key = meal_key
        self._color = color
        self.setMinimumWidth(245)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-size: {FONT_SECTION}px; font-weight: bold;
                color: {color};
                background: {_PANEL_BG};
                border: 1px solid {color};
                border-radius: 16px;
                margin-top: 16px; padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top right;
                padding: 0 10px; right: 14px;
            }}
        """)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 14, 10, 10)

        # Column headers
        hdr = QGridLayout()
        for col, lbl in enumerate(["", _LBL_GRANTED, _LBL_COMPLEMENT, "المجموع"]):
            h = QLabel(lbl)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setStyleSheet(
                f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px; font-weight:bold;"
            )
            hdr.addWidget(h, 0, col)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{COLOR_BORDER};")
        layout.addWidget(sep)

        grid = QGridLayout()
        grid.setSpacing(6)

        self._pg = _spin(); self._pc = _spin()
        self._cg = _spin(); self._cc = _spin()
        self._qg = _spin(); self._qc = _spin()
        self._mo = _spin(); self._mc = _spin()

        self._pt_lbl = QLabel("0")
        self._ct_lbl = QLabel("0")
        self._qt_lbl = QLabel("0")
        self._mt_lbl = QLabel("0")
        self._gt_lbl = QLabel("0")

        for lbl in (self._pt_lbl, self._ct_lbl, self._qt_lbl, self._mt_lbl):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color:{self._color}; font-weight:bold; font-size:{FONT_SECTION}px;")

        rows = [
            (_LBL_PRIMARY, self._pg, self._pc, self._pt_lbl),
            (_LBL_COLLEGIAL, self._cg, self._cc, self._ct_lbl),
            (_LBL_QUALIFYING, self._qg, self._qc, self._qt_lbl),
            (_LBL_MONITORS, self._mo, self._mc, self._mt_lbl),
        ]
        for row, (label, granted_spin, complement_spin, total_lbl) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(granted_spin, row, 1)
            grid.addWidget(complement_spin, row, 2)
            grid.addWidget(total_lbl, row, 3)
        layout.addLayout(grid)

        # Grand total
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

        for sp in (self._pg, self._pc, self._cg, self._cc,
                   self._qg, self._qc, self._mo, self._mc):
            sp.valueChanged.connect(self._update_totals)

    def _update_totals(self) -> None:
        absence = self.to_absence("")
        self._pt_lbl.setText(str(absence.primary_total))
        self._ct_lbl.setText(str(absence.collegial_total))
        self._qt_lbl.setText(str(absence.qualifying_total))
        self._mt_lbl.setText(str(absence.monitors_total))
        self._gt_lbl.setText(str(absence.grand_total))

    def load(self, absence: Optional[DailyAbsence]) -> None:
        if absence is None:
            for sp in (self._pg, self._pc, self._cg, self._cc,
                       self._qg, self._qc, self._mo, self._mc):
                sp.setValue(0)
        else:
            self._pg.setValue(absence.primary_granted)
            self._pc.setValue(absence.primary_complement)
            self._cg.setValue(absence.collegial_granted + absence.collegial_paying)
            self._cc.setValue(absence.collegial_complement)
            self._qg.setValue(absence.qualifying_granted + absence.qualifying_paying)
            self._qc.setValue(absence.qualifying_complement)
            self._mo.setValue(absence.monitors)
            self._mc.setValue(absence.monitors_complement)
        self._update_totals()

    def set_counts(
        self,
        primary_full: int, primary_lunch: int,
        collegial_full: int, collegial_lunch: int,
        qualifying_full: int, qualifying_lunch: int,
        monitors_full: int, monitors_lunch: int,
    ) -> None:
        """Fill from an estimate — same shape as load(), but from plain ints
        instead of a DailyAbsence, and always leaves the fields editable."""
        for spin, value in (
            (self._pg, primary_full), (self._pc, primary_lunch),
            (self._cg, collegial_full), (self._cc, collegial_lunch),
            (self._qg, qualifying_full), (self._qc, qualifying_lunch),
            (self._mo, monitors_full), (self._mc, monitors_lunch),
        ):
            spin.setValue(max(0, int(value)))
        self._update_totals()

    def to_absence(self, date: str) -> DailyAbsence:
        return DailyAbsence(
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


def _write_daily_absence_pdf(path: Path, date_str: str, absences: List[DailyAbsence], *, place: str = "") -> None:
    """Render a single date's absence sheet as its own PDF. Thin wrapper
    around _draw_daily_absence_pdf_page — batch export uses that directly
    to draw many days onto one shared writer instead of opening a new
    file per day."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TITLE)

    painter = QPainter(writer)
    try:
        _draw_daily_absence_pdf_page(
            painter, float(writer.width()), float(writer.height()), date_str, absences, place=place,
        )
    finally:
        painter.end()


def _draw_daily_absence_pdf_page(
    painter: QPainter,
    page_w: float,
    page_h: float,
    date_str: str,
    absences: List[DailyAbsence],
    *,
    place: str = "",
) -> None:
    """Draw one absence-sheet page into an already-open painter — same
    layout as the contact sheet's PDF (_draw_daily_contact_pdf_page in
    daily_contact_screen.py), red-themed, without a document number since
    the absence sheet has no numbered-document sequence like the contact
    sheet's رقم الوثيقة."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    absence_by_meal = {a.meal_type: a for a in absences}
    display_date = _format_doc_date(date_str)
    place_text = place.strip() or "..............."
    margin = 38.0
    content_w = page_w - (margin * 2)
    settings = get_school_settings()

    title = f"{_TITLE}  ليوم: {display_date}"
    table_y = draw_official_pdf_header(
        painter, page_width=page_w, margin=margin, top=18.0, settings=settings, title=title,
    )
    table_y += 4
    _draw_contact_pdf_text(
        painter, QRectF(margin, table_y, content_w, 18),
        f"حرر ب{place_text} بتاريخ {display_date}",
        size=10, color=COLOR_TEXT_SECONDARY,
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
    row_h = min(46.0, (table_h - header_rows_h) / n_data_rows)
    label_w = 130.0
    meal_w = (table_w - label_w) / len(_MEAL_ORDER)
    sub_w = meal_w / 2
    right = table_x + table_w

    label_header = QRectF(right - label_w, table_y, label_w, header_rows_h / 2)
    _draw_contact_pdf_cell(
        painter, label_header,
        background=COLOR_DANGER, border=COLOR_DANGER,
        text="", text_color="white", size=11, bold=True,
    )
    current_right = label_header.left()
    for _, meal_label in _MEAL_ORDER:
        rect = QRectF(current_right - meal_w, table_y, meal_w, header_rows_h / 2)
        _draw_contact_pdf_cell(
            painter, rect,
            background=COLOR_DANGER, border=COLOR_DANGER,
            text=meal_label, text_color="white", size=12, bold=True,
        )
        current_right = rect.left()

    sub_y = table_y + (header_rows_h / 2)
    label_subheader = QRectF(right - label_w, sub_y, label_w, header_rows_h / 2)
    _draw_contact_pdf_cell(
        painter, label_subheader,
        background=COLOR_DANGER, border="white",
        text="الفئة", text_color="white", size=10, bold=True,
    )
    current_right = label_subheader.left()
    for _ in _MEAL_ORDER:
        for sub_label in (_LBL_GRANTED, _LBL_COMPLEMENT):
            rect = QRectF(current_right - sub_w, sub_y, sub_w, header_rows_h / 2)
            _draw_contact_pdf_cell(
                painter, rect,
                background=COLOR_DANGER, border="white",
                text=sub_label, text_color="white", size=9,
            )
            current_right = rect.left()

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
            absence = absence_by_meal.get(meal_key) or DailyAbsence(date="", meal_type=meal_key)
            for field_name in (granted_field, complement_field):
                rect = QRectF(current_right - sub_w, row_y, sub_w, row_h)
                _draw_contact_pdf_cell(
                    painter, rect,
                    background="white", border=COLOR_BORDER,
                    text=str(getattr(absence, field_name)), text_color=COLOR_TEXT_PRIMARY, size=11,
                )
                current_right = rect.left()

    total_y = table_y + header_rows_h + (len(rows_data) * row_h)
    total_label_rect = QRectF(right - label_w, total_y, label_w, row_h)
    _draw_contact_pdf_cell(
        painter, total_label_rect,
        background=COLOR_DANGER, border=COLOR_DANGER,
        text=_LBL_GRAND_TOT, text_color="white", size=11, bold=True,
    )
    current_right = total_label_rect.left()
    for meal_key, _ in _MEAL_ORDER:
        absence = absence_by_meal.get(meal_key) or DailyAbsence(date="", meal_type=meal_key)
        rect = QRectF(current_right - meal_w, total_y, meal_w, row_h)
        _draw_contact_pdf_cell(
            painter, rect,
            background="#F8F9FA", border=COLOR_BORDER,
            text=str(absence.grand_total), text_color=COLOR_TEXT_PRIMARY, size=11, bold=True,
        )
        current_right = rect.left()

    footer_y = page_h - margin - footer_h + 6
    draw_official_pdf_footer(
        painter, page_width=page_w, margin=margin, top=footer_y, settings=settings,
        roles=["رئيس المؤسسة", "مسير المصالح المادية والمالية", "الحارس العام للداخلية"],
    )


def _counts_to_absences(date_str: str, counts: Dict[str, Dict[str, int]]) -> List[DailyAbsence]:
    """Same per-meal mapping DailyAbsenceScreen._apply_generated_counts uses
    to fill the live cards, but building DailyAbsence rows to save directly
    instead — used by batch data generation, which has no open cards to
    write into."""
    primary = counts.get("primary", {})
    collegial = counts.get("collegial", {})
    qualifying = counts.get("qualifying", {})
    monitors = counts.get("monitors", {})
    return [
        DailyAbsence(
            date=date_str, meal_type=MEAL_FTOUR,
            primary_granted=primary.get("full", 0),
            collegial_granted=collegial.get("full", 0),
            qualifying_granted=qualifying.get("full", 0),
            monitors=monitors.get("full", 0),
        ),
        DailyAbsence(
            date=date_str, meal_type=MEAL_GHADA,
            primary_granted=primary.get("full", 0), primary_complement=primary.get("lunch", 0),
            collegial_granted=collegial.get("full", 0), collegial_complement=collegial.get("lunch", 0),
            qualifying_granted=qualifying.get("full", 0), qualifying_complement=qualifying.get("lunch", 0),
            monitors=monitors.get("full", 0), monitors_complement=monitors.get("lunch", 0),
        ),
        DailyAbsence(
            date=date_str, meal_type=MEAL_ASHA,
            primary_granted=primary.get("full", 0),
            collegial_granted=collegial.get("full", 0),
            qualifying_granted=qualifying.get("full", 0),
            monitors=monitors.get("full", 0),
        ),
    ]


def _unflatten_counts(roster: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {
        "primary": {}, "collegial": {}, "qualifying": {}, "monitors": {},
    }
    for key, value in roster.items():
        category, grant_kind = key.rsplit("_", 1)
        counts[category][grant_kind] = value
    return counts


def generate_and_save_absence_for_date(
    date_str: str, active_roster: Dict[str, int], history: List[DailyAbsence],
) -> bool:
    """Auto-fill AND SAVE real absence numbers for one date using the same
    estimator as "توليد تلقائي" — shared by the batch-generate button and
    ui/work_pipeline_screen.py. Returns False (no-op) for a real holiday
    or a date that already has saved data, never overwriting it."""
    if is_holiday(date_str) or get_day_absences(date_str):
        return False
    target_date = datetime.date.fromisoformat(date_str)
    result = estimate_absence(active_roster, history, target_date, MEAL_GHADA)
    for absence in _counts_to_absences(date_str, _unflatten_counts(result.counts)):
        save_daily_absence(absence)
    return True


def build_absence_pdf_page(
    painter, page_w: float, page_h: float, date_str: str,
    holiday_labels: Dict[str, str], settings,
) -> str:
    """Draw one date's page for a combined batch PDF — real data, a
    holiday placeholder, or a no-data placeholder. Shared by
    _on_batch_export and ui/work_pipeline_screen.py's "generate
    everything" action. Returns "data" / "holiday" / "empty" for the
    caller's summary."""
    if date_str in holiday_labels:
        label = holiday_labels[date_str] or "بدون سبب محدد"
        draw_placeholder_pdf_page(
            painter, page_w, page_h, f"{date_str} — يوم عطلة", f"📅 عطلة: {label}",
        )
        return "holiday"
    absences = get_day_absences(date_str)
    if not absences:
        draw_placeholder_pdf_page(
            painter, page_w, page_h, f"{date_str} — لا توجد بيانات",
            "لم يتم تسجيل بيانات ورقة الغياب لهذا اليوم بعد.",
        )
        return "empty"
    _draw_daily_absence_pdf_page(
        painter, page_w, page_h, date_str, absences, place=settings.city if settings else "",
    )
    return "data"


# ── Main screen ───────────────────────────────────────────────────────────────

class DailyAbsenceScreen(QWidget):
    """Daily absence sheet screen — red-themed parallel of DailyContactScreen."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._cards: Dict[str, _AbsenceCard] = {}
        self._loaded_once = False
        self._build_ui()

    def refresh(self) -> None:
        if not getattr(self, "_loaded_once", False):
            self._load_today()
            self._loaded_once = True
        else:
            self._load_selected()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(14)

        inner.addLayout(self._build_header())
        inner.addLayout(self._build_date_bar())
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

    def _build_date_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel(_LBL_DATE,
                             styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))

        self._date_edit = DateInput(display_format="yyyy-MM-dd")
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setMinimumHeight(36)
        self._date_edit.setMinimumWidth(128)
        self._date_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            f"padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        row.addWidget(self._date_edit)

        for label, icon, slot, color in [
            (_BTN_TODAY, None,           self._load_today,    _INK),
            (_BTN_PREV,  _BTN_PREV_ICON, self._go_prev,       _INK),
            (_BTN_NEXT,  _BTN_NEXT_ICON, self._go_next,       _INK),
            (_BTN_LOAD,  _BTN_LOAD_ICON, self._load_selected, "#0891b2"),
            (_BTN_AUTO,  _BTN_AUTO_ICON, self._on_auto_generate_clicked, "#7c3aed"),
        ]:
            btn = self._btn(label, color, icon=icon)
            btn.clicked.connect(slot)
            row.addWidget(btn)

        row.addStretch()

        batch_generate_btn = self._btn(_BTN_BATCH_GENERATE, "#7c3aed", icon=_BTN_BATCH_GENERATE_ICON)
        batch_generate_btn.clicked.connect(self._on_batch_generate_data)
        row.addWidget(batch_generate_btn)

        export_btn = self._btn(_BTN_EXPORT, _INK, icon=_BTN_EXPORT_ICON)
        export_btn.clicked.connect(self._on_export)
        row.addWidget(export_btn)

        batch_export_btn = self._btn(_BTN_BATCH_EXPORT, _INK, icon=_BTN_BATCH_EXPORT_ICON)
        batch_export_btn.clicked.connect(self._on_batch_export)
        row.addWidget(batch_export_btn)

        save_btn = self._btn(_BTN_SAVE, COLOR_SUCCESS, icon=_BTN_SAVE_ICON)
        save_btn.clicked.connect(self._on_save)
        row.addWidget(save_btn)
        return row

    def _btn(self, label: str, color: str, *, icon: str | None = None) -> QPushButton:
        return IconButton(
            label, icon=icon, bg=color, text_color="white",
            border_radius=12, padding_h=12, font_size=13, bold=False, min_height=36,
        )

    def _build_estimate_note(self) -> QLabel:
        label = QLabel("")
        label.setWordWrap(True)
        label.setVisible(False)
        label.setStyleSheet(
            f"background:transparent; color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;"
        )
        self._estimate_note = label
        return label

    def _set_estimate_note(self, result: Optional[EstimateResult]) -> None:
        if result is None:
            self._estimate_note.setVisible(False)
            return
        if result.reason == "insufficient_history":
            text = _ESTIMATE_NOTE_LOW.format(records=result.records_used)
        else:
            text = _ESTIMATE_NOTE_ESTIMATED.format(
                records=result.records_used,
                confidence=_CONFIDENCE_LABELS.get(result.confidence, result.confidence),
            )
        self._estimate_note.setText(text)
        self._estimate_note.setVisible(True)

    def _build_cards_row(self) -> QGridLayout:
        row = QGridLayout()
        row.setSpacing(12)
        for index, (meal_key, meal_label) in enumerate(_MEAL_ORDER):
            card = _AbsenceCard(meal_key, meal_label, _MEAL_COLORS[meal_key])
            self._cards[meal_key] = card
            row.addWidget(card, index // 2, index % 2)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 1)
        return row

    def _build_history(self) -> QGroupBox:
        grp = QGroupBox("سجل الغيابات الأخيرة")
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_DANGER};
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
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(_HISTORY_COLUMN_WIDTHS):
            self._history_table.setColumnWidth(col, width)
        self._history_table.setMaximumHeight(190)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {_PANEL_BORDER}; border-radius:12px;
                background:white; alternate-background-color:#fff5f5;
                font-size:{FONT_LABEL}px;
            }}
            QHeaderView::section {{
                background:{_HISTORY_HEADER_BG}; color:{_INK};
                padding:7px 10px; border:none;
                border-bottom:1px solid {_PANEL_BORDER};
                font-weight:bold; font-size:{FONT_CAPTION}px;
            }}
            QTableWidget::item {{ padding:5px 10px; }}
        """)
        self._history_table.doubleClicked.connect(self._on_history_click)
        layout.addWidget(self._history_table)
        return grp

    # ── Data helpers ────────────────────────────────────────────────────────

    def _selected_date_str(self) -> str:
        return self._date_edit.date().toString("yyyy-MM-dd")

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
        date_str = self._selected_date_str()
        absences = {a.meal_type: a for a in get_day_absences(date_str)}
        for meal_key, card in self._cards.items():
            card.load(absences.get(meal_key))
        self._set_estimate_note(None)
        self._refresh_history()

    def _refresh_history(self) -> None:
        recent = get_recent_absences(60)
        self._history_table.setRowCount(0)
        meal_labels = dict(_MEAL_ORDER)
        for a in recent:
            r = self._history_table.rowCount()
            self._history_table.insertRow(r)
            values = [
                a.date,
                meal_labels.get(a.meal_type, a.meal_type),
                str(a.primary_granted), str(a.primary_complement),
                str(a.collegial_granted), str(a.collegial_complement),
                str(a.qualifying_granted), str(a.qualifying_complement),
                str(a.monitors), str(a.monitors_complement),
                str(a.grand_total),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                )
                self._history_table.setItem(r, col, item)

    def _on_auto_generate_clicked(self) -> None:
        """Fill today's absence counts from historical patterns for this
        weekday+meal — a median rate, not a random number (see
        core.attendance_estimate). Fields stay editable afterward."""
        students = get_all_students()
        if not students:
            QMessageBox.information(self, "توليد تلقائي", _TOAST_NO_STUDENTS)
            return

        active_roster = self._flatten_counts(count_students(students))
        if sum(active_roster.values()) == 0:
            QMessageBox.information(self, "توليد تلقائي", _TOAST_NO_CLASSIFIED_STUDENTS)
            return

        target_date = self._date_edit.date().toPython()
        history = get_recent_absences(limit=_ESTIMATE_HISTORY_LIMIT)

        # One estimate call drives all 3 cards, same as the contact sheet's
        # auto-generate — ghada carries the وجبة غذاء (lunch-only) rate,
        # ftour/asha only ever get the "full" column.
        result = estimate_absence(active_roster, history, target_date, MEAL_GHADA)
        counts = self._unflatten_counts(result.counts)
        self._apply_generated_counts(counts)
        self._set_estimate_note(result)

    def _flatten_counts(self, counts: Dict[str, Dict[str, int]]) -> Dict[str, int]:
        return {
            f"{category}_{grant_kind}": count
            for category, grants in counts.items()
            for grant_kind, count in grants.items()
        }

    def _unflatten_counts(self, roster: Dict[str, int]) -> Dict[str, Dict[str, int]]:
        counts: Dict[str, Dict[str, int]] = {
            "primary": {}, "collegial": {}, "qualifying": {}, "monitors": {},
        }
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

    def _on_batch_generate_data(self) -> None:
        """Auto-fill AND SAVE real absence numbers for every date in a
        range that has none yet — the same estimator behind "توليد تلقائي"
        (median of real historical same-weekday rates, not random), just
        run over many days instead of one. Never overwrites a day that
        already has saved data, and skips real holidays."""
        students = get_all_students()
        if not students:
            QMessageBox.information(self, "تنبيه", _TOAST_NO_STUDENTS)
            return
        active_roster = self._flatten_counts(count_students(students))
        if sum(active_roster.values()) == 0:
            QMessageBox.information(self, "تنبيه", _TOAST_NO_CLASSIFIED_STUDENTS)
            return
        history = get_recent_absences(limit=_ESTIMATE_HISTORY_LIMIT)

        def generate_day(date_str: str) -> bool:
            return generate_and_save_absence_for_date(date_str, active_roster, history)

        run_batch_generate_data(self, generate_day)

    def _on_history_click(self) -> None:
        row = self._history_table.currentRow()
        if row < 0:
            return
        date_str = self._history_table.item(row, 0).text()
        self._date_edit.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))
        self._load_selected()

    def _on_save(self) -> None:
        date_str = self._selected_date_str()
        try:
            for meal_key, card in self._cards.items():
                save_daily_absence(card.to_absence(date_str))
            self._refresh_history()
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_export(self) -> None:
        date_str = self._selected_date_str()
        path_str, _ = QFileDialog.getSaveFileName(
            self, _PDF_DIALOG_TITLE, f"{_PDF_DEFAULT_NAME}_{date_str}.pdf", _PDF_FILTER,
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        try:
            absences = [card.to_absence(date_str) for card in self._cards.values()]
            for absence in absences:
                save_daily_absence(absence)
            self._refresh_history()
            settings = get_school_settings()
            _write_daily_absence_pdf(path, date_str, absences, place=settings.city if settings else "")
            QMessageBox.information(self, "تم", _PDF_SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_PDF_SAVE_ERROR}\n{exc}")

    def _on_batch_export(self) -> None:
        """Export the absence sheet for a range of days as ONE combined
        PDF — one page per day, like a mail merge, instead of a separate
        file per day. A real holiday or a day with no saved data still
        gets its own page explaining why, instead of silently vanishing.
        Read-only: never saves/records anything — it only exports what's
        already in the database."""
        settings = get_school_settings()
        holiday_labels = {h.date: h.label for h in get_all_holidays()}

        def build_page(painter, page_w: float, page_h: float, date_str: str) -> str:
            return build_absence_pdf_page(painter, page_w, page_h, date_str, holiday_labels, settings)

        run_batch_combined_pdf(self, _PDF_DEFAULT_NAME, QPageLayout.Orientation.Portrait, build_page)
