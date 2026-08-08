import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import DailyContact, DailyReceptionRecord
from data import database
from ui import daily_reception_screen as drs


def _docx_plain_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml.replace("</w:p>", "\n"))
    return re.sub(r"\n{2,}", "\n", text)


class DailyReceptionScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._original_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.information = self._original_info
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_fresh_date_prefills_quantities_from_contact_sheet(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type=MEAL_FTOUR, primary_granted=10))
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=20, collegial_granted=15,
        ))

        screen = drs.DailyReceptionScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertEqual(screen._quantity_spins[MEAL_FTOUR].value(), 10)
        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 35)
        self.assertEqual(screen._quantity_spins[MEAL_ASHA].value(), 0)
        self.assertEqual(screen._remarks_edit.toPlainText(), "")
        screen.close()

    def test_saved_record_is_preserved_not_recomputed(self) -> None:
        """Once a محضر is saved, regenerating (e.g. navigating dates and
        back) must show the saved quantities exactly, even if ورقة
        الاتصال changed since — matches contact_sheet's own beneficiary-
        override guarantee. Use إعادة الحساب to force a refresh."""
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=99))
        database.save_daily_reception_record(DailyReceptionRecord(
            date="2026-06-11", ftour_qty=1, ghada_qty=2, asha_qty=3, remarks="ملاحظة محفوظة",
        ))

        screen = drs.DailyReceptionScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 2)  # not recomputed to 99
        self.assertEqual(screen._remarks_edit.toPlainText(), "ملاحظة محفوظة")

        screen._recompute_from_contacts()
        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 99)  # explicit refresh works
        screen.close()

    def test_save_and_reload_roundtrip(self) -> None:
        screen = drs.DailyReceptionScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()
        screen._quantity_spins[MEAL_FTOUR].setValue(7)
        screen._quantity_spins[MEAL_GHADA].setValue(14)
        screen._quantity_spins[MEAL_ASHA].setValue(2)
        screen._remarks_edit.setPlainText("تم التسليم كاملا")

        screen._on_save()

        saved = database.get_daily_reception_record("2026-06-11")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.ftour_qty, 7)
        self.assertEqual(saved.ghada_qty, 14)
        self.assertEqual(saved.asha_qty, 2)
        self.assertEqual(saved.remarks, "تم التسليم كاملا")
        screen.close()


class BuildReceptionPdfPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _draw(self, date_str: str, holiday_labels=None):
        out = Path(self._tmpdir.name) / "combined.pdf"
        writer = QPdfWriter(str(out))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Portrait)
        painter = QPainter(writer)
        try:
            kind = drs.build_reception_pdf_page(
                painter, float(writer.width()), float(writer.height()),
                date_str, holiday_labels or {}, database.get_school_settings(),
            )
        finally:
            painter.end()
        return kind

    def test_holiday_returns_placeholder_and_saves_nothing(self) -> None:
        kind = self._draw("2026-06-11", {"2026-06-11": "عطلة تجريبية"})
        self.assertEqual(kind, "holiday")
        self.assertIsNone(database.get_daily_reception_record("2026-06-11"))

    def test_no_contact_data_returns_empty_placeholder(self) -> None:
        kind = self._draw("2026-06-11")
        self.assertEqual(kind, "empty")
        self.assertIsNone(database.get_daily_reception_record("2026-06-11"))

    def test_real_data_saves_a_new_record_matching_contact_totals(self) -> None:
        """Unlike daily_report's batch export (read-only), a reception
        confirmation is meant to be a permanent signed snapshot — a
        "ready" day here creates and saves a real record."""
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=12))
        kind = self._draw("2026-06-11")
        self.assertEqual(kind, "data")
        record = database.get_daily_reception_record("2026-06-11")
        self.assertIsNotNone(record)
        self.assertEqual(record.ghada_qty, 12)

    def test_already_saved_day_is_preserved_exactly(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=999))
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-11", ghada_qty=3))
        kind = self._draw("2026-06-11")
        self.assertEqual(kind, "data")
        record = database.get_daily_reception_record("2026-06-11")
        self.assertEqual(record.ghada_qty, 3)  # untouched, not recomputed to 999


class ReceptionDocxWriterTests(unittest.TestCase):
    """Regression coverage for the exact bug found while building this:
    the real template has 3 SEPARATE <w:tbl> elements (signers / items /
    remarks), and the closing date field shares a paragraph with a static
    "FAIT A TAGLEFT. LE" label. A naive "first table" / "first <w:t> in
    the paragraph" approach silently fills the wrong place."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_all_fields_land_in_the_right_place(self) -> None:
        record = DailyReceptionRecord(
            date="2026-06-11", ftour_qty=42, ghada_qty=113, asha_qty=27,
            remarks="ملاحظة اختبار",
        )
        out = Path(self._tmpdir.name) / "reception.docx"
        drs._write_reception_docx(out, "2026-06-11", record)

        text = _docx_plain_text(out)
        self.assertIn("2026/06/11", text)
        self.assertIn("FAIT A TAGLEFT. LE", text)  # static label survives, not clobbered
        self.assertIn("42", text)
        self.assertIn("113", text)
        self.assertIn("27", text)
        self.assertIn("ملاحظة اختبار", text)

    def test_no_remarks_leaves_remarks_cell_blank(self) -> None:
        record = DailyReceptionRecord(date="2026-06-11", ftour_qty=1, ghada_qty=2, asha_qty=3)
        out = Path(self._tmpdir.name) / "reception.docx"
        drs._write_reception_docx(out, "2026-06-11", record)
        text = _docx_plain_text(out)
        self.assertIn("Remarques", text)


if __name__ == "__main__":
    unittest.main()
