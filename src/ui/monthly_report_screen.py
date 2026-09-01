"""
src/ui/monthly_report_screen.py
Monthly summary (الملخص الشهري) — aggregates daily data for a full month,
computes net meals served and total cost, with مسير notes. Renamed from
"المحضر الشهري" (2026-08-23) — that name was too close to محضر التسليم
الشهري's own (a genuinely different, official signed document — see
monthly_reception_screen.py) and kept causing the two to be confused for
the same thing. This screen has no official government template at all;
it's an internal working summary, hence "ملخص" (summary), matching what
its own subtitle already called it.
"""
import datetime
import logging
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER, COLOR_DANGER, COLOR_PANEL_ALT,
    COLOR_SIDEBAR_BG, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_IFTAR, MEAL_SHOUR, MEAL_LABELS,
    FONT_BODY, FONT_LABEL, FONT_SECTION,
)
from core.models import MonthlyMealSummary
from data.database import (
    get_monthly_report_notes, get_monthly_summaries,
    get_months_with_data, get_school_settings,
    save_monthly_report_notes,
)
from ui.daily_reception_screen import _draw_reception_pdf_cell, _draw_reception_pdf_text
from ui.dialogs import ask_choice
from ui.document_header import draw_official_pdf_header
from ui.widgets.empty_state import EmptyState
from ui.widgets.icon_button import IconButton

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "الملخص الشهري"
_SUBTITLE       = "ملخص نشاط الإطعام المدرسي الشهري"
_BTN_GENERATE   = "توليد الملخص"
_BTN_GENERATE_ICON = "🔄"
_BTN_SAVE_NOTES = "حفظ الملاحظات"
_BTN_SAVE_NOTES_ICON = "💾"
_BTN_EXPORT      = "تصدير"
_BTN_EXPORT_ICON = "📄"
_LBL_MONTH      = "الشهر:"
_LBL_YEAR       = "السنة:"
_LBL_NOTES      = "ملاحظات المسير"
_NOTES_HINT     = "أدخل ملاحظاتك هنا..."
_NO_DATA        = "لا توجد بيانات لهذا الشهر.\nأدخل بيانات ورقة الاتصال أو الغياب أولاً."
_SAVED_OK       = "تم حفظ الملاحظات بنجاح."
_EXPORT_NO_DATA = "ولّد الملخص أولاً ثم قم بالتصدير."
_EXPORT_SAVED   = "تم حفظ الملف بنجاح:\n"
_EXPORT_ERROR   = "تعذر تصدير الملف:"
_EXPORT_CHOICE_TITLE = "اختر صيغة التصدير"
_EXPORT_CHOICE_TEXT  = "هل تريد تصدير الملخص بصيغة PDF أم Excel؟"
# Two decimals for dirham amounts in the Excel export.
_EXCEL_MONEY_FORMAT = "0.00"

_ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر",
]

# Main summary table headers
_MAIN_HEADERS = [
    "الوجبة", "أيام البيانات",
    "إجمالي الحضور", "إجمالي الغياب",
    "الوجبات المقدمة", "ثمن الوجبة", "التكلفة الإجمالية (د.م)",
]

# Detail breakdown table headers
_DETAIL_HEADERS = [
    "الوجبة", "القطاع",
    "إجمالي الحضور", "إجمالي الغياب", "الصافي",
]

_MEAL_ASHA_PURPLE = "#534AB7"  # matches dashboard_screen.py / meal_program_screen.py exactly —
# this screen used to have its own off-brand "#f59e0b"/"#7c3aed" shades, so the same meal
# read as a different color depending which screen you were on.

_MEAL_COLORS = {
    MEAL_FTOUR: "#EF9F27",
    MEAL_GHADA: COLOR_ACCENT,
    MEAL_ASHA:  _MEAL_ASHA_PURPLE,
    MEAL_IFTAR: "#C2703D",
    MEAL_SHOUR: COLOR_ACCENT_DEEP,
}


