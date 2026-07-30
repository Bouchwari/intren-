"""SQLite database — local, file-based, zero setup."""
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from config.settings import DB_PATH, MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import DailyAbsence, DailyContact, DailyContactDocumentLog, DailyReport, MealEntry, MealProgram, MonthlyMealSummary, OrderItem, OrderLetter, SchoolSettings, Student, Violation


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """Open a connection and guarantee commit-then-close."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add new columns to existing tables without losing data (safe to run every launch)."""
    settings_cols = [
        "school_name_fr TEXT NOT NULL DEFAULT ''",
        "aref TEXT NOT NULL DEFAULT ''",
        "direction_provinciale TEXT NOT NULL DEFAULT ''",
        "gresa_code TEXT NOT NULL DEFAULT ''",
        "gestionnaire TEXT NOT NULL DEFAULT ''",
        "surveillant_general TEXT NOT NULL DEFAULT ''",
        "contract_number TEXT NOT NULL DEFAULT ''",
        "contract_object TEXT NOT NULL DEFAULT ''",
        "supplier_name TEXT NOT NULL DEFAULT ''",
        "company_name TEXT NOT NULL DEFAULT ''",
        "supplier_address TEXT NOT NULL DEFAULT ''",
        "price_ftour TEXT NOT NULL DEFAULT ''",
        "price_ghada TEXT NOT NULL DEFAULT ''",
        "price_asha TEXT NOT NULL DEFAULT ''",
        "price_ftour_ramadan TEXT NOT NULL DEFAULT ''",
        "price_asha_ramadan TEXT NOT NULL DEFAULT ''",
        "price_shour TEXT NOT NULL DEFAULT ''",
    ]
    student_cols = [
        "massar_number TEXT NOT NULL DEFAULT ''",
        "gender TEXT NOT NULL DEFAULT ''",
        "cycle TEXT NOT NULL DEFAULT ''",
        "education_type TEXT NOT NULL DEFAULT ''",
        "is_monitor INTEGER NOT NULL DEFAULT 0",
        "phone TEXT NOT NULL DEFAULT ''",
    ]
    daily_contact_cols = [
        "primary_granted INTEGER NOT NULL DEFAULT 0",
        "primary_complement INTEGER NOT NULL DEFAULT 0",
        "monitors_complement INTEGER NOT NULL DEFAULT 0",
    ]
    daily_absence_cols = [
        "primary_granted INTEGER NOT NULL DEFAULT 0",
        "primary_complement INTEGER NOT NULL DEFAULT 0",
        "monitors_complement INTEGER NOT NULL DEFAULT 0",
    ]
    for col_def in settings_cols:
        try:
            conn.execute(f"ALTER TABLE school_settings ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists — skip
    for col_def in student_cols:
        try:
            conn.execute(f"ALTER TABLE students ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass
    for col_def in daily_contact_cols:
        try:
            conn.execute(f"ALTER TABLE daily_contact ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass
    for col_def in daily_absence_cols:
        try:
            conn.execute(f"ALTER TABLE daily_absence ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass


def init_database() -> None:
    """Create tables on first run and apply migrations. Safe to call every launch."""
    with _connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS school_settings (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                school_name TEXT    NOT NULL,
                city        TEXT    NOT NULL DEFAULT '',
                academy     TEXT    NOT NULL DEFAULT '',
                director    TEXT    NOT NULL DEFAULT '',
                school_year TEXT    NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS students (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name     TEXT    NOT NULL,
                massar_number TEXT    NOT NULL DEFAULT '',
                gender        TEXT    NOT NULL DEFAULT '',
                cycle         TEXT    NOT NULL DEFAULT '',
                education_type TEXT   NOT NULL DEFAULT '',
                student_class TEXT    NOT NULL DEFAULT '',
                birth_date    TEXT    NOT NULL DEFAULT '',
                birth_place   TEXT    NOT NULL DEFAULT '',
                grant_number  TEXT    NOT NULL DEFAULT '',
                section       TEXT    NOT NULL DEFAULT 'cantine',
                grant_type    TEXT    NOT NULL DEFAULT 'full'
            );
            CREATE TABLE IF NOT EXISTS meal_programs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                school_year TEXT    NOT NULL DEFAULT '',
                is_ramadan  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS meal_program_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                program_id  INTEGER NOT NULL REFERENCES meal_programs(id) ON DELETE CASCADE,
                day_of_week INTEGER NOT NULL,
                meal_type   TEXT    NOT NULL,
                menu_text   TEXT    NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS daily_contact (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                date                  TEXT    NOT NULL,
                meal_type             TEXT    NOT NULL,
                primary_granted       INTEGER NOT NULL DEFAULT 0,
                primary_complement    INTEGER NOT NULL DEFAULT 0,
                collegial_granted     INTEGER NOT NULL DEFAULT 0,
                collegial_paying      INTEGER NOT NULL DEFAULT 0,
                collegial_complement  INTEGER NOT NULL DEFAULT 0,
                qualifying_granted    INTEGER NOT NULL DEFAULT 0,
                qualifying_paying     INTEGER NOT NULL DEFAULT 0,
                qualifying_complement INTEGER NOT NULL DEFAULT 0,
                monitors              INTEGER NOT NULL DEFAULT 0,
                monitors_complement   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(date, meal_type)
            );
            CREATE TABLE IF NOT EXISTS daily_contact_documents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT    NOT NULL,
                document_number INTEGER NOT NULL,
                action          TEXT    NOT NULL,
                ftour_total     INTEGER NOT NULL DEFAULT 0,
                ghada_total     INTEGER NOT NULL DEFAULT 0,
                asha_total      INTEGER NOT NULL DEFAULT 0,
                grand_total     INTEGER NOT NULL DEFAULT 0,
                file_path       TEXT    NOT NULL DEFAULT '',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS daily_absence (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                date                  TEXT    NOT NULL,
                meal_type             TEXT    NOT NULL,
                primary_granted       INTEGER NOT NULL DEFAULT 0,
                primary_complement    INTEGER NOT NULL DEFAULT 0,
                collegial_granted     INTEGER NOT NULL DEFAULT 0,
                collegial_paying      INTEGER NOT NULL DEFAULT 0,
                collegial_complement  INTEGER NOT NULL DEFAULT 0,
                qualifying_granted    INTEGER NOT NULL DEFAULT 0,
                qualifying_paying     INTEGER NOT NULL DEFAULT 0,
                qualifying_complement INTEGER NOT NULL DEFAULT 0,
                monitors              INTEGER NOT NULL DEFAULT 0,
                monitors_complement   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(date, meal_type)
            );
            CREATE TABLE IF NOT EXISTS daily_reports (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT    NOT NULL UNIQUE,
                notes      TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS monthly_reports (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                month      TEXT    NOT NULL UNIQUE,
                notes      TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS order_letters (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                letter_date  TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end   TEXT NOT NULL,
                notes        TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                letter_id  INTEGER NOT NULL REFERENCES order_letters(id) ON DELETE CASCADE,
                meal_type  TEXT NOT NULL,
                collegial  INTEGER NOT NULL DEFAULT 0,
                qualifying INTEGER NOT NULL DEFAULT 0,
                monitors   INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS violations (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                date           TEXT NOT NULL,
                student_id     INTEGER REFERENCES students(id) ON DELETE SET NULL,
                student_name   TEXT NOT NULL DEFAULT '',
                student_class  TEXT NOT NULL DEFAULT '',
                violation_type TEXT NOT NULL DEFAULT '',
                description    TEXT NOT NULL DEFAULT '',
                action_taken   TEXT NOT NULL DEFAULT '',
                reported_by    TEXT NOT NULL DEFAULT '',
                created_at     TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS app_preferences (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
        """)
        _migrate(conn)


# ── School settings CRUD ──────────────────────────────────────────────────────

def save_school_settings(s: SchoolSettings) -> None:
    """Upsert all school settings (always stored as row id=1)."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO school_settings (
                id, school_name, school_name_fr, aref, direction_provinciale,
                gresa_code, city, academy, director, school_year,
                gestionnaire, surveillant_general,
                contract_number, contract_object, supplier_name,
                company_name, supplier_address,
                price_ftour, price_ghada, price_asha,
                price_ftour_ramadan, price_asha_ramadan, price_shour
            ) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                school_name=excluded.school_name,
                school_name_fr=excluded.school_name_fr,
                aref=excluded.aref,
                direction_provinciale=excluded.direction_provinciale,
                gresa_code=excluded.gresa_code,
                city=excluded.city,
                academy=excluded.academy,
                director=excluded.director,
                school_year=excluded.school_year,
                gestionnaire=excluded.gestionnaire,
                surveillant_general=excluded.surveillant_general,
                contract_number=excluded.contract_number,
                contract_object=excluded.contract_object,
                supplier_name=excluded.supplier_name,
                company_name=excluded.company_name,
                supplier_address=excluded.supplier_address,
                price_ftour=excluded.price_ftour,
                price_ghada=excluded.price_ghada,
                price_asha=excluded.price_asha,
                price_ftour_ramadan=excluded.price_ftour_ramadan,
                price_asha_ramadan=excluded.price_asha_ramadan,
                price_shour=excluded.price_shour
        """, (
            s.school_name, s.school_name_fr, s.aref, s.direction_provinciale,
            s.gresa_code, s.city, s.academy, s.director, s.school_year,
            s.gestionnaire, s.surveillant_general,
            s.contract_number, s.contract_object, s.supplier_name,
            s.company_name, s.supplier_address,
            s.price_ftour, s.price_ghada, s.price_asha,
            s.price_ftour_ramadan, s.price_asha_ramadan, s.price_shour,
        ))


def get_school_settings() -> Optional[SchoolSettings]:
    """Return the saved school settings, or None if not yet configured."""
    with _connection() as conn:
        row = conn.execute("SELECT * FROM school_settings WHERE id = 1").fetchone()
    if row is None:
        return None

    def _r(key: str) -> str:
        try:
            return row[key] or ""
        except IndexError:
            return ""

    return SchoolSettings(
        school_name=_r("school_name"),
        school_name_fr=_r("school_name_fr"),
        aref=_r("aref"),
        direction_provinciale=_r("direction_provinciale"),
        gresa_code=_r("gresa_code"),
        city=_r("city"),
        academy=_r("academy"),
        director=_r("director"),
        school_year=_r("school_year"),
        gestionnaire=_r("gestionnaire"),
        surveillant_general=_r("surveillant_general"),
        contract_number=_r("contract_number"),
        contract_object=_r("contract_object"),
        supplier_name=_r("supplier_name"),
        company_name=_r("company_name"),
        supplier_address=_r("supplier_address"),
        price_ftour=_r("price_ftour"),
        price_ghada=_r("price_ghada"),
        price_asha=_r("price_asha"),
        price_ftour_ramadan=_r("price_ftour_ramadan"),
        price_asha_ramadan=_r("price_asha_ramadan"),
        price_shour=_r("price_shour"),
    )


# ── Students CRUD ─────────────────────────────────────────────────────────────

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


# ── Meal programs CRUD ────────────────────────────────────────────────────────

def get_all_programs() -> List[MealProgram]:
    """Return all meal programs ordered by creation date."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, name, school_year, is_ramadan FROM meal_programs ORDER BY id"
        ).fetchall()
    return [
        MealProgram(
            id=r["id"],
            name=r["name"],
            school_year=r["school_year"] or "",
            is_ramadan=bool(r["is_ramadan"]),
        )
        for r in rows
    ]


def create_program(name: str, school_year: str = "", is_ramadan: bool = False) -> int:
    """Insert a new empty meal program. Returns the new id."""
    with _connection() as conn:
        cur = conn.execute(
            "INSERT INTO meal_programs (name, school_year, is_ramadan) VALUES (?,?,?)",
            (name, school_year, int(is_ramadan)),
        )
        return int(cur.lastrowid)  # type: ignore[arg-type]


def rename_program(program_id: int, new_name: str) -> None:
    with _connection() as conn:
        conn.execute(
            "UPDATE meal_programs SET name=? WHERE id=?", (new_name, program_id)
        )


def set_program_ramadan_mode(program_id: int, is_ramadan: bool) -> None:
    """Persist whether a meal program uses the Ramadan meal layout."""
    with _connection() as conn:
        conn.execute(
            "UPDATE meal_programs SET is_ramadan=? WHERE id=?",
            (int(is_ramadan), program_id),
        )


def delete_program(program_id: int) -> None:
    """Delete program and all its entries (CASCADE handles entries)."""
    with _connection() as conn:
        conn.execute("DELETE FROM meal_programs WHERE id=?", (program_id,))


def get_program_entries(program_id: int) -> List[MealEntry]:
    """Return all entries for one program."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, program_id, day_of_week, meal_type, menu_text "
            "FROM meal_program_entries WHERE program_id=?",
            (program_id,),
        ).fetchall()
    return [
        MealEntry(
            id=r["id"],
            program_id=r["program_id"],
            day_of_week=r["day_of_week"],
            meal_type=r["meal_type"],
            menu_text=r["menu_text"] or "",
        )
        for r in rows
    ]


def save_program_entries(program_id: int, entries: List[MealEntry]) -> None:
    """Replace all entries for a program with the provided list."""
    with _connection() as conn:
        conn.execute(
            "DELETE FROM meal_program_entries WHERE program_id=?", (program_id,)
        )
        conn.executemany(
            "INSERT INTO meal_program_entries (program_id, day_of_week, meal_type, menu_text) "
            "VALUES (?,?,?,?)",
            [(e.program_id, e.day_of_week, e.meal_type, e.menu_text) for e in entries],
        )


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


# ── Monthly report CRUD + aggregates ──────────────────────────────────────────

def _aggregate_month(month: str, table: str) -> dict:
    """SUM all count columns for a given YYYY-MM month from a daily table.
    Returns a dict keyed by meal_type."""
    with _connection() as conn:
        rows = conn.execute(f"""
            SELECT meal_type,
                SUM(primary_granted)       AS pg,
                SUM(primary_complement)    AS pc,
                SUM(collegial_granted)     AS cg,
                SUM(collegial_paying)      AS cp,
                SUM(collegial_complement)  AS cc,
                SUM(qualifying_granted)    AS qg,
                SUM(qualifying_paying)     AS qp,
                SUM(qualifying_complement) AS qc,
                SUM(monitors)              AS mo,
                SUM(monitors_complement)   AS mc,
                COUNT(DISTINCT date)       AS days
            FROM {table}
            WHERE date LIKE ?
            GROUP BY meal_type
        """, (f"{month}-%",)).fetchall()
    return {
        r["meal_type"]: {
            "pg": r["pg"] or 0, "pc": r["pc"] or 0,
            "cg": r["cg"] or 0, "cp": r["cp"] or 0, "cc": r["cc"] or 0,
            "qg": r["qg"] or 0, "qp": r["qp"] or 0, "qc": r["qc"] or 0,
            "mo": r["mo"] or 0, "mc": r["mc"] or 0, "days": r["days"] or 0,
        }
        for r in rows
    }


def get_monthly_summaries(month: str, prices: dict) -> List[MonthlyMealSummary]:
    """Build MonthlyMealSummary list for the given YYYY-MM month.
    prices = {"ftour": "X.XX", "ghada": "X.XX", "asha": "X.XX"}
    """
    contacts = _aggregate_month(month, "daily_contact")
    absences = _aggregate_month(month, "daily_absence")

    from config.settings import MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA
    meal_keys = [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA]
    result = []
    for mk in meal_keys:
        c = contacts.get(mk, {})
        a = absences.get(mk, {})
        try:
            price = float(prices.get(mk, "0") or "0")
        except (ValueError, TypeError):
            price = 0.0
        summary = MonthlyMealSummary(
            meal_type=mk,
            days_count=max(c.get("days", 0), a.get("days", 0)),
            contact_primary=c.get("pg", 0) + c.get("pc", 0),
            contact_collegial=c.get("cg", 0) + c.get("cp", 0) + c.get("cc", 0),
            contact_qualifying=c.get("qg", 0) + c.get("qp", 0) + c.get("qc", 0),
            contact_monitors=c.get("mo", 0) + c.get("mc", 0),
            absence_primary=a.get("pg", 0) + a.get("pc", 0),
            absence_collegial=a.get("cg", 0) + a.get("cp", 0) + a.get("cc", 0),
            absence_qualifying=a.get("qg", 0) + a.get("qp", 0) + a.get("qc", 0),
            absence_monitors=a.get("mo", 0) + a.get("mc", 0),
            unit_price=price,
        )
        result.append(summary)
    return result


def get_monthly_report_notes(month: str) -> str:
    with _connection() as conn:
        row = conn.execute(
            "SELECT notes FROM monthly_reports WHERE month=?", (month,)
        ).fetchone()
    return row["notes"] if row else ""


def save_monthly_report_notes(month: str, notes: str) -> None:
    with _connection() as conn:
        conn.execute("""
            INSERT INTO monthly_reports (month, notes) VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET notes = excluded.notes
        """, (month, notes))


def get_months_with_data() -> List[str]:
    """Return YYYY-MM strings that have contact or absence data, newest first."""
    with _connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT substr(date, 1, 7) AS month FROM daily_contact
            UNION
            SELECT DISTINCT substr(date, 1, 7) AS month FROM daily_absence
            ORDER BY month DESC
        """).fetchall()
    return [r["month"] for r in rows]


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


# ── Expense statement query ───────────────────────────────────────────────────

def get_expense_data(month: str) -> List[dict]:
    """Return per-meal detailed counts for YYYY-MM from daily_contact.
    Each dict has keys: meal_type, cg/cp/cc (إعدادي ممنوح/مؤد/متمم),
    qg/qp/qc (تأهيلي ممنوح/مؤد/متمم), mo (معلمون)."""
    raw = _aggregate_month(month, "daily_contact")
    from config.settings import MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA
    result = []
    for mk in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA):
        c = raw.get(mk, {})
        result.append({
            "meal_type": mk,
            "cg": c.get("cg", 0), "cp": c.get("cp", 0), "cc": c.get("cc", 0),
            "qg": c.get("qg", 0), "qp": c.get("qp", 0), "qc": c.get("qc", 0),
            "mo": c.get("mo", 0),
        })
    return result


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
