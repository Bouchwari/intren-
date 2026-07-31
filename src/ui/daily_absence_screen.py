"""
src/ui/daily_absence_screen.py
Daily absence sheet (ورقة الغياب اليومي) — count absent beneficiaries per meal per day.
Parallel structure to daily_contact_screen but for absences (red theme).
"""
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDateEdit, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_LABELS,
)
from core.models import DailyAbsence
from data.database import get_day_absences, get_recent_absences, save_daily_absence

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "ورقة الغياب اليومي"
_SUBTITLE       = "عدد الغائبين عن خدمة الإطعام المدرسي"
_BTN_PREV       = "→  اليوم السابق"
_BTN_NEXT       = "اليوم التالي  ←"
_BTN_TODAY      = "اليوم"
_BTN_LOAD       = "📂  تحميل"
_BTN_SAVE       = "💾  حفظ اليوم"
_LBL_DATE       = "التاريخ:"
_LBL_COLLEGIAL  = "إعدادي"
_LBL_QUALIFYING = "تأهيلي"
_LBL_MONITORS   = "معلمو الداخلية"
_LBL_GRANTED    = "ممنوح"
_LBL_PAYING     = "مؤد"
_LBL_COMPLEMENT = "متمم"
_LBL_GRAND_TOT  = "إجمالي الغياب"
_HDR_HISTORY    = ["التاريخ", "الوجبة", "إعدادي (م)", "إعدادي (مؤ)", "إعدادي (مت)",
                   "تأهيلي (م)", "تأهيلي (مؤ)", "تأهيلي (مت)", "معلمون", "الإجمالي"]
_SAVED_OK       = "تم حفظ ورقة الغياب بنجاح."

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
_PAGE_BG = "#f5f5f0"
_PANEL_BG = "#ffffff"
_PANEL_BORDER = "#dddccd"
_INK = "#5A5A40"
_HISTORY_COLUMN_WIDTHS = [92, 86, 78, 78, 78, 78, 78, 78, 82, 82]


