import sys
import unittest
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import LevelOption, Student
from ui import students_screen


class StudentsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_choice_text_removes_placeholder_values(self) -> None:
        combo = QComboBox()
        placeholder = next(iter(students_screen._CHOICE_PLACEHOLDERS))
        combo.addItem(placeholder)

        self.assertEqual(students_screen._choice_text(combo), "")

        combo.addItem("Custom level")
        combo.setCurrentText("Custom level")

        self.assertEqual(students_screen._choice_text(combo), "Custom level")

    def test_table_model_infers_missing_cycle_and_type_from_level(self) -> None:
        original_infer = students_screen.infer_level_parts
        students_screen.infer_level_parts = lambda level: ("Cycle A", "General")
        try:
            model = students_screen._StudentTableModel([
                Student(full_name="Student One", student_class="Level 1")
            ])

            self.assertEqual(
                model.data(model.index(0, 5), Qt.ItemDataRole.DisplayRole),
                "Cycle A",
            )
            self.assertEqual(
                model.data(model.index(0, 6), Qt.ItemDataRole.DisplayRole),
                "General",
            )
        finally:
            students_screen.infer_level_parts = original_infer

    def test_add_dialog_uses_filtered_single_level_and_visible_monitor_checkbox(self) -> None:
        original_catalog = students_screen._filtered_level_catalog
        students_screen._filtered_level_catalog = lambda: [
            LevelOption("2A", "Cycle A", "General", "Level 1")
        ]
        try:
            dialog = students_screen._AddEditDialog()
            dialog._name_in.setText("Student One")

            student = dialog.get_student()

            self.assertEqual(student.cycle, "Cycle A")
            self.assertEqual(student.education_type, "General")
            self.assertEqual(student.student_class, "Level 1")
            self.assertIn("QCheckBox#monitorCheck::indicator", dialog._monitor_chk.styleSheet())
            self.assertIn("background: #ffffff", dialog._monitor_chk.styleSheet())
        finally:
            students_screen._filtered_level_catalog = original_catalog


if __name__ == "__main__":
    unittest.main()
