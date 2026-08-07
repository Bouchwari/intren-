import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import DailyContact
from data import database
from ui import order_letter_screen as ols


class OrderLetterAutoFillTests(unittest.TestCase):
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

    def _set_period(self, screen: ols.OrderLetterScreen, start: str, end: str) -> None:
        screen._period_start.setDate(QDate.fromString(start, "yyyy-MM-dd"))
        screen._period_end.setDate(QDate.fromString(end, "yyyy-MM-dd"))

    def test_auto_fill_sums_real_data_across_the_range_per_meal(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-06-10", meal_type=MEAL_GHADA,
            collegial_granted=10, qualifying_granted=5, monitors=2,
        ))
        database.save_daily_contact(DailyContact(
            date="2026-06-11", meal_type=MEAL_GHADA,
            collegial_granted=8, qualifying_granted=6, monitors=1,
        ))

        screen = ols.OrderLetterScreen()
        self._set_period(screen, "2026-06-10", "2026-06-11")
        screen._auto_fill()

        ghada_card = screen._cards[MEAL_GHADA]
        self.assertEqual(ghada_card.collegial(), 18)   # 10 + 8
        self.assertEqual(ghada_card.qualifying(), 11)  # 5 + 6
        self.assertEqual(ghada_card.monitors(), 3)     # 2 + 1
        screen.close()

    def test_auto_fill_does_not_leak_one_meals_data_into_another(self) -> None:
        """Regression: the old auto-fill applied the same flat number to
        all 3 meal cards. فطور/غداء/عشاء must be able to differ."""
        database.save_daily_contact(DailyContact(
            date="2026-06-10", meal_type=MEAL_GHADA, collegial_granted=20,
        ))
        # No ftour or asha data saved for this range at all.

        screen = ols.OrderLetterScreen()
        self._set_period(screen, "2026-06-10", "2026-06-10")
        screen._auto_fill()

        self.assertEqual(screen._cards[MEAL_GHADA].collegial(), 20)
        self.assertEqual(screen._cards[MEAL_FTOUR].total(), 0)
        self.assertEqual(screen._cards[MEAL_ASHA].total(), 0)
        screen.close()

    def test_auto_fill_warns_and_leaves_cards_untouched_when_range_has_no_data(self) -> None:
        screen = ols.OrderLetterScreen()
        screen._cards[MEAL_GHADA].set_values(7, 3, 1)
        self._set_period(screen, "2026-06-10", "2026-06-10")

        with patch.object(QMessageBox, "information", return_value=None) as info:
            screen._auto_fill()

        info.assert_called_once()
        self.assertEqual(screen._cards[MEAL_GHADA].collegial(), 7)
        self.assertEqual(screen._cards[MEAL_GHADA].qualifying(), 3)
        self.assertEqual(screen._cards[MEAL_GHADA].monitors(), 1)
        screen.close()


class OrderLetterNumberTests(unittest.TestCase):
    """رقم الوثيقة — an editable field, always pre-filled with a real
    suggested number (never blank), whose saved value the مسير can
    override before saving."""

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

    def test_number_field_is_never_blank_on_a_fresh_screen(self) -> None:
        """Regression: the field used to stay blank/placeholder until the
        letter was explicitly saved — a مسير who exported first (without
        saving) saw no number at all."""
        screen = ols.OrderLetterScreen()
        self.assertNotEqual(screen._number_edit.text().strip(), "")
        self.assertEqual(screen._number_edit.text().strip(), "1")
        screen.close()

    def test_save_uses_and_persists_the_number_typed_in_the_box(self) -> None:
        screen = ols.OrderLetterScreen()
        screen._number_edit.setText("42")
        screen._on_save()

        letters = database.get_all_order_letters()
        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0].document_number, 42)
        screen.close()

    def test_new_letter_suggests_the_next_number_after_an_existing_one(self) -> None:
        screen = ols.OrderLetterScreen()
        screen._number_edit.setText("42")
        screen._on_save()

        screen._on_new()
        self.assertEqual(screen._number_edit.text().strip(), "43")
        screen.close()

    def test_loading_history_shows_that_letters_own_saved_number(self) -> None:
        screen = ols.OrderLetterScreen()
        screen._number_edit.setText("7")
        screen._on_save()
        screen._on_new()  # box now suggests 8 — loading history must override this

        screen._refresh_history()
        screen._history_combo.setCurrentIndex(0)
        self.assertEqual(screen._number_edit.text().strip(), "7")
        screen.close()


if __name__ == "__main__":
    unittest.main()
