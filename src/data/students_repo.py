"""Students CRUD, level preferences, dashboard stats — moved out of
database.py (Stage 1.5, Prompt 6)."""
import json
import sqlite3
from typing import List

from core.models import Student
from data.database import _connection


def _row_to_student(r: sqlite3.Row) -> Student:
    def _b(key: str) -> bool:
        try:
            return bool(r[key])
        except IndexError:
            return False

    def _s(key: str) -> str:
        try:
            return r[key] or ""
        except IndexError:
            return ""

    return Student(
        id=r["id"],
        full_name=r["full_name"],
        massar_number=_s("massar_number"),
        gender=_s("gender"),
        cycle=_s("cycle"),
        education_type=_s("education_type"),
        student_class=_s("student_class"),
        birth_date=_s("birth_date"),
        birth_place=_s("birth_place"),
        grant_number=_s("grant_number"),
        section=_s("section") or "cantine",
        grant_type=_s("grant_type") or "full",
        is_monitor=_b("is_monitor"),
        phone=_s("phone"),
    )


def get_all_students() -> List[Student]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM students ORDER BY full_name"
        ).fetchall()
    return [_row_to_student(r) for r in rows]


def get_students_filtered(monitor_only: bool = False, exclude_monitors: bool = False) -> List[Student]:
    """Return students by monitor status."""
    if monitor_only:
        sql = "SELECT * FROM students WHERE is_monitor=1 ORDER BY full_name"
    elif exclude_monitors:
        sql = "SELECT * FROM students WHERE is_monitor=0 ORDER BY full_name"
    else:
        sql = "SELECT * FROM students ORDER BY full_name"
    with _connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_student(r) for r in rows]


def add_student(student: Student) -> int:
    """Insert one student. Returns the new row id."""
    with _connection() as conn:
        cursor = conn.execute(
            "INSERT INTO students "
            "(full_name, massar_number, gender, cycle, education_type, student_class, birth_date, birth_place, grant_number, "
            " section, grant_type, is_monitor, phone) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (student.full_name, student.massar_number, student.gender,
             student.cycle, student.education_type, student.student_class,
             student.birth_date, student.birth_place,
             student.grant_number, student.section,
             student.grant_type, int(student.is_monitor), student.phone),
        )
        return int(cursor.lastrowid)  # type: ignore[arg-type]


def update_student(student: Student) -> None:
    with _connection() as conn:
        conn.execute(
            "UPDATE students SET full_name=?, massar_number=?, gender=?, cycle=?, education_type=?, student_class=?, birth_date=?, "
            "birth_place=?, grant_number=?, section=?, grant_type=?, "
            "is_monitor=?, phone=? WHERE id=?",
            (student.full_name, student.massar_number, student.gender,
             student.cycle, student.education_type, student.student_class,
             student.birth_date, student.birth_place,
             student.grant_number, student.section,
             student.grant_type, int(student.is_monitor), student.phone, student.id),
        )


def delete_student(student_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM students WHERE id=?", (student_id,))


def add_students_bulk(students: List[Student]) -> int:
    """Insert many students at once. Returns count inserted."""
    with _connection() as conn:
        conn.executemany(
            "INSERT INTO students "
            "(full_name, massar_number, gender, cycle, education_type, student_class, birth_date, birth_place, grant_number, "
            " section, grant_type, is_monitor, phone) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(s.full_name, s.massar_number, s.gender, s.cycle, s.education_type, s.student_class, s.birth_date, s.birth_place,
              s.grant_number, s.section, s.grant_type, int(s.is_monitor), s.phone)
             for s in students],
        )
    return len(students)


def get_level_preferences() -> dict:
    """Return the visible cycle/type filters chosen in Settings."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_preferences WHERE key='level_filters'"
        ).fetchone()
    if not row or not row["value"]:
        return {"cycles": [], "education_types": []}
    try:
        data = json.loads(row["value"])
    except json.JSONDecodeError:
        return {"cycles": [], "education_types": []}
    return {
        "cycles": list(data.get("cycles", [])),
        "education_types": list(data.get("education_types", [])),
    }


def save_level_preferences(cycles: list[str], education_types: list[str]) -> None:
    """Persist which level groups should be shown to the user."""
    payload = json.dumps(
        {"cycles": cycles, "education_types": education_types},
        ensure_ascii=False,
    )
    with _connection() as conn:
        conn.execute("""
            INSERT INTO app_preferences (key, value) VALUES ('level_filters', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (payload,))


