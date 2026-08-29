import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA
from core.models import MealEntry, MealProgram
from data import database
from ui import meal_program_screen


class MealProgramScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        # This class patches module-level repo functions rather than the
        # database, so an unpatched one used to reach the REAL matama.db.
        # Point DB_PATH somewhere disposable as a backstop.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._originals = {
            "get_all_programs": meal_program_screen.get_all_programs,
            "get_program_entries": meal_program_screen.get_program_entries,
            "set_program_ramadan_mode": meal_program_screen.set_program_ramadan_mode,
            "save_program_entries": meal_program_screen.save_program_entries,
            "file_save": meal_program_screen.QFileDialog.getSaveFileName,
            "message_info": meal_program_screen.QMessageBox.information,
            "message_warning": meal_program_screen.QMessageBox.warning,
            "message_critical": meal_program_screen.QMessageBox.critical,
        }

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()
        meal_program_screen.get_all_programs = self._originals["get_all_programs"]
        meal_program_screen.get_program_entries = self._originals["get_program_entries"]
        meal_program_screen.set_program_ramadan_mode = self._originals["set_program_ramadan_mode"]
        meal_program_screen.save_program_entries = self._originals["save_program_entries"]
        meal_program_screen.QFileDialog.getSaveFileName = self._originals["file_save"]
        meal_program_screen.QMessageBox.information = self._originals["message_info"]
        meal_program_screen.QMessageBox.warning = self._originals["message_warning"]
        meal_program_screen.QMessageBox.critical = self._originals["message_critical"]

    def test_empty_state_is_available_when_there_are_no_programs(self) -> None:
        meal_program_screen.get_all_programs = lambda: []

        screen = meal_program_screen.MealProgramScreen()

        self.assertFalse(screen._empty_widget.isHidden())
        self.assertTrue(screen._scroll.isHidden())
        self.assertFalse(screen._save_btn.isEnabled())
        screen.close()

    def test_regular_program_collects_all_weekly_cells(self) -> None:
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=7, name="Weekly", school_year="2025-2026", is_ramadan=False)
        ]
        meal_program_screen.get_program_entries = lambda _program_id: []

        screen = meal_program_screen.MealProgramScreen()
        screen._cells[(0, meal_program_screen.MEAL_FTOUR)].setPlainText("Milk and bread")

        entries = screen._collect_entries()

        self.assertEqual(len(entries), 21)
        self.assertTrue(
            any(
                entry.day_of_week == 0
                and entry.meal_type == meal_program_screen.MEAL_FTOUR
                and entry.menu_text == "Milk and bread"
                for entry in entries
            )
        )
        screen.close()

    def test_saving_after_ramadan_toggle_persists_program_mode(self) -> None:
        captured: dict[str, object] = {}
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=8, name="Weekly", school_year="2025-2026", is_ramadan=False)
        ]
        meal_program_screen.get_program_entries = lambda _program_id: []
        meal_program_screen.set_program_ramadan_mode = (
            lambda program_id, is_ramadan: captured.update(mode=(program_id, is_ramadan))
        )
        meal_program_screen.save_program_entries = (
            lambda program_id, entries: captured.update(entries=(program_id, entries))
        )
        meal_program_screen.QMessageBox.information = lambda *args, **kwargs: None
        meal_program_screen.QMessageBox.critical = lambda *args, **kwargs: None

        screen = meal_program_screen.MealProgramScreen()
        screen._toggle_ramadan()
        screen._cells[(0, "ftour_ramadan")].setPlainText("Dates and soup")
        screen._on_save()

        self.assertEqual(captured["mode"], (8, True))
        saved_program_id, entries = captured["entries"]
        self.assertEqual(saved_program_id, 8)
        self.assertEqual(len(entries), 14)
        self.assertTrue(any(entry.meal_type == "ftour_ramadan" for entry in entries))
        screen.close()

    def test_export_pdf_uses_current_visible_menu(self) -> None:
        written_paths: list[Path] = []
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=9, name="Weekly", school_year="2025-2026", is_ramadan=False)
        ]
        meal_program_screen.get_program_entries = lambda _program_id: []
        meal_program_screen.QFileDialog.getSaveFileName = lambda *args, **kwargs: ("menu", "")
        meal_program_screen.QMessageBox.information = lambda *args, **kwargs: None
        meal_program_screen.QMessageBox.critical = lambda *args, **kwargs: None

        screen = meal_program_screen.MealProgramScreen()
        screen._cells[(2, meal_program_screen.MEAL_FTOUR)].setPlainText("Milk and bread")
        screen._write_menu_pdf = lambda path: written_paths.append(path)  # type: ignore[method-assign]

        rows = screen._pdf_menu_rows()
        screen._on_export_pdf()

        self.assertTrue(any("Milk and bread" in cells for _, cells in rows))
        self.assertEqual(written_paths, [Path("menu.pdf")])
        screen.close()

    def _select_history(self, screen, program_id: int) -> None:
        """Pick a history row by PROGRAM, never by index — the list is ordered
        newest-first and that order is not what get_all_programs() returns."""
        from PySide6.QtCore import Qt
        for row in range(screen._history_list.count()):
            item = screen._history_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole).id == program_id:
                screen._history_list.setCurrentRow(row)
                return
        raise AssertionError(f"program {program_id} is not in the history list")

    def test_history_list_shows_every_program_with_its_date(self) -> None:
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=1, name="برنامج قديم", is_ramadan=False, created_at="2026-01-05"),
            MealProgram(id=2, name="برنامج رمضان", is_ramadan=True, created_at="2026-02-10"),
        ]
        meal_program_screen.get_program_entries = lambda _program_id: []

        screen = meal_program_screen.MealProgramScreen()

        # Newest first — the history exists to reach a RECENT week.
        self.assertEqual(screen._history_list.count(), 2)
        self.assertIn("2026-02-10", screen._history_list.item(0).text())
        self.assertIn("2026-01-05", screen._history_list.item(1).text())
        screen.close()

    def test_copy_program_fills_grid_from_selected_history_entry(self) -> None:
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=10, name="الحالي", is_ramadan=False, created_at="2026-03-01"),
            MealProgram(id=11, name="قديم", is_ramadan=False, created_at="2026-01-01"),
        ]

        def entries_for(program_id):
            if program_id == 11:
                return [meal_program_screen.MealEntry(
                    program_id=11, day_of_week=0,
                    meal_type=meal_program_screen.MEAL_FTOUR, menu_text="حليب وخبز",
                )]
            return []

        meal_program_screen.get_program_entries = entries_for
        meal_program_screen.QMessageBox.information = lambda *a, **k: None

        screen = meal_program_screen.MealProgramScreen()
        self.assertEqual(screen._current_program.id, 10)

        self._select_history(screen, 11)   # "قديم"
        screen._on_copy_program_clicked()

        self.assertEqual(
            screen._cells[(0, meal_program_screen.MEAL_FTOUR)].toPlainText(), "حليب وخبز"
        )
        self.assertTrue(screen._is_dirty)
        screen.close()

    def test_copy_program_blocks_ramadan_mode_mismatch(self) -> None:
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=20, name="عادي", is_ramadan=False, created_at="2026-03-01"),
            MealProgram(id=21, name="رمضان", is_ramadan=True, created_at="2026-02-01"),
        ]
        meal_program_screen.get_program_entries = lambda _program_id: [
            meal_program_screen.MealEntry(
                program_id=21, day_of_week=0, meal_type="ftour_ramadan", menu_text="تمر وحليب",
            )
        ]
        warnings: list[str] = []
        meal_program_screen.QMessageBox.warning = lambda self, title, text: warnings.append(text)

        screen = meal_program_screen.MealProgramScreen()
        self._select_history(screen, 21)   # the Ramadan program
        screen._on_copy_program_clicked()

        self.assertEqual(len(warnings), 1)
        self.assertFalse(screen._is_dirty)
        screen.close()


