import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QBuffer, QDate, QIODevice, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QPageLayout
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from core.models import DailyContact, SchoolSettings
from core.document_pipeline import (
    DOC_ABSENCE, DOC_CONTACT, DOC_ORDER_LETTER, DOC_RECEPTION, DOC_REPORT,
)
from data import database
from data.database import get_pdf_print_layout, save_pdf_print_layout
from ui.batch_export import write_combined_pdf
from ui.pdf_layout import _Picture96, write_copy_sheets, write_copy_pdf, choose_company_copies
from ui.theme import load_fonts, body_font_family
from ui.work_pipeline_screen import WorkPipelineScreen


class PdfCopyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        load_fonts()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "copies.pdf"

    def tearDown(self):
        self.doCleanups()
        self.app.processEvents()
        self.tmp.cleanup()

    def open_pdf(self):
        pdf = QPdfDocument()
        buffer = QBuffer(pdf)
        buffer.setData(self.path.read_bytes())
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        pdf.load(buffer)
        self.app.processEvents()
        self.assertEqual(pdf.status(), QPdfDocument.Status.Ready)
        self.addCleanup(pdf.close)
        return pdf

    def test_three_identical_copies_of_one_day_fill_two_landscape_sheets(self):
        seen = []

        def draw(painter, width, height):
            seen.append((width, height))
            painter.setFont(QFont(body_font_family(), 12))
            painter.drawText(QRectF(50, 50, 400, 50), "COPY-ONE")
            painter.fillRect(QRectF(100, 150, 80, 80), QColor("red"))

        write_copy_pdf(self.path, draw, copies=3)
        self.assertEqual(len(seen), 1)
        self.assertLess(seen[0][0], seen[0][1])
        pdf = self.open_pdf()
        self.assertEqual(pdf.pageCount(), 2)
        self.assertGreater(pdf.pagePointSize(0).width(), pdf.pagePointSize(0).height())
        self.assertEqual(pdf.getAllText(0).text().count("COPY-ONE"), 2, repr(pdf.getAllText(0).text()))
        self.assertEqual(pdf.getAllText(1).text().count("COPY-ONE"), 1)
        first = pdf.render(0, QSize(1123, 794))
        second = pdf.render(1, QSize(1123, 794))
        for x in (99, 661):
            self.assertEqual(first.pixelColor(x, 134).name(), "#ff0000")
        self.assertEqual(second.pixelColor(661, 134).name(), "#ff0000")
        self.assertEqual(second.pixelColor(99, 134).alpha(), 0)

    def test_two_days_share_the_middle_sheet_without_rebuilding(self):
        seen = []

        def build(painter, width, height, day):
            seen.append(day)
            painter.setFont(QFont(body_font_family(), 12))
            painter.drawText(QRectF(50, 50, 400, 50), day)
            return "data"

        counts, failed = write_combined_pdf(
            self.path, QDate(2026, 9, 1), QDate(2026, 9, 2),
            QPageLayout.Orientation.Portrait, build, print_layout="three_copies", copies=3,
        )
        self.assertEqual(seen, ["2026-09-01", "2026-09-02"])
        self.assertEqual((counts, failed), ({"data": 2}, []))
        pdf = self.open_pdf()
        self.assertEqual(pdf.pageCount(), 3)
        texts = [pdf.getAllText(i).text() for i in range(3)]
        self.assertEqual(texts[0].count("2026-09-01"), 2)
        self.assertEqual(texts[1].count("2026-09-01"), 1)
        self.assertEqual(texts[1].count("2026-09-02"), 1)
        self.assertEqual(texts[2].count("2026-09-02"), 2)

    def test_notices_print_once_and_failed_partial_content_is_discarded(self):
        def build(painter, width, height, day):
            painter.setFont(QFont(body_font_family(), 12))
            painter.drawText(QRectF(50, 50, 400, 50), day)
            if day == "BAD-PARTIAL":
                raise ValueError("render failed")
            return day

        counts, failed = write_copy_sheets(self.path, ["holiday", "empty", "BAD-PARTIAL", "data"], build, copies=3)
        self.assertEqual(counts, {"holiday": 1, "empty": 1, "data": 1})
        self.assertEqual(failed, ["BAD-PARTIAL"])
        pdf = self.open_pdf()
        self.assertEqual(pdf.pageCount(), 3)
        text = "".join(pdf.getAllText(i).text() for i in range(3))
        self.assertEqual(text.count("holiday"), 1)
        self.assertEqual(text.count("empty"), 1)
        self.assertEqual(text.count("data"), 3)
        # The date remains on the error notice, but never as an official form.
        self.assertEqual(text.count("BAD-PARTIAL"), 1)

    def test_recording_uses_same_dpi_as_pdf_writer(self):
        picture = _Picture96()
        self.assertEqual((picture.logicalDpiX(), picture.logicalDpiY()), (96, 96))

    def test_single_export_reports_render_errors(self):
        with self.assertRaises(RuntimeError):
            write_copy_pdf(self.path, lambda *args: 1 / 0)

    def test_thirty_days_use_forty_five_sheets(self):
        counts, failed = write_copy_sheets(self.path, range(30), lambda *args: "data", copies=3)
        self.assertEqual(counts, {"data": 30})
        self.assertEqual(failed, [])
        self.assertEqual(self.open_pdf().pageCount(), 45)

    def test_default_is_two_internal_copies_on_one_sheet(self):
        write_copy_pdf(self.path, lambda *args: None)
        self.assertEqual(self.open_pdf().pageCount(), 1)

    def test_company_choice_is_explicit_and_cancelable(self):
        for response, expected in (("2", 2), ("3", 3), (None, None)):
            with self.subTest(response=response), patch("ui.dialogs.ask_choice", return_value=response) as ask:
                self.assertEqual(choose_company_copies(None, "رسالة الطلبية", "three_copies"), expected)
                self.assertEqual(ask.call_args.args[1], "رسالة الطلبية")
        with patch("ui.dialogs.ask_choice") as ask:
            self.assertEqual(choose_company_copies(None, "رسالة الطلبية", "standard"), 2)
            ask.assert_not_called()


class PdfLayoutIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "test.db"
        database.init_database()
        self.settings = SchoolSettings(school_name="Test school", school_year="2026", director="Director")
        database.save_school_settings(self.settings)

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_preference_defaults_to_paper_saving_and_round_trips(self):
        self.assertEqual(get_pdf_print_layout(), "three_copies")
        save_pdf_print_layout("standard")
        self.assertEqual(get_pdf_print_layout(), "standard")
        save_pdf_print_layout("three_copies")
        self.assertEqual(get_pdf_print_layout(), "three_copies")
        with self.assertRaises(ValueError):
            save_pdf_print_layout("invalid")
        self.assertEqual(database.get_school_settings().school_name, "Test school")

    def test_settings_control_saves_and_reloads_the_layout(self):
        from ui.settings_screen import SettingsScreen

        screen = SettingsScreen()
        try:
            combo = screen._pdf_layout_combo
            self.assertEqual(combo.currentData(), "three_copies")
            combo.setCurrentIndex(combo.findData("standard"))
            self.assertEqual(get_pdf_print_layout(), "standard")
            screen._load_export_format_preference()
            self.assertEqual(combo.currentData(), "standard")
        finally:
            screen.close()

    def test_order_export_button_uses_layout_only_for_pdf(self):
        from ui import order_letter_screen as order
        from config.settings import EXPORT_FORMAT_PDF, EXPORT_FORMAT_DOCX

        screen = order.OrderLetterScreen()
        try:
            for fmt in (EXPORT_FORMAT_PDF, EXPORT_FORMAT_DOCX):
                with self.subTest(format=fmt), \
                     patch.object(order, "ask_export_format", return_value=fmt), \
                     patch.object(order, "choose_company_copies", return_value=3) as copies, \
                     patch.object(order.QFileDialog, "getSaveFileName", return_value=(str(Path(self.tmp.name) / "order"), "")), \
                     patch.object(order.QMessageBox, "information"), \
                     patch.object(order.QMessageBox, "critical") as error, \
                     patch.object(order, "_write_order_letter_pdf") as pdf, \
                     patch.object(order, "_write_order_letter_docx") as docx:
                    screen._on_export()
                    error.assert_not_called()
                    if fmt == EXPORT_FORMAT_PDF:
                        self.assertEqual(pdf.call_args.kwargs["print_layout"], "three_copies")
                        self.assertEqual(pdf.call_args.kwargs["copies"], 3)
                        docx.assert_not_called()
                    else:
                        docx.assert_called_once()
                        self.assertNotIn("print_layout", docx.call_args.kwargs)
                        pdf.assert_not_called()
                        copies.assert_not_called()
        finally:
            screen.close()

    def test_all_five_batch_builders_default_to_two_sheets_for_two_days(self):
        from ui import daily_report_screen as report

        for day in ("2026-09-01", "2026-09-02"):
            database.save_daily_contact(DailyContact(date=day, meal_type="ghada", collegial_granted=37))
        screen = WorkPipelineScreen(navigate_to=lambda _: None)
        self.addCleanup(screen.close)
        for key in (DOC_CONTACT, DOC_ABSENCE, DOC_ORDER_LETTER, DOC_RECEPTION, DOC_REPORT):
            with self.subTest(key=key), patch.object(report, "_draw_report_copy", wraps=report._draw_report_copy) as draw:
                path = Path(self.tmp.name) / f"{key}.pdf"
                counts, failed = write_combined_pdf(
                    path, QDate(2026, 9, 1), QDate(2026, 9, 2),
                    QPageLayout.Orientation.Portrait,
                    screen._page_builder(key, self.settings, print_layout="three_copies"),
                    print_layout="three_copies",
                )
                self.assertEqual(failed, [])
                pdf = QPdfDocument()
                self.assertEqual(pdf.load(str(path)), QPdfDocument.Error.None_)
                try:
                    # Absences have not been entered, so only two notices are printed.
                    self.assertEqual(pdf.pageCount(), 1 if key == DOC_ABSENCE else 2)
                    if key != DOC_ABSENCE:
                        self.assertIn("37", pdf.getAllText(0).text())
                    if key == DOC_REPORT:
                        self.assertEqual(draw.call_count, 2)
                finally:
                    pdf.close()

    def test_canceling_reception_company_copy_question_does_not_save(self):
        from ui import daily_reception_screen as reception
        from config.settings import EXPORT_FORMAT_PDF

        screen = reception.DailyReceptionScreen()
        try:
            with patch.object(reception, "ask_export_format", return_value=EXPORT_FORMAT_PDF), \
                 patch.object(reception, "choose_company_copies", return_value=None), \
                 patch.object(reception.QFileDialog, "getSaveFileName") as file, \
                 patch.object(reception, "save_daily_reception_record") as save:
                screen._on_export()
            file.assert_not_called()
            save.assert_not_called()
        finally:
            screen.close()
