"""Reviewed transcription of the user's 2026/2027 calendar, not an OCR engine."""
from datetime import date, timedelta

CALENDAR_YEAR = "2026/2027"
CALENDAR_KEY = "holiday_calendar_2026_2027"
# Both endpoints are included, as stated on the supplied source image.
_PERIODS = (
    ("break1", "الفترة البينية الأولى", "2026-10-18", "2026-10-25", ""),
    ("unity", "عيد الوحدة", "2026-10-31", "2026-10-31", ""),
    ("march", "ذكرى المسيرة الخضراء", "2026-11-06", "2026-11-06", ""),
    ("independence", "عيد الاستقلال", "2026-11-18", "2026-11-18", ""),
    ("break2", "الفترة البينية الثانية", "2026-12-06", "2026-12-13", ""),
    ("newyear", "فاتح السنة الميلادية", "2027-01-01", "2027-01-01", ""),
    ("manifesto", "ذكرى تقديم وثيقة الاستقلال", "2027-01-11", "2027-01-11", ""),
    ("amazigh", "فاتح السنة الأمازيغية", "2027-01-14", "2027-01-14", ""),
    ("midyear", "عطلة منتصف السنة الدراسية", "2027-01-24", "2027-01-31", ""),
    ("fitr", "عيد الفطر", "", "", "29 رمضان إلى 2 شوال 1448؛ 3 أو 4 أيام"),
    ("break3", "الفترة البينية الثالثة", "2027-03-21", "2027-03-28", ""),
    ("labour", "عيد الشغل", "2027-05-01", "2027-05-01", ""),
    ("break4", "الفترة البينية الرابعة", "2027-05-09", "2027-05-16", ""),
    ("adha", "عيد الأضحى", "", "", "9 إلى 11 ذي الحجة 1448؛ 3 أيام"),
    ("muharram", "فاتح محرم", "", "", "1 محرم 1449؛ يوم واحد"),
)


def default_calendar_rows() -> list[dict]:
    return [dict(key=key, label=label, start=start, end=end, hijri=hijri, enabled=bool(start))
            for key, label, start, end, hijri in _PERIODS]


def validate_calendar_rows(rows: list[dict]) -> list[dict]:
    expected = {row[0] for row in _PERIODS}
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError("لائحة العطل غير مكتملة.")
    if any(not isinstance(row, dict) for row in rows) or {row.get("key") for row in rows} != expected:
        raise ValueError("لائحة العطل غير صحيحة.")
    result = []
    for original in default_calendar_rows():
        row = next(row for row in rows if row["key"] == original["key"])
        start, end, enabled = row.get("start", ""), row.get("end", ""), row.get("enabled")
        if not isinstance(start, str) or not isinstance(end, str) or type(enabled) is not bool:
            raise ValueError("صيغة التاريخ غير صحيحة.")
        if start or end or enabled:
            try:
                first, last = date.fromisoformat(start), date.fromisoformat(end)
            except ValueError:
                raise ValueError(f"{original['label']}: أدخل تاريخ البداية والنهاية بصيغة YYYY-MM-DD.") from None
            if (first.isoformat() != start or last.isoformat() != end
                    or not date(2026, 9, 1) <= first <= last <= date(2027, 8, 31)):
                raise ValueError(f"{original['label']}: اختر مدة صحيحة داخل السنة 2026/2027.")
        result.append(dict(original, start=start, end=end, enabled=enabled))
    return result


def calendar_days(rows: list[dict]) -> dict[str, str]:
    days = {}
    for row in validate_calendar_rows(rows):
        if row["enabled"]:
            first, last = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
            for offset in range((last - first).days + 1):
                day = (first + timedelta(days=offset)).isoformat()
                days[day] = f"{days[day]} / {row['label']}" if day in days else row["label"]
    return days


def pending_hijri(rows: list[dict]) -> list[str]:
    return [row["label"] for row in rows if row["hijri"] and not (row["start"] and row["end"])]
