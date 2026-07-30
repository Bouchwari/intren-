"""
src/ui/daily_report_screen.py
Daily report (التقرير اليومي) — auto-generated from contact + absence data.
Shows a structured summary table and a notes field for the مسير.
"""
import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
)
from core.models import DailyContact, DailyAbsence
from data.database import (
    get_day_contacts, get_day_absences,
    get_dates_with_data, get_report_notes, get_school_settings,
    save_report_notes,
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
_SAVED_OK       = "تم حفظ الملاحظات بنجاح."

_MEAL_ORDER: List[Tuple[str, str]] = [
    (MEAL_FTOUR, MEAL_LABELS[MEAL_FTOUR]),
    (MEAL_GHADA, MEAL_LABELS[MEAL_GHADA]),
    (MEAL_ASHA,  MEAL_LABELS[MEAL_ASHA]),
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

        save_btn = self._btn(_BTN_SAVE_NOTES, COLOR_SUCCESS)
        save_btn.clicked.connect(self._on_save_notes)
        save_btn.setMaximumWidth(200)
        layout.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

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

        # Load notes
        self._notes_edit.setPlainText(get_report_notes(date_str))

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

    # ── Notes save ─────────────────────────────────────────────────────────

    def _on_save_notes(self) -> None:
        date_str = self._date_edit.date().toString("yyyy-MM-dd")
        try:
            save_report_notes(date_str, self._notes_edit.toPlainText().strip())
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")
