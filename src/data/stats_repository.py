"""
src/data/stats_repository.py
SQL queries for dashboard statistics — adapted to the Matama schema.
Returns plain Python dataclasses only (no PySide6).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from config.settings import DB_PATH
import sqlite3
from contextlib import contextmanager


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class StudentStats:
    total:            int = 0
    internat_count:   int = 0
    dar_talib_count:  int = 0
    cantine_count:    int = 0
    full_grant_count: int = 0
    half_grant_count: int = 0
    teachers_count:   int = 0   # monitors


@dataclass
class DailyTotal:
    """Combined total for ALL meals on ONE day."""
    log_date: str
    total:    int = 0


@dataclass
class WeeklyMealDay:
    """Per-meal breakdown for one day."""
    log_date: str
    ftour:    int = 0
    ghada:    int = 0
    asha:     int = 0

    @property
    def day_total(self) -> int:
        return self.ftour + self.ghada + self.asha


@dataclass
class MonthSummary:
    total_meals:  int   = 0
    days_logged:  int   = 0
    avg_daily:    float = 0.0
    ftour_total:  int   = 0
    ghada_total:  int   = 0
    asha_total:   int   = 0


# ── SQL fragment: total beneficiaries per row in daily_contact ────────────────
# Our schema keeps older *_paying columns for migration/backward compatibility.
_SUM_CONTACT = """
    (primary_granted + primary_complement +
     collegial_granted + collegial_paying + collegial_complement +
     qualifying_granted + qualifying_paying + qualifying_complement +
     monitors + monitors_complement)
"""


# ── Query functions ───────────────────────────────────────────────────────────

def fetch_student_stats() -> StudentStats:
    with _conn() as con:
        s = con.execute("""
            SELECT
                COUNT(*)                                               AS total,
                SUM(CASE WHEN section    = 'internat' THEN 1 ELSE 0 END) AS internat_count,
                SUM(CASE WHEN section    = 'dar_talib' THEN 1 ELSE 0 END) AS dar_talib_count,
                SUM(CASE WHEN section    = 'cantine'  THEN 1 ELSE 0 END) AS cantine_count,
                SUM(CASE WHEN grant_type = 'full'     THEN 1 ELSE 0 END) AS full_grant_count,
                SUM(CASE WHEN grant_type = 'half'     THEN 1 ELSE 0 END) AS half_grant_count,
                SUM(CASE WHEN is_monitor = 1          THEN 1 ELSE 0 END) AS teachers_count
            FROM students
        """).fetchone()
    return StudentStats(
        total            = s["total"]            or 0,
        internat_count   = s["internat_count"]   or 0,
        dar_talib_count  = s["dar_talib_count"]  or 0,
        cantine_count    = s["cantine_count"]    or 0,
        full_grant_count = s["full_grant_count"] or 0,
        half_grant_count = s["half_grant_count"] or 0,
        teachers_count   = s["teachers_count"]   or 0,
    )


def fetch_month_summary(year: int, month: int) -> MonthSummary:
    month_str = f"{year:04d}-{month:02d}"
    with _conn() as con:
        row = con.execute(f"""
            SELECT
                SUM({_SUM_CONTACT})                                                            AS total_meals,
                COUNT(DISTINCT date)                                                            AS days_logged,
                SUM(CASE WHEN meal_type = 'ftour' THEN {_SUM_CONTACT} ELSE 0 END)             AS ftour_total,
                SUM(CASE WHEN meal_type = 'ghada' THEN {_SUM_CONTACT} ELSE 0 END)             AS ghada_total,
                SUM(CASE WHEN meal_type = 'asha'  THEN {_SUM_CONTACT} ELSE 0 END)             AS asha_total
            FROM daily_contact
            WHERE strftime('%Y-%m', date) = ?
        """, (month_str,)).fetchone()

    total = row["total_meals"] or 0
    days  = row["days_logged"]  or 0
    return MonthSummary(
        total_meals  = total,
        days_logged  = days,
        avg_daily    = round(total / days, 1) if days > 0 else 0.0,
        ftour_total  = row["ftour_total"] or 0,
        ghada_total  = row["ghada_total"] or 0,
        asha_total   = row["asha_total"]  or 0,
    )


def fetch_last_7_days() -> list:
    today = date.today()
    days_map: dict = {
        (today - timedelta(days=i)).isoformat(): WeeklyMealDay(
            log_date=(today - timedelta(days=i)).isoformat()
        )
        for i in range(6, -1, -1)
    }

    with _conn() as con:
        rows = con.execute(f"""
            SELECT date AS log_date, meal_type, {_SUM_CONTACT} AS total
            FROM daily_contact
            WHERE date >= date('now', '-6 days')
        """).fetchall()

    for row in rows:
        d    = row["log_date"]
        meal = row["meal_type"]
        val  = row["total"] or 0
        if d not in days_map:
            continue
        if meal == "ftour":   days_map[d].ftour = val
        elif meal == "ghada": days_map[d].ghada = val
        elif meal == "asha":  days_map[d].asha  = val

    return list(days_map.values())


def fetch_last_30_days() -> list:
    today = date.today()
    days_map: dict = {
        (today - timedelta(days=i)).isoformat(): DailyTotal(
            log_date=(today - timedelta(days=i)).isoformat()
        )
        for i in range(29, -1, -1)
    }

    with _conn() as con:
        rows = con.execute(f"""
            SELECT date AS log_date, SUM({_SUM_CONTACT}) AS day_total
            FROM daily_contact
            WHERE date >= date('now', '-29 days')
            GROUP BY date
        """).fetchall()

    for row in rows:
        d = row["log_date"]
        if d in days_map:
            days_map[d].total = row["day_total"] or 0

    return list(days_map.values())


def fetch_last_log_date() -> str | None:
    with _conn() as con:
        row = con.execute(
            "SELECT MAX(date) AS d FROM daily_contact"
        ).fetchone()
    return row["d"] if (row and row["d"]) else None
