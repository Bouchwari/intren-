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
from core.models import DailyAbsence, DailyContact, DailyReceptionRecord, SchoolSettings
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
        gestionnaire="فاطمة الزهراء",
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

    def test_quantities_are_contact_minus_absence(self) -> None:
        """The user's rule: "(daily contact numbers - absence) = the PV daily".
        محضر التسلم confirms what was actually DELIVERED, so a meal ordered for
        a student who never turned up must not be counted as received. It used
        to prefill from the contact sheet alone and overstated every day that
        had any absence."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=20, collegial_granted=15))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=3, collegial_granted=2))

        screen = drs.DailyReceptionScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 30)   # 35 ordered - 5 absent
        screen.close()

    def test_quantities_never_go_negative(self) -> None:
        """Bad data (absence larger than the contact sheet) must floor at zero,
        not print a negative delivery on a signed document."""
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=5))
        database.save_daily_absence(DailyAbsence(
            date="2026-06-11", meal_type=MEAL_GHADA, primary_granted=40))

        screen = drs.DailyReceptionScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._generate()

        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 0)
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

    def test_header_textbox_with_matchable_placeholder_is_filled_in_place(self) -> None:
        """The real template's own floating text box (wps:wsp / v:rect)
        currently has matchable Arabic placeholder text baked into it (the
        user typed real header text directly into it by hand at some
        point) — _fill_contact_header_xml finds those paragraphs and
        rewrites them in place. Regression this replaces: earlier code
        ALWAYS blanked this box right after filling it, then re-added a
        separate duplicate paragraph elsewhere — throwing away a correct
        in-place fill and replacing it with a redundant copy, which is
        exactly what left a visible EMPTY box for the user (the blank came
        from our own code, not the template). Now the blank+duplicate path
        only runs as a fallback when the box has nothing matchable at all
        — see test_fill_contact_header_xml_returns_zero_when_nothing_matches."""
        out = self._write(_test_settings(school_name="مدرسة اختبار مختلفة تماما"))
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/header2.xml"))

        parent_map = {c: p for p in root.iter() for c in p}

        def has_floating_ancestor(el):
            cur = el
            while cur in parent_map:
                cur = parent_map[cur]
                if cur.tag in (f"{_W_NS}drawing", f"{_W_NS}pict"):
                    return True
            return False

        floating_texts = []
        for p in root.findall(f".//{_W_NS}p"):
            if p.findall(f".//{_W_NS}p") or not has_floating_ancestor(p):
                continue
            floating_texts.append("".join(t.text or "" for t in p.iter(f"{_W_NS}t")))

        self.assertTrue(floating_texts)  # the paragraphs exist structurally
        self.assertIn("مدرسة اختبار مختلفة تماما", floating_texts)  # filled in place, not blanked

    def test_no_duplicate_header_paragraph_when_the_box_already_has_matchable_text(self) -> None:
        """With the real template's box already fillable in place, the
        separate "reliable text" fallback paragraph must NOT also be
        added — that would be a redundant second copy, adding real page
        height for nothing and contributing to the 2-page overflow the
        user reported."""
        out = self._write(_test_settings(school_name="مدرسة فريدة للتحقق من عدم التكرار"))
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/header2.xml"))

        occurrences = 0
        for p in root.findall(f".//{_W_NS}p"):
            if p.findall(f".//{_W_NS}p"):
                continue
            text = "".join(t.text or "" for t in p.iter(f"{_W_NS}t"))
            if "مدرسة فريدة للتحقق من عدم التكرار" in text:
                occurrences += 1
        # One copy in the DrawingML branch + one in the legacy VML
        # fallback branch of the SAME floating group is expected and
        # harmless (only one branch ever renders) — a 3rd, independent
        # paragraph would mean the always-add-a-duplicate behavior
        # regressed back.
        self.assertLessEqual(occurrences, 2)

    def test_fill_contact_header_xml_returns_zero_when_nothing_matches(self) -> None:
        """_write_reception_docx uses this return value to decide whether
        the separate fallback paragraph is needed — must be an honest
        count, not just None, so a template with no matchable placeholder
        text still gets a working fallback instead of a silently blank
        header."""
        from ui.daily_contact_screen import _fill_contact_header_xml

        root = ET.fromstring(
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:p><w:r><w:t>Nothing here matches any identity line</w:t></w:r></w:p>"
            "</w:hdr>"
        )
        filled = _fill_contact_header_xml(
            root, academy="اكاديمية اختبار", province="مديرية اختبار", school_name="مدرسة اختبار"
        )
        self.assertEqual(filled, 0)

    def test_fill_contact_header_xml_returns_count_when_matched(self) -> None:
        from ui.daily_contact_screen import _fill_contact_header_xml

        root = ET.fromstring(
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:p><w:r><w:t>الأكاديمية قديمة</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>المديرية قديمة</w:t></w:r></w:p>"
            "</w:hdr>"
        )
        filled = _fill_contact_header_xml(
            root, academy="اكاديمية اختبار", province="مديرية اختبار", school_name="مدرسة اختبار"
        )
        self.assertEqual(filled, 2)

    def test_fill_contact_header_xml_forces_arabswell_font(self) -> None:
        """Explicit standing instruction from the user: header identity
        text must always use the "arabswell" font (arabswell_1 — the
        bundled project display font), regardless of whatever font the
        matched paragraph's run happened to already carry."""
        from ui.daily_contact_screen import _fill_contact_header_xml

        root = ET.fromstring(
            '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:p><w:r><w:rPr><w:rFonts w:cs="Arial"/></w:rPr>'
            "<w:t>الأكاديمية قديمة</w:t></w:r></w:p>"
            "</w:hdr>"
        )
        _fill_contact_header_xml(
            root, academy="اكاديمية اختبار", province="مديرية اختبار", school_name="مدرسة اختبار"
        )
        rFonts = root.find(f".//{_W_NS}rFonts")
        self.assertEqual(rFonts.get(f"{_W_NS}cs"), "arabswell_1")

    def test_remarks_blank_row_height_is_capped_not_left_at_96pt(self) -> None:
        """The remarks table's blank row declares trHeight=1921 twentieths
        (~96pt) for a single EMPTY cell in the real template — by far the
        largest row height in the whole document and, on its own, bigger
        than the app's entire estimated page-2 overflow. hRule="atLeast"
        means this can only ever be a minimum, never a hard cap, so
        shrinking it can't clip real remarks text."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        tables = root.findall(f".//{_W_NS}tbl")
        remarks_rows = tables[2].findall(f"{_W_NS}tr")
        trHeight = remarks_rows[1].find(f"{_W_NS}trPr/{_W_NS}trHeight")
        self.assertIsNotNone(trHeight)
        val = int(trHeight.get(f"{_W_NS}val"))
        self.assertLessEqual(val, 950)
        self.assertGreater(val, 400)  # still real handwriting space, not collapsed to nothing

    def test_body_legal_paragraphs_use_configured_contract_and_contractor(self) -> None:
        """The user's current hand-edited template no longer has a
        separate matchable "LYCEE QUALIFIANT..." paragraph (it was
        deleted while editing), so school_fr has nothing to fill —
        only contract number and contractor are asserted here."""
        out = self._write(_test_settings(
            contract_number="55AAA/2027/ZZ",
            company_name="SOCIETE TEST XYZ",
            school_name_fr="LYCEE TEST FRANCAIS",
        ))
        text = _docx_plain_text(out)
        self.assertIn("55AAA/2027/ZZ", text)
        self.assertIn("SOCIETE TEST XYZ", text)
        # the template's own hardcoded originals must be gone, not just supplemented
        self.assertNotIn("10EXP/2025/AZ", text)
        self.assertNotIn("ALPHA MEN POWER", text)
        self.assertNotIn("LYCEE QUALIFIANT HASSAN 1 TAGLEFT", text)

    def test_closing_line_uses_configured_city_as_the_place(self) -> None:
        out = self._write(_test_settings(city="أكادير"))
        text = _docx_plain_text(out)
        self.assertIn("FAIT A أكادير. LE", text)

    def test_closing_line_prefers_french_city_name_when_set(self) -> None:
        """The whole document is French except the title/header — the
        place name should be too, when a French city name is configured."""
        out = self._write(_test_settings(city="أكادير", city_fr="Agadir"))
        text = _docx_plain_text(out)
        self.assertIn("FAIT A Agadir. LE", text)
        self.assertNotIn("FAIT A أكادير", text)

    def test_signer_table_prefilled_with_director_and_gestionnaire_names(self) -> None:
        """The user asked for the actual names in the document instead of
        leaving the "Nous soussignons" cells blank for handwriting. The
        role-label cell (2nd column) is intentionally NOT asserted against
        an exact hardcoded string here — the fill code deliberately leaves
        it as whatever the user's own template currently says (accents,
        apostrophe style, and even the full wording have all changed more
        than once this project), only the name cell is ever written."""
        out = self._write(_test_settings(director="سعيد بنعلي", gestionnaire="مريم التازي"))
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        signer_table = root.findall(f".//{_W_NS}tbl")[0]
        rows = signer_table.findall(f"{_W_NS}tr")

        def _row_texts(row):
            return ["".join(t.text or "" for t in c.iter(f"{_W_NS}t")) for c in row.findall(f"{_W_NS}tc")]

        chef_row = _row_texts(rows[1])
        gestionnaire_row = _row_texts(rows[2])
        self.assertEqual(chef_row[0], "سعيد بنعلي")
        self.assertTrue(chef_row[1].strip())  # role label present, untouched
        self.assertEqual(gestionnaire_row[0], "مريم التازي")
        self.assertTrue(gestionnaire_row[1].strip())

    def test_quantity_cells_reuse_the_existing_run_not_a_new_one(self) -> None:
        """Regression: filling an empty cell by creating a brand new
        sibling run (instead of reusing the cell's existing one) drops
        whatever formatting (e.g. font size) that existing run already
        had, rendering visibly inconsistent with its neighbors. All 3
        meal-quantity cells go through the same _set_empty_run_text now
        (ftour/ghada no longer reliably have a live MERGEFIELD to fall
        back on in the user's hand-edited template) — each cell must
        still end up with exactly ONE run (reused), not two (one old
        empty + one freshly created), regardless of what that run's own
        formatting happens to be."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        tables = root.findall(f".//{_W_NS}tbl")
        items_table = tables[1]
        rows = items_table.findall(f"{_W_NS}tr")

        for meal_row, expected_qty in ((rows[1], "1"), (rows[2], "2"), (rows[3], "3")):
            cell = meal_row.findall(f"{_W_NS}tc")[-1]
            runs_with_text = [r for r in cell.findall(f".//{_W_NS}r") if r.find(f"{_W_NS}t") is not None]
            self.assertEqual(len(runs_with_text), 1, f"expected exactly 1 text-bearing run in {cell!r}")
            self.assertEqual(runs_with_text[0].find(f"{_W_NS}t").text, expected_qty)

    def test_header_body_gap_is_widened_a_modest_safety_amount(self) -> None:
        """Regression: the template's own page margins leave the header
        zone (pgMar/@header) only ~3pt of clearance before the body zone
        (pgMar/@top) starts. This is a secondary safety hedge — kept
        modest (not the whole ~50pt the header needs) specifically so it
        can't push body content onto a second page on its own; the real
        fix is the floating textbox's own position, tested below."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        pg_mar = root.find(f".//{_W_NS}sectPr/{_W_NS}pgMar")
        header_dist = int(pg_mar.get(f"{_W_NS}header"))
        top_margin = int(pg_mar.get(f"{_W_NS}top"))
        gap_pt = (top_margin - header_dist) / 20
        self.assertGreaterEqual(gap_pt, 20)

    def test_header_textbox_pushed_further_above_the_margin_line(self) -> None:
        """Regression: the header's academy/directorate/school text lives
        inside a floating DrawingML group (image + text box) anchored to
        the page margin with wp:positionV/wp:posOffset — a NEGATIVE value
        exactly equal to the group's own height, meaning the group (and
        the text box inside it) sits flush against the margin line with
        zero clearance from the body. Every such upward-anchored offset
        in the header must end up more negative than the template's own
        original value, giving the text real breathing room."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            generated_h2 = z.read("word/header2.xml").decode("utf-8")
        template_path = Path(drs.__file__).resolve().parents[2] / "templets" / "المحضر اليومي لتسلم الخدمة.docx"
        with zipfile.ZipFile(template_path) as z:
            original_h2 = z.read("word/header2.xml").decode("utf-8")

        wp_ns = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        pattern = re.compile(rf"<[\w]*:?positionV[^>]*>\s*<[\w]*:?posOffset[^>]*>(-?\d+)</")
        original_offsets = [int(m) for m in pattern.findall(original_h2)]
        generated_offsets = [int(m) for m in pattern.findall(generated_h2)]

        self.assertTrue(original_offsets)
        self.assertEqual(len(original_offsets), len(generated_offsets))
        for original, generated in zip(original_offsets, generated_offsets):
            if original < 0:
                self.assertLess(generated, original)

    def _header_with(self, image_top, image_cy, text_top, text_cy, *, frame=False):
        wp = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        pic = "http://schemas.openxmlformats.org/drawingml/2006/picture"
        frame_xml = (
            f'<wp:anchor><wp:positionH relativeFrom="column"><wp:posOffset>9</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{text_top - 500000}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="100" cy="900000"/><wp:docPr name="Frame4"/></wp:anchor>'
        ) if frame else ""
        return ET.fromstring(
            f'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            f'xmlns:wp="{wp}" xmlns:pic="{pic}">'
            f"{frame_xml}"
            f'<wp:anchor><wp:positionH relativeFrom="column"><wp:posOffset>7</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{image_top}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="100" cy="{image_cy}"/><wp:docPr name="Image 2"/><pic:pic/></wp:anchor>'
            f'<wp:anchor><wp:positionH relativeFrom="column"><wp:posOffset>5</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{text_top}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="100" cy="{text_cy}"/><wp:docPr name="Zone de texte 1"/>'
            f"<w:p><w:r><w:t>الأكاديمية</w:t></w:r></w:p></wp:anchor>"
            "</w:hdr>"
        )

    @staticmethod
    def _anchor_v(root, name):
        wp = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
        for a in root.iter(f"{wp}anchor"):
            if a.find(f"{wp}docPr").get("name") == name:
                return int(a.find(f"{wp}positionV/{wp}posOffset").text)
        return None

    @staticmethod
    def _anchor_bounds(root, name):
        wp = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
        for a in root.iter(f"{wp}anchor"):
            if a.find(f"{wp}docPr").get("name") == name:
                top = int(a.find(f"{wp}positionV/{wp}posOffset").text)
                cy = int(a.find(f"{wp}extent").get("cy"))
                return top, top + cy
        return None

    def test_header_text_moved_below_image_when_it_overlaps(self) -> None:
        """The monthly template's identity text box starts 2.75pt ABOVE
        the crest image's bottom edge, and the image is behindDoc="0" so
        it paints ON TOP — hiding the first line. The text box must end
        up fully below the image, and centered."""
        wp = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
        # image -102pt..-53.1pt, text starting -55.9pt (the real numbers)
        root = self._header_with(-1296035, 621665, -709295, 938530, frame=True)
        drs._stack_reception_header_text_under_image(root)

        image_bottom = -1296035 + 621665
        text_top = self._anchor_v(root, "Zone de texte 1")
        self.assertGreaterEqual(text_top, image_bottom, "text box still overlaps the image")

        # ...and centered horizontally
        for a in root.iter(f"{wp}anchor"):
            if a.find(f"{wp}docPr").get("name") == "Zone de texte 1":
                ph = a.find(f"{wp}positionH")
                self.assertEqual(ph.get("relativeFrom"), "margin")
                self.assertEqual(ph.find(f"{wp}align").text, "center")

    def test_header_text_already_clear_is_left_untouched(self) -> None:
        """Self-limiting guard: the DAILY template's text box already
        clears its image by 8pt, so this fix must be a no-op there — it's
        shared by both documents and must not disturb daily's own
        confirmed-good header layout."""
        # the real daily numbers: image -95..-46.1pt, text -38.1pt
        root = self._header_with(-1206500, 621665, -483870, 764540)
        before = self._anchor_v(root, "Zone de texte 1")
        drs._stack_reception_header_text_under_image(root)
        self.assertEqual(self._anchor_v(root, "Zone de texte 1"), before)

    def test_empty_decorative_frame_grows_to_enclose_the_moved_text(self) -> None:
        """"Frame4" is the empty border rectangle drawn around the whole
        header. Regression: an earlier version of this fix moved the
        text out from behind the image but left the frame at its
        original fixed size — the repositioned text then ran ~9pt past
        the frame's own bottom border, spilling text outside its visible
        box. The frame must grow to enclose BOTH the image and the
        (moved) text, not just be left untouched or moved by the same
        raw delta as the text."""
        root = self._header_with(-1296035, 621665, -709295, 938530, frame=True)
        image_top, image_bottom = -1296035, -1296035 + 621665
        drs._stack_reception_header_text_under_image(root)

        frame_top, frame_bottom = self._anchor_bounds(root, "Frame4")
        text_top, text_bottom = self._anchor_bounds(root, "Zone de texte 1")

        self.assertLessEqual(frame_top, min(image_top, text_top), "frame no longer covers the top content")
        self.assertGreaterEqual(frame_bottom, max(image_bottom, text_bottom), "text still spills past the frame's bottom")

    def test_push_title_box_down_gives_small_offsets_real_clearance(self) -> None:
        """Regression: the bilingual title box (a floating shape anchored
        relative to its own paragraph) sits close enough to its anchor
        point in some templates (as little as ~11pt in the monthly
        template) to visibly collide with the header's own floating
        content rendered just above it — a real user-reported overlap.
        A small positive offset must be pushed further down; an
        already-generous one (like the daily template's own ~29pt) or a
        negative one (some other, unrelated shape) must be left alone."""
        wp_ns = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        root = ET.fromstring(
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            f'xmlns:wp="{wp_ns}">'
            "<wp:positionV relativeFrom=\"paragraph\"><wp:posOffset>135890</wp:posOffset></wp:positionV>"
            "<wp:positionV relativeFrom=\"paragraph\"><wp:posOffset>366395</wp:posOffset></wp:positionV>"
            "<wp:positionV relativeFrom=\"margin\"><wp:posOffset>-1203325</wp:posOffset></wp:positionV>"
            "</w:document>"
        )
        drs._push_reception_title_box_down(root)
        offsets = [int(el.text) for el in root.iter(f"{{{wp_ns}}}posOffset")]
        self.assertEqual(offsets, [285890, 366395, -1203325])

    def test_widen_title_clearance_gap_stops_at_first_real_text(self) -> None:
        """Regression: a first version of this fix DOUBLED each blank
        paragraph's line height, adding ~60-70pt — enough to risk a
        2-page overflow, the same class of regression the daily template
        suffered from a too-generous spacing fix earlier. Now adds a
        modest, fixed amount instead — and must stop at the first
        paragraph with real text, never touching content beyond the
        title-to-content gap it's meant to widen."""
        root = ET.fromstring(
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>title</w:t></w:r></w:p>"
            '<w:p><w:pPr><w:spacing w:line="240"/></w:pPr></w:p>'
            '<w:p><w:pPr><w:spacing w:line="276"/></w:pPr></w:p>'
            "<w:p><w:r><w:t>Nous soussignons :</w:t></w:r></w:p>"
            '<w:p><w:pPr><w:spacing w:line="240"/></w:pPr></w:p>'
            "</w:body></w:document>"
        )
        drs._widen_reception_title_clearance_gap(root)
        body = root.find(f"{_W_NS}body")
        paragraphs = body.findall(f"{_W_NS}p")

        def _line(p):
            spacing = p.find(f"{_W_NS}pPr/{_W_NS}spacing")
            return int(spacing.get(f"{_W_NS}line")) if spacing is not None and spacing.get(f"{_W_NS}line") else None

        self.assertEqual(_line(paragraphs[1]), 340)  # 240 + 100
        self.assertEqual(_line(paragraphs[2]), 376)  # 276 + 100
        self.assertEqual(_line(paragraphs[4]), 240)  # past "Nous soussignons" — left at its original value

    def test_date_paragraphs_are_left_aligned_not_centered(self) -> None:
        """Regression: date paragraphs use the template's BodyText style,
        whose default is centered — the user wanted dates pushed to the
        far left instead. Both the MERGEFIELD-based fill path
        (_set_mergefield_value(..., align="start")) and the plain-text
        fallback path (when the template no longer has a live field —
        _set_paragraph_alignment called directly) must override that
        inherited default. Only requires at least one match, not a fixed
        count — the template's hand-edited state has varied between 1
        (closing line only) and 2 (also a standalone date line) occurrences
        this session, and both are valid as long as every one is left-aligned."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))

        date_paragraphs = []
        for p in root.iter(f"{_W_NS}p"):
            text = "".join(t.text or "" for t in p.findall(f"{_W_NS}r/{_W_NS}t"))
            if "11/06/2026" in text:  # the formatted date itself, not just any "2026" substring
                date_paragraphs.append((text, p))

        self.assertTrue(date_paragraphs)  # at least the closing "FAIT A...LE" line
        for text, p in date_paragraphs:
            pPr = p.find(f"{_W_NS}pPr")
            jc = pPr.find(f"{_W_NS}jc") if pPr is not None else None
            self.assertIsNotNone(jc, f"no explicit alignment on: {text!r}")
            self.assertEqual(jc.get(f"{_W_NS}val"), "start", f"not left-aligned: {text!r}")


if __name__ == "__main__":
    unittest.main()
