import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR,
)
from core.models import DailyContact, SchoolSettings, Student
from data import database
from ui import daily_contact_screen
from ui import daily_contact_screen as dcs


class DailyContactDocumentTests(unittest.TestCase):
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

    def test_document_number_defaults_from_selected_date(self) -> None:
        screen = daily_contact_screen.DailyContactScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))

        self.assertEqual(screen._document_number_text(), "1")

        screen._number_edit.setText("7")
        screen._date_edit.setDate(QDate(2026, 6, 12))

        self.assertEqual(screen._document_number_text(), "7")
        screen.close()

    def test_document_number_advances_after_logged_document(self) -> None:
        screen = daily_contact_screen.DailyContactScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))

        database.record_daily_contact_document(
            "2026-06-11",
            284,
            "save",
            [DailyContact(date="2026-06-11", meal_type="ftour", primary_granted=3)],
        )
        screen._sync_document_number(force=True)

        self.assertEqual(screen._document_number_text(), "285")
        screen.close()

    def test_manual_document_number_is_remembered_for_date(self) -> None:
        screen = daily_contact_screen.DailyContactScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))

        screen._number_edit.setText("901")
        screen.close()

        reopened = daily_contact_screen.DailyContactScreen()
        reopened._date_edit.setDate(QDate(2026, 6, 11))

        self.assertEqual(reopened._document_number_text(), "901")
        reopened.close()

    def test_load_today_does_not_overwrite_manual_mode_values(self) -> None:
        screen = daily_contact_screen.DailyContactScreen()
        ghada = screen._cards[daily_contact_screen.MEAL_GHADA]
        ghada._pg.setValue(9)

        screen._on_load_today_clicked()

        self.assertEqual(ghada._pg.value(), 9)
        self.assertFalse(screen._auto_mode)
        screen.close()

    def test_auto_mode_generates_counts_from_students(self) -> None:
        database.add_student(Student(full_name="A", student_class="السادس ابتدائي", grant_type="منحة كاملة"))
        database.add_student(Student(full_name="B", student_class="الأولى إعدادي", grant_type="وجبة غذاء"))
        database.add_student(Student(full_name="C", student_class="الثانية تأهيلي", grant_type="full"))
        database.add_student(Student(full_name="D", grant_type="full", is_monitor=True))
        database.add_student(Student(full_name="E", student_class="الأولى إعدادي", grant_type="غير صالح"))
        screen = daily_contact_screen.DailyContactScreen()
        screen._on_mode_changed(True)
        screen._on_load_today_clicked()

        ftour = screen._cards[daily_contact_screen.MEAL_FTOUR].to_contact("2026-06-11")
        ghada = screen._cards[daily_contact_screen.MEAL_GHADA].to_contact("2026-06-11")
        asha = screen._cards[daily_contact_screen.MEAL_ASHA].to_contact("2026-06-11")

        self.assertTrue(screen._cards[daily_contact_screen.MEAL_GHADA]._pg.isReadOnly())
        self.assertEqual(ftour.primary_granted, 1)
        self.assertEqual(ftour.primary_complement, 0)
        self.assertEqual(ftour.qualifying_granted, 1)
        self.assertEqual(ftour.monitors, 1)
        self.assertEqual(ghada.primary_granted, 1)
        self.assertEqual(ghada.collegial_complement, 1)
        self.assertEqual(ghada.qualifying_granted, 1)
        self.assertEqual(ghada.monitors, 1)
        self.assertEqual(asha.primary_granted, 1)
        self.assertEqual(asha.collegial_complement, 0)
        self.assertEqual(asha.qualifying_granted, 1)
        self.assertEqual(asha.monitors, 1)
        screen.close()

    def test_auto_generate_warns_instead_of_silently_saving_zeros(self) -> None:
        """Regression: real students with no القسم (class) assigned made
        count_students() classify nobody, so the estimator had zero
        students to work from and silently produced all-zero numbers —
        indistinguishable from the button doing nothing at all. Must warn
        instead of silently generating zeros."""
        database.add_student(Student(full_name="تلميذ بدون قسم", student_class="", grant_type="full"))
        screen = daily_contact_screen.DailyContactScreen()
        screen._on_mode_changed(True)

        screen._on_load_today_clicked()

        self.assertEqual(screen._toast.text(), daily_contact_screen._TOAST_NO_CLASSIFIED_STUDENTS)
        ghada = screen._cards[daily_contact_screen.MEAL_GHADA].to_contact("2026-06-11")
        self.assertEqual(ghada.grand_total, 0)
        screen.close()

    def test_copy_previous_fills_cards_from_last_available_day(self) -> None:
        # 2026-06-10 (a Wednesday) has no saved data — the button should
        # still find 2026-06-09, not just look at the literal day before.
        database.save_daily_contact(DailyContact(
            date="2026-06-09", meal_type=daily_contact_screen.MEAL_GHADA,
            primary_granted=4, collegial_complement=2,
        ))

        screen = daily_contact_screen.DailyContactScreen()
        screen._mode_toggle.set_auto(True)  # switch to auto/read-only mode first
        screen._date_edit.setDate(QDate(2026, 6, 11))

        screen._on_copy_previous_clicked()

        ghada = screen._cards[daily_contact_screen.MEAL_GHADA]
        self.assertEqual(ghada._pg.value(), 4)
        self.assertEqual(ghada._cc.value(), 2)
        self.assertFalse(screen._auto_mode)
        self.assertFalse(ghada._pg.isReadOnly())
        screen.close()

    def test_copy_previous_shows_toast_when_nothing_to_copy(self) -> None:
        screen = daily_contact_screen.DailyContactScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))

        screen._on_copy_previous_clicked()

        self.assertIsNotNone(screen._toast)
        self.assertEqual(screen._toast.text(), daily_contact_screen._TOAST_COPY_NONE)
        screen.close()

    def test_load_button_hidden_until_auto_mode_selected(self) -> None:
        """تحميل اليوم only makes sense in تلقائي mode — showing it in
        يدوي mode would be a dead click with no data-driven reason to
        exist (there's nothing to load, the مسير types the numbers)."""
        screen = daily_contact_screen.DailyContactScreen()
        self.assertTrue(screen._load_btn.isHidden())

        screen._mode_toggle.set_auto(True)
        self.assertFalse(screen._load_btn.isHidden())

        screen._mode_toggle.set_auto(False)
        self.assertTrue(screen._load_btn.isHidden())
        screen.close()

    def test_copy_segment_click_triggers_the_same_copy_action(self) -> None:
        """نسخ الأمس is one segment of the 3-way selector, not a separate
        standalone button anymore — it must still fire the same copy
        logic the old dedicated button called directly."""
        database.save_daily_contact(DailyContact(
            date="2026-06-09", meal_type=daily_contact_screen.MEAL_GHADA,
            primary_granted=9,
        ))
        screen = daily_contact_screen.DailyContactScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))

        screen._mode_toggle._copy_btn.click()

        ghada = screen._cards[daily_contact_screen.MEAL_GHADA]
        self.assertEqual(ghada._pg.value(), 9)
        screen.close()

    def test_copy_segment_settles_selector_back_on_manual(self) -> None:
        """Picking نسخ الأمس while in تلقائي mode must leave the selector
        showing يدوي afterward — matches the data, which becomes freely
        editable once copied in, not still "auto"."""
        database.save_daily_contact(DailyContact(
            date="2026-06-09", meal_type=daily_contact_screen.MEAL_GHADA,
            primary_granted=5,
        ))
        screen = daily_contact_screen.DailyContactScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._mode_toggle.set_auto(True)

        screen._mode_toggle._copy_btn.click()

        self.assertFalse(screen._mode_toggle.is_auto())
        screen.close()

    def test_history_shows_saved_and_printed_documents(self) -> None:
        database.record_daily_contact_document(
            "2026-06-11",
            12,
            "save",
            [DailyContact(date="2026-06-11", meal_type="ftour", primary_granted=3)],
        )
        database.record_daily_contact_document(
            "2026-06-12",
            13,
            "print",
            [DailyContact(date="2026-06-12", meal_type="ghada", primary_granted=4)],
            "daily.docx",
        )
        screen = daily_contact_screen.DailyContactScreen()
        screen._refresh_history()

        self.assertEqual(screen._history_table.rowCount(), 2)
        self.assertEqual(screen._history_table.item(0, 0).text(), "13")
        self.assertEqual(screen._history_table.item(0, 1).text(), "2026-06-12")
        self.assertEqual(screen._history_table.item(0, 2).text(), "طباعة")
        self.assertEqual(screen._history_table.item(1, 2).text(), "حفظ")
        screen.close()

    def test_write_daily_contact_docx_fills_visible_totals(self) -> None:
        contacts = [
            DailyContact(
                date="2026-06-11",
                meal_type="ftour",
                primary_granted=1,
                primary_complement=2,
                collegial_granted=3,
                collegial_complement=4,
                qualifying_granted=5,
                qualifying_complement=6,
                monitors=7,
                monitors_complement=8,
            ),
            DailyContact(
                date="2026-06-11",
                meal_type="ghada",
                primary_granted=10,
                primary_complement=20,
                collegial_granted=30,
                collegial_complement=40,
                qualifying_granted=50,
                qualifying_complement=60,
                monitors=70,
                monitors_complement=80,
            ),
            DailyContact(
                date="2026-06-11",
                meal_type="asha",
                primary_granted=100,
                primary_complement=200,
                collegial_granted=300,
                collegial_complement=400,
                qualifying_granted=500,
                qualifying_complement=600,
                monitors=700,
                monitors_complement=800,
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out = Path(tmp_dir) / "daily_contact.docx"
            daily_contact_screen._write_daily_contact_docx(
                out,
                "2026-06-11",
                contacts,
                document_number="12",
                place="تنغير",
                academy="درعة تافيلالت",
                province="تنغير",
                school_name="الثانوية الإعدادية المدون",
            )

            self.assertTrue(out.exists())
            rows = self._docx_table_rows(out)
            paragraph_text = "\n".join(self._docx_paragraphs(out))
            header_paragraphs = self._docx_header_paragraphs(out)
            header_text = "\n".join(header_paragraphs)

        self.assertIn("2026/06/11", paragraph_text)
        self.assertIn("رقم: 12", paragraph_text)
        self.assertIn("حرر بتنغير بتاريخ 2026/06/11", paragraph_text)
        self.assertIn("الأكاديمية الجهوية للتربية والتكوين لجهة درعة تافيلالت", header_text)
        self.assertIn("المديرية الإقليمية تنغير", header_text)
        self.assertIn("الثانوية الإعدادية المدون", header_text)
        self.assertIn("الأكاديمية الجهوية للتربية والتكوين لجهة درعة تافيلالت", header_text.splitlines())
        self.assertIn("المديرية الإقليمية تنغير", header_text.splitlines())
        self.assertIn("الثانوية الإعدادية المدون", header_text.splitlines())
        self.assertFalse(any("\n" in paragraph for paragraph in header_paragraphs))
        self.assertEqual(rows[3], ["الابتدائي", "1", "2", "10", "20", "100", "200"])
        self.assertEqual(rows[4], ["الإعدادي", "3", "4", "30", "40", "300", "400"])
        self.assertEqual(rows[5], ["التأهيلي", "5", "6", "50", "60", "500", "600"])
        self.assertEqual(rows[6], ["معلمو الداخلية", "7", "8", "70", "80", "700", "800"])
        self.assertEqual(rows[7], ["المجموع", "36", "360", "3600"])

    def test_header_body_gap_is_widened_a_modest_safety_amount(self) -> None:
        """Regression: this template's own page margins put the body zone
        (pgMar/@top) BEFORE the header zone (pgMar/@header) even starts —
        a negative gap, worse than محضر التسلم اليومي's ~3pt version of
        the same pre-existing template design issue. The header's own
        3-line academy/directorate/school block needs ~45-50pt to lay
        out without colliding with the body's first paragraph."""
        contacts = [DailyContact(date="2026-06-11", meal_type=m) for m in ("ftour", "ghada", "asha")]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = Path(tmp_dir) / "daily_contact.docx"
            daily_contact_screen._write_daily_contact_docx(
                out, "2026-06-11", contacts,
                document_number="1", place="تنغير", academy="درعة تافيلالت",
                province="تنغير", school_name="الثانوية الإعدادية المدون",
            )
            with ZipFile(out) as z:
                root = ET.fromstring(z.read("word/document.xml"))

        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        pg_mar = root.find(f".//{W}sectPr/{W}pgMar")
        header_dist = int(pg_mar.get(f"{W}header"))
        top_margin = int(pg_mar.get(f"{W}top"))
        gap_pt = (top_margin - header_dist) / 20
        self.assertGreaterEqual(gap_pt, 20)

    def _docx_paragraphs(self, path: Path) -> list[str]:
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(path) as docx:
            root = ET.fromstring(docx.read("word/document.xml"))
        return [
            "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()
            for paragraph in root.findall(".//w:p", ns)
        ]

    def _docx_table_rows(self, path: Path) -> list[list[str]]:
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(path) as docx:
            root = ET.fromstring(docx.read("word/document.xml"))
        table = root.findall(".//w:tbl", ns)[0]
        return [
            [
                "".join(node.text or "" for node in cell.findall(".//w:t", ns)).strip()
                for cell in row.findall("./w:tc", ns)
            ]
            for row in table.findall("./w:tr", ns)
        ]

    def _docx_header_paragraphs(self, path: Path) -> list[str]:
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(path) as docx:
            header_names = [name for name in docx.namelist() if name.startswith("word/header") and name.endswith(".xml")]
            roots = [ET.fromstring(docx.read(name)) for name in header_names]
        return [
            "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()
            for root in roots
            for paragraph in root.findall(".//w:p", ns)
        ]


class DailyContactRamadanTests(unittest.TestCase):
    """During Ramadan the school serves إفطار + سحور instead of the three
    normal meals, so this screen must collect and save those instead."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية اختبار", school_year="2025/2026", director="مدير",
            ramadan_start="2026-02-18", ramadan_end="2026-03-19",
        ))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _screen_on(self, year: int, month: int, day: int):
        screen = dcs.DailyContactScreen()
        screen.show()
        screen._date_edit.setDate(QDate(year, month, day))
        self.app.processEvents()
        return screen

    def test_normal_day_shows_and_saves_the_three_normal_meals(self) -> None:
        screen = self._screen_on(2026, 1, 15)
        visible = [k for k, c in screen._cards.items() if c.isVisible()]
        self.assertEqual(visible, [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA])
        self.assertEqual(
            [c.meal_type for c in screen._current_contacts()],
            [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA])
        screen.close()

    def test_ramadan_day_swaps_to_iftar_and_shour(self) -> None:
        screen = self._screen_on(2026, 3, 1)
        visible = [k for k, c in screen._cards.items() if c.isVisible()]
        self.assertEqual(visible, [MEAL_IFTAR, MEAL_SHOUR])
        # A Ramadan day must not write empty normal-meal rows either.
        self.assertEqual(
            [c.meal_type for c in screen._current_contacts()],
            [MEAL_IFTAR, MEAL_SHOUR])
        screen.close()

    def test_a_day_override_flips_the_meal_set(self) -> None:
        """The moon sighting can move Ramadan by a day, so a single-day
        correction has to change which meals the screen collects."""
        database.set_ramadan_override("2026-03-20", True)   # just after the range
        screen = self._screen_on(2026, 3, 20)
        self.assertEqual(
            [c.meal_type for c in screen._current_contacts()],
            [MEAL_IFTAR, MEAL_SHOUR])
        screen.close()

    def test_ramadan_counts_round_trip_through_the_database(self) -> None:
        screen = self._screen_on(2026, 3, 1)
        screen._cards[MEAL_IFTAR]._cg.setValue(42)
        for contact in screen._current_contacts():
            database.save_daily_contact(contact)
        saved = {c.meal_type: c for c in database.get_day_contacts("2026-03-01")}
        self.assertIn(MEAL_IFTAR, saved)
        self.assertEqual(saved[MEAL_IFTAR].collegial_granted, 42)
        self.assertNotIn(MEAL_GHADA, saved)
        screen.close()


    def test_word_sheet_prints_two_meal_columns_during_ramadan(self) -> None:
        """The user asked for the SAME official sheet with two columns
        instead of three on a Ramadan day, so the template's 7-column meal
        table is trimmed to 5 rather than replaced."""
        out = Path(self._tmpdir.name) / "ramadan.docx"
        dcs._write_daily_contact_docx(
            out, "2026-03-01",
            [DailyContact(date="2026-03-01", meal_type=m, collegial_granted=7)
             for m in (MEAL_IFTAR, MEAL_SHOUR)],
            document_number="2", place="ألمدون",
        )
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(out) as docx:
            table = ET.fromstring(docx.read("word/document.xml")).findall(".//w:tbl", ns)[0]
        rows = table.findall("./w:tr", ns)

        def texts(row):
            return ["".join(t.text or "" for t in c.findall(".//w:t", ns)).strip()
                    for c in row.findall("./w:tc", ns)]

        self.assertEqual(texts(rows[1]), ["", "إفطار", "سحور"])
        self.assertEqual(len(rows[3].findall("./w:tc", ns)), 5)   # label + 2 meals x 2
        self.assertEqual(
            len(table.find("./w:tblGrid", ns).findall("./w:gridCol", ns)), 5)
        # The recorded counts still land in the right cells.
        self.assertEqual(texts(rows[4]), ["الإعدادي", "7", "0", "7", "0"])

    def test_word_sheet_keeps_three_columns_on_a_normal_day(self) -> None:
        out = Path(self._tmpdir.name) / "normal.docx"
        dcs._write_daily_contact_docx(
            out, "2026-01-15",
            [DailyContact(date="2026-01-15", meal_type=m, collegial_granted=10)
             for m in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA)],
            document_number="1", place="ألمدون",
        )
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(out) as docx:
            table = ET.fromstring(docx.read("word/document.xml")).findall(".//w:tbl", ns)[0]
        rows = table.findall("./w:tr", ns)
        self.assertEqual(len(rows[3].findall("./w:tc", ns)), 7)
        self.assertEqual(
            len(table.find("./w:tblGrid", ns).findall("./w:gridCol", ns)), 7)


if __name__ == "__main__":
    unittest.main()


class DateChangeReloadsTests(unittest.TestCase):
    """Picking a date from the calendar must load THAT date's saved numbers.
    The prev/next buttons always reloaded, but changing the date directly did
    not — so an export produced a document stamped with the new date while
    carrying the previously-loaded day's figures."""

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

    def test_changing_the_date_loads_that_dates_numbers(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-05-11", meal_type=dcs.MEAL_GHADA, collegial_granted=40))
        database.save_daily_contact(DailyContact(
            date="2026-05-12", meal_type=dcs.MEAL_GHADA, collegial_granted=17))

        screen = dcs.DailyContactScreen()
        screen.show()
        screen._date_edit.setDate(QDate(2026, 5, 11))
        self.app.processEvents()
        self.assertEqual(
            screen._cards[dcs.MEAL_GHADA].to_contact("2026-05-11").grand_total, 40)

        # ...and switching again must not leave the first day's numbers behind
        screen._date_edit.setDate(QDate(2026, 5, 12))
        self.app.processEvents()
        self.assertEqual(
            screen._cards[dcs.MEAL_GHADA].to_contact("2026-05-12").grand_total, 17)
        screen.close()

    def test_moving_to_a_date_with_no_data_clears_the_previous_day(self) -> None:
        """The worst case: stale numbers exported under a fresh date."""
        database.save_daily_contact(DailyContact(
            date="2026-05-11", meal_type=dcs.MEAL_GHADA, collegial_granted=40))

        screen = dcs.DailyContactScreen()
        screen.show()
        screen._date_edit.setDate(QDate(2026, 5, 11))
        self.app.processEvents()
        screen._date_edit.setDate(QDate(2026, 5, 20))   # nothing saved here
        self.app.processEvents()

        self.assertEqual(
            screen._cards[dcs.MEAL_GHADA].to_contact("2026-05-20").grand_total, 0)
        screen.close()
