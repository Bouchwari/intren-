"""
src/ui/nutrition_editor.py
The two editing panels behind التحليل الغذائي, kept out of the screen itself
so neither file grows unmanageable.

  ProductLibraryPanel — المواد الغذائية: the raw foodstuffs, entered once with
      their values against a basis (per 100g / per 100ml / per unit).
  RecipeEditorPanel   — مكونات الوجبة: how much of each product goes into a
      menu line. This is also the content of "التوزيع الكمي لمكونات الوجبات
      الغذائية", which the ministry guide (p.5) requires to accompany the
      approved weekly program.

Neither panel invents a value. Both emit `changed` so the screen re-analyses.
"""
import logging
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.models import FoodProduct, MealComponent
from core.nutrition import (
    BASIS_PER_100G, BASIS_PER_100ML, BASIS_PER_UNIT, component_values,
    normalize_dish, recipe_values,
)
from data.database import (
    delete_food_product, delete_meal_component, get_all_food_products,
    get_meal_components, save_food_product, save_meal_component,
)
from ui.widgets.icon_button import IconButton

# ── Arabic strings ──────────────────────────────────────────────────────────
_PRODUCTS_TITLE = "المواد الغذائية"
_PRODUCTS_HINT = ("المواد الخام التي تتكون منها الوجبات. تُدخل مرة واحدة "
                  "وتُستعمل في كل الوجبات — القيم من إدخالك أنت")
_RECIPE_TITLE = "مكونات الوجبة والتوزيع الكمي"
_RECIPE_HINT = ("حدد كمية كل مادة في الوجبة. هذا هو «التوزيع الكمي لمكونات "
                "الوجبات الغذائية» الذي يرفق بالبرنامج الغذائي المعتمد")

_LBL_PRODUCT = "المادة"
_LBL_BASIS = "الوحدة"
_LBL_CALORIES = "السعرات"
_LBL_PROTEIN = "بروتين (غ)"
_LBL_CARBS = "سكريات (غ)"
_LBL_FATS = "دهون (غ)"
_LBL_QUANTITY = "الكمية"
_LBL_DISH = "الوجبة"
_LBL_SHARE = "مساهمتها"

_BASIS_LABELS = {
    BASIS_PER_100G: "لكل 100 غ",
    BASIS_PER_100ML: "لكل 100 مل",
    BASIS_PER_UNIT: "للوحدة",
}
_BASIS_UNITS = {
    BASIS_PER_100G: "غ",
    BASIS_PER_100ML: "مل",
    BASIS_PER_UNIT: "وحدة",
}

_BTN_SAVE_PRODUCT = "حفظ المادة"
_BTN_SAVE_PRODUCT_ICON = "💾"
_BTN_ADD_COMPONENT = "إضافة إلى الوجبة"
_BTN_ADD_COMPONENT_ICON = "➕"
_BTN_DELETE = "حذف"

_MSG_PRODUCT_NAME = "اكتب اسم المادة أولاً."
_MSG_PRODUCT_SAVED = "تم حفظ المادة الغذائية."
_MSG_PRODUCT_DELETED = "تم حذف المادة، وأُزيلت من كل الوجبات التي كانت فيها."
_MSG_NO_PRODUCTS = "أضف مادة غذائية واحدة على الأقل قبل تكوين الوجبات."
_MSG_NO_DISH = "اختر الوجبة التي تريد تكوينها."
_MSG_QUANTITY = "حدد كمية أكبر من صفر."
_MSG_COMPONENT_SAVED = "تمت إضافة المادة إلى الوجبة."
_MSG_COMPONENT_DELETED = "تم حذف المادة من الوجبة."

_EMPTY_PRODUCTS = "لا توجد مواد غذائية بعد"
_EMPTY_RECIPE = "لم تُحدد مكونات هذه الوجبة بعد"
_TOTAL_PREFIX = "مجموع الوجبة"
_NO_DISHES = "لا توجد وجبات في البرنامج"

_PRODUCT_HDR = [_LBL_PRODUCT, _LBL_BASIS, _LBL_CALORIES, _LBL_PROTEIN,
                _LBL_CARBS, _LBL_FATS, ""]
_RECIPE_HDR = [_LBL_PRODUCT, _LBL_QUANTITY, _LBL_SHARE, ""]

_PANEL_BG = "#ffffff"
_MAX_QUANTITY = 5000.0

_LOGGER = logging.getLogger(__name__)


