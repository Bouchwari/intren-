import sys
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QLabel, QPushButton, QScrollArea, QStyleFactory, QTableWidget, QWidget

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from main import _apply_light_palette
from core.models import DailyReport
from data import database
from ui.report_options import ReportReviewDialog
from ui.settings_screen import SettingsScreen
from ui.header_editor import HeaderEditorDialog
from ui.holiday_calendar_dialog import HolidayCalendarDialog
from ui.document_header import _original_template_header_image
from ui.theme import build_stylesheet, load_fonts
from ui import theme


class ResponsiveReportUiChecks(unittest.TestCase):
    __test__ = False
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.windows = set(self.app.topLevelWidgets())
        self.stylesheet = self.app.styleSheet()
        self.palette = self.app.palette()
        self.direction = self.app.layoutDirection()
        self.font = self.app.font()
        self.style_name = self.app.style().objectName()
        self.font_families = (theme._body_font_family, theme._title_font_family)
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "test.db"
        database.init_database()
        _apply_light_palette(self.app)
        load_fonts()
        self.app.setStyleSheet(build_stylesheet())
        self.app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    def tearDown(self) -> None:
        for window in self.app.topLevelWidgets():
            if window not in self.windows:
                window.close()
                window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.setStyleSheet(self.stylesheet)
        self.app.setStyle(QStyleFactory.create(self.style_name))
        self.app.setFont(self.font)
        self.app.setPalette(self.palette)
        self.app.setLayoutDirection(self.direction)
        theme._body_font_family, theme._title_font_family = self.font_families
        database.DB_PATH = self.original_db
        self.temp.cleanup()

    def _assert_rows_fit(self, table: QTableWidget) -> None:
        for row in range(table.rowCount()):
            label = table.cellWidget(row, 0)
            self.assertTrue(label.wordWrap())
            self.assertGreaterEqual(table.rowHeight(row), label.heightForWidth(table.columnWidth(0)))
            for column in range(1, table.columnCount()):
                editor = table.cellWidget(row, column)
                self.assertGreaterEqual(table.rowHeight(row), editor.sizeHint().height())

    def test_settings_fit_restored_width_and_resize_without_clipping_rows(self) -> None:
        parent = QWidget()
        parent.setStyleSheet("background-color:#f5f5f0; border:none;")
        screen = SettingsScreen()
        screen.setParent(parent)
        parent.show()
        screen.show()
        for width in (1200, 900, 760, 680, 1200):
            with self.subTest(width=width):
                screen.resize(width, 700)
                self.app.processEvents()
                scroll = screen.findChild(QScrollArea)
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                self.assertLessEqual(screen._report_preferences.width(), scroll.viewport().width())
                self._assert_rows_fit(screen._report_preferences.table)
                for form in screen.findChildren(QFormLayout):
                    for row in range(form.rowCount()):
                        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                        label = item.widget() if item else None
                        if isinstance(label, QLabel):
                            self.assertIn("background:transparent", label.styleSheet())
                            self.assertTrue(label.wordWrap())
                            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))

    def test_holiday_review_fits_small_window_and_source_is_available(self) -> None:
        from config.settings import RESOURCE_DIR
        dialog = HolidayCalendarDialog()
        dialog.show()
        for width, height in ((870, 660), (640, 460)):
            dialog.resize(width, height)
            self.app.processEvents()
            self.assertEqual(dialog.table.horizontalScrollBar().maximum(), 0)
            for row in range(dialog.table.rowCount()):
                label = dialog.table.cellWidget(row, 1)
                self.assertGreaterEqual(dialog.table.rowHeight(row), label.heightForWidth(label.width()))
            for button in dialog.findChildren(QPushButton):
                self.assertTrue(dialog.rect().contains(button.geometry()))
        self.assertFalse(QPixmap(str(RESOURCE_DIR / "assets" / "holidays_2026_2027.webp")).isNull())

    def test_review_buttons_and_rows_fit_with_parent_and_real_theme(self) -> None:
        parent = QWidget()
        parent.setStyleSheet("background:#f5f5f0;")
        dialog = ReportReviewDialog(["2026-11-05"], parent)
        dialog.show()
        for width, height in ((940, 650), (760, 540), (640, 460)):
            dialog.resize(width, height)
            self.app.processEvents()
            self.assertEqual((dialog.width(), dialog.height()), (width, height))
            for button in dialog.findChildren(QPushButton):
                self.assertTrue(button.isVisible())
                self.assertTrue(dialog.rect().contains(button.geometry()))
                self.assertGreaterEqual(button.width(), button.sizeHint().width())
            self._assert_rows_fit(dialog.table)
        cancel = dialog.findChild(QPushButton, "reportReviewCancel")
        self.assertNotEqual(cancel._bg, cancel._text_color)
        self.assertNotEqual(cancel._hover_bg, cancel._text_color)
        cancel.click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertIsNone(database.get_daily_report("2026-11-05"))

    def test_saved_review_accepts_edits_without_writing_until_approval(self) -> None:
        database.save_daily_report(DailyReport(date="2026-11-06", notes="Original"))
        dialog = ReportReviewDialog(["2026-11-06"])
        dialog.show()
        self.app.processEvents()
        self.assertFalse(dialog.notes.isReadOnly())
        self.assertTrue(all(combo.isEnabled() for combo in dialog.combos.values()))
        self.assertEqual(dialog.overrides(), {})
        dialog.notes.setPlainText("Updated")
        self.assertEqual(dialog.overrides(), {"2026-11-06": {"notes": "Updated"}})
        dialog.reject()
        self.assertEqual(database.get_daily_report("2026-11-06").notes, "Original")

    def test_dropdown_uses_available_qt_arrow_asset(self) -> None:
        resource = ":/qt-project.org/styles/commonstyle/images/arrow-down-16.png"
        self.assertFalse(QPixmap(resource).isNull())
        self.assertIn(resource, build_stylesheet())

    def test_header_editor_fits_small_window(self) -> None:
        editor = HeaderEditorDialog(_original_template_header_image())
        editor.show()
        for width, height in ((780, 650), (600, 540)):
            editor.resize(width, height)
            self.app.processEvents()
            self.assertEqual((editor.width(), editor.height()), (width, height))
            for button in editor.findChildren(QPushButton):
                self.assertTrue(editor.rect().contains(button.geometry()))
            self.assertFalse(editor.output_preview.pixmap().isNull())
        editor.sliders["left"].setValue(10)
        self.assertGreater(editor.crop_rect().left(), 0)
        editor.reject()


class ResponsiveReportUiTests(unittest.TestCase):
    def test_real_theme_in_clean_qt_process(self) -> None:
        # Replacing QApplication's style after hundreds of other UI tests can
        # repolish their retained widgets. Exercise startup in a fresh process.
        for scale in ("1", "1.5"):
            with self.subTest(scale=scale):
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve())],
                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_SCALE_FACTOR": scale},
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ResponsiveReportUiChecks)
    outcome = unittest.TextTestRunner().run(suite)
    sys.exit(0 if outcome.wasSuccessful() else 1)
