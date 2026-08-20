import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6.QtCore import QDate
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import DailyContact, DailyReceptionRecord, SchoolSettings
from data import database
from ui import daily_reception_screen as drs

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_plain_text(path: Path, part: str = "word/document.xml") -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read(part).decode("utf-8")
    text = re.sub(r"<[^>]+>", "", xml.replace("</w:p>", "\n"))
    return re.sub(r"\n{2,}", "\n", text)


def _test_settings(**overrides) -> SchoolSettings:
    values = dict(
        school_name="الثانوية التأهيلية الحسن الأول",
        school_year="2026/2027",
        director="محمد العلوي",
        school_name_fr="LYCEE HASSAN PREMIER TEST",
        aref="سوس ماسة",
        direction_provinciale="أكادير",
        contract_number="99XYZ/2026/BB",
        contract_object="PRESTATION DE RESTAURATION TEST",
        company_name="TEST CONTRACTOR SARL",
        city="TAGLEFT",
    )
    values.update(overrides)
    return SchoolSettings(**values)


class ReceptionDateFormatTests(unittest.TestCase):
    """The template's own dates read day/month/year (e.g. "01/02/2026") —
    a plain dash-to-slash swap on the stored ISO date would print the
    year first instead."""

    def test_reorders_iso_date_to_day_month_year(self) -> None:
        self.assertEqual(drs._reception_date_format("2026-06-11"), "11/06/2026")

    def test_single_digit_day_and_month_are_not_stripped(self) -> None:
        self.assertEqual(drs._reception_date_format("2026-01-05"), "05/01/2026")


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
        drs._write_reception_docx(out, "2026-06-11", record, _test_settings())

        text = _docx_plain_text(out)
        self.assertIn("11/06/2026", text)  # template's own day/month/year order
        self.assertIn("FAIT A TAGLEFT. LE", text)  # static label survives, not clobbered
        self.assertIn("42", text)
        self.assertIn("113", text)
        self.assertIn("27", text)
        self.assertIn("ملاحظة اختبار", text)

    def test_no_remarks_leaves_remarks_cell_blank(self) -> None:
        record = DailyReceptionRecord(date="2026-06-11", ftour_qty=1, ghada_qty=2, asha_qty=3)
        out = Path(self._tmpdir.name) / "reception.docx"
        drs._write_reception_docx(out, "2026-06-11", record, _test_settings())
        text = _docx_plain_text(out)
        self.assertIn("Remarques", text)

    def test_missing_settings_still_produces_a_valid_document(self) -> None:
        """settings=None (the default) must not crash — every dynamic
        piece has a fallback, same guarantee as _fill_contact_header_xml."""
        record = DailyReceptionRecord(date="2026-06-11", ftour_qty=1, ghada_qty=2, asha_qty=3)
        out = Path(self._tmpdir.name) / "reception.docx"
        drs._write_reception_docx(out, "2026-06-11", record)  # no settings arg
        text = _docx_plain_text(out)
        self.assertIn("11/06/2026", text)


class ReceptionDocxDynamicContentTests(unittest.TestCase):
    """The header and several body paragraphs (school name, contract
    number/object, contractor, school year, closing place name) are
    plain fixed text in the real template, not MERGEFIELDs — before this
    fix they showed the template author's own school/contractor no
    matter what was configured in الإعدادات."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, settings: SchoolSettings) -> Path:
        record = DailyReceptionRecord(date="2026-06-11", ftour_qty=1, ghada_qty=2, asha_qty=3)
        out = Path(self._tmpdir.name) / "reception.docx"
        drs._write_reception_docx(out, "2026-06-11", record, settings)
        return out

    def test_header_shows_the_configured_school_not_the_templates_own(self) -> None:
        out = self._write(_test_settings(school_name="مدرسة اختبار مختلفة تماما"))
        header_text = _docx_plain_text(out, "word/header2.xml")
        self.assertIn("مدرسة اختبار مختلفة تماما", header_text)
        self.assertNotIn("الثانوية الإعدادية ألمدون", header_text)  # template's own hardcoded school

    def test_body_legal_paragraphs_use_configured_contract_and_contractor(self) -> None:
        out = self._write(_test_settings(
            contract_number="55AAA/2027/ZZ",
            company_name="SOCIETE TEST XYZ",
            school_name_fr="LYCEE TEST FRANCAIS",
        ))
        text = _docx_plain_text(out)
        self.assertIn("55AAA/2027/ZZ", text)
        self.assertIn("SOCIETE TEST XYZ", text)
        self.assertIn("LYCEE TEST FRANCAIS", text)
        # the template's own hardcoded originals must be gone, not just supplemented
        self.assertNotIn("10EXP/2025/AZ", text)
        self.assertNotIn("ALPHA MEN POWER", text)
        self.assertNotIn("LYCEE QUALIFIANT HASSAN 1 TAGLEFT", text)

    def test_closing_line_uses_configured_city_as_the_place(self) -> None:
        out = self._write(_test_settings(city="أكادير"))
        text = _docx_plain_text(out)
        self.assertIn("FAIT A أكادير. LE", text)

    def test_dinner_quantity_matches_breakfast_lunch_font_size(self) -> None:
        """Regression: the dinner cell has no MERGEFIELD in the real
        template, just an existing-but-empty run — filling it by creating
        a brand new sibling run (instead of reusing that one) used to
        drop the template's 10pt sizing and render visibly bigger."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        tables = root.findall(f".//{_W_NS}tbl")
        items_table = tables[1]
        rows = items_table.findall(f"{_W_NS}tr")

        def _quantity_cell_sz(row) -> str | None:
            cell = row.findall(f"{_W_NS}tc")[-1]
            run = cell.find(f".//{_W_NS}r")
            sz = run.find(f".//{_W_NS}sz")
            return sz.get(f"{_W_NS}val") if sz is not None else None

        ftour_sz = _quantity_cell_sz(rows[1])
        dinner_sz = _quantity_cell_sz(rows[3])
        self.assertIsNotNone(dinner_sz)
        self.assertEqual(dinner_sz, ftour_sz)


if __name__ == "__main__":
    unittest.main()
