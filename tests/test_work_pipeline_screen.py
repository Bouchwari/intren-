import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import EXPORT_FORMAT_PDF
from core.models import DailyContact, Student
from data import database
from core.document_pipeline import DOC_ABSENCE, DOC_CONTACT, DOC_ORDER_LETTER, DOC_REPORT
from ui import work_pipeline_screen as wps


class _FakeGenerateDialog:
    """Stand-in for _GenerateEverythingDialog — avoids a real modal
    QDialog.exec() event loop under the offscreen platform."""

    def __init__(self, start: QDate, end: QDate, doc_keys, auto_fill: bool) -> None:
        self._choice = (start, end, doc_keys, auto_fill)

    def __call__(self, _default_date, _parent):
        return self

    def exec(self) -> int:
        return QDialog.DialogCode.Accepted

    def result_choice(self):
        return self._choice


class WorkPipelineScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._db_tmpdir = tempfile.TemporaryDirectory()
        self._out_tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._db_tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_document_export_format(EXPORT_FORMAT_PDF)
        self._original_info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.information = self._original_info
        database.DB_PATH = self._original_db_path
        self._db_tmpdir.cleanup()
        self._out_tmpdir.cleanup()

    def test_refresh_reflects_saved_data(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type="ghada", collegial_granted=5))

        screen = wps.WorkPipelineScreen(navigate_to=lambda i: None)
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen.refresh()

        self.assertEqual(screen._cards_container.count(), 4)
        screen.close()

    def test_fix_button_navigates_to_the_right_screen(self) -> None:
        from ui.widgets.icon_button import IconButton

        seen = []
        screen = wps.WorkPipelineScreen(navigate_to=lambda i: seen.append(i))
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen.refresh()  # nothing saved for this date -> all 4 cards show a fix button

        first_card = screen._cards_container.itemAt(0).widget()
        fix_btn = first_card.findChildren(IconButton)[0]
        fix_btn.click()

        self.assertEqual(seen, [wps._DOC_TARGET_SCREEN[DOC_CONTACT]])
        screen.close()

    def test_order_letter_fix_button_navigates_to_the_right_screen(self) -> None:
        from ui.widgets.icon_button import IconButton

        seen = []
        screen = wps.WorkPipelineScreen(navigate_to=lambda i: seen.append(i))
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen.refresh()  # nothing saved for this date -> all 4 cards show a fix button

        order_letter_card = screen._cards_container.itemAt(3).widget()
        fix_btn = order_letter_card.findChildren(IconButton)[0]
        fix_btn.click()

        self.assertEqual(seen, [wps._DOC_TARGET_SCREEN[DOC_ORDER_LETTER]])
        screen.close()

    def test_generate_everything_auto_fills_and_exports_selected_documents(self) -> None:
        for name in ("تلميذ 1", "تلميذ 2", "تلميذ 3"):
            database.add_student(Student(
                full_name=name, student_class="الأولى إعدادي", grant_type="منحة كاملة",
            ))

        screen = wps.WorkPipelineScreen(navigate_to=lambda i: None)
        fake_dialog = _FakeGenerateDialog(
            QDate(2026, 6, 11), QDate(2026, 6, 12), [DOC_CONTACT, DOC_ABSENCE], True,
        )
        with patch.object(wps, "_GenerateEverythingDialog", fake_dialog), \
             patch.object(QFileDialog, "getExistingDirectory", return_value=self._out_tmpdir.name):
            screen._on_generate_everything()

        # Data was auto-filled for both days.
        for day in ("2026-06-11", "2026-06-12"):
            self.assertNotEqual(database.get_day_contacts(day), [])
            self.assertNotEqual(database.get_day_absences(day), [])

        # Two combined PDFs were written (contact + absence), report was not requested.
        written = sorted(p.name for p in Path(self._out_tmpdir.name).glob("*.pdf"))
        self.assertEqual(len(written), 2)
        self.assertTrue(any("الاتصال" in name for name in written))
        self.assertTrue(any("الغياب" in name for name in written))
        screen.close()

    def test_generate_everything_without_auto_fill_only_exports(self) -> None:
        database.save_daily_contact(DailyContact(date="2026-06-11", meal_type="ghada", collegial_granted=5))

        screen = wps.WorkPipelineScreen(navigate_to=lambda i: None)
        fake_dialog = _FakeGenerateDialog(
            QDate(2026, 6, 11), QDate(2026, 6, 11), [DOC_CONTACT], False,
        )
        with patch.object(wps, "_GenerateEverythingDialog", fake_dialog), \
             patch.object(QFileDialog, "getExistingDirectory", return_value=self._out_tmpdir.name):
            screen._on_generate_everything()

        # No students were ever added, so if auto-fill had run it would
        # have shown a warning and generated nothing new — confirm the
        # only contact data present is exactly what was saved manually.
        contacts = database.get_day_contacts("2026-06-11")
        self.assertEqual(len(contacts), 1)
        written = list(Path(self._out_tmpdir.name).glob("*.pdf"))
        self.assertEqual(len(written), 1)
        screen.close()

    def test_no_students_warns_and_auto_fills_nothing(self) -> None:
        screen = wps.WorkPipelineScreen(navigate_to=lambda i: None)
        fake_dialog = _FakeGenerateDialog(
            QDate(2026, 6, 11), QDate(2026, 6, 12), [DOC_CONTACT, DOC_ABSENCE], True,
        )
        with patch.object(wps, "_GenerateEverythingDialog", fake_dialog), \
             patch.object(QFileDialog, "getExistingDirectory", return_value=self._out_tmpdir.name):
            screen._on_generate_everything()

        # No students in the roster -> auto-fill must warn and save
        # nothing, not silently create real-looking rows.
        for day in ("2026-06-11", "2026-06-12"):
            self.assertEqual(database.get_day_contacts(day), [])
            self.assertEqual(database.get_day_absences(day), [])
        screen.close()

    def test_unclassified_students_warn_instead_of_saving_silent_zeros(self) -> None:
        """Regression: a real student with no القسم (class) assigned makes
        count_students() classify nobody, so auto-fill must warn and save
        nothing instead of silently saving real-looking rows full of
        zeros — indistinguishable from doing nothing."""
        database.add_student(Student(full_name="تلميذ بدون قسم", student_class="", grant_type="full"))

        screen = wps.WorkPipelineScreen(navigate_to=lambda i: None)
        fake_dialog = _FakeGenerateDialog(
            QDate(2026, 6, 11), QDate(2026, 6, 11), [DOC_CONTACT], True,
        )
        with patch.object(wps, "_GenerateEverythingDialog", fake_dialog), \
             patch.object(QFileDialog, "getExistingDirectory", return_value=self._out_tmpdir.name):
            screen._on_generate_everything()

        self.assertEqual(database.get_day_contacts("2026-06-11"), [])
        screen.close()


if __name__ == "__main__":
    unittest.main()
