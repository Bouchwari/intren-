"""Monthly report CRUD + aggregates, expense statement query — moved out of
database.py (Stage 1.5, Prompt 6)."""
from typing import List, Optional

from core.models import MonthlyMealSummary, MonthlyReceptionRecord
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

    from config.settings import RAMADAN_MEALS, REGULAR_MEALS
    meal_keys = list(REGULAR_MEALS) + [
        meal for meal in RAMADAN_MEALS
        if meal in contacts or meal in absences
    ]
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


# ── Monthly reception record (محضر التسلم الشهري) ─────────────────────────────

def sum_daily_reception_for_month(month: str) -> dict:
    """Sum that month's saved daily_reception_records — the actual-
    delivered confirmations, not contact_sheet's ordered/estimated
    totals — as the default a fresh monthly reception record starts
    from."""
    with _connection() as conn:
        row = conn.execute("""
            SELECT SUM(ftour_qty) AS ftour, SUM(ghada_qty) AS ghada, SUM(asha_qty) AS asha,
                   SUM(ftour_ramadan_qty) AS iftar, SUM(shour_qty) AS shour
            FROM daily_reception_records
            WHERE date LIKE ?
        """, (f"{month}-%",)).fetchone()
    return {
        "ftour": row["ftour"] or 0,
        "ghada": row["ghada"] or 0,
        "asha": row["asha"] or 0,
        "iftar": row["iftar"] or 0,
        "shour": row["shour"] or 0,
    }


def _row_to_monthly_reception_record(r) -> MonthlyReceptionRecord:
    return MonthlyReceptionRecord(
        id=r["id"],
        month=r["month"],
        ftour_qty=r["ftour_qty"],
        ftour_ramadan_qty=r["ftour_ramadan_qty"],
        shour_qty=r["shour_qty"],
        ghada_qty=r["ghada_qty"],
        asha_qty=r["asha_qty"],
        remarks=r["remarks"],
    )


def get_monthly_reception_record(month: str) -> Optional[MonthlyReceptionRecord]:
    """Return the saved محضر تسليم الخدمة الشهري (quantities + remarks)
    for a YYYY-MM month, or None."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM monthly_reception_records WHERE month=?", (month,)
        ).fetchone()
    return _row_to_monthly_reception_record(row) if row else None


def save_monthly_reception_record(record: MonthlyReceptionRecord) -> None:
    """Upsert the monthly reception record (delivered quantities + remarks)."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO monthly_reception_records (month, ftour_qty, ghada_qty, asha_qty,
                                                   ftour_ramadan_qty, shour_qty, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(month) DO UPDATE SET
                ftour_qty=excluded.ftour_qty,
                ftour_ramadan_qty=excluded.ftour_ramadan_qty,
                shour_qty=excluded.shour_qty,
                ghada_qty=excluded.ghada_qty,
                asha_qty=excluded.asha_qty,
                remarks=excluded.remarks
        """, (record.month, record.ftour_qty, record.ghada_qty, record.asha_qty,
              record.ftour_ramadan_qty, record.shour_qty, record.remarks))


# ── Expense statement query ───────────────────────────────────────────────────

def get_expense_data(month: str) -> List[dict]:
    """Return per-meal detailed counts for YYYY-MM from daily_contact.
    Each dict has keys: meal_type, pg/pc (ابتدائي ممنوح/متمم — no "paying"
    column exists for this cycle), cg/cp/cc (إعدادي ممنوح/مؤد/متمم),
    qg/qp/qc (تأهيلي ممنوح/مؤد/متمم), mo (معلمون، شامل المتمم).

    ابتدائي used to be silently dropped here even though _aggregate_month
    already computes it (pg/pc) — every total in the expense statement
    (table, summary cards, Excel) understated real cost for any school
    with primary-cycle boarders. Monitors' complement (mc) was similarly
    computed but discarded; now folded into "mo", matching how
    get_monthly_summaries treats contact_monitors elsewhere."""
    raw = _aggregate_month(month, "daily_contact")
    from config.settings import MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA
    result = []
    for mk in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA):
        c = raw.get(mk, {})
        result.append({
            "meal_type": mk,
            "pg": c.get("pg", 0), "pc": c.get("pc", 0),
            "cg": c.get("cg", 0), "cp": c.get("cp", 0), "cc": c.get("cc", 0),
            "qg": c.get("qg", 0), "qp": c.get("qp", 0), "qc": c.get("qc", 0),
            "mo": c.get("mo", 0) + c.get("mc", 0),
        })
    return result


# ── Quarterly reception attestation (محضر التسلم الفصلي) ─────────────────────

def get_daily_meals_by_lot_for_month(month: str) -> List[dict]:
    """One row per calendar day in YYYY-MM (including days with no data,
    matching the real quarterly attestation template's own day-by-day
    layout), net meals served (contact − absence, floored at 0) split
    into the two catering-contract groupings the template itself uses:
    LOT 901 "PRIMAIRE ET COLLEGIAL" (ابتدائي + إعدادي, plus معلمو
    الداخلية folded in here since they have no LOT of their own) and
    LOT 902 "QUALIFIANT" (تأهيلي alone).

    Netting is done PER CATEGORY and only then summed into a LOT — not the
    other way round. Aggregating first lets an absence booked against one
    category eat another category's real attendance (e.g. a collegial
    absence row cancelling primary meals that genuinely happened), and the
    floor-at-zero would then hide that it ever occurred. Since these totals
    are what the administration pays against, an absence can only ever
    reduce meals in its own category.

    Ramadan's meals (إفطار/سحور) are returned alongside the normal three,
    keyed `lot901_ftour_ramadan` / `lot901_shour` and their 902 twins, so
    the quarterly attestation can fill its FTOUR/SHOUR blocks with real
    recorded numbers instead of leaving them blank.

    Each dict: {"date", "day"} plus lot901_/lot902_ for every meal key."""
    import calendar
    from config.settings import (
        MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR,
    )

    year_str, month_num_str = month.split("-")
    year, month_num = int(year_str), int(month_num_str)
    days_in_month = calendar.monthrange(year, month_num)[1]

    # Every counted column, grouped by the catering LOT it belongs to.
    lot_columns = {
        "lot901": (
            "primary_granted", "primary_complement",
            "collegial_granted", "collegial_paying", "collegial_complement",
            "monitors", "monitors_complement",
        ),
        "lot902": (
            "qualifying_granted", "qualifying_paying", "qualifying_complement",
        ),
    }
    all_columns = lot_columns["lot901"] + lot_columns["lot902"]
    column_list = ", ".join(all_columns)

    def _fetch(table: str) -> dict:
        with _connection() as conn:
            rows = conn.execute(f"""
                SELECT date, meal_type, {column_list}
                FROM {table}
                WHERE date LIKE ?
            """, (f"{month}-%",)).fetchall()
        return {
            (r["date"], r["meal_type"]): {col: r[col] or 0 for col in all_columns}
            for r in rows
        }

    contact = _fetch("daily_contact")
    absence = _fetch("daily_absence")
    empty = {col: 0 for col in all_columns}

    result = []
    for day in range(1, days_in_month + 1):
        date_str = f"{month}-{day:02d}"
        row = {"date": date_str, "day": day}
        for meal in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA, MEAL_IFTAR, MEAL_SHOUR):
            served = contact.get((date_str, meal), empty)
            missed = absence.get((date_str, meal), empty)
            for lot, columns in lot_columns.items():
                row[f"{lot}_{meal}"] = sum(
                    max(0, served[col] - missed[col]) for col in columns
                )
        result.append(row)
    return result
