import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import Holiday
from ui import settings_screen as ss


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
