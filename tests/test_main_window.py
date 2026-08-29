"""Sidebar/stack wiring tests.

Both bugs covered here were found by the user, not by the suite: a screen
was renaming itself because a live label was written to a hardcoded button
index, and deleting a screen shifts every later index in two places that
must stay in step.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import SchoolSettings, Student
from data import database
from data.students_repo import add_student
from ui import main_window as mw


class MainWindowSidebarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية اختبار", school_year="2025/2026", director="مدير"))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_student_count_lands_on_the_students_button_only(self) -> None:
        """Regression: the count was written to a hardcoded index that
        pointed one button too high, so الإحصائيات renamed itself to
        "لائحة التلاميذ (N)" and the dashboard appeared to disappear."""
        for index in range(7):
            add_student(Student(full_name=f"تلميذ {index}", cycle="الثانوي الإعدادي"))

        window = mw.MainWindow()
        self.app.processEvents()
        labels = [button.text() for button in window._nav_buttons]

        self.assertIn("الإحصائيات", labels)
        self.assertIn("لائحة التلاميذ (7)", labels)
        # Exactly one button may carry the count.
        self.assertEqual(
            sum(1 for label in labels if label.startswith("لائحة التلاميذ")), 1)
        window.close()

    def test_every_sidebar_entry_opens_its_own_screen(self) -> None:
        """Deleting a screen shifts every later index; the nav list and the
        stack are built separately, so they can silently drift apart."""
        window = mw.MainWindow()
        self.assertEqual(window._stack.count(), len(mw._NAV_ITEMS))
        for _icon, label, index in mw._NAV_ITEMS:
            window._navigate(index)
            self.assertEqual(window._stack.currentIndex(), index, label)
        window.close()

    def test_nav_indices_are_unique_and_contiguous(self) -> None:
        indices = [index for _icon, _label, index in mw._NAV_ITEMS]
        self.assertEqual(indices, list(range(len(mw._NAV_ITEMS))))


if __name__ == "__main__":
    unittest.main()