class MealProgramHistoryPanelTests(unittest.TestCase):
    """The program list, the history, "نسخ من برنامج سابق" AND the save button
    all live in the side panel. It used to start closed and refresh() forced it
    closed again on every visit, so the user could type a whole week's menu
    with no visible way to save it — and never discovered that program history
    or copying existed at all."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._info = meal_program_screen.QMessageBox.information
        meal_program_screen.QMessageBox.information = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        meal_program_screen.QMessageBox.information = self._info
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _screen(self):
        screen = meal_program_screen.MealProgramScreen()
        screen.show()
        return screen

    def test_the_panel_and_its_save_button_are_visible_by_default(self) -> None:
        screen = self._screen()
        self.assertTrue(screen._control_panel.isVisible())
        self.assertTrue(screen._save_btn.isVisible())
        self.assertTrue(screen._copy_program_btn.isVisible())
        screen.close()

    def test_refresh_does_not_close_the_panel(self) -> None:
        screen = self._screen()
        screen.refresh()
        self.assertTrue(screen._control_panel.isVisible(),
                        "refresh() hid the panel, taking the save button with it")
        screen.close()

    def test_refresh_keeps_a_deliberately_collapsed_panel_collapsed(self) -> None:
        """The header toggle is still the user's own choice to respect."""
        screen = self._screen()
        screen._set_program_panel_visible(False)
        screen.refresh()
        self.assertFalse(screen._control_panel.isVisible())
        screen.close()

    def test_history_lists_newest_first_and_marks_the_open_program(self) -> None:
        for name in ("أسبوع 1", "أسبوع 2", "أسبوع 3"):
            database.create_program(name, "2025-2026", False)
        screen = self._screen()

        texts = [screen._history_list.item(i).text()
                 for i in range(screen._history_list.count())]
        self.assertEqual(len(texts), 3)
        self.assertIn("أسبوع 3", texts[0])   # newest first
        self.assertIn("أسبوع 1", texts[-1])
        # The dropdown keeps its own oldest-first order, matching the naming.
        self.assertIn("أسبوع 1", screen._prog_combo.itemText(0))
        screen.close()

    def test_saving_a_ramadan_switch_refreshes_the_history_badge(self) -> None:
        """_on_save updated the dropdown's ☾ badge but not the history's, so
        the history showed the wrong program type until the page was rebuilt."""
        database.create_program("برنامج", "2025-2026", False)
        screen = self._screen()
        self.assertNotIn("☾", screen._history_list.item(0).text())

        screen._toggle_ramadan()
        screen._on_save()

        self.assertIn("☾", screen._history_list.item(0).text())
        screen.close()

    def test_copying_an_old_program_fills_the_current_grid(self) -> None:
        source_id = database.create_program("أسبوع قديم", "2025-2026", False)
        database.save_program_entries(source_id, [
            MealEntry(program_id=source_id, day_of_week=day,
                      meal_type=meal, menu_text=f"وجبة {day}")
            for day in range(7)
            for meal in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA)
        ])
        database.create_program("أسبوع جديد", "2025-2026", False)

        screen = self._screen()
        screen._prog_combo.setCurrentIndex(1)          # the empty new one
        self.assertEqual(sum(1 for c in screen._cells.values() if c.toPlainText().strip()), 0)

        for i in range(screen._history_list.count()):
            if "أسبوع قديم" in screen._history_list.item(i).text():
                screen._history_list.setCurrentRow(i)
        screen._on_copy_program_clicked()

        self.assertEqual(sum(1 for c in screen._cells.values() if c.toPlainText().strip()), 21)
        self.assertTrue(screen._is_dirty, "a copy must be saveable, not silently committed")
        screen.close()

    def test_copying_between_a_normal_and_a_ramadan_program_is_refused(self) -> None:
        database.create_program("عادي", "2025-2026", False)
        database.create_program("رمضان", "2025-2026", True)
        warnings = []
        meal_program_screen.QMessageBox.warning = staticmethod(
            lambda *a, **k: warnings.append(a))
        try:
            screen = self._screen()
            screen._prog_combo.setCurrentIndex(1)       # the Ramadan one
            for i in range(screen._history_list.count()):
                if "عادي" in screen._history_list.item(i).text():
                    screen._history_list.setCurrentRow(i)
            screen._on_copy_program_clicked()
            self.assertEqual(len(warnings), 1)
            screen.close()
        finally:
            meal_program_screen.QMessageBox.warning = self._originals_warning()

    def _originals_warning(self):
        import PySide6.QtWidgets
        return PySide6.QtWidgets.QMessageBox.warning


if __name__ == "__main__":
    unittest.main()
