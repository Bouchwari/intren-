"""
src/ui/students_screen.py
Student management: view, search, add, edit, delete, import/export Excel.
Three tabs: all beneficiaries / students only / monitors (معلمو الداخلية).
"""
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog,
    QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QTabWidget, QTableView, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_DANGER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    GRANT_LABELS, SECTION_LABELS,
)
from core.excel_handler import (
    infer_level_parts, load_level_catalog, read_students_from_excel,
    write_students_template, write_students_to_excel,
)
from core.models import Student
from data.database import (
    add_student, add_students_bulk, delete_student,
    get_all_students, get_level_preferences, get_students_filtered, update_student,
)

_PAGE_BG = "#f5f5f0"
_PANEL_BG = "#E4E4D7"
_PANEL_BORDER = "#d6d6c8"
_INK = "#5A5A40"
_SUCCESS = "#16a34a"

# ── Arabic UI strings ─────────────────────────────────────────────────────────
_TITLE          = "لائحة التلاميذ والمستفيدين"
_TAB_ALL        = "كل المستفيدين"
_TAB_STUDENTS   = "التلاميذ"
_TAB_MONITORS   = "معلمو الداخلية"
_BTN_ADD        = "➕  إضافة"
_BTN_EDIT       = "✏️  تعديل"
_BTN_DELETE     = "🗑️  حذف"
_BTN_IMPORT     = "📥  استيراد Excel"
_BTN_EXPORT     = "📤  تصدير Excel"
_BTN_TEMPLATE   = "📋  نموذج"
_BTN_SET_LEVEL  = "🎓  مستوى للجميع"
_SEARCH_HINT    = "البحث بالاسم، رقم مسار، المستوى أو رقم المنحة..."
_NO_SEL_MSG     = "الرجاء تحديد صف أولاً."
_DEL_CONFIRM    = "هل أنت متأكد من الحذف؟ لا يمكن التراجع."

_GENDER_LABELS = {
    "": "",
    "male": "ذكر",
    "female": "أنثى",
}

_CHOICE_PLACEHOLDERS = {
    "اختر السلك",
    "اختر السلك أولاً",
    "اختر نوع التعليم",
    "اختر نوع التعليم أولاً",
    "اختر المستوى",
}

_HEADERS = [
    "#", "الاسم الكامل", "رقم مسار", "الجنس", "رقم المنحة",
    "السلك", "نوع التعليم", "المستوى", "بنية الاستقبال",
    "تاريخ الازدياد", "مكان الازدياد",
]


# ── Table model ───────────────────────────────────────────────────────────────

