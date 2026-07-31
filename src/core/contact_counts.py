"""Counting rules for the daily contact sheet — moved out of
src/ui/daily_contact_screen.py so the numbers can be unit tested.

The logic below is copied exactly from the screen. It is not simplified or
fixed in this step; only relocated.
"""
from core.models import Student

CATEGORY_PRIMARY = "primary"
CATEGORY_COLLEGIAL = "collegial"
CATEGORY_QUALIFYING = "qualifying"
CATEGORY_MONITORS = "monitors"

GRANT_FULL = "full"
GRANT_LUNCH = "lunch"

# The Arabic literals below match text stored in imported spreadsheet data
# (class names, grant types) — they are not shown to the user, so they stay
# here rather than in ui/.


def student_category(student: Student) -> str | None:
    if getattr(student, "is_monitor", False):
        return CATEGORY_MONITORS
    level_text = " ".join(
        str(value or "")
        for value in (
            getattr(student, "student_class", ""),
            getattr(student, "cycle", ""),
            getattr(student, "education_type", ""),
        )
    )
    normalized = (
        level_text
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
    )
    if "ابتدائي" in normalized:
        return CATEGORY_PRIMARY
    if "اعدادي" in normalized:
        return CATEGORY_COLLEGIAL
    if "تاهيلي" in normalized:
        return CATEGORY_QUALIFYING
    return None


def student_grant_kind(student: Student) -> str | None:
    grant_type = str(getattr(student, "grant_type", "") or "").strip()
    grant_number = str(getattr(student, "grant_number", "") or "").strip()
    grant_text = f"{grant_type} {grant_number}".strip()
    normalized = (
        grant_text
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
    )
    if grant_type == "full" or "منحه كامله" in normalized or "كاملة" in grant_text:
        return GRANT_FULL
    if grant_type in {"half", "lunch", "meal", "ghada"} or "وجبه غذاء" in normalized or "غداء" in grant_text:
        return GRANT_LUNCH
    return None


def empty_counts() -> dict[str, dict[str, int]]:
    return {
        "primary": {"full": 0, "lunch": 0},
        "collegial": {"full": 0, "lunch": 0},
        "qualifying": {"full": 0, "lunch": 0},
        "monitors": {"full": 0, "lunch": 0},
    }


def count_students(students: list[Student]) -> dict[str, dict[str, int]]:
    counts = empty_counts()
    for student in students:
        category = student_category(student)
        grant_kind = student_grant_kind(student)
        if not category or not grant_kind:
            continue
        counts[category][grant_kind] += 1
    return counts
