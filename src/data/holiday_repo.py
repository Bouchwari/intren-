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