_TABLE_COLUMN_WIDTHS = [44, 260, 140, 90, 145, 125, 125, 210, 150, 130, 150]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = (value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _choice_text(combo: QComboBox) -> str:
    text = combo.currentText().strip()
    return "" if text in _CHOICE_PLACEHOLDERS else text


def _student_cycle(student: Student) -> str:
    if student.cycle:
        return student.cycle
    cycle, _ = infer_level_parts(student.student_class)
    return cycle


def _student_education_type(student: Student) -> str:
    if student.education_type:
        return student.education_type
    _, education_type = infer_level_parts(student.student_class)
    return education_type


def _filtered_level_catalog():
    prefs = get_level_preferences()
    cycles = set(prefs.get("cycles", []))
    education_types = set(prefs.get("education_types", []))
    catalog = load_level_catalog()
    return [
        option for option in catalog
        if (not cycles or option.cycle_label in cycles)
        and (not education_types or option.education_type in education_types)
    ]


def _section_card() -> QFrame:
    card = QFrame()
    card.setObjectName("sectionCard")
    card.setStyleSheet(f"""
        #sectionCard {{
            background: white;
            border: 1px solid {_PANEL_BORDER};
            border-radius: 20px;
        }}
    """)
    return card


def _stat_chip(title: str, value: str, color: str = _INK) -> QFrame:
    chip = QFrame()
    chip.setObjectName("statChip")
    chip.setMinimumHeight(86)
    chip.setMaximumHeight(96)
    chip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    chip.setStyleSheet(f"""
        #statChip {{
            background: white;
            border: 1px solid {_PANEL_BORDER};
            border-radius: 14px;
        }}
    """)
    layout = QVBoxLayout(chip)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)

    title_lbl = QLabel(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
    title_lbl.setMaximumHeight(20)
    title_lbl.setStyleSheet(f"background: transparent; color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: 700;")
    value_lbl = QLabel(value)
    value_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
    value_lbl.setMaximumHeight(34)
    f = QFont(); f.setPointSize(16); f.setBold(True)
    value_lbl.setFont(f)
    value_lbl.setStyleSheet(f"background: transparent; color: {color};")

    layout.addWidget(title_lbl)
    layout.addWidget(value_lbl)
    return chip


class _StudentTableModel(QAbstractTableModel):
    def __init__(self, students: List[Student]) -> None:
        super().__init__()
        self._students: List[Student] = students

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._students)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        s = self._students[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            match col:
                case 0: return str(index.row() + 1)
                case 1: return s.full_name
                case 2: return s.massar_number
                case 3: return _GENDER_LABELS.get(s.gender, s.gender)
                case 4: return s.grant_number
                case 5: return _student_cycle(s)
                case 6: return _student_education_type(s)
                case 7: return s.student_class
                case 8: return SECTION_LABELS.get(s.section, s.section)
                case 9: return s.birth_date
                case 10: return s.birth_place
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _HEADERS[section]
        return None

    def student_at(self, row: int) -> Student:
        return self._students[row]

    def refresh(self, students: List[Student]) -> None:
        self.beginResetModel()
        self._students = students
        self.endResetModel()

    def all_students(self) -> List[Student]:
        return list(self._students)


# ── Add / Edit dialog ─────────────────────────────────────────────────────────

class _AddEditDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None,
                 student: Optional[Student] = None,
                 force_monitor: bool = False) -> None:
        super().__init__(parent)
        self._student = student
        self._force_monitor = force_monitor
        self._level_catalog = _filtered_level_catalog()
        is_edit = student is not None
        self.setWindowTitle("تعديل تلميذ" if is_edit else "إضافة تلميذ")
        self.setMinimumWidth(680)
        self.resize(740, 560)
        self.setObjectName("studentDialog")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            #studentDialog {{
                background: {_PAGE_BG};
            }}
            #studentDialog QLabel {{
                background: transparent;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
            }}
            #studentDialog QComboBox {{
                background: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {_PANEL_BORDER};
                border-radius: 10px;
                padding: 4px 10px;
                min-height: 34px;
                font-size: 13px;
            }}
            #studentDialog QComboBox::drop-down {{
                width: 34px;
                border: none;
                border-left: 1px solid {_PANEL_BORDER};
                background: #f7f7ef;
                border-radius: 8px 0 0 8px;
            }}
            #studentDialog QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {_INK};
            }}
        """)
        self._build_ui()
        if is_edit:
            self._populate(student)  # type: ignore[arg-type]

    def _field(self, placeholder: str = "") -> QLineEdit:
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        w.setMinimumHeight(32)
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        w.setStyleSheet(
            f"background: white; color: {COLOR_TEXT_PRIMARY};"
            f"border: 1px solid {_PANEL_BORDER}; border-radius: 10px;"
            "padding: 4px 10px; font-size: 13px;"
        )
        return w

    def _combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(32)
        combo.setMinimumWidth(250)
        combo.setMaxVisibleItems(8)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return combo

    def _field_box(self, label: str, widget: QWidget) -> QWidget:
        box = QWidget()
        box.setObjectName("compactField")
        box.setStyleSheet("#compactField { background: transparent; }")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        label_widget = QLabel(label)
        label_widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        label_widget.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; font-weight: 700;"
        )
        layout.addWidget(label_widget)
        layout.addWidget(widget)
        return box

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(22, 20, 22, 18)

        heading = QLabel(self.windowTitle())
        f = QFont(); f.setPointSize(13); f.setBold(True)
        heading.setFont(f)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"color: {_INK}; font-size: 16px; font-weight: 800;")
        root.addWidget(heading)

        hint = QLabel("املأ الضروري أولاً، ويمكن ترك باقي الحقول فارغة عند الحاجة.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px;")
        root.addWidget(hint)

        self._name_in      = self._field("الاسم الشخصي والعائلي")
        self._massar_in    = self._field("مثال: H123456789")
        self._grant_in     = self._field("رقم المنحة")
        self._bdate_in     = self._field("مثال: 2010-05-15")
        self._bplace_in    = self._field("مثال: الرباط")

        self._cycle_cb = self._combo()
        cycle_options = _unique([option.cycle_label for option in self._level_catalog])
        self._cycle_options_count = len(cycle_options)
        self._cycle_cb.addItem("اختر السلك" if len(cycle_options) > 1 else "")
        self._cycle_cb.addItems(cycle_options)
        if len(cycle_options) == 1:
            self._cycle_cb.setCurrentText(cycle_options[0])

        self._education_type_cb = self._combo()

        self._class_cb = self._combo()
        self._class_cb.setEditable(True)
        if self._class_cb.lineEdit():
            self._class_cb.lineEdit().setPlaceholderText("اختر المستوى من اللائحة أو اكتب يدوياً")

        self._gender_cb = self._combo()
        self._gender_cb.addItem("", "")
        self._gender_cb.addItem("ذكر", "male")
        self._gender_cb.addItem("أنثى", "female")

        self._section_cb = self._combo()
        for key, label in SECTION_LABELS.items():
            self._section_cb.addItem(label, key)

        self._grant_cb = self._combo()
        for key, label in GRANT_LABELS.items():
            self._grant_cb.addItem(label, key)

        self._monitor_chk = QCheckBox("معلم الداخلية")
        self._monitor_chk.setObjectName("monitorCheck")
        self._monitor_chk.setToolTip("ضع علامة إذا كان هذا المستفيد من معلمي الداخلية.")
        self._monitor_chk.setStyleSheet(f"""
            QCheckBox#monitorCheck {{
                background: transparent;
                color: {COLOR_TEXT_PRIMARY};
                spacing: 10px;
                font-size: 13px;
                font-weight: 700;
            }}
            QCheckBox#monitorCheck::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {_INK};
                border-radius: 3px;
                background: #ffffff;
            }}
            QCheckBox#monitorCheck::indicator:hover {{
                background: #f7f7ef;
            }}
            QCheckBox#monitorCheck::indicator:checked {{
                background: {_INK};
                border-color: {_INK};
            }}
        """)
        if self._force_monitor:
            self._monitor_chk.setChecked(True)
            self._monitor_chk.setEnabled(False)

        self._cycle_cb.currentTextChanged.connect(self._refresh_education_types)
        self._education_type_cb.currentTextChanged.connect(self._refresh_levels)
        self._refresh_education_types()

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)

        form.addWidget(self._field_box("الاسم الكامل *", self._name_in), 0, 0, 1, 2)
        form.addWidget(self._field_box("رقم مسار", self._massar_in), 1, 0)
        form.addWidget(self._field_box("الجنس", self._gender_cb), 1, 1)
        form.addWidget(self._field_box("رقم المنحة", self._grant_in), 2, 0)
        form.addWidget(self._field_box("نوع المنحة", self._grant_cb), 2, 1)
        form.addWidget(self._field_box("السلك", self._cycle_cb), 3, 0)
        form.addWidget(self._field_box("نوع التعليم", self._education_type_cb), 3, 1)
        form.addWidget(self._field_box("المستوى", self._class_cb), 4, 0)
        form.addWidget(self._field_box("بنية الاستقبال", self._section_cb), 4, 1)
        form.addWidget(self._field_box("تاريخ الازدياد", self._bdate_in), 5, 0)
        form.addWidget(self._field_box("مكان الازدياد", self._bplace_in), 5, 1)
        form.addWidget(self._monitor_chk, 6, 0, 1, 2, Qt.AlignmentFlag.AlignRight)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        save_btn   = QPushButton("💾  حفظ")
        cancel_btn = QPushButton("إلغاء")
        save_btn.setMinimumHeight(38)
        cancel_btn.setMinimumHeight(38)
        save_btn.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: white;"
            "font-weight: bold; border-radius: 12px; padding: 0 20px;"
        )
        cancel_btn.setStyleSheet(
            f"background-color: #e2e8f0; color: {COLOR_TEXT_PRIMARY};"
            "border-radius: 12px; padding: 0 20px;"
        )
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

    def _refresh_education_types(self) -> None:
        current = _choice_text(self._education_type_cb)
        cycle = _choice_text(self._cycle_cb)
        wait_for_cycle = not cycle and getattr(self, "_cycle_options_count", 0) > 1
        types = _unique([
            option.education_type for option in self._level_catalog
            if not wait_for_cycle and (not cycle or option.cycle_label == cycle)
        ])
        self._education_type_options_count = len(types)
        self._education_type_cb.blockSignals(True)
        self._education_type_cb.clear()
        placeholder = "اختر السلك أولاً" if wait_for_cycle else ("اختر نوع التعليم" if len(types) > 1 else "")
        self._education_type_cb.addItem(placeholder)
        self._education_type_cb.addItems(types)
        self._education_type_cb.setEnabled(not wait_for_cycle and bool(types))
        idx = self._education_type_cb.findText(current)
        if current and idx >= 0:
            self._education_type_cb.setCurrentIndex(idx)
        elif len(types) == 1:
            self._education_type_cb.setCurrentText(types[0])
        self._education_type_cb.blockSignals(False)
        self._refresh_levels()

    def _refresh_levels(self) -> None:
        current = _choice_text(self._class_cb)
        cycle = _choice_text(self._cycle_cb)
        education_type = _choice_text(self._education_type_cb)
        wait_for_cycle = not cycle and getattr(self, "_cycle_options_count", 0) > 1
        wait_for_type = (
            not wait_for_cycle
            and not education_type
            and getattr(self, "_education_type_options_count", 0) > 1
        )
        levels = _unique([
            option.level_name for option in self._level_catalog
            if not wait_for_cycle
            and not wait_for_type
            and (not cycle or option.cycle_label == cycle)
            and (not education_type or option.education_type == education_type)
        ])
        self._class_cb.blockSignals(True)
        self._class_cb.clear()
        if wait_for_cycle:
            self._class_cb.addItem("اختر السلك أولاً")
        elif wait_for_type:
            self._class_cb.addItem("اختر نوع التعليم أولاً")
        else:
            self._class_cb.addItem("اختر المستوى" if len(levels) > 1 else "")
        self._class_cb.addItems(levels)
        self._class_cb.setEnabled((not wait_for_cycle and not wait_for_type and bool(levels)) or self._class_cb.isEditable())
        if current:
            idx = self._class_cb.findText(current)
            if idx >= 0:
                self._class_cb.setCurrentIndex(idx)
            else:
                self._class_cb.setCurrentText(current)
        elif len(levels) == 1:
            self._class_cb.setCurrentText(levels[0])
        self._class_cb.blockSignals(False)

    def _populate(self, s: Student) -> None:
        self._name_in.setText(s.full_name)
        self._massar_in.setText(s.massar_number)
        cycle = s.cycle
        education_type = s.education_type
        inferred_cycle, inferred_type = infer_level_parts(s.student_class)
        cycle = cycle or inferred_cycle
        education_type = education_type or inferred_type
        cycle_idx = self._cycle_cb.findText(cycle)
        if cycle_idx >= 0:
            self._cycle_cb.setCurrentIndex(cycle_idx)
        elif cycle:
            self._cycle_cb.addItem(cycle)
            self._cycle_cb.setCurrentText(cycle)
        self._refresh_education_types()
        type_idx = self._education_type_cb.findText(education_type)
        if type_idx >= 0:
            self._education_type_cb.setCurrentIndex(type_idx)
        elif education_type:
            self._education_type_cb.addItem(education_type)
            self._education_type_cb.setCurrentText(education_type)
        self._refresh_levels()
        class_idx = self._class_cb.findText(s.student_class)
        if class_idx >= 0:
            self._class_cb.setCurrentIndex(class_idx)
        else:
            self._class_cb.setCurrentText(s.student_class)
        self._bdate_in.setText(s.birth_date)
        self._bplace_in.setText(s.birth_place)
        self._grant_in.setText(s.grant_number)
        self._monitor_chk.setChecked(s.is_monitor)
        idx = self._section_cb.findData(s.section)
        if idx >= 0:
            self._section_cb.setCurrentIndex(idx)
        idx = self._gender_cb.findData(s.gender)
        if idx >= 0:
            self._gender_cb.setCurrentIndex(idx)
        idx = self._grant_cb.findData(s.grant_type)
        if idx >= 0:
            self._grant_cb.setCurrentIndex(idx)

    def _on_save(self) -> None:
        if not self._name_in.text().strip():
            QMessageBox.warning(self, "حقل مطلوب", "الرجاء إدخال الاسم الكامل.")
            return
        self.accept()

    def get_student(self) -> Student:
        level = _choice_text(self._class_cb)
        cycle = _choice_text(self._cycle_cb)
        education_type = _choice_text(self._education_type_cb)
        inferred_cycle, inferred_type = infer_level_parts(level)
        return Student(
            id=self._student.id if self._student else None,
            full_name=self._name_in.text().strip(),
            massar_number=self._massar_in.text().strip(),
            gender=self._gender_cb.currentData(),
            cycle=cycle or inferred_cycle,
            education_type=education_type or inferred_type,
            student_class=level,
            birth_date=self._bdate_in.text().strip(),
            birth_place=self._bplace_in.text().strip(),
            grant_number=self._grant_in.text().strip(),
            section=self._section_cb.currentData(),
            grant_type=self._grant_cb.currentData(),
            is_monitor=self._monitor_chk.isChecked(),
            phone="",
        )


class _LevelPickerDialog(QDialog):
    """Pick one official level and apply it to a batch of students."""

    def __init__(self, parent: Optional[QWidget], title: str, prompt: str) -> None:
        super().__init__(parent)
        self._level_catalog = _filtered_level_catalog()
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(520)
        self.setObjectName("levelPickerDialog")
        self.setStyleSheet(f"""
            #levelPickerDialog {{
                background: {_PAGE_BG};
            }}
            #levelPickerDialog QLabel {{
                background: transparent;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
            }}
            #levelPickerDialog QComboBox {{
                background: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {_PANEL_BORDER};
                border-radius: 10px;
                padding: 4px 10px;
                min-height: 36px;
                font-size: 13px;
            }}
            #levelPickerDialog QComboBox::drop-down {{
                width: 34px;
                border: none;
                border-left: 1px solid {_PANEL_BORDER};
                background: #f7f7ef;
                border-radius: 8px 0 0 8px;
            }}
            #levelPickerDialog QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {_INK};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(16)

        heading = QLabel(title)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        heading.setFont(f)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"color: {_INK}; font-weight: 800;")
        root.addWidget(heading)

        message = QLabel(prompt)
        message.setWordWrap(True)
        message.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; line-height: 1.4;")
        root.addWidget(message)

        self._cycle_cb = QComboBox()
        self._cycle_cb.setMinimumWidth(420)
        cycle_options = _unique([option.cycle_label for option in self._level_catalog])
        self._cycle_options_count = len(cycle_options)
        self._cycle_cb.addItem("اختر السلك" if len(cycle_options) > 1 else "")
        self._cycle_cb.addItems(cycle_options)
        if len(cycle_options) == 1:
            self._cycle_cb.setCurrentText(cycle_options[0])
        root.addWidget(QLabel("السلك"))
        root.addWidget(self._cycle_cb)

        self._education_type_cb = QComboBox()
        self._education_type_cb.setMinimumWidth(420)
        root.addWidget(QLabel("نوع التعليم"))
        root.addWidget(self._education_type_cb)

        self._level_cb = QComboBox()
        self._level_cb.setEditable(True)
        self._level_cb.setMinimumWidth(420)
        if self._level_cb.lineEdit():
            self._level_cb.lineEdit().setPlaceholderText("اختر المستوى أو اكتب يدوياً")
        root.addWidget(QLabel("المستوى"))
        root.addWidget(self._level_cb)

        self._cycle_cb.currentTextChanged.connect(self._refresh_education_types)
        self._education_type_cb.currentTextChanged.connect(self._refresh_levels)
        self._refresh_education_types()

        row = QHBoxLayout()
        cancel = QPushButton("إلغاء")
        apply = QPushButton("تطبيق")
        for btn in (cancel, apply):
            btn.setMinimumHeight(40)
        cancel.setStyleSheet(
            f"background-color: #e2e8f0; color: {COLOR_TEXT_PRIMARY};"
            "border-radius: 12px; padding: 0 20px; font-weight: 700;"
        )
        apply.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: white;"
            "font-weight: bold; border-radius: 12px; padding: 0 20px;"
        )
        cancel.clicked.connect(self.reject)
        apply.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(apply)
        root.addLayout(row)

    def _accept(self) -> None:
        if not self.level:
            QMessageBox.warning(self, "حقل مطلوب", "الرجاء اختيار المستوى.")
            return
        self.accept()

    def _refresh_education_types(self) -> None:
        current = _choice_text(self._education_type_cb)
        cycle = _choice_text(self._cycle_cb)
        wait_for_cycle = not cycle and getattr(self, "_cycle_options_count", 0) > 1
        types = _unique([
            option.education_type for option in self._level_catalog
            if not wait_for_cycle and (not cycle or option.cycle_label == cycle)
        ])
        self._education_type_options_count = len(types)
        self._education_type_cb.blockSignals(True)
        self._education_type_cb.clear()
        placeholder = "اختر السلك أولاً" if wait_for_cycle else ("اختر نوع التعليم" if len(types) > 1 else "")
        self._education_type_cb.addItem(placeholder)
        self._education_type_cb.addItems(types)
        self._education_type_cb.setEnabled(not wait_for_cycle and bool(types))
        idx = self._education_type_cb.findText(current)
        if current and idx >= 0:
            self._education_type_cb.setCurrentIndex(idx)
        elif len(types) == 1:
            self._education_type_cb.setCurrentText(types[0])
        self._education_type_cb.blockSignals(False)
        self._refresh_levels()

    def _refresh_levels(self) -> None:
        current = _choice_text(self._level_cb)
        cycle = _choice_text(self._cycle_cb)
        education_type = _choice_text(self._education_type_cb)
        wait_for_cycle = not cycle and getattr(self, "_cycle_options_count", 0) > 1
        wait_for_type = (
            not wait_for_cycle
            and not education_type
            and getattr(self, "_education_type_options_count", 0) > 1
        )
        levels = _unique([
            option.level_name for option in self._level_catalog
            if not wait_for_cycle
            and not wait_for_type
            and (not cycle or option.cycle_label == cycle)
            and (not education_type or option.education_type == education_type)
        ])
        self._level_cb.blockSignals(True)
        self._level_cb.clear()
        if wait_for_cycle:
            self._level_cb.addItem("اختر السلك أولاً")
        elif wait_for_type:
            self._level_cb.addItem("اختر نوع التعليم أولاً")
        else:
            self._level_cb.addItem("اختر المستوى" if len(levels) > 1 else "")
        self._level_cb.addItems(levels)
        self._level_cb.setEnabled((not wait_for_cycle and not wait_for_type and bool(levels)) or self._level_cb.isEditable())
        if current:
            idx = self._level_cb.findText(current)
            if idx >= 0:
                self._level_cb.setCurrentIndex(idx)
            else:
                self._level_cb.setCurrentText(current)
        elif len(levels) == 1:
            self._level_cb.setCurrentText(levels[0])
        self._level_cb.blockSignals(False)

    @property
    def level(self) -> str:
        return _choice_text(self._level_cb)

    @property
    def cycle(self) -> str:
        level_cycle, _ = infer_level_parts(self.level)
        return _choice_text(self._cycle_cb) or level_cycle

    @property
    def education_type(self) -> str:
        _, level_type = infer_level_parts(self.level)
        return _choice_text(self._education_type_cb) or level_type


