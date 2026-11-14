import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from PySide6.QtWidgets import QApplication
from core.models import DailyContact, Holiday, Student
from data import database
from data.student_meals_repo import monthly_student_meals, period_student_meals, save_student_meal_changes
from ui.student_meals_dialog import StudentMealsDialog
from ui.expense_roster_export import write_expense_roster_excel


class StudentMealsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / 'test.db'
        database.init_database()
        self.students = [Student(id=1, full_name='Student A', cycle='2A', section='internat'),
                         Student(id=2, full_name='Student B', cycle='2A', section='internat')]
        database.save_daily_contact(DailyContact(date='2026-10-17', meal_type='ftour', collegial_granted=20))
        database.save_daily_contact(DailyContact(date='2026-10-18', meal_type='ftour', collegial_granted=20))
        database.save_daily_contact(DailyContact(date='2026-10-19', meal_type='ghada', collegial_granted=0))
        database.add_holiday(Holiday(date='2026-10-18', label='Holiday'))

    def tearDown(self):
        database.DB_PATH = self.previous
        self.temp.cleanup()

    def test_service_days_skip_holidays_zero_rows_and_other_months(self):
        values = monthly_student_meals('2026-10', self.students)
        self.assertEqual(values[1]['ftour'], 1)
        self.assertEqual(values[1]['ghada'], 0)
        self.assertEqual(monthly_student_meals('2026-11', self.students)[1]['ftour'], 0)

    def test_attestation_excludes_holiday_meals_and_daily_receipts(self):
        from core.models import DailyReceptionRecord
        from data.monthly_repo import get_daily_meals_by_lot_for_month, sum_daily_reception_for_month
        database.save_daily_reception_record(DailyReceptionRecord(
            date='2026-10-17', ftour_qty=20))
        database.save_daily_reception_record(DailyReceptionRecord(
            date='2026-10-18', ftour_qty=20))
        rows = get_daily_meals_by_lot_for_month('2026-10')
        self.assertEqual(rows[17]['lot901_ftour'], 0)
        self.assertEqual(sum(row['lot901_ftour'] for row in rows), 20)
        self.assertEqual(sum_daily_reception_for_month('2026-10')['ftour'], 20)

    def test_zero_override_survives_new_days_and_quarter_rollup(self):
        save_student_meal_changes({'2026-10': {1: {'ftour': 0}}})
        database.save_daily_contact(DailyContact(date='2026-10-20', meal_type='ftour', collegial_granted=20))
        totals = period_student_meals([(2026, 10), (2026, 11)], self.students)
        self.assertEqual(totals[1]['ftour'], 0)
        self.assertEqual(totals[2]['ftour'], 2)

    def test_comparison_reports_gap_and_matches_after_individual_correction(self):
        from data.student_meals_repo import monthly_meal_comparison
        counts = monthly_student_meals('2026-10', self.students)
        result = monthly_meal_comparison('2026-10', self.students, counts)
        self.assertEqual(result['lot901_ftour'], (2, 20))
        counts[1]['ftour'] = 10
        counts[2]['ftour'] = 10
        result = monthly_meal_comparison('2026-10', self.students, counts)
        self.assertEqual(result['lot901_ftour'], (20, 20))
        save_student_meal_changes({'2026-10': {1: {'ftour': 0}}})
        counts = monthly_student_meals('2026-10', self.students)
        self.assertEqual(monthly_meal_comparison('2026-10', self.students, counts)['lot901_ftour'],
                         (1, 20))

    def test_dialog_cancel_and_save_across_month_switches(self):
        dialog = StudentMealsDialog([(2026, 10), (2026, 11)], self.students)
        dialog.table.cellWidget(0, 2).setValue(0)
        dialog.reject()
        self.assertEqual(monthly_student_meals('2026-10', self.students)[1]['ftour'], 1)
        dialog = StudentMealsDialog([(2026, 10), (2026, 11)], self.students)
        dialog.table.cellWidget(0, 2).setValue(0)
        dialog.month.setCurrentIndex(1)
        dialog.month.setCurrentIndex(0)
        self.assertEqual(dialog.table.cellWidget(0, 2).value(), 0)
        dialog._save()
        self.assertEqual(monthly_student_meals('2026-10', self.students)[1]['ftour'], 0)

    def test_distributes_screenshot_totals_exactly_across_340_students(self):
        from data.student_meals_repo import monthly_meal_comparison
        people = [Student(id=i, full_name=f'Student {i}', cycle='2A') for i in range(1, 341)]
        targets = {'ftour': 4916, 'ghada': 5004, 'asha': 4983}
        for meal, total in targets.items():
            base, extra = divmod(total, 29)
            for day in range(1, 30):
                database.save_daily_contact(DailyContact(
                    date=f'2026-09-{day:02d}', meal_type=meal,
                    collegial_granted=base + (day <= extra)))
        counts = monthly_student_meals('2026-09', people)
        comparison = monthly_meal_comparison('2026-09', people, counts)
        for meal, total in targets.items():
            self.assertEqual(comparison[f'lot901_{meal}'], (total, total))
            values = [counts[person.id][meal] for person in people]
            self.assertLessEqual(max(values) - min(values), 1)
            self.assertLessEqual(max(values), 29)

    def test_allocation_subtracts_absences_within_each_cycle_and_grant(self):
        from core.models import DailyAbsence
        people = [Student(id=i, full_name=f'Student {i}', cycle='2A') for i in range(1, 5)]
        people.append(Student(id=5, full_name='Lunch', cycle='2A', grant_type='half'))
        people.append(Student(id=6, full_name='Qualifying', cycle='3A'))
        database.save_daily_contact(DailyContact(date='2026-11-01', meal_type='ghada',
                                               collegial_granted=4, collegial_complement=1,
                                               qualifying_granted=1))
        database.save_daily_absence(DailyAbsence(date='2026-11-01', meal_type='ghada',
                                               collegial_granted=1))
        counts = monthly_student_meals('2026-11', people)
        self.assertEqual(sum(counts[i]['ghada'] for i in range(1, 5)), 3)
        self.assertEqual(counts[5]['ghada'], 1)
        self.assertEqual(counts[6]['ghada'], 1)

    def test_redistribution_clears_only_current_month_on_approval(self):
        save_student_meal_changes({'2026-10': {1: {'ftour': 29}},
                                   '2026-11': {1: {'ftour': 4}}})
        dialog = StudentMealsDialog([(2026, 10), (2026, 11)], self.students)
        dialog._redistribute()
        self.assertEqual(dialog.table.cellWidget(0, 2).value(), 1)
        dialog.reject()
        self.assertEqual(monthly_student_meals('2026-10', self.students)[1]['ftour'], 29)
        dialog = StudentMealsDialog([(2026, 10), (2026, 11)], self.students)
        dialog._redistribute()
        dialog._save()
        self.assertEqual(monthly_student_meals('2026-10', self.students)[1]['ftour'], 1)
        self.assertEqual(monthly_student_meals('2026-11', self.students)[1]['ftour'], 4)

    def test_excel_uses_reviewed_counts_and_live_totals(self):
        import openpyxl
        path = Path(self.temp.name) / 'meals.xlsx'
        counts = period_student_meals([(2026, 10)], self.students)
        write_expense_roster_excel(path, None, self.students, [(2026, 10)], meal_counts=counts)
        book = openpyxl.load_workbook(path)
        sheet = book['اعدادي']
        self.assertEqual(sheet['H16'].value, 1)
        self.assertEqual(sheet['H17'].value, 1)
        self.assertEqual(sheet['H18'].value, '=SUM(H16:H17)')
        self.assertEqual(int(sheet.page_setup.paperSize), 9)
        book.close()

    def test_monthly_pdfs_use_two_up_and_company_copy_count(self):
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from core.models import MonthlyReceptionRecord
        from data.settings_repo import save_pdf_print_layout
        from ui.monthly_report_screen import _write_monthly_summary_pdf
        from ui.monthly_reception_screen import _write_monthly_reception_pdf
        save_pdf_print_layout('three_copies')
        summary = Path(self.temp.name) / 'summary.pdf'
        _write_monthly_summary_pdf(summary, None, 'October 2026', [], '')
        reception = Path(self.temp.name) / 'reception.pdf'
        _write_monthly_reception_pdf(reception, None, '2026-10',
                                     MonthlyReceptionRecord(month='2026-10'),
                                     print_layout='three_copies', copies=3)
        for path, pages in ((summary, 1), (reception, 2)):
            document = QPdfDocument(self.app)
            buffer = QBuffer()
            buffer.setData(QByteArray(path.read_bytes()))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            document.load(buffer)
            self.assertEqual(document.pageCount(), pages)
            size = document.pagePointSize(0)
            self.assertGreater(size.width(), size.height())
            document.close()
            del document
            buffer.close()
