"""
src/ui/setup_steps.py
The setup wizard's optional data steps: the roster, the closed days, and the
first weekly menu.

Kept out of setup_wizard.py, which owns the shell (steps, navigation,
validation, saving the settings) and was already long before these existed.

EVERY step here is skippable and says so. Setup must never become a wall a
beginner cannot get past — a school with no Excel file to hand still has to
reach the app. Each step reports through `summary()` what it did, so the final
page can tell the user honestly what is set up and what is still empty.
"""
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_PANEL_ALT, COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_LABEL,
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA,
)
from core.models import Holiday, MealEntry
from ui.widgets.date_input import DateInput

# ── Arabic strings ──────────────────────────────────────────────────────────
_SKIP_NOTE = "هذه الخطوة اختيارية — يمكنك تخطيها والقيام بها لاحقاً من التطبيق."

_STUDENTS_TITLE = "لائحة التلاميذ"
_STUDENTS_HINT = ("استورد لائحة التلاميذ من ملف Excel. يمكنك أيضاً إضافتهم "
                  "يدوياً لاحقاً من شاشة لائحة التلاميذ.")
_BTN_PICK_FILE = "اختيار ملف Excel"
_BTN_TEMPLATE = "تحميل نموذج فارغ"
_TEMPLATE_HINT = ("ليس لديك ملف جاهز؟ حمّل النموذج، عبّئه بأسماء التلاميذ، ثم "
                  "استورده من هنا.")
_TEMPLATE_DEFAULT = "نموذج_التلاميذ.xlsx"
_TEMPLATE_DIALOG = "حفظ النموذج"
_TEMPLATE_DONE = "تم حفظ النموذج في:\n{path}"
_TEMPLATE_FAILED = "تعذر حفظ النموذج:\n{error}"
_STUDENTS_NONE = "لم يتم استيراد أي تلميذ بعد."
_STUDENTS_DONE = "تم استيراد {count} تلميذ."
_STUDENTS_BAD_FILE = "تعذرت قراءة الملف:\n{error}"
_STUDENTS_NO_LEVEL = ("{count} تلميذاً في هذا الملف بدون مستوى. يمكنك تحديد "
                      "مستواهم لاحقاً من شاشة لائحة التلاميذ.")

_HOLIDAYS_TITLE = "العطل وأيام الإغلاق"
_HOLIDAYS_HINT = ("سجّل العطل والأيام التي لا تُقدَّم فيها الوجبات، حتى يميّز "
                  "التطبيق بين يوم مغلق ويوم نُسي إدخال بياناته.")
_LBL_FROM = "من"
_LBL_TO = "إلى"
_LBL_LABEL = "السبب"
_HOLIDAY_PLACEHOLDER = "مثال: عطلة نصف السنة"
_BTN_ADD_HOLIDAY = "إضافة"
_BTN_REMOVE = "حذف المحدد"
_HOLIDAYS_NONE = "لم تُسجَّل أي عطلة بعد."
_HOLIDAYS_COUNT = "{count} يوماً مسجَّلاً."
_HOLIDAY_BAD_RANGE = "تاريخ النهاية قبل تاريخ البداية."
_HOLIDAY_TOO_LONG = "المدة أطول من {days} يوماً — تأكد من التاريخين."
_HOLIDAY_LABEL_REQUIRED = "اكتب سبب العطلة."

_PROGRAM_TITLE = "البرنامج الغذائي الأسبوعي"
_PROGRAM_HINT = ("اكتب قائمة الأسبوع. يمكنك تركها فارغة وملؤها لاحقاً من شاشة "
                 "البرنامج الغذائي.")
_LBL_PROGRAM_NAME = "اسم البرنامج"
_PROGRAM_DEFAULT_NAME = "البرنامج الأسبوعي"
_PROGRAM_NONE = "لم يُنشأ برنامج غذائي."
_PROGRAM_DONE = "تم إنشاء برنامج بـ {count} وجبة."