# ── Reusable table panel ──────────────────────────────────────────────────────

class _TablePanel(QWidget):
    """A search-box + table panel used inside each tab."""

    def __init__(self, students: List[Student]) -> None:
        super().__init__()
        self._model = _StudentTableModel(students)
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        search = QLineEdit()
        search.setPlaceholderText(_SEARCH_HINT)
        search.setMinimumHeight(38)
        search.setMaximumWidth(420)
        search.setStyleSheet(
            f"border:1px solid {_PANEL_BORDER}; border-radius:14px;"
            "padding:6px 14px; font-size:13px; background:white;"
        )
        search.textChanged.connect(self._proxy.setFilterFixedString)
        layout.addWidget(search)

        table = QTableView()
        table.setModel(self._proxy)
        table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, width in enumerate(_TABLE_COLUMN_WIDTHS):
            table.setColumnWidth(col, width)
        table.setShowGrid(False)
        table.setStyleSheet(f"""
            QTableView {{
                border: 1px solid {_PANEL_BORDER}; border-radius: 14px;
                background: white; alternate-background-color: #f8fafc;
                selection-background-color: {_PANEL_BG};
                selection-color: {COLOR_TEXT_PRIMARY}; font-size: 13px;
            }}
            QHeaderView::section {{
                background-color: #f5f5f0; color: {_INK};
                padding: 9px 12px; border: none;
                border-bottom: 1px solid {_PANEL_BORDER};
                font-weight: bold; font-size: 12px;
            }}
            QTableView::item {{ padding: 7px 12px; border-bottom: 1px solid #f1f5f9; }}
        """)
        self._table = table
        layout.addWidget(table)

    def refresh(self, students: List[Student]) -> None:
        self._model.refresh(students)

    def selected_source_row(self) -> int:
        indexes = self._table.selectedIndexes()
        if not indexes:
            return -1
        return self._proxy.mapToSource(self._proxy.index(indexes[0].row(), 0)).row()

    def student_at(self, row: int) -> Student:
        return self._model.student_at(row)

    def all_students(self) -> List[Student]:
        return self._model.all_students()

    def connect_double_click(self, slot: Any) -> None:
        self._table.doubleClicked.connect(lambda _: slot())


