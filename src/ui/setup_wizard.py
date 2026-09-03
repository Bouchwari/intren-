"""
src/ui/setup_wizard.py
Two-page first-run wizard matching the official Moroccan school form layout.
Page 1: institution identity + staff names
Page 2: supplier contract + meal prices
"""
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget, QScrollArea, QFrame
)

from config.settings import (
    APP_NAME,
    COLOR_ACCENT, COLOR_BORDER, COLOR_PANEL_ALT, COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.excel_handler import load_level_catalog
from ui.widgets.date_input import DateInput
from core.models import SchoolSettings
from data.database import save_level_preferences, save_school_settings

# ── Arabic UI strings ─────────────────────────────────────────────────────────
_TITLE_P1      = "المؤسسة التعليمية"
_TITLE_P2      = "صفقة المطعمة"

# (title, subtitle, optional). An optional step can be skipped outright — the
# app must be reachable by a school that has no Excel file to hand.
_STEPS: list[tuple[str, str, bool]] = [
    ("المؤسسة", "معلومات المؤسسة وأطرها", False),
    ("الصفقة", "المورد وأثمان الوجبات ومدة رمضان", False),
    ("التلاميذ", "استيراد لائحة التلاميذ", True),
    ("العطل", "الأيام التي لا تُقدَّم فيها وجبات", True),
    ("البرنامج", "قائمة الأسبوع", True),
    ("تم", "ملخص ما تم إعداده", False),
]
_SUBTITLE_FMT  = "الخطوة {number} من {total} — {subtitle}"
_GRP_INST      = "المؤسسة التعليمية"
_GRP_STAFF     = "أطر المؤسسة"
_GRP_CONTRACT  = "الصفقة"
_GRP_PRICES    = "أثمان الوجبات"
_GRP_LEVELS    = "المستويات المستعملة"
_GRP_RAMADAN   = "مدة رمضان"
_LBL_RAMADAN_ENABLE = "مؤسستي تقدّم وجبات رمضان (إفطار وسحور)"
_MSG_RAMADAN_NOTE = ("خلال هذه المدة تتحول وثائق اليوم تلقائياً إلى وجبتي "
                     "الإفطار والسحور بدل الفطور والغداء والعشاء. اتركها فارغة "
                     "إن لم تكن تعرف التواريخ بعد — يمكن ضبطها من الإعدادات.")
_MSG_BAD_PRICE = ("«{label}» ليس رقماً صالحاً. اكتب الثمن بالأرقام مع نقطة "
                  "عشرية، مثال: 12.50")
_MSG_BAD_RAMADAN = "تاريخ نهاية رمضان قبل تاريخ بدايته."
_BTN_NEXT      = "التالي  ←"
_BTN_BACK      = "→  السابق"
_BTN_SAVE      = "💾  حفظ والانطلاق"
_BTN_SKIP      = "تخطي هذه الخطوة"
_BTN_FINISH    = "🚀  انطلاق"
_DONE_TITLE    = "تم إعداد التطبيق"
_DONE_HINT     = ("هذا ما تم حفظه. كل ما تُرك فارغاً يمكن إكماله في أي وقت من "
                  "داخل التطبيق.")
_DONE_SETTINGS = "بيانات المؤسسة والصفقة: محفوظة."
_DONE_RAMADAN  = "مدة رمضان: {start} إلى {end}."
_DONE_NO_RAMADAN = "مدة رمضان: لم تُحدَّد."
_MSG_REQUIRED  = "الرجاء تعبئة الحقول الإلزامية (*):\n• اسم المؤسسة\n• السنة الدراسية\n• اسم المدير"


def _line(placeholder: str = "") -> QLineEdit:
    """Helper — create a styled QLineEdit."""
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(38)
    w.setStyleSheet(
        f"background: white; color: {COLOR_TEXT_PRIMARY};"
        f"border: 1px solid {COLOR_BORDER}; border-radius: 6px;"
        f"padding: 4px 12px; font-size: {FONT_BODY}px;"
    )
    return w


def _group(title: str) -> tuple[QGroupBox, QFormLayout]:
    """Helper — create a styled QGroupBox with a QFormLayout inside."""
    box = QGroupBox(title)
    box.setStyleSheet(f"""
        QGroupBox {{
            font-weight: bold; font-size: {FONT_SECTION}px;
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            border-radius: 8px; margin-top: 14px; padding: 14px;
            background: white;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top right;
            padding: 0 8px; right: 14px;
            background: {COLOR_PANEL_ALT};
        }}
        QLabel {{
            color: {COLOR_TEXT_PRIMARY};
            font-weight: normal;
        }}
    """)
    form = QFormLayout(box)
    form.setSpacing(12)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return box, form


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = (value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


class SetupWizard(QDialog):
    """Modal two-page setup wizard — shown once on first launch."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"الإعداد الأولي — {APP_NAME}")
        self.setMinimumWidth(680)
        self.setMinimumHeight(650)
        self.resize(680, 700)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._build_ui()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Header bar
        root.addWidget(self._build_header())

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_page1())
        self._stack.addWidget(self._build_page2())

        # The optional data steps live in ui/setup_steps.py — each writes its
        # own data and reports back for the summary page.
        from ui.setup_steps import HolidaysStep, MealProgramStep, StudentsStep
        self._students_step = StudentsStep()
        self._holidays_step = HolidaysStep()
        self._program_step = MealProgramStep()
        self._optional_steps = [self._students_step, self._holidays_step,
                                self._program_step]
        for step in self._optional_steps:
            self._stack.addWidget(self._wrap_step(step))
        self._stack.addWidget(self._build_done_page())
        root.addWidget(self._stack, 1)

        # Footer nav
        root.addWidget(self._build_footer())
        self._show_step(0)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(f"background-color: {COLOR_ACCENT};")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(24, 16, 24, 16)

        self._title_lbl = QLabel(_TITLE_P1)
        f = QFont(); f.setPointSize(15); f.setBold(True)
        self._title_lbl.setFont(f)
        self._title_lbl.setStyleSheet("color: white;")

        self._sub_lbl = QLabel("")
        self._sub_lbl.setStyleSheet(
            f"color: rgba(255,255,255,0.85); font-size: {FONT_LABEL}px;")

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._sub_lbl)
        layout.addSpacing(6)
        layout.addLayout(self._build_step_indicator())
        return header

    def _build_step_indicator(self) -> QHBoxLayout:
        """A chip per step, so the user can see how much is left rather than
        reading it off one line of small text."""
        row = QHBoxLayout()
        row.setSpacing(6)
        self._step_chips: list[QLabel] = []
        for number, (name, _subtitle, _optional) in enumerate(_STEPS, start=1):
            chip = QLabel(f"{number}. {name}")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_chips.append(chip)
            row.addWidget(chip)
        return row

    def _refresh_indicator(self) -> None:
        current = self._stack.currentIndex()
        for index, chip in enumerate(self._step_chips):
            if index < current:
                # done
                background, colour = "rgba(255,255,255,0.30)", "white"
            elif index == current:
                background, colour = "white", COLOR_ACCENT
            else:
                background, colour = "rgba(255,255,255,0.12)", "rgba(255,255,255,0.75)"
            chip.setStyleSheet(
                f"background:{background}; color:{colour}; border-radius:9px;"
                f"padding:3px 8px; font-size:{FONT_CAPTION}px; font-weight:bold;")

    def _wrap_step(self, step: QWidget) -> QWidget:
        """Give an optional step the same scrolled, padded page shell as the
        two form pages."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {COLOR_SURFACE}; border: none; }}")
        page = QWidget()
        page.setObjectName("WizardPage")
        page.setStyleSheet(f"#WizardPage {{ background: {COLOR_SURFACE}; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(step)
        scroll.setWidget(page)
        return scroll

    def _build_done_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {COLOR_SURFACE}; border: none; }}")
        page = QWidget()
        page.setObjectName("WizardPage")
        page.setStyleSheet(f"#WizardPage {{ background: {COLOR_SURFACE}; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        heading = QLabel(_DONE_TITLE)
        heading_font = QFont(); heading_font.setPointSize(14); heading_font.setBold(True)
        heading.setFont(heading_font)
        heading.setStyleSheet(f"color:{COLOR_TEXT_PRIMARY};")
        layout.addWidget(heading)

        note = QLabel(_DONE_HINT)
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        layout.addWidget(note)

        self._done_list = QVBoxLayout()
        self._done_list.setSpacing(6)
        layout.addLayout(self._done_list)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _refresh_done_page(self) -> None:
        """Say what was saved AND what was left empty — a summary that only
        lists successes would hide the gaps the user still has to fill."""
        while self._done_list.count():
            item = self._done_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        lines = [_DONE_SETTINGS]
        start, end = self._ramadan_period()
        lines.append(_DONE_RAMADAN.format(start=start, end=end)
                     if start and end else _DONE_NO_RAMADAN)
        lines.extend(step.summary() for step in self._optional_steps)
        for text in lines:
            label = QLabel(f"•  {text}")
            label.setWordWrap(True)
            label.setStyleSheet(
                f"color:{COLOR_TEXT_PRIMARY}; font-size:{FONT_BODY}px;")
            self._done_list.addWidget(label)

    def _build_page1(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {COLOR_SURFACE}; border: none; }}")

        page = QWidget()
        page.setObjectName("WizardPage")
        page.setStyleSheet(f"#WizardPage {{ background: {COLOR_SURFACE}; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Group: institution
        grp_inst, form_inst = _group(_GRP_INST)

        self._school_name    = _line("اسم المؤسسة بالعربية")
        self._school_name_fr = _line("Nom d'établissement")
        self._aref           = _line("مثال: جهة الرباط سلا القنيطرة")
        self._dir_prov       = _line("مثال: مديرية سلا")
        self._city           = _line("مثال: سلا")
        self._city_fr        = _line("Nom de la ville")
        self._school_year    = _line("مثال: 2024-2025")

        form_inst.addRow("اسم المؤسسة *",            self._school_name)
        form_inst.addRow("Nom d'établissement",       self._school_name_fr)
        form_inst.addRow("الأكاديمية الجهوية (AREF)", self._aref)
        form_inst.addRow("المديرية الإقليمية",        self._dir_prov)
        form_inst.addRow("الجماعة",                   self._city)
        form_inst.addRow("Nom de la ville",           self._city_fr)
        form_inst.addRow("السنة الدراسية *",          self._school_year)

        # Group: staff
        grp_staff, form_staff = _group(_GRP_STAFF)

        self._director        = _line("الاسم الكامل للمدير")
        self._gestionnaire    = _line("مسير المصالح المادية والمالية")

        form_staff.addRow("اسم مدير المؤسسة *",                    self._director)
        form_staff.addRow("اسم مسير المصالح المادية والمالية",     self._gestionnaire)

        layout.addWidget(grp_inst)
        layout.addWidget(grp_staff)
        layout.addStretch()
        
        scroll.setWidget(page)
        return scroll

    def _build_page2(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {COLOR_SURFACE}; border: none; }}")

        page = QWidget()
        page.setObjectName("WizardPage")
        page.setStyleSheet(f"#WizardPage {{ background: {COLOR_SURFACE}; }}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Group: contract
        grp_contract, form_c = _group(_GRP_CONTRACT)

        self._contract_number  = _line("رقم الصفقة")
        self._company_name     = _line("Raison sociale")
        self._supplier_address = _line("العنوان / Adresse")

        form_c.addRow("رقم الصفقة",       self._contract_number)
        form_c.addRow("اسم الشركة",       self._company_name)
        form_c.addRow("العنوان",          self._supplier_address)

        # Group: prices. The three RAMADAN price fields that used to sit here
        # were removed 2026-08-29 — the user dropped Ramadan pricing, nothing
        # in the app reads them, and a first-run wizard should not ask for
        # three numbers that do nothing.
        grp_prices, price_form = _group(_GRP_PRICES)
        self._price_ftour = _line("0.00")
        self._price_ghada = _line("0.00")
        self._price_asha  = _line("0.00")
        price_form.addRow("ثمن وجبة الفطور", self._price_ftour)
        price_form.addRow("ثمن وجبة الغداء", self._price_ghada)
        price_form.addRow("ثمن وجبة العشاء", self._price_asha)

        # Group: the Ramadan PERIOD, which every document actually reads to
        # decide whether a day serves إفطار/سحور instead of the three meals.
        grp_ramadan, ramadan_form = _group(_GRP_RAMADAN)
        self._ramadan_start = DateInput()
        self._ramadan_end = DateInput()
        for field in (self._ramadan_start, self._ramadan_end):
            field.setMinimumHeight(38)
        self._ramadan_enabled = QCheckBox(_LBL_RAMADAN_ENABLE)
        self._ramadan_enabled.toggled.connect(self._on_ramadan_toggled)
        ramadan_form.addRow(self._ramadan_enabled)
        ramadan_form.addRow("بداية رمضان", self._ramadan_start)
        ramadan_form.addRow("نهاية رمضان", self._ramadan_end)
        ramadan_note = QLabel(_MSG_RAMADAN_NOTE)
        ramadan_note.setWordWrap(True)
        ramadan_note.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        ramadan_form.addRow(ramadan_note)
        self._on_ramadan_toggled(False)

        note = QLabel("* يمكن تعديل هذه المعلومات لاحقاً من صفحة الإعدادات")
        note.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: {FONT_CAPTION}px;")

        layout.addWidget(grp_contract)
        layout.addWidget(grp_prices)
        layout.addWidget(grp_ramadan)
        levels_group = self._build_levels_section()
        if levels_group is not None:
            layout.addWidget(levels_group)
        layout.addWidget(note)
        layout.addStretch()

        scroll.setWidget(page)
        return scroll

    def _build_levels_section(self) -> QGroupBox | None:
        catalog = load_level_catalog()
        if not catalog:
            self._cycle_checks = {}
            self._type_checks = {}
            return None

        grp = QGroupBox(_GRP_LEVELS)
        grp.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold; font-size: {FONT_SECTION}px;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px; margin-top: 14px; padding: 14px;
                background: white;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top right;
                padding: 0 8px; right: 14px;
                background: {COLOR_PANEL_ALT};
            }}
            QLabel {{
                color: {COLOR_TEXT_SECONDARY};
                font-weight: normal;
            }}
            QCheckBox {{
                color: {COLOR_TEXT_PRIMARY};
                spacing: 10px;
                padding: 4px 2px;
                font-weight: normal;
            }}
        """)
        layout = QVBoxLayout(grp)
        layout.setSpacing(12)

        note = QLabel("اختر فقط الأسلاك وأنواع التعليم الموجودة في مؤسستك. هذا يجعل لائحة التلاميذ والنموذج أقصر وأسهل.")
        note.setWordWrap(True)
        layout.addWidget(note)

        columns = QHBoxLayout()
        cycle_box = QGroupBox("السلك")
        type_box = QGroupBox("نوع التعليم")
        for box in (cycle_box, type_box):
            box.setStyleSheet(
                f"QGroupBox {{ background:{COLOR_PANEL_ALT}; border:1px solid {COLOR_BORDER};"
                "border-radius:8px; margin-top:10px; padding:10px; }}"
                "QGroupBox::title { padding:0 6px; right:10px; }"
                "QCheckBox { spacing:10px; padding:5px 2px; }"
            )

        self._cycle_checks: dict[str, QCheckBox] = {}
        self._type_checks: dict[str, QCheckBox] = {}
        cycle_grid = QGridLayout(cycle_box)
        type_grid = QGridLayout(type_box)

        for index, label in enumerate(_unique([option.cycle_label for option in catalog])):
            check = QCheckBox(label)
            check.setChecked(True)
            self._cycle_checks[label] = check
            cycle_grid.addWidget(check, index // 2, index % 2)

        for index, label in enumerate(_unique([option.education_type for option in catalog])):
            check = QCheckBox(label)
            check.setChecked(True)
            self._type_checks[label] = check
            type_grid.addWidget(check, index // 2, index % 2)

        columns.addWidget(cycle_box)
        columns.addWidget(type_box)
        layout.addLayout(columns)
        return grp

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setStyleSheet(f"background: white; border-top: 1px solid {COLOR_BORDER};")
        row = QHBoxLayout(footer)
        row.setContentsMargins(24, 12, 24, 12)

        self._back_btn = QPushButton(_BTN_BACK)
        self._back_btn.setMinimumHeight(38)
        self._back_btn.setVisible(False)
        self._back_btn.setStyleSheet(
            f"background: {COLOR_PANEL_ALT}; color: {COLOR_TEXT_PRIMARY};"
            f"border-radius: 6px; padding: 0 18px; font-size: {FONT_BODY}px;"
        )
        self._back_btn.clicked.connect(self._go_back)

        self._next_btn = QPushButton(_BTN_NEXT)
        self._next_btn.setMinimumHeight(38)
        self._next_btn.setStyleSheet(
            f"background: {COLOR_ACCENT}; color: white;"
            f"border-radius: 6px; padding: 0 18px; font-size: {FONT_BODY}px; font-weight: bold;"
        )
        self._next_btn.clicked.connect(self._go_next)

        self._skip_btn = QPushButton(_BTN_SKIP)
        self._skip_btn.setMinimumHeight(38)
        self._skip_btn.setVisible(False)
        self._skip_btn.setStyleSheet(
            f"background: transparent; color: {COLOR_TEXT_SECONDARY};"
            f"border: 1px solid {COLOR_BORDER}; border-radius: 6px;"
            f"padding: 0 18px; font-size: {FONT_BODY}px;")
        self._skip_btn.clicked.connect(self._on_skip)

        row.addWidget(self._back_btn)
        row.addStretch()
        row.addWidget(self._skip_btn)
        row.addWidget(self._next_btn)
        return footer

    # ── Navigation ─────────────────────────────────────────────────────────

    def _go_next(self) -> None:
        index = self._stack.currentIndex()
        if index == 0:
            if not self._validate_page1():
                return
        elif index == 1:
            # Settings are written HERE, not at the very end: the steps that
            # follow are all optional, and a user who closes the window on one
            # of them should still keep the identity they typed.
            if not self._save_settings():
                return
        elif index == len(_STEPS) - 1:
            self.accept()
            return
        else:
            if not self._commit_step(index):
                return
        self._show_step(index + 1)

    def _on_skip(self) -> None:
        """Move on without saving this step's data — it is optional and says
        so on the page itself."""
        self._show_step(self._stack.currentIndex() + 1)

    def _go_back(self) -> None:
        self._show_step(max(0, self._stack.currentIndex() - 1))

    def _commit_step(self, index: int) -> bool:
        step = self._optional_steps[index - 2]
        try:
            step.save()
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")
            return False
        return True

    def _show_step(self, index: int) -> None:
        index = max(0, min(index, len(_STEPS) - 1))
        self._stack.setCurrentIndex(index)
        name, subtitle, optional = _STEPS[index]
        self._title_lbl.setText(name)
        self._sub_lbl.setText(_SUBTITLE_FMT.format(
            number=index + 1, total=len(_STEPS), subtitle=subtitle))
        self._back_btn.setVisible(index > 0)
        self._skip_btn.setVisible(optional)
        last = index == len(_STEPS) - 1
        self._next_btn.setText(_BTN_FINISH if last else _BTN_NEXT)
        if last:
            self._refresh_done_page()
        self._refresh_indicator()

    # ── Validation & save ──────────────────────────────────────────────────

    def _on_ramadan_toggled(self, enabled: bool) -> None:
        """The dates only mean anything when the school serves Ramadan meals;
        greyed out they cannot be filled in by accident and then saved."""
        for field in (self._ramadan_start, self._ramadan_end):
            field.setEnabled(enabled)

    def _ramadan_period(self) -> tuple:
        """(start, end) as ISO strings — both blank unless the box is ticked,
        so an untouched wizard never writes a Ramadan period nobody meant."""
        if not self._ramadan_enabled.isChecked():
            return "", ""
        return (self._ramadan_start.date().toString("yyyy-MM-dd"),
                self._ramadan_end.date().toString("yyyy-MM-dd"))

    def _validate_prices(self) -> bool:
        """A price that is not a number would be read as 0.00 by every cost
        figure in the app, silently. Caught here instead."""
        for field, label in ((self._price_ftour, "ثمن وجبة الفطور"),
                             (self._price_ghada, "ثمن وجبة الغداء"),
                             (self._price_asha, "ثمن وجبة العشاء")):
            text = field.text().strip()
            if not text:
                continue                 # blank is allowed; nonsense is not
            try:
                float(text)
            except ValueError:
                QMessageBox.warning(self, "قيمة غير صالحة",
                                    _MSG_BAD_PRICE.format(label=label))
                field.setFocus()
                return False

        start, end = self._ramadan_period()
        if start and end and end < start:
            QMessageBox.warning(self, "تواريخ غير صالحة", _MSG_BAD_RAMADAN)
            return False
        return True

    def _validate_page1(self) -> bool:
        missing = (
            not self._school_name.text().strip() or
            not self._school_year.text().strip() or
            not self._director.text().strip()
        )
        if missing:
            QMessageBox.warning(self, "حقول مطلوبة", _MSG_REQUIRED)
        return not missing

    def _save_settings(self) -> bool:
        selected_cycles = [
            label for label, check in getattr(self, "_cycle_checks", {}).items()
            if check.isChecked()
        ]
        selected_types = [
            label for label, check in getattr(self, "_type_checks", {}).items()
            if check.isChecked()
        ]
        if getattr(self, "_cycle_checks", {}) and not selected_cycles:
            QMessageBox.warning(self, "اختيار مطلوب", "اختر سلكاً واحداً على الأقل.")
            return False
        if getattr(self, "_type_checks", {}) and not selected_types:
            QMessageBox.warning(self, "اختيار مطلوب", "اختر نوع تعليم واحداً على الأقل.")
            return False

        if not self._validate_prices():
            return False
        ramadan_start, ramadan_end = self._ramadan_period()

        settings = SchoolSettings(
            school_name=self._school_name.text().strip(),
            school_name_fr=self._school_name_fr.text().strip(),
            aref=self._aref.text().strip(),
            direction_provinciale=self._dir_prov.text().strip(),
            city=self._city.text().strip(),
            city_fr=self._city_fr.text().strip(),
            academy=self._aref.text().strip(),   # keep legacy field in sync
            director=self._director.text().strip(),
            school_year=self._school_year.text().strip(),
            gestionnaire=self._gestionnaire.text().strip(),
            contract_number=self._contract_number.text().strip(),
            company_name=self._company_name.text().strip(),
            supplier_address=self._supplier_address.text().strip(),
            price_ftour=self._price_ftour.text().strip(),
            price_ghada=self._price_ghada.text().strip(),
            price_asha=self._price_asha.text().strip(),
            ramadan_start=ramadan_start,
            ramadan_end=ramadan_end,
        )
        try:
            save_school_settings(settings)
            save_level_preferences(
                [] if len(selected_cycles) == len(getattr(self, "_cycle_checks", {})) else selected_cycles,
                [] if len(selected_types) == len(getattr(self, "_type_checks", {})) else selected_types,
            )
            # The program step stamps the school year on the program it makes.
            self._program_step.set_school_year(self._school_year.text().strip())
            return True
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")
            return False

    # ── Public helper: pre-fill for editing existing settings ──────────────

    def load_settings(self, s: SchoolSettings) -> None:
        """Pre-fill all form fields from existing settings (used by SettingsScreen)."""
        self._school_name.setText(s.school_name)
        self._school_name_fr.setText(s.school_name_fr)
        self._aref.setText(s.aref)
        self._dir_prov.setText(s.direction_provinciale)
        self._city.setText(s.city)
        self._city_fr.setText(s.city_fr)
        self._school_year.setText(s.school_year)
        self._director.setText(s.director)
        self._gestionnaire.setText(s.gestionnaire)
        self._contract_number.setText(s.contract_number)
        self._company_name.setText(s.company_name)
        self._supplier_address.setText(s.supplier_address)
        self._price_ftour.setText(s.price_ftour)
        self._price_ghada.setText(s.price_ghada)
        self._price_asha.setText(s.price_asha)

        # A saved Ramadan period ticks the box and fills the dates; nothing
        # saved leaves the box clear, which is what a school that does not
        # serve Ramadan meals should see.
        has_period = bool((s.ramadan_start or "").strip()
                          and (s.ramadan_end or "").strip())
        self._ramadan_enabled.setChecked(has_period)
        if has_period:
            self._ramadan_start.setDate(
                QDate.fromString(s.ramadan_start, "yyyy-MM-dd"))
            self._ramadan_end.setDate(
                QDate.fromString(s.ramadan_end, "yyyy-MM-dd"))