def _spin() -> QSpinBox:
    s = QSpinBox()
    s.setRange(0, 9999)
    s.setMinimumHeight(34)
    s.setAlignment(Qt.AlignmentFlag.AlignCenter)
    s.setStyleSheet(
        f"border:1px solid {COLOR_BORDER}; border-radius:5px;"
        "padding:2px 6px; font-size:13px;"
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
                font-size: 15px; font-weight: bold;
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
        for col, lbl in enumerate(["", _LBL_GRANTED, _LBL_PAYING, _LBL_COMPLEMENT, "المجموع"]):
            h = QLabel(lbl)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setStyleSheet(
                f"color:{COLOR_TEXT_SECONDARY}; font-size:11px; font-weight:bold;"
            )
            hdr.addWidget(h, 0, col)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{COLOR_BORDER};")
        layout.addWidget(sep)

        grid = QGridLayout()
        grid.setSpacing(6)

        self._cg = _spin(); self._cp = _spin(); self._cc = _spin()
        self._qg = _spin(); self._qp = _spin(); self._qc = _spin()
        self._mo = _spin()

        self._ct_lbl = QLabel("0")
        self._qt_lbl = QLabel("0")
        self._gt_lbl = QLabel("0")

        for lbl in (self._ct_lbl, self._qt_lbl):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color:{self._color}; font-weight:bold; font-size:14px;")

        # إعدادي row
        grid.addWidget(QLabel(_LBL_COLLEGIAL), 0, 0)
        grid.addWidget(self._cg, 0, 1)
        grid.addWidget(self._cp, 0, 2)
        grid.addWidget(self._cc, 0, 3)
        grid.addWidget(self._ct_lbl, 0, 4)

        # تأهيلي row
        grid.addWidget(QLabel(_LBL_QUALIFYING), 1, 0)
        grid.addWidget(self._qg, 1, 1)
        grid.addWidget(self._qp, 1, 2)
        grid.addWidget(self._qc, 1, 3)
        grid.addWidget(self._qt_lbl, 1, 4)

        # معلمون row
        grid.addWidget(QLabel(_LBL_MONITORS), 2, 0)
        grid.addWidget(self._mo, 2, 1, 1, 3)
        layout.addLayout(grid)

        # Grand total
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

        for sp in (self._cg, self._cp, self._cc,
                   self._qg, self._qp, self._qc, self._mo):
            sp.valueChanged.connect(self._update_totals)

    def _update_totals(self) -> None:
        absence = self.to_absence("")
        self._ct_lbl.setText(str(absence.collegial_total))
        self._qt_lbl.setText(str(absence.qualifying_total))
        self._gt_lbl.setText(str(absence.grand_total))

    def load(self, absence: Optional[DailyAbsence]) -> None:
        if absence is None:
            for sp in (self._cg, self._cp, self._cc,
                       self._qg, self._qp, self._qc, self._mo):
                sp.setValue(0)
        else:
            self._cg.setValue(absence.collegial_granted)
            self._cp.setValue(absence.collegial_paying)
            self._cc.setValue(absence.collegial_complement)
            self._qg.setValue(absence.qualifying_granted)
            self._qp.setValue(absence.qualifying_paying)
            self._qc.setValue(absence.qualifying_complement)
            self._mo.setValue(absence.monitors)
        self._update_totals()

    def to_absence(self, date: str) -> DailyAbsence:
        return DailyAbsence(
            date=date,
            meal_type=self._meal_key,
            collegial_granted=self._cg.value(),
            collegial_paying=self._cp.value(),
            collegial_complement=self._cc.value(),
            qualifying_granted=self._qg.value(),
            qualifying_paying=self._qp.value(),
            qualifying_complement=self._qc.value(),
            monitors=self._mo.value(),
        )


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
        self._date_edit.setMinimumWidth(128)
        self._date_edit.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            "padding:4px 10px; font-size:13px;"
        )
        row.addWidget(self._date_edit)

        for label, slot, color in [
            (_BTN_TODAY, self._load_today,    _INK),
            (_BTN_PREV,  self._go_prev,       _INK),
            (_BTN_NEXT,  self._go_next,       _INK),
            (_BTN_LOAD,  self._load_selected, "#0891b2"),
        ]:
            btn = self._btn(label, color)
            btn.clicked.connect(slot)
            row.addWidget(btn)

        row.addStretch()

        save_btn = self._btn(_BTN_SAVE, COLOR_SUCCESS)
        save_btn.clicked.connect(self._on_save)
        row.addWidget(save_btn)
        return row

    def _btn(self, label: str, color: str) -> QPushButton:
        b = QPushButton(label)
        b.setMinimumHeight(36)
        b.setStyleSheet(
            f"background:{color}; color:white; border-radius:12px;"
            "padding:0 12px; font-size:13px;"
        )
        return b

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
                font-size:13px; font-weight:bold; color:{COLOR_DANGER};
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
        self._history_table.horizontalHeader().setStretchLastSection(False)
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(_HISTORY_COLUMN_WIDTHS):
            self._history_table.setColumnWidth(col, width)
        self._history_table.setMaximumHeight(190)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {_PANEL_BORDER}; border-radius:12px;
                background:white; alternate-background-color:#fff5f5;
                font-size:12px;
            }}
            QHeaderView::section {{
                background:#E4E4D7; color:{_INK};
                padding:7px 10px; border:none;
                border-bottom:1px solid {_PANEL_BORDER};
                font-weight:bold; font-size:11px;
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
                str(a.collegial_granted), str(a.collegial_paying),
                str(a.collegial_complement), str(a.qualifying_granted),
                str(a.qualifying_paying), str(a.qualifying_complement),
                str(a.monitors), str(a.grand_total),
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                )
                self._history_table.setItem(r, col, item)

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