# ── Main screen ───────────────────────────────────────────────────────────────

class StudentsScreen(QWidget):
    """Full student management screen with 3 tabs."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background-color: {_PAGE_BG};")
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = _section_card()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(16)

        title_col = QVBoxLayout()
        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(18); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"background: white; color: {COLOR_TEXT_PRIMARY};")
        subtitle = QLabel("إدارة المستفيدين، الاستيراد من Excel، والتصدير عند الحاجة")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"background: white; color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        header_layout.addLayout(title_col, 1)
        header_layout.addLayout(self._build_toolbar())
        root.addWidget(header)

        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(10)
        root.addLayout(self._stats_grid)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid {_PANEL_BORDER}; border-radius: 18px; background: white; }}
            QTabBar::tab {{
                background: #f5f5f0; color: {COLOR_TEXT_SECONDARY};
                padding: 10px 22px; font-size: 13px; border-radius: 12px;
                margin-left: 2px;
            }}
            QTabBar::tab:selected {{ background: {_INK}; color: white; font-weight: bold; }}
        """)

        self._panel_all      = _TablePanel([])
        self._panel_students = _TablePanel([])
        self._panel_monitors = _TablePanel([])

        self._tabs.addTab(self._panel_all,      _TAB_ALL)
        self._tabs.addTab(self._panel_students,  _TAB_STUDENTS)
        self._tabs.addTab(self._panel_monitors,  _TAB_MONITORS)

        for panel in (self._panel_all, self._panel_students, self._panel_monitors):
            panel.connect_double_click(self._on_edit)

        root.addWidget(self._tabs, 1)

        # Empty state
        self._empty_widget = QWidget()
        elayout = QVBoxLayout(self._empty_widget)
        elayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("لا يوجد تلاميذ — استورد من Excel أو أضف يدوياً")
        lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 16px; margin: 40px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elayout.addWidget(lbl)
        root.addWidget(self._empty_widget)
        self._empty_widget.hide()

        self._stat_cards: list[QFrame] = []
        self._lbl_total = QLabel()
        self._lbl_internat = QLabel()
        self._lbl_cantine = QLabel()
        self._lbl_monitors = QLabel()

    def _build_toolbar(self) -> QGridLayout:
        row = QGridLayout()
        row.setSpacing(8)

        primary_actions = [
            (_BTN_ADD,    self._on_add,    False),
            (_BTN_EDIT,   self._on_edit,   False),
            (_BTN_DELETE, self._on_delete, True),
        ]
        for col, (label, slot, danger) in enumerate(primary_actions):
            btn = self._btn(label, slot, danger=danger)
            row.addWidget(btn, 0, col)

        secondary_actions = [
            (_BTN_IMPORT,   self._on_import),
            (_BTN_EXPORT,   self._on_export),
            (_BTN_TEMPLATE, self._on_template),
            (_BTN_SET_LEVEL, self._on_set_level_for_current_tab),
        ]
        for col, (label, slot) in enumerate(secondary_actions):
            row.addWidget(self._btn(label, slot, secondary=True), 1, col)

        return row

    def _btn(self, label: str, slot: Any, *, danger: bool = False, secondary: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setMinimumHeight(38)
        color = COLOR_DANGER if danger else (_PANEL_BG if secondary else _INK)
        text_color = _INK if secondary else "white"
        border = _PANEL_BORDER if secondary else color
        btn.setStyleSheet(
            f"background:{color}; color:{text_color}; border:1px solid {border};"
            "border-radius:12px; padding:0 12px; font-size:12px; font-weight:700;"
        )
        btn.clicked.connect(slot)
        return btn

    # ── Data ───────────────────────────────────────────────────────────────

    def _load_data(self) -> None:
        try:
            all_s      = get_all_students()
            students   = get_students_filtered(exclude_monitors=True)
            monitors   = get_students_filtered(monitor_only=True)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل البيانات:\n{exc}")
            all_s = students = monitors = []

        self._panel_all.refresh(all_s)
        self._panel_students.refresh(students)
        self._panel_monitors.refresh(monitors)
        self._update_stats(all_s)
        self._refresh_stat_cards(all_s)
        
        if not all_s:
            self._tabs.hide()
            self._empty_widget.show()
        else:
            self._tabs.show()
            self._empty_widget.hide()

    def _update_stats(self, students: List[Student]) -> None:
        total    = len(students)
        internat = sum(1 for s in students if s.section == "internat")
        dar_talib = sum(1 for s in students if s.section == "dar_talib")
        cantine  = sum(1 for s in students if s.section == "cantine")
        monitors = sum(1 for s in students if s.is_monitor)
        self._lbl_total.setText(f"المجموع: {total}")
        self._lbl_internat.setText(f"     القسم الداخلي: {internat}")
        self._lbl_cantine.setText(f"     المطعم: {cantine}")
        self._lbl_monitors.setText(f"     معلمو داخلية: {monitors}")

    def _refresh_stat_cards(self, students: List[Student]) -> None:
        total = len(students)
        internat = sum(1 for s in students if s.section == "internat")
        dar_talib = sum(1 for s in students if s.section == "dar_talib")
        cantine = sum(1 for s in students if s.section == "cantine")
        monitors = sum(1 for s in students if s.is_monitor)

        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        stats = [
            ("المجموع", str(total), _INK),
            ("القسم الداخلي", str(internat), COLOR_ACCENT),
            ("دار الطالب/ة", str(dar_talib), "#e67e22"),
            ("المطعم", str(cantine), _SUCCESS),
            ("معلمو الداخلية", str(monitors), COLOR_DANGER),
        ]
        for i, (title, value, color) in enumerate(stats):
            self._stats_grid.addWidget(_stat_chip(title, value, color), i // 3, i % 3)

    def _current_panel(self) -> _TablePanel:
        return self._tabs.currentWidget()  # type: ignore[return-value]

    def _ask_level(self, title: str, prompt: str) -> tuple[str, str, str]:
        dlg = _LevelPickerDialog(self, title, prompt)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return "", "", ""
        return dlg.cycle, dlg.education_type, dlg.level

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        is_monitor_tab = self._tabs.currentIndex() == 2
        dlg = _AddEditDialog(parent=self, force_monitor=is_monitor_tab)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                add_student(dlg.get_student())
                self._load_data()
            except Exception as exc:
                QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    def _on_edit(self) -> None:
        panel = self._current_panel()
        row = panel.selected_source_row()
        if row < 0:
            QMessageBox.information(self, "تنبيه", _NO_SEL_MSG)
            return
        dlg = _AddEditDialog(parent=self, student=panel.student_at(row))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                update_student(dlg.get_student())
                self._load_data()
            except Exception as exc:
                QMessageBox.critical(self, "خطأ", f"تعذر التحديث:\n{exc}")

    def _on_delete(self) -> None:
        panel = self._current_panel()
        row = panel.selected_source_row()
        if row < 0:
            QMessageBox.information(self, "تنبيه", _NO_SEL_MSG)
            return
        s = panel.student_at(row)
        reply = QMessageBox.question(
            self, "تأكيد الحذف", f"حذف:  {s.full_name}\n\n{_DEL_CONFIRM}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_student(s.id)  # type: ignore[arg-type]
                self._load_data()
            except Exception as exc:
                QMessageBox.critical(self, "خطأ", f"تعذر الحذف:\n{exc}")

    def _on_import(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "استيراد ملف Excel", "", "Excel (*.xlsx *.xls)"
        )
        if not path_str:
            return
        try:
            students = read_students_from_excel(Path(path_str))
            missing_level = [s for s in students if not s.student_class.strip()]
            if missing_level:
                cycle, education_type, level = self._ask_level(
                    "تحديد المستوى دفعة واحدة",
                    f"هذا الملف لا يحتوي على المستوى لـ {len(missing_level)} تلميذ.\n"
                    "اختر المستوى مرة واحدة وسيتم تطبيقه عليهم جميعاً.",
                )
                if level:
                    for student in missing_level:
                        student.cycle = cycle
                        student.education_type = education_type
                        student.student_class = level
            count = add_students_bulk(students)
            self._load_data()
            QMessageBox.information(self, "تم", f"تم استيراد {count} تلميذ.")
        except ValueError as exc:
            QMessageBox.warning(self, "خطأ في الملف", str(exc))
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def _on_export(self) -> None:
        students = self._current_panel().all_students()
        if not students:
            QMessageBox.information(self, "تنبيه", "لا توجد بيانات للتصدير.")
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, "تصدير", "التلاميذ.xlsx", "Excel (*.xlsx)"
        )
        if not path_str:
            return
        try:
            write_students_to_excel(students, Path(path_str))
            QMessageBox.information(self, "تم", "تم التصدير بنجاح.")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def _on_template(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, "حفظ النموذج", "نموذج_التلاميذ.xlsx", "Excel (*.xlsx)"
        )
        if not path_str:
            return
        try:
            write_students_template(Path(path_str), _filtered_level_catalog())
            QMessageBox.information(self, "تم", "تم تحميل النموذج. عبّئه ثم استورده.")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def _on_set_level_for_current_tab(self) -> None:
        students = self._current_panel().all_students()
        if not students:
            QMessageBox.information(self, "تنبيه", "لا توجد بيانات لتعيين المستوى.")
            return

        cycle, education_type, level = self._ask_level(
            "تعيين المستوى للجميع",
            f"سيتم تطبيق مستوى واحد على {len(students)} سجل في التبويب الحالي.\n"
            "هذا مفيد عندما تكون اللائحة كلها لنفس المستوى.",
        )
        if not level:
            return

        reply = QMessageBox.question(
            self,
            "تأكيد التغيير",
            f"هل تريد تطبيق المستوى:\n{level}\n\nعلى {len(students)} سجل؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            for student in students:
                student.cycle = cycle
                student.education_type = education_type
                student.student_class = level
                update_student(student)
            self._load_data()
            QMessageBox.information(self, "تم", "تم تعيين المستوى بنجاح.")
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر تعيين المستوى:\n{exc}")
