"""Aggregating recorded meal ratings (تقييم التلاميذ).

Every figure comes from ratings someone actually entered. A dish with no
ratings is reported as having none — never as a zero, which would read as
"everyone hated it".

An average is meaningless without knowing how many opinions it rests on, so
every summary carries its own count and the caller is expected to show it.

Pure logic: no Qt, no database, no Arabic.
"""
import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from core.models import MealFeedback

# A feedback week runs الإثنين → الأحد, matching the meal program's own grid.
_DAYS_IN_WEEK = 7


def week_start_of(value: str) -> str:
    """The MONDAY of the week containing `value`, as ISO text.

    Any day the user picks snaps to one canonical week, so two ratings for the
    same week can never disagree about which week that is. Blank or unparseable
    in → blank out; the value comes from the database and from Qt widgets.
    """
    text = (value or "").strip()
    if not text:
        return ""
    try:
        day = datetime.date.fromisoformat(text)
    except ValueError:
        return ""
    return (day - datetime.timedelta(days=day.weekday())).isoformat()


def week_end_of(week_start: str) -> str:
    """The Sunday closing a week that starts on `week_start`."""
    monday = week_start_of(week_start)
    if not monday:
        return ""
    return (datetime.date.fromisoformat(monday)
            + datetime.timedelta(days=_DAYS_IN_WEEK - 1)).isoformat()

RATING_MIN = 1
RATING_MAX = 5
# Best first — the order the counts are entered and displayed in.
RATING_LEVELS = (5, 4, 3, 2, 1)

# Which MealFeedback field holds the count for each level.
COUNT_FIELDS = {
    5: "count_excellent",
    4: "count_good",
    3: "count_average",
    2: "count_poor",
    1: "count_bad",
}

# Below this many RESPONSES a dish is not offered as "most/least popular":
# one five-star opinion is not evidence that a dish is the school's favourite.
MIN_RATINGS_FOR_RANKING = 3


def normalize_dish(name: str) -> str:
    """The key ratings for the same menu line are grouped under."""
    return " ".join((name or "").split())


def is_valid_rating(value: int) -> bool:
    return RATING_MIN <= value <= RATING_MAX


def response_counts(record: MealFeedback) -> Dict[int, int]:
    """How many pupils gave each level for one served meal.

    A row saved before the counts existed carries a single `rating` instead;
    it is read as exactly ONE response at that level, so old entries still
    count for something without being inflated.
    """
    counts = {
        level: max(0, int(getattr(record, field, 0) or 0))
        for level, field in COUNT_FIELDS.items()
    }
    if any(counts.values()):
        return counts
    if is_valid_rating(record.rating):
        counts[record.rating] = 1
    return counts


def response_total(record: MealFeedback) -> int:
    """The number of pupils who expressed an opinion about this meal."""
    return sum(response_counts(record).values())


def rating_sum(record: MealFeedback) -> int:
    """Sum of every level given, weighted by how many gave it."""
    return sum(level * count for level, count in response_counts(record).items())


def record_average(record: MealFeedback) -> Optional[float]:
    """One meal's own average, or None when nobody rated it."""
    total = response_total(record)
    if not total:
        return None
    return rating_sum(record) / total


@dataclass
class DishSummary:
    """One menu line's standing, with the number of opinions behind it."""
    dish: str
    count: int
    total: int

    @property
    def average(self) -> float:
        return self.total / self.count if self.count else 0.0

    @property
    def is_rankable(self) -> bool:
        """Enough opinions to be worth calling popular or unpopular."""
        return self.count >= MIN_RATINGS_FOR_RANKING


def summarize_by_dish(records: Sequence[MealFeedback]) -> List[DishSummary]:
    """Per-dish averages, best first, then by how many ratings back them up."""
    buckets: Dict[str, DishSummary] = {}
    for record in records:
        responses = response_total(record)
        if not responses:
            continue
        key = normalize_dish(record.dish)
        if not key:
            continue
        summary = buckets.get(key)
        if summary is None:
            buckets[key] = DishSummary(
                dish=key, count=responses, total=rating_sum(record))
        else:
            summary.count += responses
            summary.total += rating_sum(record)
    return sorted(buckets.values(),
                  key=lambda s: (-s.average, -s.count, s.dish))


def overall_average(records: Sequence[MealFeedback]) -> Optional[float]:
    """The mean of every valid rating, or None when there are none.

    None rather than 0.0 on purpose: "no ratings yet" and "everyone rated it
    zero" are different things, and only one of them is possible.
    """
    responses = sum(response_total(r) for r in records)
    if not responses:
        return None
    return sum(rating_sum(r) for r in records) / responses


def average_by_meal_type(
    records: Sequence[MealFeedback],
) -> Dict[str, DishSummary]:
    """Per meal (فطور / غداء / …), so a consistently weak service shows up.

    Only records that NAME a meal contribute: a week rating covers a dish
    across the whole week and cannot be attributed to فطور or غداء, so it is
    skipped here rather than being filed under a meal it never named.
    """
    buckets: Dict[str, DishSummary] = {}
    for record in records:
        meal_type = getattr(record, "meal_type", "")
        if not meal_type:
            continue
        responses = response_total(record)
        if not responses:
            continue
        summary = buckets.get(meal_type)
        if summary is None:
            buckets[meal_type] = DishSummary(
                dish=meal_type, count=responses, total=rating_sum(record))
        else:
            summary.count += responses
            summary.total += rating_sum(record)
    return buckets


