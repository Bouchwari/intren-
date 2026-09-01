"""Sidebar/stack wiring tests.

Both original bugs here were found by the user, not by the suite: a screen was
renaming itself because a live label was written to a hardcoded button index,
and deleting a screen shifts every later index in two places that must stay in
step. Grouping the menu into collapsible sections (2026-08-29) made a third
version of the same mistake possible — the highlight compared a button's
POSITION in the list against a stack index — so that is covered here too.
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

from config.settings import WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH
from core.models import SchoolSettings, Student
from data import database
from data.students_repo import add_student
from ui import main_window as mw


class _SidebarTestCase(unittest.TestCase):
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

    def _window(self) -> mw.MainWindow:
        window = mw.MainWindow()
        self.addCleanup(window.close)
        return window


class MainWindowSidebarTests(_SidebarTestCase):
    def test_student_count_lands_on_the_students_button_only(self) -> None:
        """Regression: the count was written to a hardcoded index that pointed
        one button too high, so الإحصائيات renamed itself to
        "لائحة التلاميذ (N)" and the dashboard appeared to disappear."""
        for index in range(7):
            add_student(Student(full_name=f"تلميذ {index}", cycle="الثانوي الإعدادي"))

        window = self._window()
        self.app.processEvents()
        labels = [button.text() for button in window._nav_buttons]

        self.assertIn("الإحصائيات", labels)
        self.assertIn("لائحة التلاميذ (7)", labels)
        self.assertEqual(
            sum(1 for label in labels if label.startswith("لائحة التلاميذ")), 1)

    def test_every_sidebar_entry_opens_its_own_screen(self) -> None:
        """The nav tree and the stack are built separately and can silently
        drift apart."""
        window = self._window()
        self.assertEqual(window._stack.count(), len(mw._NAV_ITEMS))
        for _icon, label, index in mw._NAV_ITEMS:
            window._navigate(index)
            self.assertEqual(window._stack.currentIndex(), index, label)

    def test_every_screen_is_reachable_exactly_once(self) -> None:
        """Order is the user's business, coverage is not: the tree may list
        pages in any order, but every stack index must appear exactly once."""
        indices = sorted(index for _icon, _label, index in mw._NAV_ITEMS)
        self.assertEqual(indices, list(range(len(mw._NAV_ITEMS))))


class NavSectionTests(_SidebarTestCase):
    """The collapsible sections added 2026-08-29."""

    def _section_named(self, window: mw.MainWindow, label: str):
        return next(s for s in window._nav_sections if s._label == label)

    def test_the_highlight_follows_the_page_not_the_button_position(self) -> None:
        """Regression for a bug the grouping would have introduced: the active
        button used to be picked with `position == stack index`, which held
        only while the flat list happened to mirror the stack. لائحة التلاميذ
        is page 2 but no longer sits second in the menu."""
        window = self._window()
        window._navigate(2)                       # لائحة التلاميذ
        active = [b.page_label for b in window._nav_buttons if b.is_active()]
        self.assertEqual(active, ["لائحة التلاميذ"])

        position = [b.page_index for b in window._nav_buttons].index(2)
        self.assertNotEqual(position, 2, "the test no longer proves anything")

    def test_navigating_opens_the_section_holding_the_page(self) -> None:
        """Navigation also arrives from الصفحة الرئيسية and the dashboard quick
        actions, so the menu has to follow rather than be clicked."""
        window = self._window()
        window._navigate(6)                       # رسالة الطلبية
        opened = [s._label for s in window._nav_sections if s.is_expanded()]
        self.assertEqual(opened, ["الوثائق اليومية"])

    def test_only_one_section_is_open_at_a_time(self) -> None:
        window = self._window()
        window._toggle_section(window._nav_sections[0])
        window._toggle_section(window._nav_sections[2])
        self.assertEqual(
            sum(1 for s in window._nav_sections if s.is_expanded()), 1)

    def test_a_shut_section_still_shows_where_you_are(self) -> None:
        """Closing the section you are working in must not erase every trace
        of the current page."""
        window = self._window()
        window._navigate(6)                       # رسالة الطلبية
        daily = self._section_named(window, "الوثائق اليومية")
        window._toggle_section(daily)             # shut it again
        self.assertFalse(daily.is_expanded())
        self.assertTrue(daily.header.is_active())

    def test_an_open_section_hands_the_highlight_to_its_page(self) -> None:
        window = self._window()
        window._navigate(6)
        daily = self._section_named(window, "الوثائق اليومية")
        self.assertTrue(daily.is_expanded())
        self.assertFalse(daily.header.is_active())

    def test_no_menu_button_is_crushed_at_the_smallest_window(self) -> None:
        """Regression: before the menu scrolled, the QVBoxLayout had to fit an
        open section into what was left and violated the buttons' own minimum
        heights — the five الوثائق اليومية pages rendered stacked on top of
        each other at 700px."""
        window = self._window()
        window.resize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        window.show()
        window._navigate(4)                       # opens the 5-page section
        self.app.processEvents()

        crushed = [(b.page_label, b.height(), b.minimumHeight())
                   for b in window._nav_buttons
                   if b.isVisible() and b.height() < b.minimumHeight()]
        self.assertEqual(crushed, [])


if __name__ == "__main__":
    unittest.main()
