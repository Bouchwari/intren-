"""Size wrapped Excel rows explicitly, including horizontal merged cells."""
import math
import textwrap
from copy import copy
from typing import Iterable, TYPE_CHECKING

from PySide6.QtGui import QFont, QFontInfo, QFontMetricsF, QGuiApplication, QTextLayout, QTextOption

if TYPE_CHECKING:
    from openpyxl.worksheet.worksheet import Worksheet


def columns_width_pixels(ws: "Worksheet", first: int, last: int) -> float:
    from openpyxl.utils import get_column_letter

    width = 0.0
    for col in range(first, last + 1):
        dimension = ws.column_dimensions.get(get_column_letter(col))
        units = (dimension.width if dimension is not None else
                 ws.sheet_format.defaultColWidth or 8.43)
        width += math.floor(units * 7 + 5)
    return width


def prefer_single_line(ws: "Worksheet", rows: Iterable[int], min_size: float = 9) -> None:
    """Fit readable single-line text first; wrap only when it cannot fit."""
    merges = list(ws.merged_cells.ranges)
    for row in rows:
        for cell in ws[row]:
            if not isinstance(cell.value, str) or cell.data_type == "f":
                continue
            area = next((area for area in merges if cell.coordinate in area), None)
            if area and area.min_row != area.max_row:
                continue
            first, last = (area.min_col, area.max_col) if area else (cell.column, cell.column)
            available = max(1, columns_width_pixels(ws, first, last) - 10)
            original = cell.font.sz or 11
            font = QFont(cell.font.name or "Calibri")
            font.setPixelSize(math.ceil(original * 96 / 72))
            font.setBold(bool(cell.font.bold))
            measured = (QFontMetricsF(font).horizontalAdvance(cell.value)
                        if QGuiApplication.instance() and QFontInfo(font).family()
                        else len(cell.value) * original * 0.85)
            fitted = min(original, math.floor(original * available / max(1, measured) * 2) / 2)
            alignment, style = copy(cell.alignment), copy(cell.font)
            if "\n" not in cell.value and fitted >= min(min_size, original):
                alignment.wrap_text = False
                alignment.shrink_to_fit = False
                style.sz = fitted
            else:
                alignment.wrap_text = True
                style.sz = min(original, min_size)
            cell.alignment, cell.font = alignment, style


def _wrapped_height(text: str, font_name: str, size: float, bold: bool,
                    width: float) -> float:
    # Use pixel fonts so screen DPI/Windows scaling cannot change the export.
    pixels = math.ceil(size * 96 / 72)
    font = QFont(font_name)
    font.setPixelSize(pixels)
    font.setBold(bold)
    if QGuiApplication.instance() is None or not QFontInfo(font).family():
        # Non-GUI export callers get a conservative full-em estimate.
        chars = max(1, int(width / pixels))
        lines = sum(max(1, len(textwrap.wrap(part, chars)))
                    for part in text.split("\n"))
        return lines * size * 1.4 + 6
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    height = 0.0
    for paragraph in text.split("\n"):
        layout = QTextLayout(paragraph or " ", font)
        layout.setTextOption(option)
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1.0, width))
            height += line.height()
        layout.endLayout()
    return math.ceil(height * 72 / 96) + 6


def fit_wrapped_rows(ws: "Worksheet", rows: Iterable[int]) -> None:
    """Grow requested rows without changing fonts, values or existing space.

    Excel does not reliably AutoFit merged cells. Vertical merges keep their
    explicitly designed multi-row geometry; horizontal merges use their full
    width when measuring text.
    """
    from openpyxl.utils import get_column_letter

    merges = list(ws.merged_cells.ranges)
    for row in rows:
        height = ws.row_dimensions[row].height or ws.sheet_format.defaultRowHeight or 15
        for cell in ws[row]:
            if not isinstance(cell.value, str) or not cell.alignment.wrap_text:
                continue
            if cell.data_type == "f":
                continue
            first, last = cell.column, cell.column
            merged = next((area for area in merges if cell.coordinate in area), None)
            if merged is not None:
                if merged.min_row != merged.max_row:
                    continue
                first, last = merged.min_col, merged.max_col
            width = 0.0
            for col in range(first, last + 1):
                dimension = ws.column_dimensions.get(get_column_letter(col))
                units = (dimension.width if dimension is not None else
                         ws.sheet_format.defaultColWidth or 8.43)
                width += math.floor(units * 7 + 5)
            # Allow for cell padding and small Excel/Qt font metric differences.
            available = max(1.0, width - 10)
            height = max(height, _wrapped_height(
                cell.value, cell.font.name or "Calibri", cell.font.sz or 11,
                bool(cell.font.bold), available))
        ws.row_dimensions[row].height = height
