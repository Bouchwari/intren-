import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6.QtWidgets import QApplication, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import DailyReceptionRecord, MonthlyReceptionRecord, SchoolSettings
from data import database
from ui import monthly_reception_screen as mrs

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_MODULE_TMPDIR: tempfile.TemporaryDirectory[str] | None = None
_MODULE_ORIGINAL_DB_PATH: Path | None = None


def setUpModule() -> None:
    """Document writers may read Ramadan overrides; give them a real DB."""
    global _MODULE_TMPDIR, _MODULE_ORIGINAL_DB_PATH
    _MODULE_TMPDIR = tempfile.TemporaryDirectory()
    _MODULE_ORIGINAL_DB_PATH = database.DB_PATH
    database.DB_PATH = Path(_MODULE_TMPDIR.name) / "monthly_reception_tests.db"
    database.init_database()


def tearDownModule() -> None:
    global _MODULE_TMPDIR
    if _MODULE_ORIGINAL_DB_PATH is not None:
        database.DB_PATH = _MODULE_ORIGINAL_DB_PATH
    if _MODULE_TMPDIR is not None:
        _MODULE_TMPDIR.cleanup()
        _MODULE_TMPDIR = None


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
        company_name="TEST CONTRACTOR SARL",
        city="TAGLEFT",
    )
    values.update(overrides)
    return SchoolSettings(**values)


class MonthlyReceptionMonthLabelTests(unittest.TestCase):
    def test_french_label_from_yyyy_mm(self) -> None:
        self.assertEqual(mrs._month_label_fr("2026-01"), "Janvier 2026")
        self.assertEqual(mrs._month_label_fr("2026-12"), "Décembre 2026")

    def test_arabic_label_from_yyyy_mm(self) -> None:
        self.assertEqual(mrs._month_label_ar("2026-08"), "غشت 2026")


class MonthlyReceptionRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_sum_daily_reception_for_month_aggregates_only_that_month(self) -> None:
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-01", ftour_qty=10, ghada_qty=20, asha_qty=5))
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-15", ftour_qty=8, ghada_qty=16, asha_qty=4))
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-07-01", ftour_qty=100, ghada_qty=100, asha_qty=100))

        sums = database.sum_daily_reception_for_month("2026-06")
        self.assertEqual(sums["ftour"], 18)
        self.assertEqual(sums["ghada"], 36)
        self.assertEqual(sums["asha"], 9)

    def test_sum_with_no_data_returns_zeros(self) -> None:
        sums = database.sum_daily_reception_for_month("2026-06")
        # Ramadan's two meals are summed alongside the normal three.
        self.assertEqual(
            sums, {"ftour": 0, "ghada": 0, "asha": 0, "iftar": 0, "shour": 0})

    def test_save_and_get_monthly_reception_record_roundtrip(self) -> None:
        database.save_monthly_reception_record(MonthlyReceptionRecord(
            month="2026-06", ftour_qty=180, ghada_qty=360, asha_qty=90, remarks="شهر كامل",
        ))
        record = database.get_monthly_reception_record("2026-06")
        self.assertIsNotNone(record)
        self.assertEqual(record.ftour_qty, 180)
        self.assertEqual(record.ghada_qty, 360)
        self.assertEqual(record.asha_qty, 90)
        self.assertEqual(record.remarks, "شهر كامل")

    def test_save_upserts_not_duplicates(self) -> None:
        database.save_monthly_reception_record(MonthlyReceptionRecord(month="2026-06", ftour_qty=1))
        database.save_monthly_reception_record(MonthlyReceptionRecord(month="2026-06", ftour_qty=99))
        record = database.get_monthly_reception_record("2026-06")
        self.assertEqual(record.ftour_qty, 99)

    def test_missing_month_returns_none(self) -> None:
        self.assertIsNone(database.get_monthly_reception_record("2026-06"))


