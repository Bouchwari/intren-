"""Per-day records — contact sheet, absence sheet, daily report, order
letters, violations — moved out of database.py (Stage 1.5, Prompt 6)."""
import sqlite3
from typing import List, Optional

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import (
    DailyAbsence, DailyContact, DailyContactDocumentLog,
    OrderItem, OrderLetter, Violation,
)
from data.database import _connection


# ── Daily contact CRUD ────────────────────────────────────────────────────────

def _row_to_contact(r: sqlite3.Row) -> DailyContact:
    return DailyContact(
        id=r["id"],
        date=r["date"],
        meal_type=r["meal_type"],
        primary_granted=r["primary_granted"],
        primary_complement=r["primary_complement"],
        collegial_granted=r["collegial_granted"] + r["collegial_paying"],
        collegial_paying=0,
        collegial_complement=r["collegial_complement"],
        qualifying_granted=r["qualifying_granted"] + r["qualifying_paying"],
        qualifying_paying=0,
        qualifying_complement=r["qualifying_complement"],
        monitors=r["monitors"],
        monitors_complement=r["monitors_complement"],
    )


def get_day_contacts(date: str) -> List[DailyContact]:
    """Return all meal rows for a given date (up to 3 rows)."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_contact WHERE date=? ORDER BY meal_type",
            (date,),
        ).fetchall()
    return [_row_to_contact(r) for r in rows]


def get_contact(date: str, meal_type: str) -> Optional[DailyContact]:
    """Return one meal row for a given date, or None."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM daily_contact WHERE date=? AND meal_type=?",
            (date, meal_type),
        ).fetchone()
    return _row_to_contact(row) if row else None


def save_daily_contact(c: DailyContact) -> None:
    """Upsert one meal row (enforces UNIQUE on date + meal_type)."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO daily_contact
                (date, meal_type,
                 primary_granted, primary_complement,
                 collegial_granted, collegial_paying, collegial_complement,
                 qualifying_granted, qualifying_paying, qualifying_complement,
                 monitors, monitors_complement)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date, meal_type) DO UPDATE SET
                primary_granted      = excluded.primary_granted,
                primary_complement   = excluded.primary_complement,
                collegial_granted    = excluded.collegial_granted,
                collegial_paying     = excluded.collegial_paying,
                collegial_complement = excluded.collegial_complement,
                qualifying_granted   = excluded.qualifying_granted,
                qualifying_paying    = excluded.qualifying_paying,
                qualifying_complement= excluded.qualifying_complement,
                monitors             = excluded.monitors,
                monitors_complement  = excluded.monitors_complement
        """, (
            c.date, c.meal_type,
            c.primary_granted, c.primary_complement,
            c.collegial_granted + c.collegial_paying, 0, c.collegial_complement,
            c.qualifying_granted + c.qualifying_paying, 0, c.qualifying_complement,
            c.monitors, c.monitors_complement,
        ))


def get_recent_contacts(limit: int = 60) -> List[DailyContact]:
    """Return the most recent contact rows, newest first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_contact ORDER BY date DESC, meal_type LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_contact(r) for r in rows]


# ── Daily contact document log ────────────────────────────────────────────────

def _row_to_contact_document_log(r: sqlite3.Row) -> DailyContactDocumentLog:
    return DailyContactDocumentLog(
        id=r["id"],
        date=r["date"],
        document_number=r["document_number"],
        action=r["action"],
        ftour_total=r["ftour_total"],
        ghada_total=r["ghada_total"],
        asha_total=r["asha_total"],
        grand_total=r["grand_total"],
        file_path=r["file_path"] or "",
        created_at=r["created_at"] or "",
    )


def get_next_daily_contact_document_number(fallback: int = 1) -> int:
    """Return the next official daily-contact document number."""
    fallback = max(1, int(fallback or 1))
    try:
        with _connection() as conn:
            row = conn.execute(
                "SELECT MAX(document_number) AS last_number FROM daily_contact_documents"
            ).fetchone()
    except sqlite3.OperationalError:
        return fallback

    last_number = row["last_number"] if row else None
    if last_number is None:
        return fallback
    return max(fallback, int(last_number) + 1)


def get_daily_contact_document_number_draft(date: str) -> Optional[int]:
    """Return the current editable daily-contact document number, if one exists."""
    key = "daily_contact_document_number"
    try:
        with _connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_preferences WHERE key=?",
                (key,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if not row or not row["value"]:
        return None
    try:
        value = int(row["value"])
    except ValueError:
        return None
    return value if value > 0 else None


def save_daily_contact_document_number_draft(date: str, document_number: int) -> None:
    """Persist the current editable daily-contact document number."""
    key = "daily_contact_document_number"
    value = str(max(1, int(document_number or 1)))
    with _connection() as conn:
        conn.execute("""
            INSERT INTO app_preferences (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))


