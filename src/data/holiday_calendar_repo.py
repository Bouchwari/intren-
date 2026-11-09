"""Persist reviewed calendar periods and track only the dates this import owns."""
import json

from core.holiday_calendar import (
    CALENDAR_KEY, CALENDAR_YEAR, calendar_days, default_calendar_rows,
    pending_hijri, validate_calendar_rows,
)
from data.database import _connection
from data.settings_repo import get_school_settings


def get_calendar_state() -> dict:
    with _connection() as conn:
        row = conn.execute("SELECT value FROM app_preferences WHERE key=?", (CALENDAR_KEY,)).fetchone()
    if row is None:
        return {"rows": default_calendar_rows(), "reviewed": False, "owned": {}}
    state = json.loads(row["value"])
    state["rows"] = validate_calendar_rows(state["rows"])
    return state


def calendar_notice() -> str:
    settings = get_school_settings()
    if not settings or settings.school_year.replace("-", "/").replace(" ", "") != CALENDAR_YEAR:
        return ""
    state = get_calendar_state()
    if not state["reviewed"]:
        return "لائحة عطل 2026/2027 في انتظار المراجعة"
    pending = pending_hijri(state["rows"])
    return f"عطل تحتاج تأكيد التاريخ الميلادي: {len(pending)}" if pending else ""


def save_reviewed_calendar(rows: list[dict]) -> tuple[int, int]:
    """Commit the review and its holidays together; preserve manual dates/labels."""
    rows = validate_calendar_rows(rows)
    days = calendar_days(rows)
    owned = {}
    added = kept = 0
    with _connection() as conn:
        record = conn.execute("SELECT value FROM app_preferences WHERE key=?", (CALENDAR_KEY,)).fetchone()
        previous = json.loads(record["value"]).get("owned", {}) if record else {}
        # Reconcile only dates previously inserted by this import and not renamed.
        for day, label in previous.items():
            if days.get(day) != label:
                conn.execute("DELETE FROM holidays WHERE date=? AND label=?", (day, label))
        for day, label in days.items():
            existing = conn.execute("SELECT label FROM holidays WHERE date=?", (day,)).fetchone()
            if existing is None:
                conn.execute("INSERT INTO holidays(date,label) VALUES (?,?)", (day, label))
                owned[day] = label
                added += 1
            else:
                kept += 1
                if previous.get(day) == existing["label"] == label:
                    owned[day] = label
        payload = json.dumps({"rows": rows, "reviewed": True, "owned": owned}, ensure_ascii=False)
        conn.execute("INSERT INTO app_preferences(key,value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (CALENDAR_KEY, payload))
    return added, kept