class MonthlyReceptionScreenTests(unittest.TestCase):
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

    def _select_month(self, screen: "mrs.MonthlyReceptionScreen", year: int, month: int) -> None:
        screen._year_combo.setCurrentText(str(year))
        screen._month_combo.setCurrentIndex(month - 1)
        screen._generate()

    def test_fresh_month_prefills_quantities_from_daily_receptions(self) -> None:
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-01", ftour_qty=10, ghada_qty=20, asha_qty=5))
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-15", ftour_qty=8, ghada_qty=16, asha_qty=4))

        screen = mrs.MonthlyReceptionScreen()
        self._select_month(screen, 2026, 6)

        self.assertEqual(screen._quantity_spins[MEAL_FTOUR].value(), 18)
        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 36)
        self.assertEqual(screen._quantity_spins[MEAL_ASHA].value(), 9)
        self.assertEqual(screen._remarks_edit.toPlainText(), "")
        screen.close()

    def test_saved_record_is_preserved_not_recomputed(self) -> None:
        database.save_daily_reception_record(DailyReceptionRecord(date="2026-06-01", ghada_qty=999))
        database.save_monthly_reception_record(MonthlyReceptionRecord(
            month="2026-06", ftour_qty=1, ghada_qty=2, asha_qty=3, remarks="ملاحظة محفوظة",
        ))

        screen = mrs.MonthlyReceptionScreen()
        self._select_month(screen, 2026, 6)

        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 2)  # not recomputed to 999
        self.assertEqual(screen._remarks_edit.toPlainText(), "ملاحظة محفوظة")

        screen._recompute_from_daily_receptions()
        self.assertEqual(screen._quantity_spins[MEAL_GHADA].value(), 999)  # explicit refresh works
        screen.close()

    def test_save_and_reload_roundtrip(self) -> None:
        screen = mrs.MonthlyReceptionScreen()
        self._select_month(screen, 2026, 6)
        screen._quantity_spins[MEAL_FTOUR].setValue(180)
        screen._quantity_spins[MEAL_GHADA].setValue(360)
        screen._quantity_spins[MEAL_ASHA].setValue(90)
        screen._remarks_edit.setPlainText("تم التسليم طيلة الشهر")

        screen._on_save()

        saved = database.get_monthly_reception_record("2026-06")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.ftour_qty, 180)
        self.assertEqual(saved.ghada_qty, 360)
        self.assertEqual(saved.asha_qty, 90)
        self.assertEqual(saved.remarks, "تم التسليم طيلة الشهر")
        screen.close()