def record_daily_contact_document(
    date: str,
    document_number: int,
    action: str,
    contacts: List[DailyContact],
    file_path: str = "",
) -> int:
    """Record a save/print event for the daily contact document history."""
    totals = {
        MEAL_FTOUR: 0,
        MEAL_GHADA: 0,
        MEAL_ASHA: 0,
    }
    for contact in contacts:
        if contact.meal_type in totals:
            totals[contact.meal_type] = contact.grand_total

    grand_total = totals[MEAL_FTOUR] + totals[MEAL_GHADA] + totals[MEAL_ASHA]
    with _connection() as conn:
        cur = conn.execute("""
            INSERT INTO daily_contact_documents
                (date, document_number, action, ftour_total, ghada_total, asha_total, grand_total, file_path)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            date,
            max(1, int(document_number or 1)),
            action,
            totals[MEAL_FTOUR],
            totals[MEAL_GHADA],
            totals[MEAL_ASHA],
            grand_total,
            file_path,
        ))
    return int(cur.lastrowid)  # type: ignore[arg-type]


def get_recent_daily_contact_documents(limit: int = 40) -> List[DailyContactDocumentLog]:
    """Return recent saved/printed daily-contact document events."""
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_contact_documents ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [_row_to_contact_document_log(r) for r in rows]


# ── Daily absence CRUD ────────────────────────────────────────────────────────

def _row_to_absence(r: sqlite3.Row) -> DailyAbsence:
    return DailyAbsence(
        id=r["id"],
        date=r["date"],
        meal_type=r["meal_type"],
        collegial_granted=r["collegial_granted"],
        collegial_paying=r["collegial_paying"],
        collegial_complement=r["collegial_complement"],
        qualifying_granted=r["qualifying_granted"],
        qualifying_paying=r["qualifying_paying"],
        qualifying_complement=r["qualifying_complement"],
        monitors=r["monitors"],
    )


def get_day_absences(date: str) -> List[DailyAbsence]:
    """Return all meal rows for a given date (up to 3 rows)."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_absence WHERE date=? ORDER BY meal_type",
            (date,),
        ).fetchall()
    return [_row_to_absence(r) for r in rows]


def save_daily_absence(a: DailyAbsence) -> None:
    """Upsert one absence row (enforces UNIQUE on date + meal_type)."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO daily_absence
                (date, meal_type,
                 collegial_granted, collegial_paying, collegial_complement,
                 qualifying_granted, qualifying_paying, qualifying_complement,
                 monitors)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date, meal_type) DO UPDATE SET
                collegial_granted    = excluded.collegial_granted,
                collegial_paying     = excluded.collegial_paying,
                collegial_complement = excluded.collegial_complement,
                qualifying_granted   = excluded.qualifying_granted,
                qualifying_paying    = excluded.qualifying_paying,
                qualifying_complement= excluded.qualifying_complement,
                monitors             = excluded.monitors
        """, (
            a.date, a.meal_type,
            a.collegial_granted, a.collegial_paying, a.collegial_complement,
            a.qualifying_granted, a.qualifying_paying, a.qualifying_complement,
            a.monitors,
        ))


def get_recent_absences(limit: int = 60) -> List[DailyAbsence]:
    """Return the most recent absence rows, newest first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_absence ORDER BY date DESC, meal_type LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_absence(r) for r in rows]


# ── Daily report CRUD ─────────────────────────────────────────────────────────

def get_report_notes(date: str) -> str:
    """Return the saved notes for a given date, or empty string."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT notes FROM daily_reports WHERE date=?", (date,)
        ).fetchone()
    return row["notes"] if row else ""


def save_report_notes(date: str, notes: str) -> None:
    """Upsert the مسير notes for a given date."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO daily_reports (date, notes) VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET notes = excluded.notes
        """, (date, notes))


