"""
src/ui/incident_log_screen.py
Incident / Disciplinary log (دفتر المخالفات).
Form + searchable history table. Click a row to load it for editing.
"""
import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
)
from core.models import Student, Violation
from data.database import (
    add_violation, delete_violation, get_all_students,
    get_all_violations, search_violations, update_violation,
)

# ── Constants ─────────────────────────────────────────────────────────────────
_TITLE    = "دفتر المخالفات"
_SUBTITLE = "سجل المخالفات التأديبية للإطعام المدرسي"

_VIOLATION_TYPES = [
    "تأخر عن موعد الوجبة",
    "غياب غير مبرر عن الوجبة",
    "سلوك غير لائق في المطعم",
    "عدم احترام قواعد النظام",
    "إتلاف الممتلكات",
    "ضوضاء وإزعاج",
    "مخالفة أخرى",
]

_ACTION_TYPES = [
    "توبيخ شفهي",
    "إنذار كتابي",
    "إشعار الولي",
    "إيقاف مؤقت عن خدمة الإطعام",
    "إحالة على مجلس التأديب",
    "إجراء آخر",
]

_TABLE_HEADERS = [
    "#", "التاريخ", "اسم التلميذ", "القسم",
    "نوع المخالفة", "الوصف", "الإجراء المتخذ", "المُبلِّغ",
]

_BTN_SAVE   = "💾  حفظ المخالفة"
_BTN_NEW    = "➕  جديد"
_BTN_DELETE = "🗑️  حذف"
_BTN_SEARCH = "🔍  بحث"
_BTN_RESET  = "↺  إعادة ضبط"
_SAVED_OK   = "تم حفظ المخالفة بنجاح."
_DEL_CONFIRM= "هل تريد حذف هذا السجل نهائياً؟"
_UPDATED_OK = "تم تحديث المخالفة بنجاح."


def _btn(label: str, color: str, min_w: int = 0) -> QPushButton:
    b = QPushButton(label)
    b.setMinimumHeight(36)
    if min_w:
        b.setMinimumWidth(min_w)
    b.setStyleSheet(
        f"background:{color}; color:white; border-radius:6px;"
        "padding:0 14px; font-size:13px;"
    )
    return b


def _titem(text: str, bold: bool = False, fg: str = "",
           align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(align | Qt.AlignmentFlag.AlignVCenter))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    f = QFont(); f.setBold(bold); item.setFont(f)
    if fg:
        item.setForeground(QColor(fg))
    return item


# ── Main screen ───────────────────────────────────────────────────────────────

