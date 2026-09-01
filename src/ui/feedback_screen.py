"""
src/ui/feedback_screen.py
تقييم التلاميذ — what the pupils thought of the meals.

The unit is ONE DISH PER WEEK, not per day: a week's menu has ~12 distinct
dishes against 21 day-slots, a dish served twice is asked about once, and the
collecting happens once a week. The user asked for this on 2026-08-29 after
finding the day-by-day version too much work. The old per-day records are kept
and shown in their own section — nothing typed before was thrown away.

Ratings are ENTERED IN THE APP, by the مسير or الحارس العام. The prototype this
came from collected them by QR code from pupils' phones; that needs a web
server reachable from those phones, and this app is offline on a single PC.

Every figure comes from ratings actually entered. A dish with none is reported
as having none, never as a zero, and every average is shown WITH the number of
opinions behind it: 5.0 from one rating is not the same claim as 5.0 from
twenty.
"""
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_PAPER, COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_WARNING,
    MEAL_LABELS, FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.feedback import (
    COUNT_FIELDS, CYCLES, GENDERS, MIN_RATINGS_FOR_RANKING, RATING_LEVELS,
    RATING_MAX, UNSPECIFIED,
    DishSummary, average_by_meal_type, least_popular, most_popular,
    normalize_dish, overall_average,
    record_average, response_counts, response_total, week_start_of,
)
from core.active_cycles import visible_cycles
from core.models import MealFeedback, WeekFeedback
from data.database import (
    delete_feedback, delete_week_feedback, get_all_feedback,
    get_all_students, get_all_week_feedback, get_school_settings,
    get_week_feedback,
    save_week_feedback,
)
from ui.feedback_collect import (
    dishes_for_week, groups_to_collect, import_feedback_workbook, week_label,
    write_feedback_workbook, write_tally_sheet_pdf,
)
from ui.feedback_export import write_feedback_report_pdf
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ──────────────────────────────────────────────────────────
_TITLE = "تقييم التلاميذ"
_SUBTITLE = ("آراء التلاميذ في الوجبات المقدمة — تُسجَّل هنا بعد الوجبة "
             "من طرف المسير أو الحارس العام")

_LBL_DATE = "تاريخ الوجبة"
_LBL_MEAL = "الوجبة"
_LBL_DISH = "الطبق"
_LBL_WEEK = "أسبوع القائمة"
_LBL_CYCLE = "السلك"
_LBL_GENDER = "الجنس"
_GROUP_ANY = "غير محدد"
_CYCLE_LABELS = {"primary": "ابتدائي", "collegial": "إعدادي",
                 "qualifying": "تأهيلي"}
_GENDER_LABELS = {"male": "ذكور", "female": "إناث"}
_LBL_GROUP_HINT = ("سجّل الأعداد لكل فئة على حدة ليعرف التقرير مَن أبدى الرأي. "
                   "اترك الحقلين «غير محدد» لتسجيل رأي عام دون تصنيف.")
_LBL_GROUPS_SAVED = "مسجّل هذا الأسبوع:"
_LBL_GROUPS_NONE = "لم تُسجَّل أي فئة في هذا الأسبوع بعد."
_LBL_LEGACY = "سجل قديم — تقييمات مسجلة يوماً بيوم"
_LBL_LEGACY_HINT = ("سُجّلت قبل الانتقال إلى تقييم قائمة الأسبوع. تبقى محفوظة "
                    "ومحتسبة في المتوسطات، ولا تُضاف إليها تقييمات جديدة")
_MENU_HDR = (["الطبق"] + ["ممتاز", "جيد", "متوسط", "ضعيف", "سيء"]
             + ["المعبّرون", "المتوسط"])
_LBL_RATING = "عدد التلاميذ حسب التقييم"
_LBL_RESPONSES = "عدد المعبّرين"
_LBL_NOTE = "ملاحظة"
_LBL_BY = "سجّل التقييم"

_LBL_AVERAGE = "متوسط التقييم العام"
_LBL_COUNT = "عدد التلاميذ المعبّرين"
_LBL_COUNT_ROWS = "من {rows} وجبة مسجلة"
_LBL_TOP = "الوجبات الأكثر استحساناً"
_LBL_BOTTOM = "الوجبات الأقل استحساناً"
_LBL_BY_MEAL = "المتوسط حسب الوجبة"

