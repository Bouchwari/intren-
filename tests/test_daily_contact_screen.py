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

from core.models import DailyContact, Student
from data import database
from ui import daily_contact_screen


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


if __name__ == "__main__":
    unittest.main()
