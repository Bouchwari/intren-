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

from core.models import DailyAbsence, Student
from data import database
from ui import daily_absence_screen as das


class DailyAbsenceScreenTests(unittest.TestCase):
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

    def test_primary_absences_are_saved_and_reloaded(self) -> None:
        """The core bug: primary-cycle absences used to be silently dropped
        even though the daily_absence table already had columns for them."""
        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        card = screen._cards[das.MEAL_GHADA]
        card._pg.setValue(3)
        card._pc.setValue(1)

        screen._on_save()

        reopened = das.DailyAbsenceScreen()
        reopened._date_edit.setDate(QDate(2026, 6, 11))
        reopened._load_selected()
        reloaded = reopened._cards[das.MEAL_GHADA]
        self.assertEqual(reloaded._pg.value(), 3)
        self.assertEqual(reloaded._pc.value(), 1)
        screen.close()
        reopened.close()

    def test_legacy_paying_column_merges_into_granted_on_load(self) -> None:
        """Old rows saved before "مؤد" was retired must still add up
        correctly, and re-saving must never write to *_paying again."""
        database.save_daily_absence(DailyAbsence(
            date="2026-06-11", meal_type=das.MEAL_FTOUR,
            collegial_granted=2, collegial_paying=5, collegial_complement=1,
        ))
        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._load_selected()

        card = screen._cards[das.MEAL_FTOUR]
        self.assertEqual(card._cg.value(), 7)  # 2 granted + 5 legacy paying

        screen._on_save()
        with database._connection() as conn:
            row = conn.execute(
                "SELECT collegial_granted, collegial_paying FROM daily_absence "
                "WHERE date='2026-06-11' AND meal_type=?",
                (das.MEAL_FTOUR,),
            ).fetchone()
        self.assertEqual(row["collegial_granted"], 7)
        self.assertEqual(row["collegial_paying"], 0)
        screen.close()

    def test_monitors_complement_round_trips(self) -> None:
        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        card = screen._cards[das.MEAL_ASHA]
        card._mo.setValue(2)
        card._mc.setValue(4)

        absence = card.to_absence("2026-06-11")
        self.assertEqual(absence.monitors, 2)
        self.assertEqual(absence.monitors_complement, 4)
        self.assertEqual(absence.monitors_total, 6)
        screen.close()

    def test_auto_generate_with_no_students_shows_message_and_stays_zero(self) -> None:
        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))

        screen._on_auto_generate_clicked()

        card = screen._cards[das.MEAL_GHADA]
        self.assertEqual(card._pg.value(), 0)
        self.assertEqual(card._cg.value(), 0)
        screen.close()

    def test_auto_generate_estimates_from_absence_history(self) -> None:
        database.add_student(Student(full_name="A", student_class="الأولى إعدادي", grant_type="منحة كاملة"))
        database.add_student(Student(full_name="B", student_class="الأولى إعدادي", grant_type="منحة كاملة"))
        database.add_student(Student(full_name="C", student_class="الأولى إعدادي", grant_type="منحة كاملة"))
        database.add_student(Student(full_name="D", student_class="الأولى إعدادي", grant_type="منحة كاملة"))

        # Same weekday (Thursday) as the target date, 3 records so the
        # estimator has enough history to produce a real rate instead of
        # falling back to "insufficient_history".
        for d in ("2026-05-21", "2026-05-28", "2026-06-04"):
            database.save_daily_absence(DailyAbsence(
                date=d, meal_type=das.MEAL_GHADA, collegial_granted=2,
            ))

        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))  # also a Thursday

        screen._on_auto_generate_clicked()

        card = screen._cards[das.MEAL_GHADA]
        # 2 absent out of 4 enrolled, every matching record -> median rate
        # 0.5 -> 2 estimated absent today.
        self.assertEqual(card._cg.value(), 2)
        self.assertFalse(screen._estimate_note.isHidden())
        screen.close()


if __name__ == "__main__":
    unittest.main()