def _titem(text: str, bold: bool = False, bg: str = "", fg: str = "",
           align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    f = QFont()
    f.setBold(bold)
    item.setFont(f)
    if bg:
        item.setBackground(QColor(bg))
    if fg:
        item.setForeground(QColor(fg))
    return item


def _styled_table(rows: int, cols: int, headers: List[str],
                  header_bg: str = COLOR_ACCENT) -> QTableWidget:
    t = QTableWidget(rows, cols)
    t.setHorizontalHeaderLabels(headers)
    t.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setShowGrid(True)
    t.setAlternatingRowColors(True)
    t.setStyleSheet(f"""
        QTableWidget {{
            border: 1px solid {COLOR_BORDER}; border-radius: 8px;
            font-size: {FONT_BODY}px; background: white;
            alternate-background-color: {COLOR_PANEL_ALT};
            gridline-color: {COLOR_BORDER};
        }}
        QHeaderView::section {{
            background: {header_bg}; color: white;
            padding: 8px 10px; border: none;
            font-weight: bold; font-size: {FONT_LABEL}px;
        }}
        QTableWidget::item {{ padding: 7px 10px; }}
    """)
    return t


def _size_table_to_contents(table: QTableWidget) -> None:
    """Set an exact height that fits every row, computed from the
    table's own real (already-populated) row heights instead of a
    hardcoded "rows * guessed_pixels" formula. That formula under-
    estimated the real per-row height here — confirmed by actually
    rendering this screen, where the detail table showed an internal
    scrollbar and clipped most of its own rows instead of displaying
    all of them, exactly the class of bug a fixed-pixel guess invites
    the moment font size, padding, or DPI changes.

    Sets BOTH minimum and maximum height to the same computed value —
    maximum alone only permits the table to grow that tall, it doesn't
    make the surrounding QVBoxLayout actually GIVE it that much space
    (confirmed by rendering again after a maximum-only version: the
    scrollbar was still there, just less exaggerated). Forcing an exact
    height is safe here since this table's content is fully known and
    fixed at build time, not something a user resizes."""
    header_h = table.horizontalHeader().height()
    rows_h = table.verticalHeader().length()  # sum of every row's real height
    frame = table.frameWidth() * 2
    exact_height = header_h + rows_h + frame + 2
    table.setMinimumHeight(exact_height)
    table.setMaximumHeight(exact_height)


_LOGGER = logging.getLogger(__name__)


# ── PDF export — hand-drawn, mirrors the on-screen tables ──────────────────

def _draw_rtl_table(
    painter: QPainter, *, top: float, left: float, content_w: float,
    headers: List[str], col_ratios: List[float], rows: List[dict],
    header_bg: str, row_height: float = 18.0, header_height: float = 22.0,
    font_size: int = 9,
) -> float:
    """Generic RTL table drawer — headers[0] renders at the RIGHT edge,
    matching the on-screen QTableWidget's own RTL column order (and this
    document's all-Arabic content, unlike the bilingual reception
    records). Each row dict: {"cells": [(text, bold), ...], "bg": color,
    "fg": color} — bg/fg default to white/near-black when omitted.
    Returns the Y position after the table."""
    col_widths = [content_w * r for r in col_ratios]

    x = left + content_w
    for label, w in zip(headers, col_widths):
        x -= w
        _draw_reception_pdf_cell(
            painter, QRectF(x, top, w, header_height),
            background=header_bg, border="#000000",
            text=label, text_color="white", size=font_size, bold=True,
        )
    y = top + header_height

    for row in rows:
        bg = row.get("bg", "white")
        fg = row.get("fg", "#111827")
        x = left + content_w
        for cell, w in zip(row["cells"], col_widths):
            text, bold = cell
            x -= w
            _draw_reception_pdf_cell(
                painter, QRectF(x, y, w, row_height),
                background=bg, border="#000000",
                text=text, text_color=fg, size=font_size, bold=bold,
            )
        y += row_height

    return y


def _monthly_summary_main_rows(summaries: List[MonthlyMealSummary]) -> tuple:
    """Shared row-building logic for the main table — used by both the
    PDF and (indirectly, for totals) the Excel export, so the two exports
    and the on-screen table can't silently drift out of sync on the
    grand-total arithmetic."""
    rows = []
    total_contact = total_absence = total_net = 0
    total_cost = 0.0
    for s in summaries:
        rows.append({"cells": [
            (MEAL_LABELS.get(s.meal_type, s.meal_type), True),
            (str(s.days_count), False),
            (str(s.contact_total), False),
            (str(s.absence_total), False),
            (str(s.net_total), True),
            (f"{s.unit_price:.2f}", False),
            (f"{s.total_cost:.2f}", True),
        ]})
        total_contact += s.contact_total
        total_absence += s.absence_total
        total_net += s.net_total
        total_cost += s.total_cost
    totals = {"contact": total_contact, "absence": total_absence, "net": total_net, "cost": total_cost}
    return rows, totals


def _draw_monthly_summary_pdf_page(
    painter: QPainter, page_w: float, page_h: float,
    settings, month_label: str, summaries: List[MonthlyMealSummary], notes: str,
) -> None:
    margin = 32.0
    content_w = page_w - (margin * 2)

    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=margin, top=16.0,
        settings=settings, title=_TITLE,
    )

    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 20), f"{_TITLE} — {month_label}",
        size=12, color=COLOR_TEXT_SECONDARY, bold=True,
    )
    y += 26

    # Main table
    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 16), "أ — ملخص الوجبات والتكاليف",
        size=10, color=COLOR_ACCENT, bold=True,
    )
    y += 18

    main_rows, totals = _monthly_summary_main_rows(summaries)
    main_rows.append({
        "bg": COLOR_ACCENT_DEEP, "fg": "white",
        "cells": [
            ("الإجمالي", True), ("", False),
            (str(totals["contact"]), True), (str(totals["absence"]), True),
            (str(totals["net"]), True), ("", False), (f"{totals['cost']:.2f}", True),
        ],
    })
    y = _draw_rtl_table(
        painter, top=y, left=margin, content_w=content_w,
        headers=_MAIN_HEADERS, col_ratios=[0.14, 0.11, 0.14, 0.14, 0.14, 0.12, 0.21],
        rows=main_rows, header_bg=COLOR_ACCENT,
    )
    y += 16

    # Detail table
    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 16), "ب — التفصيل حسب الفئة",
        size=10, color=_MEAL_ASHA_PURPLE, bold=True,
    )
    y += 18

    sectors = [
        ("ابتدائي", "contact_primary", "absence_primary"),
        ("إعدادي", "contact_collegial", "absence_collegial"),
        ("تأهيلي", "contact_qualifying", "absence_qualifying"),
        ("معلمو الداخلية", "contact_monitors", "absence_monitors"),
    ]
    detail_rows = []
    for s in summaries:
        color = _MEAL_COLORS.get(s.meal_type, COLOR_ACCENT)
        meal_lbl = MEAL_LABELS.get(s.meal_type, s.meal_type)
        for index, (sector_label, contact_attr, absence_attr) in enumerate(sectors):
            contact, absence = getattr(s, contact_attr), getattr(s, absence_attr)
            detail_rows.append({"cells": [
                (meal_lbl if index == 0 else "", True), (sector_label, False),
                (str(contact), False), (str(absence), False),
                (str(max(0, contact - absence)), True),
            ], "fg": color if index == 0 else "#111827"})
        detail_rows.append({
            "bg": "#f0f9ff",
            "cells": [
                ("", False), (f"مجموع {meal_lbl}", True),
                (str(s.contact_total), True), (str(s.absence_total), True),
                (str(s.net_total), True),
            ],
        })
    y = _draw_rtl_table(
        painter, top=y, left=margin, content_w=content_w,
        headers=_DETAIL_HEADERS, col_ratios=[0.16, 0.22, 0.20, 0.20, 0.22],
        rows=detail_rows, header_bg=_MEAL_ASHA_PURPLE,
    )
    y += 18

    _draw_reception_pdf_text(
        painter, QRectF(margin, y, content_w, 20),
        f"إجمالي الوجبات المقدمة: {totals['net']:,}      —      التكلفة الإجمالية للشهر: {totals['cost']:,.2f} د.م",
        size=11, color=COLOR_ACCENT_DEEP, bold=True,
    )
    y += 28

    if notes.strip():
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 16), _LBL_NOTES,
            size=10, color=COLOR_TEXT_SECONDARY, bold=True,
        )
        y += 18
        _draw_reception_pdf_text(
            painter, QRectF(margin, y, content_w, 60), notes.strip(),
            size=9, color=COLOR_TEXT_PRIMARY,
            align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
        )


