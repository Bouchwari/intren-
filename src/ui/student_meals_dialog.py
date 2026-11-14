"""Review editable monthly meal counts before exporting the student roster."""
import calendar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from config.settings import MEAL_LABELS
from data.student_meals_repo import (
    MEALS, monthly_student_meals, save_student_meal_changes, monthly_meal_comparison,
)
from ui.dialogs import _button


class StudentMealsDialog(QDialog):
    def __init__(self, months, students, parent=None):
        super().__init__(parent)
        self.setWindowTitle('وجبات التلاميذ الشهرية')
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(900, 600)
        self.students = students
        self.months = [f'{y:04d}-{m:02d}' for y, m in months]
        self.original = {m: monthly_student_meals(m, students) for m in self.months}
        self.edits = {m: {} for m in self.months}
        self.current_month = None
        self.reset_months = set()
        layout = QVBoxLayout(self)
        hint = QLabel('توزيع مقترح للوجبات المسجلة بعد خصم الغياب والعطل على تلاميذ كل فئة. راجع نصيب كل تلميذ.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.month = QComboBox()
        self.month.addItems(self.months)
        layout.addWidget(self.month)
        self.table = QTableWidget(0, 2 + len(MEALS))
        self.table.setHorizontalHeaderLabels(['التلميذ', 'رقم مسار', *[MEAL_LABELS[m] for m in MEALS]])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 125)
        for col in range(2, 2 + len(MEALS)):
            self.table.setColumnWidth(col, 85)
        layout.addWidget(self.table, 1)
        self.comparison = QLabel()
        self.comparison.setWordWrap(True)
        layout.addWidget(self.comparison)
        actions = QHBoxLayout()
        recalculate = _button('إعادة التوزيع من السجلات')
        recalculate.clicked.connect(self._redistribute)
        actions.addWidget(recalculate)
        cancel = _button('إلغاء')
        cancel.clicked.connect(self.reject)
        save = _button('اعتماد الأعداد', primary=True)
        save.clicked.connect(self._save)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)
        self.month.currentTextChanged.connect(self._show_month)
        self._show_month(self.month.currentText())

    def _collect(self):
        if self.current_month is None:
            return
        for row, student in enumerate(self.students):
            changes = self.edits[self.current_month].setdefault(student.id, {})
            for offset, meal in enumerate(MEALS, 2):
                value = self.table.cellWidget(row, offset).value()
                if value != self.original[self.current_month][student.id][meal]:
                    changes[meal] = value
                else:
                    changes.pop(meal, None)

    def _show_month(self, month):
        self._collect()
        self.current_month = month
        self.table.setRowCount(len(self.students))
        maximum = calendar.monthrange(*map(int, month.split('-')))[1]
        for row, student in enumerate(self.students):
            for col, text in enumerate((student.full_name, student.massar_number)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, item)
            for col, meal in enumerate(MEALS, 2):
                editor = QSpinBox()
                editor.setRange(0, maximum)
                editor.setValue(self.edits[month].get(student.id, {}).get(
                    meal, self.original[month][student.id][meal]))
                self.table.setCellWidget(row, col, editor)
                editor.valueChanged.connect(self._update_comparison)
            self.table.setRowHeight(row, 38)
        self._update_comparison()

    def _update_comparison(self):
        counts = {student.id: {meal: self.table.cellWidget(row, col).value()
                              for col, meal in enumerate(MEALS, 2)}
                  for row, student in enumerate(self.students)}
        comparison = monthly_meal_comparison(self.current_month, self.students, counts)
        differences = []
        for key, (detail, recorded) in comparison.items():
            if detail != recorded:
                lot, meal = key.split('_', 1)
                label = 'الابتدائي والإعدادي والمعلمون' if lot == 'lot901' else 'التأهيلي'
                differences.append(f'{label} — {MEAL_LABELS[meal]}  '
                                   f'تفاصيل التلاميذ {detail} / المحضر {recorded} / الفرق {detail - recorded:+d}')
        self.comparison.setText('\n'.join(differences) if differences else 'مجموع التفاصيل يطابق المحضر لجميع الوجبات.')

    def _save(self):
        self._collect()
        try:
            save_student_meal_changes(self.edits, reset_months=self.reset_months)
        except Exception:
            QMessageBox.warning(self, 'خطأ', 'تعذر حفظ أعداد الوجبات. حاول مرة أخرى.')
            return
        self.accept()

    def _redistribute(self):
        month = self.current_month
        self.original[month] = monthly_student_meals(month, self.students, use_saved=False)
        self.edits[month] = {}
        self.reset_months.add(month)
        self.current_month = None
        self._show_month(month)
