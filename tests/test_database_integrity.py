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

from core.models import (
    DailyAbsence, DailyContact, Holiday, InfractionRecord, Student,
)
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

    def test_dashboard_violation_card_counts_this_months_infractions(self) -> None:
        """The dashboard's "المخالفات" card counts محضر المخالفة — the PV against
        the CATERING COMPANY. It used to count the student-discipline log, a
        document that never existed in the user's job; that screen and its
        table were retired 2026-08-28 and the card was repointed here."""
        from data.infraction_repo import save_infraction

        today = date.today()
        for number in (1, 2):
            save_infraction(InfractionRecord(
                date=today.replace(day=5).isoformat(), document_number=number,
                year=today.year, infraction_type="تأخر في تقديم الوجبة",
                description="x", written_date=today.isoformat()))
        # A PV from another month must not leak into this month's card.
        save_infraction(InfractionRecord(
            date="2020-01-09", document_number=1, year=2020,
            infraction_type="تأخر في تقديم الوجبة", description="x",
            written_date="2020-01-09"))

        summary = stats_repository.fetch_month_summary(today.year, today.month)
        self.assertEqual(summary.infractions_count, 2)

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

    def test_holiday_add_query_and_delete_round_trip(self) -> None:
        database.add_holiday(Holiday(date="2026-06-15", label="عطلة نصف السنة"))
        database.add_holiday(Holiday(date="2026-03-21", label="طريق مقطوعة بسبب الثلج"))

        self.assertTrue(database.is_holiday("2026-06-15"))
        self.assertFalse(database.is_holiday("2026-06-16"))
        all_holidays = database.get_all_holidays()
        self.assertEqual([h.date for h in all_holidays], ["2026-03-21", "2026-06-15"])

        database.add_holiday(Holiday(date="2026-06-15", label="محدث"))  # same date -> updates label
        self.assertEqual(database.get_all_holidays()[1].label, "محدث")
        self.assertEqual(len(database.get_all_holidays()), 2)

        database.delete_holiday("2026-06-15")
        self.assertFalse(database.is_holiday("2026-06-15"))
        self.assertEqual(len(database.get_all_holidays()), 1)


if __name__ == "__main__":
    unittest.main()
