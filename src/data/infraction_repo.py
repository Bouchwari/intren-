"""محضر المخالفة CRUD — the PV raised against the catering company when a
contractual breach is observed.

Kept in its own module rather than added to daily_repo.py: this is an
as-needed document, not one of the per-date daily records, and daily_repo
is already the largest file in this package.
"""
import sqlite3
from typing import List, Optional

from core.models import InfractionRecord
from data.database import _connection

_COLUMNS = (
    "date", "document_number", "year", "meal_type", "place",
    "infraction_type", "description", "reported_by", "written_date",
)


def _row_to_infraction(row: sqlite3.Row) -> InfractionRecord:
    return InfractionRecord(
        id=row["id"],
        created_at=row["created_at"],
        **{column: row[column] for column in _COLUMNS},
    )


def get_all_infractions() -> List[InfractionRecord]:
    """Every recorded PV, newest first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM infraction_records ORDER BY year DESC, document_number DESC"
        ).fetchall()
    return [_row_to_infraction(row) for row in rows]


def get_infraction(record_id: int) -> Optional[InfractionRecord]:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM infraction_records WHERE id=?", (record_id,)
        ).fetchone()
    return _row_to_infraction(row) if row else None


def get_next_infraction_number(year: int) -> int:
    """The next free sequence number within `year`.

    Numbering restarts each year, matching how the reference is printed on
    the document ("محضر مخالفة رقم 2026/01"). Returned as a suggestion the
    user can still edit before saving, like the order letter's own number.
    """
    with _connection() as conn:
        row = conn.execute(
            "SELECT MAX(document_number) AS last FROM infraction_records WHERE year=?",
            (year,),
        ).fetchone()
    last = row["last"] if row else None
    return 1 if last is None else int(last) + 1


def save_infraction(record: InfractionRecord) -> int:
    """Insert or update one PV. Returns its row id.

    (year, document_number) is UNIQUE in the schema, so two records can
    never end up printing the same reference on a signed document — a
    clash raises sqlite3.IntegrityError for the caller to report.
    """
    placeholders = ", ".join("?" for _ in _COLUMNS)
    values = tuple(getattr(record, column) for column in _COLUMNS)
    with _connection() as conn:
        if record.id is None:
            cursor = conn.execute(
                f"INSERT INTO infraction_records ({', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders})",
                values,
            )
            return int(cursor.lastrowid)
        assignments = ", ".join(f"{column}=?" for column in _COLUMNS)
        conn.execute(
            f"UPDATE infraction_records SET {assignments} WHERE id=?",
            values + (record.id,),
        )
        return int(record.id)


def delete_infraction(record_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM infraction_records WHERE id=?", (record_id,))