def most_popular(records: Sequence[MealFeedback],
                 limit: int = 3) -> List[DishSummary]:
    """The best-rated dishes that have enough ratings to mean anything."""
    return [s for s in summarize_by_dish(records) if s.is_rankable][:limit]


def least_popular(records: Sequence[MealFeedback],
                  limit: int = 3) -> List[DishSummary]:
    rankable = [s for s in summarize_by_dish(records) if s.is_rankable]
    return list(reversed(rankable))[:limit]


# ── Who said what: patterns across cycles and genders ───────────────────────
# Codes, not Arabic — the labels live in ui/. These match
# core.contact_counts' own category names so a Student can be mapped to a
# feedback group with the function the rest of the app already uses.
CYCLE_PRIMARY = "primary"
CYCLE_COLLEGIAL = "collegial"
CYCLE_QUALIFYING = "qualifying"
CYCLES = (CYCLE_PRIMARY, CYCLE_COLLEGIAL, CYCLE_QUALIFYING)

GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDERS = (GENDER_MALE, GENDER_FEMALE)

# A row recorded before the grouping existed. Never assigned to a real group:
# claiming an opinion came from a cycle that may not have given it is exactly
# the invention this feature exists to avoid.
UNSPECIFIED = ""

# A group needs at least this many opinions about a dish before it is compared
# with another group. Two pupils disagreeing is not a pattern.
MIN_RESPONSES_FOR_PATTERN = 10


def _accumulate(bucket: Dict, key, record: MealFeedback) -> None:
    responses = response_total(record)
    if not responses:
        return
    summary = bucket.get(key)
    if summary is None:
        bucket[key] = DishSummary(dish=str(key), count=responses,
                                  total=rating_sum(record))
    else:
        summary.count += responses
        summary.total += rating_sum(record)


def summarize_by_attribute(records: Sequence, attribute: str
                           ) -> Dict[str, DishSummary]:
    """Overall standing per cycle, or per gender.

    Records with no value for that attribute are skipped, not lumped into a
    group they never named.
    """
    buckets: Dict[str, DishSummary] = {}
    for record in records:
        value = (getattr(record, attribute, "") or "").strip()
        if not value:
            continue
        _accumulate(buckets, value, record)
    return buckets


def dish_by_attribute(records: Sequence, attribute: str
                      ) -> Dict[str, Dict[str, DishSummary]]:
    """dish → group → standing, for the per-dish comparison table."""
    table: Dict[str, Dict[str, DishSummary]] = {}
    for record in records:
        value = (getattr(record, attribute, "") or "").strip()
        dish = normalize_dish(record.dish)
        if not value or not dish:
            continue
        _accumulate(table.setdefault(dish, {}), value, record)
    return table


@dataclass
class GroupGap:
    """One dish two groups genuinely disagree about."""
    dish: str
    high_group: str
    high_average: float
    high_count: int
    low_group: str
    low_average: float
    low_count: int

    @property
    def gap(self) -> float:
        return self.high_average - self.low_average


def biggest_gaps(records: Sequence, attribute: str,
                 minimum: int = MIN_RESPONSES_FOR_PATTERN,
                 limit: int = 5) -> List[GroupGap]:
    """Dishes where two groups disagree most, widest gap first.

    Only groups with at least `minimum` opinions about that dish are compared,
    and a dish only one group rated is skipped — it shows no disagreement, it
    shows missing data.
    """
    gaps: List[GroupGap] = []
    for dish, groups in dish_by_attribute(records, attribute).items():
        usable = {name: summary for name, summary in groups.items()
                  if summary.count >= minimum}
        if len(usable) < 2:
            continue
        ordered = sorted(usable.items(), key=lambda item: -item[1].average)
        (high_name, high), (low_name, low) = ordered[0], ordered[-1]
        gaps.append(GroupGap(
            dish=dish,
            high_group=high_name, high_average=high.average, high_count=high.count,
            low_group=low_name, low_average=low.average, low_count=low.count,
        ))
    return sorted(gaps, key=lambda item: -item.gap)[:limit]


def favourite_per_group(records: Sequence, attribute: str,
                        minimum: int = MIN_RESPONSES_FOR_PATTERN
                        ) -> Dict[str, DishSummary]:
    """Each group's best-rated dish — "ابتدائي like X best"."""
    best: Dict[str, DishSummary] = {}
    for dish, groups in dish_by_attribute(records, attribute).items():
        for name, summary in groups.items():
            if summary.count < minimum:
                continue
            summary.dish = dish
            current = best.get(name)
            if current is None or summary.average > current.average:
                best[name] = summary
    return best


def ungrouped_responses(records: Sequence) -> int:
    """How many opinions carry no group — reported so the reader knows what
    the comparison is NOT based on."""
    return sum(response_total(record) for record in records
               if not (getattr(record, "cycle", "") or "").strip()
               and not (getattr(record, "gender", "") or "").strip())