def _panel() -> QFrame:
    frame = QFrame()
    frame.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    frame.setStyleSheet(
        f"QFrame {{ background:{_PANEL_BG}; border:1px solid {COLOR_BORDER};"
        f"border-radius:14px; }}")
    return frame


def _field_style() -> str:
    return (
        f"background:white; color:{COLOR_TEXT_PRIMARY};"
        f"border:1px solid {COLOR_BORDER}; border-radius:8px;"
        f"padding:6px 10px; font-size:{FONT_BODY}px;"
    )


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
        f"font-size:{FONT_CAPTION}px; font-weight:bold;")
    return label


def _heading(text: str, hint: str) -> QVBoxLayout:
    column = QVBoxLayout()
    column.setSpacing(2)
    title = QLabel(text)
    font = QFont()
    font.setPointSize(FONT_SECTION)
    font.setBold(True)
    title.setFont(font)
    title.setStyleSheet(
        f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;")
    note = QLabel(hint)
    note.setWordWrap(True)
    note.setStyleSheet(
        f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
        f"font-size:{FONT_CAPTION}px;")
    column.addWidget(title)
    column.addWidget(note)
    return column


def _table(headers: Sequence[str], stretch_column: int) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.horizontalHeader().setSectionResizeMode(
        stretch_column, QHeaderView.ResizeMode.Stretch)
    table.setStyleSheet(f"""
        QTableWidget {{
            border:1px solid {COLOR_BORDER}; border-radius:10px;
            background:white; alternate-background-color:#FAFAF7;
            font-size:{FONT_LABEL}px; color:{COLOR_TEXT_PRIMARY};
        }}
        QHeaderView::section {{
            background:#F1F5F2; color:{COLOR_TEXT_PRIMARY};
            padding:7px 10px; border:none;
            border-bottom:1px solid {COLOR_BORDER};
            font-weight:bold; font-size:{FONT_CAPTION}px;
        }}
        QTableWidget::item {{ padding:5px 10px; }}
    """)
    return table


def _cell(text: str, *, bold: bool = False,
          color: str = COLOR_TEXT_PRIMARY) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(
        int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter))
    if bold:
        font = QFont()
        font.setBold(True)
        item.setFont(font)
    if color != COLOR_TEXT_PRIMARY:
        from PySide6.QtGui import QColor
        item.setForeground(QColor(color))
    return item


def _delete_button(on_click) -> QPushButton:
    button = QPushButton(_BTN_DELETE)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setStyleSheet(
        f"QPushButton {{ background:transparent; color:{COLOR_DANGER};"
        f"border:1px solid {COLOR_DANGER}; border-radius:6px;"
        f"padding:2px 10px; font-size:{FONT_CAPTION}px; }}"
        f"QPushButton:hover {{ background:{COLOR_DANGER}; color:white; }}")
    button.clicked.connect(on_click)
    return button


