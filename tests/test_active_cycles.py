import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.active_cycles import chosen_cycles, cycle_from_label, visible_cycles
from core.contact_counts import (
    CATEGORY_COLLEGIAL, CATEGORY_PRIMARY, CATEGORY_QUALIFYING,
)
from core.models import DailyContact
from data import database
from ui import daily_absence_screen as absence_ui
from ui import daily_contact_screen as contact_ui
from ui import daily_report_screen as report_ui
from ui import feedback_screen as feedback_ui
from ui import order_letter_screen as order_ui


class ActiveCycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_labels_map_to_cycle_codes(self) -> None:
        self.assertEqual(cycle_from_label("الثانوي الإعدادي"), CATEGORY_COLLEGIAL)
        self.assertEqual(cycle_from_label("التعليم الابتدائي"), CATEGORY_PRIMARY)
        self.assertEqual(cycle_from_label("الثانوي التأهيلي"), CATEGORY_QUALIFYING)
        self.assertIsNone(cycle_from_label("غير معروف"))

    def test_no_selection_keeps_all_cycles_visible(self) -> None:
        preferences = {"cycles": [], "education_types": []}
        self.assertEqual(chosen_cycles(preferences), set())
        self.assertEqual(visible_cycles(preferences), [
            CATEGORY_PRIMARY, CATEGORY_COLLEGIAL, CATEGORY_QUALIFYING,
        ])

    def test_middle_school_only_hides_other_empty_cycles(self) -> None:
        preferences = {"cycles": ["الثانوي الإعدادي"], "education_types": []}
        self.assertEqual(visible_cycles(preferences), [CATEGORY_COLLEGIAL])

    def test_saved_data_keeps_a_cycle_visible(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-08-31", meal_type="ghada", primary_granted=3,
        ))
        preferences = {"cycles": ["الثانوي الإعدادي"], "education_types": []}
        self.assertEqual(visible_cycles(preferences), [
            CATEGORY_PRIMARY, CATEGORY_COLLEGIAL,
        ])

    def test_daily_cards_show_middle_school_and_monitors_only(self) -> None:
        visible = (CATEGORY_COLLEGIAL,)
        widgets = [
            contact_ui._MealCard("ghada", "غداء", "#000000", visible),
            absence_ui._AbsenceCard("ghada", "غداء", "#000000", visible),
            order_ui._MealQtyCard("ghada", "غداء", "#000000", visible),
        ]
        for widget in widgets:
            labels = {label.text() for label in widget.findChildren(QLabel)}
            self.assertIn("إعدادي", labels)
            self.assertIn("معلمو الداخلية", labels)
            self.assertNotIn("الابتدائي", labels)
            self.assertNotIn("تأهيلي", labels)
            widget.close()

    def test_feedback_group_picker_follows_selected_cycles(self) -> None:
        database.save_level_preferences(["الثانوي الإعدادي"], [])
        screen = feedback_ui.FeedbackScreen()
        choices = [screen._cycle_combo.itemData(index)
                   for index in range(screen._cycle_combo.count())]
        self.assertEqual(choices, ["", CATEGORY_COLLEGIAL])
        screen.close()

    def test_daily_report_table_leaves_out_unused_cycle_rows(self) -> None:
        database.save_level_preferences(["الثانوي الإعدادي"], [])
        screen = report_ui.DailyReportScreen()
        table = screen._make_report_table({})
        sectors = {
            table.item(row, 1).text()
            for row in range(table.rowCount())
            if table.item(row, 1) is not None
        }
        self.assertIn("إعدادي", sectors)
        self.assertIn("معلمو الداخلية", sectors)
        self.assertNotIn("الابتدائي", sectors)
        self.assertNotIn("تأهيلي", sectors)
        table.close()
        screen.close()

    def test_absence_history_leaves_out_unused_cycle_columns(self) -> None:
        database.save_level_preferences(["الثانوي الإعدادي"], [])
        screen = absence_ui.DailyAbsenceScreen()
        headers = [
            screen._history_table.horizontalHeaderItem(index).text()
            for index in range(screen._history_table.columnCount())
        ]
        self.assertIn("إعدادي (ك)", headers)
        self.assertNotIn("ابتدائي (ك)", headers)
        self.assertNotIn("تأهيلي (ك)", headers)
        self.assertEqual(headers[-1], "الإجمالي")
        screen.close()


if __name__ == "__main__":
    unittest.main()
