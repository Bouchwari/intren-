"""SQLite database — local, file-based, zero setup.

Connection helper and schema live here. The CRUD functions that used to
live in this file were split by subject into students_repo.py,
daily_repo.py, program_repo.py, monthly_repo.py and settings_repo.py
(Stage 1.5, Prompt 6) — this module re-exports all of them so existing
imports in src/ui/ keep working unchanged.
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config.settings import DB_PATH


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
    daily_report_cols = [
        "hygiene_staff INTEGER NOT NULL DEFAULT -1",
        "hygiene_utensils INTEGER NOT NULL DEFAULT -1",
        "hygiene_dining_hall INTEGER NOT NULL DEFAULT -1",
        "hygiene_kitchen INTEGER NOT NULL DEFAULT -1",
        "hygiene_storage INTEGER NOT NULL DEFAULT -1",
        "hygiene_waste INTEGER NOT NULL DEFAULT -1",
        "hygiene_dorms INTEGER NOT NULL DEFAULT -1",
        "ftour_expected INTEGER NOT NULL DEFAULT 0",
        "ftour_present INTEGER NOT NULL DEFAULT 0",
        "ghada_expected INTEGER NOT NULL DEFAULT 0",
        "ghada_present INTEGER NOT NULL DEFAULT 0",
        "asha_expected INTEGER NOT NULL DEFAULT 0",
        "asha_present INTEGER NOT NULL DEFAULT 0",
        "quality_supplies INTEGER NOT NULL DEFAULT -1",
        "quality_storage INTEGER NOT NULL DEFAULT -1",
        "quality_program INTEGER NOT NULL DEFAULT -1",
        "quality_quantities INTEGER NOT NULL DEFAULT -1",
        "quality_sample_kept INTEGER NOT NULL DEFAULT -1",
        "quality_prep INTEGER NOT NULL DEFAULT -1",
        "quality_serving INTEGER NOT NULL DEFAULT -1",
        "building_condition INTEGER NOT NULL DEFAULT -1",
        "equipment_condition INTEGER NOT NULL DEFAULT -1",
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
    for col_def in daily_report_cols:
        try:
            conn.execute(f"ALTER TABLE daily_reports ADD COLUMN {col_def}")
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


# ── Re-exports — keep every existing `from data.database import ...` working ───

from data.settings_repo import (  # noqa: E402
    save_school_settings,
    get_school_settings,
    get_document_export_format,
    save_document_export_format,
)
from data.students_repo import (  # noqa: E402
    get_all_students,
    get_students_filtered,
    add_student,
    update_student,
    delete_student,
    add_students_bulk,
    get_level_preferences,
    save_level_preferences,
    get_student_counts,
    get_dashboard_stats,
)
from data.program_repo import (  # noqa: E402
    get_all_programs,
    create_program,
    rename_program,
    set_program_ramadan_mode,
    delete_program,
    get_program_entries,
    save_program_entries,
)
from data.daily_repo import (  # noqa: E402
    get_day_contacts,
    get_contact,
    save_daily_contact,
    get_recent_contacts,
    get_last_contacts_before,
    get_next_daily_contact_document_number,
    get_daily_contact_document_number_draft,
    save_daily_contact_document_number_draft,
    record_daily_contact_document,
    get_recent_daily_contact_documents,
    get_day_absences,
    save_daily_absence,
    get_recent_absences,
    get_daily_report,
    save_daily_report,
    get_dates_with_data,
    save_order_letter,
    get_all_order_letters,
    get_order_items,
    delete_order_letter,
    add_violation,
    update_violation,
    delete_violation,
    get_all_violations,
    search_violations,
)
from data.monthly_repo import (  # noqa: E402
    get_monthly_summaries,
    get_monthly_report_notes,
    save_monthly_report_notes,
    get_months_with_data,
    get_expense_data,
)
