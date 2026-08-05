"""
scripts/seed_test_db.py
Fills whatever database is currently configured (config.settings.DB_PATH)
with clearly-fake sample data — a fictional school, students, a few days
of contact/absence/report data, and a holiday — so run_test.sh has
something to explore. Never touches real data: run_test.sh always points
this at a separate matama_test.db, never at the real matama.db.

Safe to re-run: skips seeding if the database already has a school name
saved, so it won't duplicate data on a second launch.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_ROOT_DIR = _SRC_DIR.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_ROOT_DIR))

from config.settings import MEAL_FTOUR, MEAL_GHADA
from core.models import DailyAbsence, DailyContact, Holiday, SchoolSettings, Student
from data import database

_FAKE_STUDENTS = [
    ("تلميذ تجريبي الأول", "الأولى إعدادي"),
    ("تلميذة تجريبية الثانية", "الثانية إعدادي"),
    ("تلميذ تجريبي الثالث", "الجذع المشترك"),
    ("تلميذة تجريبية الرابعة", "الأولى بكالوريا"),
]


def seed() -> None:
    database.init_database()

    if database.get_school_settings() is not None:
        print(f"Test database already seeded: {database.DB_PATH}")
        return

    database.save_school_settings(SchoolSettings(
        school_name="مدرسة تجريبية للاختبار",
        school_year="2025-2026",
        director="مدير تجريبي",
        city="مدينة تجريبية",
        gestionnaire="مسير تجريبي",
    ))

    for full_name, student_class in _FAKE_STUDENTS:
        database.add_student(Student(
            full_name=full_name, student_class=student_class,
            section="cantine", grant_type="full",
        ))

    today = date.today()
    for offset in (2, 1, 0):
        day = (today - timedelta(days=offset)).isoformat()
        database.save_daily_contact(DailyContact(
            date=day, meal_type=MEAL_GHADA, collegial_granted=12, qualifying_granted=8, monitors=2,
        ))
        database.save_daily_contact(DailyContact(
            date=day, meal_type=MEAL_FTOUR, collegial_granted=10, qualifying_granted=6, monitors=2,
        ))
        database.save_daily_absence(DailyAbsence(
            date=day, meal_type=MEAL_GHADA, collegial_granted=2, qualifying_granted=1,
        ))

    database.add_holiday(Holiday(date=(today + timedelta(days=5)).isoformat(), label="عطلة تجريبية"))

    print(f"Seeded fake test data into: {database.DB_PATH}")


if __name__ == "__main__":
    seed()