_BTN_SAVE = "حفظ تقييم الأسبوع"
_BTN_SAVE_ICON = "⭐"
_BTN_DELETE = "حذف"

_MSG_DISH_REQUIRED = "اكتب اسم الطبق الذي يخصه التقييم."
_MSG_SAVED = "تم حفظ تقييم الأسبوع ({saved} طبق)."
_MSG_NO_DISHES = "لا توجد أطباق في قائمة هذا الأسبوع — تحقق من البرنامج الغذائي."
_MSG_NOTHING_ENTERED = "أدخل عدد التلاميذ لطبق واحد على الأقل."
_MSG_DELETED = "تم حذف التقييم."

_NO_RATINGS = "—"
_NO_RATINGS_HINT = "لم يُسجَّل أي تقييم بعد"
_RANKING_HINT = ("تظهر هنا الأطباق التي عبّر عنها {minimum} تلاميذ على الأقل — "
                 "رأي واحد لا يكفي للحكم على طبق")
_NOT_ENOUGH = "لا يوجد طبق بعدد تقييمات كافٍ بعد"
# The counts are PUPILS now, not saved entries.
_COUNT_SUFFIX = "تلميذ"

_HDR = ["التاريخ", "الوجبة", "الطبق", "التوزيع", "المتوسط", "المعبّرون",
        "ملاحظة", "سجّله", ""]
_MSG_NO_RESPONSES = "أدخل عدد التلاميذ في مستوى واحد على الأقل."
_BTN_EXPORT = "تصدير التقرير"
_BTN_EXPORT_ICON = "📄"
_PDF_DIALOG_TITLE = "تصدير تقرير آراء التلاميذ"
_PDF_DEFAULT_NAME = "تقرير_آراء_التلاميذ"
_PDF_FILTER = "PDF (*.pdf)"
_MSG_EXPORT_SAVED = "تم تصدير التقرير إلى:\n"
_MSG_EXPORT_FAILED = "تعذر تصدير التقرير. تحقق من المكان المختار ثم أعد المحاولة."
_MSG_EXPORT_EMPTY = "لا توجد تقييمات مسجلة بعد."
_BTN_TALLY = "ورقة التفريغ"
_BTN_TALLY_ICON = "🧾"
_BTN_XLSX_OUT = "تصدير Excel"
_BTN_XLSX_OUT_ICON = "📤"
_BTN_XLSX_IN = "استيراد Excel"
_BTN_XLSX_IN_ICON = "📥"
_TALLY_DIALOG_TITLE = "تصدير ورقة التفريغ"
_TALLY_DEFAULT_NAME = "ورقة_تفريغ_آراء_التلاميذ"
_XLSX_OUT_DIALOG_TITLE = "تصدير ورقة الآراء بصيغة Excel"
_XLSX_IN_DIALOG_TITLE = "استيراد ورقة الآراء المملوءة"
_XLSX_DEFAULT_NAME = "آراء_التلاميذ"
_XLSX_FILTER = "Excel (*.xlsx)"
_MSG_NO_MEALS = "لا توجد وجبات مقدمة في هذه الفترة."
_MSG_TALLY_SAVED = "تم تصدير ورقة التفريغ إلى:\n"
_MSG_XLSX_SAVED = "تم تصدير ورقة Excel إلى:\n"
_MSG_IMPORT_DONE = "تم استيراد {saved} وجبة."
_MSG_IMPORT_SKIPPED = "\nتم تجاوز {skipped} سطراً بدون أعداد."
_MSG_IMPORT_PROBLEMS = "\n\nأسطر لم تُقرأ:\n{problems}"
_MSG_IMPORT_NONE = "لم يُستورد أي سطر — تأكد من ملء الأعداد في الملف."
_MSG_IMPORT_FAILED = "تعذر قراءة الملف. تأكد من أنه ورقة Excel صادرة عن التطبيق."
_IMPORT_PROBLEM_LIMIT = 8

_RATING_LABELS = {
    5: "ممتاز",
    4: "جيد",
    3: "متوسط",
    2: "ضعيف",
    1: "سيء",
}