_WEEK_DAYS: List[Tuple[int, str]] = [
    (2, "الإثنين"), (3, "الثلاثاء"), (4, "الأربعاء"),
    (5, "الخميس"), (6, "الجمعة"),
]
_MEALS: List[Tuple[str, str]] = [
    (MEAL_FTOUR, "الفطور"), (MEAL_GHADA, "الغذاء"), (MEAL_ASHA, "العشاء"),
]

# A holiday range longer than this is almost certainly a mistyped year.
_MAX_HOLIDAY_DAYS = 120


def _field(placeholder: str = "") -> QLineEdit:
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    field.setMinimumHeight(34)
    field.setStyleSheet(
        f"background:white; color:{COLOR_TEXT_PRIMARY};"
        f"border:1px solid {COLOR_BORDER}; border-radius:8px;"
        f"padding:4px 10px; font-size:{FONT_BODY}px;")
    return field


def _hint(text: str, color: str = COLOR_TEXT_SECONDARY) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(
        f"background:transparent; border:none; color:{color};"
        f"font-size:{FONT_CAPTION}px;")
    return label


def _button(text: str, *, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setMinimumHeight(34)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    background = COLOR_ACCENT if primary else "white"
    colour = "white" if primary else COLOR_TEXT_PRIMARY
    button.setStyleSheet(
        f"QPushButton {{ background:{background}; color:{colour};"
        f" border:1px solid {COLOR_BORDER if not primary else COLOR_ACCENT};"
        f" border-radius:8px; padding:6px 16px; font-size:{FONT_BODY}px;"
        " font-weight:bold; }"
        f"QPushButton:hover {{ background:{COLOR_PANEL_ALT if not primary else COLOR_ACCENT}; }}")
    return button


class _StepBase(QWidget):
    """Shared shell: a title, a hint, the skippable note, and a status line."""

    def __init__(self, title: str, hint: str) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        heading = QLabel(title)
        heading.setStyleSheet(
            f"background:transparent; color:{COLOR_TEXT_PRIMARY};"
            f"font-size:{FONT_LABEL + 2}px; font-weight:bold;")
        self._layout.addWidget(heading)
        self._layout.addWidget(_hint(hint))
        self._layout.addWidget(_hint(_SKIP_NOTE, COLOR_ACCENT))

        self._status = _hint("")
        self._body = QVBoxLayout()
        self._body.setSpacing(10)
        self._layout.addLayout(self._body)
        self._layout.addWidget(self._status)
        self._layout.addStretch()

    def _set_status(self, text: str, colour: str = COLOR_TEXT_SECONDARY) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(
            f"background:transparent; border:none; color:{colour};"
            f"font-size:{FONT_CAPTION}px; font-weight:bold;")

    def save(self) -> None:
        """Persist whatever the step gathered. Steps that write as they go
        override nothing."""

    def summary(self) -> str:
        raise NotImplementedError


class StudentsStep(_StepBase):
    """Import the roster from Excel — the same reader لائحة التلاميذ uses.

    Pupils are written to the database as soon as the file is read, not held
    until the wizard finishes: if setup is abandoned halfway the roster is
    still there, which is the outcome the user would want either way.
    """

    def __init__(self) -> None:
        super().__init__(_STUDENTS_TITLE, _STUDENTS_HINT)
        self._imported = 0

        # The template comes FIRST: a user with no file yet cannot act on an
        # import button, and until now the wizard gave them no way to find out
        # what columns the file needs.
        self._body.addWidget(_hint(_TEMPLATE_HINT))
        row = QHBoxLayout()
        row.setSpacing(8)
        template = _button(_BTN_TEMPLATE)
        template.clicked.connect(self._on_template)
        row.addWidget(template)
        pick = _button(_BTN_PICK_FILE, primary=True)
        pick.clicked.connect(self._on_pick)
        row.addWidget(pick)
        row.addStretch()
        self._body.addLayout(row)
        self._set_status(_STUDENTS_NONE)

    def _on_template(self) -> None:
        """The same blank workbook لائحة التلاميذ hands out — one file format
        for both routes, so a template filled in here imports there too."""
        from core.excel_handler import write_students_template
        from ui.students_screen import _filtered_level_catalog

        path_str, _filter = QFileDialog.getSaveFileName(
            self, _TEMPLATE_DIALOG, _TEMPLATE_DEFAULT, "Excel (*.xlsx)")
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        try:
            write_students_template(path, _filtered_level_catalog())
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.critical(self, _STUDENTS_TITLE,
                                 _TEMPLATE_FAILED.format(error=exc))
            return
        QMessageBox.information(self, _STUDENTS_TITLE,
                                _TEMPLATE_DONE.format(path=path))

    def _on_pick(self) -> None:
        path_str, _filter = QFileDialog.getOpenFileName(
            self, _BTN_PICK_FILE, "", "Excel (*.xlsx *.xls)")
        if not path_str:
            return
        from core.excel_handler import read_students_from_excel
        from data.database import add_students_bulk

        try:
            students = read_students_from_excel(Path(path_str))
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.warning(self, _STUDENTS_TITLE,
                                _STUDENTS_BAD_FILE.format(error=exc))
            return
        try:
            count = add_students_bulk(students)
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.critical(self, _STUDENTS_TITLE,
                                 _STUDENTS_BAD_FILE.format(error=exc))
            return

        self._imported += count
        self._set_status(_STUDENTS_DONE.format(count=self._imported),
                         COLOR_SUCCESS)
        # Said plainly rather than guessed at: the level picker on
        # لائحة التلاميذ is where a missing المستوى gets filled in.
        missing = [s for s in students if not (s.student_class or "").strip()]
        if missing:
            QMessageBox.information(
                self, _STUDENTS_TITLE,
                _STUDENTS_NO_LEVEL.format(count=len(missing)))

    def summary(self) -> str:
        return (_STUDENTS_DONE.format(count=self._imported)
                if self._imported else _STUDENTS_NONE)


class HolidaysStep(_StepBase):
    """Days the refectory is closed, entered as ranges.

    Stored one row per date (the Holiday model's own shape), so a range typed
    here and a single day added later from the app are the same thing.
    """

    def __init__(self) -> None:
        super().__init__(_HOLIDAYS_TITLE, _HOLIDAYS_HINT)
        self._added: Dict[str, str] = {}

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_hint(_LBL_FROM))
        self._from = DateInput()
        self._from.setMinimumHeight(34)
        row.addWidget(self._from)
        row.addWidget(_hint(_LBL_TO))
        self._to = DateInput()
        self._to.setMinimumHeight(34)
        row.addWidget(self._to)
        self._label = _field(_HOLIDAY_PLACEHOLDER)
        row.addWidget(self._label, 1)
        add = _button(_BTN_ADD_HOLIDAY, primary=True)
        add.clicked.connect(self._on_add)
        row.addWidget(add)
        self._body.addLayout(row)

        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        self._list.setStyleSheet(
            f"QListWidget {{ background:white; border:1px solid {COLOR_BORDER};"
            f" border-radius:8px; font-size:{FONT_CAPTION}px; }}")
        self._body.addWidget(self._list)

        remove_row = QHBoxLayout()
        remove = _button(_BTN_REMOVE)
        remove.clicked.connect(self._on_remove)
        remove_row.addWidget(remove)
        remove_row.addStretch()
        self._body.addLayout(remove_row)
        self._set_status(_HOLIDAYS_NONE)

    def _on_add(self) -> None:
        start = self._from.date().toPython()
        end = self._to.date().toPython()
        label = self._label.text().strip()
        if end < start:
            QMessageBox.warning(self, _HOLIDAYS_TITLE, _HOLIDAY_BAD_RANGE)
            return
        # A mistyped year turns a week into a decade; refuse rather than
        # silently writing thousands of rows.
        if (end - start).days > _MAX_HOLIDAY_DAYS:
            QMessageBox.warning(
                self, _HOLIDAYS_TITLE,
                _HOLIDAY_TOO_LONG.format(days=_MAX_HOLIDAY_DAYS))
            return
        if not label:
            QMessageBox.warning(self, _HOLIDAYS_TITLE,
                                _HOLIDAY_LABEL_REQUIRED)
            return

        day = start
        while day <= end:
            self._added[day.isoformat()] = label
            day += datetime.timedelta(days=1)
        self._label.clear()
        self._refresh_list()

    def _on_remove(self) -> None:
        for item in self._list.selectedItems():
            self._added.pop(item.data(Qt.ItemDataRole.UserRole), None)
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.clear()
        for date_str, label in sorted(self._added.items()):
            self._list.addItem(f"{date_str}  —  {label}")
            self._list.item(self._list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, date_str)
        self._set_status(
            _HOLIDAYS_COUNT.format(count=len(self._added))
            if self._added else _HOLIDAYS_NONE,
            COLOR_SUCCESS if self._added else COLOR_TEXT_SECONDARY)

    def save(self) -> None:
        from data.database import add_holiday

        for date_str, label in self._added.items():
            add_holiday(Holiday(date=date_str, label=label))

    def summary(self) -> str:
        return (_HOLIDAYS_COUNT.format(count=len(self._added))
                if self._added else _HOLIDAYS_NONE)


