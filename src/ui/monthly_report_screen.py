"""
src/ui/monthly_report_screen.py
Monthly report (المحضر الشهري) — aggregates daily data for a full month,
computes net meals served and total cost, with مسير notes.
"""
import datetime
import logging
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
)
from core.models import MonthlyMealSummary
from data.database import (
    get_monthly_report_notes, get_monthly_summaries,
    get_months_with_data, get_school_settings,
    save_monthly_report_notes,
)

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "المحضر الشهري"
_SUBTITLE       = "ملخص نشاط الإطعام المدرسي الشهري"
_BTN_GENERATE   = "🔄  توليد المحضر"
_BTN_SAVE_NOTES = "💾  حفظ الملاحظات"
_LBL_MONTH      = "الشهر:"
_LBL_YEAR       = "السنة:"
_LBL_NOTES      = "ملاحظات المسير"
_NOTES_HINT     = "أدخل ملاحظاتك هنا..."
_NO_DATA        = "لا توجد بيانات لهذا الشهر.\nأدخل بيانات ورقة الاتصال أو الغياب أولاً."
_SAVED_OK       = "تم حفظ الملاحظات بنجاح."

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

_MEAL_COLORS = {
    MEAL_FTOUR: "#f59e0b",
    MEAL_GHADA: COLOR_ACCENT,
    MEAL_ASHA:  "#7c3aed",
}