_TABLE_STYLE = ""      # filled in below, once the colours are known
_PAGE_BG = COLOR_PAPER
_PANEL_BG = "#ffffff"
_HISTORY_LIMIT = 500
_MENU_ROW_HEIGHT = 38
_TOP_LIMIT = 3

_LOGGER = logging.getLogger(__name__)


def _table_style() -> str:
    return f"""
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
    """


def _tint(hex_color: str, alpha: float = 0.13) -> str:
    """Translucent palette colour as Qt-stylesheet rgba().

    Not `f"{color}22"` — Qt reads 8-digit hex as #AARRGGBB, which produces a
    dark opaque colour rather than a light tint.
    """
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _rating_color(average: float) -> str:
    if average >= 4:
        return COLOR_SUCCESS
    if average >= 3:
        return COLOR_WARNING
    return COLOR_DANGER


def _stars(rating: int) -> str:
    """A rating read at a glance, with the number kept alongside it so the
    meaning does not depend on counting little shapes."""
    filled = max(0, min(RATING_MAX, rating))
    return "★" * filled + "☆" * (RATING_MAX - filled)


def _panel() -> QFrame:
    frame = QFrame()
    frame.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    frame.setStyleSheet(
        f"QFrame {{ background:{_PANEL_BG}; border:1px solid {COLOR_BORDER};"
        f"border-radius:14px; }}")
    return frame


def _field_style() -> str:
    """Shared look for every input on this screen.

    Written as real selectors, not a bare property list, so the spin buttons
    can be told NOT to inherit the field's own border — unstyled they drew as
    a detached bordered box beside every count cell.
    """
    return (
        f"QLineEdit, QSpinBox {{"
        f"  background:white; color:{COLOR_TEXT_PRIMARY};"
        f"  border:1px solid {COLOR_BORDER}; border-radius:8px;"
        f"  padding:6px 10px; font-size:{FONT_BODY}px; }}"
        f"QSpinBox::up-button, QSpinBox::down-button {{"
        f"  border:none; background:transparent; width:13px; }}"
    )