def get_dates_with_data() -> List[str]:
    """Return sorted list of dates that have either contact or absence data."""
    with _connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT date FROM daily_contact
            UNION
            SELECT DISTINCT date FROM daily_absence
            ORDER BY date DESC
            LIMIT 90
        """).fetchall()
    return [r["date"] for r in rows]


# ── Order letter CRUD ─────────────────────────────────────────────────────────

def save_order_letter(letter: OrderLetter, items: List[OrderItem]) -> int:
    """Insert a new order letter + its items. Returns the new letter id."""
    with _connection() as conn:
        cur = conn.execute("""
            INSERT INTO order_letters (letter_date, period_start, period_end, notes)
            VALUES (?,?,?,?)
        """, (letter.letter_date, letter.period_start, letter.period_end, letter.notes))
        letter_id = int(cur.lastrowid)  # type: ignore[arg-type]
        conn.executemany("""
            INSERT INTO order_items (letter_id, meal_type, collegial, qualifying, monitors)
            VALUES (?,?,?,?,?)
        """, [(letter_id, i.meal_type, i.collegial, i.qualifying, i.monitors)
              for i in items])
    return letter_id


def get_all_order_letters() -> List[OrderLetter]:
    """Return all order letters ordered by letter_date DESC."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM order_letters ORDER BY letter_date DESC"
        ).fetchall()
    return [
        OrderLetter(
            id=r["id"], letter_date=r["letter_date"],
            period_start=r["period_start"], period_end=r["period_end"],
            notes=r["notes"],
        )
        for r in rows
    ]


def get_order_items(letter_id: int) -> List[OrderItem]:
    """Return all items for a given order letter."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM order_items WHERE letter_id=? ORDER BY meal_type",
            (letter_id,),
        ).fetchall()
    return [
        OrderItem(
            id=r["id"], letter_id=r["letter_id"],
            meal_type=r["meal_type"],
            collegial=r["collegial"], qualifying=r["qualifying"],
            monitors=r["monitors"],
        )
        for r in rows
    ]


def delete_order_letter(letter_id: int) -> None:
    """Delete an order letter and its items (CASCADE)."""
    with _connection() as conn:
        conn.execute("DELETE FROM order_letters WHERE id=?", (letter_id,))


# ── Violations CRUD ───────────────────────────────────────────────────────────

def _row_to_violation(r: sqlite3.Row) -> Violation:
    return Violation(
        id=r["id"],
        date=r["date"],
        student_id=r["student_id"],
        student_name=r["student_name"],
        student_class=r["student_class"],
        violation_type=r["violation_type"],
        description=r["description"],
        action_taken=r["action_taken"],
        reported_by=r["reported_by"],
    )


def add_violation(v: Violation) -> int:
    """Insert a new violation. Returns its new id."""
    with _connection() as conn:
        cur = conn.execute("""
            INSERT INTO violations
                (date, student_id, student_name, student_class,
                 violation_type, description, action_taken, reported_by)
            VALUES (?,?,?,?,?,?,?,?)
        """, (v.date, v.student_id, v.student_name, v.student_class,
              v.violation_type, v.description, v.action_taken, v.reported_by))
        return int(cur.lastrowid)  # type: ignore[arg-type]


def update_violation(v: Violation) -> None:
    """Update an existing violation by id."""
    with _connection() as conn:
        conn.execute("""
            UPDATE violations SET
                date=?, student_id=?, student_name=?, student_class=?,
                violation_type=?, description=?, action_taken=?, reported_by=?
            WHERE id=?
        """, (v.date, v.student_id, v.student_name, v.student_class,
              v.violation_type, v.description, v.action_taken, v.reported_by,
              v.id))


def delete_violation(violation_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM violations WHERE id=?", (violation_id,))


def get_all_violations(limit: int = 200) -> List[Violation]:
    """Return violations newest-first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM violations ORDER BY date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_violation(r) for r in rows]


def search_violations(
    name_q: str = "",
    date_from: str = "",
    date_to: str = "",
    vtype: str = "",
) -> List[Violation]:
    """Flexible search with optional filters."""
    sql  = "SELECT * FROM violations WHERE 1=1"
    args: list = []
    if name_q:
        sql += " AND student_name LIKE ?"
        args.append(f"%{name_q}%")
    if date_from:
        sql += " AND date >= ?"
        args.append(date_from)
    if date_to:
        sql += " AND date <= ?"
        args.append(date_to)
    if vtype:
        sql += " AND violation_type = ?"
        args.append(vtype)
    sql += " ORDER BY date DESC, id DESC LIMIT 500"
    with _connection() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_violation(r) for r in rows]