def _write_monthly_summary_pdf(
    path: Path, settings, month_label: str,
    summaries: List[MonthlyMealSummary], notes: str,
) -> None:
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
        _draw_monthly_summary_pdf_page(
            painter, float(writer.width()), float(writer.height()),
            settings, month_label, summaries, notes,
        )
    finally:
        painter.end()


# ── Excel export ─────────────────────────────────────────────────────────

def _write_monthly_summary_excel(
    path: Path, settings, month_label: str,
    summaries: List[MonthlyMealSummary], notes: str,
) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "الملخص الشهري"

    hdr_fill = PatternFill("solid", fgColor="1D9E75")
    tot_fill = PatternFill("solid", fgColor="177E5E")
    hdr_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    tot_font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    body_font = Font(name="Arial", size=11)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True, readingOrder=2)
    thin = Side(style="thin", color="94a3b8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:G1")
    ws["A1"] = f"{_TITLE} — {month_label}"
    ws["A1"].font = Font(name="Arial", bold=True, size=14, color="177E5E")
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 26

    ws.merge_cells("A2:G2")
    ws["A2"] = settings.school_name if settings else ""
    ws["A2"].alignment = center
    ws["A2"].font = Font(name="Arial", size=11, color="6B7280")

    row_num = 4
    ws.row_dimensions[row_num].height = 26
    for col_idx, text in enumerate(_MAIN_HEADERS, 1):
        cell = ws.cell(row=row_num, column=col_idx, value=text)
        cell.fill, cell.font, cell.alignment, cell.border = hdr_fill, hdr_font, center, border
    row_num += 1

    # Written as real NUMBERS, not the PDF's display strings: reusing
    # _monthly_summary_main_rows' pre-formatted text here made Excel treat
    # every count, price and cost as text, so a SUM over those columns
    # returned 0 for whoever opened the file.
    _main_rows, totals = _monthly_summary_main_rows(summaries)
    for summary in summaries:
        values = [
            MEAL_LABELS.get(summary.meal_type, summary.meal_type),
            summary.days_count, summary.contact_total,
            summary.absence_total, summary.net_total,
            round(summary.unit_price, 2), round(summary.total_cost, 2),
        ]
        for col_idx, value in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=value)
            cell.font, cell.alignment, cell.border = body_font, center, border
            if col_idx in (6, 7):
                cell.number_format = _EXCEL_MONEY_FORMAT
        row_num += 1

    total_row = [
        "الإجمالي", None, totals["contact"], totals["absence"],
        totals["net"], None, round(totals["cost"], 2),
    ]
    for col_idx, value in enumerate(total_row, 1):
        cell = ws.cell(row=row_num, column=col_idx, value=value)
        cell.fill, cell.font, cell.alignment, cell.border = tot_fill, tot_font, center, border
        if col_idx == 7:
            cell.number_format = _EXCEL_MONEY_FORMAT
    row_num += 3

    ws.merge_cells(f"A{row_num}:E{row_num}")
    ws.cell(row=row_num, column=1, value="التفصيل حسب الفئة").font = Font(name="Arial", bold=True, size=12, color=_MEAL_ASHA_PURPLE.lstrip("#"))
    row_num += 1
    for col_idx, text in enumerate(_DETAIL_HEADERS, 1):
        cell = ws.cell(row=row_num, column=col_idx, value=text)
        cell.fill = PatternFill("solid", fgColor=_MEAL_ASHA_PURPLE.lstrip("#"))
        cell.font, cell.alignment, cell.border = hdr_font, center, border
    row_num += 1

    sectors = [
        ("ابتدائي", "contact_primary", "absence_primary"),
        ("إعدادي", "contact_collegial", "absence_collegial"),
        ("تأهيلي", "contact_qualifying", "absence_qualifying"),
        ("معلمو الداخلية", "contact_monitors", "absence_monitors"),
    ]
    for s in summaries:
        meal_lbl = MEAL_LABELS.get(s.meal_type, s.meal_type)
        for index, (sector_label, contact_attr, absence_attr) in enumerate(sectors):
            contact, absence = getattr(s, contact_attr), getattr(s, absence_attr)
            values = [meal_lbl if index == 0 else "", sector_label, contact, absence, max(0, contact - absence)]
            for col_idx, value in enumerate(values, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=value)
                cell.font, cell.alignment, cell.border = body_font, center, border
            row_num += 1
        subtotal = ["", f"مجموع {meal_lbl}", s.contact_total, s.absence_total, s.net_total]
        for col_idx, value in enumerate(subtotal, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=value)
            cell.fill = PatternFill("solid", fgColor="E1F5EE")
            cell.font = Font(name="Arial", bold=True, size=11)
            cell.alignment, cell.border = center, border
        row_num += 1

    if notes.strip():
        row_num += 1
        ws.merge_cells(f"A{row_num}:G{row_num}")
        ws.cell(row=row_num, column=1, value=f"{_LBL_NOTES}: {notes.strip()}").alignment = Alignment(
            horizontal="right", vertical="center", wrap_text=True, readingOrder=2,
        )

    for col_idx, width in enumerate([16, 14, 14, 14, 14, 12, 16], 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
    ws.sheet_view.rightToLeft = True

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


class MonthlyReportScreen(QWidget):
    """Monthly report — aggregated summary with cost calculation."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._summaries: List[MonthlyMealSummary] = []
        self._saved_notes = ""
        self._build_ui()
        # Pre-fill selectors with current month and load its report
        # immediately — every sibling screen (daily/monthly reception,
        # etc.) shows real data on open rather than a blank header
        # waiting for an explicit "generate" click. Signals blocked here
        # since both combos are now wired to auto-regenerate on change —
        # without this, setting them would fire _generate() twice before
        # the explicit call below runs it a third time.
        now = datetime.date.today()
        self._month_combo.blockSignals(True)
        self._year_spin_combo.blockSignals(True)
        self._month_combo.setCurrentIndex(now.month - 1)
        self._year_spin_combo.setCurrentText(str(now.year))
        self._month_combo.blockSignals(False)
        self._year_spin_combo.blockSignals(False)
        self._generate()

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
        inner.addLayout(self._build_selector_bar())
        inner.addWidget(self._build_report_card())
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
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        col.addWidget(title)
        col.addWidget(sub)
        return col

    def _build_selector_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        # Month selector
        row.addWidget(QLabel(_LBL_MONTH,
                             styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))
        self._month_combo = QComboBox()
        self._month_combo.setMinimumHeight(36)
        self._month_combo.setMinimumWidth(130)
        for m in _ARABIC_MONTHS:
            self._month_combo.addItem(m)
        self._month_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:4px 8px; font-size:{FONT_BODY}px;"
        )
        self._month_combo.currentIndexChanged.connect(self._generate)
        row.addWidget(self._month_combo)

        # Year selector (combo of last 5 years)
        row.addWidget(QLabel(_LBL_YEAR,
                             styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};"))
        self._year_spin_combo = QComboBox()
        self._year_spin_combo.setMinimumHeight(36)
        self._year_spin_combo.setMinimumWidth(90)
        current_year = datetime.date.today().year
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_spin_combo.addItem(str(y))
        self._year_spin_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:4px 8px; font-size:{FONT_BODY}px;"
        )
        self._year_spin_combo.currentIndexChanged.connect(self._generate)
        row.addWidget(self._year_spin_combo)

        # Quick jump to months with data
        self._months_combo = QComboBox()
        self._months_combo.setMinimumHeight(36)
        self._months_combo.setMinimumWidth(160)
        self._months_combo.setPlaceholderText("الأشهر التي لها بيانات")
        self._months_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:4px 8px; font-size:{FONT_BODY}px;"
        )
        self._months_combo.currentTextChanged.connect(self._on_quick_jump)
        self._refresh_months_combo()
        row.addWidget(self._months_combo)

        row.addStretch()

        gen_btn = IconButton(
            _BTN_GENERATE, icon=_BTN_GENERATE_ICON, bg=COLOR_ACCENT, text_color="white",
            border_radius=7, padding_h=18, font_size=13, bold=True, min_height=38,
        )
        gen_btn.clicked.connect(self._generate)
        row.addWidget(gen_btn)

        export_btn = IconButton(
            _BTN_EXPORT, icon=_BTN_EXPORT_ICON, bg=COLOR_TEXT_PRIMARY, text_color="white",
            border_radius=7, padding_h=18, font_size=13, bold=True, min_height=38,
        )
        export_btn.clicked.connect(self._on_export)
        row.addWidget(export_btn)

        return row

    def _build_report_card(self) -> QFrame:
        self._report_card = QFrame()
        self._report_card.setStyleSheet(
            f"background:white; border-radius:12px; border:1px solid {COLOR_BORDER};"
        )
        self._report_layout = QVBoxLayout(self._report_card)
        self._report_layout.setContentsMargins(24, 20, 24, 20)
        self._report_layout.setSpacing(14)

        self._school_lbl = QLabel()
        self._school_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._school_lbl.setStyleSheet(
            f"font-size:{FONT_SECTION}px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};"
            f"border-bottom:2px solid {COLOR_ACCENT}; padding-bottom:10px;"
        )
        self._month_lbl = QLabel()
        self._month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_lbl.setStyleSheet(
            f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_SECONDARY}; padding-bottom:6px;"
        )

        self._no_data_lbl = EmptyState(_NO_DATA, icon="📊")

        self._report_layout.addWidget(self._school_lbl)
        self._report_layout.addWidget(self._month_lbl)
        self._report_layout.addWidget(self._no_data_lbl)

        # Placeholder for tables (rebuilt on generate)
        self._main_table:   Optional[QTableWidget] = None
        self._detail_table: Optional[QTableWidget] = None
        self._cost_box:     Optional[QFrame] = None
        self._main_title:   Optional[QLabel] = None
        self._detail_title: Optional[QLabel] = None

        return self._report_card

    def _build_notes_section(self) -> QGroupBox:
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
        v = QVBoxLayout(grp)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText(_NOTES_HINT)
        self._notes_edit.setMinimumHeight(110)
        self._notes_edit.setMaximumHeight(180)
        self._notes_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            f"padding:8px; font-size:{FONT_BODY}px;"
        )
        save_btn = IconButton(
            _BTN_SAVE_NOTES, icon=_BTN_SAVE_NOTES_ICON, bg=COLOR_SUCCESS, text_color="white",
            border_radius=6, padding_h=14, font_size=13, bold=True, min_height=36,
        )
        save_btn.setMaximumWidth(200)
        save_btn.clicked.connect(self._on_save_notes)
        v.addWidget(self._notes_edit)
        v.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return grp

    # ── Generate ───────────────────────────────────────────────────────────

    def _selected_month_str(self) -> str:
        """Return YYYY-MM string from the selectors."""
        year  = self._year_spin_combo.currentText()
        month = str(self._month_combo.currentIndex() + 1).zfill(2)
        return f"{year}-{month}"

    def _generate(self) -> None:
        month_str = self._selected_month_str()
        settings  = get_school_settings()

        # Update school header
        school_name = settings.school_name if settings else "—"
        school_year = settings.school_year if settings else "—"
        self._school_lbl.setText(f"{school_name}  —  السنة الدراسية: {school_year}")
        month_label = f"{_ARABIC_MONTHS[self._month_combo.currentIndex()]} {self._year_spin_combo.currentText()}"
        self._month_lbl.setText(f"{_TITLE} لشهر: {month_label}  ({_SUBTITLE})")

        # Build price map
        prices = {}
        if settings:
            prices = {
                MEAL_FTOUR: settings.price_ftour,
                MEAL_GHADA: settings.price_ghada,
                MEAL_ASHA:  settings.price_asha,
            }

        self._summaries = get_monthly_summaries(month_str, prices)

        has_data = any(s.contact_total > 0 or s.absence_total > 0
                       for s in self._summaries)
        self._no_data_lbl.setVisible(not has_data)

        # Remove old tables/titles. .hide() runs immediately; deleteLater()
        # only runs on the next event-loop iteration — with the month/year
        # combos now auto-regenerating on change (see _build_selector_bar),
        # two _generate() calls can land before that iteration happens
        # (confirmed via an offscreen render: rapid changes left the old
        # widgets ghosted, still painted at their last position, behind
        # the newly-built ones). Hiding immediately is what actually
        # prevents that, not the deferred deletion.
        for attr in ("_main_table", "_detail_table", "_cost_box", "_main_title", "_detail_title"):
            old = getattr(self, attr, None)
            if old is not None:
                old.hide()
                self._report_layout.removeWidget(old)
                old.deleteLater()
                setattr(self, attr, None)

        if has_data:
            self._main_table = self._build_main_table(self._summaries)
            self._detail_table = self._build_detail_table(self._summaries)
            self._cost_box = self._build_cost_box(self._summaries)
            self._main_title = QLabel(
                "أ — ملخص الوجبات والتكاليف",
                styleSheet=f"font-size:{FONT_BODY}px; font-weight:bold; color:{COLOR_ACCENT};",
            )
            self._report_layout.addWidget(self._main_title)
            self._report_layout.addWidget(self._main_table)
            self._detail_title = QLabel(
                "ب — التفصيل حسب الفئة",
                styleSheet=f"font-size:{FONT_BODY}px; font-weight:bold; color:{_MEAL_ASHA_PURPLE};",
            )
            self._report_layout.addWidget(self._detail_title)
            self._report_layout.addWidget(self._detail_table)
            self._report_layout.addWidget(self._cost_box)

        # Load notes
        self._saved_notes = get_monthly_report_notes(month_str)
        self._notes_edit.setPlainText(self._saved_notes)
        self._refresh_months_combo()

    def refresh(self) -> None:
        """Reload totals without discarding notes the user has not saved."""
        pending_notes = self._notes_edit.toPlainText()
        has_unsaved_notes = pending_notes.strip() != self._saved_notes.strip()
        self._generate()
        if has_unsaved_notes:
            self._notes_edit.setPlainText(pending_notes)

    # ── Table builders ─────────────────────────────────────────────────────

    def _build_main_table(self, summaries: List[MonthlyMealSummary]) -> QTableWidget:
        rows = len(summaries) + 1  # +1 grand total
        t = _styled_table(rows, len(_MAIN_HEADERS), _MAIN_HEADERS)

        total_contact = total_absence = total_net = total_cost = 0.0

        for i, s in enumerate(summaries):
            color = _MEAL_COLORS.get(s.meal_type, COLOR_ACCENT)
            t.setItem(i, 0, _titem(MEAL_LABELS.get(s.meal_type, s.meal_type), bold=True, fg=color))
            t.setItem(i, 1, _titem(str(s.days_count)))
            t.setItem(i, 2, _titem(str(s.contact_total)))
            t.setItem(i, 3, _titem(str(s.absence_total)))
            t.setItem(i, 4, _titem(str(s.net_total), bold=True))
            t.setItem(i, 5, _titem(f"{s.unit_price:.2f}"))
            t.setItem(i, 6, _titem(f"{s.total_cost:.2f}", bold=True))
            total_contact += s.contact_total
            total_absence += s.absence_total
            total_net     += s.net_total
            total_cost    += s.total_cost

        # Grand total
        r = len(summaries)
        t.setItem(r, 0, _titem("الإجمالي", bold=True, bg=COLOR_ACCENT_DEEP, fg="white"))
        t.setItem(r, 1, _titem("", bg=COLOR_ACCENT_DEEP))
        t.setItem(r, 2, _titem(f"{int(total_contact):,}", bold=True, bg=COLOR_ACCENT_DEEP, fg="white"))
        t.setItem(r, 3, _titem(f"{int(total_absence):,}", bold=True, bg=COLOR_ACCENT_DEEP, fg="white"))
        t.setItem(r, 4, _titem(f"{int(total_net):,}",     bold=True, bg=COLOR_ACCENT_DEEP, fg="white"))
        t.setItem(r, 5, _titem("", bg=COLOR_ACCENT_DEEP))
        t.setItem(r, 6, _titem(f"{total_cost:,.2f}", bold=True, bg=COLOR_ACCENT, fg="white"))

        _size_table_to_contents(t)
        return t

    def _build_detail_table(self, summaries: List[MonthlyMealSummary]) -> QTableWidget:
        """Per-meal, per-sector breakdown table. Covers all 3 real cycles
        (ابتدائي/إعدادي/تأهيلي per the matama skill's own vocabulary) plus
        معلمو الداخلية — an earlier version of this table skipped
        ابتدائي entirely, so a school with primary-cycle boarders would
        see per-sector rows that didn't add up to the "مجموع" subtotal
        (which DOES include primary, via contact_total/absence_total)."""
        sectors = [
            ("ابتدائي", "contact_primary", "absence_primary"),
            ("إعدادي", "contact_collegial", "absence_collegial"),
            ("تأهيلي", "contact_qualifying", "absence_qualifying"),
            ("معلمو الداخلية", "contact_monitors", "absence_monitors"),
        ]
        rows = len(summaries) * (len(sectors) + 1)  # +1 subtotal per meal
        t = _styled_table(rows, len(_DETAIL_HEADERS), _DETAIL_HEADERS, _MEAL_ASHA_PURPLE)

        row = 0
        for s in summaries:
            color = _MEAL_COLORS.get(s.meal_type, COLOR_ACCENT)
            meal_lbl = MEAL_LABELS.get(s.meal_type, s.meal_type)

            for index, (sector_label, contact_attr, absence_attr) in enumerate(sectors):
                contact = getattr(s, contact_attr)
                absence = getattr(s, absence_attr)
                t.setItem(row, 0, _titem(meal_lbl if index == 0 else "", bold=True, fg=color))
                t.setItem(row, 1, _titem(sector_label))
                t.setItem(row, 2, _titem(str(contact)))
                t.setItem(row, 3, _titem(str(absence)))
                t.setItem(row, 4, _titem(str(max(0, contact - absence)), bold=True))
                row += 1

            # Meal subtotal
            t.setItem(row, 0, _titem(""))
            t.setItem(row, 1, _titem(f"مجموع {meal_lbl}", bold=True, bg="#f0f9ff"))
            t.setItem(row, 2, _titem(str(s.contact_total), bold=True, bg="#f0f9ff"))
            t.setItem(row, 3, _titem(str(s.absence_total), bold=True, bg="#f0f9ff"))
            t.setItem(row, 4, _titem(str(s.net_total), bold=True, bg=COLOR_PANEL_ALT, fg=COLOR_ACCENT_DEEP))
            row += 1

        _size_table_to_contents(t)
        return t

    def _build_cost_box(self, summaries: List[MonthlyMealSummary]) -> QFrame:
        """A summary cost card at the bottom of the report."""
        total_cost = sum(s.total_cost for s in summaries)
        total_net  = sum(s.net_total  for s in summaries)

        frame = QFrame()
        frame.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLOR_ACCENT_DEEP}, stop:1 {COLOR_SIDEBAR_BG});"
            "border-radius:10px;"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(24, 16, 24, 16)

        left = QVBoxLayout()
        lbl1 = QLabel("إجمالي الوجبات المقدمة")
        lbl1.setStyleSheet(f"color:rgba(255,255,255,0.8); font-size:{FONT_LABEL}px;")
        lbl2 = QLabel(f"{total_net:,}")
        f = QFont(); f.setPointSize(22); f.setBold(True)
        lbl2.setFont(f)
        lbl2.setStyleSheet("color:white;")
        left.addWidget(lbl1)
        left.addWidget(lbl2)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl3 = QLabel("التكلفة الإجمالية للشهر")
        lbl3.setStyleSheet(f"color:rgba(255,255,255,0.8); font-size:{FONT_LABEL}px;")
        lbl3.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lbl4 = QLabel(f"{total_cost:,.2f} د.م")
        g = QFont(); g.setPointSize(22); g.setBold(True)
        lbl4.setFont(g)
        lbl4.setStyleSheet("color:#fde68a;")  # amber for cost
        lbl4.setAlignment(Qt.AlignmentFlag.AlignLeft)
        right.addWidget(lbl3)
        right.addWidget(lbl4)

        row.addLayout(left)
        row.addStretch()
        row.addLayout(right)
        return frame

    # ── Helpers ────────────────────────────────────────────────────────────

    def _refresh_months_combo(self) -> None:
        self._months_combo.blockSignals(True)
        self._months_combo.clear()
        for m in get_months_with_data():
            self._months_combo.addItem(m)
        self._months_combo.blockSignals(False)

    def _on_quick_jump(self, month_str: str) -> None:
        if not month_str or len(month_str) != 7:
            return
        try:
            year, month = month_str.split("-")
            self._year_spin_combo.blockSignals(True)
            self._month_combo.blockSignals(True)
            self._year_spin_combo.setCurrentText(year)
            self._month_combo.setCurrentIndex(int(month) - 1)
            self._year_spin_combo.blockSignals(False)
            self._month_combo.blockSignals(False)
            self._generate()
        except (ValueError, IndexError):
            _LOGGER.warning("Ignoring invalid quick-jump month: %s", month_str)

    def _on_save_notes(self) -> None:
        try:
            notes = self._notes_edit.toPlainText().strip()
            save_monthly_report_notes(self._selected_month_str(), notes)
            self._saved_notes = notes
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_export(self) -> None:
        if not self._summaries:
            QMessageBox.warning(self, "تنبيه", _EXPORT_NO_DATA)
            return

        fmt = ask_choice(
            self, _EXPORT_CHOICE_TITLE, _EXPORT_CHOICE_TEXT,
            [("PDF", "pdf"), ("Excel", "xlsx"), ("إلغاء", "cancel")],
        )
        if fmt is None:
            return

        month_label = f"{_ARABIC_MONTHS[self._month_combo.currentIndex()]} {self._year_spin_combo.currentText()}"
        default_name = f"الملخص_الشهري_{self._selected_month_str()}.{fmt}"
        filter_str = "PDF Files (*.pdf)" if fmt == "pdf" else "Excel Files (*.xlsx)"
        path_str, _ = QFileDialog.getSaveFileName(self, _BTN_EXPORT, str(Path.home() / default_name), filter_str)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != f".{fmt}":
            path = path.with_suffix(f".{fmt}")

        try:
            settings = get_school_settings()
            notes = self._notes_edit.toPlainText()
            if fmt == "pdf":
                _write_monthly_summary_pdf(path, settings, month_label, self._summaries, notes)
            else:
                _write_monthly_summary_excel(path, settings, month_label, self._summaries, notes)
            QMessageBox.information(self, "تم", f"{_EXPORT_SAVED}{path}")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"{_EXPORT_ERROR}\n{exc}")
