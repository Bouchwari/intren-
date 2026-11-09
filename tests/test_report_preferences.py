import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QDate, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from core.models import DailyContact, DailyReport, Holiday
from core.report_defaults import (
    default_report_preferences, fill_report_defaults, apply_report_overrides,
    normalize_report_preferences,
)
from data import database
from data.daily_repo import save_new_daily_reports
from data.settings_repo import get_report_preferences, save_report_preferences
from ui import report_options as options
from ui import daily_report_screen as drs


class ReportPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.existing_windows = set(self.app.topLevelWidgets())
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "test.db"
        database.init_database()

    def tearDown(self) -> None:
        # Flush deferred Qt deletion before pytest's final Python GC on Windows.
        for window in self.app.topLevelWidgets():
            if window not in self.existing_windows:
                window.close()
                window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        database.DB_PATH = self.original
        self.temp.cleanup()

    def test_preferences_round_trip_and_old_defaults(self) -> None:
        prefs = get_report_preferences()
        self.assertEqual(prefs, default_report_preferences())
        prefs["variation"] = 40
        prefs["rules"]["hygiene_staff"] = {"base": 4, "alternatives": [5, 3]}
        save_report_preferences(prefs)
        self.assertEqual(get_report_preferences(), prefs)

    def test_invalid_preferences_are_rejected_without_replacing_saved_rules(self) -> None:
        prefs = default_report_preferences()
        for bad in (dict(prefs, variation=-1), dict(prefs, variation=True),
                    dict(prefs, rules={"hygiene_staff": {"base": 9}}),
                    dict(prefs, rules={"unknown": {"base": 0}})):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                save_report_preferences(bad)
        self.assertEqual(get_report_preferences(), prefs)

    def test_corrupt_stored_preferences_fall_back_safely(self) -> None:
        with database._connection() as conn:
            conn.execute("INSERT INTO app_preferences VALUES (?, ?)",
                         ("daily_report_preferences", "{broken"))
        with self.assertLogs("data.settings_repo", level="WARNING"):
            self.assertEqual(get_report_preferences(), default_report_preferences())

    def test_same_date_stays_stable_and_different_dates_can_vary(self) -> None:
        prefs = default_report_preferences()
        prefs["variation"] = 100
        values = []
        for day in range(1, 29):
            report = DailyReport(date=f"2026-10-{day:02d}")
            first = fill_report_defaults(report, prefs)
            self.assertEqual(first, fill_report_defaults(report, prefs))
            values.append(first.hygiene_dorms)
        self.assertEqual(set(values), {3, 4})

    def test_zero_variation_fixed_manual_and_saved_values(self) -> None:
        prefs = default_report_preferences()
        prefs["variation"] = 0
        prefs["rules"]["quality_storage"] = {"base": -1, "alternatives": []}
        fresh = fill_report_defaults(DailyReport(date="2026-10-31"), prefs)
        self.assertEqual(fresh.hygiene_dorms, 5)
        self.assertEqual(fresh.quality_storage, -1)
        saved = DailyReport(date="2026-10-30", id=1, hygiene_staff=0, notes="saved")
        self.assertEqual(fill_report_defaults(saved, prefs), saved)
        self.assertEqual(apply_report_overrides(saved, None), saved)
        self.assertEqual(apply_report_overrides(saved, {"notes": "changed"}).notes, "changed")

    def test_preferences_widget_edits_and_saves_actual_controls(self) -> None:
        widget = options.ReportPreferencesWidget()
        widget.variation.setValue(25)
        base, alt1, alt2 = widget.combos["hygiene_staff"]
        base.setCurrentIndex(base.findData(4))
        alt1.setCurrentIndex(alt1.findData(5))
        with patch.object(QMessageBox, "information"):
            widget.save()
        self.assertEqual(get_report_preferences()["variation"], 25)
        self.assertEqual(get_report_preferences()["rules"]["hygiene_staff"],
                         {"base": 4, "alternatives": [5]})
        base.setCurrentIndex(base.findData(-1))
        self.assertFalse(alt1.isEnabled())
        widget.close()

    def test_date_notes_and_ratings_survive_navigation_without_saving(self) -> None:
        dates = ["2026-10-28", "2026-10-29", "2026-10-30"]
        database.save_daily_report(DailyReport(date=dates[2], notes="Saved", hygiene_staff=0))
        dialog = options.ReportReviewDialog(dates)
        dialog.notes.setPlainText("ملاحظة خاصة بهذا اليوم")
        combo = dialog.combos["hygiene_staff"]
        combo.setCurrentIndex(combo.findData(2))
        dialog.days.setCurrentRow(1)
        self.assertEqual(dialog.notes.toPlainText(), "")
        dialog.days.setCurrentRow(0)
        self.assertEqual(dialog.notes.toPlainText(), "ملاحظة خاصة بهذا اليوم")
        self.assertEqual(combo.currentData(), 2)
        dialog.days.setCurrentRow(2)
        self.assertTrue(combo.isEnabled())
        self.assertFalse(dialog.notes.isReadOnly())
        result = dialog.overrides()
        self.assertNotIn(dates[2], result)
        dialog.notes.setPlainText("Edited")
        dialog.days.setCurrentRow(0)
        dialog.days.setCurrentRow(2)
        self.assertEqual(dialog.notes.toPlainText(), "Edited")
        self.assertEqual(dialog.overrides()[dates[2]], {"notes": "Edited"})
        self.assertIsNone(database.get_daily_report(dates[0]))
        dialog.reject()
        self.assertEqual(database.get_daily_report(dates[2]).notes, "Saved")
        self.assertIsNone(database.get_daily_report(dates[0]))

    def test_override_counts_are_never_accepted_and_new_save_is_atomic(self) -> None:
        with self.assertRaises(ValueError):
            apply_report_overrides(DailyReport(date="2026-10-28"), {"ghada_expected": 999})
        original = DailyReport(date="2026-10-29", notes="Saved")
        database.save_daily_report(original)
        save_new_daily_reports([DailyReport(date="2026-10-28", notes="New"),
                                DailyReport(date="2026-10-29", notes="Do not overwrite")])
        self.assertEqual(database.get_daily_report("2026-10-29").notes, "Saved")
        self.assertEqual(database.get_daily_report("2026-10-28").notes, "New")

    def test_daily_screen_review_saves_selected_notes_and_fresh_counts(self) -> None:
        date = "2026-10-28"
        database.save_daily_contact(DailyContact(date=date, meal_type="ghada", collegial_granted=37))
        screen = drs.DailyReportScreen()
        with patch.object(drs, "pick_date_range", return_value=(QDate(2026, 10, 28), QDate(2026, 10, 28))), \
             patch.object(options, "review_report_range", return_value={date: {"notes": "Special", "hygiene_staff": 1}}), \
             patch.object(QMessageBox, "information"):
            screen._review_range()
        report = database.get_daily_report(date)
        self.assertEqual((report.notes, report.hygiene_staff, report.ghada_expected), ("Special", 1, 37))
        screen.close()

    def test_review_changes_saved_notes_and_ratings_but_preserves_counts(self) -> None:
        day = "2026-10-28"
        database.save_daily_report(DailyReport(date=day, notes="Before", ghada_expected=45, ghada_present=40))
        screen = drs.DailyReportScreen()
        with patch.object(drs, "pick_date_range", return_value=(QDate(2026, 10, 28), QDate(2026, 10, 28))), \
             patch.object(options, "review_report_range", return_value={day: {"notes": "After", "hygiene_staff": 3}}), \
             patch.object(QMessageBox, "information"):
            screen._review_range()
        report = database.get_daily_report(day)
        self.assertEqual((report.notes, report.hygiene_staff, report.ghada_expected, report.ghada_present),
                         ("After", 3, 45, 40))
        screen.close()

    def test_holidays_and_empty_days_are_excluded_and_cancel_does_not_save(self) -> None:
        database.add_holiday(Holiday(date="2026-10-29", label="Holiday"))
        database.save_daily_contact(DailyContact(date="2026-10-28", meal_type="ghada", collegial_granted=10))
        with patch.object(options, "ReportReviewDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Rejected
            result = options.review_report_range(None, QDate(2026, 10, 28), QDate(2026, 10, 30))
            dialog.assert_called_once_with(["2026-10-28"], None)
        self.assertIsNone(result)
        self.assertIsNone(database.get_daily_report("2026-10-28"))
