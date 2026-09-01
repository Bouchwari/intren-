"""
src/ui/quarterly_reception_screen.py
Quarterly reception attestation (محضر التسلم الفصلي) — matches
templets/LOT 02 attestation de reception trimestrielle
restauration...xlsx: real, computed NET meal totals (contact − absence)
for 3 consecutive months, split by the catering contract's own LOT
grouping ("901 PRIMAIRE ET COLLEGIAL" = ابتدائي+إعدادي+معلمو الداخلية,
"902 QUALIFIANT" = تأهيلي alone — see get_daily_meals_by_lot_for_month's
docstring for why monitors fold into 901, a disclosed assumption since
the real contract's own LOT split for monitors wasn't given). This is
the document whose total is what "the administration pays from" — every
number here is real, computed from daily contact/absence records, never
estimated or invented, unlike بيان المصاريف's per-student breakdown.

Ramadan columns (سحور + الإفطار) appear on a month's sheet when that
month actually contains Ramadan, decided from the Ramadan period saved
in Settings via core.ramadan — matching the real template, whose March
2026 sheet is the only one carrying them. They carry the real إفطار/سحور
counts recorded on ورقة الاتصال for those days, netted against absence
exactly like the normal three meals.

Excel-only export, matching بيان المصاريف's own precedent — 4 sheets:
one daily grid per month plus a signed recap sheet mirroring the real
attestation's legal text and signer table.
"""
import calendar
import datetime
import logging
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_ACCENT_DEEP, COLOR_BORDER, COLOR_PANEL_ALT,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_LABEL,
)
from core.models import SchoolSettings
from core.ramadan import month_has_ramadan, ramadan_days_in_month
from data.database import get_ramadan_overrides, get_school_settings
from data.monthly_repo import get_daily_meals_by_lot_for_month
from data.students_repo import get_all_students
from ui.expense_roster_export import write_expense_roster_excel
from ui.monthly_report_screen import _size_table_to_contents
from ui.widgets.icon_button import IconButton

if TYPE_CHECKING:  # openpyxl is imported lazily; these are annotations only
    from openpyxl.cell.cell import Cell
    from openpyxl.styles import Border
    from openpyxl.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

# ── Arabic strings ──────────────────────────────────────────────────────────
_TITLE      = "الوثائق الفصلية"
_SUBTITLE   = ("وثيقتا الفصل الرسميتان لثلاثة أشهر متتالية: "
               "بيانات المصاريف (لائحة التلاميذ) ومحضر التسلم (Attestation de réception)")
_BTN_GEN    = "توليد المحضر"
_BTN_GEN_ICON = "🔄"
_BTN_EXCEL  = "تصدير محضر التسلم"
_BTN_ROSTER = "تصدير بيانات المصاريف"
_BTN_ROSTER_ICON = "👥"
_ROSTER_SAVED = "تم تصدير بيانات المصاريف بنجاح إلى:\n"
_ROSTER_NO_STUDENTS = ("لا توجد لائحة تلاميذ.\n"
                       "استورد لائحة التلاميذ أولاً من صفحة «لائحة التلاميذ».")
_ROSTER_HINT = ("بيانات المصاريف تُملأ بأسماء التلاميذ الحقيقية؛ "
                "خانات عدد الوجبات تُترك فارغة لتملأها بخط اليد.")
_BTN_EXCEL_ICON = "📊"
_LBL_YEAR   = "السنة:"
_LBL_FIRST_MONTH = "الشهر الأول من الفصل:"
_RAMADAN_MONTHS_FMT = ("رمضان خلال هذا الفصل: {months} — تُضاف أعمدة السحور "
                       "والإفطار تلقائياً لهذه الأشهر.")
_RAMADAN_NONE = ("لا يوجد رمضان في هذا الفصل. حدّد مدة رمضان من «الإعدادات» "
                 "لتتحول الوثائق تلقائياً.")
_EXCEL_SAVED = "تم تصدير المحضر بنجاح إلى:\n"
_EXCEL_NO_DATA = ("لا توجد وجبات مسجلة في هذا الفصل.\n"
                  "أدخل بيانات ورقة الاتصال اليومية أولاً، ثم أعد المحاولة.")
_EXCEL_NO_OPENPYXL = "مكتبة openpyxl غير مثبتة.\nثبّتها بـ:  pip install openpyxl"
_EXCEL_PERMISSION = ("لا يمكن الحفظ في هذا المجلد.\n"
                     "اختر مجلدًا آخر (مثل سطح المكتب) ثم أعد المحاولة.")
_EXCEL_FAILED = "تعذر تصدير المحضر. تحقق من المكان المختار ثم أعد المحاولة."

_ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر",
]

_LOT901_LABEL = "ابتدائي + إعدادي + معلمو الداخلية (901)"
_LOT902_LABEL = "تأهيلي (902)"
# Short column captions — spelling the full LOT label into all six headers made
# the table wider than the window, which forced a horizontal scrollbar and
# clipped the الإجمالي row. The legend below the table carries the full meaning.
_LOT901_SHORT = "901"
_LOT902_SHORT = "902"
_LOT_LEGEND = f"901 = {_LOT901_LABEL}      ·      902 = {_LOT902_LABEL}"

_LOGGER = logging.getLogger(__name__)