class IncidentLogScreen(QWidget):

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{COLOR_SURFACE};")
        self._editing_id: Optional[int] = None   # None = new, int = edit mode
        self._students: List[Student] = []
        self._current_violations: List[Violation] = []
        self._build_ui()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)

        # Title
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(17); f.setBold(True); title.setFont(f)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        sub = QLabel(_SUBTITLE)
        sub.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;")
        root.addWidget(title)
        root.addWidget(sub)

        # Splitter: form (top) | history (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(8)
        splitter.setStyleSheet(
            "QSplitter::handle { background:#e2e8f0; border-radius:4px; }"
        )
        splitter.addWidget(self._build_form_panel())
        splitter.addWidget(self._build_history_panel())
        splitter.setSizes([340, 420])
        root.addWidget(splitter, 1)

    # ── Form panel ─────────────────────────────────────────────────────────

    def _build_form_panel(self) -> QGroupBox:
        grp = QGroupBox("إضافة / تعديل مخالفة")
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:13px; font-weight:bold; color:{COLOR_TEXT_PRIMARY};
                border:2px solid {COLOR_ACCENT}; border-radius:10px;
                margin-top:10px; padding:12px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 10px; right:14px;
            }}
        """)
        outer = QVBoxLayout(grp)
        outer.setSpacing(10)

        # ── Row 1: date | student picker | class ──
        r1 = QHBoxLayout(); r1.setSpacing(10)

        # Date
        date_col = QVBoxLayout()
        date_col.addWidget(QLabel("التاريخ:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setMinimumHeight(34)
        self._date_edit.setMinimumWidth(140)
        self._date_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        date_col.addWidget(self._date_edit)
        r1.addLayout(date_col)

        # Student picker
        stu_col = QVBoxLayout()
        stu_col.addWidget(QLabel("التلميذ:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._student_combo = QComboBox()
        self._student_combo.setEditable(True)
        self._student_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._student_combo.setMinimumHeight(34)
        self._student_combo.setMinimumWidth(220)
        self._student_combo.setPlaceholderText("اختر تلميذاً أو اكتب الاسم...")
        self._student_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        self._student_combo.currentIndexChanged.connect(self._on_student_selected)
        stu_col.addWidget(self._student_combo)
        r1.addLayout(stu_col, 1)

        # Class
        cls_col = QVBoxLayout()
        cls_col.addWidget(QLabel("القسم:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._class_edit = QLineEdit()
        self._class_edit.setMinimumHeight(34)
        self._class_edit.setMinimumWidth(100)
        self._class_edit.setPlaceholderText("القسم")
        self._class_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        cls_col.addWidget(self._class_edit)
        r1.addLayout(cls_col)

        outer.addLayout(r1)

        # ── Row 2: violation type | action taken | reported by ──
        r2 = QHBoxLayout(); r2.setSpacing(10)

        vtype_col = QVBoxLayout()
        vtype_col.addWidget(QLabel("نوع المخالفة:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._vtype_combo = QComboBox()
        self._vtype_combo.setEditable(True)
        self._vtype_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._vtype_combo.setMinimumHeight(34)
        self._vtype_combo.addItems(_VIOLATION_TYPES)
        self._vtype_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        vtype_col.addWidget(self._vtype_combo)
        r2.addLayout(vtype_col, 2)

        action_col = QVBoxLayout()
        action_col.addWidget(QLabel("الإجراء المتخذ:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._action_combo = QComboBox()
        self._action_combo.setEditable(True)
        self._action_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._action_combo.setMinimumHeight(34)
        self._action_combo.addItems(_ACTION_TYPES)
        self._action_combo.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        action_col.addWidget(self._action_combo)
        r2.addLayout(action_col, 2)

        rep_col = QVBoxLayout()
        rep_col.addWidget(QLabel("المُبلِّغ:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._reporter_edit = QLineEdit()
        self._reporter_edit.setMinimumHeight(34)
        self._reporter_edit.setPlaceholderText("اسم المُبلِّغ")
        self._reporter_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        rep_col.addWidget(self._reporter_edit)
        r2.addLayout(rep_col, 1)

        outer.addLayout(r2)

        # ── Row 3: description ──
        desc_col = QVBoxLayout()
        desc_col.addWidget(QLabel("وصف المخالفة:", styleSheet=f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("اكتب تفاصيل المخالفة هنا...")
        self._desc_edit.setMaximumHeight(70)
        self._desc_edit.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:6px; font-size:13px;")
        desc_col.addWidget(self._desc_edit)
        outer.addLayout(desc_col)

        # ── Buttons ──
        btn_row = QHBoxLayout()

        self._mode_badge = QLabel("• وضع الإضافة")
        self._mode_badge.setStyleSheet(
            f"color:{COLOR_SUCCESS}; font-size:12px; font-weight:bold;")
        btn_row.addWidget(self._mode_badge)
        btn_row.addStretch()

        new_btn    = _btn(_BTN_NEW,    "#475569")
        save_btn   = _btn(_BTN_SAVE,   COLOR_SUCCESS, min_w=160)
        delete_btn = _btn(_BTN_DELETE, COLOR_DANGER)

        new_btn.clicked.connect(self._on_new)
        save_btn.clicked.connect(self._on_save)
        delete_btn.clicked.connect(self._on_delete)

        btn_row.addWidget(new_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(delete_btn)
        outer.addLayout(btn_row)

        return grp

    # ── History panel ──────────────────────────────────────────────────────

    def _build_history_panel(self) -> QGroupBox:
        grp = QGroupBox("سجل المخالفات")
        grp.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-size:13px; font-weight:bold; color:{COLOR_DANGER};
                border:1px solid {COLOR_BORDER}; border-radius:10px;
                margin-top:10px; padding:10px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 10px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)
        layout.setSpacing(8)

        # Filter bar
        flt = QHBoxLayout(); flt.setSpacing(8)

        self._search_name = QLineEdit()
        self._search_name.setPlaceholderText("🔍  بحث بالاسم...")
        self._search_name.setMinimumHeight(34)
        self._search_name.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        self._search_name.textChanged.connect(self._on_search)

        self._filter_type = QComboBox()
        self._filter_type.setMinimumHeight(34)
        self._filter_type.setMinimumWidth(180)
        self._filter_type.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 8px; font-size:13px;")
        self._filter_type.addItem("كل أنواع المخالفات", "")
        for vt in _VIOLATION_TYPES:
            self._filter_type.addItem(vt, vt)
        self._filter_type.currentIndexChanged.connect(self._on_search)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addMonths(-12))
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.setMinimumHeight(34)
        self._date_from.setMinimumWidth(130)
        self._date_from.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 6px; font-size:13px;")

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.setMinimumHeight(34)
        self._date_to.setMinimumWidth(130)
        self._date_to.setStyleSheet(
            f"border:1px solid {COLOR_BORDER}; border-radius:6px; padding:4px 6px; font-size:13px;")

        search_btn = _btn(_BTN_SEARCH, COLOR_ACCENT)
        reset_btn  = _btn(_BTN_RESET,  "#475569")
        search_btn.clicked.connect(self._on_search)
        reset_btn.clicked.connect(self._on_reset_search)

        flt.addWidget(self._search_name, 2)
        flt.addWidget(self._filter_type, 2)
        flt.addWidget(QLabel("من:", styleSheet=f"color:{COLOR_TEXT_SECONDARY};"))
        flt.addWidget(self._date_from)
        flt.addWidget(QLabel("إلى:", styleSheet=f"color:{COLOR_TEXT_SECONDARY};"))
        flt.addWidget(self._date_to)
        flt.addWidget(search_btn)
        flt.addWidget(reset_btn)
        layout.addLayout(flt)

        # Count label
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:12px;")
        layout.addWidget(self._count_lbl)

        # Table
        self._table = QTableWidget(0, len(_TABLE_HEADERS))
        self._table.setHorizontalHeaderLabels(_TABLE_HEADERS)
        self._table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {COLOR_BORDER}; border-radius:8px;
                font-size:12px; background:white;
                alternate-background-color:#fff5f5;
                gridline-color:#e2e8f0;
            }}
            QHeaderView::section {{
                background:{COLOR_DANGER}; color:white;
                padding:8px 8px; border:none;
                font-weight:bold; font-size:11px;
            }}
            QTableWidget::item {{ padding:5px 8px; }}
            QTableWidget::item:selected {{
                background:{COLOR_ACCENT}33; color:{COLOR_TEXT_PRIMARY};
            }}
        """)
        self._table.doubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self._table)
        return grp

    # ── Data helpers ────────────────────────────────────────────────────────

    def _load_students(self) -> None:
        """Populate student dropdown from DB."""
        self._students = get_all_students()
        self._student_combo.blockSignals(True)
        self._student_combo.clear()
        self._student_combo.addItem("— اختر تلميذاً —", None)
        for s in self._students:
            self._student_combo.addItem(
                f"{s.full_name}  ({s.student_class})", s
            )
        self._student_combo.blockSignals(False)

    def _on_student_selected(self, idx: int) -> None:
        data = self._student_combo.itemData(idx)
        if isinstance(data, Student):
            self._class_edit.setText(data.student_class)

    def _refresh_table(self, violations: List[Violation]) -> None:
        self._current_violations = list(violations)
        self._table.setRowCount(0)
        for v in violations:
            r = self._table.rowCount()
            self._table.insertRow(r)
            row_data = [
                str(r + 1), v.date, v.student_name, v.student_class,
                v.violation_type, v.description, v.action_taken, v.reported_by,
            ]
            for col, val in enumerate(row_data):
                item = _titem(val, align=Qt.AlignmentFlag.AlignRight
                              if col in (2, 3, 5, 6, 7) else Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(r, col, item)
            # store the violation id in the first cell's UserRole
            self._table.item(r, 0).setData(Qt.ItemDataRole.UserRole, v.id)

        self._count_lbl.setText(f"إجمالي النتائج: {len(violations)}")

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_new(self) -> None:
        self._editing_id = None
        self._date_edit.setDate(QDate.currentDate())
        self._student_combo.setCurrentIndex(0)
        self._class_edit.clear()
        self._vtype_combo.setCurrentIndex(0)
        self._action_combo.setCurrentIndex(0)
        self._reporter_edit.clear()
        self._desc_edit.clear()
        self._mode_badge.setText("• وضع الإضافة")
        self._mode_badge.setStyleSheet(f"color:{COLOR_SUCCESS}; font-size:12px; font-weight:bold;")

    def _form_to_violation(self) -> Violation:
        student_data = self._student_combo.currentData()
        stu_id = student_data.id if isinstance(student_data, Student) else None
        stu_name = (
            student_data.full_name if isinstance(student_data, Student)
            else self._student_combo.currentText().split("  (")[0].strip()
        )
        return Violation(
            id=self._editing_id,
            date=self._date_edit.date().toString("yyyy-MM-dd"),
            student_id=stu_id,
            student_name=stu_name,
            student_class=self._class_edit.text().strip(),
            violation_type=self._vtype_combo.currentText().strip(),
            description=self._desc_edit.toPlainText().strip(),
            action_taken=self._action_combo.currentText().strip(),
            reported_by=self._reporter_edit.text().strip(),
        )

    def _on_save(self) -> None:
        v = self._form_to_violation()
        if not v.student_name:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد اسم التلميذ.")
            return
        try:
            if self._editing_id is None:
                add_violation(v)
                QMessageBox.information(self, "تم", _SAVED_OK)
            else:
                update_violation(v)
                QMessageBox.information(self, "تم", _UPDATED_OK)
            self._on_new()
            self._on_search()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def _on_delete(self) -> None:
        if self._editing_id is None:
            QMessageBox.information(self, "تنبيه", "حدد سجلاً من الجدول أولاً.")
            return
        reply = QMessageBox.question(
            self, "تأكيد الحذف", _DEL_CONFIRM,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_violation(self._editing_id)
                self._on_new()
                self._on_search()
            except Exception as exc:
                QMessageBox.critical(self, "خطأ", str(exc))

    def _on_search(self) -> None:
        name_q  = self._search_name.text().strip()
        vtype   = self._filter_type.currentData() or ""
        d_from  = self._date_from.date().toString("yyyy-MM-dd")
        d_to    = self._date_to.date().toString("yyyy-MM-dd")
        results = search_violations(name_q=name_q, date_from=d_from,
                                    date_to=d_to, vtype=vtype)
        self._refresh_table(results)

    def _on_reset_search(self) -> None:
        self._search_name.clear()
        self._filter_type.setCurrentIndex(0)
        self._date_from.setDate(QDate.currentDate().addMonths(-12))
        self._date_to.setDate(QDate.currentDate())
        self._on_search()

    def _on_row_double_click(self) -> None:
        """Load the clicked row into the form for editing."""
        row = self._table.currentRow()
        if row < 0:
            return
        v_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if v_id is None:
            return

        # Reuse the table's current result set so edit mode matches the visible row.
        v = next((x for x in self._current_violations if x.id == v_id), None)
        if v is None:
            return

        self._editing_id = v.id
        self._date_edit.setDate(QDate.fromString(v.date, "yyyy-MM-dd"))
        self._class_edit.setText(v.student_class)
        self._reporter_edit.setText(v.reported_by)
        self._desc_edit.setPlainText(v.description)

        # Set student combo
        for i in range(self._student_combo.count()):
            d = self._student_combo.itemData(i)
            if isinstance(d, Student) and d.id == v.student_id:
                self._student_combo.setCurrentIndex(i)
                break
        else:
            # Manual name entry
            self._student_combo.setCurrentText(v.student_name)

        # Violation type
        idx = self._vtype_combo.findText(v.violation_type)
        if idx >= 0:
            self._vtype_combo.setCurrentIndex(idx)
        else:
            self._vtype_combo.setCurrentText(v.violation_type)

        # Action
        idx = self._action_combo.findText(v.action_taken)
        if idx >= 0:
            self._action_combo.setCurrentIndex(idx)
        else:
            self._action_combo.setCurrentText(v.action_taken)

        self._mode_badge.setText(f"• وضع التعديل  —  سجل #{v.id}")
        self._mode_badge.setStyleSheet(
            f"color:{COLOR_ACCENT}; font-size:12px; font-weight:bold;")

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._load_students()
        self._on_search()
