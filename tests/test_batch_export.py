import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtGui import QPageLayout
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import EXPORT_FORMAT_PDF
from core.models import DailyAbsence, DailyContact, Holiday, Student
from data import database
from ui import batch_export as be
from ui import daily_absence_screen as das
from ui import daily_contact_screen as dcs
from ui import daily_report_screen as drs

_HAS_PDFINFO = shutil.which("pdfinfo") is not None


def _pdf_page_count(path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError(f"could not find page count in pdfinfo output for {path}")


class _FakeRangeDialog:
    """Stand-in for _DateRangeDialog — avoids ever entering a real modal
    QDialog.exec() event loop, which just hangs under the offscreen
    platform with nothing to click."""

    def __init__(self, start: QDate, end: QDate) -> None:
        self._start = start
        self._end = end

    def __call__(self, _parent):
        return self

    def exec(self) -> int:
        return QDialog.DialogCode.Accepted

    def chosen_range(self):
        return (self._start, self._end)


class _AcceptRange(ExitStack):
    """Patches the date-range dialog to accept the given range immediately
    and the save-file picker to return `path`, so run_batch_combined_pdf()
    (and run_batch_generate_data(), which never opens a file dialog at all)
    run headless. `.info` is the mocked QMessageBox.information, for
    asserting on the summary message shown at the end."""

    def __init__(self, start: QDate, end: QDate, path: str) -> None:
        super().__init__()
        self._start, self._end, self._path = start, end, path
        self.info = None

    def __enter__(self):
        super().__enter__()
        self.enter_context(patch.object(be, "_DateRangeDialog", _FakeRangeDialog(self._start, self._end)))
        self.enter_context(patch.object(QFileDialog, "getSaveFileName", return_value=(self._path, "PDF (*.pdf)")))
        self.info = self.enter_context(patch.object(QMessageBox, "information", return_value=None))
        return self


class BatchExportCoreTests(unittest.TestCase):
    """run_batch_combined_pdf()'s own mechanics, independent of any screen:
    one shared PDF, one page per date, nothing silently skipped."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._out_path = str(Path(self._tmpdir.name) / "combined.pdf")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_calls_build_page_once_per_date_inclusive(self) -> None:
        seen = []

        def build_page(painter, page_w, page_h, date_str):
            seen.append(date_str)
            return "data"

        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_path):
            be.run_batch_combined_pdf(None, "test", QPageLayout.Orientation.Portrait, build_page)
        self.assertEqual(seen, ["2026-06-01", "2026-06-02", "2026-06-03"])

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_produces_one_pdf_with_one_page_per_date(self) -> None:
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_path):
            be.run_batch_combined_pdf(None, "test", QPageLayout.Orientation.Portrait, lambda *a: "data")
        self.assertEqual(_pdf_page_count(Path(self._out_path)), 3)

    def test_category_counts_appear_in_summary(self) -> None:
        categories = iter(["data", "holiday", "empty"])
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_path) as ctx:
            be.run_batch_combined_pdf(
                None, "test", QPageLayout.Orientation.Portrait, lambda *a: next(categories),
            )
        message = ctx.info.call_args[0][2]
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

        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_path) as ctx:
            be.run_batch_combined_pdf(None, "test", QPageLayout.Orientation.Portrait, build_page)
        self.assertEqual(seen, ["2026-06-01", "2026-06-02", "2026-06-03"])
        message = ctx.info.call_args[0][2]
        self.assertIn("2026-06-02", message)


class BatchExportScreenIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._db_tmpdir = tempfile.TemporaryDirectory()
        self._out_tmpdir = tempfile.TemporaryDirectory()
        self._out_path = str(Path(self._out_tmpdir.name) / "combined.pdf")
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._db_tmpdir.name) / "test_matama.db"
        database.init_database()
        # Legacy PDF-or-Word preference no longer read by batch export
        # (combined mode is PDF-only), kept here in case a future format
        # choice is added — harmless no-op today.
        database.save_document_export_format(EXPORT_FORMAT_PDF)
        self._original_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.information = self._original_info
        database.DB_PATH = self._original_db_path
        self._db_tmpdir.cleanup()
        self._out_tmpdir.cleanup()

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_daily_contact_batch_export_makes_one_combined_pdf(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5,
        ))
        # 2026-06-02 intentionally left with no data -> its own placeholder page.
        database.save_daily_contact(DailyContact(
            date="2026-06-03", meal_type=dcs.MEAL_GHADA, collegial_granted=7,
        ))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_path):
            screen._on_batch_export()

        self.assertEqual(_pdf_page_count(Path(self._out_path)), 3)
        screen.close()

    def test_daily_contact_batch_export_marks_holiday_days(self) -> None:
        database.add_holiday(Holiday(date="2026-06-02", label="عطلة تجريبية"))
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5,
        ))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 2), self._out_path) as ctx:
            screen._on_batch_export()

        message = ctx.info.call_args[0][2]
        self.assertIn("1 يوم ببيانات فعلية", message)
        self.assertIn("1 يوم عطلة", message)
        screen.close()

    def test_daily_contact_batch_export_assigns_a_real_number_when_missing(self) -> None:
        """Regression: a day filled by توليد الأرقام لعدة أيام has contact
        data but was never officially "printed", so it had no recorded
        رقم الوثيقة — the combined PDF showed "...." for it. Batch export
        must now assign and record a real number for such a day."""
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5,
        ))
        self.assertIsNone(database.get_document_number_for_date("2026-06-01"))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), self._out_path):
            screen._on_batch_export()

        assigned = database.get_document_number_for_date("2026-06-01")
        self.assertIsNotNone(assigned)
        self.assertGreaterEqual(assigned, 1)
        screen.close()

    def test_daily_contact_batch_export_keeps_an_already_recorded_number(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5,
        ))
        database.record_daily_contact_document(
            "2026-06-01", 42, "print", [DailyContact(date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5)],
        )

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), self._out_path):
            screen._on_batch_export()

        self.assertEqual(database.get_document_number_for_date("2026-06-01"), 42)
        screen.close()

    def test_daily_contact_batch_export_assigns_increasing_numbers_in_date_order(self) -> None:
        for day in ("2026-06-01", "2026-06-02", "2026-06-03"):
            database.save_daily_contact(DailyContact(date=day, meal_type=dcs.MEAL_GHADA, collegial_granted=5))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_path):
            screen._on_batch_export()

        numbers = [database.get_document_number_for_date(d) for d in ("2026-06-01", "2026-06-02", "2026-06-03")]
        self.assertEqual(numbers, sorted(numbers))
        self.assertEqual(len(set(numbers)), 3)
        screen.close()

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_daily_report_batch_export_makes_one_combined_pdf(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=10,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=2,
        ))
        # 2026-06-02 has neither contact nor absence data -> placeholder page.

        screen = drs.DailyReportScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 2), self._out_path):
            screen._on_batch_export()

        self.assertEqual(_pdf_page_count(Path(self._out_path)), 2)
        screen.close()

    def test_batch_export_never_saves_report_to_database(self) -> None:
        """Read-only guarantee: batch export must not create a saved
        DailyReport row, or it would silently freeze that date's beneficiary
        numbers away from future auto-recompute (see _load_report_fields)."""
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=drs.MEAL_FTOUR, collegial_granted=3,
        ))

        screen = drs.DailyReportScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), self._out_path):
            screen._on_batch_export()

        self.assertIsNone(database.get_daily_report("2026-06-01"))
        screen.close()

    @unittest.skipUnless(_HAS_PDFINFO, "pdfinfo not installed")
    def test_daily_absence_batch_export_makes_one_combined_pdf(self) -> None:
        database.save_daily_absence(DailyAbsence(
            date="2026-06-01", meal_type=das.MEAL_GHADA, collegial_granted=2,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-02", meal_type=das.MEAL_GHADA, collegial_granted=1,
        ))

        screen = das.DailyAbsenceScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 2), self._out_path):
            screen._on_batch_export()

        self.assertEqual(_pdf_page_count(Path(self._out_path)), 2)
        screen.close()

    def test_daily_absence_batch_export_never_saves_to_database(self) -> None:
        screen = das.DailyAbsenceScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), self._out_path):
            screen._on_batch_export()

        self.assertEqual(database.get_day_absences("2026-06-01"), [])
        screen.close()


class BatchGenerateDataTests(unittest.TestCase):
    """توليد الأرقام لعدة أيام — auto-fill AND SAVE real numbers (the same
    estimator behind توليد تلقائي) for every day in a range that has none
    yet, instead of one day at a time."""

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
        self._original_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.information = self._original_info
        database.DB_PATH = self._original_db_path
        self._db_tmpdir.cleanup()

    def test_daily_contact_fills_and_saves_every_day_in_range(self) -> None:
        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), "/unused"):
            screen._on_batch_generate_data()

        for day in ("2026-06-01", "2026-06-02", "2026-06-03"):
            contacts = database.get_day_contacts(day)
            self.assertEqual({c.meal_type for c in contacts}, {dcs.MEAL_FTOUR, dcs.MEAL_GHADA, dcs.MEAL_ASHA})
        screen.close()

    def test_daily_contact_never_overwrites_a_day_that_already_has_data(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-02", meal_type=dcs.MEAL_GHADA, collegial_granted=999,
        ))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), "/unused"):
            screen._on_batch_generate_data()

        untouched = [c for c in database.get_day_contacts("2026-06-02") if c.meal_type == dcs.MEAL_GHADA][0]
        self.assertEqual(untouched.collegial_granted, 999)
        screen.close()

    def test_daily_contact_skips_a_real_holiday(self) -> None:
        database.add_holiday(Holiday(date="2026-06-02", label="عطلة تجريبية"))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), "/unused"):
            screen._on_batch_generate_data()

        self.assertEqual(database.get_day_contacts("2026-06-02"), [])
        self.assertNotEqual(database.get_day_contacts("2026-06-01"), [])
        screen.close()

    def test_daily_absence_fills_and_saves_every_day_in_range(self) -> None:
        screen = das.DailyAbsenceScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 2), "/unused"):
            screen._on_batch_generate_data()

        for day in ("2026-06-01", "2026-06-02"):
            absences = database.get_day_absences(day)
            self.assertEqual({a.meal_type for a in absences}, {das.MEAL_FTOUR, das.MEAL_GHADA, das.MEAL_ASHA})
        screen.close()

    def test_daily_absence_never_overwrites_a_day_that_already_has_data(self) -> None:
        database.save_daily_absence(DailyAbsence(
            date="2026-06-01", meal_type=das.MEAL_GHADA, collegial_granted=7,
        ))

        screen = das.DailyAbsenceScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), "/unused"):
            screen._on_batch_generate_data()

        untouched = [a for a in database.get_day_absences("2026-06-01") if a.meal_type == das.MEAL_GHADA][0]
        self.assertEqual(untouched.collegial_granted, 7)
        screen.close()

    def test_no_students_shows_message_and_saves_nothing(self) -> None:
        database.DB_PATH = Path(self._db_tmpdir.name) / "empty_roster.db"
        database.init_database()

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), "/unused"):
            screen._on_batch_generate_data()

        self.assertEqual(database.get_day_contacts("2026-06-01"), [])
        screen.close()

    def test_unclassified_students_warn_instead_of_saving_silent_zeros(self) -> None:
        """Regression: real students with no القسم (class) assigned made
        count_students() classify nobody, so batch generate silently saved
        real rows full of zeros — indistinguishable from doing nothing.
        Must warn and save nothing instead."""
        database.DB_PATH = Path(self._db_tmpdir.name) / "unclassified_roster.db"
        database.init_database()
        database.add_student(Student(full_name="تلميذ بدون قسم", student_class="", grant_type="full"))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), "/unused"):
            screen._on_batch_generate_data()

        self.assertEqual(database.get_day_contacts("2026-06-01"), [])
        screen.close()


if __name__ == "__main__":
    unittest.main()
