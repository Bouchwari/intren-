"""Queries behind the deep statistics on الإحصائيات.

Everything here answers a question the app could not answer before: how the
months compare, when pupils are absent, and which days are still missing
paperwork. Each function returns plain data — no Qt, no Arabic, no formatting.

A day with no row is NOT a day of zeros: these functions report what was
recorded and leave "not recorded" distinguishable from "recorded as none",
because on a paperwork app the difference is the whole point.
"""
from typing import Dict, List, Set, Tuple

from data.database import _connection

# The count columns on daily_contact / daily_absence, grouped by cycle. The
# retired *_paying columns are still summed so old rows keep adding up — see
# the skill's vocabulary table.
_CYCLE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "primary": ("primary_granted", "primary_complement"),
    "collegial": ("collegial_granted", "collegial_paying", "collegial_complement"),
    "qualifying": ("qualifying_granted", "qualifying_paying", "qualifying_complement"),
    "monitors": ("monitors", "monitors_complement"),
}


def _cycle_sum_sql() -> str:
    # The alias is QUOTED: "primary" is a reserved word in SQLite, the same
    # trap that forced order_items.primary_count to be named that way.
    return ", ".join(
        f'SUM({" + ".join(columns)}) AS "{cycle}"'
        for cycle, columns in _CYCLE_COLUMNS.items()
    )


def get_absence_by_cycle(start_date: str, end_date: str) -> Dict[str, int]:
    """Absences in the period, per cycle. Empty dict when nothing is recorded."""
    with _connection() as conn:
        row = conn.execute(f"""
            SELECT {_cycle_sum_sql()}
            FROM daily_absence
            WHERE date BETWEEN ? AND ?
        """, (start_date, end_date)).fetchone()
    if row is None:
        return {}
    return {cycle: (row[cycle] or 0) for cycle in _CYCLE_COLUMNS}


def get_absence_by_date(start_date: str, end_date: str) -> Dict[str, int]:
    """date → total absences. The caller turns dates into weekdays; SQLite's
    own strftime('%w') would work but the app already parses ISO dates in
    core/, and keeping the weekday logic there keeps it testable."""
    total = " + ".join(
        column for columns in _CYCLE_COLUMNS.values() for column in columns)
    with _connection() as conn:
        rows = conn.execute(f"""
            SELECT date, SUM({total}) AS absences
            FROM daily_absence
            WHERE date BETWEEN ? AND ?
            GROUP BY date
        """, (start_date, end_date)).fetchall()
    return {row["date"]: (row["absences"] or 0) for row in rows}


def get_attendance_by_date(start_date: str, end_date: str) -> Dict[str, int]:
    """date → total expected beneficiaries, so an absence count can be read as
    a RATE. 40 absences means nothing without the roster it came out of."""
    total = " + ".join(
        column for columns in _CYCLE_COLUMNS.values() for column in columns)
    with _connection() as conn:
        rows = conn.execute(f"""
            SELECT date, SUM({total}) AS expected
            FROM daily_contact
            WHERE date BETWEEN ? AND ?
            GROUP BY date
        """, (start_date, end_date)).fetchall()
    return {row["date"]: (row["expected"] or 0) for row in rows}


def get_document_dates(start_date: str, end_date: str) -> Dict[str, Set[str]]:
    """Which dates in the period have which document, in ONE pass per table.

    Keys match core.document_pipeline's DOC_* constants so the two agree on
    what a document is called. Building this per-day instead would re-query
    five tables for every date in the month.
    """
    dates: Dict[str, Set[str]] = {}
    with _connection() as conn:
        for key, table in (("contact", "daily_contact"),
                           ("absence", "daily_absence"),
                           ("report", "daily_reports"),
                           ("reception", "daily_reception_records")):
            rows = conn.execute(
                f"SELECT DISTINCT date FROM {table} WHERE date BETWEEN ? AND ?",
                (start_date, end_date)).fetchall()
            dates[key] = {row["date"] for row in rows}

        # An order letter covers a RANGE of days, so it cannot be matched by
        # date equality like the others.
        letters = conn.execute("""
            SELECT period_start, period_end FROM order_letters
            WHERE period_end >= ? AND period_start <= ?
        """, (start_date, end_date)).fetchall()
    dates["order_letter"] = {
        (row["period_start"], row["period_end"]) for row in letters}
    return dates


def get_recorded_dates(start_date: str, end_date: str) -> List[str]:
    """Every date in the period that has a contact or absence sheet — the days
    the school actually served, as opposed to every date on the calendar."""
    with _connection() as conn:
        rows = conn.execute("""
            SELECT DISTINCT date FROM daily_contact
            WHERE date BETWEEN ? AND ?
            UNION
            SELECT DISTINCT date FROM daily_absence
            WHERE date BETWEEN ? AND ?
            ORDER BY date
        """, (start_date, end_date, start_date, end_date)).fetchall()
    return [row["date"] for row in rows]


def get_monthly_meal_totals() -> Dict[str, Dict[str, int]]:
    """month → meal_type → meals served (contact minus absence, floored at 0).

    EVERY meal type, Ramadan's إفطار/سحور included. get_monthly_summaries —
    which الملخص الشهري uses — hardcodes the three normal meals, so a month
    containing Ramadan comes back missing whatever was served on those days;
    on the demo database that is 3,060 of March's meals. A trend built on it
    would show a collapse that never happened.

    Netted PER MEAL TYPE then floored, never on the month's aggregate: an
    absence booked against one meal must not cancel another meal's attendance.
    """
    total = " + ".join(
        column for columns in _CYCLE_COLUMNS.values() for column in columns)
    served: Dict[str, Dict[str, int]] = {}
    with _connection() as conn:
        for table, sign in (("daily_contact", 1), ("daily_absence", -1)):
            rows = conn.execute(f"""
                SELECT substr(date, 1, 7) AS month, meal_type,
                       SUM({total}) AS meals
                FROM {table}
                GROUP BY month, meal_type
            """).fetchall()
            for row in rows:
                month = served.setdefault(row["month"], {})
                month[row["meal_type"]] = (
                    month.get(row["meal_type"], 0) + sign * (row["meals"] or 0))
    return {month: {meal: max(0, count) for meal, count in meals.items()}
            for month, meals in served.items()}


def get_days_recorded_per_month() -> Dict[str, int]:
    """month → how many distinct days have any contact or absence sheet."""
    with _connection() as conn:
        rows = conn.execute("""
            SELECT substr(date, 1, 7) AS month, COUNT(DISTINCT date) AS days
            FROM (SELECT date FROM daily_contact
                  UNION SELECT date FROM daily_absence)
            GROUP BY month
        """).fetchall()
    return {row["month"]: row["days"] for row in rows}