def _titem(text: str, bold: bool = False, bg: str = "", fg: str = "",
           align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
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
            font-size: 13px; background: white;
            alternate-background-color: #f8fafc;
            gridline-color: #e2e8f0;
        }}
        QHeaderView::section {{
            background: {header_bg}; color: white;
            padding: 8px 10px; border: none;
            font-weight: bold; font-size: 12px;
        }}
        QTableWidget::item {{ padding: 7px 10px; }}
    """)
    return t


_LOGGER = logging.getLogger(__name__)


class MonthlyReportScreen(QWidget):
    """Monthly report — aggregated summary with cost calculation."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._summaries: List[MonthlyMealSummary] = []
        self._build_ui()
        # Pre-fill selectors with current month
        now = datetime.date.today()
        self._month_combo.setCurrentIndex(now.month - 1)
        self._year_spin_combo.setCurrentText(str(now.year))

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
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;")
        col.addWidget(title)
        col.addWidget(sub)
        return col

    def _build_selector_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        # Month selector
        row.addWidget(QLabel(_LBL_MONTH,
                             styleSheet=f"font-size:13px; color:{COLOR_TEXT_PRIMARY};"))
        self._month_combo = QComboBox()
        self._month_combo.setMinimumHeight(36)
        self._month_combo.setMinimumWidth(130)
        for m in _ARABIC_MONTHS:
            self._month_combo.addItem(m)
        self._month_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:4px 8px; font-size:13px;"
        )
        row.addWidget(self._month_combo)

        # Year selector (combo of last 5 years)
        row.addWidget(QLabel(_LBL_YEAR,
                             styleSheet=f"font-size:13px; color:{COLOR_TEXT_PRIMARY};"))
        self._year_spin_combo = QComboBox()
        self._year_spin_combo.setMinimumHeight(36)
        self._year_spin_combo.setMinimumWidth(90)
        current_year = datetime.date.today().year
        for y in range(current_year + 1, current_year - 5, -1):
            self._year_spin_combo.addItem(str(y))
        self._year_spin_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:4px 8px; font-size:13px;"
        )
        row.addWidget(self._year_spin_combo)

        # Quick jump to months with data
        self._months_combo = QComboBox()
        self._months_combo.setMinimumHeight(36)
        self._months_combo.setMinimumWidth(160)
        self._months_combo.setPlaceholderText("الأشهر التي لها بيانات")
        self._months_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px;"
            "padding:4px 8px; font-size:13px;"
        )
        self._months_combo.currentTextChanged.connect(self._on_quick_jump)
        self._refresh_months_combo()
        row.addWidget(self._months_combo)

        row.addStretch()

        gen_btn = QPushButton(_BTN_GENERATE)
        gen_btn.setMinimumHeight(38)
        gen_btn.setStyleSheet(
            f"background:{COLOR_ACCENT}; color:white; border-radius:7px;"
            "padding:0 18px; font-size:13px; font-weight:bold;"
        )
        gen_btn.clicked.connect(self._generate)
        row.addWidget(gen_btn)

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
            f"font-size:14px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};"
            f"border-bottom:2px solid {COLOR_ACCENT}; padding-bottom:10px;"
        )
        self._month_lbl = QLabel()
        self._month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_lbl.setStyleSheet(
            f"font-size:13px; color:{COLOR_TEXT_SECONDARY}; padding-bottom:6px;"
        )

        self._no_data_lbl = QLabel(_NO_DATA)
        self._no_data_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_data_lbl.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:14px; padding:40px;"
        )

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
                font-size:13px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
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
            "padding:8px; font-size:13px;"
        )
        save_btn = QPushButton(_BTN_SAVE_NOTES)
        save_btn.setMinimumHeight(36)
        save_btn.setMaximumWidth(200)
        save_btn.setStyleSheet(
            f"background:{COLOR_SUCCESS}; color:white; border-radius:6px;"
            "padding:0 14px; font-size:13px; font-weight:bold;"
        )
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
        self._month_lbl.setText(f"المحضر الشهري لشهر: {month_label}  ({_SUBTITLE})")

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

        # Remove old tables
        for attr in ("_main_table", "_detail_table", "_cost_box"):
            old = getattr(self, attr, None)
            if old is not None:
                self._report_layout.removeWidget(old)
                old.deleteLater()
                setattr(self, attr, None)
        for attr in ("_main_title", "_detail_title"):
            old = getattr(self, attr, None)
            if old is not None:
                self._report_layout.removeWidget(old)
                old.deleteLater()
                setattr(self, attr, None)

        if has_data:
            self._main_table = self._build_main_table(self._summaries)
            self._detail_table = self._build_detail_table(self._summaries)
            self._cost_box = self._build_cost_box(self._summaries)
            self._main_title = QLabel(
                "أ — ملخص الوجبات والتكاليف",
                styleSheet=f"font-size:13px; font-weight:bold; color:{COLOR_ACCENT};",
            )
            self._report_layout.addWidget(self._main_title)
            self._report_layout.addWidget(self._main_table)
            self._detail_title = QLabel(
                "ب — التفصيل حسب الفئة",
                styleSheet="font-size:13px; font-weight:bold; color:#7c3aed;",
            )
            self._report_layout.addWidget(self._detail_title)
            self._report_layout.addWidget(self._detail_table)
            self._report_layout.addWidget(self._cost_box)

        # Load notes
        self._notes_edit.setPlainText(get_monthly_report_notes(month_str))
        self._refresh_months_combo()

    # ── Table builders ─────────────────────────────────────────────────────

    def _build_main_table(self, summaries: List[MonthlyMealSummary]) -> QTableWidget:
        rows = len(summaries) + 1  # +1 grand total
        t = _styled_table(rows, len(_MAIN_HEADERS), _MAIN_HEADERS)

        meal_labels = {MEAL_FTOUR: MEAL_LABELS[MEAL_FTOUR],
                       MEAL_GHADA: MEAL_LABELS[MEAL_GHADA],
                       MEAL_ASHA:  MEAL_LABELS[MEAL_ASHA]}

        total_contact = total_absence = total_net = total_cost = 0.0

        for i, s in enumerate(summaries):
            color = _MEAL_COLORS.get(s.meal_type, COLOR_ACCENT)
            t.setItem(i, 0, _titem(meal_labels.get(s.meal_type, s.meal_type), bold=True, fg=color))
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
        t.setItem(r, 0, _titem("الإجمالي", bold=True, bg="#0f172a", fg="white"))
        t.setItem(r, 1, _titem("", bg="#0f172a"))
        t.setItem(r, 2, _titem(str(int(total_contact)), bold=True, bg="#0f172a", fg="white"))
        t.setItem(r, 3, _titem(str(int(total_absence)), bold=True, bg="#0f172a", fg="white"))
        t.setItem(r, 4, _titem(str(int(total_net)),     bold=True, bg="#0f172a", fg="white"))
        t.setItem(r, 5, _titem("", bg="#0f172a"))
        t.setItem(r, 6, _titem(f"{total_cost:.2f}", bold=True, bg=COLOR_ACCENT, fg="white"))

        t.setMaximumHeight(rows * 38 + 42)
        return t

    def _build_detail_table(self, summaries: List[MonthlyMealSummary]) -> QTableWidget:
        """Per-meal, per-sector breakdown table."""
        sectors = ["إعدادي", "تأهيلي", "معلمو الداخلية"]
        rows = len(summaries) * (len(sectors) + 1)  # +1 subtotal per meal
        t = _styled_table(rows, len(_DETAIL_HEADERS), _DETAIL_HEADERS, "#7c3aed")

        meal_labels = {MEAL_FTOUR: MEAL_LABELS[MEAL_FTOUR],
                       MEAL_GHADA: MEAL_LABELS[MEAL_GHADA],
                       MEAL_ASHA:  MEAL_LABELS[MEAL_ASHA]}

        row = 0
        for s in summaries:
            color = _MEAL_COLORS.get(s.meal_type, COLOR_ACCENT)
            meal_lbl = meal_labels.get(s.meal_type, s.meal_type)

            # إعدادي
            t.setItem(row, 0, _titem(meal_lbl, bold=True, fg=color))
            t.setItem(row, 1, _titem("إعدادي"))
            t.setItem(row, 2, _titem(str(s.contact_collegial)))
            t.setItem(row, 3, _titem(str(s.absence_collegial)))
            t.setItem(row, 4, _titem(str(max(0, s.contact_collegial - s.absence_collegial)), bold=True))
            row += 1

            # تأهيلي
            t.setItem(row, 0, _titem(""))
            t.setItem(row, 1, _titem("تأهيلي"))
            t.setItem(row, 2, _titem(str(s.contact_qualifying)))
            t.setItem(row, 3, _titem(str(s.absence_qualifying)))
            t.setItem(row, 4, _titem(str(max(0, s.contact_qualifying - s.absence_qualifying)), bold=True))
            row += 1

            # معلمون
            t.setItem(row, 0, _titem(""))
            t.setItem(row, 1, _titem("معلمو الداخلية"))
            t.setItem(row, 2, _titem(str(s.contact_monitors)))
            t.setItem(row, 3, _titem(str(s.absence_monitors)))
            t.setItem(row, 4, _titem(str(max(0, s.contact_monitors - s.absence_monitors)), bold=True))
            row += 1

            # Meal subtotal
            t.setItem(row, 0, _titem(""))
            t.setItem(row, 1, _titem(f"مجموع {meal_lbl}", bold=True, bg="#f0f9ff"))
            t.setItem(row, 2, _titem(str(s.contact_total), bold=True, bg="#f0f9ff"))
            t.setItem(row, 3, _titem(str(s.absence_total), bold=True, bg="#f0f9ff"))
            t.setItem(row, 4, _titem(str(s.net_total), bold=True, bg="#dbeafe", fg="#1d4ed8"))
            row += 1

        t.setMaximumHeight(rows * 36 + 42)
        return t

    def _build_cost_box(self, summaries: List[MonthlyMealSummary]) -> QFrame:
        """A summary cost card at the bottom of the report."""
        total_cost = sum(s.total_cost for s in summaries)
        total_net  = sum(s.net_total  for s in summaries)

        frame = QFrame()
        frame.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLOR_ACCENT}, stop:1 #0369a1);"
            "border-radius:10px;"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(24, 16, 24, 16)

        left = QVBoxLayout()
        lbl1 = QLabel("إجمالي الوجبات المقدمة")
        lbl1.setStyleSheet("color:rgba(255,255,255,0.8); font-size:12px;")
        lbl2 = QLabel(str(total_net))
        f = QFont(); f.setPointSize(22); f.setBold(True)
        lbl2.setFont(f)
        lbl2.setStyleSheet("color:white;")
        left.addWidget(lbl1)
        left.addWidget(lbl2)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl3 = QLabel("التكلفة الإجمالية للشهر")
        lbl3.setStyleSheet("color:rgba(255,255,255,0.8); font-size:12px;")
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
            self._year_spin_combo.setCurrentText(year)
            self._month_combo.setCurrentIndex(int(month) - 1)
            self._generate()
        except (ValueError, IndexError):
            _LOGGER.warning("Ignoring invalid quick-jump month: %s", month_str)

    def _on_save_notes(self) -> None:
        try:
            save_monthly_report_notes(
                self._selected_month_str(),
                self._notes_edit.toPlainText().strip()
            )
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")
