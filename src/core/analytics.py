"""The numbers behind الإحصائيات's deep sections.

Three questions the app could not answer before:
  · how the months compare (اتجاهات شهرية)
  · when and to whom absence happens (أنماط الغياب)
  · which days are still missing paperwork (اكتمال الوثائق)

Every figure comes from what was recorded. Three rules are enforced here and
each has a test, because breaking any of them would make the page lie:

  1. A month with no recorded days has NO average, not an average of zero.
  2. An absence rate is None when nothing was expected — 40 absences out of an
     unknown roster is not a percentage.
  3. Completeness is measured over the days the school ACTUALLY SERVED, never
     over every date on the calendar. Counting weekends and holidays as
     "missing paperwork" would make the number meaningless.

Pure logic and repository calls: no Qt, no Arabic (labels live in ui/).
"""
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from data.analytics_repo import (
    get_absence_by_cycle, get_absence_by_date, get_attendance_by_date,
    get_document_dates, get_recorded_dates,
)

# The five daily documents, in the order the process produces them. Matches
# core.document_pipeline's DOC_* constants so the two never disagree.
DAILY_DOCUMENTS = ("contact", "absence", "report", "order_letter", "reception")

# Monday-first, matching datetime.date.weekday().
WEEKDAY_COUNT = 7


def parse_iso(value: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


# ── اتجاهات شهرية ───────────────────────────────────────────────────────────

@dataclass
class MonthPoint:
    """One month on the trend."""
    month: str                  # YYYY-MM
    meals: int = 0              # net of absence, EVERY meal type
    cost: float = 0.0           # only the meals that have a price
    days: int = 0               # days that actually have data
    unpriced_meals: int = 0     # meals counted above but not costed

    @property
    def meals_per_day(self) -> Optional[float]:
        """None, not zero, when the month recorded nothing — an average over
        no days is not an average."""
        if not self.days:
            return None
        return self.meals / self.days

    @property
    def cost_is_partial(self) -> bool:
        """True when the month served meals nobody set a price for, so the
        cost shown is a floor rather than the total. Ramadan is the real case:
        the user asked for Ramadan pricing to be left alone (2026-08-25), so
        إفطار/سحور are counted as meals but never costed. The page says so
        rather than printing a total that quietly understates the month."""
        return self.unpriced_meals > 0


def monthly_trend(prices: Dict[str, str], limit: int = 12) -> List[MonthPoint]:
    """The most recent `limit` months, OLDEST FIRST so it reads as a timeline.

    Counts EVERY meal type. get_monthly_summaries — what الملخص الشهري uses —
    hardcodes فطور/غداء/عشاء, so a Ramadan month comes back missing whatever
    was served on its Ramadan days and the trend would show a collapse that
    never happened.
    """
    from data.analytics_repo import (
        get_days_recorded_per_month, get_monthly_meal_totals)

    totals = get_monthly_meal_totals()
    days_per_month = get_days_recorded_per_month()

    points: List[MonthPoint] = []
    for month in sorted(totals)[-limit:]:
        point = MonthPoint(month=month, days=days_per_month.get(month, 0))
        for meal_type, meals in totals[month].items():
            point.meals += meals
            try:
                price = float(prices.get(meal_type, "") or 0)
            except (TypeError, ValueError):
                price = 0.0
            if price > 0:
                point.cost += meals * price
            else:
                point.unpriced_meals += meals
        points.append(point)
    return points


# ── أنماط الغياب ────────────────────────────────────────────────────────────

@dataclass
class AbsencePatterns:
    by_weekday: Dict[int, int] = field(default_factory=dict)
    expected_by_weekday: Dict[int, int] = field(default_factory=dict)
    by_cycle: Dict[str, int] = field(default_factory=dict)
    total_absent: int = 0
    total_expected: int = 0

    @property
    def rate(self) -> Optional[float]:
        """Absent as a share of expected, or None when nothing was expected."""
        if not self.total_expected:
            return None
        return self.total_absent / self.total_expected

    def weekday_rate(self, weekday: int) -> Optional[float]:
        expected = self.expected_by_weekday.get(weekday, 0)
        if not expected:
            return None
        return self.by_weekday.get(weekday, 0) / expected

    @property
    def worst_weekday(self) -> Optional[int]:
        """The weekday with the highest absence RATE, not the highest count —
        a day the school serves more often would otherwise always 'win'."""
        rates = [(day, self.weekday_rate(day)) for day in self.by_weekday]
        usable = [(day, rate) for day, rate in rates if rate is not None]
        if not usable:
            return None
        return max(usable, key=lambda item: item[1])[0]


def absence_patterns(start_date: str, end_date: str) -> AbsencePatterns:
    """When absence happens, and to whom, over a date range."""
    absent_by_date = get_absence_by_date(start_date, end_date)
    expected_by_date = get_attendance_by_date(start_date, end_date)

    patterns = AbsencePatterns(
        by_cycle={cycle: count for cycle, count
                  in get_absence_by_cycle(start_date, end_date).items() if count},
        total_absent=sum(absent_by_date.values()),
        total_expected=sum(expected_by_date.values()),
    )
    for date_str, count in absent_by_date.items():
        day = parse_iso(date_str)
        if day is None:
            continue                # a malformed date is skipped, never guessed
        patterns.by_weekday[day.weekday()] = (
            patterns.by_weekday.get(day.weekday(), 0) + count)
    for date_str, count in expected_by_date.items():
        day = parse_iso(date_str)
        if day is None:
            continue
        patterns.expected_by_weekday[day.weekday()] = (
            patterns.expected_by_weekday.get(day.weekday(), 0) + count)
    return patterns


# ── اكتمال الوثائق ──────────────────────────────────────────────────────────

@dataclass
class DayGap:
    """A day the school served that is still missing paperwork."""
    date: str
    missing: List[str] = field(default_factory=list)


@dataclass
class Completeness:
    served_days: int = 0
    complete_days: int = 0
    per_document: Dict[str, int] = field(default_factory=dict)
    gaps: List[DayGap] = field(default_factory=list)

    @property
    def rate(self) -> Optional[float]:
        if not self.served_days:
            return None
        return self.complete_days / self.served_days

    def document_rate(self, key: str) -> Optional[float]:
        if not self.served_days:
            return None
        return self.per_document.get(key, 0) / self.served_days


def document_completeness(start_date: str, end_date: str) -> Completeness:
    """Which of the five daily documents exist for each day SERVED.

    Days with no contact and no absence sheet are not counted at all: they are
    weekends, holidays and days the refectory did not open, and calling them
    "missing paperwork" would drown the days that really are missing it.
    """
    served = get_recorded_dates(start_date, end_date)
    if not served:
        return Completeness()

    dates = get_document_dates(start_date, end_date)
    letter_ranges = dates.get("order_letter", set())

    completeness = Completeness(served_days=len(served),
                                per_document={key: 0 for key in DAILY_DOCUMENTS})
    for date_str in served:
        missing: List[str] = []
        for key in DAILY_DOCUMENTS:
            if key == "order_letter":
                present = any(start <= date_str <= end
                              for start, end in letter_ranges)
            else:
                present = date_str in dates.get(key, set())
            if present:
                completeness.per_document[key] += 1
            else:
                missing.append(key)
        if missing:
            completeness.gaps.append(DayGap(date=date_str, missing=missing))
        else:
            completeness.complete_days += 1
    return completeness
