import sys
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import MealProgram
from ui import meal_program_screen


class MealProgramScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
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

    def test_history_list_shows_every_program_with_its_date(self) -> None:
        meal_program_screen.get_all_programs = lambda: [
            MealProgram(id=1, name="برنامج قديم", is_ramadan=False, created_at="2026-01-05"),
            MealProgram(id=2, name="برنامج رمضان", is_ramadan=True, created_at="2026-02-10"),
        ]
        meal_program_screen.get_program_entries = lambda _program_id: []

        screen = meal_program_screen.MealProgramScreen()

        self.assertEqual(screen._history_list.count(), 2)
        self.assertIn("2026-01-05", screen._history_list.item(0).text())
        self.assertIn("2026-02-10", screen._history_list.item(1).text())
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

        # Row 1 in the history list is "قديم" (id=11) since programs load
        # in the order get_all_programs returned them.
        screen._history_list.setCurrentRow(1)
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
        screen._history_list.setCurrentRow(1)  # the Ramadan program
        screen._on_copy_program_clicked()

        self.assertEqual(len(warnings), 1)
        self.assertFalse(screen._is_dirty)
        screen.close()


if __name__ == "__main__":
    unittest.main()
