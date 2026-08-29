"""طاقم المطبخ — the kitchen team roster and its printable list.

An internal tracker, not an official document: the value is the شهادة طبية
expiry warning, so most of what is worth testing is the date arithmetic and
the fact that a problem certificate cannot hide at the bottom of the screen.
"""
import datetime
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.models import SchoolSettings, StaffMember
from core.staff_certificates import (
    EXPIRY_WARNING_DAYS, STATE_EXPIRED, STATE_EXPIRING, STATE_MISSING,
    STATE_VALID, certificate_state, days_until_expiry, needs_attention,
)
from data import database
from ui import staff_screen as sts
from ui.staff_export import write_staff_pdf

TODAY = datetime.date(2026, 8, 29)


def _in(days: int) -> str:
    return (TODAY + datetime.timedelta(days=days)).isoformat()


class CertificateStateTests(unittest.TestCase):
    """A valid medical certificate is a contractual requirement for anyone
    handling food, so the point is catching one BEFORE it lapses."""

    def test_a_future_date_well_away_is_valid(self) -> None:
        self.assertEqual(certificate_state(_in(200), TODAY), STATE_VALID)

    def test_a_past_date_is_expired(self) -> None:
        self.assertEqual(certificate_state(_in(-1), TODAY), STATE_EXPIRED)

    def test_the_expiry_day_itself_still_counts_as_valid(self) -> None:
        """A certificate is good through the end of the day it names."""
        self.assertEqual(certificate_state(_in(0), TODAY), STATE_EXPIRING)
        self.assertGreaterEqual(days_until_expiry(_in(0), TODAY), 0)

    def test_the_warning_window_boundary(self) -> None:
        self.assertEqual(
            certificate_state(_in(EXPIRY_WARNING_DAYS), TODAY), STATE_EXPIRING)
        self.assertEqual(
            certificate_state(_in(EXPIRY_WARNING_DAYS + 1), TODAY), STATE_VALID)

    def test_blank_and_garbage_never_raise(self) -> None:
        """A member whose certificate was never recorded stores an empty
        string, and the value also arrives from a Qt widget."""
        for value in ("", "   ", "not-a-date", "2026-13-45"):
            self.assertEqual(certificate_state(value, TODAY), STATE_MISSING)
            self.assertIsNone(days_until_expiry(value, TODAY))

    def test_needs_attention_covers_everything_but_valid(self) -> None:
        self.assertFalse(needs_attention(_in(200), TODAY))
        for value in (_in(-1), _in(5), ""):
            self.assertTrue(needs_attention(value, TODAY))


class StaffRepositoryTests(unittest.TestCase):
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

    def test_insert_update_and_delete_round_trip(self) -> None:
        staff_id = database.save_staff_member(StaffMember(
            full_name="محمد العلوي", role="رئيس الطباخين", shift="صباحي",
            phone="0600000000", health_cert_expiry=_in(90), status="حاضر"))

        saved = database.get_staff_member(staff_id)
        self.assertEqual(saved.full_name, "محمد العلوي")
        self.assertEqual(saved.role, "رئيس الطباخين")

        saved.status = "غائب"
        database.save_staff_member(saved)
        self.assertEqual(database.get_staff_member(staff_id).status, "غائب")
        self.assertEqual(len(database.get_all_staff()), 1)

        database.delete_staff_member(staff_id)
        self.assertEqual(database.get_all_staff(), [])

    def test_a_member_with_no_certificate_date_is_allowed(self) -> None:
        """The date is genuinely optional — someone can join before handing
        their certificate in, and that is exactly what the screen flags."""
        staff_id = database.save_staff_member(StaffMember(full_name="بدون شهادة"))
        self.assertEqual(database.get_staff_member(staff_id).health_cert_expiry, "")


class StaffScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="مؤسسة", school_year="2025-2026", director="المدير",
            company_name="SOC TEST"))
        self._info = QMessageBox.information
        self._question = QMessageBox.question
        self._save_dialog = QFileDialog.getSaveFileName
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)
        # Any test touching the export must patch the file dialog, or a modal
        # opens and hangs the whole run instead of failing.
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))

    def tearDown(self) -> None:
        QMessageBox.information = self._info
        QMessageBox.question = self._question
        QFileDialog.getSaveFileName = self._save_dialog
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _screen(self, today: datetime.date = TODAY):
        screen = sts.StaffScreen()
        screen._today = lambda: today       # freeze "now" for the expiry maths
        screen._reload()
        screen.show()
        return screen

    def _add(self, name: str, expiry: str) -> int:
        return database.save_staff_member(
            StaffMember(full_name=name, role="مساعد طباخ", shift="صباحي",
                        health_cert_expiry=expiry, status="حاضر"))

    def test_the_alert_counters_match_the_certificates(self) -> None:
        self._add("منتهية", _in(-5))
        self._add("قريبة", _in(10))
        self._add("بدون", "")
        self._add("سارية", _in(300))
        screen = self._screen()

        self.assertEqual(screen._alert_labels["total"].text(), "4")
        self.assertEqual(screen._alert_labels[STATE_EXPIRED].text(), "1")
        self.assertEqual(screen._alert_labels[STATE_EXPIRING].text(), "1")
        self.assertEqual(screen._alert_labels[STATE_MISSING].text(), "1")
        screen.close()

    def test_certificates_needing_attention_are_shown_first(self) -> None:
        """A problem card must never be buried below the valid ones — that is
        the whole reason to open this screen."""
        self._add("ياسين سارية", _in(300))
        self._add("أحمد منتهية", _in(-5))
        screen = self._screen()

        first_card = screen._cards_layout.itemAtPosition(0, 0).widget()
        self.assertIn("منتهية", first_card._member.full_name)
        screen.close()

    def test_saving_a_new_member_requires_a_name(self) -> None:
        screen = self._screen()
        screen._name_edit.setText("   ")
        screen._on_save()

        self.assertEqual(database.get_all_staff(), [])
        screen.close()

    def test_saving_then_editing_updates_the_same_row(self) -> None:
        screen = self._screen()
        screen._name_edit.setText("سعيد")
        screen._on_save()
        self.assertEqual(len(database.get_all_staff()), 1)

        member = database.get_all_staff()[0]
        screen._on_edit(member)
        screen._name_edit.setText("سعيد بنعيسى")
        screen._on_save()

        everyone = database.get_all_staff()
        self.assertEqual(len(everyone), 1, "editing created a second row")
        self.assertEqual(everyone[0].full_name, "سعيد بنعيسى")
        screen.close()

    def test_deleting_removes_the_member(self) -> None:
        self._add("للحذف", _in(30))
        screen = self._screen()
        screen._on_delete(database.get_all_staff()[0])

        self.assertEqual(database.get_all_staff(), [])
        screen.close()

    def test_exporting_an_empty_team_never_opens_a_file_dialog(self) -> None:
        opened = []
        QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: opened.append(a) or ("", ""))
        screen = self._screen()
        screen._on_export()

        self.assertEqual(opened, [], "a save dialog opened with nothing to export")
        screen.close()


class StaffPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._settings = SchoolSettings(
            school_name="مؤسسة", school_year="2025-2026", director="المدير",
            company_name="SOC TEST")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_the_printed_list_is_a_real_non_empty_pdf(self) -> None:
        path = Path(self._tmpdir.name) / "staff.pdf"
        members = [
            StaffMember(full_name="سناء", role="عامل نظافة", shift="تناوب",
                        health_cert_expiry=_in(-20), status="غائب"),
            StaffMember(full_name="مصطفى", role="رئيس الطباخين", shift="صباحي",
                        health_cert_expiry=_in(200), status="حاضر"),
        ]
        write_staff_pdf(path, members, self._settings, TODAY)

        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 2000)
        self.assertEqual(path.read_bytes()[:4], b"%PDF")

    def test_a_long_name_does_not_shrink_the_card_below_its_content(self) -> None:
        """The card height is measured from the tallest member, because two
        earlier guesses produced a badge that overflowed the card and then one
        that overlapped the details line."""
        from ui.staff_export import _card_height

        short = [StaffMember(full_name="علي", health_cert_expiry=_in(10))]
        long = [StaffMember(
            full_name="عبد الرحمان بن محمد الإدريسي العلوي الحسني الطاهري",
            role="رئيس الطباخين", shift="تناوب", phone="0600000000",
            health_cert_expiry=_in(-40), status="غائب")]

        self.assertGreater(_card_height(long, 200.0, TODAY),
                           _card_height(short, 200.0, TODAY))

    def test_every_member_reaches_the_page_even_when_many(self) -> None:
        """More members than fit on one page must paginate, not vanish."""
        members = [
            StaffMember(full_name=f"عضو {index}", role="مساعد طباخ",
                        health_cert_expiry=_in(index))
            for index in range(40)
        ]
        path = Path(self._tmpdir.name) / "many.pdf"
        write_staff_pdf(path, members, self._settings, TODAY)

        self.assertGreater(path.stat().st_size, 2000)
        # A 40-card sheet cannot be one page at two columns per row.
        self.assertGreater(path.read_bytes().count(b"/Type /Page"), 1)


if __name__ == "__main__":
    unittest.main()
