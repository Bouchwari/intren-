import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import EXPORT_FORMAT_PDF
from core.models import DailyAbsence, DailyContact
from data import database
from ui import batch_export as be
from ui import daily_contact_screen as dcs
from ui import daily_report_screen as drs


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
    and the folder picker to return `folder`, so run_batch_export() runs
    headless. `.info` is the mocked QMessageBox.information, for asserting
    on the summary message shown at the end."""

    def __init__(self, start: QDate, end: QDate, folder: str) -> None:
        super().__init__()
        self._start, self._end, self._folder = start, end, folder
        self.info = None

    def __enter__(self):
        super().__enter__()
        self.enter_context(patch.object(be, "_DateRangeDialog", _FakeRangeDialog(self._start, self._end)))
        self.enter_context(patch.object(QFileDialog, "getExistingDirectory", return_value=self._folder))
        self.info = self.enter_context(patch.object(QMessageBox, "information", return_value=None))
        return self


class BatchExportCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_calls_generate_day_once_per_date_inclusive(self) -> None:
        seen = []
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._tmpdir.name):
            be.run_batch_export(None, lambda date_str, folder: seen.append(date_str) or True)
        self.assertEqual(seen, ["2026-06-01", "2026-06-02", "2026-06-03"])

    def test_skipped_days_dont_count_as_done(self) -> None:
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 2), self._tmpdir.name) as ctx:
            be.run_batch_export(None, lambda date_str, folder: date_str == "2026-06-01")
        message = ctx.info.call_args[0][2]
        self.assertIn("1 ملف من أصل 2 يوم", message)

    def test_a_failing_day_is_reported_but_doesnt_stop_the_batch(self) -> None:
        seen = []

        def generate_day(date_str: str, folder: Path) -> bool:
            seen.append(date_str)
            if date_str == "2026-06-02":
                raise RuntimeError("boom")
            return True

        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._tmpdir.name) as ctx:
            be.run_batch_export(None, generate_day)
        self.assertEqual(seen, ["2026-06-01", "2026-06-02", "2026-06-03"])
        message = ctx.info.call_args[0][2]
        self.assertIn("2 ملف من أصل 3", message)
        self.assertIn("2026-06-02", message)


class BatchExportScreenIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._db_tmpdir = tempfile.TemporaryDirectory()
        self._out_tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._db_tmpdir.name) / "test_matama.db"
        database.init_database()
        # Skip the "PDF or Word?" prompt _on_batch_export shows when no
        # preference is saved — it's a real modal dialog, would hang here.
        database.save_document_export_format(EXPORT_FORMAT_PDF)
        self._original_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.information = self._original_info
        database.DB_PATH = self._original_db_path
        self._db_tmpdir.cleanup()
        self._out_tmpdir.cleanup()

    def test_daily_contact_batch_export_skips_days_with_no_data(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=dcs.MEAL_GHADA, collegial_granted=5,
        ))
        # 2026-06-02 intentionally left with no data.
        database.save_daily_contact(DailyContact(
            date="2026-06-03", meal_type=dcs.MEAL_GHADA, collegial_granted=7,
        ))

        screen = dcs.DailyContactScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 3), self._out_tmpdir.name):
            screen._on_batch_export()

        written = sorted(p.name for p in Path(self._out_tmpdir.name).glob("*.pdf"))
        self.assertEqual(len(written), 2)
        self.assertTrue(any("2026-06-01" in name for name in written))
        self.assertTrue(any("2026-06-03" in name for name in written))
        self.assertFalse(any("2026-06-02" in name for name in written))
        screen.close()

    def test_daily_report_batch_export_uses_contact_and_absence_data(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=10,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-01", meal_type=drs.MEAL_GHADA, collegial_granted=2,
        ))
        # 2026-06-02 has neither contact nor absence data -> must be skipped.

        screen = drs.DailyReportScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 2), self._out_tmpdir.name):
            screen._on_batch_export()

        written = list(Path(self._out_tmpdir.name).glob("*.pdf"))
        self.assertEqual(len(written), 1)
        self.assertIn("2026-06-01", written[0].name)
        screen.close()

    def test_batch_export_never_saves_report_to_database(self) -> None:
        """Read-only guarantee: batch export must not create a saved
        DailyReport row, or it would silently freeze that date's beneficiary
        numbers away from future auto-recompute (see _load_report_fields)."""
        database.save_daily_contact(DailyContact(
            date="2026-06-01", meal_type=drs.MEAL_FTOUR, collegial_granted=3,
        ))

        screen = drs.DailyReportScreen()
        with _AcceptRange(QDate(2026, 6, 1), QDate(2026, 6, 1), self._out_tmpdir.name):
            screen._on_batch_export()

        self.assertIsNone(database.get_daily_report("2026-06-01"))
        screen.close()


if __name__ == "__main__":
    unittest.main()
