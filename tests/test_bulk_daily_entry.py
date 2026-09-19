"""Bulk real-number entry for middle-school full-grant meals."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR
from core.bulk_daily_entry import save_bulk_daily_entries
from core.models import BulkDailyEntry, DailyAbsence, DailyContact, Holiday, SchoolSettings
from data import database
from ui.bulk_daily_entry import BulkDailyEntryDialog


class BulkDailyEntryTests(unittest.TestCase):
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

    def test_service_saves_many_meals_atomically(self) -> None:
        save_bulk_daily_entries([
            BulkDailyEntry("2026-06-01", MEAL_FTOUR, 90, 3),
            BulkDailyEntry("2026-06-01", MEAL_GHADA, 95, 2),
            BulkDailyEntry("2026-06-02", MEAL_ASHA, 88, 4),
        ])

        contacts = database.get_day_contacts("2026-06-01")
        absences = database.get_day_absences("2026-06-01")
        self.assertEqual(
            {item.meal_type: item.collegial_granted for item in contacts},
            {MEAL_FTOUR: 90, MEAL_GHADA: 95},
        )
        self.assertEqual(
            {item.meal_type: item.collegial_granted for item in absences},
            {MEAL_FTOUR: 3, MEAL_GHADA: 2},
        )

    def test_bulk_update_preserves_other_official_form_categories(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=MEAL_GHADA,
            primary_granted=7, collegial_granted=10,
            collegial_complement=4, qualifying_granted=6,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-01", meal_type=MEAL_GHADA,
            primary_granted=1, collegial_granted=2,
            qualifying_granted=3,
        ))

        save_bulk_daily_entries([
            BulkDailyEntry("2026-06-01", MEAL_GHADA, 80, 5),
        ])

        contact = database.get_day_contacts("2026-06-01")[0]
        absence = database.get_day_absences("2026-06-01")[0]
        self.assertEqual(contact.collegial_granted, 80)
        self.assertEqual(contact.primary_granted, 7)
        self.assertEqual(contact.collegial_complement, 4)
        self.assertEqual(contact.qualifying_granted, 6)
        self.assertEqual(absence.collegial_granted, 5)
        self.assertEqual(absence.primary_granted, 1)
        self.assertEqual(absence.qualifying_granted, 3)

    def test_invalid_batch_is_rejected_before_any_row_is_saved(self) -> None:
        with self.assertRaises(ValueError):
            save_bulk_daily_entries([
                BulkDailyEntry("2026-06-01", MEAL_FTOUR, 90, 2),
                BulkDailyEntry("2026-06-01", MEAL_GHADA, 20, 21),
            ])

        self.assertEqual(database.get_day_contacts("2026-06-01"), [])
        self.assertEqual(database.get_day_absences("2026-06-01"), [])

    def test_dialog_pastes_and_saves_one_full_day_without_students(self) -> None:
        dialog = BulkDailyEntryDialog(QDate(2026, 6, 1))
        self.addCleanup(dialog.close)
        dialog._from.setDate(QDate(2026, 6, 1))
        dialog._to.setDate(QDate(2026, 6, 1))
        dialog._load_rows()

        self.assertEqual(dialog._table.rowCount(), 3)
        dialog._table.paste_text("90\t3\n95\t2\n88\t4", 0, 3)
        with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
            dialog._save()

        self.assertEqual(dialog.saved_count, 3)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(database.get_day_contacts("2026-06-01")), 3)
        self.assertEqual(len(database.get_day_absences("2026-06-01")), 3)

    def test_dialog_does_not_save_a_half_completed_meal(self) -> None:
        dialog = BulkDailyEntryDialog(QDate(2026, 6, 1))
        self.addCleanup(dialog.close)
        dialog._from.setDate(QDate(2026, 6, 1))
        dialog._to.setDate(QDate(2026, 6, 1))
        dialog._load_rows()
        dialog._table.item(0, 3).setText("90")

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok):
            dialog._save()

        self.assertEqual(dialog.saved_count, 0)
        self.assertEqual(database.get_day_contacts("2026-06-01"), [])

    def test_holiday_is_locked_and_ramadan_uses_two_meals(self) -> None:
        database.save_school_settings(SchoolSettings(
            school_name="اختبار", school_year="2026/2027", director="مدير",
            ramadan_start="2026-03-01", ramadan_end="2026-03-30",
        ))
        database.add_holiday(Holiday(date="2026-03-02", label="عطلة"))
        dialog = BulkDailyEntryDialog(QDate(2026, 3, 2))
        self.addCleanup(dialog.close)
        dialog._from.setDate(QDate(2026, 3, 1))
        dialog._to.setDate(QDate(2026, 3, 2))
        dialog._load_rows()

        self.assertEqual(dialog._table.rowCount(), 3)
        self.assertEqual(
            [key.meal_type for key in dialog._row_keys],
            [MEAL_IFTAR, MEAL_SHOUR, None],
        )
        holiday_item = dialog._table.item(2, 3)
        self.assertFalse(holiday_item.flags() & Qt.ItemFlag.ItemIsEditable)


if __name__ == "__main__":
    unittest.main()
