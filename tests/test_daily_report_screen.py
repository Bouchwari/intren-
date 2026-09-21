import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import DailyAbsence, DailyContact, DailyReport, SchoolSettings
from data import database
from ui import daily_report_screen as drs


class DailyReportScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._original_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.information = self._original_info
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_beneficiary_counts_computed_from_contact_and_absence_sheets(self) -> None:
        """expected = contact sheet total, present = expected minus absent
        — no manual re-entry of numbers already on the other two pages."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=drs.MEAL_GHADA,
            primary_granted=10, collegial_granted=20, qualifying_granted=15, monitors=3,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-11", meal_type=drs.MEAL_GHADA,
            primary_granted=1, collegial_granted=2,
        ))

        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        expected, present = screen._beneficiary_spins[drs.MEAL_GHADA]
        self.assertEqual(expected.value(), 48)  # 10+20+15+3
        self.assertEqual(present.value(), 45)   # 48 - (1+2)
        screen.close()

    def test_beneficiary_counts_zero_with_no_data(self) -> None:
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        expected, present = screen._beneficiary_spins[drs.MEAL_FTOUR]
        self.assertEqual(expected.value(), 0)
        self.assertEqual(present.value(), 0)
        screen.close()

    def test_ramadan_detail_table_shows_iftar_and_shour(self) -> None:
        database.save_school_settings(SchoolSettings(
            school_name="test", school_year="2026", director="d",
            ramadan_start="2026-03-01", ramadan_end="2026-03-30",
        ))
        database.save_daily_contact(DailyContact(
            date="2026-03-10", meal_type=drs.MEAL_IFTAR,
            collegial_granted=12,
        ))
        database.save_daily_contact(DailyContact(
            date="2026-03-10", meal_type=drs.MEAL_SHOUR,
            collegial_granted=9,
        ))
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 3, 10))
        screen._generate()

        labels = {
            screen._contact_table.item(row, 0).text()
            for row in range(screen._contact_table.rowCount())
            if screen._contact_table.item(row, 0) is not None
        }
        self.assertIn("إفطار", labels)
        self.assertIn("سحور", labels)
        self.assertNotIn("فطور", labels)
        self.assertNotIn("غداء", labels)
        screen.close()

    def test_present_never_goes_negative_when_absence_exceeds_contact(self) -> None:
        """Shouldn't happen in real data, but a stray absence entry outside
        the contact sheet's count must not produce a negative "present"."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=drs.MEAL_ASHA, primary_granted=2,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-11", meal_type=drs.MEAL_ASHA, primary_granted=5,
        ))

        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        expected, present = screen._beneficiary_spins[drs.MEAL_ASHA]
        self.assertEqual(expected.value(), 2)
        self.assertEqual(present.value(), 0)
        screen.close()

    def test_saved_beneficiary_override_survives_regenerate(self) -> None:
        """Once a report is saved, clicking "توليد التقرير" again (or
        navigating dates and back) must show the saved numbers, not
        silently recompute and wipe a manual edit the مسير already saved."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=drs.MEAL_GHADA, primary_granted=10,
        ))
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        expected, present = screen._beneficiary_spins[drs.MEAL_GHADA]
        self.assertEqual(expected.value(), 10)  # auto-computed, nothing saved yet

        present.setValue(999)  # مسير manually overrides "الحاضرون فعليا"
        screen._on_save_report()

        screen._generate()  # re-generate, e.g. by navigating dates and back
        expected, present = screen._beneficiary_spins[drs.MEAL_GHADA]
        self.assertEqual(present.value(), 999)  # override preserved, not wiped

        screen._recompute_beneficiary_counts()  # explicit refresh
        expected, present = screen._beneficiary_spins[drs.MEAL_GHADA]
        self.assertEqual(present.value(), 10)  # 10 expected - 0 absent
        screen.close()

    def test_fresh_report_defaults_to_good_except_two_cleanliness_rows(self) -> None:
        """Only dining-hall and dorm cleanliness may vary automatically."""
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        hygiene_good = drs._HYGIENE_SCALE.index("جيدة")
        allowed_variable = {
            drs._HYGIENE_SCALE.index("لا بأس بها"),
            drs._HYGIENE_SCALE.index("حسنة"),
            hygiene_good,
        }
        for field, combo in screen._hygiene_combos.items():
            if field in drs._VARIABLE_HYGIENE_FIELDS:
                self.assertIn(combo.currentData(), allowed_variable)
            else:
                self.assertEqual(combo.currentData(), hygiene_good)
        three_scale_good = drs._THREE_SCALE.index("جيدة")
        for field, combo in screen._quality_combos.items():
            self.assertEqual(combo.currentData(), three_scale_good)
        for field, combo in screen._building_combos.items():
            self.assertEqual(combo.currentData(), three_scale_good)
        screen.close()

    def test_only_allowed_cleanliness_rows_receive_random_suggestions(self) -> None:
        """The two variable rows can use حسنة and لا بأس بها; no other row can."""
        report = DailyReport(date="2026-06-11")
        with patch.object(drs, "suggest_rating_index", side_effect=[4, 3]) as suggest:
            filled = drs._fill_unrated_items(report)

        self.assertEqual(filled.hygiene_dining_hall, 4)  # حسنة
        self.assertEqual(filled.hygiene_dorms, 3)  # لا بأس بها
        self.assertEqual(suggest.call_count, 2)
        for field, _ in drs._HYGIENE_ITEMS:
            if field not in drs._VARIABLE_HYGIENE_FIELDS:
                self.assertEqual(getattr(filled, field), drs._HYGIENE_GOOD)
        for field, _ in drs._QUALITY_ITEMS + drs._BUILDING_ITEMS:
            self.assertEqual(getattr(filled, field), drs._THREE_SCALE_GOOD)

    def test_fresh_report_notes_stay_empty(self) -> None:
        """Notes are free text from the مسير — never auto-filled."""
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertEqual(screen._notes_edit.toPlainText(), "")
        screen.close()

    def test_saved_checklist_ratings_survive_regenerate(self) -> None:
        """An already-saved rating — even a bad one — must never be
        silently replaced by a fresh random suggestion on regenerate."""
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        staff_combo = screen._hygiene_combos["hygiene_staff"]
        staff_combo.setCurrentIndex(staff_combo.findData(0))  # ضعيفة — a real problem today
        screen._on_save_report()

        screen._generate()  # regenerate, e.g. navigating dates and back
        staff_combo = screen._hygiene_combos["hygiene_staff"]
        self.assertEqual(staff_combo.currentData(), 0)  # still ضعيفة, not re-rolled
        screen.close()

    def test_report_table_height_fits_all_rows(self) -> None:
        """Table height must be pinned (min == max), not just capped, or
        the surrounding layout can squeeze it down to almost nothing."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=drs.MEAL_FTOUR, primary_granted=1,
        ))
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertIsNotNone(screen._contact_table)
        expected_height = (len(drs._MEAL_ORDER) * 5 + 1) * 36 + 40
        self.assertEqual(screen._contact_table.minimumHeight(), expected_height)
        self.assertEqual(screen._contact_table.maximumHeight(), expected_height)
        screen.close()

    def test_tables_collapsed_by_default_and_toggle_expands(self) -> None:
        """Both report tables are 16 rows of mostly zeros most days — they
        stay hidden until the مسير explicitly asks to see them, and toggling
        one never touches the other."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=drs.MEAL_FTOUR, primary_granted=1,
        ))
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertTrue(screen._contact_table.isHidden())
        self.assertTrue(screen._absence_table.isHidden())

        screen._toggle_table_section("contact")
        self.assertFalse(screen._contact_table.isHidden())
        self.assertTrue(screen._absence_table.isHidden())
        self.assertEqual(screen._contact_toggle_btn.text(), drs._BTN_HIDE_DETAILS)

        screen._toggle_table_section("contact")
        self.assertTrue(screen._contact_table.isHidden())
        self.assertEqual(screen._contact_toggle_btn.text(), drs._BTN_SHOW_DETAILS)
        screen.close()

    def test_expanded_state_survives_regenerate(self) -> None:
        """Expanding a table, then navigating to another date and back,
        must not silently re-collapse it — that would fight the user's
        own click every time they change dates."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=drs.MEAL_FTOUR, primary_granted=1,
        ))
        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()
        screen._toggle_table_section("contact")
        self.assertFalse(screen._contact_table.isHidden())

        screen._generate()  # e.g. re-generate on the same date
        self.assertFalse(screen._contact_table.isHidden())
        screen.close()

    def test_report_saved_with_blank_checklist_still_gets_suggestions(self) -> None:
        """A report saved before this feature existed (or saved only for
        its notes) has every checklist item at -1 — regenerating it must
        still suggest real ratings, not treat "a row exists" as "already
        answered". This is the exact case that shipped broken."""
        database.save_daily_report(DailyReport(date="2026-06-11", notes="سبق حفظه"))

        screen = drs.DailyReportScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        for field, combo in screen._hygiene_combos.items():
            self.assertNotEqual(combo.currentData(), -1, f"{field} was left at not-rated")
        self.assertEqual(screen._notes_edit.toPlainText(), "سبق حفظه")  # notes untouched
        screen.close()


if __name__ == "__main__":
    unittest.main()
