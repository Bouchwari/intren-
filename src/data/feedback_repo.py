"""تقييم التلاميذ CRUD — recorded opinions about the meals served."""
import sqlite3
from typing import List, Optional

from core.models import MealFeedback, WeekFeedback
from data.database import _connection

_COLUMNS = (
    "date", "meal_type", "dish",
    "count_excellent", "count_good", "count_average", "count_poor", "count_bad",
    "rating", "note", "recorded_by",
)


def _row_to_feedback(row: sqlite3.Row) -> MealFeedback:
    return MealFeedback(
        id=row["id"],
        created_at=row["created_at"],
        **{column: row[column] for column in _COLUMNS},
    )


def get_all_feedback(limit: int = 500) -> List[MealFeedback]:
    """Newest first — the recent meals are the ones being discussed."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meal_feedback ORDER BY date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_feedback(row) for row in rows]


def get_feedback_for_month(month: str) -> List[MealFeedback]:
    """Every rating in a "YYYY-MM" month."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meal_feedback WHERE strftime('%Y-%m', date)=? "
            "ORDER BY date DESC, id DESC",
            (month,),
        ).fetchall()
    return [_row_to_feedback(row) for row in rows]


def get_feedback_for(date: str, meal_type: str, dish: str) -> Optional[MealFeedback]:
    """The existing row for one served meal, if there is one.

    Used by the Excel import so re-importing the same sheet UPDATES the meal
    rather than adding a second row for it and doubling the response counts.
    """
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM meal_feedback WHERE date=? AND meal_type=? AND dish=?",
            (date, meal_type, dish),
        ).fetchone()
    return _row_to_feedback(row) if row else None


def save_feedback(record: MealFeedback) -> int:
    """Insert or update one rating. Returns its row id."""
    values = tuple(getattr(record, column) for column in _COLUMNS)
    with _connection() as conn:
        if record.id is None:
            placeholders = ", ".join("?" for _ in _COLUMNS)
            cursor = conn.execute(
                f"INSERT INTO meal_feedback ({', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders})",
                values,
            )
            return int(cursor.lastrowid)
        assignments = ", ".join(f"{column}=?" for column in _COLUMNS)
        conn.execute(
            f"UPDATE meal_feedback SET {assignments} WHERE id=?",
            values + (record.id,),
        )
        return int(record.id)


def delete_feedback(record_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM meal_feedback WHERE id=?", (record_id,))


# ── Week menu feedback (تقييم قائمة الأسبوع) ────────────────────────────────

_WEEK_COLUMNS = (
    "week_start", "dish", "cycle", "gender",
    "count_excellent", "count_good", "count_average", "count_poor", "count_bad",
    "note", "recorded_by",
)


def _row_to_week_feedback(row: sqlite3.Row) -> WeekFeedback:
    return WeekFeedback(
        id=row["id"], created_at=row["created_at"],
        **{column: row[column] for column in _WEEK_COLUMNS},
    )


def get_week_feedback(week_start: str) -> List[WeekFeedback]:
    """Every dish rated for one week."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM week_feedback WHERE week_start=? "
            "ORDER BY dish, cycle, gender",
            (week_start,),
        ).fetchall()
    return [_row_to_week_feedback(row) for row in rows]


def get_all_week_feedback(limit: int = 500) -> List[WeekFeedback]:
    """Newest weeks first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM week_feedback "
            "ORDER BY week_start DESC, dish, cycle, gender LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_week_feedback(row) for row in rows]


def save_week_feedback(record: WeekFeedback) -> int:
    """Insert or update one dish's rating for one week.

    Matched on (week, dish, cycle, gender) so re-entering one group's numbers
    UPDATES them rather than adding a second row and doubling the counts.
    """
    values = tuple(getattr(record, column) for column in _WEEK_COLUMNS)
    assignments = ", ".join(
        f"{column}=excluded.{column}" for column in _WEEK_COLUMNS[4:])
    with _connection() as conn:
        conn.execute(f"""
            INSERT INTO week_feedback ({', '.join(_WEEK_COLUMNS)})
            VALUES ({', '.join('?' for _ in _WEEK_COLUMNS)})
            ON CONFLICT(week_start, dish, cycle, gender)
            DO UPDATE SET {assignments}
        """, values)
        row = conn.execute(
            "SELECT id FROM week_feedback "
            "WHERE week_start=? AND dish=? AND cycle=? AND gender=?",
            (record.week_start, record.dish, record.cycle, record.gender),
        ).fetchone()
        return int(row["id"])


def delete_week_feedback(record_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM week_feedback WHERE id=?", (record_id,))