class MealProgramStep(_StepBase):
    """The first weekly menu — five weekdays against the three normal meals.

    Only the lines actually typed are saved: an empty slot means the school
    does not serve that meal that day, not an empty meal.
    """

    def __init__(self, school_year: str = "") -> None:
        super().__init__(_PROGRAM_TITLE, _PROGRAM_HINT)
        self._school_year = school_year
        self._created = 0

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(_hint(_LBL_PROGRAM_NAME))
        self._name = _field(_PROGRAM_DEFAULT_NAME)
        self._name.setText(_PROGRAM_DEFAULT_NAME)
        name_row.addWidget(self._name, 1)
        self._body.addLayout(name_row)

        grid = QGridLayout()
        grid.setSpacing(6)
        for column, (_meal, meal_label) in enumerate(_MEALS, start=1):
            header = QLabel(meal_label)
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header.setStyleSheet(
                f"background:transparent; color:{COLOR_TEXT_PRIMARY};"
                f"font-size:{FONT_CAPTION}px; font-weight:bold;")
            grid.addWidget(header, 0, column)

        self._cells: Dict[Tuple[int, str], QLineEdit] = {}
        for row, (day_index, day_label) in enumerate(_WEEK_DAYS, start=1):
            name = QLabel(day_label)
            name.setStyleSheet(
                f"background:transparent; color:{COLOR_TEXT_PRIMARY};"
                f"font-size:{FONT_CAPTION}px; font-weight:bold;")
            grid.addWidget(name, row, 0)
            for column, (meal_key, _label) in enumerate(_MEALS, start=1):
                cell = _field("")
                self._cells[(day_index, meal_key)] = cell
                grid.addWidget(cell, row, column)
        self._body.addLayout(grid)
        self._set_status(_PROGRAM_NONE)

    def _entries(self) -> List[Tuple[int, str, str]]:
        return [(day, meal, cell.text().strip())
                for (day, meal), cell in self._cells.items()
                if cell.text().strip()]

    def save(self) -> None:
        from data.database import create_program, save_program_entries

        typed = self._entries()
        if not typed:
            return                      # nothing typed is not an empty program
        program_id = create_program(
            self._name.text().strip() or _PROGRAM_DEFAULT_NAME,
            self._school_year, False)
        save_program_entries(program_id, [
            MealEntry(program_id=program_id, day_of_week=day,
                      meal_type=meal, menu_text=text)
            for day, meal, text in typed
        ])
        self._created = len(typed)

    def summary(self) -> str:
        typed = self._entries()
        return (_PROGRAM_DONE.format(count=len(typed)) if typed
                else _PROGRAM_NONE)

    def set_school_year(self, school_year: str) -> None:
        """Stamped from the wizard once the identity page is saved."""
        self._school_year = school_year
