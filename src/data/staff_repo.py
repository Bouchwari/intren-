"""طاقم المطبخ CRUD — the catering company's kitchen team.

Kept in its own module rather than added to daily_repo.py: this is a small
standing roster, not one of the per-date daily records, and daily_repo is
already the largest file in this package (same reasoning as infraction_repo).
"""
import sqlite3
from typing import List, Optional

from core.models import StaffMember
from data.database import _connection

_COLUMNS = (
    "full_name", "role", "shift", "phone",
    "health_cert_expiry", "status", "notes",
)


def _row_to_staff(row: sqlite3.Row) -> StaffMember:
    return StaffMember(
        id=row["id"],
        created_at=row["created_at"],
        **{column: row[column] for column in _COLUMNS},
    )


def get_all_staff() -> List[StaffMember]:
    """The whole team, ordered by name so the printed list is stable."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM staff_members ORDER BY full_name COLLATE NOCASE"
        ).fetchall()
    return [_row_to_staff(row) for row in rows]


def get_staff_member(staff_id: int) -> Optional[StaffMember]:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM staff_members WHERE id=?", (staff_id,)
        ).fetchone()
    return _row_to_staff(row) if row else None


def save_staff_member(member: StaffMember) -> int:
    """Insert or update one member. Returns its row id."""
    values = tuple(getattr(member, column) for column in _COLUMNS)
    with _connection() as conn:
        if member.id is None:
            placeholders = ", ".join("?" for _ in _COLUMNS)
            cursor = conn.execute(
                f"INSERT INTO staff_members ({', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders})",
                values,
            )
            return int(cursor.lastrowid)
        assignments = ", ".join(f"{column}=?" for column in _COLUMNS)
        conn.execute(
            f"UPDATE staff_members SET {assignments} WHERE id=?",
            values + (member.id,),
        )
        return int(member.id)


def delete_staff_member(staff_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM staff_members WHERE id=?", (staff_id,))