def _month_add(year: int, month: int, offset: int) -> tuple:
    """Return (year, month) for `offset` months after (year, month),
    rolling over into the next year(s) — a quarter can start in any
    month, e.g. November 2026 → December 2026 → January 2027."""
    zero_based = (month - 1) + offset
    return year + zero_based // 12, zero_based % 12 + 1


def _quarter_months(year: int, first_month: int) -> List[tuple]:
    return [_month_add(year, first_month, i) for i in range(3)]


def _titem(text: str, bold: bool = False, bg: str = "", fg: str = "") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    f = QFont(); f.setBold(bold)
    item.setFont(f)
    if bg:
        item.setBackground(QColor(bg))
    if fg:
        item.setForeground(QColor(fg))
    return item


class QuarterlyReceptionScreen(QWidget):
    """Quarterly reception attestation — 3-month LOT-grouped net meal totals."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._quarter_data: List[dict] = []  # one entry per month: {month, label, is_ramadan, days}
        self._build_ui()
        now = datetime.date.today()
        # Default to the calendar quarter today falls in (Jan/Apr/Jul/Oct start).
        # Signals are blocked while pre-selecting: both combos are wired to
        # regenerate on change, so without this each setter would fire a full
        # 3-month rebuild before the explicit _generate() below runs a third
        # one (the same fix already applied in بيان المصاريف and siblings).
        quarter_start = ((now.month - 1) // 3) * 3 + 1
        self._year_combo.blockSignals(True)
        self._first_month_combo.blockSignals(True)
        self._year_combo.setCurrentText(str(now.year))
        self._first_month_combo.setCurrentIndex(quarter_start - 1)
        self._year_combo.blockSignals(False)
        self._first_month_combo.blockSignals(False)
        self._generate()

    def refresh(self) -> None:
        """Re-read the database whenever the user navigates to this screen.

        MainWindow builds every screen once at startup and only re-reads one
        through this hook (see MainWindow._navigate). Without it the quarter
        stayed frozen at whatever the database held when the app launched, so
        meals entered during the session were silently missing from the
        exported attestation — on a document the administration pays against.
        """
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
        inner.setSpacing(18)

        inner.addLayout(self._build_header())
        inner.addLayout(self._build_selector_bar())
        inner.addLayout(self._build_ramadan_row())
        inner.addWidget(self._build_table_card())
        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(17); f.setBold(True); title.setFont(f)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        sub = QLabel(_SUBTITLE)
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        sub.setWordWrap(True)
        col.addWidget(title); col.addWidget(sub)
        return col

    def _build_selector_bar(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)

        def lbl(t: str) -> QLabel:
            return QLabel(t, styleSheet=f"font-size:{FONT_BODY}px; color:{COLOR_TEXT_PRIMARY};")

        row.addWidget(lbl(_LBL_YEAR))
        self._year_combo = QComboBox()
        self._year_combo.setMinimumHeight(36); self._year_combo.setMinimumWidth(90)
        cur_year = datetime.date.today().year
        for y in range(cur_year + 1, cur_year - 5, -1):
            self._year_combo.addItem(str(y))
        self._year_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:{FONT_BODY}px;")
        self._year_combo.currentIndexChanged.connect(self._generate)
        row.addWidget(self._year_combo)

        row.addWidget(lbl(_LBL_FIRST_MONTH))
        self._first_month_combo = QComboBox()
        self._first_month_combo.setMinimumHeight(36); self._first_month_combo.setMinimumWidth(130)
        for m in _ARABIC_MONTHS:
            self._first_month_combo.addItem(m)
        self._first_month_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:{FONT_BODY}px;")
        self._first_month_combo.currentIndexChanged.connect(self._generate)
        row.addWidget(self._first_month_combo)
        row.addStretch()

        gen_btn = IconButton(
            _BTN_GEN, icon=_BTN_GEN_ICON, bg=COLOR_ACCENT, text_color="white",
            border_radius=7, padding_h=18, font_size=13, bold=True, min_height=38,
        )
        gen_btn.clicked.connect(self._generate)
        row.addWidget(gen_btn)

        roster_btn = IconButton(
            _BTN_ROSTER, icon=_BTN_ROSTER_ICON, bg=COLOR_ACCENT_DEEP,
            text_color="white", border_radius=7, padding_h=14, font_size=13,
            bold=True, min_height=38,
        )
        roster_btn.clicked.connect(self._export_roster)
        row.addWidget(roster_btn)

        xls_btn = IconButton(
            _BTN_EXCEL, icon=_BTN_EXCEL_ICON, bg="#16a34a", text_color="white",
            border_radius=7, padding_h=14, font_size=13, bold=True, min_height=38,
        )
        xls_btn.clicked.connect(self._export_excel)
        row.addWidget(xls_btn)
        return row

    def _build_ramadan_row(self) -> QHBoxLayout:
        """Shows which months of the quarter fall in Ramadan. This is read
        from the Ramadan period in Settings rather than ticked by hand — the
        earlier manual checkboxes were positional, so a tick could follow the
        slot onto an unrelated month when the quarter changed."""
        row = QHBoxLayout(); row.setSpacing(18)
        self._ramadan_label = QLabel("")
        self._ramadan_label.setWordWrap(True)
        self._ramadan_label.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        row.addWidget(self._ramadan_label)
        row.addStretch()
        return row

    def _build_table_card(self) -> QGroupBox:
        grp = QGroupBox("ملخص الفصل — عدد الوجبات الصافي (حضور − غياب)")
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
        headers = [
            "الشهر",
            f"فطور {_LOT901_SHORT}", f"غداء {_LOT901_SHORT}", f"عشاء {_LOT901_SHORT}",
            f"فطور {_LOT902_SHORT}", f"غداء {_LOT902_SHORT}", f"عشاء {_LOT902_SHORT}",
        ]
        self._table = QTableWidget(0, len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.verticalHeader().setVisible(False)
        # Stretch (not ResizeToContents + stretchLastSection) so the seven
        # columns share the width evenly — otherwise the final column absorbs
        # all the slack and ends up several times wider than its siblings.
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                font-size:{FONT_LABEL}px; background:white;
                alternate-background-color:{COLOR_PANEL_ALT};
                gridline-color:{COLOR_BORDER};
            }}
            QHeaderView::section {{
                background:{COLOR_ACCENT}; color:white;
                padding:8px 8px; border:none;
                font-weight:bold; font-size:{FONT_CAPTION}px;
            }}
            QTableWidget::item {{ padding:6px 8px; }}
        """)
        layout.addWidget(self._table)
        legend = QLabel(_LOT_LEGEND)
        legend.setWordWrap(True)
        legend.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        layout.addWidget(legend)
        hint = QLabel(_ROSTER_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        layout.addWidget(hint)
        return grp

    # ── Generate ───────────────────────────────────────────────────────────

    def _selected_quarter(self) -> List[tuple]:
        year = int(self._year_combo.currentText())
        first_month = self._first_month_combo.currentIndex() + 1
        return _quarter_months(year, first_month)

    def _generate(self) -> None:
        months = self._selected_quarter()
        month_keys = [f"{y:04d}-{m:02d}" for y, m in months]

        # Which months contain Ramadan comes from the period saved in
        # Settings (with any per-day corrections applied), not from a manual
        # tick — so every document in the app agrees on the same answer.
        settings = get_school_settings()
        overrides = get_ramadan_overrides()

        self._quarter_data = []
        ramadan_labels: List[str] = []
        for (y, m), month_str in zip(months, month_keys):
            label = f"{_ARABIC_MONTHS[m - 1]} {y}"
            is_ramadan = month_has_ramadan(month_str, settings, overrides)
            if is_ramadan:
                ramadan_labels.append(label)
            self._quarter_data.append({
                "month": month_str,
                "label": label,
                "is_ramadan": is_ramadan,
                "days": get_daily_meals_by_lot_for_month(month_str),
            })

        self._ramadan_label.setText(
            _RAMADAN_MONTHS_FMT.format(months="، ".join(ramadan_labels))
            if ramadan_labels else _RAMADAN_NONE
        )
        self._populate_table()

    def _populate_table(self) -> None:
        rows = len(self._quarter_data) + 1  # +1 quarterly total
        self._table.setRowCount(rows)

        totals = {k: 0 for k in ("lot901_ftour", "lot901_ghada", "lot901_asha",
                                  "lot902_ftour", "lot902_ghada", "lot902_asha")}
        for i, month_info in enumerate(self._quarter_data):
            month_totals = {k: sum(d[k] for d in month_info["days"]) for k in totals}
            self._table.setItem(i, 0, _titem(month_info["label"], bold=True, fg=COLOR_ACCENT_DEEP))
            for col, key in enumerate((
                "lot901_ftour", "lot901_ghada", "lot901_asha",
                "lot902_ftour", "lot902_ghada", "lot902_asha",
            ), start=1):
                self._table.setItem(i, col, _titem(f"{month_totals[key]:,}"))
                totals[key] += month_totals[key]

        r = rows - 1
        bg, fg = COLOR_ACCENT_DEEP, "white"
        self._table.setItem(r, 0, _titem("إجمالي الفصل", bold=True, bg=bg, fg=fg))
        for col, key in enumerate((
            "lot901_ftour", "lot901_ghada", "lot901_asha",
            "lot902_ftour", "lot902_ghada", "lot902_asha",
        ), start=1):
            self._table.setItem(r, col, _titem(f"{totals[key]:,}", bold=True, bg=bg, fg=fg))

        _size_table_to_contents(self._table)

    # ── Excel export ───────────────────────────────────────────────────────

    def _export_excel(self) -> None:
        # The quarter is always generated by now (__init__ and both combos do
        # it), so an empty result means the quarter genuinely has no meals —
        # telling the user to "generate first" would send them in a loop.
        if not any(
            any(d[k] for d in m["days"] for k in
                ("lot901_ftour", "lot901_ghada", "lot901_asha",
                 "lot902_ftour", "lot902_ghada", "lot902_asha"))
            for m in self._quarter_data
        ):
            QMessageBox.warning(self, "تنبيه", _EXCEL_NO_DATA)
            return

        default_name = f"محضر_التسلم_الفصلي_{self._quarter_data[0]['month']}.xlsx"
        path_str, _ = QFileDialog.getSaveFileName(
            self, _BTN_EXCEL, str(Path.home() / default_name), "Excel Files (*.xlsx)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        try:
            settings = get_school_settings()
            _write_quarterly_reception_excel(path, settings, self._quarter_data)
            QMessageBox.information(self, "تم", f"{_EXCEL_SAVED}{path}")
        except ImportError:
            _LOGGER.exception("openpyxl is unavailable — cannot export the attestation")
            QMessageBox.critical(self, "خطأ", _EXCEL_NO_OPENPYXL)
        except PermissionError:
            _LOGGER.exception("Permission denied writing the attestation to %s", path)
            QMessageBox.critical(self, "خطأ", _EXCEL_PERMISSION)
        except Exception:
            # Technical detail goes to the log; the teacher gets Arabic.
            _LOGGER.exception("Failed to export the quarterly attestation to %s", path)
            QMessageBox.critical(self, "خطأ", _EXCEL_FAILED)

    def _export_roster(self) -> None:
        """Export بيانات المصاريف — the official per-student quarterly roster,
        one sheet per cycle, for the same quarter shown on screen."""
        students = get_all_students()
        if not students:
            QMessageBox.warning(self, "تنبيه", _ROSTER_NO_STUDENTS)
            return

        months = self._selected_quarter()
        default_name = f"بيانات_المصاريف_{months[0][0]}-{months[0][1]:02d}.xlsx"
        path_str, _ = QFileDialog.getSaveFileName(
            self, _BTN_ROSTER, str(Path.home() / default_name), "Excel Files (*.xlsx)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        try:
            has_ramadan = any(m["is_ramadan"] for m in self._quarter_data)
            write_expense_roster_excel(
                path, get_school_settings(), students, months, has_ramadan)
            QMessageBox.information(self, "تم", f"{_ROSTER_SAVED}{path}")
        except ImportError:
            _LOGGER.exception("openpyxl is unavailable — cannot export the roster")
            QMessageBox.critical(self, "خطأ", _EXCEL_NO_OPENPYXL)
        except PermissionError:
            _LOGGER.exception("Permission denied writing the roster to %s", path)
            QMessageBox.critical(self, "خطأ", _EXCEL_PERMISSION)
        except Exception:
            _LOGGER.exception("Failed to export بيانات المصاريف to %s", path)
            QMessageBox.critical(self, "خطأ", _EXCEL_FAILED)


# ── Excel export — matches the real template cell-for-cell ─────────────────
#
# Structure below was read directly out of
# `templets/LOT 02 attestation de reception trimestrielle restauration
# 01-02-03-2026.xlsx`, not approximated. The first version of this export
# invented its own layout (LOTs stacked vertically, Arabic sheet names) and
# the user rightly rejected it as "not like the template at all". The real
# shape is:
#
#   * One sheet per month, named "MOIS {MM} {YYYY}" — e.g. "MOIS 01 2026".
#   * Each month sheet carries the two catering LOTs SIDE BY SIDE:
#       A-D  901 (PRIMAIRE ET COLLEGIAL) — JOURS / PETIT DEJ, / DEJEUNER / DINER
#       E    coloured spacer column, merged from row 1 down to the TOTAL row
#       F-I  902 (QUALIFIANT) — the same four columns
#     Column A prints real dates in the template's own long-date format;
#     every other JOURS column prints plain day numbers (1, 2, 3...), which
#     is exactly the asymmetry the source file has.
#   * A Ramadan month does NOT add columns to those blocks — it adds two
#     MORE blocks to their right, which is why the real March sheet runs out
#     to column Q while January stops at I:
#       J    plain gap column (no fill)
#       K-M  901 — JOURS / FTOUR / SHOUR
#       N    coloured spacer
#       O-Q  902 — JOURS / FTOUR / SHOUR
#     FTOUR/SHOUR cells are left EMPTY on purpose. The app has never tracked
#     Ramadan meal attendance anywhere (config/settings.py defines no
#     MEAL_IFTAR/MEAL_SUHOOR — only Ramadan *price* fields), so there is no
#     real number to put there. On a document the administration pays
#     against, a blank the user fills in is the only honest option.
#   * TOTAL rows are live =SUM() formulas, and the recap's meal figures are
#     live cross-sheet formulas, both exactly as the template does it — so
#     the workbook stays checkable and recalculable rather than frozen.

_SHEET_RECAP = "RECAP A IMPRIMER"
_SUBTITLE_FR = "Le nombre des repas servis\xa0"
_LOT901_FR = "901 (PRIMAIRE ET COLLEGIAL)"
_LOT902_FR = "902 (QUALIFIANT)"
_MEAL_HEADERS_FR = ["PETIT DEJ,", "DEJEUNER", "DINER"]
_RAMADAN_HEADERS_FR = ["FTOUR", "SHOUR"]

_FRENCH_MONTHS = [
    "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN",
    "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE",
]

# The template's own long-date format on column A.
_DATE_NUMBER_FORMAT = r"[$-F800]dddd\,\ mmmm\ dd\,\ yyyy"

# Theme colours resolved from the template's own theme1.xml, so these are the
# real fills rather than lookalikes: accent4 FFC000 lightened 80%, accent6
# 70AD47 lightened 60%, accent5 5B9BD5 lightened 40%.
_FILL_LOT_HEADER = "FFF2CC"
_FILL_SUBTITLE = "C5E0B4"
_FILL_SPACER = "9DC3E6"
_FILL_TOTAL_LABEL = "FFC000"
_FILL_TOTAL_VALUE = "FFF2CC"
_FILL_FTOUR_HEADER = "FA9EC8"
_FILL_SHOUR_HEADER = "FFFF00"
_FILL_RECAP_SIGNER = "D9D9D9"
_FILL_RECAP_TABLE = "E2EFDA"

_RAMADAN_HEADER_FILLS = {
    "FTOUR": _FILL_FTOUR_HEADER,
    "SHOUR": _FILL_SHOUR_HEADER,
}

# The template green-highlights every Sunday (verified across all three of
# its month sheets — Jan 4/11/18/25, Feb 1/8/15/22, Mar 1/8/15/22/29 are all
# Sundays). In the two main blocks the whole row is filled including the
# JOURS column; in the Ramadan blocks only the meal columns are, which is the
# template's own small inconsistency, reproduced here rather than tidied up.
_FILL_SUNDAY = "92D050"

_FIRST_DATA_ROW = 4

# Row heights read straight off the template's RECAP sheet. They matter: this
# is the one sheet meant to be printed and signed, and without them the tuned
# rows (the wrapped marché paragraph, the signature boxes) collapse to the
# 15pt default and the attestation spills onto extra sheets of paper.
_RECAP_ROW_HEIGHTS = {
    5: 21.75, 6: 16.5, 7: 24.75, 8: 17.25, 9: 24.0, 10: 30.0, 11: 30.0,
    12: 4.5, 13: 21.75, 14: 21.75, 15: 34.5, 16: 26.15, 17: 44.25, 18: 20.15,
    19: 25.5, 20: 36.75, 21: 18.0, 22: 18.0, 23: 18.0, 24: 18.0, 25: 18.0,
    26: 14.25, 27: 5.25, 28: 26.25, 29: 35.25, 30: 18.75, 31: 18.75,
    32: 18.75, 33: 18.75, 34: 18.75, 35: 13.5, 36: 16.0, 37: 37.5, 38: 20.0,
    39: 6.75, 40: 28.5, 41: 15.0, 42: 15.0, 43: 23.25, 44: 20.0,
}

# A4 at the template's own margins. openpyxl writes no page setup at all by
# default, which falls back to the printer's paper (often US Letter) at 100%
# with ~0.75in margins — enough to break the recap across 2-3 pages.
_PAPER_A4 = 9
_PRINT_MARGIN_SIDE = 0.0393700787
_PRINT_MARGIN_TOP = 0.157480315


def _apply_print_setup(
    ws: "Worksheet", *, scale: int | None = None, tight_margins: bool = False,
) -> None:
    """Give a sheet the template's A4 portrait page geometry.

    Only the RECAP sheet gets the scale and the near-zero margins — verified
    against the template's own XML, where the month sheets keep Excel's
    default 0.7in/0.75in margins and no scaling.
    """
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = _PAPER_A4
    if scale is not None:
        ws.page_setup.scale = scale
    if tight_margins:
        ws.page_margins.left = ws.page_margins.right = _PRINT_MARGIN_SIDE
        ws.page_margins.top = ws.page_margins.bottom = _PRINT_MARGIN_TOP
        ws.page_margins.header = ws.page_margins.footer = 0


def _thin_border() -> "Border":
    from openpyxl.styles import Border, Side
    side = Side(style="thin", color="FF000000")
    return Border(left=side, right=side, top=side, bottom=side)


def _styled(
    ws: "Worksheet", row: int, col: int, value: object = None, *,
    fill: str = "", bold: bool = False, size: int = 11,
    font_name: str = "Calibri", horizontal: str = "center",
    numfmt: str = "", border: bool = True, wrap: bool = False,
) -> "Cell":
    """Write one cell with the template's own look. `horizontal=""` leaves
    alignment unset, matching the template's plain data cells (numbers fall
    back to Excel's default right alignment there)."""
    from openpyxl.styles import Alignment, Font, PatternFill

    cell = ws.cell(row=row, column=col)
    if value is not None:
        cell.value = value
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.font = Font(name=font_name, bold=bold, size=size)
    if horizontal:
        cell.alignment = Alignment(horizontal=horizontal, vertical="center", wrap_text=wrap)
    if border:
        cell.border = _thin_border()
    if numfmt:
        cell.number_format = numfmt
    return cell


def _write_lot_block(
    ws: "Worksheet", *, start_col: int, lot_title: str, meal_headers: List[str],
    day_values: List[list], total_row: int, year: int = 0, month: int = 0,
    date_column: bool = False, header_fills: dict | None = None,
    sunday_days: set | None = None, highlight_jours: bool = True,
    day_numbers: list | None = None,
) -> None:
    """Write one LOT block — title, subtitle, header row, per-day rows and a
    TOTAL row of =SUM() formulas — starting at `start_col`."""
    from openpyxl.utils import get_column_letter

    last_col = start_col + len(meal_headers)

    ws.merge_cells(start_row=1, start_column=start_col, end_row=1, end_column=last_col)
    ws.merge_cells(start_row=2, start_column=start_col, end_row=2, end_column=last_col)
    for col in range(start_col, last_col + 1):
        _styled(ws, 1, col, lot_title if col == start_col else None,
                fill=_FILL_LOT_HEADER, bold=True)
        _styled(ws, 2, col, _SUBTITLE_FR if col == start_col else None,
                fill=_FILL_SUBTITLE, bold=True, font_name="Arial")

    _styled(ws, 3, start_col, "JOURS", bold=True)
    for offset, header in enumerate(meal_headers):
        _styled(ws, 3, start_col + 1 + offset, header, bold=True,
                fill=(header_fills or {}).get(header, ""))

    sundays = sunday_days or set()
    for index, values in enumerate(day_values):
        row = _FIRST_DATA_ROW + index
        is_sunday = (index + 1) in sundays
        day_fill = _FILL_SUNDAY if is_sunday else ""
        if date_column:
            _styled(ws, row, start_col, datetime.date(year, month, index + 1),
                    bold=True, numfmt=_DATE_NUMBER_FORMAT,
                    fill=day_fill if highlight_jours else "")
        else:
            # day_numbers lets a block leave a day blank — the Ramadan block
            # must not number days that are not part of Ramadan.
            number = day_numbers[index] if day_numbers is not None else index + 1
            _styled(ws, row, start_col, number, bold=True,
                    fill=day_fill if highlight_jours else "")
        for offset, value in enumerate(values):
            _styled(ws, row, start_col + 1 + offset, value, horizontal="", fill=day_fill)

    _styled(ws, total_row, start_col, "TOTAL", fill=_FILL_TOTAL_LABEL, bold=True)
    for offset in range(len(meal_headers)):
        col = start_col + 1 + offset
        letter = get_column_letter(col)
        _styled(ws, total_row, col,
                f"=SUM({letter}{_FIRST_DATA_ROW}:{letter}{total_row - 1})",
                fill=_FILL_TOTAL_VALUE, bold=True)


def _write_spacer_column(ws: "Worksheet", col: int, total_row: int, width: float) -> None:
    """The template's coloured divider columns (E, and N on a Ramadan sheet),
    merged from row 1 down to the TOTAL row."""
    from openpyxl.utils import get_column_letter

    ws.merge_cells(start_row=1, start_column=col, end_row=total_row, end_column=col)
    for row in range(1, total_row + 1):
        _styled(ws, row, col, fill=_FILL_SPACER, bold=True)
    ws.column_dimensions[get_column_letter(col)].width = width


def _write_month_sheet(wb: "Workbook", month_info: dict) -> None:
    """Write one "MOIS MM YYYY" sheet, recording its title and TOTAL row on
    `month_info` so the recap sheet can point formulas at it."""
    year, month_num = (int(part) for part in month_info["month"].split("-"))
    days = month_info["days"]
    total_row = _FIRST_DATA_ROW + len(days)

    title = f"MOIS {month_num:02d} {year}"
    ws = wb.create_sheet(title=title)

    # weekday() == 6 is Sunday — the day the template green-highlights.
    sundays = {
        index + 1 for index in range(len(days))
        if datetime.date(year, month_num, index + 1).weekday() == 6
    }

    _write_lot_block(
        ws, start_col=1, lot_title=_LOT901_FR, meal_headers=_MEAL_HEADERS_FR,
        day_values=[[d["lot901_ftour"], d["lot901_ghada"], d["lot901_asha"]] for d in days],
        total_row=total_row, year=year, month=month_num, date_column=True,
        sunday_days=sundays,
    )
    _write_spacer_column(ws, 5, total_row, 4.8)
    _write_lot_block(
        ws, start_col=6, lot_title=_LOT902_FR, meal_headers=_MEAL_HEADERS_FR,
        day_values=[[d["lot902_ftour"], d["lot902_ghada"], d["lot902_asha"]] for d in days],
        total_row=total_row, sunday_days=sundays,
    )
    ws.column_dimensions["A"].width = 27.2
    ws.column_dimensions["B"].width = 9.7

    if month_info["is_ramadan"]:
        # Ramadan quantities have no real source in this app — see the module
        # note above. The blocks are laid out so the user can fill them in.
        # Real recorded إفطار/سحور counts — these used to be blank because
        # nothing captured Ramadan attendance; the daily screens now do.
        # Only the month's ACTUAL Ramadan days are numbered: Ramadan is a
        # Hijri month of at most 30 days, so numbering every day of a
        # 31-day Gregorian month would claim a 31st day of Ramadan.
        ramadan_dates = set(ramadan_days_in_month(
            month_info["month"], get_school_settings(), get_ramadan_overrides()))
        ramadan_day_numbers = [
            (d["day"] if d["date"] in ramadan_dates else None) for d in days
        ]
        ws.column_dimensions["J"].width = 8.7
        _write_lot_block(
            ws, start_col=11, lot_title=_LOT901_FR, meal_headers=_RAMADAN_HEADERS_FR,
            day_values=[[d["lot901_ftour_ramadan"], d["lot901_shour"]] for d in days],
            total_row=total_row, header_fills=_RAMADAN_HEADER_FILLS,
            sunday_days=sundays, highlight_jours=False,
            day_numbers=ramadan_day_numbers,
        )
        _write_spacer_column(ws, 14, total_row, 4.3)
        _write_lot_block(
            ws, start_col=15, lot_title=_LOT902_FR, meal_headers=_RAMADAN_HEADERS_FR,
            day_values=[[d["lot902_ftour_ramadan"], d["lot902_shour"]] for d in days],
            total_row=total_row, header_fills=_RAMADAN_HEADER_FILLS,
            sunday_days=sundays, highlight_jours=False,
            day_numbers=ramadan_day_numbers,
        )
        ws.column_dimensions["M"].width = 11.5

    _apply_print_setup(ws)
    month_info["_sheet_title"] = title
    month_info["_total_row"] = total_row


def _sum_across_months(
    quarter_data: List[dict], column: str, *, ramadan_only: bool = False,
) -> str | int:
    """Build the template's own cross-sheet total formula, e.g.
    ='MOIS 01 2026'!B35+'MOIS 02 2026'!B32+'MOIS 03 2026'!B35 — returns a
    literal 0 when no month qualifies (a quarter with no Ramadan month)."""
    parts = [
        f"'{month['_sheet_title']}'!{column}{month['_total_row']}"
        for month in quarter_data
        if not ramadan_only or month["is_ramadan"]
    ]
    return "=" + "+".join(parts) if parts else 0


def _write_recap_sheet(
    wb: "Workbook", settings: Optional[SchoolSettings], quarter_data: List[dict],
) -> None:
    """The printable "RECAP A IMPRIMER" attestation, reproducing the real
    template's French legal wording, signer table and article tables."""
    ws = wb.create_sheet(title=_SHEET_RECAP)

    school_year = (settings.school_year if settings else "") or ""
    school_name = (settings.school_name_fr if settings and settings.school_name_fr
                   else (settings.school_name if settings else "")) or ""
    director = (settings.director if settings else "") or ""
    gestionnaire = (settings.gestionnaire if settings else "") or ""
    company = (settings.company_name if settings else "") or ""
    contract_number = (settings.contract_number if settings else "") or ""
    city = ((settings.city_fr if settings and settings.city_fr else
             (settings.city if settings else "")) or "")

    months = [tuple(int(p) for p in m["month"].split("-")) for m in quarter_data]
    years = {year for year, _month in months}
    # A quarter can legitimately straddle 31 December — Dec-Jan-Feb is the
    # standard Moroccan 2nd trimester. Labelling the whole period with only
    # the LAST month's year (as a first version did) makes the signed
    # attestation certify months that belong to the previous year, and
    # contradicts the month sheets its own formulas sum. So the year is
    # printed per month whenever the quarter crosses a year boundary, and
    # only collapsed into the template's single trailing year when every
    # month really does share one — which is the template's own case.
    if len(years) == 1:
        month_names = "-".join(_FRENCH_MONTHS[m - 1] for _y, m in months)
        month_numbers = "-".join(f"{m:02d}" for _y, m in months)
        year_label = str(months[-1][0])
        period_banner = f"LES MOIS: {month_names}-  {year_label}"
        period_sentence = f"{month_numbers} année {year_label}"
    else:
        month_names = "-".join(f"{_FRENCH_MONTHS[m - 1]} {y}" for y, m in months)
        month_numbers = "-".join(f"{m:02d}/{y}" for y, m in months)
        period_banner = f"LES MOIS: {month_names}"
        period_sentence = month_numbers

    def line(row: int, text, *, span=(1, 8), bold=False, size=11,
             horizontal="left", fill="", wrap=False, border=False):
        start, end = span
        if end > start:
            ws.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)
        for col in range(start, end + 1):
            _styled(ws, row, col, text if col == start else None, bold=bold, size=size,
                    horizontal=horizontal, fill=fill, wrap=wrap, border=border)

    # Font sizes and row heights below are the template's own measured values,
    # not house style — this sheet is printed and signed, so its geometry has
    # to survive the round trip.
    line(5, f"ANNEE: {school_year}", span=(1, 4), bold=True, size=14)
    line(6, "Attestation de réception", bold=True, size=18, horizontal="center")
    line(7, period_banner, bold=True, size=18, horizontal="center")
    line(8, "Nous soussignons\xa0:", span=(1, 4), bold=True, size=14)

    line(9, "Nom et Prénom", span=(1, 4), bold=True, size=16,
         horizontal="center", fill=_FILL_RECAP_SIGNER, border=True)
    line(9, None, span=(5, 8), bold=True, size=16,
         horizontal="center", fill=_FILL_RECAP_SIGNER, border=True)
    ws.cell(row=9, column=5).value = "Fonction"
    for row, (name, role) in enumerate(
        ((director, "Le directeur de l’établissement"),
         (gestionnaire, "Le gestionnaire des S.M.F")), start=10,
    ):
        line(row, name, span=(1, 4), size=16, bold=True, horizontal="center", border=True)
        line(row, None, span=(5, 8), size=16, horizontal="center", border=True)
        ws.cell(row=row, column=5).value = role

    line(13, f"     Attestons que les prestations exécutés durant les mois\xa0:"
             f"{period_sentence}", size=14)
    line(14, "Ayant pour Objet\xa0: Prestation de restauration au profit de "
             "l’internat (cantine) du\xa0:", size=14)
    line(15, school_name, bold=True, size=14, horizontal="center")
    line(16, f"      Ont été réellement exécutées par la Sté\xa0: {company}", size=14)
    line(17, "Conformément aux spécifications techniques exigées par le marché\n"
             f"                                                   N°:{contract_number}",
         size=16, wrap=True)
    line(18, "à hauteur des quantités suivantes\xa0:", size=14)

    def article_table(start_row: int, lot_caption: str, columns: dict,
                      article_numbers: list) -> None:
        """One "Nbre de repas servis" table — 5 article rows whose figures are
        live formulas across the month sheets."""
        line(start_row, "Le nombre des repas servis\xa0:", span=(1, 4), bold=True,
             size=16, horizontal="center", border=True)
        line(start_row, None, span=(5, 8), bold=True, size=16,
             horizontal="center", border=True)
        ws.cell(row=start_row, column=5).value = lot_caption

        header = start_row + 1
        _styled(ws, header, 1, "N° Article", size=12, fill=_FILL_RECAP_TABLE)
        ws.merge_cells(start_row=header, start_column=2, end_row=header, end_column=3)
        _styled(ws, header, 2, "Désignations des articles", size=12, fill=_FILL_RECAP_TABLE)
        _styled(ws, header, 3, None, fill=_FILL_RECAP_TABLE)
        _styled(ws, header, 4, "U.M", size=12, fill=_FILL_RECAP_TABLE)
        ws.merge_cells(start_row=header, start_column=5, end_row=header, end_column=8)
        for col in range(5, 9):
            _styled(ws, header, col, "Nbre de repas servis" if col == 5 else None,
                    size=14, fill=_FILL_RECAP_TABLE)

        articles = [
            ("Le Petit déjeuner", columns["ftour"], False),
            ("Le déjeuner", columns["ghada"], False),
            ("Le diner", columns["asha"], False),
            ("Ftour", columns["ramadan_ftour"], True),
            ("Shour", columns["ramadan_shour"], True),
        ]
        for index, (label, column_letter, ramadan_only) in enumerate(articles):
            row = header + 1 + index
            # Article numbers are copied from the template rather than made
            # sequential. Its QUALIFANT table really does read 1, (blank),
            # (blank), 2, 3 — a slip by whoever wrote it, but the standing
            # rule is to reproduce the official document, not correct it.
            _styled(ws, row, 1, article_numbers[index], size=12)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
            _styled(ws, row, 2, label, size=12, horizontal="left")
            _styled(ws, row, 3, None)
            _styled(ws, row, 4, "U", size=12)
            ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=8)
            for col in range(5, 9):
                _styled(ws, row, col,
                        _sum_across_months(quarter_data, column_letter,
                                           ramadan_only=ramadan_only) if col == 5 else None,
                        size=14)

    article_table(19, "PRIMAIRE ET COLLEGIAL", {
        "ftour": "B", "ghada": "C", "asha": "D",
        "ramadan_ftour": "L", "ramadan_shour": "M",
    }, [1, 2, 3, 4, 5])
    # The template's own QUALIFANT numbering, blanks included — see the note
    # in article_table.
    article_table(28, "QUALIFANT", {
        "ftour": "G", "ghada": "H", "asha": "I",
        "ramadan_ftour": "P", "ramadan_shour": "Q",
    }, [1, None, None, 2, 3])

    # The two grey bands that close off each article table in the template.
    for band_row in (26, 35):
        line(band_row, None, fill=_FILL_RECAP_SIGNER, border=True)

    line(36, "             Remarques :", bold=True, size=14)
    line(37, "." * 180, size=11, wrap=True, border=True)
    # The quarter's final day. NOT copied from the template — its own copy
    # reads 30/03/2026 for a quarter ending 31/03, i.e. simply the day that
    # school happened to sign. A deterministic quarter-end date is used here
    # instead so that re-exporting the same quarter can never silently
    # re-date an already-signed attestation.
    last_year, last_month = months[-1]
    closing_date = datetime.date(
        last_year, last_month, calendar.monthrange(last_year, last_month)[1])
    line(38, f"    Fait à {city} Le\xa0:{closing_date.strftime('%d/%m/%Y')}",
         span=(2, 7), size=16)

    # Signature area: two captioned, framed boxes the signers actually sign in.
    line(40, "Le Directeur de l’établissement", span=(1, 4), size=16,
         horizontal="center", fill=_FILL_RECAP_TABLE, border=True)
    line(40, None, span=(5, 8), size=16, horizontal="center",
         fill=_FILL_RECAP_TABLE, border=True)
    ws.cell(row=40, column=5).value = "Le Gestionnaire de S.M.F"
    ws.merge_cells(start_row=41, start_column=1, end_row=43, end_column=4)
    ws.merge_cells(start_row=41, start_column=5, end_row=43, end_column=8)
    for box_row in range(41, 44):
        for col in list(range(1, 5)) + list(range(5, 9)):
            _styled(ws, box_row, col, None)
    line(44, "Contresigné par le directeur Provincial\xa0;", span=(1, 5),
         size=16, border=True)

    ws.column_dimensions["H"].width = 18.2
    for row, height in _RECAP_ROW_HEIGHTS.items():
        ws.row_dimensions[row].height = height
    ws.print_area = f"'{_SHEET_RECAP}'!$A$1:$H$45"
    _apply_print_setup(ws, scale=88, tight_margins=True)


def _write_quarterly_reception_excel(
    path: Path, settings: Optional[SchoolSettings], quarter_data: List[dict],
) -> None:
    """Build the whole workbook: one "MOIS MM YYYY" sheet per month, then the
    printable recap — the same 4-sheet shape as the real template."""
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # drop the default blank sheet; we add our own
    for month_info in quarter_data:
        _write_month_sheet(wb, month_info)
    _write_recap_sheet(wb, settings, quarter_data)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
