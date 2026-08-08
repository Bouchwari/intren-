import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.document_pipeline import (
    DOC_ABSENCE, DOC_CONTACT, DOC_ORDER_LETTER, DOC_RECEPTION, DOC_REPORT, get_daily_pipeline_status,
)
from core.models import DailyAbsence, DailyContact, DailyReceptionRecord, DailyReport, OrderLetter
from data import database


class DocumentPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_all_five_documents_not_ready_for_a_blank_date(self) -> None:
        items = get_daily_pipeline_status("2026-06-11")
        self.assertEqual(
            {item.key for item in items},
            {DOC_CONTACT, DOC_ABSENCE, DOC_REPORT, DOC_ORDER_LETTER, DOC_RECEPTION},
        )
        self.assertTrue(all(not item.ready for item in items))

    def test_contact_ready_once_saved(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type="ghada", collegial_granted=5))
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-11")}
        self.assertTrue(items[DOC_CONTACT].ready)
        self.assertFalse(items[DOC_ABSENCE].ready)

    def test_absence_ready_once_saved(self) -> None:
        database.save_daily_absence(DailyAbsence(date="2026-06-11", meal_type="ghada", collegial_granted=1))
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-11")}
        self.assertTrue(items[DOC_ABSENCE].ready)
        self.assertFalse(items[DOC_CONTACT].ready)

    def test_report_not_ready_until_explicitly_saved_even_with_contact_and_absence(self) -> None:
        """The report's numbers auto-compute from contact+absence, but the
        checklist only exists once the مسير explicitly saves it — so
        "ready" must require an actual saved DailyReport row, not just
        that contact/absence data exists."""
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type="ghada", collegial_granted=5))
        database.save_daily_absence(DailyAbsence(date="2026-06-11", meal_type="ghada", collegial_granted=1))
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-11")}
        self.assertFalse(items[DOC_REPORT].ready)
        self.assertIn("جاهزة", items[DOC_REPORT].detail)  # numbers ready, just needs the checklist

    def test_report_ready_once_explicitly_saved(self) -> None:
        database.save_daily_report(DailyReport(date="2026-06-11"))
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-11")}
        self.assertTrue(items[DOC_REPORT].ready)

    def test_order_letter_ready_when_a_saved_letter_covers_the_date(self) -> None:
        database.save_order_letter(
            OrderLetter(letter_date="2026-06-09", period_start="2026-06-10", period_end="2026-06-14"),
            [],
        )
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-11")}
        self.assertTrue(items[DOC_ORDER_LETTER].ready)

    def test_order_letter_not_ready_when_date_is_outside_every_saved_period(self) -> None:
        database.save_order_letter(
            OrderLetter(letter_date="2026-06-09", period_start="2026-06-10", period_end="2026-06-14"),
            [],
        )
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-20")}
        self.assertFalse(items[DOC_ORDER_LETTER].ready)

    def test_reception_ready_once_saved(self) -> None:
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-11", ftour_qty=5))
        items = {item.key: item for item in get_daily_pipeline_status("2026-06-11")}
        self.assertTrue(items[DOC_RECEPTION].ready)


if __name__ == "__main__":
    unittest.main()
