"""
src/core/stats_service.py
Business logic for the home dashboard.
Fetches from stats_repository and returns one DashboardData object.
No PySide6 here.
"""

from dataclasses import dataclass
from datetime import date

from config.settings import ARABIC_DAY_NAMES, ARABIC_MONTHS
from data.stats_repository import (
    DailyTotal,
    MonthSummary,
    StudentStats,
    WeeklyMealDay,
    fetch_cycle_breakdown,
    fetch_last_30_days,
    fetch_last_7_days,
    fetch_last_log_date,
    fetch_month_summary,
    fetch_student_stats,
)


@dataclass
class DashboardData:
    students:        StudentStats
    month:           MonthSummary
    weekly:          list
    trend:           list
    last_log_date:   str | None
    month_label:     str
    today_label:     str
    school_name:     str
    cycle_breakdown: list


def load_dashboard() -> DashboardData:
    from data.database import get_school_settings
    today    = date.today()
    settings = get_school_settings()
    school_name = settings.school_name if settings else ""

    month_label = f"{ARABIC_MONTHS[today.month]} {today.year}"
    today_label = (
        f"{ARABIC_DAY_NAMES[today.weekday()]}  "
        f"{today.day} "
        f"{ARABIC_MONTHS[today.month]} "
        f"{today.year}"
    )

    return DashboardData(
        students        = fetch_student_stats(),
        month           = fetch_month_summary(today.year, today.month),
        weekly          = fetch_last_7_days(),
        trend           = fetch_last_30_days(),
        last_log_date   = fetch_last_log_date(),
        month_label     = month_label,
        today_label     = today_label,
        school_name     = school_name,
        cycle_breakdown = fetch_cycle_breakdown(),
    )
