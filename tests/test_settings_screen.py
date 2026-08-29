import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import Holiday, SchoolSettings
from data import database
from ui import settings_screen as ss


class SchoolSettingsCityFrTests(unittest.TestCase):
    """city_fr (added after the user asked for a French place name on the
    reception document's closing line) must round-trip through the real
    DB, including for an existing row saved before this column existed."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_city_fr_saves_and_loads_alongside_arabic_city(self) -> None:
        database.save_school_settings(SchoolSettings(
            school_name="test", school_year="2026", director="d",
            city="إغيل نمكون", city_fr="Ighil Ncoun",
        ))
        s = database.get_school_settings()
        self.assertEqual(s.city, "إغيل نمكون")
        self.assertEqual(s.city_fr, "Ighil Ncoun")

    def test_city_fr_defaults_to_blank_for_a_row_saved_before_the_column_existed(self) -> None:
        """Simulates an existing user's database: a row saved without
        ever setting city_fr must still load cleanly, not crash."""
        database.save_school_settings(SchoolSettings(
            school_name="test", school_year="2026", director="d", city="أكادير",
        ))
        s = database.get_school_settings()
        self.assertEqual(s.city, "أكادير")
        self.assertEqual(s.city_fr, "")


class GroupConsecutiveHolidaysTests(unittest.TestCase):
    def test_consecutive_same_label_days_collapse_into_one_group(self) -> None:
        holidays = [
            Holiday(date="2026-08-13", label="عطلة الصيف"),
            Holiday(date="2026-08-14", label="عطلة الصيف"),
            Holiday(date="2026-08-15", label="عطلة الصيف"),
        ]
        groups = ss._group_consecutive_holidays(holidays)
        self.assertEqual(len(groups), 1)
        start, end, label, dates = groups[0]
        self.assertEqual((start, end, label), ("2026-08-13", "2026-08-15", "عطلة الصيف"))
        self.assertEqual(dates, ["2026-08-13", "2026-08-14", "2026-08-15"])

    def test_gap_in_dates_breaks_the_group_even_with_same_label(self) -> None:
        holidays = [
            Holiday(date="2026-08-13", label="عطلة"),
            Holiday(date="2026-08-15", label="عطلة"),  # skips the 14th
        ]
        groups = ss._group_consecutive_holidays(holidays)
        self.assertEqual(len(groups), 2)

    def test_different_label_breaks_the_group_even_on_consecutive_dates(self) -> None:
        holidays = [
            Holiday(date="2026-08-13", label="عطلة الصيف"),
            Holiday(date="2026-08-14", label="يوم آخر"),
        ]
        groups = ss._group_consecutive_holidays(holidays)
        self.assertEqual(len(groups), 2)

    def test_single_day_group_has_matching_start_and_end(self) -> None:
        groups = ss._group_consecutive_holidays([Holiday(date="2026-08-13", label="")])
        self.assertEqual(groups, [("2026-08-13", "2026-08-13", "", ["2026-08-13"])])


if __name__ == "__main__":
    unittest.main()
