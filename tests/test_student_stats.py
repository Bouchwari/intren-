"""Counting the roster for the feedback report's context section.

Nothing is estimated: a pupil with no birth date is counted as unknown rather
than given a plausible age, and a blank gender is reported as blank.
"""
import datetime
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR))

from core.models import Student
from core.student_stats import (
    age_on, sorted_counts, summarize_students,
)

TODAY = datetime.date(2026, 8, 29)


def _student(**kwargs) -> Student:
    kwargs.setdefault("full_name", "تلميذ")
    return Student(**kwargs)


class AgeTests(unittest.TestCase):
    def test_age_is_whole_years_and_respects_the_birthday(self) -> None:
        self.assertEqual(age_on("2010-08-29", TODAY), 16)   # birthday today
        self.assertEqual(age_on("2010-08-30", TODAY), 15)   # tomorrow
        self.assertEqual(age_on("2010-08-28", TODAY), 16)

    def test_missing_and_unparseable_dates_give_none(self) -> None:
        for value in ("", "   ", "junk", "2026-13-45"):
            self.assertIsNone(age_on(value, TODAY))

    def test_an_implausible_age_is_refused_rather_than_charted(self) -> None:
        """A typo'd year would otherwise stretch the age chart to nonsense."""
        self.assertIsNone(age_on("1900-01-01", TODAY))     # age 126
        self.assertIsNone(age_on("2025-01-01", TODAY))     # age 1

    def test_an_adult_monitor_still_gets_an_age(self) -> None:
        """معلمو الداخلية are on the same roster and are adults — capping at a
        pupil's age would silently drop real staff from the chart."""
        self.assertEqual(age_on("1985-01-01", TODAY), 41)


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.students = [
            _student(gender="male", cycle="إعدادي", student_class="1 إعدادي",
                     section="internat", grant_type="full",
                     birth_date="2012-01-01"),
            _student(gender="female", cycle="إعدادي", student_class="1 إعدادي",
                     section="cantine", grant_type="half",
                     birth_date="2012-06-01"),
            _student(gender="female", cycle="تأهيلي", student_class="جذع",
                     birth_date=""),
            _student(gender="", cycle="", student_class="",
                     is_monitor=True, birth_date="1995-01-01"),
        ]
        self.stats = summarize_students(self.students, TODAY)

    def test_totals_and_monitors(self) -> None:
        self.assertEqual(self.stats.total, 4)
        self.assertEqual(self.stats.monitors, 1)

    def test_a_blank_gender_or_cycle_is_reported_not_guessed(self) -> None:
        self.assertEqual(self.stats.by_gender, {"male": 1, "female": 2, "": 1})
        self.assertEqual(self.stats.by_cycle["إعدادي"], 2)
        self.assertIn("", self.stats.by_cycle)

    def test_a_pupil_with_no_birth_date_is_counted_as_unknown(self) -> None:
        self.assertEqual(self.stats.unknown_age, 1)        # the blank one
        # the two pupils plus the adult monitor
        self.assertEqual(sum(self.stats.by_age.values()), 3)

    def test_the_average_age_uses_only_the_known_ones(self) -> None:
        self.assertIsNotNone(self.stats.average_age)
        self.assertAlmostEqual(
            self.stats.average_age,
            sum(age * n for age, n in self.stats.by_age.items())
            / sum(self.stats.by_age.values()))

    def test_a_roster_with_no_birth_dates_reports_no_ages(self) -> None:
        """The report says the dates are missing instead of printing an empty
        chart."""
        stats = summarize_students([_student(birth_date="")], TODAY)
        self.assertFalse(stats.has_ages)
        self.assertIsNone(stats.average_age)
        self.assertEqual(stats.unknown_age, 1)

    def test_an_empty_roster_is_safe(self) -> None:
        stats = summarize_students([], TODAY)
        self.assertEqual(stats.total, 0)
        self.assertFalse(stats.has_ages)

    def test_sorted_counts_is_biggest_first_and_can_be_limited(self) -> None:
        ordered = sorted_counts(self.stats.by_gender)
        self.assertEqual(ordered[0][0], "female")
        self.assertEqual(len(sorted_counts(self.stats.by_gender, limit=2)), 2)


if __name__ == "__main__":
    unittest.main()
