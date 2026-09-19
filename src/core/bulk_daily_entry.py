"""Validation and persistence service for multi-day real-number entry."""
from __future__ import annotations

from datetime import date
from typing import Sequence

from config.settings import RAMADAN_MEALS, REGULAR_MEALS
from core.models import BulkDailyEntry


_ALLOWED_MEALS = set(REGULAR_MEALS) | set(RAMADAN_MEALS)


def validate_bulk_daily_entries(entries: Sequence[BulkDailyEntry]) -> None:
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        try:
            date.fromisoformat(entry.date)
        except ValueError as exc:
            raise ValueError(f"invalid date: {entry.date}") from exc
        if entry.meal_type not in _ALLOWED_MEALS:
            raise ValueError(f"invalid meal type: {entry.meal_type}")
        if entry.attendance < 0 or entry.absence < 0:
            raise ValueError("daily values cannot be negative")
        if entry.absence > entry.attendance:
            raise ValueError("absence cannot exceed attendance")
        key = (entry.date, entry.meal_type)
        if key in seen:
            raise ValueError(f"duplicate daily entry: {entry.date}/{entry.meal_type}")
        seen.add(key)


def save_bulk_daily_entries(entries: Sequence[BulkDailyEntry]) -> None:
    """Validate, then atomically save all supplied meals."""
    validated = list(entries)
    validate_bulk_daily_entries(validated)
    if not validated:
        return
    from data.daily_repo import upsert_bulk_daily_entries
    upsert_bulk_daily_entries(validated)
