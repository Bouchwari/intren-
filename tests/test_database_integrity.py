import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import DailyAbsence, DailyContact, Student, Violation
from data import database, stats_repository


class DatabaseIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test_matama.db"
        self._original_database_path = database.DB_PATH
        self._original_stats_path = stats_repository.DB_PATH
        database.DB_PATH = self.db_path
        stats_repository.DB_PATH = self.db_path
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_database_path
        stats_repository.DB_PATH = self._original_stats_path
        self._tmpdir.cleanup()

    def test_deleting_student_nulls_linked_violation_student_id(self) -> None:
        student_id = database.add_student(Student(full_name="Test Student"))
        database.add_violation(
            Violation(
                date="2026-05-20",
                student_id=student_id,
                student_name="Test Student",
                violation_type="Late",
            )
        )

        database.delete_student(student_id)

        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT student_id FROM violations LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row[0])

    def test_dashboard_stats_use_full_meal_totals(self) -> None:
        today = date.today().isoformat()
        database.save_daily_contact(
            DailyContact(
                date=today,
                meal_type="ftour",
                collegial_granted=1,
                collegial_paying=2,
                collegial_complement=3,
                qualifying_granted=4,
                qualifying_paying=5,
                qualifying_complement=6,
                monitors=7,
            )
        )
        database.save_daily_absence(
            DailyAbsence(
                date=today,
                meal_type="ftour",
                collegial_granted=1,
                collegial_paying=1,
                collegial_complement=1,
                qualifying_granted=1,
                qualifying_paying=1,
                qualifying_complement=1,
                monitors=1,
            )
        )

        stats = database.get_dashboard_stats()

        self.assertEqual(stats["today"]["contact"]["ftour"], 28)
        self.assertEqual(stats["today"]["absence"]["ftour"], 7)
        self.assertEqual(stats["month"]["meals_total"], 28)
        self.assertEqual(stats["month"]["absences_total"], 7)
        self.assertIn((today, 28), stats["week_activity"])

    def test_monthly_summaries_calculate_net_totals_and_costs(self) -> None:
        database.save_daily_contact(
            DailyContact(
                date="2026-05-01",
                meal_type="ftour",
                collegial_granted=3,
                collegial_paying=2,
                qualifying_granted=4,
                monitors=1,
            )
        )
        database.save_daily_contact(
            DailyContact(
                date="2026-05-02",
                meal_type="ftour",
                collegial_complement=5,
                qualifying_paying=2,
                qualifying_complement=1,
            )
        )
        database.save_daily_absence(
            DailyAbsence(
                date="2026-05-01",
                meal_type="ftour",
                collegial_granted=2,
                qualifying_granted=1,
                monitors=1,
            )
        )

        summaries = database.get_monthly_summaries(
            "2026-05",
            {"ftour": "2.5", "ghada": "0", "asha": "0"},
        )
        ftour_summary = next(s for s in summaries if s.meal_type == "ftour")

        self.assertEqual(ftour_summary.days_count, 2)
        self.assertEqual(ftour_summary.contact_collegial, 10)
        self.assertEqual(ftour_summary.contact_qualifying, 7)
        self.assertEqual(ftour_summary.contact_monitors, 1)
        self.assertEqual(ftour_summary.absence_collegial, 2)
        self.assertEqual(ftour_summary.absence_qualifying, 1)
        self.assertEqual(ftour_summary.absence_monitors, 1)
        self.assertEqual(ftour_summary.net_total, 14)
        self.assertEqual(ftour_summary.total_cost, 35.0)

    def test_level_preferences_round_trip(self) -> None:
        database.save_level_preferences(["الإعدادي"], ["عام"])

        prefs = database.get_level_preferences()

        self.assertEqual(prefs["cycles"], ["الإعدادي"])
        self.assertEqual(prefs["education_types"], ["عام"])

    def test_meal_program_ramadan_mode_round_trip(self) -> None:
        program_id = database.create_program("Weekly", "2025-2026", False)

        database.set_program_ramadan_mode(program_id, True)

        programs = database.get_all_programs()

        self.assertEqual(len(programs), 1)
        self.assertTrue(programs[0].is_ramadan)


if __name__ == "__main__":
    unittest.main()
