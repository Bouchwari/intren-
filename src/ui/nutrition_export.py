"""
src/ui/nutrition_export.py
التوزيع الكمي لمكونات الوجبات الغذائية — the quantity breakdown that the
ministry guide requires to accompany the approved weekly program.

الدليل المسطري, p.5, on the regional committee preparing the program:
    "إرفاق مكونات البرنامج الغذائي المعتمد بالتوزيع الكمي لمكونات الوجبات
     الغذائية"

The guide states the requirement but gives no template and no figures — the
committee sets those, and the contracted doctors sign the approved programs.
So this is our own layout carrying the school's own recorded quantities, with
a signature area for that approval. Nothing here is estimated: a meal with no
components recorded simply does not appear.
"""
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter,
    QPen,
)

from config.settings import (
    COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
)
from core.models import FoodProduct, MealComponent, SchoolSettings
from core.nutrition import (
    BASIS_PER_100G, BASIS_PER_100ML, BASIS_PER_UNIT, recipe_values,
)
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header

_TITLE = "التوزيع الكمي لمكونات الوجبات الغذائية"
_SUBTITLE = "يرفق بالبرنامج الغذائي الأسبوعي المعتمد"
_LBL_PROGRAM = "البرنامج"
_LBL_TOTAL = "مجموع الوجبة"
_HDR = ["المادة الغذائية", "الكمية", "السعرات"]
_SIGN_ROLES = ["مدير(ة) المؤسسة", "مسير المصالح المادية والمالية",
               "الطبيب(ة) المتعاقد معه"]

_UNITS = {BASIS_PER_100G: "غ", BASIS_PER_100ML: "مل", BASIS_PER_UNIT: "وحدة"}

_MARGIN = 44.0
_DISH_GAP = 16.0
_ROW_HEIGHT = 20.0
_HEADER_ROW_HEIGHT = 22.0
_TITLE_SIZE = 11
_BODY_SIZE = 9
_META_SIZE = 9
# Column widths as a share of the table — the product name needs the room.
_COLUMN_SHARE = (0.56, 0.22, 0.22)


def _text(painter: QPainter, rect: QRectF, value: str, *, size: int,
          color: str, bold: bool = False,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight) -> float:
    """Draw wrapped text and return the height used — drawText CLIPS."""
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    flags = int(align | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
    metrics = QFontMetricsF(font)
    needed = metrics.boundingRect(
        QRectF(rect.left(), rect.top(), rect.width(), 10000.0), flags, value)
    height = max(rect.height(), needed.height())
    painter.drawText(
        QRectF(rect.left(), rect.top(), rect.width(), height), flags, value)
    return height


def _cell(painter: QPainter, rect: QRectF, value: str, *, bold: bool = False,
          fill: str = "") -> None:
    if fill:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRect(rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.drawRect(rect)
    _text(painter, QRectF(rect.left() + 6, rect.top(), rect.width() - 12,
                          rect.height()),
          value, size=_BODY_SIZE, color=COLOR_TEXT_PRIMARY, bold=bold,
          align=Qt.AlignmentFlag.AlignCenter)


def _dish_block_height(components: Sequence[MealComponent]) -> float:
    """Title row + header row + one row per component + the total row."""
    return (_HEADER_ROW_HEIGHT * 2
            + _ROW_HEIGHT * (len(components) + 1)
            + _DISH_GAP)


def _draw_dish(painter: QPainter, left: float, top: float, width: float,
               dish: str, components: Sequence[MealComponent],
               products: Dict[int, FoodProduct]) -> float:
    """One meal's component table. Returns the height it used."""
    y = top
    _cell(painter, QRectF(left, y, width, _HEADER_ROW_HEIGHT), dish,
          bold=True, fill="#EFF4F0")
    y += _HEADER_ROW_HEIGHT

    widths = [width * share for share in _COLUMN_SHARE]
    # RTL: the first column sits on the RIGHT.
    def column_left(index: int) -> float:
        return left + sum(widths[index + 1:])

    for index, header in enumerate(_HDR):
        _cell(painter, QRectF(column_left(index), y, widths[index],
                              _HEADER_ROW_HEIGHT),
              header, bold=True, fill="#F7F7F4")
    y += _HEADER_ROW_HEIGHT

    for component in components:
        product = products.get(component.product_id)
        name = product.name if product else "—"
        unit = _UNITS.get(product.unit_basis, "") if product else ""
        calories = 0.0
        if product is not None:
            from core.nutrition import component_values
            calories = component_values(product, component.quantity).calories
        values = [name, f"{component.quantity:g} {unit}", f"{calories:,.0f}"]
        for index, value in enumerate(values):
            _cell(painter, QRectF(column_left(index), y, widths[index],
                                  _ROW_HEIGHT), value)
        y += _ROW_HEIGHT

    total = recipe_values(components, products)
    total_text = f"{total.calories:,.0f}" if total else "—"
    _cell(painter, QRectF(column_left(0), y, widths[0], _ROW_HEIGHT),
          _LBL_TOTAL, bold=True, fill="#F7F7F4")
    _cell(painter, QRectF(column_left(1), y, widths[1], _ROW_HEIGHT), "",
          fill="#F7F7F4")
    _cell(painter, QRectF(column_left(2), y, widths[2], _ROW_HEIGHT),
          total_text, bold=True, fill="#F7F7F4")
    y += _ROW_HEIGHT + _DISH_GAP
    return y - top


def write_quantity_breakdown_pdf(
    path: Path,
    settings: SchoolSettings,
    program_name: str,
    recipes: Sequence[Tuple[str, Sequence[MealComponent]]],
    products: Dict[int, FoodProduct],
) -> None:
    """Render every composed meal as its own component table.

    `recipes` carries only the meals that HAVE components — a meal with none
    is left out rather than printed as an empty promise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TITLE)

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        page_w = float(writer.width())
        page_h = float(writer.height())
        content_w = page_w - (_MARGIN * 2)
        # Leave room for the signature strip at the foot of the last page.
        usable_bottom = page_h - _MARGIN - 90.0

        index = 0
        first_page = True
        while index < len(recipes) or first_page:
            if not first_page:
                writer.newPage()

            y = draw_official_pdf_header(
                painter, page_width=page_w, margin=_MARGIN, top=16.0,
                settings=settings, title=_TITLE)
            y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0), _SUBTITLE,
                       size=_META_SIZE, color=COLOR_TEXT_SECONDARY,
                       align=Qt.AlignmentFlag.AlignCenter) + 2.0
            y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0),
                       f"{_LBL_PROGRAM}: {program_name}",
                       size=_META_SIZE, color=COLOR_TEXT_PRIMARY, bold=True,
                       align=Qt.AlignmentFlag.AlignCenter) + 12.0

            drew_any = False
            while index < len(recipes):
                dish, components = recipes[index]
                needed = _dish_block_height(components)
                if drew_any and y + needed > usable_bottom:
                    break
                y += _draw_dish(painter, _MARGIN, y, content_w, dish,
                                components, products)
                index += 1
                drew_any = True

            first_page = False
            if index >= len(recipes):
                break

        # The guide has the committee's programs signed off by the contracted
        # doctors, so the attachment carries their signature line too.
        draw_official_pdf_footer(
            painter, page_width=page_w, margin=_MARGIN,
            top=page_h - _MARGIN - 70.0, settings=settings, roles=_SIGN_ROLES)
    finally:
        painter.end()
