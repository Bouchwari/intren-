"""Monthly report CRUD + aggregates, expense statement query — moved out of
database.py (Stage 1.5, Prompt 6)."""
from typing import List

from core.models import MonthlyMealSummary
from data.database import _connection


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