class MonthlyReceptionDocxWriterTests(unittest.TestCase):
    """Regression coverage mirroring test_daily_reception_screen.py's own
    ReceptionDocxWriterTests — the real monthly template also has
    multiple separate <w:tbl> elements and no MERGEFIELDs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_all_fields_land_in_the_right_place(self) -> None:
        record = MonthlyReceptionRecord(
            month="2026-06", ftour_qty=180, ghada_qty=360, asha_qty=90,
            remarks="ملاحظة اختبار شهرية",
        )
        out = Path(self._tmpdir.name) / "monthly_reception.docx"
        mrs._write_monthly_reception_docx(out, "2026-06", record, _test_settings())

        text = _docx_plain_text(out)
        self.assertIn("Juin 2026", text)
        self.assertIn("180", text)
        self.assertIn("360", text)
        self.assertIn("90", text)
        self.assertIn("ملاحظة اختبار شهرية", text)

    def test_no_remarks_leaves_remarks_cell_blank(self) -> None:
        record = MonthlyReceptionRecord(month="2026-06", ftour_qty=1, ghada_qty=2, asha_qty=3)
        out = Path(self._tmpdir.name) / "monthly_reception.docx"
        mrs._write_monthly_reception_docx(out, "2026-06", record, _test_settings())
        text = _docx_plain_text(out)
        self.assertIn("Remarques", text)

    def test_missing_settings_still_produces_a_valid_document(self) -> None:
        record = MonthlyReceptionRecord(month="2026-06", ftour_qty=1, ghada_qty=2, asha_qty=3)
        out = Path(self._tmpdir.name) / "monthly_reception.docx"
        mrs._write_monthly_reception_docx(out, "2026-06", record)  # no settings arg
        text = _docx_plain_text(out)
        self.assertIn("Juin 2026", text)


class MonthlyReceptionDocxDynamicContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, settings: SchoolSettings, **record_overrides) -> Path:
        defaults = dict(month="2026-06", ftour_qty=1, ghada_qty=2, asha_qty=3)
        defaults.update(record_overrides)
        record = MonthlyReceptionRecord(**defaults)
        out = Path(self._tmpdir.name) / "monthly_reception.docx"
        mrs._write_monthly_reception_docx(out, "2026-06", record, settings)
        return out

    def test_header_shows_the_configured_school_not_the_templates_own(self) -> None:
        out = self._write(_test_settings(school_name="مدرسة اختبار مختلفة تماما"))
        header_text = _docx_plain_text(out, "word/header2.xml")
        self.assertIn("مدرسة اختبار مختلفة تماما", header_text)

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
        self.assertNotIn("Alpha man power", text)
        self.assertNotIn("Lycée Qualifiant Hassan I", text)

    def test_only_school_and_company_are_bold_italic_rest_explicitly_off(self) -> None:
        """The user asked for ONLY the school name and contractor name in
        bold+italic. The subtle part: this template's `BodyText`
        paragraph style carries `<w:b/>` itself, so a run that merely
        OMITS `w:b` still renders bold by inheritance — an earlier
        version of this fix produced XML with no `w:b` on the plain runs
        and still rendered the whole paragraph bold. Every run must
        therefore state bold/italic EXPLICITLY: val="1" on the two
        emphasized names, val="0" on the surrounding boilerplate."""
        out = self._write(_test_settings(
            school_name_fr="ECOLE EMPHASE", company_name="STE EMPHASE",
        ))
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))

        found = {}
        for run in root.iter(f"{_W_NS}r"):
            t = run.find(f"{_W_NS}t")
            if t is None or not (t.text or "").strip():
                continue
            rPr = run.find(f"{_W_NS}rPr")
            if rPr is None:
                continue

            def _val(tag):
                el = rPr.find(f"{_W_NS}{tag}")
                return el.get(f"{_W_NS}val") if el is not None else None

            text = t.text
            if text.strip() in ("ECOLE EMPHASE", "STE EMPHASE"):
                found[text.strip()] = (_val("b"), _val("i"))
            elif text.startswith("Attestons que") or "conformément aux" in text:
                # surrounding boilerplate must be explicitly NOT bold/italic,
                # not merely missing the property (which would inherit bold)
                self.assertEqual(_val("b"), "0", f"boilerplate not explicitly unbolded: {text[:40]!r}")
                self.assertEqual(_val("i"), "0", f"boilerplate not explicitly unitalicized: {text[:40]!r}")

        self.assertEqual(found.get("ECOLE EMPHASE"), ("1", "1"))
        self.assertEqual(found.get("STE EMPHASE"), ("1", "1"))

    def test_legal_paragraphs_handle_merged_single_paragraph_template_state(self) -> None:
        """Regression: the user's template used to hold the contract
        sentence, school name, and contractor sentence as 3 SEPARATE
        paragraphs, but later hand-editing merged them into ONE paragraph
        containing all 3 back to back. A naive "first matching branch
        wins" loop would match "Attestons que" and overwrite the WHOLE
        paragraph with just that sentence, silently deleting the school
        name and contractor text that used to live in their own,
        now-gone, paragraphs. Verified directly against a synthetic
        merged paragraph, independent of whatever the real template's
        current state happens to be."""
        from ui.monthly_reception_screen import _fill_monthly_reception_legal_paragraphs

        root = ET.fromstring(
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body>"
            "<w:p><w:r><w:t>Attestons que les prestations objet du marché N° : OLD/123 ayant pour "
            "objet la prestation de restauration au profit de l'internat du : OLD SCHOOL NAME "
            "Ont été réellement exécutées par la société : OLD COMPANY conformément aux "
            "spécifications techniques exigées par le CPS au titre du mois : Janvier 2020, "
            "à hauteur des quantités suivantes :</w:t></w:r></w:p>"
            "</w:body></w:document>"
        )
        settings = _test_settings(
            contract_number="NEW/999", company_name="NEW COMPANY", school_name_fr="NEW SCHOOL",
        )
        _fill_monthly_reception_legal_paragraphs(root, settings, "2026-08", "23/08/2026")
        text = "".join(t.text or "" for t in root.iter(f"{_W_NS}t"))

        self.assertIn("NEW/999", text)
        self.assertIn("NEW SCHOOL", text)
        self.assertIn("NEW COMPANY", text)
        self.assertIn("Août 2026", text)
        self.assertNotIn("OLD/123", text)
        self.assertNotIn("OLD SCHOOL NAME", text)
        self.assertNotIn("OLD COMPANY", text)

    def test_closing_line_uses_configured_city_as_the_place(self) -> None:
        out = self._write(_test_settings(city="أكادير"))
        text = _docx_plain_text(out)
        self.assertIn("Fait à أكادير Le", text)

    def test_closing_line_prefers_french_city_name_when_set(self) -> None:
        out = self._write(_test_settings(city="أكادير", city_fr="Agadir"))
        text = _docx_plain_text(out)
        self.assertIn("Fait à Agadir Le", text)
        self.assertNotIn("Fait à أكادير", text)

    def test_signer_table_prefilled_with_director_and_gestionnaire_names(self) -> None:
        """The template's own "Nous soussignons" table lists the
        gestionnaire row FIRST, then the director row — the real
        template's own order, not this app's usual director-first order.
        Role-label cells are intentionally left untouched, only names."""
        out = self._write(_test_settings(director="سعيد بنعلي", gestionnaire="مريم التازي"))
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        signer_table = root.findall(f".//{_W_NS}tbl")[0]
        rows = signer_table.findall(f"{_W_NS}tr")

        def _row_texts(row):
            return ["".join(t.text or "" for t in c.iter(f"{_W_NS}t")) for c in row.findall(f"{_W_NS}tc")]

        gestionnaire_row = _row_texts(rows[1])
        director_row = _row_texts(rows[2])
        self.assertEqual(gestionnaire_row[0], "مريم التازي")
        self.assertTrue(gestionnaire_row[1].strip())
        self.assertEqual(director_row[0], "سعيد بنعلي")
        self.assertTrue(director_row[1].strip())

    def test_quantity_cells_filled_correctly(self) -> None:
        out = self._write(_test_settings(), ftour_qty=180, ghada_qty=360, asha_qty=90)
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        tables = root.findall(f".//{_W_NS}tbl")
        # signer(0), items(1), remarks(2), signature-labels(3)
        items_table = tables[1]
        rows = items_table.findall(f"{_W_NS}tr")

        def _last_cell_text(row):
            cells = row.findall(f"{_W_NS}tc")
            return "".join(t.text or "" for t in cells[-1].iter(f"{_W_NS}t"))

        self.assertEqual(_last_cell_text(rows[1]), "180")
        self.assertEqual(_last_cell_text(rows[2]), "360")
        self.assertEqual(_last_cell_text(rows[3]), "90")

    def test_bottom_signature_label_row_is_untouched(self) -> None:
        """The final 3-column Directeur/Gestionnaire/Le prestataire row is
        a separate table from the top "Nous soussignons" one — pure
        labels for handwritten signatures, never filled with names,
        matching daily_reception_screen.py's own repeating footer."""
        out = self._write(_test_settings(director="X", gestionnaire="Y"))
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        tables = root.findall(f".//{_W_NS}tbl")
        signature_row_table = tables[-1]
        rows = signature_row_table.findall(f"{_W_NS}tr")
        self.assertEqual(len(rows), 1)
        cells = rows[0].findall(f"{_W_NS}tc")
        texts = ["".join(t.text or "" for t in c.iter(f"{_W_NS}t")) for c in cells]
        self.assertEqual(len(texts), 3)
        for text in texts:
            self.assertNotIn("X", text)
            self.assertNotIn("Y", text)

    def test_remarks_blank_row_height_is_capped(self) -> None:
        """Same shared fix as the daily template — _shrink_reception_
        remarks_blank_row is reused via import, not reimplemented."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        tables = root.findall(f".//{_W_NS}tbl")
        remarks_rows = tables[2].findall(f"{_W_NS}tr")
        trHeight = remarks_rows[1].find(f"{_W_NS}trPr/{_W_NS}trHeight")
        if trHeight is not None:
            val = int(trHeight.get(f"{_W_NS}val"))
            self.assertLessEqual(val, 950)

    def test_header_body_gap_is_widened_a_modest_safety_amount(self) -> None:
        """Same shared fix as the daily template — _fix_reception_header_
        body_gap is reused via import, not reimplemented."""
        out = self._write(_test_settings())
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        pg_mar = root.find(f".//{_W_NS}sectPr/{_W_NS}pgMar")
        header_dist = int(pg_mar.get(f"{_W_NS}header"))
        top_margin = int(pg_mar.get(f"{_W_NS}top"))
        gap_pt = (top_margin - header_dist) / 20
        self.assertGreaterEqual(gap_pt, 20)


if __name__ == "__main__":
    unittest.main()


class MonthlyRamadanMealsTests(unittest.TestCase):
    """محضر التسلم الشهري printed only فطور/غداء/عشاء, because both writers
    passed those three fields by name instead of using the month's own meal
    list. A month CONTAINING Ramadan serves five meal types — the three
    normal ones on its ordinary days plus إفطار/سحور on its Ramadan days —
    so the official record under-reported every Ramadan month."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="مؤسسة", school_year="2025-2026", director="المدير",
            gestionnaire="المسير", company_name="SOC TEST",
            contract_number="07/2026",
            ramadan_start="2026-03-01", ramadan_end="2026-03-20"))
        self._record = MonthlyReceptionRecord(
            month="2026-03", ftour_qty=665, ghada_qty=922, asha_qty=651,
            ftour_ramadan_qty=1714, shour_qty=1204)
        database.save_monthly_reception_record(self._record)

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_a_ramadan_month_lists_five_meals(self) -> None:
        meals = [key for key, _label in mrs._meals_for_month("2026-03")]
        self.assertIn("ftour_ramadan", meals)
        self.assertIn("shour", meals)
        self.assertEqual(len(meals), 5)

    def test_word_export_carries_the_ramadan_quantities(self) -> None:
        path = Path(self._tmpdir.name) / "monthly.docx"
        mrs._write_monthly_reception_docx(
            path, "2026-03", self._record, database.get_school_settings())

        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        self.assertIn("1714", xml, "إفطار quantity missing from the Word output")
        self.assertIn("1204", xml, "سحور quantity missing from the Word output")
        self.assertIn("Le Ftour", xml)
        self.assertIn("Le Shour", xml)

    def test_a_normal_month_gets_no_ramadan_rows(self) -> None:
        record = MonthlyReceptionRecord(
            month="2026-05", ftour_qty=100, ghada_qty=200, asha_qty=300)
        database.save_monthly_reception_record(record)
        path = Path(self._tmpdir.name) / "normal.docx"
        mrs._write_monthly_reception_docx(
            path, "2026-05", record, database.get_school_settings())

        xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        self.assertNotIn("Le Ftour", xml)
        self.assertNotIn("Le Shour", xml)
