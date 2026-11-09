import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from core.holiday_calendar import calendar_days, default_calendar_rows, pending_hijri, validate_calendar_rows
from core.models import Holiday, SchoolSettings, DailyReport
from data import database
from data.holiday_calendar_repo import calendar_notice, get_calendar_state, save_reviewed_calendar
from ui.holiday_calendar_dialog import HolidayCalendarDialog


class HolidayCalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_PATH", Path(self.temp.name) / "test.db")
        self.db_patch.start()
        database.init_database()
        database.save_school_settings(SchoolSettings(school_year="2026/2027", school_name="Test", director="Test"))

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_transcribed_dates_include_both_endpoints_and_do_not_guess_hijri(self):
        rows = default_calendar_rows()
        days = calendar_days(rows)
        self.assertEqual(len(rows), 15)
        self.assertEqual(len(days), 47)
        self.assertEqual(len(pending_hijri(rows)), 3)
        for start, end in (("2026-10-18", "2026-10-25"), ("2026-12-06", "2026-12-13"),
                           ("2027-01-24", "2027-01-31"), ("2027-03-21", "2027-03-28"),
                           ("2027-05-09", "2027-05-16")):
            self.assertIn(start, days)
            self.assertIn(end, days)
        for day in ("2026-10-31", "2026-11-06", "2026-11-18", "2027-01-01",
                    "2027-01-11", "2027-01-14", "2027-05-01"):
            self.assertIn(day, days)
        for row in rows:
            if row["hijri"]:
                self.assertFalse(row["enabled"])
                self.assertEqual((row["start"], row["end"]), ("", ""))

    def test_invalid_or_unconfirmed_dates_are_rejected_without_writes(self):
        for changes in ({"start": "2026-10-26"}, {"start": "2025-10-18"},
                        {"end": "2026-02-30"}, {"start": ""}):
            rows = default_calendar_rows()
            rows[0].update(changes)
            with self.assertRaises(ValueError):
                save_reviewed_calendar(rows)
        rows = default_calendar_rows()
        rows[9]["enabled"] = True
        with self.assertRaises(ValueError):
            validate_calendar_rows(rows)
        self.assertEqual(database.get_all_holidays(), [])
        self.assertFalse(get_calendar_state()["reviewed"])

    def test_import_is_idempotent_preserves_manual_entries_and_reports(self):
        database.add_holiday(Holiday(date="2026-10-18", label="Manual"))
        database.save_daily_report(DailyReport(date="2026-10-18", notes="Keep"))
        self.assertEqual(save_reviewed_calendar(default_calendar_rows()), (46, 1))
        self.assertEqual(save_reviewed_calendar(default_calendar_rows()), (0, 47))
        self.assertEqual(len(database.get_all_holidays()), 47)
        self.assertEqual(database.get_all_holidays()[0].label, "Manual")
        self.assertEqual(database.get_daily_report("2026-10-18").notes, "Keep")

    def test_editing_imported_range_only_removes_unchanged_owned_days(self):
        rows = default_calendar_rows()
        save_reviewed_calendar(rows)
        database.add_holiday(Holiday(date="2026-10-18", label="Manually changed"))
        rows[0]["start"] = "2026-10-20"
        save_reviewed_calendar(rows)
        days = {row.date: row.label for row in database.get_all_holidays()}
        self.assertEqual(days["2026-10-18"], "Manually changed")
        self.assertNotIn("2026-10-19", days)
        self.assertIn("2026-10-20", days)

    def test_pending_reminder_survives_reload_until_hijri_dates_are_entered(self):
        self.assertIn("انتظار", calendar_notice())
        save_reviewed_calendar(default_calendar_rows())
        self.assertIn("3", calendar_notice())
        rows = get_calendar_state()["rows"]
        # Synthetic dates verify the workflow; these are not calendar predictions.
        for row, day in zip([row for row in rows if row["hijri"]], ("2027-02-01", "2027-04-01", "2027-06-01")):
            row.update(start=day, end=day, enabled=True)
        save_reviewed_calendar(rows)
        self.assertEqual(calendar_notice(), "")
        database.save_school_settings(SchoolSettings(school_year="2027/2028", school_name="Test", director="Test"))
        self.assertEqual(calendar_notice(), "")

    def test_cancel_and_missing_confirmation_never_import(self):
        dialog = HolidayCalendarDialog()
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog._apply()
        dialog.reject()
        self.assertEqual(database.get_all_holidays(), [])
        self.assertFalse(get_calendar_state()["reviewed"])

    def test_approval_persists_review_and_selected_days(self):
        dialog = HolidayCalendarDialog()
        dialog.confirm.setChecked(True)
        self.assertTrue(dialog.apply_button.isEnabled())
        with patch.object(QMessageBox, "information"):
            dialog._apply()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(get_calendar_state()["reviewed"])
        self.assertEqual(len(database.get_all_holidays()), 47)
