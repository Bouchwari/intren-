"""
src/ui/meal_program_screen.py
Weekly meal program editor — 7 days × meal rows grid.
Supports multiple named programs and Ramadan mode.
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen, QTextOption,
)
from PySide6.QtWidgets import (
    QBoxLayout, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QFileDialog, QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_DANGER,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA,
)
from core.models import MealEntry, MealProgram
from data.database import (
    create_program, delete_program, get_all_programs,
    get_program_entries, get_school_settings,
    rename_program, save_program_entries, set_program_ramadan_mode,
)
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "البرنامج الغذائي الأسبوعي"
_PDF_TITLE      = "البرنامج الغذائي"
_BTN_NEW        = "➕  برنامج جديد"
_BTN_RENAME     = "✏️  إعادة تسمية"
_BTN_DELETE     = "🗑️  حذف"
_BTN_SAVE       = "💾  حفظ"
_BTN_EXPORT_PDF = "📄  تحميل PDF"
_BTN_RAMADAN    = "☾  تحويل إلى برنامج رمضان"
_BTN_NORMAL     = "  تحويل إلى برنامج عادي"
_EMPTY_TITLE    = "ابدأ بإنشاء برنامج غذائي"
_EMPTY_HINT     = "أنشئ برنامجاً أسبوعياً، ثم اكتب وجبات كل يوم واحفظه للرجوع إليه لاحقاً."
_PANEL_TITLE    = "إدارة البرنامج"
_PROGRAM_LABEL  = "البرنامج الحالي"
_MODE_TITLE     = "نوع البرنامج"
_NORMAL_BADGE   = "برنامج عادي"
_RAMADAN_BADGE  = "برنامج رمضان"
_SAVE_HINT      = "برنامج رمضان يبقى محفوظاً بعد الحفظ ويمكن الرجوع إليه من القائمة."
_BOARD_TITLE    = "لوحة الأسبوع"
_CELL_HINT      = "اكتب مكونات الوجبة..."
_PANEL_SHOW     = "⚙  إدارة البرنامج"
_PANEL_HIDE     = "إخفاء إدارة البرنامج"
_ACTIVE_DAYS    = "أيام نشطة"
_MEALS_PER_DAY  = "وجبات/يوم"
_COMPLETED      = "وجبات مكتملة"
_UNSAVED_TITLE  = "تعديلات غير محفوظة"
_UNSAVED_PROMPT = "توجد تعديلات غير محفوظة. هل تريد المتابعة بدون حفظها؟"
_NEW_NAME_TITLE = "اسم البرنامج الجديد"
_NEW_NAME_HINT  = "أدخل اسماً للبرنامج:"
_RENAME_TITLE   = "إعادة التسمية"
_DEL_CONFIRM    = "هل أنت متأكد من حذف هذا البرنامج وكل وجباته؟"
_SAVED_OK       = "تم حفظ البرنامج الغذائي بنجاح."
_PDF_DIALOG_TITLE = "تحميل القائمة بصيغة PDF"
_PDF_SAVED_OK     = "تم تحميل القائمة بصيغة PDF بنجاح."
_PDF_DEFAULT_NAME = "قائمة_البرنامج_الغذائي"
_EMPTY_MENU_CELL  = "—"

# Day ids stay unchanged because saved meal entries use these numeric values.
_PAGE_BG = "#F8F9FA"
_PANEL_BG = "#E1F5EE"
_PANEL_BORDER = "#9FE1CB"
_INK = "#085041"
_MUTED = "#6B7280"
_CLAY = "#EF9F27"
_TEAL = "#1D9E75"
_NAVY = "#534AB7"
_AMBER = "#EF9F27"
_SUCCESS = "#16a34a"
_CELL_BG = "#FFFFFF"
_CONTROL_BG = "#2D2D3A"
_CONTROL_SOFT = "#3F3F50"
_BOARD_BG = "#FFFFFF"
_PURPLE_LIGHT = "#EEEDFE"
_AMBER_LIGHT = "#FAEEDA"
_GREEN_LIGHT = "#E1F5EE"

_DAYS: List[Tuple[int, str]] = [
    (2, "الإثنين"),
    (3, "الثلاثاء"),
    (4, "الأربعاء"),
    (5, "الخميس"),
    (6, "الجمعة"),
    (0, "السبت"),
    (1, "الأحد"),
]

# Regular meals
_REGULAR_MEALS: List[Tuple[str, str]] = [
    (MEAL_FTOUR, "الفطور"),
    (MEAL_GHADA, "الغذاء"),
    (MEAL_ASHA,  "العشاء"),
]

# Ramadan meals
_RAMADAN_MEALS: List[Tuple[str, str]] = [
    ("ftour_ramadan", "الإفطار"),
    ("shour",         "السحور"),
]

_MEAL_ACCENTS: Dict[str, str] = {
    MEAL_FTOUR: _AMBER,
    MEAL_GHADA: _TEAL,
    MEAL_ASHA: _NAVY,
    "ftour_ramadan": _CLAY,
    "shour": _TEAL,
}

# Type alias for the grid cell dict
_CellKey = Tuple[int, str]   # (day_of_week, meal_type)


def _make_btn(
    label: str,
    color: str = COLOR_ACCENT,
    *,
    text_color: str = "white",
    min_height: int = 40,
) -> QPushButton:
    btn = QPushButton(label)
    btn.setMinimumHeight(min_height)
    btn.setStyleSheet(
        f"background:{color}; color:{text_color}; border:1px solid {color}; border-radius:12px;"
        "padding:0 14px; font-size:12px; font-weight:800;"
        "min-width:96px;"
    )
    return btn


def _card(
    object_name: str = "mealProgramCard",
    *,
    background: str = "white",
    border: str = _PANEL_BORDER,
    radius: int = 22,
) -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    frame.setStyleSheet(f"""
        #{object_name} {{
            background: {background};
            border: 1px solid {border};
            border-radius: {radius}px;
        }}
    """)
    return frame


class MealProgramScreen(QWidget):
    """Full weekly meal program screen."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._current_program: Optional[MealProgram] = None
        self._cells: Dict[_CellKey, QPlainTextEdit] = {}
        self._stat_labels: Dict[str, QLabel] = {}
        self._control_panel: Optional[QWidget] = None
        self._pdf_btn: Optional[QPushButton] = None
        self._current_index: int = -1
        self._is_dirty: bool = False
        self._loading_grid: bool = False
        self._program_panel_visible: bool = False
        self._ramadan_mode: bool = False
        self._build_ui()
        self._load_programs()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setDirection(QBoxLayout.Direction.RightToLeft)
        body.setSpacing(14)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background:transparent;")

        self._empty_widget = self._build_empty_state()
        body.addWidget(self._scroll, 1)
        body.addWidget(self._empty_widget, 1)
        self._control_panel = self._build_control_panel()
        self._control_panel.setVisible(self._program_panel_visible)
        body.addWidget(self._control_panel, 0)
        root.addLayout(body, 1)

    def _build_header(self) -> QWidget:
        header = _card("mealHero", background=_BOARD_BG, radius=26)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        title_col = QVBoxLayout()
        title_col.setSpacing(7)
        title = QLabel(_TITLE)
        f = QFont()
        f.setPointSize(20)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"background:transparent; color:{_INK};")

        title_col.addWidget(title)

        quick_actions = QHBoxLayout()
        quick_actions.setDirection(QBoxLayout.Direction.RightToLeft)
        quick_actions.setSpacing(8)
        self._pdf_btn = _make_btn(_BTN_EXPORT_PDF, _CLAY, min_height=34)
        self._pdf_btn.clicked.connect(self._on_export_pdf)
        quick_new_btn = _make_btn(_BTN_NEW, _SUCCESS, min_height=34)
        quick_new_btn.clicked.connect(self._on_new)
        self._panel_toggle_btn = _make_btn(_PANEL_SHOW, _CONTROL_BG, min_height=34)
        self._panel_toggle_btn.clicked.connect(self._toggle_program_panel)
        quick_actions.addWidget(self._pdf_btn)
        quick_actions.addWidget(quick_new_btn)
        quick_actions.addWidget(self._panel_toggle_btn)
        quick_actions.addStretch()
        title_col.addLayout(quick_actions)

        badge_col = QVBoxLayout()
        badge_col.setSpacing(8)
        self._hero_status = self._make_badge(_NORMAL_BADGE, _TEAL, "white")
        board_badge = self._make_badge(_BOARD_TITLE, _PANEL_BG, _INK)

        badge_col.addWidget(board_badge, 0, Qt.AlignmentFlag.AlignLeft)
        badge_col.addWidget(self._hero_status, 0, Qt.AlignmentFlag.AlignLeft)
        badge_col.addStretch()

        layout.addLayout(title_col, 1)
        layout.addLayout(badge_col)
        return header

    def _toggle_program_panel(self) -> None:
        self._set_program_panel_visible(not self._program_panel_visible)

    def _set_program_panel_visible(self, visible: bool) -> None:
        self._program_panel_visible = visible
        if self._control_panel is not None:
            self._control_panel.setVisible(self._program_panel_visible)
        self._panel_toggle_btn.setText(_PANEL_HIDE if self._program_panel_visible else _PANEL_SHOW)

    def refresh(self) -> None:
        """Open this page in focus mode so the full week has maximum space."""
        self._set_program_panel_visible(False)

    def _build_control_panel(self) -> QWidget:
        panel = _card("mealControlPanel", background=_CONTROL_BG, border=_CONTROL_BG, radius=26)
        panel.setFixedWidth(306)
        panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)

        title = QLabel(_PANEL_TITLE)
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignRight)
        title.setStyleSheet("background:transparent; color:white;")
        layout.addWidget(title)

        layout.addWidget(self._make_panel_label(_PROGRAM_LABEL))
        self._prog_combo = QComboBox()
        self._prog_combo.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._prog_combo.setMinimumHeight(38)
        self._prog_combo.setStyleSheet(
            "QComboBox {"
            "background:white; color:#111827; border:0; border-radius:14px;"
            "padding:6px 14px 6px 34px; font-size:13px; font-weight:700;"
            f"selection-background-color:{_TEAL}; selection-color:white;"
            "}"
            "QComboBox::drop-down {"
            "subcontrol-origin:padding; subcontrol-position:left center;"
            "width:30px; border:0; background:transparent;"
            "}"
            "QComboBox::down-arrow { image:none; width:0; height:0; }"
            "QComboBox QAbstractItemView {"
            "background:white; color:#111827; border:1px solid #D9E1DA;"
            "selection-background-color:#E1F5EE; selection-color:#085041;"
            "padding:6px;"
            "}"
        )
        self._prog_combo.currentIndexChanged.connect(self._on_program_changed)
        layout.addWidget(self._prog_combo)

        self._new_btn = _make_btn(_BTN_NEW, _SUCCESS, min_height=36)
        self._rename_btn = _make_btn(_BTN_RENAME, _CONTROL_SOFT, min_height=36)
        self._delete_btn = _make_btn(_BTN_DELETE, COLOR_DANGER, min_height=36)
        self._new_btn.clicked.connect(self._on_new)
        self._rename_btn.clicked.connect(self._on_rename)
        self._delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self._new_btn)
        layout.addWidget(self._rename_btn)
        layout.addWidget(self._delete_btn)

        layout.addSpacing(4)
        layout.addWidget(self._make_panel_label(_MODE_TITLE))
        self._mode_badge = self._make_badge(_NORMAL_BADGE, _TEAL, "white")
        layout.addWidget(self._mode_badge)

        self._ramadan_btn = _make_btn(_BTN_RAMADAN, _CLAY, min_height=38)
        self._ramadan_btn.clicked.connect(self._toggle_ramadan)
        layout.addWidget(self._ramadan_btn)

        layout.addSpacing(6)
        hint = QLabel(_SAVE_HINT)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        hint.setStyleSheet("background:transparent; color:#D8E4DE; font-size:11px; line-height:130%;")
        layout.addWidget(hint)

        self._save_btn = _make_btn(_BTN_SAVE, COLOR_ACCENT, min_height=42)
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)
        return panel

    def _make_panel_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignRight)
        label.setStyleSheet("background:transparent; color:#C9D8D1; font-size:12px; font-weight:700;")
        return label

    def _make_badge(self, text: str, background: str, text_color: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(28)
        label.setStyleSheet(
            f"background:{background}; color:{text_color}; border-radius:14px;"
            "padding:4px 12px; font-size:12px; font-weight:800;"
        )
        return label

    def _build_empty_state(self) -> QWidget:
        card = _card("mealEmptyState", background=_BOARD_BG, radius=26)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(34, 52, 34, 52)
        layout.setSpacing(14)

        title = QLabel(_EMPTY_TITLE)
        f = QFont()
        f.setPointSize(18)
        f.setBold(True)
        title.setFont(f)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"background:transparent; color:{_INK};")

        hint = QLabel(_EMPTY_HINT)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"background:transparent; color:{_MUTED}; font-size:13px;")

        action = _make_btn(_BTN_NEW, _SUCCESS)
        action.setMinimumWidth(180)
        action.clicked.connect(self._on_new)

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(10)
        layout.addWidget(action, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        return card

    def _build_grid(self) -> QWidget:
        """Build the whole week as a 4+3 board with no horizontal dragging."""
        meals = _RAMADAN_MEALS if self._ramadan_mode else _REGULAR_MEALS

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(12)
        container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout.addWidget(self._build_stats_row(len(meals)))

        board = QWidget()
        board.setStyleSheet("background:transparent;")
        board.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        board_grid = QGridLayout(board)
        board_grid.setContentsMargins(0, 0, 0, 0)
        board_grid.setHorizontalSpacing(10)
        board_grid.setVerticalSpacing(10)
        self._cells = {}
        for index, (day_idx, day_name) in enumerate(_DAYS):
            day_card = self._build_day_card(day_idx, day_name, meals)
            board_grid.addWidget(day_card, index // 4, index % 4)

        for col in range(4):
            board_grid.setColumnStretch(col, 1)
        layout.addWidget(board)
        self._update_stats()
        return container

    def _build_stats_row(self, meals_per_day: int) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._stat_labels = {}
        stats = [
            ("days", str(len(_DAYS)), _ACTIVE_DAYS, _GREEN_LIGHT, _TEAL),
            ("meals", str(meals_per_day), _MEALS_PER_DAY, _AMBER_LIGHT, _AMBER),
            ("completed", "0", _COMPLETED, _PURPLE_LIGHT, _NAVY),
        ]
        for key, value, label, background, color in stats:
            stat_card = self._build_stat_card(key, value, label, background, color)
            self._stat_labels[key] = stat_card.findChild(QLabel, f"statValue{key}")  # type: ignore[assignment]
            layout.addWidget(stat_card)
        layout.addStretch()
        return row

    def _build_stat_card(self, key: str, value: str, label: str, background: str, color: str) -> QWidget:
        card = _card(f"mealStat{key}", background=background, border=background, radius=18)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        value_label = QLabel(value)
        value_label.setObjectName(f"statValue{key}")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet(f"background:transparent; color:{color}; font-size:18px; font-weight:900;")

        text_label = QLabel(label)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet(f"background:transparent; color:{_MUTED}; font-size:11px; font-weight:700;")
        layout.addWidget(value_label)
        layout.addWidget(text_label)
        return card

    def _build_day_card(self, day_idx: int, day_name: str, meals: List[Tuple[str, str]]) -> QWidget:
        card = _card(f"mealDayCard{day_idx}", background=_BOARD_BG, radius=24)
        card.setMinimumWidth(188)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        day_label = QLabel(day_name)
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        day_label.setFont(f)
        day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        day_label.setMinimumHeight(34)
        day_label.setStyleSheet(
            f"background:{_GREEN_LIGHT}; color:{_INK};"
            "border-radius:14px; padding:3px 10px;"
        )
        meal_count = QLabel(f"{len(meals)} وجبات")
        meal_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meal_count.setMinimumHeight(26)
        meal_count.setStyleSheet(
            f"background:{_PANEL_BG}; color:{_MUTED};"
            "border-radius:12px; padding:3px 8px; font-size:11px; font-weight:700;"
        )
        title_row.addWidget(day_label)
        title_row.addStretch()
        title_row.addWidget(meal_count)
        layout.addLayout(title_row)

        for meal_key, meal_name in meals:
            layout.addWidget(self._build_meal_card(day_idx, meal_key, meal_name))
        return card

    def _build_meal_card(self, day_idx: int, meal_key: str, meal_name: str) -> QWidget:
        accent = _MEAL_ACCENTS.get(meal_key, _TEAL)
        block = _card(f"mealBlock{day_idx}{meal_key}", background="white", radius=18)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        dot = QLabel("")
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background:{accent}; border-radius:5px;")
        label = QLabel(meal_name)
        label.setStyleSheet(
            f"background:transparent; color:{accent};"
            "font-size:12px; font-weight:900;"
        )
        title_row.addWidget(label)
        title_row.addStretch()
        title_row.addWidget(dot)

        cell = QPlainTextEdit()
        cell.setPlaceholderText(_CELL_HINT)
        cell.setMinimumHeight(50)
        cell.setMaximumHeight(62)
        cell.setTabChangesFocus(True)
        cell.setStyleSheet(
            f"background:{_CELL_BG}; color:{COLOR_TEXT_PRIMARY};"
            f"border:1px solid {_PANEL_BORDER}; border-radius:12px; padding:7px; font-size:12px;"
            f"selection-background-color:{accent}; selection-color:white;"
        )
        cell.textChanged.connect(self._mark_dirty)
        layout.addLayout(title_row)
        layout.addWidget(cell)
        self._cells[(day_idx, meal_key)] = cell
        return block

    # ── Programs management ────────────────────────────────────────────────

    def _load_programs(self) -> None:
        """Refresh program dropdown from DB."""
        programs: List[MealProgram] = get_all_programs()
        self._prog_combo.blockSignals(True)
        self._prog_combo.clear()
        for p in programs:
            label = f"{'☾ ' if p.is_ramadan else ''}{p.name}"
            self._prog_combo.addItem(label, p)
        self._prog_combo.blockSignals(False)

        has_programs = len(programs) > 0
        self._empty_widget.setVisible(not has_programs)
        self._scroll.setVisible(has_programs)
        self._save_btn.setEnabled(has_programs)
        self._rename_btn.setEnabled(has_programs)
        self._delete_btn.setEnabled(has_programs)
        self._ramadan_btn.setEnabled(has_programs)
        if self._pdf_btn is not None:
            self._pdf_btn.setEnabled(has_programs)

        if has_programs:
            self._on_program_changed(0)
        else:
            self._current_index = -1

    def _on_program_changed(self, index: int) -> None:
        """Switch grid to the selected program."""
        if index < 0 or self._prog_combo.count() == 0:
            return
        if self._is_dirty and index != self._current_index:
            if not self._confirm_discard_changes():
                self._restore_combo_index()
                return
        program: MealProgram = self._prog_combo.itemData(index)
        self._current_program = program
        self._current_index = index
        self._ramadan_mode = program.is_ramadan
        self._update_mode_ui()
        self._rebuild_grid()
        self._fill_grid(get_program_entries(program.id))  # type: ignore[arg-type]

    def _rebuild_grid(self) -> None:
        """Replace the grid widget inside the scroll area."""
        new_grid = self._build_grid()
        self._scroll.setWidget(new_grid)

    def _update_mode_ui(self) -> None:
        """Keep all visible mode indicators aligned with the current layout."""
        label = _RAMADAN_BADGE if self._ramadan_mode else _NORMAL_BADGE
        color = _CLAY if self._ramadan_mode else _TEAL
        self._ramadan_btn.setText(_BTN_NORMAL if self._ramadan_mode else _BTN_RAMADAN)
        self._mode_badge.setText(label)
        self._mode_badge.setStyleSheet(
            f"background:{color}; color:white; border-radius:14px;"
            "padding:4px 12px; font-size:12px; font-weight:800;"
        )
        self._hero_status.setText(label)
        self._hero_status.setStyleSheet(
            f"background:{color}; color:white; border-radius:14px;"
            "padding:4px 12px; font-size:12px; font-weight:800;"
        )

    def _fill_grid(self, entries: List[MealEntry]) -> None:
        """Populate QPlainTextEdit cells from stored entries."""
        self._loading_grid = True
        for entry in entries:
            key = (entry.day_of_week, entry.meal_type)
            if key in self._cells:
                self._cells[key].setPlainText(entry.menu_text)
        self._loading_grid = False
        self._is_dirty = False
        self._update_stats()

    def _mark_dirty(self) -> None:
        if self._loading_grid:
            return
        self._is_dirty = True
        self._update_stats()

    def _update_stats(self) -> None:
        if not self._stat_labels:
            return
        completed = sum(1 for cell in self._cells.values() if cell.toPlainText().strip())
        meals_per_day = len(_RAMADAN_MEALS if self._ramadan_mode else _REGULAR_MEALS)
        self._stat_labels["days"].setText(str(len(_DAYS)))
        self._stat_labels["meals"].setText(str(meals_per_day))
        self._stat_labels["completed"].setText(str(completed))

    def _confirm_discard_changes(self) -> bool:
        reply = QMessageBox.question(
            self,
            _UNSAVED_TITLE,
            _UNSAVED_PROMPT,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _restore_combo_index(self) -> None:
        self._prog_combo.blockSignals(True)
        self._prog_combo.setCurrentIndex(self._current_index)
        self._prog_combo.blockSignals(False)

    def _collect_entries(self) -> List[MealEntry]:
        """Read all non-empty cells and build a list of MealEntry objects."""
        assert self._current_program is not None
        program_id = self._current_program.id
        entries: List[MealEntry] = []
        for (day_idx, meal_key), cell in self._cells.items():
            text = cell.toPlainText().strip()
            entries.append(MealEntry(
                program_id=program_id,  # type: ignore[arg-type]
                day_of_week=day_idx,
                meal_type=meal_key,
                menu_text=text,
            ))
        return entries

    def _default_pdf_path(self) -> str:
        if self._current_program is None:
            return f"{_PDF_DEFAULT_NAME}.pdf"
        safe_name = self._safe_filename(self._current_program.name)
        return f"{_PDF_DEFAULT_NAME}_{safe_name}.pdf"

    def _safe_filename(self, value: str) -> str:
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid else char for char in value).strip(" .")
        return cleaned or _PDF_DEFAULT_NAME

    def _pdf_menu_rows(self) -> List[Tuple[str, List[str]]]:
        meals = _RAMADAN_MEALS if self._ramadan_mode else _REGULAR_MEALS
        rows: List[Tuple[str, List[str]]] = []
        for day_idx, day_name in _DAYS:
            cells = []
            for meal_key, _ in meals:
                text = self._cells.get((day_idx, meal_key))
                value = text.toPlainText().strip() if text is not None else ""
                cells.append(value or _EMPTY_MENU_CELL)
            rows.append((day_name, cells))
        return rows

    def _draw_pdf_text(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        *,
        size: int,
        color: str,
        bold: bool = False,
        align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
        wrap: bool = False,
    ) -> None:
        font = QFont("Segoe UI")
        font.setPointSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        option = QTextOption()
        option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        option.setAlignment(align)
        option.setWrapMode(QTextOption.WrapMode.WordWrap if wrap else QTextOption.WrapMode.NoWrap)
        painter.drawText(rect, text, option)

    def _draw_pdf_cell(
        self,
        painter: QPainter,
        rect: QRectF,
        *,
        background: str,
        border: str,
        text: str,
        text_color: str,
        size: int,
        bold: bool = False,
        align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
        wrap: bool = False,
    ) -> None:
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(background))
        painter.drawRect(rect)
        text_rect = rect.adjusted(8, 7, -8, -7)
        self._draw_pdf_text(
            painter,
            text_rect,
            text,
            size=size,
            color=text_color,
            bold=bold,
            align=align,
            wrap=wrap,
        )

    def _write_menu_pdf(self, path: Path) -> None:
        if self._current_program is None:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        writer = QPdfWriter(str(path))
        writer.setResolution(96)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Landscape)
        writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        writer.setTitle(_PDF_TITLE)

        painter = QPainter(writer)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            page_w = float(writer.width())
            page_h = float(writer.height())
            margin = 38.0
            content_w = page_w - (margin * 2)
            settings = get_school_settings()

            table_y = draw_official_pdf_header(
                painter,
                page_width=page_w,
                margin=margin,
                top=18.0,
                settings=settings,
                title=_PDF_TITLE,
            )

            table_y += 6

            meals = _RAMADAN_MEALS if self._ramadan_mode else _REGULAR_MEALS
            rows = self._pdf_menu_rows()
            footer_h = 82.0
            table_x = margin
            table_w = content_w
            table_h = page_h - table_y - footer_h - margin
            header_h = 42.0
            row_h = (table_h - header_h) / max(1, len(rows))
            day_w = 118.0
            meal_w = (table_w - day_w) / max(1, len(meals))
            right = table_x + table_w

            header_y = table_y
            day_header = QRectF(right - day_w, header_y, day_w, header_h)
            self._draw_pdf_cell(
                painter,
                day_header,
                background=_INK,
                border=_INK,
                text="اليوم",
                text_color="white",
                size=13,
                bold=True,
                align=Qt.AlignmentFlag.AlignCenter,
            )

            current_right = day_header.left()
            for _, meal_name in meals:
                rect = QRectF(current_right - meal_w, header_y, meal_w, header_h)
                self._draw_pdf_cell(
                    painter,
                    rect,
                    background=_INK,
                    border=_INK,
                    text=meal_name,
                    text_color="white",
                    size=13,
                    bold=True,
                    align=Qt.AlignmentFlag.AlignCenter,
                )
                current_right = rect.left()

            for row_index, (day_name, values) in enumerate(rows):
                row_y = table_y + header_h + (row_index * row_h)
                day_rect = QRectF(right - day_w, row_y, day_w, row_h)
                self._draw_pdf_cell(
                    painter,
                    day_rect,
                    background="#F8F9FA",
                    border=_PANEL_BORDER,
                    text=day_name,
                    text_color=_INK,
                    size=13,
                    bold=True,
                    align=Qt.AlignmentFlag.AlignCenter,
                    wrap=True,
                )

                current_right = day_rect.left()
                for value in values:
                    is_empty = value == _EMPTY_MENU_CELL
                    rect = QRectF(current_right - meal_w, row_y, meal_w, row_h)
                    self._draw_pdf_cell(
                        painter,
                        rect,
                        background="white",
                        border=_PANEL_BORDER,
                        text=value,
                        text_color=_MUTED if is_empty else "#111827",
                        size=11,
                        align=Qt.AlignmentFlag.AlignCenter if is_empty else Qt.AlignmentFlag.AlignRight,
                        wrap=True,
                    )
                    current_right = rect.left()

            footer_y = page_h - margin - footer_h + 6
            draw_official_pdf_footer(
                painter,
                page_width=page_w,
                margin=margin,
                top=footer_y,
                settings=settings,
            )
        finally:
            painter.end()

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_export_pdf(self) -> None:
        if self._current_program is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            _PDF_DIALOG_TITLE,
            self._default_pdf_path(),
            "PDF (*.pdf)",
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")

        try:
            self._write_menu_pdf(path)
            QMessageBox.information(self, "تم", _PDF_SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل PDF:\n{exc}")

    def _on_new(self) -> None:
        if self._is_dirty and not self._confirm_discard_changes():
            return
        settings = get_school_settings()
        school_year = settings.school_year if settings else ""
        default_name = "برنامج رمضان" if self._ramadan_mode else "البرنامج الأسبوعي"
        name, ok = QInputDialog.getText(
            self, _NEW_NAME_TITLE, _NEW_NAME_HINT,
            QLineEdit.EchoMode.Normal, f"{default_name} {self._prog_combo.count() + 1}"
        )
        if not ok or not name.strip():
            return
        try:
            create_program(name.strip(), school_year, self._ramadan_mode)
            self._load_programs()
            # Select the newly created program (last in list)
            self._prog_combo.setCurrentIndex(self._prog_combo.count() - 1)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def _on_rename(self) -> None:
        if self._current_program is None:
            return
        name, ok = QInputDialog.getText(
            self, _RENAME_TITLE, _NEW_NAME_HINT,
            QLineEdit.EchoMode.Normal, self._current_program.name
        )
        if not ok or not name.strip():
            return
        try:
            rename_program(self._current_program.id, name.strip())  # type: ignore[arg-type]
            current_idx = self._prog_combo.currentIndex()
            self._load_programs()
            self._prog_combo.setCurrentIndex(current_idx)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", str(exc))

    def _on_delete(self) -> None:
        if self._current_program is None:
            return
        reply = QMessageBox.question(
            self, "تأكيد الحذف",
            f"حذف:  {self._current_program.name}\n\n{_DEL_CONFIRM}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                delete_program(self._current_program.id)  # type: ignore[arg-type]
                self._current_program = None
                self._load_programs()
            except Exception as exc:
                QMessageBox.critical(self, "خطأ", str(exc))

    def _toggle_ramadan(self) -> None:
        """Switch between regular and Ramadan meal layout."""
        if self._is_dirty and not self._confirm_discard_changes():
            return
        self._ramadan_mode = not self._ramadan_mode
        self._update_mode_ui()
        self._rebuild_grid()
        # Re-fill from saved entries after rebuilding
        if self._current_program and self._current_program.id:
            self._fill_grid(get_program_entries(self._current_program.id))

    def _on_save(self) -> None:
        if self._current_program is None:
            return
        try:
            entries = self._collect_entries()
            set_program_ramadan_mode(self._current_program.id, self._ramadan_mode)  # type: ignore[arg-type]
            save_program_entries(self._current_program.id, entries)  # type: ignore[arg-type]
            self._current_program.is_ramadan = self._ramadan_mode
            self._is_dirty = False
            self._update_mode_ui()
            current_idx = self._prog_combo.currentIndex()
            if current_idx >= 0:
                label = f"{'☾ ' if self._ramadan_mode else ''}{self._current_program.name}"
                self._prog_combo.setItemText(current_idx, label)
            QMessageBox.information(self, "تم", _SAVED_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")
