"""
scripts/seed_test_db.py
Fills whatever database is currently configured (config.settings.DB_PATH)
with a COMPLETE set of clearly-fake sample data, so the whole app can be
explored without touching real school data: a fictional school with every
settings field filled in, a full student roster, weekly meal programs
(normal + Ramadan), holidays, and roughly seven months of daily
contact/absence/report/order-letter/reception data — including a real
Ramadan stretch — plus monthly reception records and one infraction PV.

Run it through run_test.sh, which points MATAMA_DB_PATH at a separate
matama_test.db. This script REFUSES to run against the real matama.db.

Safe to re-run: it skips seeding if the database already has a school name
saved. Pass --force to wipe the test database and rebuild it from scratch.

Everything is generated from a FIXED random seed, so the same command always
produces the same database — a number that looks wrong can be reproduced.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_ROOT_DIR = _SRC_DIR.parent
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_ROOT_DIR))

from config.settings import (
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR,
)
from core.models import (
    DailyAbsence, DailyContact, DailyReceptionRecord, DailyReport, Holiday,
    InfractionRecord, MealEntry, MonthlyReceptionRecord, OrderItem, OrderLetter,
    DishNutrition, FoodProduct, MealComponent, MealFeedback,
    SchoolSettings, StaffMember, Student, WeekFeedback,
)
from core.ramadan import meals_for_date
from data import database

# ── The fictional school ──────────────────────────────────────────────────────
_REAL_DB_NAME = "matama.db"
_SEED = 20260828          # fixed, so every run produces the same database

_SCHOOL_YEAR = "2025-2026"
# Data window and the Ramadan stretch inside it. Ramadan sits in Feb-Mar so
# the Jan-Mar quarter exercises الوثائق الفصلية's FTOUR/SHOUR blocks while
# Apr-Jun stays an ordinary quarter.
_DATA_START = date(2026, 2, 2)
_RAMADAN_START = date(2026, 2, 17)
_RAMADAN_END = date(2026, 3, 18)

_CYCLES: List[Tuple[str, str, int]] = [
    # (cycle label, class label, how many students)
    ("ابتدائي", "السادس ابتدائي", 18),
    ("إعدادي", "الأولى إعدادي", 26),
    ("إعدادي", "الثانية إعدادي", 24),
    ("إعدادي", "الثالثة إعدادي", 22),
    ("تأهيلي", "الجذع المشترك", 20),
    ("تأهيلي", "الأولى بكالوريا", 18),
    ("تأهيلي", "الثانية بكالوريا", 14),
]
_MONITOR_COUNT = 6

_FIRST_NAMES_M = [
    "محمد", "أحمد", "يوسف", "عبد الله", "إبراهيم", "حمزة", "أيوب", "مهدي",
    "رضا", "أنس", "بلال", "زكرياء", "ياسين", "عثمان", "خالد", "سفيان",
]
_FIRST_NAMES_F = [
    "فاطمة", "مريم", "خديجة", "عائشة", "سلمى", "زينب", "هاجر", "أسماء",
    "نورة", "إيمان", "سارة", "ليلى", "أمينة", "حنان", "سناء", "رقية",
]
_LAST_NAMES = [
    "العلوي", "بنعيسى", "الإدريسي", "أوبيهي", "الفاسي", "بوعزة", "الرامي",
    "أيت الحاج", "الصقلي", "بنكيران", "المرابط", "الزهراوي", "أمزيل",
    "الحسني", "بومهدي", "الطاهري",
]

_MENUS = {
    MEAL_FTOUR: ["خبز وزبدة وشاي", "حليب وخبز وعسل", "قهوة بالحليب وخبز", "شاي وخبز وجبن"],
    MEAL_GHADA: ["طاجين لحم بالخضر", "كسكس بالخضر", "دجاج محمر وأرز", "عدس وخبز", "سمك وأرز"],
    MEAL_ASHA:  ["حريرة وخبز", "شوربة خضر", "بيض وخبز وشاي", "مكرونة بالصلصة"],
    MEAL_IFTAR: ["حريرة وتمر وشباكية", "حريرة وبيض وعصير", "شوربة وتمر وحلوى"],
    MEAL_SHOUR: ["حليب وخبز وتمر", "شاي وخبز وزبدة", "عصير وخبز وجبن"],
}

_HOLIDAY_LABELS = [
    (date(2026, 3, 20), "عيد الفطر"),
    (date(2026, 3, 23), "عيد الفطر"),
    (date(2026, 5, 1),  "عيد الشغل"),
    (date(2026, 7, 30), "عيد العرش"),
]

_DAY_NAMES = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# Roughly how much of each category shows up, as a fraction of the roster.
_ATTENDANCE_RANGE = (0.86, 0.98)
_ABSENCE_RANGE = (0.01, 0.06)


def _guard_against_the_real_database() -> None:
    if database.DB_PATH.name == _REAL_DB_NAME:
        raise SystemExit(
            f"refusing to seed the real database ({database.DB_PATH}).\n"
            "Run scripts/seed_test_db.py through run_test.sh, which points\n"
            "MATAMA_DB_PATH at a separate matama_test.db."
        )


def _build_students(rng: random.Random) -> List[Student]:
    """A roster with both grant types, both sections and a few monitors."""
    students: List[Student] = []
    used: set = set()

    def unique_name(female: bool) -> str:
        pool = _FIRST_NAMES_F if female else _FIRST_NAMES_M
        for _ in range(200):
            name = f"{rng.choice(pool)} {rng.choice(_LAST_NAMES)}"
            if name not in used:
                used.add(name)
                return name
        return f"{rng.choice(pool)} {rng.choice(_LAST_NAMES)} {len(used)}"

    massar = 1000
    for cycle, student_class, count in _CYCLES:
        for _ in range(count):
            female = rng.random() < 0.5
            massar += 1
            # Primary pupils are lunch-only far more often; the older cycles
            # are mostly full boarders.
            full_grant = rng.random() < (0.35 if cycle == "ابتدائي" else 0.75)
            # A plausible age for the cycle, so the report's age chart has
            # something real to show.
            base_age = {"ابتدائي": 11, "إعدادي": 13, "تأهيلي": 16}[cycle]
            born = date.today().replace(
                year=date.today().year - base_age - rng.randint(0, 2))
            students.append(Student(
                full_name=unique_name(female),
                massar_number=f"J{massar}",
                gender="female" if female else "male",
                cycle=cycle,
                student_class=student_class,
                birth_date=born.isoformat(),
                grant_number=f"{massar}",
                section="internat" if full_grant else "cantine",
                grant_type="full" if full_grant else "half",
            ))

    for index in range(_MONITOR_COUNT):
        massar += 1
        students.append(Student(
            full_name=unique_name(index % 2 == 0),
            massar_number=f"J{massar}",
            gender="female" if index % 2 == 0 else "male",
            cycle="إعدادي",
            student_class="معلمو الداخلية",
            section="internat",
            grant_type="full",
            is_monitor=True,
        ))
    return students


def _seed_meal_programs() -> None:
    normal_id = database.create_program("البرنامج الأسبوعي العادي", _SCHOOL_YEAR, False)
    entries: List[MealEntry] = []
    for day in range(7):
        for meal in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA):
            entries.append(MealEntry(
                program_id=normal_id, day_of_week=day, meal_type=meal,
                menu_text=_MENUS[meal][day % len(_MENUS[meal])],
            ))
    database.save_program_entries(normal_id, entries)

    ramadan_id = database.create_program("البرنامج الأسبوعي — رمضان", _SCHOOL_YEAR, True)
    database.set_program_ramadan_mode(ramadan_id, True)
    ramadan_entries: List[MealEntry] = []
    for day in range(7):
        for meal in (MEAL_IFTAR, MEAL_SHOUR):
            ramadan_entries.append(MealEntry(
                program_id=ramadan_id, day_of_week=day, meal_type=meal,
                menu_text=_MENUS[meal][day % len(_MENUS[meal])],
            ))
    database.save_program_entries(ramadan_id, ramadan_entries)


def _roster_by_category() -> Dict[str, Dict[str, int]]:
    from core.contact_counts import count_students
    return count_students(database.get_all_students())


def _meal_counts(
    roster: Dict[str, Dict[str, int]], meal: str, rng: random.Random,
) -> Dict[str, Dict[str, int]]:
    """How many of each category turn up for one meal.

    Mirrors the app's own rule: only غداء and إفطار serve the وجبة غذاء
    (lunch-only) students — فطور / عشاء / سحور are for full boarders.
    """
    serves_lunch_only = meal in (MEAL_GHADA, MEAL_IFTAR)
    counts: Dict[str, Dict[str, int]] = {}
    for category, grants in roster.items():
        bucket: Dict[str, int] = {}
        for grant_kind, total in grants.items():
            if total <= 0:
                bucket[grant_kind] = 0
                continue
            if grant_kind == "lunch" and not serves_lunch_only:
                bucket[grant_kind] = 0
                continue
            bucket[grant_kind] = max(0, round(total * rng.uniform(*_ATTENDANCE_RANGE)))
        counts[category] = bucket
    return counts


def _absent_counts(
    present: Dict[str, Dict[str, int]], rng: random.Random,
) -> Dict[str, Dict[str, int]]:
    return {
        category: {
            grant_kind: min(value, round(value * rng.uniform(*_ABSENCE_RANGE)))
            for grant_kind, value in grants.items()
        }
        for category, grants in present.items()
    }


def _row(model, date_str: str, meal: str, counts: Dict[str, Dict[str, int]]):
    """Build a DailyContact/DailyAbsence from per-category counts."""
    primary = counts.get("primary", {})
    collegial = counts.get("collegial", {})
    qualifying = counts.get("qualifying", {})
    monitors = counts.get("monitors", {})
    return model(
        date=date_str, meal_type=meal,
        primary_granted=primary.get("full", 0),
        primary_complement=primary.get("lunch", 0),
        collegial_granted=collegial.get("full", 0),
        collegial_complement=collegial.get("lunch", 0),
        qualifying_granted=qualifying.get("full", 0),
        qualifying_complement=qualifying.get("lunch", 0),
        monitors=monitors.get("full", 0),
        monitors_complement=monitors.get("lunch", 0),
    )


def _seed_daily_data(rng: random.Random, settings: SchoolSettings) -> Dict[str, Dict[str, int]]:
    """Contact + absence + report + order letter + reception, day by day.

    Returns per-month reception totals so the monthly محاضر can be built
    from exactly the same numbers.
    """
    roster = _roster_by_category()
    holidays = {holiday.isoformat() for holiday, _ in _HOLIDAY_LABELS}
    overrides = database.get_ramadan_overrides()
    monthly: Dict[str, Dict[str, int]] = {}

    today = date.today()
    day = _DATA_START
    letter_number = 0
    while day <= today:
        date_str = day.isoformat()
        # Weekends and holidays serve nothing.
        if day.weekday() >= 5 or date_str in holidays:
            day += timedelta(days=1)
            continue

        meals = meals_for_date(date_str, settings, overrides)
        report_fields: Dict[str, int] = {}
        order_items: List[OrderItem] = []
        reception: Dict[str, int] = {}

        for meal in meals:
            present = _meal_counts(roster, meal, rng)
            absent = _absent_counts(present, rng)
            contact = _row(DailyContact, date_str, meal, present)
            absence = _row(DailyAbsence, date_str, meal, absent)
            database.save_daily_contact(contact)
            database.save_daily_absence(absence)

            expected = contact.grand_total
            missing = absence.grand_total
            report_fields[f"{meal}_expected"] = expected
            report_fields[f"{meal}_present"] = max(0, expected - missing)
            reception[meal] = max(0, expected - missing)

            order_items.append(OrderItem(
                letter_id=0, meal_type=meal,
                primary=contact.primary_total,
                collegial=contact.collegial_total,
                qualifying=contact.qualifying_total,
                monitors=contact.monitors_total,
            ))

        # التقرير اليومي — hygiene/quality ratings mostly good, occasionally
        # average, so the screen has something other than one flat value.
        ratings = {
            field: rng.choices([2, 1, 0], weights=[75, 20, 5])[0]
            for field in (
                "hygiene_staff", "hygiene_utensils", "hygiene_dining_hall",
                "hygiene_kitchen", "hygiene_storage", "hygiene_waste",
                "hygiene_dorms", "quality_supplies", "quality_storage",
                "quality_program", "quality_quantities", "quality_sample_kept",
                "quality_prep", "quality_serving", "building_condition",
                "equipment_condition",
            )
        }
        database.save_daily_report(DailyReport(
            date=date_str,
            notes=f"يوم {_DAY_NAMES[day.weekday()]} — بيانات تجريبية.",
            **report_fields, **ratings,
        ))

        letter_number += 1
        database.save_order_letter(
            OrderLetter(letter_date=date_str, period_start=date_str,
                        period_end=date_str, document_number=letter_number),
            order_items,
        )

        database.save_daily_reception_record(DailyReceptionRecord(
            date=date_str,
            ftour_qty=reception.get(MEAL_FTOUR, 0),
            ghada_qty=reception.get(MEAL_GHADA, 0),
            asha_qty=reception.get(MEAL_ASHA, 0),
            ftour_ramadan_qty=reception.get(MEAL_IFTAR, 0),
            shour_qty=reception.get(MEAL_SHOUR, 0),
        ))

        month_key = date_str[:7]
        bucket = monthly.setdefault(month_key, {})
        for meal, value in reception.items():
            bucket[meal] = bucket.get(meal, 0) + value

        day += timedelta(days=1)
    return monthly


def _seed_monthly_records(monthly: Dict[str, Dict[str, int]]) -> None:
    for month_key, totals in sorted(monthly.items()):
        database.save_monthly_reception_record(MonthlyReceptionRecord(
            month=month_key,
            ftour_qty=totals.get(MEAL_FTOUR, 0),
            ghada_qty=totals.get(MEAL_GHADA, 0),
            asha_qty=totals.get(MEAL_ASHA, 0),
            ftour_ramadan_qty=totals.get(MEAL_IFTAR, 0),
            shour_qty=totals.get(MEAL_SHOUR, 0),
            remarks="محضر شهري تجريبي.",
        ))


# Nutrition values for MOST of the demo menu lines. A few are deliberately
# left out so التحليل الغذائي's "غير محدد" path is visible without having to
# break something first.
_DISH_NUTRITION = [
    ("خبز وزبدة وشاي", 320, 8, 46, 11),
    ("حليب وخبز وعسل", 380, 12, 58, 9),
    ("قهوة بالحليب وخبز", 300, 9, 44, 8),
    ("طاجين لحم بالخضر", 620, 34, 52, 26),
    ("كسكس بالخضر", 540, 18, 82, 14),
    ("دجاج محمر وأرز", 610, 36, 66, 18),
    ("عدس وخبز", 430, 22, 68, 6),
    ("حريرة وخبز", 350, 14, 52, 9),
    ("شوربة خضر", 210, 7, 32, 5),
    ("حريرة وتمر وشباكية", 520, 13, 84, 15),
    ("حليب وخبز وتمر", 400, 13, 62, 9),
]


# A small product library plus recipes for a few dishes, so the component
# workflow and the التوزيع الكمي export both have real data. The remaining
# dishes keep only their whole-line values, and a few have neither — that mix
# is deliberate: it shows all three states the screen can report.
_PRODUCTS = [
    ("لحم بقري", "100g", 250, 26, 0, 15),
    ("دجاج", "100g", 165, 31, 0, 4),
    ("سمك", "100g", 140, 22, 0, 5),
    ("أرز", "100g", 130, 3, 28, 0),
    ("خضر مشكلة", "100g", 40, 2, 8, 0),
    ("عدس", "100g", 115, 9, 20, 0),
    ("خبز", "unit", 250, 8, 48, 2),
    ("زيت الزيتون", "100ml", 884, 0, 0, 100),
    ("حليب", "100ml", 61, 3, 5, 3),
    ("تمر", "100g", 282, 2, 75, 0),
]
_RECIPES = {
    "طاجين لحم بالخضر": [("لحم بقري", 80), ("خضر مشكلة", 150), ("زيت الزيتون", 10)],
    "دجاج محمر وأرز": [("دجاج", 90), ("أرز", 120), ("زيت الزيتون", 8)],
    "عدس وخبز": [("عدس", 90), ("خبز", 1), ("زيت الزيتون", 5)],
    "حليب وخبز وعسل": [("حليب", 200), ("خبز", 1)],
}


def _seed_food_products() -> None:
    ids = {}
    for name, basis, calories, protein, carbs, fats in _PRODUCTS:
        ids[name] = database.save_food_product(FoodProduct(
            name=name, unit_basis=basis, calories=calories,
            protein=protein, carbs=carbs, fats=fats))
    for dish, components in _RECIPES.items():
        for product_name, quantity in components:
            database.save_meal_component(MealComponent(
                dish_name=dish, product_id=ids[product_name], quantity=quantity))


def _seed_dish_nutrition() -> None:
    for name, calories, protein, carbs, fats in _DISH_NUTRITION:
        database.save_dish_nutrition(DishNutrition(
            dish_name=name, calories=calories, protein=protein,
            carbs=carbs, fats=fats))


def _seed_feedback(rng: random.Random) -> None:
    """Ratings across recent weekdays, weighted so some dishes clearly do
    better than others and the ranking panels have something real to show."""
    liked = {"كسكس بالخضر": (4, 5), "دجاج محمر وأرز": (4, 5),
             "طاجين لحم بالخضر": (3, 5)}
    disliked = {"عدس وخبز": (1, 3), "شوربة خضر": (2, 3)}
    recorders = ["الحارس العام للداخلية", "مسير المصالح المادية والمالية"]

    day = date.today() - timedelta(days=30)
    while day <= date.today():
        if day.weekday() >= 5:
            day += timedelta(days=1)
            continue
        for meal in (MEAL_GHADA, MEAL_ASHA):
            dish = _MENUS[meal][day.day % len(_MENUS[meal])]
            low, high = liked.get(dish, disliked.get(dish, (3, 5)))
            # A distribution, not one opinion: roughly 90 pupils express a
            # view, clustered around the dish's own standing.
            responses = rng.randint(70, 110)
            weights = {5: 1, 4: 1, 3: 1, 2: 1, 1: 1}
            for level in (5, 4, 3, 2, 1):
                weights[level] = 6 if low <= level <= high else 1
            counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
            for _ in range(responses):
                level = rng.choices(list(weights), weights=list(weights.values()))[0]
                counts[level] += 1
            database.save_feedback(MealFeedback(
                date=day.isoformat(), meal_type=meal, dish=dish,
                count_excellent=counts[5], count_good=counts[4],
                count_average=counts[3], count_poor=counts[2],
                count_bad=counts[1],
                note="" if rng.random() < 0.7 else "ملاحظة تجريبية من التلاميذ.",
                recorded_by=rng.choice(recorders),
            ))
        day += timedelta(days=1)


def _seed_week_feedback(rng: random.Random) -> None:
    """Ratings for the last few WEEKS' menus — the current shape. The older
    per-day rows above are kept on purpose so the legacy section has content."""
    from core.feedback import CYCLES, GENDERS, week_start_of
    from ui.feedback_collect import dishes_for_week

    liked = {"كسكس بالخضر": (4, 5), "دجاج محمر وأرز": (4, 5),
             "طاجين لحم بالخضر": (3, 5)}
    disliked = {"عدس وخبز": (1, 3), "شوربة خضر": (2, 3)}
    recorder = "الحارس العام للداخلية"

    # A real difference of taste between the groups, so the report's patterns
    # page has something true to find instead of six identical bars: the
    # youngest pupils dislike عدس and love كسكس, the oldest are the reverse.
    by_cycle = {"primary": {"عدس وخبز": -2, "كسكس بالخضر": +1},
                "collegial": {"عدس وخبز": -1},
                "qualifying": {"عدس وخبز": +1, "كسكس بالخضر": -1}}

    for weeks_back in range(1, 5):
        monday = week_start_of(
            (date.today() - timedelta(days=7 * weeks_back)).isoformat())
        for dish in dishes_for_week(monday):
            low, high = liked.get(dish, disliked.get(dish, (3, 5)))
            for cycle in CYCLES:
                for gender in GENDERS:
                    shift = by_cycle.get(cycle, {}).get(dish, 0)
                    shift += 1 if gender == "female" else 0
                    counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
                    weights = {
                        level: (6 if low + shift <= level <= high + shift
                                else 1)
                        for level in (5, 4, 3, 2, 1)}
                    for _ in range(rng.randint(14, 26)):
                        level = rng.choices(
                            list(weights), weights=list(weights.values()))[0]
                        counts[level] += 1
                    database.save_week_feedback(WeekFeedback(
                        week_start=monday, dish=dish,
                        cycle=cycle, gender=gender,
                        count_excellent=counts[5], count_good=counts[4],
                        count_average=counts[3], count_poor=counts[2],
                        count_bad=counts[1], recorded_by=recorder))


def _seed_staff() -> None:
    """A kitchen team covering every certificate state, so the expiry
    warnings on طاقم المطبخ actually have something to show."""
    today = date.today()
    team = [
        ("مصطفى بوعزة", "رئيس الطباخين", "صباحي", "0661234501", 210, "حاضر"),
        ("خديجة الرامي", "مساعد طباخ", "صباحي", "0661234502", 45, "حاضر"),
        ("عبد الله أمزيل", "مساعد طباخ", "مسائي", "0661234503", 12, "حاضر"),
        ("سناء الحسني", "عامل نظافة", "تناوب", "0661234504", -20, "غائب"),
        ("يوسف بومهدي", "حارس المخزن", "صباحي", "0661234505", None, "في عطلة"),
        ("أمينة الطاهري", "نادل", "مسائي", "0661234506", 120, "حاضر"),
    ]
    for name, role, shift, phone, offset, status in team:
        expiry = "" if offset is None else (today + timedelta(days=offset)).isoformat()
        database.save_staff_member(StaffMember(
            full_name=name, role=role, shift=shift, phone=phone,
            health_cert_expiry=expiry, status=status,
        ))


def _seed_infractions() -> None:
    database.save_infraction(InfractionRecord(
        date="2026-04-14", document_number=1, year=2026, meal_type=MEAL_GHADA,
        place="المطبخ", infraction_type="عدم احترام شروط النظافة",
        description="لوحظ عدم ارتداء المستخدمين للقفازات أثناء تحضير الوجبة.",
        reported_by="الحارس العام للداخلية", written_date="2026-04-14",
    ))
    database.save_infraction(InfractionRecord(
        date="2026-05-21", document_number=2, year=2026, meal_type=MEAL_ASHA,
        place="المطعم", infraction_type="تأخر في تقديم الوجبة",
        description="قُدمت وجبة العشاء متأخرة بأزيد من أربعين دقيقة عن التوقيت المحدد.",
        reported_by="مسير المصالح المادية والمالية", written_date="2026-05-21",
    ))


def seed() -> None:
    _guard_against_the_real_database()
    database.init_database()

    if database.get_school_settings() is not None:
        print(f"Test database already seeded: {database.DB_PATH}")
        print("Pass --force to wipe it and rebuild from scratch.")
        return

    rng = random.Random(_SEED)

    settings = SchoolSettings(
        school_name="الثانوية الإعدادية النموذجية التجريبية",
        school_name_fr="College Modele (donnees de test)",
        school_year=_SCHOOL_YEAR,
        director="سعيد بنعيسى",
        gestionnaire="نادية العلوي",
        aref="جهة درعة تافيلالت",
        direction_provinciale="المديرية الإقليمية تنغير",
        city="مدينة تجريبية",
        city_fr="Ville de test",
        academy="جهة درعة تافيلالت",
        contract_number="07/2026",
        company_name="SOCIETE TEST RESTAURATION SARL",
        supplier_address="الحي الإداري، مدينة تجريبية",
        price_ftour="6.00",
        price_ghada="14.00",
        price_asha="8.00",
        price_ftour_ramadan="12.00",
        price_asha_ramadan="9.00",
        price_shour="7.00",
        ramadan_start=_RAMADAN_START.isoformat(),
        ramadan_end=_RAMADAN_END.isoformat(),
    )
    database.save_school_settings(settings)
    database.save_level_preferences(
        ["ابتدائي", "إعدادي", "تأهيلي"], ["التعليم العمومي"],
    )

    students = _build_students(rng)
    database.add_students_bulk(students)

    _seed_meal_programs()

    for holiday_date, label in _HOLIDAY_LABELS:
        database.add_holiday(Holiday(date=holiday_date.isoformat(), label=label))

    monthly = _seed_daily_data(rng, settings)
    _seed_monthly_records(monthly)
    _seed_food_products()
    _seed_dish_nutrition()
    _seed_feedback(rng)
    _seed_week_feedback(rng)
    _seed_staff()
    _seed_infractions()

    print(f"Seeded a full fake school into: {database.DB_PATH}")
    print(f"  students            {len(students)}")
    print(f"  months of daily data {len(monthly)} ({', '.join(sorted(monthly))})")
    print(f"  Ramadan             {_RAMADAN_START} → {_RAMADAN_END}")


def _force_reset() -> None:
    _guard_against_the_real_database()
    if database.DB_PATH.exists():
        database.DB_PATH.unlink()
        print(f"Deleted {database.DB_PATH}")


if __name__ == "__main__":
    if "--force" in sys.argv:
        _force_reset()
    seed()
