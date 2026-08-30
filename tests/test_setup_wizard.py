"""The first-run setup wizard.

It had no tests at all before 2026-08-29, despite being the first thing a new
user ever sees. The rules covered here are the ones that would strand someone
on their first launch: every optional step must be skippable, what the user
typed must survive abandoning the wizard halfway, and a value that cannot be
used must be refused at the door rather than saved as something that silently
reads as zero later.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QMessageBox

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import SchoolSettings
from data import database
from ui import setup_wizard as sw


class _WizardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._warning = QMessageBox.warning
        self._info = QMessageBox.information
        self._critical = QMessageBox.critical
        QMessageBox.warning = staticmethod(lambda *a, **k: None)
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.critical = staticmethod(lambda *a, **k: None)

    def tearDown(self) -> None:
        QMessageBox.warning = self._warning
        QMessageBox.information = self._info
        QMessageBox.critical = self._critical
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _wizard(self, *, filled: bool = True) -> sw.SetupWizard:
        wizard = sw.SetupWizard()
        self.addCleanup(wizard.deleteLater)
        if filled:
            wizard._school_name.setText("ثانوية اختبار")
            wizard._school_year.setText("2025/2026")
            wizard._director.setText("مدير")
        return wizard


class WizardFlowTests(_WizardTestCase):
    def test_it_has_one_page_per_declared_step(self) -> None:
        wizard = self._wizard()
        self.assertEqual(wizard._stack.count(), len(sw._STEPS))

    def test_the_identity_page_will_not_be_left_empty(self) -> None:
        wizard = self._wizard(filled=False)
        wizard._go_next()
        self.assertEqual(wizard._stack.currentIndex(), 0)

    def test_every_optional_step_offers_a_skip_and_the_others_do_not(self) -> None:
        """A school with no Excel file to hand still has to reach the app."""
        wizard = self._wizard()
        wizard.show()
        for index, (_name, _subtitle, optional) in enumerate(sw._STEPS):
            wizard._show_step(index)
            self.assertEqual(wizard._skip_btn.isVisible(), optional,
                             f"step {index}")

    def test_settings_are_saved_before_the_optional_steps(self) -> None:
        """Someone who closes the window on an optional step must still keep
        the identity they typed."""
        wizard = self._wizard()
        wizard._go_next()                      # identity → contract
        self.assertIsNone(database.get_school_settings())
        wizard._go_next()                      # contract → students, saves
        saved = database.get_school_settings()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.school_name, "ثانوية اختبار")

    def test_skipping_a_step_stores_nothing_from_it(self) -> None:
        wizard = self._wizard()
        wizard._go_next(); wizard._go_next()   # now on the students step
        wizard._on_skip()
        wizard._on_skip()
        wizard._on_skip()
        self.assertEqual(database.get_all_holidays(), [])
        self.assertEqual(database.get_all_programs(), [])

    def test_the_last_step_finishes_instead_of_advancing(self) -> None:
        wizard = self._wizard()
        wizard._show_step(len(sw._STEPS) - 1)
        self.assertEqual(wizard._next_btn.text(), sw._BTN_FINISH)


class WizardValidationTests(_WizardTestCase):
    def test_a_price_that_is_not_a_number_is_refused(self) -> None:
        """Left to save, it would be read as 0.00 by every cost figure in the
        app without a single warning."""
        wizard = self._wizard()
        wizard._price_ghada.setText("12,50")           # comma, not a point
        self.assertFalse(wizard._validate_prices())
        wizard._price_ghada.setText("12.50")
        self.assertTrue(wizard._validate_prices())

    def test_a_blank_price_is_allowed(self) -> None:
        """Not knowing a price yet is normal; nonsense is not."""
        wizard = self._wizard()
        wizard._price_ghada.setText("")
        self.assertTrue(wizard._validate_prices())

    def test_ramadan_dates_are_only_saved_when_the_school_serves_them(self) -> None:
        wizard = self._wizard()
        wizard._ramadan_start.setDate(QDate(2026, 2, 17))
        wizard._ramadan_end.setDate(QDate(2026, 3, 18))
        self.assertEqual(wizard._ramadan_period(), ("", ""))

        wizard._ramadan_enabled.setChecked(True)
        self.assertEqual(wizard._ramadan_period(),
                         ("2026-02-17", "2026-03-18"))

    def test_a_ramadan_period_that_ends_before_it_starts_is_refused(self) -> None:
        wizard = self._wizard()
        wizard._ramadan_enabled.setChecked(True)
        wizard._ramadan_start.setDate(QDate(2026, 3, 18))
        wizard._ramadan_end.setDate(QDate(2026, 2, 17))
        self.assertFalse(wizard._validate_prices())

    def test_the_dead_ramadan_price_fields_are_gone(self) -> None:
        """The user dropped Ramadan pricing; the wizard used to ask for three
        numbers nothing in the app reads, and never asked for the dates that
        every document does."""
        wizard = self._wizard()
        for name in ("_price_ftour_ramadan", "_price_asha_ramadan",
                     "_price_shour"):
            self.assertFalse(hasattr(wizard, name), name)
        self.assertTrue(hasattr(wizard, "_ramadan_start"))


class HolidayStepTests(_WizardTestCase):
    def _step(self):
        from ui.setup_steps import HolidaysStep
        step = HolidaysStep()
        self.addCleanup(step.deleteLater)
        return step

    def _add(self, step, start, end, label="عطلة") -> None:
        step._from.setDate(start)
        step._to.setDate(end)
        step._label.setText(label)
        step._on_add()

    def test_a_range_becomes_one_row_per_day(self) -> None:
        step = self._step()
        self._add(step, QDate(2026, 1, 5), QDate(2026, 1, 9), "عطلة نصف السنة")
        step.save()
        holidays = database.get_all_holidays()
        self.assertEqual(len(holidays), 5)
        self.assertEqual(holidays[0].label, "عطلة نصف السنة")

    def test_a_backwards_range_is_refused(self) -> None:
        step = self._step()
        self._add(step, QDate(2026, 1, 9), QDate(2026, 1, 5))
        step.save()
        self.assertEqual(database.get_all_holidays(), [])

    def test_an_implausibly_long_range_is_refused(self) -> None:
        """A mistyped year turns one week into a decade — it must not write
        thousands of rows."""
        step = self._step()
        self._add(step, QDate(2026, 1, 5), QDate(2030, 1, 5))
        step.save()
        self.assertEqual(database.get_all_holidays(), [])

    def test_a_range_with_no_reason_is_refused(self) -> None:
        step = self._step()
        self._add(step, QDate(2026, 1, 5), QDate(2026, 1, 6), "")
        step.save()
        self.assertEqual(database.get_all_holidays(), [])

    def test_saving_nothing_writes_nothing(self) -> None:
        step = self._step()
        step.save()
        self.assertEqual(database.get_all_holidays(), [])


class MealProgramStepTests(_WizardTestCase):
    def _step(self):
        from ui.setup_steps import MealProgramStep
        step = MealProgramStep("2025/2026")
        self.addCleanup(step.deleteLater)
        return step

    def test_only_the_lines_actually_typed_are_saved(self) -> None:
        """An empty slot means the school does not serve that meal that day,
        not a meal with an empty name."""
        step = self._step()
        step._cells[(2, "ghada")].setText("كسكس بالخضر")
        step.save()
        programs = database.get_all_programs()
        self.assertEqual(len(programs), 1)
        entries = database.get_program_entries(programs[0].id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].menu_text, "كسكس بالخضر")

    def test_an_untouched_grid_creates_no_program(self) -> None:
        step = self._step()
        step.save()
        self.assertEqual(database.get_all_programs(), [])

    def test_the_program_carries_the_school_year(self) -> None:
        step = self._step()
        step.set_school_year("2026/2027")
        step._cells[(2, "ghada")].setText("عدس")
        step.save()
        self.assertEqual(database.get_all_programs()[0].school_year,
                         "2026/2027")


class FinishPageTests(_WizardTestCase):
    def test_the_summary_names_what_was_skipped_too(self) -> None:
        """A summary listing only successes would hide the gaps the user still
        has to fill in."""
        wizard = self._wizard()
        wizard._go_next(); wizard._go_next()
        wizard._show_step(len(sw._STEPS) - 1)

        lines = [wizard._done_list.itemAt(i).widget().text()
                 for i in range(wizard._done_list.count())]
        joined = "\n".join(lines)
        self.assertIn(sw._DONE_SETTINGS, joined)
        self.assertIn(sw._DONE_NO_RAMADAN.split(":")[0], joined)
        # every optional step reports, whether it did anything or not
        self.assertEqual(len(lines), 2 + len(wizard._optional_steps))

    def test_a_saved_ramadan_period_is_reported_back(self) -> None:
        wizard = self._wizard()
        wizard._ramadan_enabled.setChecked(True)
        wizard._ramadan_start.setDate(QDate(2026, 2, 17))
        wizard._ramadan_end.setDate(QDate(2026, 3, 18))
        wizard._show_step(len(sw._STEPS) - 1)
        joined = "\n".join(
            wizard._done_list.itemAt(i).widget().text()
            for i in range(wizard._done_list.count()))
        self.assertIn("2026-02-17", joined)


if __name__ == "__main__":
    unittest.main()
