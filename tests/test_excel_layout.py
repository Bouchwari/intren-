import sys
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ui.excel_layout import fit_wrapped_rows, prefer_single_line


class ExcelLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        # Restricted Windows test sessions may not enumerate system fonts.
        for name in ("arial.ttf", "calibri.ttf"):
            path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))

    def test_long_wrapped_text_grows_without_changing_values_or_font(self) -> None:
        ws = Workbook().active
        ws.column_dimensions["A"].width = 11.3
        text = "الأولى إعدادي مسار دولي خيار فرنسية"
        ws["A1"] = text
        ws["A1"].font = Font(name="Arial", size=11)
        ws["A1"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[1].height = 21.5
        fit_wrapped_rows(ws, [1])
        self.assertGreater(ws.row_dimensions[1].height, 40)
        self.assertEqual(ws["A1"].value, text)
        self.assertEqual(ws["A1"].font.sz, 11)

    def test_horizontal_merge_uses_full_width_and_retains_minimum_height(self) -> None:
        ws = Workbook().active
        ws.merge_cells("A1:D1")
        ws["A1"] = "Le directeur de l'établissement"
        ws["A1"].font = Font(name="Arial", size=11)
        ws["A1"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[1].height = 36
        fit_wrapped_rows(ws, [1])
        self.assertEqual(ws.row_dimensions[1].height, 36)

    def test_vertical_merges_formulas_and_other_rows_are_untouched(self) -> None:
        ws = Workbook().active
        ws.merge_cells("A1:A3")
        ws["A1"] = "A long vertical header " * 10
        ws["A1"].alignment = Alignment(wrap_text=True)
        ws["B1"] = "=SUM(B4:B100)"
        ws["B1"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[1].height = 20
        ws.row_dimensions[4].height = 35
        fit_wrapped_rows(ws, [1])
        self.assertEqual(ws.row_dimensions[1].height, 20)
        self.assertEqual(ws.row_dimensions[4].height, 35)
        self.assertEqual(ws["B1"].value, "=SUM(B4:B100)")

    def test_explicit_newlines_and_headless_exports_are_supported(self) -> None:
        ws = Workbook().active
        ws["A1"] = "One\nTwo\nThree"
        ws["A1"].alignment = Alignment(wrap_text=True)
        with patch("ui.excel_layout.QGuiApplication.instance", return_value=None):
            fit_wrapped_rows(ws, [1])
        self.assertGreater(ws.row_dimensions[1].height, 45)

    def test_single_line_uses_merged_width_without_changing_content(self) -> None:
        ws = Workbook().active
        ws.merge_cells("A1:D1")
        ws["A1"] = "Le directeur de l'etablissement"
        ws["A1"].font = Font(name="Arial", size=11)
        ws["A1"].alignment = Alignment(wrap_text=True)
        prefer_single_line(ws, [1])
        self.assertFalse(ws["A1"].alignment.wrap_text)
        self.assertGreaterEqual(ws["A1"].font.sz, 9)
        self.assertEqual(ws["A1"].value, "Le directeur de l'etablissement")

    def test_single_line_falls_back_to_readable_wrapping(self) -> None:
        ws = Workbook().active
        ws.column_dimensions["A"].width = 8
        ws["A1"] = "An exceptionally long name that cannot fit in one line"
        ws["A1"].font = Font(name="Arial", size=11)
        ws["B1"] = "One\nTwo"
        ws["C1"] = "=SUM(D1:F1)"
        with patch("ui.excel_layout.QGuiApplication.instance", return_value=None):
            prefer_single_line(ws, [1])
            fit_wrapped_rows(ws, [1])
        self.assertTrue(ws["A1"].alignment.wrap_text)
        self.assertTrue(ws["B1"].alignment.wrap_text)
        self.assertEqual(ws["A1"].font.sz, 9)
        self.assertGreater(ws.row_dimensions[1].height, 30)
        self.assertEqual(ws["C1"].value, "=SUM(D1:F1)")
