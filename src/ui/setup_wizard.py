"""
src/ui/setup_wizard.py
Two-page first-run wizard matching the official Moroccan school form layout.
Page 1: institution identity + staff names
Page 2: supplier contract + meal prices
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget, QScrollArea, QFrame
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_PANEL_ALT, COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.excel_handler import load_level_catalog
from core.models import SchoolSettings
from data.database import save_level_preferences, save_school_settings

# ── Arabic UI strings ─────────────────────────────────────────────────────────
_TITLE_P1      = "المؤسسة التعليمية"
_TITLE_P2      = "صفقة المطعمة"
_SUBTITLE_P1   = "الخطوة 1 من 2 — معلومات المؤسسة وأطرها"
_SUBTITLE_P2   = "الخطوة 2 من 2 — معلومات المورد وأثمان الوجبات"
_GRP_INST      = "المؤسسة التعليمية"
_GRP_STAFF     = "أطر المؤسسة"
_GRP_CONTRACT  = "الصفقة"
_GRP_PRICES    = "أثمان الوجبات"
_GRP_LEVELS    = "المستويات المستعملة"
_BTN_NEXT      = "التالي  ←"
_BTN_BACK      = "→  السابق"
_BTN_SAVE      = "💾  حفظ والانطلاق"
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
        self.setWindowTitle("الإعداد الأولي — نظام المطعمة")
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
        root.addWidget(self._stack, 1)

        # Footer nav
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(f"background-color: {COLOR_ACCENT};")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(24, 16, 24, 16)

        self._title_lbl = QLabel(_TITLE_P1)
        f = QFont(); f.setPointSize(15); f.setBold(True)
        self._title_lbl.setFont(f)
        self._title_lbl.setStyleSheet("color: white;")

        self._sub_lbl = QLabel(_SUBTITLE_P1)
        self._sub_lbl.setStyleSheet(f"color: rgba(255,255,255,0.85); font-size: {FONT_LABEL}px;")

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._sub_lbl)
        return header

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

        # Group: prices — two columns for compactness
        grp_prices, _ = _group(_GRP_PRICES)
        price_layout = QHBoxLayout()
        left_form  = QFormLayout()
        right_form = QFormLayout()
        for f in (left_form, right_form):
            f.setSpacing(10)
            f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._price_ftour           = _line("0.00")
        self._price_ghada           = _line("0.00")
        self._price_asha            = _line("0.00")
        self._price_ftour_ramadan   = _line("0.00")
        self._price_asha_ramadan    = _line("0.00")
        self._price_shour           = _line("0.00")

        left_form.addRow("ثمن وجبة الفطور",    self._price_ftour)
        left_form.addRow("ثمن وجبة الغداء",    self._price_ghada)
        left_form.addRow("ثمن وجبة العشاء",    self._price_asha)
        right_form.addRow("ثمن فطور رمضان",    self._price_ftour_ramadan)
        right_form.addRow("ثمن عشاء رمضان",    self._price_asha_ramadan)
        right_form.addRow("ثمن السحور",         self._price_shour)

        price_layout.addLayout(left_form)
        price_layout.addSpacing(20)
        price_layout.addLayout(right_form)
        grp_prices.layout().addRow(price_layout)  # type: ignore[union-attr]

        note = QLabel("* يمكن تعديل هذه المعلومات لاحقاً من صفحة الإعدادات")
        note.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: {FONT_CAPTION}px;")

        layout.addWidget(grp_contract)
        layout.addWidget(grp_prices)
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

        row.addWidget(self._back_btn)
        row.addStretch()
        row.addWidget(self._next_btn)
        return footer

    # ── Navigation ─────────────────────────────────────────────────────────

    def _go_next(self) -> None:
        if self._stack.currentIndex() == 0:
            if not self._validate_page1():
                return
            self._stack.setCurrentIndex(1)
            self._title_lbl.setText(_TITLE_P2)
            self._sub_lbl.setText(_SUBTITLE_P2)
            self._back_btn.setVisible(True)
            self._next_btn.setText(_BTN_SAVE)
        else:
            self._save_and_accept()

    def _go_back(self) -> None:
        self._stack.setCurrentIndex(0)
        self._title_lbl.setText(_TITLE_P1)
        self._sub_lbl.setText(_SUBTITLE_P1)
        self._back_btn.setVisible(False)
        self._next_btn.setText(_BTN_NEXT)

    # ── Validation & save ──────────────────────────────────────────────────

    def _validate_page1(self) -> bool:
        missing = (
            not self._school_name.text().strip() or
            not self._school_year.text().strip() or
            not self._director.text().strip()
        )
        if missing:
            QMessageBox.warning(self, "حقول مطلوبة", _MSG_REQUIRED)
        return not missing

    def _save_and_accept(self) -> None:
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
            return
        if getattr(self, "_type_checks", {}) and not selected_types:
            QMessageBox.warning(self, "اختيار مطلوب", "اختر نوع تعليم واحداً على الأقل.")
            return

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
            price_ftour_ramadan=self._price_ftour_ramadan.text().strip(),
            price_asha_ramadan=self._price_asha_ramadan.text().strip(),
            price_shour=self._price_shour.text().strip(),
        )
        try:
            save_school_settings(settings)
            save_level_preferences(
                [] if len(selected_cycles) == len(getattr(self, "_cycle_checks", {})) else selected_cycles,
                [] if len(selected_types) == len(getattr(self, "_type_checks", {})) else selected_types,
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

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
        self._price_ftour_ramadan.setText(s.price_ftour_ramadan)
        self._price_asha_ramadan.setText(s.price_asha_ramadan)
        self._price_shour.setText(s.price_shour)
