"""Locks in the CURRENT behavior of DailyContactScreen._student_category and
_student_grant_kind before Stage 1.5 moves this logic into core/. These tests
describe what the code does today — they must not be "fixed" to match some
idea of correct behavior. If a test fails, the test is wrong, not the code.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from data import database
from ui import daily_contact_screen


def fake_student(
    student_class: str = "",
    cycle: str = "",
    education_type: str = "",
    is_monitor: bool = False,
    grant_type: str = "",
    grant_number: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        student_class=student_class,
        cycle=cycle,
        education_type=education_type,
        is_monitor=is_monitor,
        grant_type=grant_type,
        grant_number=grant_number,
    )


class StudentCategoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self.screen = daily_contact_screen.DailyContactScreen()

    def tearDown(self) -> None:
        self.screen.close()
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    # -- plain spellings -------------------------------------------------

    def test_primary_class_text(self) -> None:
        student = fake_student(student_class="السادس ابتدائي")
        self.assertEqual(self.screen._student_category(student), "primary")

    def test_collegial_class_text(self) -> None:
        student = fake_student(student_class="الأولى إعدادي")
        self.assertEqual(self.screen._student_category(student), "collegial")

    def test_qualifying_class_text(self) -> None:
        student = fake_student(student_class="الثانية تأهيلي")
        self.assertEqual(self.screen._student_category(student), "qualifying")

    # -- أ / إ / آ instead of ا, to prove normalisation works -------------

    def test_primary_normalises_hamza_variants(self) -> None:
        for variant in ("السادس أبتدائي", "السادس إبتدائي", "السادس آبتدائي"):
            with self.subTest(variant=variant):
                student = fake_student(student_class=variant)
                self.assertEqual(self.screen._student_category(student), "primary")

    def test_collegial_normalises_hamza_variants(self) -> None:
        for variant in ("الأولى أعدادي", "الأولى إعدادي", "الأولى آعدادي"):
            with self.subTest(variant=variant):
                student = fake_student(student_class=variant)
                self.assertEqual(self.screen._student_category(student), "collegial")

    def test_qualifying_normalises_hamza_variants(self) -> None:
        for variant in ("الثانية تأهيلي", "الثانية تإهيلي", "الثانية تآهيلي"):
            with self.subTest(variant=variant):
                student = fake_student(student_class=variant)
                self.assertEqual(self.screen._student_category(student), "qualifying")

    # -- other paths -------------------------------------------------------

    def test_monitor_flag_overrides_class_text(self) -> None:
        student = fake_student(student_class="الأولى إعدادي", is_monitor=True)
        self.assertEqual(self.screen._student_category(student), "monitors")

    def test_monitor_with_no_class_text(self) -> None:
        student = fake_student(is_monitor=True)
        self.assertEqual(self.screen._student_category(student), "monitors")

    def test_unmatched_class_text_returns_none(self) -> None:
        student = fake_student(student_class="غير معروف")
        self.assertIsNone(self.screen._student_category(student))

    def test_empty_class_text_returns_none(self) -> None:
        student = fake_student()
        self.assertIsNone(self.screen._student_category(student))

    def test_cycle_and_education_type_are_also_checked(self) -> None:
        student = fake_student(cycle="تأهيلي")
        self.assertEqual(self.screen._student_category(student), "qualifying")
        student = fake_student(education_type="ابتدائي")
        self.assertEqual(self.screen._student_category(student), "primary")


class StudentGrantKindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self.screen = daily_contact_screen.DailyContactScreen()

    def tearDown(self) -> None:
        self.screen.close()
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_grant_type_full(self) -> None:
        student = fake_student(grant_type="full")
        self.assertEqual(self.screen._student_grant_kind(student), "full")

    def test_grant_type_half(self) -> None:
        student = fake_student(grant_type="half")
        self.assertEqual(self.screen._student_grant_kind(student), "lunch")

    def test_grant_type_arabic_full_grant_text(self) -> None:
        student = fake_student(grant_type="منحة كاملة")
        self.assertEqual(self.screen._student_grant_kind(student), "full")

    def test_grant_type_arabic_lunch_only_text(self) -> None:
        student = fake_student(grant_type="وجبة غذاء")
        self.assertEqual(self.screen._student_grant_kind(student), "lunch")

    def test_unrecognised_grant_type_returns_none(self) -> None:
        student = fake_student(grant_type="غير صالح")
        self.assertIsNone(self.screen._student_grant_kind(student))

    def test_empty_grant_type_returns_none(self) -> None:
        student = fake_student()
        self.assertIsNone(self.screen._student_grant_kind(student))


if __name__ == "__main__":
    unittest.main()
