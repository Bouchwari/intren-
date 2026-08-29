"""Holiday/day-off CRUD — dates the مسير already knows the cafeteria is
closed, entered in advance from Settings. Kept separate from daily_repo.py
since holidays aren't per-meal records like contact/absence sheets."""
from typing import List

from core.models import Holiday
from data.database import _connection


def get_all_holidays() -> List[Holiday]:
    """Every saved holiday, earliest date first."""
    with _connection() as conn:
        rows = conn.execute("SELECT date, label FROM holidays ORDER BY date").fetchall()
    return [Holiday(date=row["date"], label=row["label"]) for row in rows]


def add_holiday(holiday: Holiday) -> None:
    """Insert a holiday, or replace its label if the date is already saved."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO holidays (date, label) VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET label=excluded.label
        """, (holiday.date, holiday.label))


def delete_holiday(date: str) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM holidays WHERE date = ?", (date,))


def is_holiday(date: str) -> bool:
    with _connection() as conn:
        row = conn.execute("SELECT 1 FROM holidays WHERE date = ?", (date,)).fetchone()
    return row is not None


# ── Ramadan per-day overrides ────────────────────────────────────────────────
# Ramadan begins on a moon sighting, so the announced dates routinely move a
# day either way. These rows let the user correct a single day without
# shifting the whole period saved in Settings.

def get_ramadan_overrides() -> dict:
    """Return {ISO date: bool} — True forces a day into Ramadan, False out."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT date, is_ramadan FROM ramadan_day_overrides"
        ).fetchall()
    return {r["date"]: bool(r["is_ramadan"]) for r in rows}


def set_ramadan_override(date: str, is_ramadan: bool) -> None:
    """Force one day on or off, overriding the configured period."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO ramadan_day_overrides (date, is_ramadan) VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET is_ramadan = excluded.is_ramadan
        """, (date, int(is_ramadan)))


def clear_ramadan_override(date: str) -> None:
    """Drop a day's override so it follows the configured period again."""
    with _connection() as conn:
        conn.execute("DELETE FROM ramadan_day_overrides WHERE date=?", (date,))