class FeedbackScreen(QWidget):
    """تقييم التلاميذ — record a rating, and see what the week thought."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._week_records: List[WeekFeedback] = []
        self._all_weeks: List[WeekFeedback] = []
        self._records: List[MealFeedback] = []      # the legacy per-day log
        self._menu_spins: Dict[str, Dict[int, QSpinBox]] = {}
        self._build_ui()
        self._reload()
        # Connected last, so it never fires while the widgets are being built.
        self._week_input.dateChanged.connect(self._on_week_changed)

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
        inner.addWidget(self._build_week_menu())
        inner.addWidget(self._build_rankings())
        inner.addWidget(self._build_history())
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

        for label, icon, handler in (
            (_BTN_TALLY, _BTN_TALLY_ICON, self._on_tally_sheet),
            (_BTN_XLSX_OUT, _BTN_XLSX_OUT_ICON, self._on_export_workbook),
            (_BTN_XLSX_IN, _BTN_XLSX_IN_ICON, self._on_import_workbook),
            (_BTN_EXPORT, _BTN_EXPORT_ICON, self._on_export),
        ):
            button = IconButton(label, icon=icon, bg=COLOR_ACCENT, min_height=36)
            button.clicked.connect(handler)
            row.addWidget(button)
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

        self._avg_card, self._avg_value, self._avg_caption = self._stat_card(
            _LBL_AVERAGE, COLOR_SUCCESS)
        self._count_card, self._count_value, self._count_caption = self._stat_card(
            _LBL_COUNT, COLOR_ACCENT)
        row.addWidget(self._avg_card, 1)
        row.addWidget(self._count_card, 1)

        by_meal = _panel()
        box = QVBoxLayout(by_meal)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(4)
        box.addWidget(self._caption(_LBL_BY_MEAL))
        self._by_meal_label = QLabel(_NO_RATINGS_HINT)
        self._by_meal_label.setWordWrap(True)
        self._by_meal_label.setStyleSheet(
            f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        box.addWidget(self._by_meal_label)
        row.addWidget(by_meal, 2)
        return panel

    def _stat_card(self, caption: str, color: str):
        card = _panel()
        card.setStyleSheet(
            f"QFrame {{ background:{_PANEL_BG}; border:1px solid {COLOR_BORDER};"
            f"border-right:4px solid {color}; border-radius:14px; }}")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(2)
        value = QLabel(_NO_RATINGS)
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

    def _build_week_menu(self) -> QWidget:
        """The week's whole menu in one editable table — the screen's point.

        You see every dish the week serves and fill in how many pupils gave
        each level, then save the week in one go.
        """
        panel = _panel()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        picker = QHBoxLayout()
        picker.setSpacing(10)
        picker.addWidget(self._caption(_LBL_WEEK))
        self._week_input = DateInput()
        self._week_input.setMinimumHeight(34)
        self._week_input.setMinimumWidth(150)
        self._week_input.setStyleSheet(_field_style())
        picker.addWidget(self._week_input)
        self._week_label = QLabel("")
        self._week_label.setStyleSheet(
            f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        picker.addWidget(self._week_label)
        picker.addStretch()
        self._by_edit = QLineEdit()
        self._by_edit.setMinimumHeight(34)
        self._by_edit.setMinimumWidth(190)
        self._by_edit.setPlaceholderText(_LBL_BY)
        self._by_edit.setStyleSheet(_field_style())
        picker.addWidget(self._by_edit)
        outer.addLayout(picker)

        # WHO is answering. Kept as two plain combos rather than one merged
        # list of six: the user picks a class group the way they think of it.
        group_row = QHBoxLayout()
        group_row.setSpacing(10)
        group_row.addWidget(self._caption(_LBL_CYCLE))
        self._cycle_combo = QComboBox()
        self._cycle_combo.addItem(_GROUP_ANY, UNSPECIFIED)
        active = set(visible_cycles())
        for code in CYCLES:
            if code not in active:
                continue
            self._cycle_combo.addItem(_CYCLE_LABELS[code], code)
        group_row.addWidget(self._cycle_combo)
        group_row.addWidget(self._caption(_LBL_GENDER))
        self._gender_combo = QComboBox()
        self._gender_combo.addItem(_GROUP_ANY, UNSPECIFIED)
        for code in GENDERS:
            self._gender_combo.addItem(_GENDER_LABELS[code], code)
        group_row.addWidget(self._gender_combo)
        for combo in (self._cycle_combo, self._gender_combo):
            combo.setMinimumHeight(34)
            combo.setMinimumWidth(130)
            # No stylesheet of its own: theme.py already gives every combo in
            # the app its drop-down zone and arrow, and overriding it here
            # silently removed the arrow.
            combo.currentIndexChanged.connect(self._render_week_menu)
        group_row.addStretch()
        outer.addLayout(group_row)

        hint = QLabel(_LBL_GROUP_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        outer.addWidget(hint)

        self._groups_label = QLabel("")
        self._groups_label.setWordWrap(True)
        self._groups_label.setStyleSheet(
            f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        outer.addWidget(self._groups_label)

        self._menu_table = QTableWidget(0, len(_MENU_HDR))
        self._menu_table.setHorizontalHeaderLabels(_MENU_HDR)
        self._menu_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._menu_table.verticalHeader().setVisible(False)
        self._menu_table.setAlternatingRowColors(True)
        self._menu_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._menu_table.setStyleSheet(_TABLE_STYLE)
        self._menu_table.setMinimumHeight(300)
        outer.addWidget(self._menu_table)

        buttons = QHBoxLayout()
        save_btn = IconButton(
            _BTN_SAVE, icon=_BTN_SAVE_ICON, bg=COLOR_ACCENT, min_height=38)
        save_btn.clicked.connect(self._on_save_week)
        buttons.addWidget(save_btn)
        buttons.addStretch()
        self._week_total_label = QLabel("")
        self._week_total_label.setStyleSheet(
            f"color:{COLOR_SUCCESS}; background:transparent; border:none;"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        buttons.addWidget(self._week_total_label)
        outer.addLayout(buttons)
        return panel

    def _build_rankings(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:transparent;")
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self._top_box, self._top_layout = self._ranking_panel(
            _LBL_TOP, COLOR_SUCCESS)
        self._bottom_box, self._bottom_layout = self._ranking_panel(
            _LBL_BOTTOM, COLOR_DANGER)
        row.addWidget(self._top_box, 1)
        row.addWidget(self._bottom_box, 1)
        return panel

    def _ranking_panel(self, title: str, color: str):
        box = _panel()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading_font = QFont()
        heading_font.setPointSize(FONT_LABEL)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color:{color}; background:transparent; border:none;")
        layout.addWidget(heading)
        hint = QLabel(_RANKING_HINT.format(minimum=MIN_RATINGS_FOR_RANKING))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        layout.addWidget(hint)
        entries = QVBoxLayout()
        entries.setSpacing(4)
        layout.addLayout(entries)
        return box, entries

    def _build_history(self) -> QWidget:
        """The OLD per-day records. Kept and shown separately at the user's
        request — nothing they typed before the week rewrite was thrown away."""
        panel = _panel()
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 14, 16, 16)
        box.setSpacing(8)

        heading = QLabel(_LBL_LEGACY)
        heading_font = QFont()
        heading_font.setPointSize(FONT_LABEL)
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;")
        box.addWidget(heading)
        hint = QLabel(_LBL_LEGACY_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px;")
        box.addWidget(hint)

        self._table = QTableWidget(0, len(_HDR))
        self._table.setHorizontalHeaderLabels(_HDR)
        self._table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Stretch)
        # Long values (the distribution, role names) elide badly at a fixed
        # width, so let those columns size to their content.
        for column in (0, 1, 3, 4, 5, 7):
            self._table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setMinimumHeight(240)
        self._table.setStyleSheet(f"""
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
        box.addWidget(self._table)
        return panel

    # ── Data ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Menus and the Ramadan period are edited elsewhere, so re-read."""
        self._reload()

    def _selected_week(self) -> str:
        """The Monday of whatever day is showing, so any day the user picks
        resolves to one canonical week."""
        return week_start_of(self._week_input.date().toString("yyyy-MM-dd"))

    def _reload(self) -> None:
        week = self._selected_week()
        self._week_records = get_week_feedback(week)
        self._all_weeks = get_all_week_feedback(_HISTORY_LIMIT)
        self._records = get_all_feedback(_HISTORY_LIMIT)   # the legacy per-day log
        self._week_label.setText(week_label(week))
        self._render_week_menu()
        self._render_summary()
        self._render_rankings()
        self._render_history()

    def _on_week_changed(self, _value: QDate) -> None:
        self._reload()

    def _all_opinions(self) -> List:
        """Week ratings AND the old per-day ones — both are opinions about the
        same dishes, so both feed the averages and the rankings."""
        return list(self._all_weeks) + list(self._records)

    def _render_week_menu(self) -> None:
        """One row per dish the week serves, with its five count boxes."""
        week = self._selected_week()
        cycle, gender = self._selected_group()
        dishes = dishes_for_week(week, get_school_settings())
        # Only THIS group's rows fill the boxes. Showing another group's counts
        # here would make the next save copy them onto the group on screen.
        mine = [record for record in self._week_records
                if record.cycle == cycle and record.gender == gender]
        saved = {record.dish: record for record in mine}
        # A dish rated earlier but no longer on the menu still deserves its row,
        # or its numbers would silently vanish from the screen that owns them.
        for record in mine:
            if record.dish not in dishes:
                dishes.append(record.dish)

        table = self._menu_table
        # clearContents() removes the cell WIDGETS too. Without it the previous
        # render's spinboxes stayed behind and every cell showed a ghost "0"
        # under its real value.
        table.clearContents()
        table.setRowCount(len(dishes))
        self._menu_spins = {}
        for row, dish in enumerate(dishes):
            table.setItem(row, 0, self._plain_cell(dish, bold=True))
            record = saved.get(dish)
            counts = response_counts(record) if record else {}
            spins = {}
            for column, level in enumerate(RATING_LEVELS, start=1):
                spin = QSpinBox()
                spin.setRange(0, 9999)
                spin.setValue(counts.get(level, 0))
                spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spin.setStyleSheet(_field_style())
                spin.valueChanged.connect(self._render_week_totals)
                spins[level] = spin
                table.setCellWidget(row, column, spin)
            self._menu_spins[dish] = spins
            table.setItem(row, 6, self._plain_cell(""))
            table.setItem(row, 7, self._plain_cell(""))
        # A fixed row height, not resizeRowsToContents(): the spinboxes are the
        # tallest thing in a row and measuring around them left dead space.
        table.verticalHeader().setDefaultSectionSize(_MENU_ROW_HEIGHT)
        self._render_week_totals()
        self._render_saved_groups()

    def _plain_cell(self, text: str, *, bold: bool = False,
                    color: str = COLOR_TEXT_PRIMARY) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if bold:
            font = QFont()
            font.setBold(True)
            item.setFont(font)
        if color != COLOR_TEXT_PRIMARY:
            item.setForeground(QColor(color))
        return item

    def _render_week_totals(self) -> None:
        """Per-dish responses and average, live as the counts are typed."""
        table = self._menu_table
        week_responses = 0
        week_sum = 0
        for row in range(table.rowCount()):
            dish_item = table.item(row, 0)
            if dish_item is None:
                continue
            spins = self._menu_spins.get(dish_item.text(), {})
            responses = sum(spin.value() for spin in spins.values())
            total = sum(level * spin.value() for level, spin in spins.items())
            week_responses += responses
            week_sum += total
            table.setItem(row, 6, self._plain_cell(
                f"{responses:,}" if responses else "—",
                color=COLOR_TEXT_PRIMARY if responses else COLOR_TEXT_SECONDARY))
            if responses:
                average = total / responses
                table.setItem(row, 7, self._plain_cell(
                    f"{average:.2f}", bold=True, color=_rating_color(average)))
            else:
                # No opinions is not a zero score.
                table.setItem(row, 7, self._plain_cell(
                    "—", color=COLOR_TEXT_SECONDARY))
        if week_responses:
            average = week_sum / week_responses
            self._week_total_label.setText(
                f"{_LBL_AVERAGE}: {average:.2f} / {RATING_MAX}  ·  "
                f"{week_responses:,} {_COUNT_SUFFIX}")
        else:
            self._week_total_label.setText(_MSG_NOTHING_ENTERED)

    def _on_save_week(self) -> None:
        week = self._selected_week()
        if not self._menu_spins:
            QMessageBox.information(self, _TITLE, _MSG_NO_DISHES)
            return
        saved = 0
        cycle, gender = self._selected_group()
        recorded_by = self._by_edit.text().strip()
        for dish, spins in self._menu_spins.items():
            counts = {level: spin.value() for level, spin in spins.items()}
            if not sum(counts.values()):
                continue
            existing = next(
                (r for r in self._week_records
                 if r.dish == dish and r.cycle == cycle and r.gender == gender),
                None)
            record = existing or WeekFeedback(
                week_start=week, dish=dish, cycle=cycle, gender=gender)
            record.recorded_by = recorded_by or record.recorded_by
            for level, field in COUNT_FIELDS.items():
                setattr(record, field, counts[level])
            save_week_feedback(record)
            saved += 1
        if not saved:
            QMessageBox.information(self, _TITLE, _MSG_NOTHING_ENTERED)
            return
        self._reload()
        QMessageBox.information(self, _TITLE, _MSG_SAVED.format(saved=saved))

    def _render_summary(self) -> None:
        opinions = self._all_opinions()
        average = overall_average(opinions)
        if average is None:
            self._avg_value.setText(_NO_RATINGS)
            self._avg_caption.setText(_NO_RATINGS_HINT)
        else:
            self._avg_value.setText(f"{average:.1f} / {RATING_MAX}")
            self._avg_caption.setText(f"{_LBL_AVERAGE} — {_stars(round(average))}")
        # RESPONSES, not rows: one saved row can carry a hundred opinions, and
        # "عدد التقييمات" meaning "number of times I pressed save" would be a
        # useless number.
        responses = sum(response_total(record) for record in opinions)
        self._count_value.setText(f"{responses:,}")
        self._count_caption.setText(
            f"{_LBL_COUNT} — {_LBL_COUNT_ROWS.format(rows=len(opinions))}")

        by_meal = average_by_meal_type(self._records)   # legacy rows only
        if not by_meal:
            self._by_meal_label.setText(_NO_RATINGS_HINT)
            return
        parts = [
            f"{MEAL_LABELS.get(meal, meal)}: {summary.average:.1f} "
            f"({summary.count} {_COUNT_SUFFIX})"
            for meal, summary in by_meal.items()
        ]
        self._by_meal_label.setText("    ·    ".join(parts))

    def _render_rankings(self) -> None:
        for layout, entries, color in (
            (self._top_layout, most_popular(self._all_opinions(), _TOP_LIMIT), COLOR_SUCCESS),
            (self._bottom_layout, least_popular(self._all_opinions(), _TOP_LIMIT), COLOR_DANGER),
        ):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            if not entries:
                label = QLabel(_NOT_ENOUGH)
                label.setStyleSheet(
                    f"color:{COLOR_TEXT_SECONDARY}; background:transparent;"
                    f"border:none; font-size:{FONT_CAPTION}px;")
                layout.addWidget(label)
                continue
            for summary in entries:
                layout.addWidget(self._ranking_row(summary, color))

    def _ranking_row(self, summary: DishSummary, color: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent; border:none;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        name = QLabel(summary.dish)
        name.setWordWrap(True)
        name.setStyleSheet(
            f"color:{COLOR_TEXT_PRIMARY}; background:transparent; border:none;"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        # The count is never dropped: an average without it is not a claim
        # anyone can weigh.
        score = QLabel(f"{summary.average:.1f}  ·  {summary.count} {_COUNT_SUFFIX}")
        score.setStyleSheet(
            f"color:{color}; background:{_tint(color)}; border-radius:7px;"
            f"padding:2px 10px; font-size:{FONT_CAPTION}px; font-weight:bold;")
        layout.addWidget(name, 1)
        layout.addWidget(score)
        return row

    def _render_history(self) -> None:
        self._table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            counts = response_counts(record)
            average = record_average(record)
            spread = " · ".join(
                f"{_RATING_LABELS[level]} {counts[level]}"
                for level in RATING_LEVELS if counts[level])
            values = [
                record.date,
                MEAL_LABELS.get(record.meal_type, record.meal_type),
                record.dish,
                spread or "—",
                f"{average:.2f}" if average is not None else "—",
                f"{response_total(record):,}",
                record.note,
                record.recorded_by,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                if column == 4 and average is not None:
                    item.setForeground(QColor(_rating_color(average)))
                self._table.setItem(row, column, item)
            button = QPushButton(_BTN_DELETE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{COLOR_DANGER};"
                f"border:1px solid {COLOR_DANGER}; border-radius:6px;"
                f"padding:2px 10px; font-size:{FONT_CAPTION}px; }}"
                f"QPushButton:hover {{ background:{COLOR_DANGER}; color:white; }}")
            button.clicked.connect(lambda _c, r=record: self._on_delete(r))
            self._table.setCellWidget(row, len(_HDR) - 1, button)

    # ── Actions ─────────────────────────────────────────────────────────────

    def _selected_group(self) -> tuple:
        """(cycle, gender) codes — both blank means an unclassified opinion."""
        return (self._cycle_combo.currentData() or UNSPECIFIED,
                self._gender_combo.currentData() or UNSPECIFIED)

    def _group_label(self, cycle: str, gender: str) -> str:
        parts = [_CYCLE_LABELS.get(cycle, ""), _GENDER_LABELS.get(gender, "")]
        named = " / ".join(part for part in parts if part)
        return named or _GROUP_ANY

    def _render_saved_groups(self) -> None:
        """What has already been collected this week, so the user can see which
        classes are still missing instead of re-typing one twice."""
        totals: Dict[tuple, int] = {}
        for record in self._week_records:
            key = (record.cycle, record.gender)
            totals[key] = totals.get(key, 0) + response_total(record)
        entries = [f"{self._group_label(*key)} ({count:,})"
                   for key, count in sorted(totals.items()) if count]
        self._groups_label.setText(
            f"{_LBL_GROUPS_SAVED} " + "  ·  ".join(entries) if entries
            else _LBL_GROUPS_NONE)

    def _week_dishes(self):
        """The dishes of the week on screen — what the sheets are printed for."""
        week = self._selected_week()
        dishes = dishes_for_week(week, get_school_settings())
        if not dishes:
            QMessageBox.information(self, _TITLE, _MSG_NO_DISHES)
            return None, week
        return dishes, week

    def _ask_path(self, title: str, default: str, filters: str,
                  suffix: str) -> Optional[Path]:
        path_str, _filter = QFileDialog.getSaveFileName(
            self, title, default, filters)
        if not path_str:
            return None
        path = Path(path_str)
        return path if path.suffix.lower() == suffix else path.with_suffix(suffix)

    def _on_tally_sheet(self) -> None:
        """The printed sheet someone carries into the refectory."""
        dishes, week = self._week_dishes()
        if not dishes:
            return
        path = self._ask_path(_TALLY_DIALOG_TITLE, _TALLY_DEFAULT_NAME,
                              _PDF_FILTER, ".pdf")
        if path is None:
            return
        try:
            write_tally_sheet_pdf(path, get_school_settings(), dishes, week,
                                  groups_to_collect(*self._selected_group()))
        except Exception:
            _LOGGER.exception("exporting the tally sheet failed")
            QMessageBox.critical(self, _TITLE, _MSG_EXPORT_FAILED)
            return
        QMessageBox.information(self, _TITLE, f"{_MSG_TALLY_SAVED}{path}")

    def _on_export_workbook(self) -> None:
        dishes, week = self._week_dishes()
        if not dishes:
            return
        path = self._ask_path(_XLSX_OUT_DIALOG_TITLE, _XLSX_DEFAULT_NAME,
                              _XLSX_FILTER, ".xlsx")
        if path is None:
            return
        try:
            write_feedback_workbook(path, dishes, week,
                                    groups_to_collect(*self._selected_group()))
        except Exception:
            _LOGGER.exception("exporting the feedback workbook failed")
            QMessageBox.critical(self, _TITLE, _MSG_EXPORT_FAILED)
            return
        QMessageBox.information(self, _TITLE, f"{_MSG_XLSX_SAVED}{path}")

    def _on_import_workbook(self) -> None:
        """Read a filled sheet back. Rows with no counts are skipped and
        reported, never stored as a meal nobody rated."""
        path_str, _filter = QFileDialog.getOpenFileName(
            self, _XLSX_IN_DIALOG_TITLE, "", _XLSX_FILTER)
        if not path_str:
            return
        try:
            saved, skipped, problems, week = import_feedback_workbook(Path(path_str))
        except Exception:
            _LOGGER.exception("importing the feedback workbook failed")
            QMessageBox.critical(self, _TITLE, _MSG_IMPORT_FAILED)
            return

        # Jump to the week the file belongs to, so the imported numbers are
        # the ones on screen afterwards.
        if week:
            year, month, day = (int(part) for part in week.split("-"))
            self._week_input.setDate(QDate(year, month, day))
        self._reload()
        if not saved and not problems:
            QMessageBox.information(self, _TITLE, _MSG_IMPORT_NONE)
            return
        message = _MSG_IMPORT_DONE.format(saved=saved)
        if skipped:
            message += _MSG_IMPORT_SKIPPED.format(skipped=skipped)
        if problems:
            shown = problems[:_IMPORT_PROBLEM_LIMIT]
            message += _MSG_IMPORT_PROBLEMS.format(problems="\n".join(shown))
            if len(problems) > _IMPORT_PROBLEM_LIMIT:
                message += f"\n… و{len(problems) - _IMPORT_PROBLEM_LIMIT} أخرى"
        QMessageBox.information(self, _TITLE, message)

    def _on_export(self) -> None:
        if not self._all_opinions():
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
        # The report covers whatever is on screen; say which dates that is
        # rather than implying it is the whole year.
        # The report covers BOTH the week ratings and the legacy per-day rows,
        # so its period must span whatever is actually included.
        opinions = self._all_opinions()
        stamps = sorted(getattr(r, "week_start", "") or getattr(r, "date", "")
                        for r in opinions)
        period = f"{stamps[0]} — {stamps[-1]}" if stamps else ""
        try:
            write_feedback_report_pdf(
                path, settings, opinions, period,
                students=get_all_students(), today=datetime.date.today())
        except Exception:
            _LOGGER.exception("exporting the feedback report failed")
            QMessageBox.critical(self, _TITLE, _MSG_EXPORT_FAILED)
            return
        QMessageBox.information(self, _TITLE, f"{_MSG_EXPORT_SAVED}{path}")

    def _on_delete(self, record: MealFeedback) -> None:
        if record.id is not None:
            delete_feedback(record.id)
        self._reload()
        QMessageBox.information(self, _TITLE, _MSG_DELETED)
