import datetime
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl
from PySide6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_SHOUR,
)
from core.models import DailyContact, DailyAbsence, SchoolSettings
from data import database
from data.monthly_repo import get_daily_meals_by_lot_for_month
from ui import quarterly_reception_screen as qrs


class MonthAddTests(unittest.TestCase):
    """Pure function tests — a quarter can start in any month and must
    roll over into the next year correctly."""

    def test_no_rollover(self) -> None:
        self.assertEqual(qrs._month_add(2026, 1, 1), (2026, 2))
        self.assertEqual(qrs._month_add(2026, 1, 2), (2026, 3))

    def test_rolls_over_into_next_year(self) -> None:
        self.assertEqual(qrs._month_add(2026, 11, 0), (2026, 11))
        self.assertEqual(qrs._month_add(2026, 11, 1), (2026, 12))
        self.assertEqual(qrs._month_add(2026, 11, 2), (2027, 1))

    def test_quarter_months_full_triplet(self) -> None:
        self.assertEqual(
            qrs._quarter_months(2026, 11),
            [(2026, 11), (2026, 12), (2027, 1)],
        )


class GetDailyMealsByLotTests(unittest.TestCase):
    """Direct unit tests on the data-layer query powering the attestation
    — this is the document whose numbers are the real payment basis, so
    every number here must be traceable to real daily_contact/absence
    rows, never estimated."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_returns_one_row_per_calendar_day_even_with_no_data(self) -> None:
        rows = get_daily_meals_by_lot_for_month("2026-02")  # Feb 2026 = 28 days
        self.assertEqual(len(rows), 28)
        self.assertTrue(all(rows[i]["day"] == i + 1 for i in range(28)))
        self.assertTrue(all(rows[i]["lot901_ftour"] == 0 for i in range(28)))

    def test_net_meals_split_correctly_by_lot_with_absence_subtracted(self) -> None:
        database.save_daily_contact(DailyContact(
            date="2026-01-05", meal_type=MEAL_GHADA,
            primary_granted=15, collegial_granted=10, qualifying_granted=8, monitors=3,
        ))
        database.save_daily_absence(DailyAbsence(
            date="2026-01-05", meal_type=MEAL_GHADA,
            primary_granted=2, collegial_granted=1,
        ))
        rows = get_daily_meals_by_lot_for_month("2026-01")
        day5 = next(r for r in rows if r["day"] == 5)
        # LOT 901 = primary + collegial + monitors (qualifying has its own LOT 902)
        self.assertEqual(day5["lot901_ghada"], (15 - 2) + (10 - 1) + 3)
        self.assertEqual(day5["lot902_ghada"], 8)

    def test_net_meals_never_negative(self) -> None:
        """Absence entered without matching contact must floor at 0, not
        go negative — a real data-entry mistake shouldn't corrupt a
        financial total."""
        database.save_daily_absence(DailyAbsence(
            date="2026-01-05", meal_type=MEAL_FTOUR, primary_granted=5,
        ))
        rows = get_daily_meals_by_lot_for_month("2026-01")
        day5 = next(r for r in rows if r["day"] == 5)
        self.assertEqual(day5["lot901_ftour"], 0)


class QuarterlyReceptionScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية اختبار", school_name_fr="Test School",
            school_year="2025/2026", director="MOHAMED TEST",
            gestionnaire="AHMED TEST", company_name="STE TEST",
            contract_number="01/TEST/2026", city_fr="TESTVILLE",
        ))
        self._originals = {
            "file_save": qrs.QFileDialog.getSaveFileName,
            "message_warning": qrs.QMessageBox.warning,
            "message_information": qrs.QMessageBox.information,
            "message_critical": qrs.QMessageBox.critical,
        }

    def tearDown(self) -> None:
        qrs.QFileDialog.getSaveFileName = self._originals["file_save"]
        qrs.QMessageBox.warning = self._originals["message_warning"]
        qrs.QMessageBox.information = self._originals["message_information"]
        qrs.QMessageBox.critical = self._originals["message_critical"]
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _seed_january(self) -> None:
        for day in (5, 6):
            for meal in (MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA):
                database.save_daily_contact(DailyContact(
                    date=f"2026-01-{day:02d}", meal_type=meal,
                    primary_granted=15, collegial_granted=10, qualifying_granted=8, monitors=3,
                ))
                database.save_daily_absence(DailyAbsence(
                    date=f"2026-01-{day:02d}", meal_type=meal,
                    primary_granted=2, collegial_granted=1,
                ))

    def test_screen_loads_and_generates_on_open(self) -> None:
        self._seed_january()
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        screen._generate()
        self.assertEqual(len(screen._quarter_data), 3)
        self.assertEqual(screen._quarter_data[0]["label"], "يناير 2026")
        screen.close()

    def test_quarter_rolls_into_next_year_in_generated_data(self) -> None:
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(10)  # نونبر (November)
        screen._generate()
        labels = [m["label"] for m in screen._quarter_data]
        self.assertEqual(labels, ["نونبر 2026", "دجنبر 2026", "يناير 2027"])
        screen.close()

    def test_table_totals_match_real_seeded_data(self) -> None:
        self._seed_january()
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        screen._generate()

        # Grand total row is the last row; column 1 = lot901_ftour
        last_row = screen._table.rowCount() - 1
        expected_lot901 = 2 * ((15 - 2) + (10 - 1) + 3)  # 2 days seeded
        expected_lot902 = 2 * 8
        self.assertEqual(screen._table.item(last_row, 1).text(), f"{expected_lot901:,}")
        self.assertEqual(screen._table.item(last_row, 4).text(), f"{expected_lot902:,}")
        screen.close()

    def test_export_with_no_data_warns_and_never_opens_file_dialog(self) -> None:
        dialog_calls: list[tuple] = []
        warnings: list[str] = []
        qrs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: dialog_calls.append((a, k)) or ("", ""))
        qrs.QMessageBox.warning = staticmethod(lambda parent, title, text, *a, **k: warnings.append(text))

        screen = qrs.QuarterlyReceptionScreen()  # no data seeded anywhere
        screen._export_excel()

        self.assertEqual(dialog_calls, [])
        self.assertEqual(len(warnings), 1)
        screen.close()

    def test_export_excel_matches_real_data_no_ramadan(self) -> None:
        out_path = Path(self._tmpdir.name) / "export_test.xlsx"
        qrs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        qrs.QMessageBox.information = staticmethod(lambda *a, **k: None)

        self._seed_january()
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        screen._generate()
        screen._export_excel()
        self.assertTrue(out_path.exists())

        wb = openpyxl.load_workbook(out_path)
        # Sheet names, order and the 4-sheet shape all come straight from the
        # real template — see the export section's module note.
        self.assertEqual(
            wb.sheetnames,
            ["MOIS 01 2026", "MOIS 02 2026", "MOIS 03 2026", "RECAP A IMPRIMER"],
        )

        jan = wb["MOIS 01 2026"]
        # Both LOTs sit side by side: A-D then a spacer column then F-I.
        self.assertEqual(jan["A1"].value, "901 (PRIMAIRE ET COLLEGIAL)")
        self.assertEqual(jan["F1"].value, "902 (QUALIFIANT)")
        self.assertEqual(
            [jan.cell(row=3, column=c).value for c in range(1, 5)],
            ["JOURS", "PETIT DEJ,", "DEJEUNER", "DINER"],
        )
        self.assertEqual(
            [jan.cell(row=3, column=c).value for c in range(6, 10)],
            ["JOURS", "PETIT DEJ,", "DEJEUNER", "DINER"],
        )
        # No Ramadan blocks on a non-Ramadan month — nothing past column I.
        self.assertEqual(jan.max_column, 9)
        # Column A prints real dates; the 902 JOURS column prints day numbers.
        self.assertEqual(jan["A4"].value.date(), datetime.date(2026, 1, 1))
        self.assertEqual(jan["F4"].value, 1)
        # TOTAL row carries live formulas, exactly like the template.
        self.assertEqual(jan["A35"].value, "TOTAL")
        self.assertEqual(jan["B35"].value, "=SUM(B4:B34)")

        recap = wb["RECAP A IMPRIMER"]
        recap_text = "\n".join(str(c.value) for row in recap.iter_rows() for c in row if c.value)
        self.assertIn("Attestation de réception", recap_text)
        self.assertIn("LES MOIS: JANVIER-FEVRIER-MARS", recap_text)
        self.assertIn("MOHAMED TEST", recap_text)
        self.assertIn("AHMED TEST", recap_text)
        self.assertIn("STE TEST", recap_text)
        self.assertIn("01/TEST/2026", recap_text)
        # Meal figures are cross-sheet formulas, not frozen numbers.
        self.assertEqual(
            recap["E21"].value,
            "='MOIS 01 2026'!B35+'MOIS 02 2026'!B32+'MOIS 03 2026'!B35",
        )
        screen.close()

    def test_recap_dated_at_quarter_end_not_today(self) -> None:
        """The template dates the attestation on the quarter's last day
        (its own copy reads 30/03/2026). Using today's date instead would
        let a re-export silently re-date an already-signed document."""
        out_path = Path(self._tmpdir.name) / "export_date.xlsx"
        qrs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        qrs.QMessageBox.information = staticmethod(lambda *a, **k: None)

        self._seed_january()
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        screen._generate()
        screen._export_excel()

        recap = openpyxl.load_workbook(out_path)["RECAP A IMPRIMER"]
        text = "\n".join(str(c.value) for row in recap.iter_rows() for c in row if c.value)
        self.assertIn("31/03/2026", text)
        screen.close()

    def test_sundays_are_highlighted_like_the_template(self) -> None:
        """The template green-highlights every Sunday across all three of
        its month sheets — verified there before being reproduced here."""
        out_path = Path(self._tmpdir.name) / "export_sun.xlsx"
        qrs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        qrs.QMessageBox.information = staticmethod(lambda *a, **k: None)

        self._seed_january()
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        screen._generate()
        screen._export_excel()

        jan = openpyxl.load_workbook(out_path)["MOIS 01 2026"]
        highlighted = [
            row - 3 for row in range(4, 35)
            if jan.cell(row=row, column=2).fill.patternType == "solid"
            and jan.cell(row=row, column=2).fill.fgColor.rgb[-6:] == qrs._FILL_SUNDAY
        ]
        self.assertEqual(highlighted, [4, 11, 18, 25])  # the Sundays of Jan 2026
        screen.close()

    def test_export_excel_ramadan_month_carries_real_recorded_counts(self) -> None:
        """Ramadan blocks appear on a month because that month really
        contains Ramadan (per the period in Settings), not because someone
        ticked a box — and they carry the real إفطار/سحور counts recorded on
        ورقة الاتصال, never invented ones."""
        out_path = Path(self._tmpdir.name) / "export_ramadan.xlsx"
        qrs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out_path), ""))
        qrs.QMessageBox.information = staticmethod(lambda *a, **k: None)

        # Ramadan 1447 runs mid-Feb to mid-Mar 2026 — only March is in range
        # here, so only the March sheet may grow its Ramadan blocks.
        settings = database.get_school_settings()
        settings.ramadan_start = "2026-03-01"
        settings.ramadan_end = "2026-03-19"
        database.save_school_settings(settings)

        database.save_daily_contact(DailyContact(
            date="2026-03-02", meal_type=MEAL_FTOUR,
            primary_granted=12, collegial_granted=9, qualifying_granted=6, monitors=2,
        ))
        # Real Ramadan attendance for the same day.
        database.save_daily_contact(DailyContact(
            date="2026-03-02", meal_type=MEAL_IFTAR,
            primary_granted=20, collegial_granted=10, qualifying_granted=4,
        ))
        database.save_daily_contact(DailyContact(
            date="2026-03-02", meal_type=MEAL_SHOUR,
            primary_granted=15, collegial_granted=5, qualifying_granted=3,
        ))
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)  # Jan/Feb/Mar
        self.app.processEvents()
        self.assertEqual(
            [m["is_ramadan"] for m in screen._quarter_data], [False, False, True])
        screen._export_excel()

        wb = openpyxl.load_workbook(out_path)
        march = wb["MOIS 03 2026"]
        # Ramadan does NOT widen the existing blocks — it adds two more of
        # them further right (K-M and O-Q), exactly as the real template does.
        self.assertEqual(march.max_column, 17)  # through column Q
        self.assertEqual(march["K1"].value, "901 (PRIMAIRE ET COLLEGIAL)")
        self.assertEqual(march["O1"].value, "902 (QUALIFIANT)")
        self.assertEqual(
            [march.cell(row=3, column=c).value for c in range(11, 14)],
            ["JOURS", "FTOUR", "SHOUR"],
        )
        # January is outside Ramadan, so it keeps the plain 9-column shape.
        self.assertEqual(wb["MOIS 01 2026"].max_column, 9)
        # The normal blocks keep their own three meal columns untouched.
        self.assertEqual(
            [march.cell(row=3, column=c).value for c in range(1, 5)],
            ["JOURS", "PETIT DEJ,", "DEJEUNER", "DINER"],
        )
        # Real contact data still lands in the normal block...
        self.assertEqual(march["B5"].value, 12 + 9 + 2)  # March 2 = row 5
        # ...and FTOUR/SHOUR now carry the real recorded Ramadan counts.
        # March 2 = row 5. LOT 901 = primary + collegial (+ monitors).
        self.assertEqual(march["L5"].value, 20 + 10)   # إفطار, 901
        self.assertEqual(march["M5"].value, 15 + 5)    # سحور, 901
        self.assertEqual(march["P5"].value, 4)         # إفطار, 902 (qualifying)
        self.assertEqual(march["Q5"].value, 3)         # سحور, 902
        # A day with no Ramadan record stays 0 — never a fabricated number.
        self.assertEqual(march["L6"].value, 0)
        screen.close()


class QuarterlyReceptionAuditFixTests(unittest.TestCase):
    """Regressions for the defects an adversarial audit of this export
    found. Each one was reproduced before being fixed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        database.save_school_settings(SchoolSettings(
            school_name="ثانوية اختبار", school_name_fr="Test School",
            school_year="2025/2026", director="MOHAMED TEST",
            gestionnaire="AHMED TEST", company_name="STE TEST",
            contract_number="01/TEST/2026", city_fr="TESTVILLE",
        ))
        self._originals = {
            "file_save": qrs.QFileDialog.getSaveFileName,
            "message_warning": qrs.QMessageBox.warning,
            "message_information": qrs.QMessageBox.information,
            "message_critical": qrs.QMessageBox.critical,
        }

    def tearDown(self) -> None:
        qrs.QFileDialog.getSaveFileName = self._originals["file_save"]
        qrs.QMessageBox.warning = self._originals["message_warning"]
        qrs.QMessageBox.information = self._originals["message_information"]
        qrs.QMessageBox.critical = self._originals["message_critical"]
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def _export(self, screen, name: str):
        out = Path(self._tmpdir.name) / name
        qrs.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(out), ""))
        qrs.QMessageBox.information = staticmethod(lambda *a, **k: None)
        screen._export_excel()
        return out

    def test_screen_rereads_database_when_navigated_to(self) -> None:
        """CRITICAL regression: MainWindow builds screens once at startup and
        only re-reads one through refresh(). Without that hook the exported
        attestation stayed frozen at launch-time data, silently omitting
        every meal entered during the session."""
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        self.app.processEvents()
        before = sum(d["lot901_ghada"] for d in screen._quarter_data[0]["days"])

        database.save_daily_contact(DailyContact(
            date="2026-01-07", meal_type=MEAL_GHADA, collegial_granted=250))
        self.assertTrue(hasattr(screen, "refresh"))
        screen.refresh()  # what MainWindow._navigate calls

        after = sum(d["lot901_ghada"] for d in screen._quarter_data[0]["days"])
        self.assertEqual(after, before + 250)
        screen.close()

    def test_year_crossing_quarter_labels_each_month_with_its_own_year(self) -> None:
        """Dec-Jan-Feb is the standard Moroccan 2nd trimester. Labelling the
        whole period with only the LAST month's year made the signed
        attestation certify months belonging to the previous year, while its
        own formulas summed the correct sheets."""
        database.save_daily_contact(DailyContact(
            date="2026-12-07", meal_type=MEAL_GHADA, collegial_granted=40))
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(11)  # دجنبر / December
        self.app.processEvents()
        out = self._export(screen, "cross.xlsx")

        wb = openpyxl.load_workbook(out)
        self.assertEqual(
            wb.sheetnames,
            ["MOIS 12 2026", "MOIS 01 2027", "MOIS 02 2027", "RECAP A IMPRIMER"],
        )
        recap = wb["RECAP A IMPRIMER"]
        text = "\n".join(str(c.value) for row in recap.iter_rows() for c in row if c.value)
        # December belongs to 2026 and must say so...
        self.assertIn("DECEMBRE 2026", text)
        self.assertIn("JANVIER 2027", text)
        # ...and the old bug's output must not reappear.
        self.assertNotIn("DECEMBRE-JANVIER-FEVRIER-  2027", text)
        screen.close()

    def test_ramadan_months_come_from_settings_and_day_overrides(self) -> None:
        """Ramadan is decided by the period in Settings plus any per-day
        correction — never by a positional checkbox, which used to let a tick
        follow its slot onto an unrelated month when the quarter changed."""
        settings = database.get_school_settings()
        settings.ramadan_start = "2026-03-01"
        settings.ramadan_end = "2026-03-19"
        database.save_school_settings(settings)

        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)   # Jan/Feb/Mar
        self.app.processEvents()
        self.assertEqual(
            [m["is_ramadan"] for m in screen._quarter_data], [False, False, True])

        # Moving to a quarter with no Ramadan must clear it everywhere.
        screen._first_month_combo.setCurrentIndex(3)   # Apr/May/Jun
        self.app.processEvents()
        self.assertFalse(any(m["is_ramadan"] for m in screen._quarter_data))

        # A single-day correction is enough to bring a month back in — the
        # moon sighting can move the real start by a day.
        database.set_ramadan_override("2026-05-04", True)
        screen._generate()
        self.assertEqual(
            [m["is_ramadan"] for m in screen._quarter_data], [False, True, False])
        screen.close()

    def test_recap_carries_the_templates_print_geometry(self) -> None:
        """RECAP A IMPRIMER is the sheet that gets printed and signed. Without
        the template's A4/88%/thin-margin page setup it spilled across 2-3
        sheets of paper, splitting the quantities from the signatures."""
        database.save_daily_contact(DailyContact(
            date="2026-01-07", meal_type=MEAL_GHADA, collegial_granted=40))
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        self.app.processEvents()
        out = self._export(screen, "print.xlsx")

        recap = openpyxl.load_workbook(out)["RECAP A IMPRIMER"]
        self.assertEqual(recap.page_setup.orientation, "portrait")
        self.assertEqual(int(recap.page_setup.paperSize), 9)  # A4
        self.assertEqual(int(recap.page_setup.scale), 88)
        self.assertLess(float(recap.page_margins.left), 0.1)
        # Row heights the template tuned for print must survive too.
        self.assertAlmostEqual(recap.row_dimensions[17].height, 44.25, places=2)
        self.assertAlmostEqual(recap.row_dimensions[43].height, 23.25, places=2)
        screen.close()

    def test_signature_boxes_are_actually_framed(self) -> None:
        """The signers physically sign inside two boxes; they were being
        merged but never given borders, so the whole lower half of the
        attestation printed as bare floating text."""
        database.save_daily_contact(DailyContact(
            date="2026-01-07", meal_type=MEAL_GHADA, collegial_granted=40))
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        self.app.processEvents()
        out = self._export(screen, "borders.xlsx")

        recap = openpyxl.load_workbook(out)["RECAP A IMPRIMER"]
        for coord in ("A40", "E40", "A41", "E41", "A43", "E43"):
            self.assertIsNotNone(
                recap[coord].border.left.style, f"{coord} has no frame")
        screen.close()

    def test_absence_only_reduces_its_own_category(self) -> None:
        """Netting the LOT aggregate let an absence booked against one
        category cancel a different category's real attendance, and the
        floor-at-zero then hid that it happened."""
        database.save_daily_contact(DailyContact(
            date="2026-01-05", meal_type=MEAL_GHADA, primary_granted=50))
        database.save_daily_absence(DailyAbsence(
            date="2026-01-05", meal_type=MEAL_GHADA, collegial_granted=60))

        rows = get_daily_meals_by_lot_for_month("2026-01")
        day5 = next(r for r in rows if r["day"] == 5)
        # The 50 primary meals really happened and must survive.
        self.assertEqual(day5["lot901_ghada"], 50)

    def test_export_failure_shows_arabic_and_logs_the_detail(self) -> None:
        """CLAUDE.md §5/§9: users get a friendly Arabic message, the technical
        detail goes to the log — never a raw English exception on screen."""
        database.save_daily_contact(DailyContact(
            date="2026-01-07", meal_type=MEAL_GHADA, collegial_granted=40))
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2026")
        screen._first_month_combo.setCurrentIndex(0)
        self.app.processEvents()

        shown: list = []
        qrs.QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: (str(Path(self._tmpdir.name) / "x.xlsx"), ""))
        qrs.QMessageBox.critical = staticmethod(
            lambda parent, title, text, *a, **k: shown.append(text))
        original_writer = qrs._write_quarterly_reception_excel
        qrs._write_quarterly_reception_excel = staticmethod(
            lambda *a, **k: (_ for _ in ()).throw(PermissionError("Errno 13")))
        try:
            with self.assertLogs(qrs._LOGGER, level="ERROR") as logged:
                screen._export_excel()
        finally:
            qrs._write_quarterly_reception_excel = original_writer

        self.assertEqual(len(shown), 1)
        self.assertNotIn("Errno 13", shown[0])          # no raw exception text
        self.assertNotIn("Permission", shown[0])
        self.assertTrue(any("Permission denied" in line or "Errno 13" in line
                            for line in logged.output))  # but it IS logged
        screen.close()

    def test_no_data_message_does_not_tell_user_to_generate_again(self) -> None:
        """The quarter is always generated by the time تصدير is clickable, so
        'generate first' sent the user in a loop. The message must name the
        real cause instead."""
        warnings: list = []
        qrs.QMessageBox.warning = staticmethod(
            lambda parent, title, text, *a, **k: warnings.append(text))
        screen = qrs.QuarterlyReceptionScreen()
        screen._year_combo.setCurrentText("2029")  # nothing recorded
        self.app.processEvents()
        screen._export_excel()

        self.assertEqual(len(warnings), 1)
        self.assertNotIn("ولّد المحضر أولاً", warnings[0])
        self.assertIn("لا توجد وجبات", warnings[0])
        screen.close()


if __name__ == "__main__":
    unittest.main()