class ProductLibraryPanel(QWidget):
    """المواد الغذائية — the raw foodstuffs and their recorded values."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("background:transparent;")
        self._products: List[FoodProduct] = []
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        panel = _panel()
        root.addWidget(panel)

        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(10)
        box.addLayout(_heading(_PRODUCTS_TITLE, _PRODUCTS_HINT))

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setMinimumHeight(34)
        self._name_edit.setStyleSheet(_field_style())

        self._basis_combo = QComboBox()
        for key, label in _BASIS_LABELS.items():
            self._basis_combo.addItem(label, key)
        self._basis_combo.setMinimumHeight(34)
        self._basis_combo.setStyleSheet(_field_style())

        self._spins: Dict[str, QSpinBox] = {}
        widgets = [(_LBL_PRODUCT, self._name_edit, None),
                   (_LBL_BASIS, self._basis_combo, None),
                   (_LBL_CALORIES, None, "calories"),
                   (_LBL_PROTEIN, None, "protein"),
                   (_LBL_CARBS, None, "carbs"),
                   (_LBL_FATS, None, "fats")]
        for column, (label, widget, key) in enumerate(widgets):
            form.addWidget(_caption(label), 0, column)
            if widget is None:
                spin = QSpinBox()
                spin.setRange(0, 9999)
                spin.setMinimumHeight(34)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setStyleSheet(_field_style())
                self._spins[key] = spin
                widget = spin
            form.addWidget(widget, 1, column)
        form.setColumnStretch(0, 3)
        box.addLayout(form)

        buttons = QHBoxLayout()
        save = IconButton(_BTN_SAVE_PRODUCT, icon=_BTN_SAVE_PRODUCT_ICON,
                          bg=COLOR_ACCENT, min_height=36)
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        buttons.addStretch()
        box.addLayout(buttons)

        self._table = _table(_PRODUCT_HDR, 0)
        self._table.setMinimumHeight(190)
        box.addWidget(self._table)

    # ── Data ────────────────────────────────────────────────────────────────

    def reload(self) -> None:
        self._products = get_all_food_products()
        self._render()

    def products(self) -> List[FoodProduct]:
        return list(self._products)

    def _render(self) -> None:
        self._table.setRowCount(len(self._products))
        for row, product in enumerate(self._products):
            self._table.setItem(row, 0, _cell(product.name, bold=True))
            self._table.setItem(
                row, 1, _cell(_BASIS_LABELS.get(product.unit_basis, product.unit_basis)))
            for column, value in enumerate(
                (product.calories, product.protein, product.carbs, product.fats),
                start=2,
            ):
                self._table.setItem(row, column, _cell(f"{value:,}"))
            self._table.setCellWidget(
                row, 6, _delete_button(lambda _c=False, p=product: self._on_delete(p)))
        if not self._products:
            self._table.setRowCount(1)
            self._table.setItem(0, 0, _cell(_EMPTY_PRODUCTS,
                                            color=COLOR_TEXT_SECONDARY))

    # ── Actions ─────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        name = normalize_dish(self._name_edit.text())
        if not name:
            QMessageBox.information(self, _PRODUCTS_TITLE, _MSG_PRODUCT_NAME)
            return
        try:
            save_food_product(FoodProduct(
                name=name,
                unit_basis=self._basis_combo.currentData(),
                calories=self._spins["calories"].value(),
                protein=self._spins["protein"].value(),
                carbs=self._spins["carbs"].value(),
                fats=self._spins["fats"].value(),
            ))
        except Exception:
            _LOGGER.exception("saving a food product failed")
            QMessageBox.critical(self, _PRODUCTS_TITLE, _MSG_PRODUCT_NAME)
            return
        self._name_edit.clear()
        for spin in self._spins.values():
            spin.setValue(0)
        self.reload()
        self.changed.emit()
        QMessageBox.information(self, _PRODUCTS_TITLE, _MSG_PRODUCT_SAVED)

    def _on_delete(self, product: FoodProduct) -> None:
        if product.id is not None:
            delete_food_product(product.id)
        self.reload()
        self.changed.emit()
        QMessageBox.information(self, _PRODUCTS_TITLE, _MSG_PRODUCT_DELETED)


class RecipeEditorPanel(QWidget):
    """مكونات الوجبة — how much of each product goes into one menu line."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("background:transparent;")
        self._products: List[FoodProduct] = []
        self._components: List[MealComponent] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        panel = _panel()
        root.addWidget(panel)

        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(10)
        box.addLayout(_heading(_RECIPE_TITLE, _RECIPE_HINT))

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self._dish_combo = QComboBox()
        self._dish_combo.setMinimumHeight(34)
        self._dish_combo.setStyleSheet(_field_style())
        self._dish_combo.currentIndexChanged.connect(lambda _i: self._render())

        self._product_combo = QComboBox()
        self._product_combo.setMinimumHeight(34)
        self._product_combo.setStyleSheet(_field_style())
        self._product_combo.currentIndexChanged.connect(self._sync_unit)

        self._quantity_spin = QDoubleSpinBox()
        self._quantity_spin.setRange(0.0, _MAX_QUANTITY)
        self._quantity_spin.setDecimals(1)
        self._quantity_spin.setSingleStep(10.0)
        self._quantity_spin.setMinimumHeight(34)
        self._quantity_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._quantity_spin.setStyleSheet(_field_style())

        for column, (label, widget) in enumerate((
            (_LBL_DISH, self._dish_combo),
            (_LBL_PRODUCT, self._product_combo),
            (_LBL_QUANTITY, self._quantity_spin),
        )):
            form.addWidget(_caption(label), 0, column)
            form.addWidget(widget, 1, column)
        form.setColumnStretch(0, 3)
        form.setColumnStretch(1, 2)
        box.addLayout(form)

        buttons = QHBoxLayout()
        add = IconButton(_BTN_ADD_COMPONENT, icon=_BTN_ADD_COMPONENT_ICON,
                         bg=COLOR_ACCENT, min_height=36)
        add.clicked.connect(self._on_add)
        buttons.addWidget(add)
        buttons.addStretch()
        self._total_label = QLabel("")
        self._total_label.setStyleSheet(
            f"color:{COLOR_SUCCESS}; background:transparent; border:none;"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        buttons.addWidget(self._total_label)
        box.addLayout(buttons)

        self._table = _table(_RECIPE_HDR, 0)
        self._table.setMinimumHeight(170)
        box.addWidget(self._table)

    # ── Data ────────────────────────────────────────────────────────────────

    def set_context(self, dishes: Sequence[str],
                    products: Sequence[FoodProduct]) -> None:
        """The menu lines that can be composed, and the available products."""
        self._products = list(products)
        previous = self._dish_combo.currentData()

        self._dish_combo.blockSignals(True)
        self._dish_combo.clear()
        for dish in dishes:
            self._dish_combo.addItem(dish, dish)
        if previous in dishes:
            self._dish_combo.setCurrentIndex(list(dishes).index(previous))
        self._dish_combo.blockSignals(False)

        self._product_combo.blockSignals(True)
        self._product_combo.clear()
        for product in self._products:
            self._product_combo.addItem(
                f"{product.name}  ({_BASIS_LABELS.get(product.unit_basis, '')})",
                product.id)
        self._product_combo.blockSignals(False)
        self._sync_unit()
        self._render()

    def current_dish(self) -> str:
        return self._dish_combo.currentData() or ""

    def _sync_unit(self) -> None:
        """The quantity is entered in the product's OWN unit, so the suffix
        has to follow the selected product rather than being fixed."""
        product = self._selected_product()
        basis = product.unit_basis if product else BASIS_PER_100G
        self._quantity_spin.setSuffix(f" {_BASIS_UNITS.get(basis, '')}")

    def _selected_product(self) -> Optional[FoodProduct]:
        product_id = self._product_combo.currentData()
        return next((p for p in self._products if p.id == product_id), None)

    def _render(self) -> None:
        dish = self.current_dish()
        self._components = get_meal_components(dish) if dish else []
        by_id = {p.id: p for p in self._products}

        self._table.setRowCount(len(self._components))
        for row, component in enumerate(self._components):
            product = by_id.get(component.product_id)
            name = product.name if product else "—"
            unit = _BASIS_UNITS.get(product.unit_basis, "") if product else ""
            self._table.setItem(row, 0, _cell(name, bold=True))
            self._table.setItem(row, 1, _cell(f"{component.quantity:g} {unit}"))
            share = (component_values(product, component.quantity).calories
                     if product else 0)
            self._table.setItem(row, 2, _cell(f"{share:,.0f} ك.ح"))
            self._table.setCellWidget(
                row, 3,
                _delete_button(lambda _c=False, c=component: self._on_delete(c)))

        if not self._components:
            self._table.setRowCount(1)
            message = _EMPTY_RECIPE if dish else _NO_DISHES
            self._table.setItem(0, 0, _cell(message, color=COLOR_TEXT_SECONDARY))
            self._total_label.setText("")
            return

        total = recipe_values(self._components, by_id)
        if total is None:
            self._total_label.setText("")
            return
        self._total_label.setText(
            f"{_TOTAL_PREFIX}: {total.calories:,.0f} ك.ح  ·  "
            f"بروتين {total.protein:,.0f} غ  ·  "
            f"سكريات {total.carbs:,.0f} غ  ·  دهون {total.fats:,.0f} غ")

    # ── Actions ─────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        dish = self.current_dish()
        if not dish:
            QMessageBox.information(self, _RECIPE_TITLE, _MSG_NO_DISH)
            return
        product = self._selected_product()
        if product is None or product.id is None:
            QMessageBox.information(self, _RECIPE_TITLE, _MSG_NO_PRODUCTS)
            return
        if self._quantity_spin.value() <= 0:
            QMessageBox.information(self, _RECIPE_TITLE, _MSG_QUANTITY)
            return
        save_meal_component(MealComponent(
            dish_name=dish, product_id=product.id,
            quantity=self._quantity_spin.value()))
        self._render()
        self.changed.emit()
        QMessageBox.information(self, _RECIPE_TITLE, _MSG_COMPONENT_SAVED)

    def _on_delete(self, component: MealComponent) -> None:
        if component.id is not None:
            delete_meal_component(component.id)
        self._render()
        self.changed.emit()
        QMessageBox.information(self, _RECIPE_TITLE, _MSG_COMPONENT_DELETED)
