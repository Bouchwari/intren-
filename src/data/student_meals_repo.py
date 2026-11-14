"""Distribute recorded net meals among students, with explicit corrections."""
import calendar
import json

from config.settings import GRANT_FULL, REGULAR_MEALS, RAMADAN_MEALS
from core.contact_counts import student_category, student_grant_kind
from data.database import _connection

MEALS = [*REGULAR_MEALS, *RAMADAN_MEALS]


def _key(month):
    return f'student_meals:{month}'


def _student_cycle(student):
    codes = {'1A': 'primary', '2A': 'collegial', '3A': 'qualifying', '4A': 'qualifying'}
    return student_category(student) or codes.get(student.cycle, 'collegial')


def student_meal_totals(students, counts):
    totals = {f'{lot}_{meal}': 0 for lot in ('lot901', 'lot902') for meal in MEALS}
    for student in students:
        lot = 'lot902' if _student_cycle(student) == 'qualifying' else 'lot901'
        for meal in MEALS:
            totals[f'{lot}_{meal}'] += counts[student.id][meal]
    return totals


def monthly_meal_comparison(month, students, counts):
    from data.monthly_repo import get_daily_meals_by_lot_for_month
    detailed = student_meal_totals(students, counts)
    daily = get_daily_meals_by_lot_for_month(month)
    return {key: (value, sum(day[key] for day in daily))
            for key, value in detailed.items()}


def monthly_student_meals(month, students, *, use_saved=True):
    year, number = map(int, month.split('-'))
    calendar.monthrange(year, number)
    with _connection() as conn:
        contacts = conn.execute(
            'SELECT * FROM daily_contact WHERE date LIKE ? AND date NOT IN '
            '(SELECT date FROM holidays)', (month + '-%',)).fetchall()
        absences = conn.execute('SELECT * FROM daily_absence WHERE date LIKE ?',
                                (month + '-%',)).fetchall()
        saved = conn.execute('SELECT value FROM app_preferences WHERE key=?',
                             (_key(month),)).fetchone()
    overrides = json.loads(saved['value']) if saved and use_saved else {}
    missed = {(row['date'], row['meal_type']): row for row in absences}
    result = {student.id: {meal: 0 for meal in MEALS} for student in students}
    groups = {}
    for student in students:
        if student.is_monitor:
            columns = ['monitors'] if student_grant_kind(student) == GRANT_FULL else ['monitors_complement']
        else:
            cycle = _student_cycle(student)
            columns = [cycle + '_complement']
            if student_grant_kind(student) == GRANT_FULL:
                columns = [cycle + '_granted']
                if cycle != 'primary':
                    columns.append(cycle + '_paying')
        groups.setdefault(tuple(columns), []).append(student)
    for columns, people in groups.items():
        people = sorted(people, key=lambda student: student.id)
        for meal in MEALS:
            days = [row for row in contacts if row['meal_type'] == meal]
            total = 0
            for row in days:
                absent = missed.get((row['date'], meal))
                total += sum(max(0, row[col] - (absent[col] if absent else 0))
                             for col in columns)
            base, remainder = divmod(total, len(people))
            # A person can receive at most one of each meal per recorded day.
            for index, student in enumerate(people):
                result[student.id][meal] = min(len(days), base + (index < remainder))
    for student in students:
        result[student.id].update(overrides.get(str(student.id), {}))
    return result


def save_student_meal_changes(changes, *, reset_months=()):
    """Merge edited cells only so later service records still update suggestions."""
    with _connection() as conn:
        for month, students in changes.items():
            maximum = calendar.monthrange(*map(int, month.split('-')))[1]
            saved = conn.execute('SELECT value FROM app_preferences WHERE key=?',
                                 (_key(month),)).fetchone()
            payload = json.loads(saved['value']) if saved and month not in reset_months else {}
            for student_id, meals in students.items():
                target = payload.setdefault(str(student_id), {})
                for meal, value in meals.items():
                    if meal not in MEALS or type(value) is not int or not 0 <= value <= maximum:
                        raise ValueError('Invalid student meal count')
                    target[meal] = value
            conn.execute('INSERT INTO app_preferences(key,value) VALUES (?,?) '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (_key(month), json.dumps(payload)))


def period_student_meals(months, students):
    totals = {s.id: {m: 0 for m in MEALS} for s in students}
    for year, month in months:
        for student_id, meals in monthly_student_meals(f'{year:04d}-{month:02d}', students).items():
            for meal, value in meals.items():
                totals[student_id][meal] += value
    return totals
