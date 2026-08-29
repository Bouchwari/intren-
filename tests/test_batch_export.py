import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtGui import QPageLayout
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.contact_counts import count_students
from core.models import DailyAbsence, DailyContact, DailyReport, Holiday, Student
from data import database
from ui import batch_export as be
from ui import daily_absence_screen as das
from ui import daily_contact_screen as dcs
from ui import daily_report_screen as drs
from ui.work_pipeline_screen import _flatten_counts as flatten_counts

_HAS_PDFINFO = shutil.which("pdfinfo") is not None


def _pdf_page_count(path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError(f"could not find page count in pdfinfo output for {path}")


class BatchExportCoreTests(unittest.TestCase):
    """write_combined_pdf()'s own mechanics, independent of any screen:
    one shared PDF, one page per date, nothing silently skipped."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._out_path = Path(self._tmpdir.name) / "combined.pdf"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_calls_build_page_once_per_date_inclusive(self) -> None:
        seen = []

        def build_page(painter, page_w, page_h, date_str):
            seen.append(date_str)
            return "data"

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 3),
            QPageLayout.Orientation.Portrait, build_page,
        )
        self.assertEqual(seen, ["2026-06-01", "2026-06-02", "2026-06-03"])

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_produces_one_pdf_with_one_page_per_date(self) -> None:
        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 3),
            QPageLayout.Orientation.Portrait, lambda *a: "data",
        )
        self.assertEqual(_pdf_page_count(self._out_path), 3)

    def test_category_counts_appear_in_summary(self) -> None:
        categories = iter(["data", "holiday", "empty"])
        counts, failed_dates = be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 3),
            QPageLayout.Orientation.Portrait, lambda *a: next(categories),
        )
        message = be._summarize_combined_pdf(self._out_path, counts, failed_dates)
        self.assertIn("1 يوم ببيانات فعلية", message)
        self.assertIn("1 يوم عطلة", message)
        self.assertIn("1 يوم بلا بيانات مسجلة", message)

    def test_a_failing_day_is_reported_but_doesnt_stop_the_batch(self) -> None:
        seen = []

        def build_page(painter, page_w, page_h, date_str):
            seen.append(date_str)
            if date_str == "2026-06-02":
                raise RuntimeError("boom")
            return "data"

        counts, failed_dates = be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 3),
            QPageLayout.Orientation.Portrait, build_page,
        )
        self.assertEqual(seen, ["2026-06-01", "2026-06-02", "2026-06-03"])
        self.assertIn("2026-06-02", failed_dates)


class BatchExportBuildPageTests(unittest.TestCase):
    """Regression coverage for build_contact_pdf_page / build_absence_pdf_page
    / build_report_pdf_page — shared by يوم العمل's "توليد شامل لعدة أيام"
    (see ui/work_pipeline_screen.py), driven here through write_combined_pdf
    directly instead of through a screen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._db_tmpdir = tempfile.TemporaryDirectory()
        self._out_tmpdir = tempfile.TemporaryDirectory()
        self._out_path = Path(self._out_tmpdir.name) / "combined.pdf"
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._db_tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._db_tmpdir.cleanup()
        self._out_tmpdir.cleanup()

    def _contact_build_page(self):
        settings = database.get_school_settings()
        holiday_labels = {h.date: h.label for h in database.get_all_holidays()}
        return lambda painter, w, h, d: dcs.build_contact_pdf_page(painter, w, h, d, holiday_labels, settings)

    def _absence_build_page(self):
        settings = database.get_school_settings()
        holiday_labels = {h.date: h.label for h in database.get_all_holidays()}
        return lambda painter, w, h, d: das.build_absence_pdf_page(painter, w, h, d, holiday_labels, settings)

    def _reception_build_page(self):
        from ui import daily_reception_screen as drc
        settings = database.get_school_settings()
        holiday_labels = {h.date: h.label for h in database.get_all_holidays()}
        return lambda painter, w, h, d: drc.build_reception_pdf_page(painter, w, h, d, holiday_labels, settings)

    def _report_build_page(self):
        settings = database.get_school_settings()
        holiday_labels = {h.date: h.label for h in database.get_all_holidays()}
        return lambda painter, w, h, d: drs.build_report_pdf_page(painter, w, h, d, holiday_labels, settings)

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_daily_contact_makes_one_combined_pdf(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5))
        # 2026-06-02 intentionally left with no data -> its own placeholder page.
        database.save_daily_contact(DailyContact(date="2026-06-03", meal_type=dcs.MEAL_GHADA, collegial_granted=7))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 3),
            QPageLayout.Orientation.Portrait, self._contact_build_page(),
        )

        self.assertEqual(_pdf_page_count(self._out_path), 3)

    def test_daily_contact_marks_holiday_days(self) -> None:
        database.add_holiday(Holiday(date="2026-06-02", label="عطلة تجريبية"))
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5))

        counts, _ = be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 2),
            QPageLayout.Orientation.Portrait, self._contact_build_page(),
        )

        self.assertEqual(counts.get("data"), 1)
        self.assertEqual(counts.get("holiday"), 1)

    def test_daily_contact_assigns_a_real_number_when_missing(self) -> None:
        """Regression: a day filled by auto-fill has contact data but was
        never officially "printed", so it had no recorded رقم الوثيقة — the
        combined PDF showed "...." for it. The combined export must assign
        and record a real number for such a day."""
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5))
        self.assertIsNone(database.get_document_number_for_date("2026-06-01"))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 1),
            QPageLayout.Orientation.Portrait, self._contact_build_page(),
        )

        assigned = database.get_document_number_for_date("2026-06-01")
        self.assertIsNotNone(assigned)
        self.assertGreaterEqual(assigned, 1)

    def test_daily_contact_keeps_an_already_recorded_number(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5))
        database.record_daily_contact_document(
            "2026-06-01", 42, "print",
            [DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5)],
        )

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 1),
            QPageLayout.Orientation.Portrait, self._contact_build_page(),
        )

        self.assertEqual(database.get_document_number_for_date("2026-06-01"), 42)

    def test_daily_contact_assigns_increasing_numbers_in_date_order(self) -> None:
        for day in ("2026-06-01", "2026-06-02", "2026-06-03"):
            database.save_daily_contact(DailyContact(date=day, meal_type=dcs.MEAL_GHADA, collegial_granted=5))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 3),
            QPageLayout.Orientation.Portrait, self._contact_build_page(),
        )

        numbers = [database.get_document_number_for_date(d) for d in ("2026-06-01", "2026-06-02", "2026-06-03")]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(len(set(numbers)), 3)

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_daily_report_makes_one_combined_pdf(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=10))
        database.save_daily_absence(DailyAbsence(date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=2))
        # 2026-06-02 has neither contact nor absence data -> placeholder page.

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 2),
            QPageLayout.Orientation.Landscape, self._report_build_page(),
        )

        self.assertEqual(_pdf_page_count(self._out_path), 2)

    def test_batch_reception_saves_a_ramadan_days_own_meals(self) -> None:
        """The batch builder used to construct the record from ftour/ghada/asha
        only, so every Ramadan day was saved as an all-zero محضر تسلم even
        though ورقة الاتصال had real إفطار/سحور numbers."""
        from config.settings import MEAL_IFTAR, MEAL_SHOUR
        from core.models import SchoolSettings

        database.save_school_settings(SchoolSettings(
            school_name="مؤسسة", school_year="2025-2026", director="المدير",
            ramadan_start="2026-03-01", ramadan_end="2026-03-30"))
        database.save_daily_contact(DailyContact(date="2026-03-10", meal_type=MEAL_IFTAR, collegial_granted=40))
        database.save_daily_contact(DailyContact(date="2026-03-10", meal_type=MEAL_SHOUR, collegial_granted=35))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 3, 10), QDate(2026, 3, 10),
            QPageLayout.Orientation.Portrait, self._reception_build_page(),
        )

        record = database.get_daily_reception_record("2026-03-10")
        self.assertIsNotNone(record)
        self.assertEqual(record.ftour_ramadan_qty, 40)
        self.assertEqual(record.shour_qty, 35)
        # and it must not invent normal-day meals on a Ramadan day
        self.assertEqual((record.ftour_qty, record.ghada_qty, record.asha_qty), (0, 0, 0))

    def test_batch_reception_still_saves_a_normal_days_meals(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=50))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 1),
            QPageLayout.Orientation.Portrait, self._reception_build_page(),
        )

        record = database.get_daily_reception_record("2026-06-01")
        self.assertIsNotNone(record)
        self.assertEqual(record.ghada_qty, 50)
        self.assertEqual((record.ftour_ramadan_qty, record.shour_qty), (0, 0))

    def test_report_export_saves_the_report_it_printed(self) -> None:
        """يوم العمل's batch run must leave the same data behind as making the
        day by hand — the user asked for this explicitly on 2026-08-28
        ("when i generated multiply days those out put and data should save
        like normal made"). It previously printed the report and saved
        nothing, so a batch-generated day looked untouched in التقرير اليومي.
        """
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=drs.MEAL_FTOUR, collegial_granted=3))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 1),
            QPageLayout.Orientation.Landscape, self._report_build_page(),
        )

        saved = database.get_daily_report("2026-06-01")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.ftour_expected, 3)

    def test_report_export_never_overwrites_a_day_already_saved(self) -> None:
        """Saving what it prints must not clobber a day the user already
        filled in by hand — batch only ever creates a missing report."""
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=drs.MEAL_FTOUR, collegial_granted=3))
        database.save_daily_report(drs.DailyReport(date="2026-06-01", ftour_expected=99, ftour_present=98))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 1),
            QPageLayout.Orientation.Landscape, self._report_build_page(),
        )

        saved = database.get_daily_report("2026-06-01")
        self.assertEqual(saved.ftour_expected, 99, "the user's own numbers were overwritten")
        self.assertEqual(saved.ftour_present, 98)

    def test_report_batch_suggests_checklist_for_every_day_not_just_the_first(self) -> None:
        """يوم العمل's "توليد شامل لعدة أيام" must suggest real ratings for
        EVERY day in the range, not just a day that happens to already have
        a saved report — previously only _load_report_fields (the live
        screen) filled unrated items, so a batch run over several unsaved
        days left every one of them blank except a day someone had already
        opened and saved on screen."""
        database.save_daily_contact(DailyContact(date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=5))
        database.save_daily_contact(DailyContact(date="2026-06-02", meal_type=drs.MEAL_GHADA, collegial_granted=6))
        database.save_daily_contact(DailyContact(date="2026-06-03", meal_type=drs.MEAL_GHADA, collegial_granted=7))

        good_index = drs._THREE_SCALE.index("جيدة")
        for date_str in ("2026-06-01", "2026-06-02", "2026-06-03"):
            report = drs._report_for_date(date_str)
            for field, _ in drs._HYGIENE_ITEMS:
                self.assertNotEqual(getattr(report, field), -1, f"{date_str}/{field} was left unrated")
            for field, _ in drs._QUALITY_ITEMS:
                self.assertNotEqual(getattr(report, field), -1, f"{date_str}/{field} was left unrated")
            for field, _ in drs._BUILDING_ITEMS:
                self.assertEqual(getattr(report, field), good_index, f"{date_str}/{field} was not جيدة")
            # still read-only — batch export must never persist (see above)
            self.assertIsNone(database.get_daily_report(date_str))

    def test_report_batch_preserves_already_saved_ratings(self) -> None:
        """A day that already has a saved report with a real (even bad)
        rating must keep it exactly — batch export only fills in items
        that are still genuinely unrated, same rule as the live screen."""
        database.save_daily_report(DailyReport(date="2026-06-01", hygiene_staff=0))  # ضعيفة, a real problem

        report = drs._report_for_date("2026-06-01")

        self.assertEqual(report.hygiene_staff, 0)  # untouched
        for field, _ in drs._HYGIENE_ITEMS:
            if field != "hygiene_staff":
                self.assertNotEqual(getattr(report, field), -1, f"{field} was left unrated")

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_daily_absence_makes_one_combined_pdf(self) -> None:
        database.save_daily_absence(DailyAbsence(date="2026-06-01", meal_type=das.MEAL_GHADA, collegial_granted=2))
        database.save_daily_absence(DailyAbsence(date="2026-06-02", meal_type=das.MEAL_GHADA, collegial_granted=1))

        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 2),
            QPageLayout.Orientation.Portrait, self._absence_build_page(),
        )

        self.assertEqual(_pdf_page_count(self._out_path), 2)

    def test_daily_absence_export_never_saves_to_database(self) -> None:
        be.write_combined_pdf(
            self._out_path, QDate(2026, 6, 1), QDate(2026, 6, 1),
            QPageLayout.Orientation.Portrait, self._absence_build_page(),
        )

        self.assertEqual(database.get_day_absences("2026-06-01"), [])


