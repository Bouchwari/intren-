import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR,
    RAMADAN_MEALS, REGULAR_MEALS,
)
from core.models import SchoolSettings
from core.ramadan import (
    is_ramadan_day, meals_for_date, month_has_ramadan, parse_iso_date,
    ramadan_days_in_month,
)
from data import database


def _settings(start: str = "", end: str = "") -> SchoolSettings:
    return SchoolSettings(
        school_name="ثانوية اختبار", school_year="2025-2026", director="مدير",
        ramadan_start=start, ramadan_end=end,
    )


class RamadanMealConstantsTests(unittest.TestCase):
    def test_ramadan_meal_keys_keep_their_historic_values(self) -> None:
        """meal_program_screen.py stored Ramadan programs under these exact
        strings long before the constants existed — changing them would
        orphan every saved Ramadan program."""
        self.assertEqual(MEAL_IFTAR, "ftour_ramadan")
        self.assertEqual(MEAL_SHOUR, "shour")

    def test_ramadan_meals_replace_the_normal_ones(self) -> None:
        """Confirmed by the user: during Ramadan the school serves إفطار +
        سحور only, and they replace the three normal meals."""
        self.assertEqual(RAMADAN_MEALS, [MEAL_IFTAR, MEAL_SHOUR])
        self.assertEqual(REGULAR_MEALS, [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA])
        self.assertFalse(set(RAMADAN_MEALS) & set(REGULAR_MEALS))


class IsRamadanDayTests(unittest.TestCase):
    def test_period_boundaries_are_inclusive(self) -> None:
        s = _settings("2026-02-18", "2026-03-19")
        self.assertFalse(is_ramadan_day("2026-02-17", s))
        self.assertTrue(is_ramadan_day("2026-02-18", s))   # first day
        self.assertTrue(is_ramadan_day("2026-03-19", s))   # last day
        self.assertFalse(is_ramadan_day("2026-03-20", s))

    def test_no_period_configured_means_no_ramadan_anywhere(self) -> None:
        """Backward compatibility: a school that never fills this in must see
        exactly the behaviour the app had before the feature existed."""
        self.assertFalse(is_ramadan_day("2026-03-01", _settings()))
        self.assertEqual(meals_for_date("2026-03-01", _settings()), REGULAR_MEALS)

    def test_missing_settings_or_bad_dates_never_raise(self) -> None:
        self.assertFalse(is_ramadan_day("2026-03-01", None))
        self.assertFalse(is_ramadan_day("not-a-date", _settings("2026-02-18", "2026-03-19")))
        self.assertFalse(is_ramadan_day("2026-03-01", _settings("garbage", "also-bad")))
        self.assertIsNone(parse_iso_date("31/03/2026"))
        self.assertIsNone(parse_iso_date(""))

    def test_reversed_period_is_treated_as_a_typo_not_an_inversion(self) -> None:
        reversed_period = _settings("2026-03-19", "2026-02-18")
        self.assertTrue(is_ramadan_day("2026-03-01", reversed_period))
        self.assertFalse(is_ramadan_day("2026-06-01", reversed_period))

    def test_a_day_override_wins_over_the_period_both_ways(self) -> None:
        """Ramadan starts on a moon sighting, so the announced dates move —
        the user must be able to fix one day without shifting the range."""
        s = _settings("2026-02-18", "2026-03-19")
        overrides = {"2026-03-20": True, "2026-03-01": False}
        self.assertTrue(is_ramadan_day("2026-03-20", s, overrides))   # forced on
        self.assertFalse(is_ramadan_day("2026-03-01", s, overrides))  # forced off
        # Days without an override still follow the period.
        self.assertTrue(is_ramadan_day("2026-03-02", s, overrides))

    def test_meals_for_date_switches_the_whole_meal_set(self) -> None:
        s = _settings("2026-02-18", "2026-03-19")
        self.assertEqual(meals_for_date("2026-03-01", s), [MEAL_IFTAR, MEAL_SHOUR])
        self.assertEqual(meals_for_date("2026-04-01", s), [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA])


class RamadanMonthHelpersTests(unittest.TestCase):
    def test_month_has_ramadan_only_for_months_the_period_touches(self) -> None:
        s = _settings("2026-02-18", "2026-03-19")
        self.assertTrue(month_has_ramadan("2026-02", s))
        self.assertTrue(month_has_ramadan("2026-03", s))
        self.assertFalse(month_has_ramadan("2026-01", s))
        self.assertFalse(month_has_ramadan("2026-04", s))

    def test_ramadan_days_in_month_lists_only_the_days_in_range(self) -> None:
        s = _settings("2026-02-18", "2026-03-19")
        february = ramadan_days_in_month("2026-02", s)
        self.assertEqual(february[0], "2026-02-18")
        self.assertEqual(february[-1], "2026-02-28")   # 2026 is not a leap year
        self.assertEqual(len(february), 11)
        march = ramadan_days_in_month("2026-03", s)
        self.assertEqual(march[-1], "2026-03-19")

    def test_a_single_override_can_pull_a_month_into_ramadan(self) -> None:
        s = _settings("2026-02-18", "2026-03-19")
        self.assertFalse(month_has_ramadan("2026-05", s))
        self.assertTrue(month_has_ramadan("2026-05", s, {"2026-05-04": True}))


class RamadanPersistenceTests(unittest.TestCase):
    """The period lives in school_settings; per-day corrections live in their
    own table. Both must survive a round trip."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_period_round_trips_through_settings(self) -> None:
        database.save_school_settings(_settings("2026-02-18", "2026-03-19"))
        loaded = database.get_school_settings()
        self.assertEqual(loaded.ramadan_start, "2026-02-18")
        self.assertEqual(loaded.ramadan_end, "2026-03-19")
        self.assertTrue(is_ramadan_day("2026-03-01", loaded))

    def test_overrides_round_trip_and_can_be_cleared(self) -> None:
        database.set_ramadan_override("2026-03-20", True)
        database.set_ramadan_override("2026-03-01", False)
        self.assertEqual(
            database.get_ramadan_overrides(),
            {"2026-03-20": True, "2026-03-01": False},
        )
        database.clear_ramadan_override("2026-03-01")
        self.assertEqual(database.get_ramadan_overrides(), {"2026-03-20": True})

    def test_setting_the_same_day_twice_updates_rather_than_duplicates(self) -> None:
        database.set_ramadan_override("2026-03-20", True)
        database.set_ramadan_override("2026-03-20", False)
        self.assertEqual(database.get_ramadan_overrides(), {"2026-03-20": False})

    def test_existing_database_without_the_new_columns_is_migrated(self) -> None:
        """A school upgrading from an older build must keep its settings and
        simply get blank Ramadan dates, not a crash."""
        database.save_school_settings(_settings())
        with database._connection() as conn:
            columns = {r["name"] for r in conn.execute(
                "PRAGMA table_info(school_settings)").fetchall()}
        self.assertIn("ramadan_start", columns)
        self.assertIn("ramadan_end", columns)
        self.assertEqual(database.get_school_settings().ramadan_start, "")


if __name__ == "__main__":
    unittest.main()
