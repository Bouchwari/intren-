import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import FONT_CAPTION
from core.models import DailyAbsence, SchoolSettings, Student
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


class AbsenceCardLayoutTests(unittest.TestCase):
    """The meal cards are built once for all five meals and only the selected
    date's are shown. A hidden widget still owns its grid cell, so on a Ramadan
    day إفطار (slot 3) and سحور (slot 4) used to render diagonally apart with
    three empty cells above them instead of side by side."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(
            SchoolSettings(school_name="مؤسسة", school_year="2025-2026",
                           director="المدير",
                           ramadan_start="2026-03-01", ramadan_end="2026-03-30"))

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _positions(self, screen) -> list:
        """(row, column) of every visible card, in display order."""
        grid = screen._cards_grid
        found = []
        for key, _ in das._CARD_MEAL_ORDER:
            card = screen._cards[key]
            if not card.isVisible():
                continue
            index = grid.indexOf(card)
            self.assertNotEqual(index, -1, f"{key} is visible but not in the grid")
            row, column, _, _ = grid.getItemPosition(index)
            found.append((key, row, column))
        return found

    def test_ramadan_day_packs_its_two_cards_side_by_side(self) -> None:
        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 3, 10))
        screen._load_selected()
        screen.show()

        placed = self._positions(screen)
        self.assertEqual([key for key, _, _ in placed],
                         [das.MEAL_IFTAR, das.MEAL_SHOUR])
        # Same row, adjacent columns — never a diagonal.
        self.assertEqual([(row, column) for _, row, column in placed],
                         [(0, 0), (0, 1)])

    def test_normal_day_still_packs_its_three_cards_from_the_top(self) -> None:
        screen = das.DailyAbsenceScreen()
        screen._date_edit.setDate(QDate(2026, 6, 11))
        screen._load_selected()
        screen.show()

        placed = self._positions(screen)
        self.assertEqual([key for key, _, _ in placed],
                         [das.MEAL_FTOUR, das.MEAL_GHADA, das.MEAL_ASHA])
        self.assertEqual([(row, column) for _, row, column in placed],
                         [(0, 0), (0, 1), (1, 0)])

    def test_switching_between_a_normal_and_a_ramadan_day_repacks(self) -> None:
        """The cards are reused, not rebuilt, so the grid must be re-packed on
        every date change rather than only on first load."""
        screen = das.DailyAbsenceScreen()
        screen.show()
        for iso, expected in ((QDate(2026, 6, 11), 3), (QDate(2026, 3, 10), 2),
                              (QDate(2026, 6, 11), 3)):
            screen._date_edit.setDate(iso)
            screen._load_selected()
            # Qt applies a re-added widget's visibility on the next event-loop
            # pass; the running app always has one.
            self.app.processEvents()
            placed = self._positions(screen)
            self.assertEqual(len(placed), expected)
            self.assertEqual(placed[0][1:], (0, 0),
                             "the first visible card must sit at the top corner")

    def test_history_columns_are_wide_enough_for_their_own_headers(self) -> None:
        """Every cycle column was pinned to 70px, which clipped its header —
        "معلمون (ك)" rendered as "علمون (ك)"."""
        screen = das.DailyAbsenceScreen()
        table = screen._history_table
        font = QFont(table.font())
        font.setPixelSize(FONT_CAPTION)
        font.setBold(True)
        metrics = QFontMetrics(font)
        headers = [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ]
        for column, label in enumerate(headers):
            self.assertGreaterEqual(
                table.columnWidth(column),
                metrics.horizontalAdvance(label) + das._HISTORY_HEADER_PADDING,
                f"column {column} ({label}) is too narrow for its header")


class BatchAbsenceGenerationTests(unittest.TestCase):
    """الصفحة الرئيسية's batch auto-fill writes absence rows straight to the
    database with no screen open."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(
            SchoolSettings(school_name="مؤسسة", school_year="2025-2026",
                           director="المدير",
                           ramadan_start="2026-03-01", ramadan_end="2026-03-30"))
        self._roster = {"collegial_full": 10, "collegial_lunch": 10}

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_ramadan_day_gets_ramadan_absence_rows_not_normal_ones(self) -> None:
        """_counts_to_contacts was made Ramadan-aware when Ramadan mode landed
        but _counts_to_absences was missed, so batch generation kept writing
        فطور/غداء/عشاء absence rows onto Ramadan days — the exact stale rows
        that had to be cleaned out of the real database on 2026-08-28."""
        das.generate_and_save_absence_for_date("2026-03-10", self._roster, [])

        saved = {a.meal_type for a in database.get_day_absences("2026-03-10")}
        self.assertEqual(saved, {das.MEAL_IFTAR, das.MEAL_SHOUR})

    def test_normal_day_gets_the_three_normal_rows(self) -> None:
        das.generate_and_save_absence_for_date("2026-05-11", self._roster, [])

        saved = {a.meal_type for a in database.get_day_absences("2026-05-11")}
        self.assertEqual(saved, {das.MEAL_FTOUR, das.MEAL_GHADA, das.MEAL_ASHA})

    def test_a_day_with_no_history_is_not_marked_fully_absent(self) -> None:
        """The whole roster used to be written as absent, which made every
        downstream document report that nobody ate."""
        das.generate_and_save_absence_for_date("2026-05-11", self._roster, [])

        for absence in database.get_day_absences("2026-05-11"):
            self.assertEqual(absence.grand_total, 0, f"{absence.meal_type} was marked fully absent")
