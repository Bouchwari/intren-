"""
src/ui/nutrition_screen.py
التحليل الغذائي — the calorie and nutrient value of the weekly meal program.

Every number shown here comes from values the USER recorded for a menu line.
A line with no recorded values is reported as "غير محدد" and left out of the
totals; the screen says how much of the week is actually covered rather than
quietly presenting a partial total as a whole one.

Nothing is derived from a dish's NAME. The prototype this screen came from
computed `calories = 300 + len(name) * 10`, so "طاجين لحم بالخضر" scored more
than "كسكس" purely for being longer — the same fabricated-number problem the
project already refused for بيانات المصاريف's per-student cells.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_PAPER, COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_WARNING,
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA, MEAL_IFTAR, MEAL_LABELS, MEAL_SHOUR,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.models import DishNutrition, MealProgram
from core.nutrition import (
    SOURCE_DIRECT, SOURCE_RECIPE, DayAnalysis, WeekAnalysis, analyse_week,
    normalize_dish, unknown_dishes,
)
from data.database import (
    delete_dish_nutrition, get_all_dish_nutrition, get_all_food_products,
    get_all_meal_components, get_all_programs,
    get_nutrition_reference_calories, get_program_entries,
    get_school_settings,
    save_dish_nutrition, save_nutrition_reference_calories,
)
from ui.nutrition_editor import ProductLibraryPanel, RecipeEditorPanel
from ui.nutrition_export import write_quantity_breakdown_pdf
from ui.widgets.icon_button import IconButton

# ── Arabic strings ──────────────────────────────────────────────────────────
_TITLE = "التحليل الغذائي"
_SUBTITLE = ("السعرات والقيم الغذائية للبرنامج الأسبوعي — محسوبة من القيم التي "
             "تُدخلها بنفسك لكل وجبة، ولا تُقدَّر أبداً")

_LBL_PROGRAM = "البرنامج"
_LBL_COVERAGE = "تغطية البيانات"
_LBL_AVG_CALORIES = "متوسط السعرات في اليوم"
_LBL_REFERENCE = "القيمة المرجعية اليومية"
_LBL_UNKNOWN = "وجبات بدون قيم غذائية"

_COVERAGE_FULL = "كل وجبات البرنامج لها قيم غذائية"
_COVERAGE_PARTIAL = "{known} من {planned} وجبة لها قيم غذائية"
_COVERAGE_NONE = "لم تُدخل أي قيم غذائية بعد"
_AVG_UNAVAILABLE = "—"
_AVG_HINT = "يُحتسب المتوسط من الأيام المكتملة وحدها"

_UNKNOWN_HINT = ("الوجبات التالية مذكورة في البرنامج لكن لا تتوفر لها قيم غذائية، "
                 "لذلك هي غير محتسبة في المجاميع. أدخل قيمها لتُحتسب:")

_HDR_DAY = "اليوم"
_HDR_TOTAL = "مجموع اليوم"
_UNSET = "غير محدد"
_NO_MENU = "—"

_TBL_DISH = "الوجبة"
_TBL_CALORIES = "السعرات (ك.ح)"
_TBL_PROTEIN = "بروتين (غ)"
_TBL_CARBS = "سكريات (غ)"
_TBL_FATS = "دهون (غ)"
_TBL_ACTION = ""

_LBL_DISHES_TITLE = "جدول القيم الغذائية"
_LBL_DISHES_HINT = ("قيمة كل وجبة لحصة واحدة. هذه القيم من إدخالك أنت — "
                    "التطبيق لا يخمّنها من اسم الوجبة")

_BTN_SAVE_DISH = "حفظ الوجبة"
_BTN_SAVE_DISH_ICON = "💾"
_BTN_DELETE = "حذف"
_BTN_FILL = "إدخال القيم"

_MSG_DISH_REQUIRED = "اكتب اسم الوجبة أولاً."
_MSG_DISH_SAVED = "تم حفظ القيم الغذائية للوجبة."
_MSG_DISH_DELETED = "تم حذف الوجبة من جدول القيم."
_MSG_NO_PROGRAM = "لا يوجد أي برنامج أسبوعي بعد — أنشئ واحداً من «البرنامج الغذائي»."
_SOURCE_RECIPE = "من المكونات"
_SOURCE_DIRECT = "قيمة مباشرة"
_BTN_EXPORT = "تصدير التوزيع الكمي"
_BTN_EXPORT_ICON = "📄"
_PDF_DIALOG_TITLE = "تصدير التوزيع الكمي لمكونات الوجبات"
_PDF_DEFAULT_NAME = "التوزيع_الكمي_لمكونات_الوجبات"
_PDF_FILTER = "PDF (*.pdf)"
_MSG_EXPORT_SAVED = "تم تصدير التوزيع الكمي إلى:\n"
_MSG_EXPORT_FAILED = "تعذر تصدير الملف. تحقق من المكان المختار ثم أعد المحاولة."
_MSG_EXPORT_EMPTY = "لم تُحدد مكونات أي وجبة بعد — كوّن وجبة واحدة على الأقل."

_DAYS: List[str] = [
    "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد",
]
# The meal-program grid stores الإثنين as day_of_week 2 (see
# meal_program_screen._DAYS); this is the same mapping, display order first.
_DAY_CODES: List[int] = [2, 3, 4, 5, 6, 0, 1]

_REGULAR_MEALS = [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA]
_RAMADAN_MEALS = [MEAL_IFTAR, MEAL_SHOUR]

# A general reference figure for a school-age boarder's daily intake, shown
# only as a comparison and editable by the user — it is NOT dietary advice and
# not derived from anything the app knows.
_DEFAULT_REFERENCE_CALORIES = 2200
_REFERENCE_MIN = 800
_REFERENCE_MAX = 5000

_PAGE_BG = COLOR_PAPER
_PANEL_BG = "#ffffff"

_LOGGER = logging.getLogger(__name__)


def _tint(hex_color: str, alpha: float = 0.13) -> str:
    """Translucent palette colour as Qt-stylesheet rgba().

    Not `f"{color}22"` — Qt reads 8-digit hex as #AARRGGBB, which produces a
    dark opaque colour instead of a light tint.
    """
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"


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


class NutritionScreen(QWidget):
    """التحليل الغذائي — the week's values, and the table they come from."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._programs: List[MealProgram] = []
        self._nutrition: List[DishNutrition] = []
        self._analysis: Optional[WeekAnalysis] = None
        self._unknown: List[str] = []
        self._recipes: Dict[str, list] = {}
        self._products: Dict[int, object] = {}
        self._build_ui()
        self._reload()

    # ── Build ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        inner = QVBoxLayout(content)
        inner.setContentsMargins(28, 22, 28, 28)
        inner.setSpacing(16)

        inner.addLayout(self._build_header())
        inner.addWidget(self._build_summary())
        inner.addWidget(self._build_unknown_panel())
        inner.addWidget(self._build_week_table())

        self._product_panel = ProductLibraryPanel()
        self._product_panel.changed.connect(self._on_editor_changed)
        inner.addWidget(self._product_panel)

        self._recipe_panel = RecipeEditorPanel()
        self._recipe_panel.changed.connect(self._on_editor_changed)
        inner.addWidget(self._recipe_panel)

        inner.addWidget(self._build_dish_editor())
        inner.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        column = QVBoxLayout()
        column.setSpacing(4)
        title = QLabel(_TITLE)
        font = QFont()
        font.setPointSize(FONT_SECTION + 3)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        subtitle = QLabel(_SUBTITLE)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        column.addWidget(title)
        column.addWidget(subtitle)
        row.addLayout(column, 1)

        picker = QVBoxLayout()
        picker.setSpacing(4)
        picker.addWidget(self._caption(_LBL_PROGRAM))
        self._program_combo = QComboBox()
        self._program_combo.setMinimumWidth(240)
        self._program_combo.setMinimumHeight(34)
        self._program_combo.setStyleSheet(_field_style())
        self._program_combo.currentIndexChanged.connect(self._on_program_changed)
        picker.addWidget(self._program_combo)
        row.addLayout(picker)

        self._export_btn = IconButton(
            _BTN_EXPORT, icon=_BTN_EXPORT_ICON, bg=COLOR_ACCENT, min_height=34)
        self._export_btn.clicked.connect(self._on_export)
        row.addWidget(self._export_btn)
        return row

    def _caption(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px; font-weight:bold;")
        return label

    def _build_summary(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:transparent;")
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self._coverage_card, self._coverage_value, self._coverage_caption = \
            self._stat_card(_LBL_COVERAGE, COLOR_ACCENT)
        self._avg_card, self._avg_value, self._avg_caption = \
            self._stat_card(_LBL_AVG_CALORIES, COLOR_SUCCESS)
        row.addWidget(self._coverage_card, 1)
        row.addWidget(self._avg_card, 1)

        reference = _panel()
        ref_box = QVBoxLayout(reference)
        ref_box.setContentsMargins(14, 10, 14, 10)
        ref_box.setSpacing(4)
        ref_box.addWidget(self._caption(_LBL_REFERENCE))
        self._reference_spin = QSpinBox()
        self._reference_spin.setRange(_REFERENCE_MIN, _REFERENCE_MAX)
        self._reference_spin.setValue(
            get_nutrition_reference_calories(_DEFAULT_REFERENCE_CALORIES))
        self._reference_spin.setSingleStep(50)
        self._reference_spin.setMinimumHeight(32)
        self._reference_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reference_spin.setStyleSheet(_field_style())
        self._reference_spin.valueChanged.connect(self._on_reference_changed)
        ref_box.addWidget(self._reference_spin)
        row.addWidget(reference, 1)
        return panel

    def _stat_card(self, caption: str, color: str):
        card = _panel()
        card.setStyleSheet(
            f"QFrame {{ background:{_PANEL_BG}; border:1px solid {COLOR_BORDER};"
            f"border-right:4px solid {color}; border-radius:14px; }}")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(2)
        value = QLabel("—")
        value_font = QFont()
        value_font.setPointSize(FONT_SECTION + 4)
        value_font.setBold(True)
        value.setFont(value_font)
        value.setStyleSheet(f"color:{color}; background:transparent; border:none;")
        note = QLabel(caption)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        box.addWidget(value)
        box.addWidget(note)
        return card, value, note

    def _build_unknown_panel(self) -> QWidget:
        """The to-do list: menu lines with no values, and a button per line to
        fill them in. Visible only when there is something missing."""
        self._unknown_panel = _panel()
        self._unknown_panel.setStyleSheet(
            f"QFrame {{ background:{_tint(COLOR_WARNING, 0.10)};"
            f"border:1px solid {COLOR_WARNING}; border-radius:14px; }}")
        box = QVBoxLayout(self._unknown_panel)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(8)

        heading = QLabel(_LBL_UNKNOWN)
        heading_font = QFont()
        heading_font.setPointSize(FONT_LABEL)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color:{COLOR_WARNING}; background:transparent; border:none;")
        box.addWidget(heading)

        hint = QLabel(_UNKNOWN_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        box.addWidget(hint)

        self._unknown_list = QVBoxLayout()
        self._unknown_list.setSpacing(6)
        box.addLayout(self._unknown_list)
        return self._unknown_panel

    def _build_week_table(self) -> QWidget:
        panel = _panel()
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(10)

        self._week_table = QTableWidget(0, 0)
        self._week_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._week_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._week_table.verticalHeader().setVisible(False)
        self._week_table.setAlternatingRowColors(True)
        self._week_table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {COLOR_BORDER}; border-radius:10px;
                background:white; alternate-background-color:#FAFAF7;
                font-size:{FONT_LABEL}px; color:{COLOR_TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background:{_tint(COLOR_ACCENT, 0.10)}; color:{COLOR_TEXT_PRIMARY};
                padding:8px 10px; border:none;
                border-bottom:1px solid {COLOR_BORDER};
                font-weight:bold; font-size:{FONT_CAPTION}px;
            }}
            QTableWidget::item {{ padding:6px 10px; }}
        """)
        box.addWidget(self._week_table)
        return panel

    def _build_dish_editor(self) -> QWidget:
        panel = _panel()
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(10)

        heading = QLabel(_LBL_DISHES_TITLE)
        heading_font = QFont()
        heading_font.setPointSize(FONT_SECTION)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;")
        box.addWidget(heading)

        hint = QLabel(_LBL_DISHES_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        box.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        self._dish_edit = QLineEdit()
        self._dish_edit.setMinimumHeight(34)
        self._dish_edit.setStyleSheet(_field_style())
        self._value_spins: Dict[str, QSpinBox] = {}
        fields = [
            (_TBL_DISH, self._dish_edit, None),
            (_TBL_CALORIES, None, "calories"),
            (_TBL_PROTEIN, None, "protein"),
            (_TBL_CARBS, None, "carbs"),
            (_TBL_FATS, None, "fats"),
        ]
        for column, (label, widget, key) in enumerate(fields):
            form.addWidget(self._caption(label), 0, column)
            if widget is None:
                spin = QSpinBox()
                spin.setRange(0, 9999)
                spin.setMinimumHeight(34)
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setStyleSheet(_field_style())
                self._value_spins[key] = spin
                widget = spin
            form.addWidget(widget, 1, column)
        form.setColumnStretch(0, 3)
        box.addLayout(form)

        save_row = QHBoxLayout()
        save_btn = IconButton(
            _BTN_SAVE_DISH, icon=_BTN_SAVE_DISH_ICON, bg=COLOR_ACCENT,
            min_height=36)
        save_btn.clicked.connect(self._on_save_dish)
        save_row.addWidget(save_btn)
        save_row.addStretch()
        box.addLayout(save_row)

        self._dish_table = QTableWidget(0, 6)
        self._dish_table.setHorizontalHeaderLabels([
            _TBL_DISH, _TBL_CALORIES, _TBL_PROTEIN, _TBL_CARBS, _TBL_FATS,
            _TBL_ACTION,
        ])
        self._dish_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._dish_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dish_table.verticalHeader().setVisible(False)
        self._dish_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._dish_table.setStyleSheet(self._week_table.styleSheet())
        self._dish_table.setMinimumHeight(180)
        box.addWidget(self._dish_table)
        return panel

    # ── Data ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Menus are edited on another screen, so re-read on every visit."""
        self._reload()

    def _on_editor_changed(self) -> None:
        """A product or a recipe changed — the week's numbers follow from
        them, so re-read and re-analyse rather than leave a stale total."""
        self._reload()

    def _reload(self) -> None:
        self._programs = get_all_programs()
        self._nutrition = get_all_dish_nutrition()
        self._recipes = get_all_meal_components()
        self._products = {p.id: p for p in get_all_food_products()}

        self._program_combo.blockSignals(True)
        self._program_combo.clear()
        for program in self._programs:
            prefix = "☾ " if program.is_ramadan else ""
            self._program_combo.addItem(f"{prefix}{program.name}", program)
        self._program_combo.blockSignals(False)

        self._render_dish_table()
        self._analyse()
        self._product_panel.reload()
        self._recipe_panel.set_context(
            self._program_dishes(), self._product_panel.products())

    def _current_program(self) -> Optional[MealProgram]:
        index = self._program_combo.currentIndex()
        if index < 0:
            return None
        return self._program_combo.itemData(index)

    def _meal_types(self, program: MealProgram) -> List[str]:
        return _RAMADAN_MEALS if program.is_ramadan else _REGULAR_MEALS

    def _analyse(self) -> None:
        program = self._current_program()
        if program is None or program.id is None:
            self._analysis = None
            self._unknown = []
            self._render_week()
            self._render_summary()
            self._render_unknown()
            return
        entries = get_program_entries(program.id)
        meals = self._meal_types(program)
        # Only the meals this program actually serves count towards coverage —
        # a normal program has no سحور line missing, it simply has no سحور.
        relevant = [entry for entry in entries if entry.meal_type in meals]
        self._analysis = analyse_week(
            relevant, self._nutrition, meals,
            recipes=self._recipes, products=self._products)
        self._unknown = unknown_dishes(
            relevant, self._nutrition,
            recipes=self._recipes, products=self._products)
        self._render_week()
        self._render_summary()
        self._render_unknown()

    def _on_reference_changed(self, value: int) -> None:
        save_nutrition_reference_calories(value)
        self._render_summary()

    def _program_dishes(self) -> List[str]:
        """Distinct menu lines in the selected program — what can be composed."""
        program = self._current_program()
        if program is None or program.id is None:
            return []
        meals = self._meal_types(program)
        seen: List[str] = []
        for entry in get_program_entries(program.id):
            if entry.meal_type not in meals:
                continue
            name = normalize_dish(entry.menu_text)
            if name and name not in seen:
                seen.append(name)
        return seen

    def _on_program_changed(self, _index: int) -> None:
        self._analyse()
        self._recipe_panel.set_context(
            self._program_dishes(), self._product_panel.products())

    # ── Render ──────────────────────────────────────────────────────────────

    def _render_summary(self) -> None:
        analysis = self._analysis
        if analysis is None or analysis.planned_count == 0:
            self._coverage_value.setText("—")
            self._coverage_caption.setText(_COVERAGE_NONE if analysis else _LBL_COVERAGE)
            self._avg_value.setText(_AVG_UNAVAILABLE)
            self._avg_caption.setText(_LBL_AVG_CALORIES)
            return

        self._coverage_value.setText(
            f"{analysis.known_count}/{analysis.planned_count}")
        self._coverage_caption.setText(
            _COVERAGE_FULL if analysis.is_complete
            else _COVERAGE_PARTIAL.format(known=analysis.known_count,
                                          planned=analysis.planned_count))

        average = analysis.average_calories
        if average is None:
            self._avg_value.setText(_AVG_UNAVAILABLE)
            self._avg_caption.setText(_AVG_HINT)
            return
        reference = self._reference_spin.value()
        percent = round(average / reference * 100) if reference else 0
        self._avg_value.setText(f"{average:,.0f}")
        self._avg_caption.setText(
            f"{_AVG_HINT}  ·  {percent}% من {reference:,} ك.ح")

    def _render_week(self) -> None:
        table = self._week_table
        table.clear()
        program = self._current_program()
        if self._analysis is None or program is None:
            table.setRowCount(0)
            table.setColumnCount(1)
            table.setHorizontalHeaderLabels([_MSG_NO_PROGRAM])
            return

        meals = self._meal_types(program)
        headers = [_HDR_DAY] + [MEAL_LABELS.get(m, m) for m in meals] + [_HDR_TOTAL]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(_DAY_CODES))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)

        by_code = {day.day_of_week: day for day in self._analysis.days}
        for row, code in enumerate(_DAY_CODES):
            table.setItem(row, 0, self._cell(_DAYS[row], bold=True))
            day = by_code.get(code, DayAnalysis(day_of_week=code))
            for column, meal_type in enumerate(meals, start=1):
                meal = next((m for m in day.meals if m.meal_type == meal_type), None)
                table.setItem(row, column, self._meal_cell(meal))
            table.setItem(row, len(headers) - 1, self._total_cell(day))
        table.resizeRowsToContents()
        # Both minimum and maximum: a maximum alone lets the surrounding layout
        # decline to grant the height, and the table keeps its own scrollbar.
        height = table.horizontalHeader().height() + table.verticalHeader().length() + 4
        table.setMinimumHeight(height)
        table.setMaximumHeight(height)

    def _cell(self, text: str, *, bold: bool = False,
              color: str = COLOR_TEXT_PRIMARY) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        if bold:
            font = QFont()
            font.setBold(True)
            item.setFont(font)
        if color != COLOR_TEXT_PRIMARY:
            from PySide6.QtGui import QColor
            item.setForeground(QColor(color))
        return item

    def _meal_cell(self, meal) -> QTableWidgetItem:
        if meal is None or meal.is_empty:
            return self._cell(_NO_MENU, color=COLOR_TEXT_SECONDARY)
        if not meal.is_known:
            # Named, but no recorded values — say so instead of showing a zero
            # that would read as "this meal has no calories".
            return self._cell(f"{meal.dish_name}\n{_UNSET}", color=COLOR_WARNING)
        # Say where the number came from: a meal summed from its components is
        # a stronger record than one typed in wholesale.
        origin = (_SOURCE_RECIPE if meal.nutrition.source == SOURCE_RECIPE
                  else _SOURCE_DIRECT)
        return self._cell(
            f"{meal.dish_name}\n{meal.nutrition.calories:,.0f} ك.ح  ·  {origin}")

    def _total_cell(self, day: DayAnalysis) -> QTableWidgetItem:
        if not day.planned_meals:
            return self._cell(_NO_MENU, color=COLOR_TEXT_SECONDARY)
        text = f"{day.calories:,.0f} ك.ح"
        if not day.is_complete:
            text = f"{text}\n({len(day.known_meals)}/{len(day.planned_meals)})"
            return self._cell(text, bold=True, color=COLOR_WARNING)
        return self._cell(text, bold=True, color=COLOR_SUCCESS)

    def _render_unknown(self) -> None:
        while self._unknown_list.count():
            item = self._unknown_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        self._unknown_panel.setVisible(bool(self._unknown))
        for dish in self._unknown:
            row = QWidget()
            row.setStyleSheet("background:transparent; border:none;")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            label = QLabel(dish)
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;"
                f"font-size:{FONT_LABEL}px; font-weight:bold;")
            button = QPushButton(_BTN_FILL)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{COLOR_ACCENT};"
                f"border:1px solid {COLOR_ACCENT}; border-radius:8px;"
                f"padding:3px 12px; font-size:{FONT_CAPTION}px; font-weight:bold; }}"
                f"QPushButton:hover {{ background:{COLOR_ACCENT}; color:white; }}")
            button.clicked.connect(lambda _c, name=dish: self._start_filling(name))
            layout.addWidget(label, 1)
            layout.addWidget(button)
            self._unknown_list.addWidget(row)

    def _render_dish_table(self) -> None:
        table = self._dish_table
        table.setRowCount(len(self._nutrition))
        for row, dish in enumerate(self._nutrition):
            table.setItem(row, 0, self._cell(dish.dish_name))
            for column, value in enumerate(
                (dish.calories, dish.protein, dish.carbs, dish.fats), start=1
            ):
                table.setItem(row, column, self._cell(f"{value:,}"))
            button = QPushButton(_BTN_DELETE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{COLOR_DANGER};"
                f"border:1px solid {COLOR_DANGER}; border-radius:6px;"
                f"padding:2px 10px; font-size:{FONT_CAPTION}px; }}"
                f"QPushButton:hover {{ background:{COLOR_DANGER}; color:white; }}")
            button.clicked.connect(lambda _c, d=dish: self._on_delete_dish(d))
            table.setCellWidget(row, 5, button)

    # ── Actions ─────────────────────────────────────────────────────────────

    def _start_filling(self, dish_name: str) -> None:
        """Put an unknown menu line into the form, ready for its values."""
        self._dish_edit.setText(dish_name)
        for spin in self._value_spins.values():
            spin.setValue(0)
        self._value_spins["calories"].setFocus()

    def _on_save_dish(self) -> None:
        name = normalize_dish(self._dish_edit.text())
        if not name:
            QMessageBox.information(self, _TITLE, _MSG_DISH_REQUIRED)
            return
        try:
            save_dish_nutrition(DishNutrition(
                dish_name=name,
                calories=self._value_spins["calories"].value(),
                protein=self._value_spins["protein"].value(),
                carbs=self._value_spins["carbs"].value(),
                fats=self._value_spins["fats"].value(),
            ))
        except Exception:
            _LOGGER.exception("saving dish nutrition failed")
            QMessageBox.critical(self, _TITLE, _MSG_DISH_REQUIRED)
            return
        self._dish_edit.clear()
        for spin in self._value_spins.values():
            spin.setValue(0)
        self._reload()
        QMessageBox.information(self, _TITLE, _MSG_DISH_SAVED)

    def _on_export(self) -> None:
        """Print the التوزيع الكمي attachment for the selected program."""
        program = self._current_program()
        if program is None:
            QMessageBox.information(self, _TITLE, _MSG_NO_PROGRAM)
            return
        # Only meals that actually HAVE components — a meal with none is left
        # out rather than printed as an empty promise.
        composed = [(dish, self._recipes[dish])
                    for dish in self._program_dishes()
                    if self._recipes.get(dish)]
        if not composed:
            QMessageBox.information(self, _TITLE, _MSG_EXPORT_EMPTY)
            return
        settings = get_school_settings()
        path_str, _filter = QFileDialog.getSaveFileName(
            self, _PDF_DIALOG_TITLE, _PDF_DEFAULT_NAME, _PDF_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            write_quantity_breakdown_pdf(
                path, settings, program.name, composed, self._products)
        except Exception:
            _LOGGER.exception("exporting the quantity breakdown failed")
            QMessageBox.critical(self, _TITLE, _MSG_EXPORT_FAILED)
            return
        QMessageBox.information(self, _TITLE, f"{_MSG_EXPORT_SAVED}{path}")

    def _on_delete_dish(self, dish: DishNutrition) -> None:
        if dish.id is not None:
            delete_dish_nutrition(dish.id)
        self._reload()
        QMessageBox.information(self, _TITLE, _MSG_DISH_DELETED)
