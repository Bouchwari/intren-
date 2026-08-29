"""
src/core/ramadan.py
Decides whether a given date is a Ramadan day, and which meals that day
serves. Pure logic — no database, no PySide6 — so every screen and every
document can ask the same question and get the same answer.

How a day is classified (user's own design, 2026-08-25):
  1. A per-day override wins outright, if one exists. Ramadan begins on a
     moon sighting, so the announced dates routinely shift by a day and the
     user must be able to correct a single day without moving the whole
     period.
  2. Otherwise the day is a Ramadan day when it falls inside the Ramadan
     period saved in Settings (inclusive of both endpoints).
  3. With no period saved, nothing is a Ramadan day — the app behaves
     exactly as it did before this feature existed.

A Ramadan day serves إفطار + سحور, which REPLACE the three normal meals
rather than adding to them (config.settings.RAMADAN_MEALS).
"""
import datetime
from typing import Dict, List, Optional

from config.settings import RAMADAN_MEALS, REGULAR_MEALS
from core.models import SchoolSettings


def parse_iso_date(value: str) -> Optional[datetime.date]:
    """Return a date from an ISO 'YYYY-MM-DD' string, or None if it is blank
    or malformed — settings hold user-typed text, so both are expected."""
    if not value or not value.strip():
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None


def is_ramadan_day(
    date_str: str,
    settings: Optional[SchoolSettings],
    overrides: Optional[Dict[str, bool]] = None,
) -> bool:
    """True when `date_str` (ISO 'YYYY-MM-DD') is a Ramadan day."""
    if overrides and date_str in overrides:
        return bool(overrides[date_str])

    day = parse_iso_date(date_str)
    if day is None or settings is None:
        return False

    start = parse_iso_date(getattr(settings, "ramadan_start", ""))
    end = parse_iso_date(getattr(settings, "ramadan_end", ""))
    if start is None or end is None:
        return False
    if end < start:
        # A reversed range is a typo, not an instruction to invert the year.
        start, end = end, start
    return start <= day <= end


def meals_for_date(
    date_str: str,
    settings: Optional[SchoolSettings],
    overrides: Optional[Dict[str, bool]] = None,
) -> List[str]:
    """The meal types served on that date — Ramadan's two, or the normal
    three. Callers should use this instead of hardcoding a meal list."""
    if is_ramadan_day(date_str, settings, overrides):
        return list(RAMADAN_MEALS)
    return list(REGULAR_MEALS)


def ramadan_days_in_month(
    month: str,
    settings: Optional[SchoolSettings],
    overrides: Optional[Dict[str, bool]] = None,
) -> List[str]:
    """Every Ramadan date inside a 'YYYY-MM' month, ISO-formatted. Used by
    the monthly and quarterly documents to decide whether a month needs its
    Ramadan columns at all."""
    import calendar

    parsed = parse_iso_date(f"{month}-01")
    if parsed is None:
        return []
    days_in_month = calendar.monthrange(parsed.year, parsed.month)[1]
    return [
        date_str
        for day in range(1, days_in_month + 1)
        for date_str in (f"{month}-{day:02d}",)
        if is_ramadan_day(date_str, settings, overrides)
    ]


def month_has_ramadan(
    month: str,
    settings: Optional[SchoolSettings],
    overrides: Optional[Dict[str, bool]] = None,
) -> bool:
    """True when any day of a 'YYYY-MM' month is a Ramadan day."""
    return bool(ramadan_days_in_month(month, settings, overrides))