def get_student_counts() -> dict:
    """Return counts useful for the dashboard."""
    with _connection() as conn:
        total      = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        internat   = conn.execute("SELECT COUNT(*) FROM students WHERE section='internat'").fetchone()[0]
        dar_talib  = conn.execute("SELECT COUNT(*) FROM students WHERE section='dar_talib'").fetchone()[0]
        cantine    = conn.execute("SELECT COUNT(*) FROM students WHERE section='cantine'").fetchone()[0]
        monitors   = conn.execute("SELECT COUNT(*) FROM students WHERE is_monitor=1").fetchone()[0]
        by_class   = conn.execute(
            "SELECT student_class, COUNT(*) as cnt FROM students "
            "WHERE student_class != '' GROUP BY student_class ORDER BY student_class"
        ).fetchall()
    return {
        "total": total,
        "internat": internat,
        "dar_talib": dar_talib,
        "cantine": cantine,
        "monitors": monitors,
        "by_class": [(r["student_class"], r["cnt"]) for r in by_class],
    }


def get_dashboard_stats() -> dict:
    """Aggregate all stats needed for the powerful dashboard."""
    import datetime
    today = datetime.date.today()
    today_str = today.strftime('%Y-%m-%d')
    month_str = today.strftime('%Y-%m')
    meal_total_expr = (
        "primary_granted + primary_complement + "
        "collegial_granted + collegial_paying + collegial_complement + "
        "qualifying_granted + qualifying_paying + qualifying_complement + "
        "monitors + monitors_complement"
    )

    with _connection() as conn:
        # Students
        total      = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        internat   = conn.execute("SELECT COUNT(*) FROM students WHERE section='internat'").fetchone()[0]
        dar_talib  = conn.execute("SELECT COUNT(*) FROM students WHERE section='dar_talib'").fetchone()[0]
        cantine    = conn.execute("SELECT COUNT(*) FROM students WHERE section='cantine'").fetchone()[0]
        monitors   = conn.execute("SELECT COUNT(*) FROM students WHERE is_monitor=1").fetchone()[0]
        grant_full = conn.execute("SELECT COUNT(*) FROM students WHERE grant_type='full'").fetchone()[0]
        grant_half = conn.execute("SELECT COUNT(*) FROM students WHERE grant_type='half'").fetchone()[0]

        # Today's meals (from daily_contact)
        today_meals = conn.execute(
            f"SELECT meal_type, {meal_total_expr} AS total "
            "FROM daily_contact WHERE date=?", (today_str,)
        ).fetchall()
        today_contact = {r["meal_type"]: r["total"] for r in today_meals}

        # Today's absences (from daily_absence)
        today_abs = conn.execute(
            f"SELECT meal_type, {meal_total_expr} AS total "
            "FROM daily_absence WHERE date=?", (today_str,)
        ).fetchall()
        today_absence = {r["meal_type"]: r["total"] for r in today_abs}

        # This month: total meal days served
        month_days_contact = conn.execute(
            "SELECT COUNT(DISTINCT date) FROM daily_contact WHERE date LIKE ?",
            (f"{month_str}-%",)
        ).fetchone()[0]

        # This month: total meals served (sum all granted)
        month_meals_row = conn.execute(
            f"SELECT SUM({meal_total_expr}) FROM daily_contact WHERE date LIKE ?",
            (f"{month_str}-%",)
        ).fetchone()[0]
        month_meals_total = month_meals_row or 0

        # This month: total absences
        month_abs_row = conn.execute(
            f"SELECT SUM({meal_total_expr}) FROM daily_absence WHERE date LIKE ?",
            (f"{month_str}-%",)
        ).fetchone()[0]
        month_absences_total = month_abs_row or 0

        # Last 7 days activity
        week_days = conn.execute(
            f"SELECT date, SUM({meal_total_expr}) AS total "
            "FROM daily_contact WHERE date >= date(?, '-7 days') GROUP BY date ORDER BY date",
            (today_str,)
        ).fetchall()
        week_activity = [(r["date"], r["total"]) for r in week_days]

    return {
        "students": {
            "total": total, "internat": internat, "dar_talib": dar_talib, "cantine": cantine,
            "monitors": monitors, "grant_full": grant_full, "grant_half": grant_half,
        },
        "today": {
            "contact": today_contact,
            "absence": today_absence,
            "date": today_str,
        },
        "month": {
            "label": month_str,
            "days_served": month_days_contact,
            "meals_total": month_meals_total,
            "absences_total": month_absences_total,
        },
        "week_activity": week_activity,
    }