class BatchGenerateDataTests(unittest.TestCase):
    """generate_and_save_contact_for_date() / generate_and_save_absence_for_date()
    — the estimator-backed auto-fill shared by the single-day "توليد
    تلقائي" button and يوم العمل's auto-fill-before-export option. The "no
    students" / "unclassified students" warnings live in يوم العمل's own
    _auto_fill_range now — see test_work_pipeline_screen.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._db_tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._db_tmpdir.name) / "test_matama.db"
        database.init_database()
        for name in ("تلميذ 1", "تلميذ 2", "تلميذ 3"):
            database.add_student(Student(
                full_name=name, student_class="الأولى إعدادي", grant_type="منحة كاملة",
            ))
        self._roster = flatten_counts(count_students(database.get_all_students()))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._db_tmpdir.cleanup()

    def _generate_contacts(self, start: QDate, end: QDate) -> None:
        history = database.get_recent_contacts(limit=900)
        date = start
        while date <= end:
            dcs.generate_and_save_contact_for_date(date.toString("yyyy-MM-dd"), self._roster, history)
            date = date.addDays(1)

    def _generate_absences(self, start: QDate, end: QDate) -> None:
        history = database.get_recent_absences(limit=900)
        date = start
        while date <= end:
            das.generate_and_save_absence_for_date(date.toString("yyyy-MM-dd"), self._roster, history)
            date = date.addDays(1)

    def test_daily_contact_fills_and_saves_every_day_in_range(self) -> None:
        self._generate_contacts(QDate(2026, 6, 1), QDate(2026, 6, 3))
        for day in ("2026-06-01", "2026-06-02", "2026-06-03"):
            contacts = database.get_day_contacts(day)
            self.assertEqual({c.meal_type for c in contacts}, {dcs.MEAL_FTOUR, dcs.MEAL_GHADA, dcs.MEAL_ASHA})

    def test_daily_contact_never_overwrites_a_day_that_already_has_data(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-02", meal_type=dcs.MEAL_GHADA, collegial_granted=999))
        self._generate_contacts(QDate(2026, 6, 1), QDate(2026, 6, 3))
        untouched = [c for c in database.get_day_contacts("2026-06-02") if c.meal_type == dcs.MEAL_GHADA][0]
        self.assertEqual(untouched.collegial_granted, 999)

    def test_daily_contact_skips_a_real_holiday(self) -> None:
        database.add_holiday(Holiday(date="2026-06-02", label="عطلة تجريبية"))
        self._generate_contacts(QDate(2026, 6, 1), QDate(2026, 6, 3))
        self.assertEqual(database.get_day_contacts("2026-06-02"), [])
        self.assertNotEqual(database.get_day_contacts("2026-06-01"), [])

    def test_daily_absence_fills_and_saves_every_day_in_range(self) -> None:
        self._generate_absences(QDate(2026, 6, 1), QDate(2026, 6, 2))
        for day in ("2026-06-01", "2026-06-02"):
            absences = database.get_day_absences(day)
            self.assertEqual({a.meal_type for a in absences}, {das.MEAL_FTOUR, das.MEAL_GHADA, das.MEAL_ASHA})

    def test_daily_absence_never_overwrites_a_day_that_already_has_data(self) -> None:
        database.save_daily_absence(DailyAbsence(date="2026-06-01", meal_type=das.MEAL_GHADA, collegial_granted=7))
        self._generate_absences(QDate(2026, 6, 1), QDate(2026, 6, 1))
        untouched = [a for a in database.get_day_absences("2026-06-01") if a.meal_type == das.MEAL_GHADA][0]
        self.assertEqual(untouched.collegial_granted, 7)


if __name__ == "__main__":
    unittest.main()
