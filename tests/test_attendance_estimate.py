import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.attendance_estimate import estimate_absence, estimate_attendance
from core.models import DailyContact

MEAL = "ghada"
TARGET_DATE = date(2026, 7, 30)  # a Thursday


def _record(days_back: int, primary_full: int, primary_lunch: int = 0) -> DailyContact:
    """A contact sheet `days_back * 7` days before TARGET_DATE, same weekday."""
    record_date = TARGET_DATE - timedelta(weeks=days_back)
    return DailyContact(
        date=record_date.isoformat(),
        meal_type=MEAL,
        primary_granted=primary_full,
        primary_complement=primary_lunch,
    )


class AttendanceEstimateTests(unittest.TestCase):
    def test_no_history_returns_full_roster_low_confidence(self) -> None:
        roster = {"primary_full": 40, "primary_lunch": 10}
        result = estimate_attendance(roster, [], TARGET_DATE, MEAL)

        self.assertEqual(result.counts, roster)
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.records_used, 0)
        self.assertEqual(result.reason, "insufficient_history")

    def test_one_record_is_not_enough(self) -> None:
        roster = {"primary_full": 40, "primary_lunch": 10}
        history = [_record(1, 36)]
        result = estimate_attendance(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(result.counts, roster)
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.records_used, 1)
        self.assertEqual(result.reason, "insufficient_history")

    def test_three_records_produce_an_estimate(self) -> None:
        roster = {"primary_full": 40}
        # rates: 36/40=.90, 32/40=.80, 34/40=.85 -> median .85 -> 34
        history = [_record(1, 36), _record(2, 32), _record(3, 34)]
        result = estimate_attendance(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(result.counts, {"primary_full": 34})
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.records_used, 3)
        self.assertEqual(result.reason, "estimated")

    def test_ten_records_use_only_the_most_recent_six(self) -> None:
        roster = {"primary_full": 40}
        # 6 most recent (weeks 1-6): rate .90 each -> median .90 -> 36
        # older records (weeks 7-10) would pull the median down if wrongly included
        history = [_record(w, 36) for w in range(1, 7)] + [
            _record(w, 10) for w in range(7, 11)
        ]
        result = estimate_attendance(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(result.counts, {"primary_full": 36})
        self.assertEqual(result.records_used, 6)
        self.assertEqual(result.confidence, "high")

    def test_one_wild_outlier_does_not_skew_the_median(self) -> None:
        roster = {"primary_full": 40}
        # five normal days at 36, one freak day at 2 -> median stays 36
        history = [_record(w, 36) for w in range(1, 6)] + [_record(6, 2)]
        result = estimate_attendance(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(result.counts, {"primary_full": 36})

    def test_empty_roster_never_divides_by_zero(self) -> None:
        roster = {"primary_full": 0}
        history = [_record(w, 0) for w in range(1, 4)]
        result = estimate_attendance(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(result.counts, {"primary_full": 0})
        self.assertEqual(result.reason, "estimated")

    def test_different_weekday_or_meal_is_excluded(self) -> None:
        roster = {"primary_full": 40}
        wrong_meal = DailyContact(
            date=(TARGET_DATE - timedelta(weeks=1)).isoformat(),
            meal_type="ftour",
            primary_granted=36,
        )
        wrong_weekday = DailyContact(
            date=(TARGET_DATE - timedelta(days=1)).isoformat(),
            meal_type=MEAL,
            primary_granted=36,
        )
        result = estimate_attendance(
            roster, [wrong_meal, wrong_weekday], TARGET_DATE, MEAL
        )

        self.assertEqual(result.records_used, 0)
        self.assertEqual(result.confidence, "low")

    def test_deterministic_across_repeated_calls(self) -> None:
        roster = {"primary_full": 40, "primary_lunch": 12}
        history = [_record(1, 36, 11), _record(2, 32, 9), _record(3, 34, 10)]

        first = estimate_attendance(roster, history, TARGET_DATE, MEAL)
        second = estimate_attendance(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()


class AbsenceEstimateFallbackTests(unittest.TestCase):
    """estimate_absence delegates to estimate_attendance, whose no-history
    fallback is "assume the whole roster came". That is right for attendance
    and exactly backwards for absence: it declared EVERY student absent, so
    التقرير اليومي then computed present = expected - absent = 0 and every
    document downstream said nobody ate. Batch generation saved that silently
    across a whole date range."""

    def test_no_history_means_zero_absences_not_the_whole_roster(self) -> None:
        roster = {"primary_full": 40, "primary_lunch": 10}
        result = estimate_absence(roster, [], TARGET_DATE, MEAL)

        self.assertEqual(result.counts, {"primary_full": 0, "primary_lunch": 0})
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.reason, "insufficient_history")

    def test_batch_fallback_is_between_zero_and_five(self) -> None:
        roster = {"collegial_full": 40, "qualifying_full": 30}
        totals = []
        for day in range(1, 29):
            result = estimate_absence(
                roster,
                [],
                date(2026, 5, day),
                MEAL,
                fallback_random_max=5,
            )
            totals.append(sum(result.counts.values()))

        self.assertTrue(all(0 <= total <= 5 for total in totals))
        self.assertTrue(any(total > 0 for total in totals))
        self.assertGreater(len(set(totals)), 1)

    def test_batch_fallback_never_exceeds_a_small_roster(self) -> None:
        roster = {"collegial_full": 1, "qualifying_full": 1}
        result = estimate_absence(
            roster,
            [],
            TARGET_DATE,
            MEAL,
            fallback_random_max=5,
        )
        self.assertLessEqual(sum(result.counts.values()), 2)
        for category, count in result.counts.items():
            self.assertLessEqual(count, roster[category])

    def test_a_real_estimate_is_still_produced_once_history_exists(self) -> None:
        roster = {"primary_full": 40}
        history = [_record(1, 4), _record(2, 2), _record(3, 3)]
        result = estimate_absence(roster, history, TARGET_DATE, MEAL)

        self.assertEqual(result.counts["primary_full"], 3)   # median of 4/2/3
        self.assertEqual(result.reason, "estimated")
