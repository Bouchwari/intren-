"""
src/core/attendance_estimate.py
Estimates attendance for a meal on days nobody physically counts students.
Deterministic: same date, meal and history always produce the same numbers.
No PySide6, no Arabic strings — ui/daily_contact_screen.py turns `reason`
and `confidence` into the Arabic sentence shown next to the generated counts.
"""
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Literal

from core.models import DailyAbsence, DailyContact

MIN_RECORDS_FOR_ESTIMATE = 3
MAX_RECORDS_USED = 6

Confidence = Literal["low", "medium", "high"]
EstimateReason = Literal["insufficient_history", "estimated"]

# category key -> attribute reader, e.g. "primary_full" -> record.primary_granted.
# collegial_granted / qualifying_granted already merge the retired *_paying
# columns (see data/database.py:_row_to_contact), so no extra merging here.
_CATEGORY_READERS = {
    "primary_full":     lambda r: r.primary_granted,
    "primary_lunch":    lambda r: r.primary_complement,
    "collegial_full":   lambda r: r.collegial_granted,
    "collegial_lunch":  lambda r: r.collegial_complement,
    "qualifying_full":  lambda r: r.qualifying_granted,
    "qualifying_lunch": lambda r: r.qualifying_complement,
    "monitors_full":    lambda r: r.monitors,
    "monitors_lunch":   lambda r: r.monitors_complement,
}


@dataclass
class EstimateResult:
    """Result of estimating today's attendance from past contact sheets."""
    counts: dict[str, int]
    confidence: Confidence
    records_used: int
    reason: EstimateReason


def estimate_attendance(
    active_roster: dict[str, int],
    history: list[DailyContact],
    target_date: date,
    meal: str,
) -> EstimateResult:
    """Estimate today's attendance per category from past contact sheets.

    Only contact sheets for the same weekday and the same meal are used
    (Monday attendance is not Friday attendance), most recent first, capped
    at MAX_RECORDS_USED. Historical roster size isn't tracked yet (see
    matama skill, roster_state note), so `active_roster` is used as the
    denominator for every historical record too.
    """
    matching = _matching_records(history, target_date, meal)

    if len(matching) < MIN_RECORDS_FOR_ESTIMATE:
        return EstimateResult(
            counts=dict(active_roster),
            confidence="low",
            records_used=len(matching),
            reason="insufficient_history",
        )

    counts: dict[str, int] = {}
    for category, roster_count in active_roster.items():
        rate = _median_rate(matching, category, roster_count)
        estimated = round(rate * roster_count)
        counts[category] = max(0, min(roster_count, estimated))

    confidence: Confidence = "high" if len(matching) >= MAX_RECORDS_USED else "medium"
    return EstimateResult(
        counts=counts,
        confidence=confidence,
        records_used=len(matching),
        reason="estimated",
    )


def estimate_absence(
    active_roster: dict[str, int],
    history: list[DailyAbsence],
    target_date: date,
    meal: str,
) -> EstimateResult:
    """Estimate today's likely ABSENCE count per category, the same way
    estimate_attendance() estimates attendance — DailyAbsence shares the
    exact same category shape (primary/collegial/qualifying/monitors ×
    full/lunch), so the same median-historical-rate logic applies directly:
    "usually ~3 من 45 قسم إعدادي غائبون على الغذاء يوم الاثنين", not a
    random number."""
    result = estimate_attendance(active_roster, history, target_date, meal)  # type: ignore[arg-type]
    if result.reason == "insufficient_history":
        # estimate_attendance falls back to "assume the whole roster came",
        # which is the right default for ATTENDANCE and exactly backwards
        # here — it would declare every single student absent, and every
        # document downstream would then report that nobody ate. Fall back to
        # zero absences instead, which is what the absence screen's own
        # "تم عرض 0 غياب" note has always promised the user.
        return EstimateResult(
            counts={category: 0 for category in active_roster},
            confidence=result.confidence,
            records_used=result.records_used,
            reason=result.reason,
        )
    return result


def _matching_records(
    history: list[DailyContact], target_date: date, meal: str
) -> list[DailyContact]:
    same = [
        record for record in history
        if record.meal_type == meal
        and date.fromisoformat(record.date).weekday() == target_date.weekday()
    ]
    same.sort(key=lambda record: record.date, reverse=True)
    return same[:MAX_RECORDS_USED]


def _median_rate(records: list[DailyContact], category: str, roster_count: int) -> float:
    if roster_count <= 0:
        return 0.0
    reader = _CATEGORY_READERS.get(category)
    if reader is None:
        return 0.0
    rates = [reader(record) / roster_count for record in records]
    return median(rates)
