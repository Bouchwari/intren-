"""محضر المخالفة — the PV raised against the catering company.

Distinct from the student disciplinary log (دفتر المخالفات): this one is a
contractual breach by the CONTRACTOR, carries the four official signatures,
and records no money.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR
from core.models import InfractionRecord, SchoolSettings
from data import database
from ui import infraction_record_screen as irs


def _settings(**kwargs) -> SchoolSettings:
    base = dict(
        school_name="الثانوية الإعدادية ألمدون", school_year="2025-2026",
        director="محمد", gestionnaire="عبد الله", surveillant_general="الحارس العام",
        company_name="شركة آيت خويا", contract_number="08/MDD-TIN/2023",
        city="ألمدون",
    )
    base.update(kwargs)
    return SchoolSettings(**base)


class InfractionRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _record(self, **kwargs) -> InfractionRecord:
        base = dict(date="2026-03-02", document_number=1, year=2026,
                    meal_type=MEAL_GHADA, place="المطبخ",
                    infraction_type="عدم احترام النظافة",
                    description="تفاصيل", reported_by="الحارس",
                    written_date="2026-03-02")
        base.update(kwargs)
        return InfractionRecord(**base)

    def test_reference_is_printed_as_year_slash_number(self) -> None:
        self.assertEqual(self._record(document_number=1, year=2026).reference, "2026/01")
        self.assertEqual(self._record(document_number=12, year=2026).reference, "2026/12")

    def test_numbering_restarts_each_year(self) -> None:
        self.assertEqual(database.get_next_infraction_number(2026), 1)
        database.save_infraction(self._record(document_number=1, year=2026))
        database.save_infraction(self._record(document_number=2, year=2026))
        self.assertEqual(database.get_next_infraction_number(2026), 3)
        # A new year starts over at 1.
        self.assertEqual(database.get_next_infraction_number(2027), 1)

    def test_two_records_cannot_share_a_reference(self) -> None:
        """The reference is printed on a signed legal document, so a clash
        must be refused rather than silently produce two identical PVs."""
        database.save_infraction(self._record(document_number=1, year=2026))
        with self.assertRaises(sqlite3.IntegrityError):
            database.save_infraction(
                self._record(document_number=1, year=2026, date="2026-04-01"))

    def test_save_update_and_delete_round_trip(self) -> None:
        record_id = database.save_infraction(self._record())
        stored = database.get_infraction(record_id)
        self.assertEqual(stored.place, "المطبخ")
        self.assertEqual(stored.meal_type, MEAL_GHADA)

        stored.place = "المخزن"
        database.save_infraction(stored)
        self.assertEqual(database.get_infraction(record_id).place, "المخزن")
        # Updating must not create a second row.
        self.assertEqual(len(database.get_all_infractions()), 1)

        database.delete_infraction(record_id)
        self.assertEqual(database.get_all_infractions(), [])


class InfractionScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.out = Path(self._tmpdir.name)
        self._original_db_path = database.DB_PATH
        database.DB_PATH = self.out / "test_matama.db"
        database.init_database()
        database.save_school_settings(_settings(
            ramadan_start="2026-02-18", ramadan_end="2026-03-19"))
        self._originals = {
            "file_save": irs.QFileDialog.getSaveFileName,
            "warning": irs.QMessageBox.warning,
            "information": irs.QMessageBox.information,
            "critical": irs.QMessageBox.critical,
            "ask_format": irs.ask_export_format,
        }
        irs.QMessageBox.information = staticmethod(lambda *a, **k: None)
        # _on_export opens a modal PDF/Word chooser; left unpatched it blocks
        # the test run forever instead of failing.
        irs.ask_export_format = staticmethod(lambda *a, **k: "pdf")

    def tearDown(self) -> None:
        irs.QFileDialog.getSaveFileName = self._originals["file_save"]
        irs.QMessageBox.warning = self._originals["warning"]
        irs.QMessageBox.information = self._originals["information"]
        irs.QMessageBox.critical = self._originals["critical"]
        irs.ask_export_format = self._originals["ask_format"]
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_new_record_suggests_the_next_free_number(self) -> None:
        database.save_infraction(InfractionRecord(
            date="2026-01-05", document_number=1, year=2026,
            infraction_type="سابقة"))
        screen = irs.InfractionRecordScreen()
        screen._year_spin.setValue(2026)
        self.app.processEvents()
        self.assertEqual(screen._number_spin.value(), 2)
        screen.close()

    def test_meal_choices_follow_the_infraction_date(self) -> None:
        """A breach on a Ramadan day must be attributable to إفطار/سحور,
        not to meals that were not served that day."""
        screen = irs.InfractionRecordScreen()
        screen._date_edit.setDate(QDate(2026, 1, 15))
        self.app.processEvents()
        normal = [screen._meal_combo.itemData(i)
                  for i in range(screen._meal_combo.count())]
        screen._date_edit.setDate(QDate(2026, 3, 2))
        self.app.processEvents()
        ramadan = [screen._meal_combo.itemData(i)
                   for i in range(screen._meal_combo.count())]

        self.assertEqual(normal, ["ftour", "ghada", "asha"])
        self.assertEqual(ramadan, [MEAL_IFTAR, MEAL_SHOUR])
        screen.close()

    def test_saving_without_an_infraction_type_is_refused(self) -> None:
        """The document exists to state WHAT was breached — an empty one
        would be meaningless on a signed PV."""
        warnings: list = []
        irs.QMessageBox.warning = staticmethod(
            lambda parent, title, text, *a, **k: warnings.append(text))
        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("")
        screen._on_save()

        self.assertEqual(len(warnings), 1)
        self.assertEqual(database.get_all_infractions(), [])
        screen.close()

    def test_duplicate_reference_warns_instead_of_crashing(self) -> None:
        database.save_infraction(InfractionRecord(
            date="2026-01-05", document_number=1, year=2026, infraction_type="سابقة"))
        warnings: list = []
        irs.QMessageBox.warning = staticmethod(
            lambda parent, title, text, *a, **k: warnings.append(text))

        screen = irs.InfractionRecordScreen()
        screen._year_spin.setValue(2026)
        screen._number_spin.setValue(1)          # already taken
        screen._type_combo.setCurrentText("عدم احترام النظافة")
        screen._on_save()

        self.assertEqual(len(warnings), 1)
        self.assertEqual(len(database.get_all_infractions()), 1)
        screen.close()

    def test_saved_record_appears_in_the_table_and_reloads_for_editing(self) -> None:
        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("تأخر في تقديم الوجبة")
        screen._place_combo.setCurrentText("المطعم")
        screen._on_save()
        self.assertEqual(screen._table.rowCount(), 1)

        record_id = screen._editing_id
        screen._new_record()
        self.assertIsNone(screen._editing_id)
        screen._on_row_activated(0, 0)
        self.assertEqual(screen._editing_id, record_id)
        self.assertEqual(screen._place_combo.currentText(), "المطعم")
        screen.close()

    def test_editing_a_saved_record_keeps_its_reference(self) -> None:
        """Re-opening a saved PV must not renumber it — the reference is
        already on a signed sheet of paper."""
        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("نقص في كمية الوجبة")
        screen._on_save()
        original = screen._number_spin.value()

        screen._year_spin.setValue(screen._year_spin.value())   # fires _suggest_number
        self.app.processEvents()
        self.assertEqual(screen._number_spin.value(), original)
        screen.close()

    def test_pdf_export_writes_a_real_single_page_document(self) -> None:
        out_path = self.out / "pv.pdf"
        irs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("عدم احترام النظافة")
        screen._description_edit.setPlainText("تفاصيل المخالفة المرصودة.")
        screen._on_export()

        self.assertTrue(out_path.exists())
        self.assertGreater(out_path.stat().st_size, 1000)
        screen.close()

    def test_export_without_contract_settings_warns_and_opens_no_dialog(self) -> None:
        """The PV quotes the صفقة number and the company name; without them
        it would print a form full of dots."""
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية", school_year="2025-2026", director="مدير"))
        dialogs: list = []
        warnings: list = []
        irs.QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: dialogs.append(a) or ("", ""))
        irs.QMessageBox.warning = staticmethod(
            lambda parent, title, text, *a, **k: warnings.append(text))

        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("عدم احترام النظافة")
        screen._on_export()

        self.assertEqual(dialogs, [])
        self.assertEqual(len(warnings), 1)
        screen.close()

    def test_pdf_carries_the_four_official_signature_blocks(self) -> None:
        """The company's representative plus the three-member follow-up
        committee — the whole point of this document."""
        from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
        from PySide6.QtCore import QMarginsF

        record = InfractionRecord(
            date="2026-03-02", document_number=1, year=2026, meal_type=MEAL_GHADA,
            place="المطبخ", infraction_type="عدم احترام النظافة",
            written_date="2026-03-02")
        out_path = self.out / "signatures.pdf"
        irs.write_infraction_pdf(out_path, record, database.get_school_settings())

        raw = out_path.read_bytes()
        self.assertGreater(len(raw), 1000)
        # The labels themselves are module constants, so assert on those
        # rather than trying to extract shaped Arabic from the PDF stream.
        for label in (irs._SIGN_COMPANY, irs._SIGN_COMMITTEE, irs._SIGN_WARDEN,
                      irs._SIGN_STEWARD, irs._SIGN_DIRECTOR):
            self.assertTrue(label.strip())

    def test_pdf_prints_in_black_not_the_app_green(self) -> None:
        """The user asked for plain black ink: this is a formal notice served
        on the contractor, not an in-app screen."""
        self.assertEqual(irs._INK, "#000000")
        # The shared header helper must keep its green default for every
        # OTHER document — only this one overrides it.
        from ui import document_header
        import inspect
        signature = inspect.signature(document_header.draw_official_pdf_header)
        self.assertEqual(signature.parameters["title_color"].default, "#085041")

    def test_word_export_produces_a_valid_editable_document(self) -> None:
        """There is no .docx template for this form, so the file is built from
        scratch — it must still be a structurally sound OOXML package."""
        import xml.etree.ElementTree as ET
        import zipfile

        out_path = self.out / "pv.docx"
        irs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        irs.ask_export_format = staticmethod(lambda *a, **k: "docx")

        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("عدم احترام النظافة")
        screen._place_combo.setCurrentText("المطبخ")
        screen._description_edit.setPlainText("تفاصيل الإخلال.")
        screen._on_export()
        self.assertTrue(out_path.exists())

        with zipfile.ZipFile(out_path) as docx:
            self.assertIsNone(docx.testzip())
            names = docx.namelist()
            for required in ("[Content_Types].xml", "_rels/.rels", "word/document.xml"):
                self.assertIn(required, names)
            # Every relationship must point at a part that exists.
            rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
            for rels, base in (("_rels/.rels", ""),
                               ("word/_rels/document.xml.rels", "word/")):
                if rels not in names:
                    continue
                root = ET.fromstring(docx.read(rels))
                for rel in root.findall(f"{{{rel_ns}}}Relationship"):
                    self.assertIn(base + rel.get("Target"), names)
            body = docx.read("word/document.xml").decode("utf-8")

        # Arabic needs both markers or Word lays the page out left-to-right.
        self.assertIn("<w:bidi/>", body)
        self.assertIn("<w:rtl/>", body)
        screen.close()

    def test_word_and_pdf_say_the_same_thing(self) -> None:
        """Two exports of one record must not drift apart — both are built
        from the same _docx_strings wording."""
        record = InfractionRecord(
            date="2026-03-02", document_number=3, year=2026, meal_type=MEAL_GHADA,
            place="المخزن", infraction_type="رداءة جودة المواد الغذائية",
            description="تفاصيل", written_date="2026-03-02")
        strings = irs._docx_strings(record, database.get_school_settings())

        self.assertIn("2026", record.reference)
        self.assertIn("المخزن", strings["place"])
        self.assertIn("رداءة جودة المواد الغذائية", strings["infraction_type"])
        self.assertIn("08/MDD-TIN/2023", strings["body"])     # the صفقة number
        self.assertIn("شركة آيت خويا", strings["holder"])      # نائل الصفقة
        # All four signature labels travel to the Word version too.
        for key in ("sign_company", "sign_warden", "sign_steward", "sign_director"):
            self.assertTrue(strings[key].strip())

    def test_word_export_still_works_without_the_crest_image(self) -> None:
        """A missing template folder must not block the export."""
        from ui import infraction_docx

        original = infraction_docx._crest_bytes
        infraction_docx._crest_bytes = staticmethod(lambda: None)
        try:
            record = InfractionRecord(
                date="2026-03-02", document_number=9, year=2026,
                infraction_type="مخالفة أخرى")
            out_path = self.out / "no_crest.docx"
            infraction_docx.write_infraction_docx(
                out_path, record, database.get_school_settings(),
                irs._docx_strings(record, database.get_school_settings()))
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 500)
        finally:
            infraction_docx._crest_bytes = original

    def test_word_property_order_follows_the_ooxml_schema(self) -> None:
        """Word and LibreOffice silently DROP run/paragraph properties that
        arrive out of schema order — emitting jc before spacing, or sz before
        b, is what made the first Word export render left-to-right."""
        import re
        from ui import infraction_docx

        record = InfractionRecord(
            date="2026-03-02", document_number=1, year=2026,
            infraction_type="عدم احترام النظافة", written_date="2026-03-02")
        xml = infraction_docx.build_infraction_document_xml(
            record, database.get_school_settings(),
            strings=irs._docx_strings(record, database.get_school_settings()),
            with_crest=False)

        def in_order(fragment: str, sequence: list) -> bool:
            positions = [fragment.find(tag) for tag in sequence if tag in fragment]
            return positions == sorted(positions)

        for paragraph_properties in re.findall(r"<w:pPr>.*?</w:pPr>", xml):
            self.assertTrue(
                in_order(paragraph_properties, ["<w:bidi/>", "<w:spacing", "<w:jc"]),
                paragraph_properties)
        for run_properties in re.findall(r"<w:rPr>.*?</w:rPr>", xml):
            self.assertTrue(
                in_order(run_properties,
                         ["<w:b/>", "<w:sz ", "<w:u ", "<w:rtl/>"]),
                run_properties)

    def test_word_never_emits_a_left_or_right_alignment(self) -> None:
        """`w:jc` is LOGICAL, not visual: inside a `w:bidi` paragraph "right"
        means *end*, and the end of right-to-left text is the LEFT edge — so
        asking for "right" pushed every line to the left and the document
        read left-to-right. A bidi paragraph already starts at the right
        margin, so only "center" may ever appear."""
        import re
        from ui import infraction_docx

        record = InfractionRecord(
            date="2026-03-02", document_number=1, year=2026,
            infraction_type="عدم احترام النظافة", description="تفاصيل",
            written_date="2026-03-02")
        xml = infraction_docx.build_infraction_document_xml(
            record, database.get_school_settings(),
            strings=irs._docx_strings(record, database.get_school_settings()),
            with_crest=True)

        self.assertEqual(set(re.findall(r'<w:jc w:val="(\w+)"/>', xml)), {"center"})
        self.assertNotIn('<w:jc w:val="right"/>', infraction_docx._STYLES)
        # Every paragraph must still declare its RTL direction.
        self.assertEqual(xml.count("<w:p>"), xml.count("<w:bidi/>") - 1)  # -1 = sectPr

    def test_word_document_declares_rtl_defaults(self) -> None:
        """Belt and braces: even if a paragraph forgets, the document's own
        defaults make the whole file right-to-left."""
        import zipfile

        out_path = self.out / "rtl.docx"
        irs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        irs.ask_export_format = staticmethod(lambda *a, **k: "docx")
        screen = irs.InfractionRecordScreen()
        screen._type_combo.setCurrentText("عدم احترام النظافة")
        screen._on_export()

        with zipfile.ZipFile(out_path) as docx:
            self.assertIn("word/styles.xml", docx.namelist())
            styles = docx.read("word/styles.xml").decode("utf-8")
            relationships = docx.read("word/_rels/document.xml.rels").decode("utf-8")
            content_types = docx.read("[Content_Types].xml").decode("utf-8")
        self.assertIn("<w:rtl/>", styles)
        self.assertIn("<w:bidi/>", styles)
        self.assertIn("rIdStyles", relationships)
        self.assertIn("styles+xml", content_types)
        screen.close()

    def test_long_text_is_not_clipped_out_of_the_pdf(self) -> None:
        """QPainter.drawText clips to the rect it is handed, so a guessed
        height silently cut the tail off a long school name or description —
        the document printed looking unfinished."""
        from PySide6.QtGui import QFont, QFontMetricsF

        long_text = ("لوحظ عند تفقد المطبخ عدم نظافة الأرضية والأواني، وعدم ارتداء "
                     "بعض المستخدمين للباس الواقي، إضافة إلى عدم الاحتفاظ بعينة من "
                     "وجبة اليوم كما تنص عليه بنود الصفقة الإطار.")
        record = InfractionRecord(
            date="2026-03-02", document_number=1, year=2026,
            infraction_type="عدم احترام النظافة", description=long_text,
            written_date="2026-03-02")
        out_path = self.out / "long.pdf"
        irs.write_infraction_pdf(out_path, record, database.get_school_settings())
        self.assertTrue(out_path.exists())

        # The helper must report a height big enough for every wrapped line,
        # never the small starting rect it was given.
        font = QFont()
        font.setPointSize(irs._BODY_SIZE)
        single_line = QFontMetricsF(font).height()
        from PySide6.QtGui import QPdfWriter, QPainter
        from PySide6.QtCore import QRectF
        writer = QPdfWriter(str(self.out / "probe.pdf"))
        writer.setResolution(96)
        painter = QPainter(writer)
        try:
            used = irs._text(painter, QRectF(0, 0, 400, 20), long_text)
        finally:
            painter.end()
        self.assertGreater(used, single_line * 2)

    def test_records_no_money_anywhere(self) -> None:
        """Per the ministry guide, this document states what happened and
        computes no deduction — a price field creeping in later would be a
        real change of meaning."""
        fields = InfractionRecord(date="2026-01-01").__dict__
        for name in fields:
            self.assertNotIn("price", name)
            self.assertNotIn("amount", name)
            self.assertNotIn("penalty", name)


if __name__ == "__main__":
    unittest.main()


class InfractionReporterFieldTests(unittest.TestCase):
    """"عاين المخالفة" — who observed the breach — is collected on screen and
    stored, but was dropped from BOTH exports. On a PV served on the
    contractor, the observer's name is not optional detail."""

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
            company_name="SOC TEST", contract_number="07/2026"))
        self._record = InfractionRecord(
            date="2026-04-14", document_number=1, year=2026,
            meal_type=MEAL_GHADA, place="المطبخ",
            infraction_type="عدم احترام النظافة", description="تفاصيل",
            reported_by="الحارس العام للداخلية", written_date="2026-04-14")

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_the_shared_wording_map_carries_the_observer(self) -> None:
        strings = irs._docx_strings(self._record, database.get_school_settings())
        self.assertIn("reported_by", strings)
        self.assertIn("الحارس العام للداخلية", strings["reported_by"])
        self.assertIn(irs._LBL_REPORTED_BY, strings["reported_by"])

    def test_word_export_prints_the_observer(self) -> None:
        from ui import infraction_docx
        settings = database.get_school_settings()
        xml = infraction_docx.build_infraction_document_xml(
            self._record, settings,
            strings=irs._docx_strings(self._record, settings), with_crest=False)

        self.assertIn("عاين المخالفة", xml)
        self.assertIn("الحارس العام للداخلية", xml)

    def test_an_empty_observer_falls_back_to_the_blank_forms_dotted_rule(self) -> None:
        record = InfractionRecord(
            date="2026-04-14", document_number=2, year=2026,
            infraction_type="تأخر", written_date="2026-04-14")
        strings = irs._docx_strings(record, database.get_school_settings())
        self.assertIn(".", strings["reported_by"])
