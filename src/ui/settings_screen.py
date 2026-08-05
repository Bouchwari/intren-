"""
src/ui/settings_screen.py
Application settings: edit school info, supplier info, logo, and backup.
"""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    DB_PATH, LOGO_PATH,
    EXPORT_FORMAT_ASK, EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF, EXPORT_FORMAT_LABELS,
    FONT_BODY, FONT_LABEL,
)
from core.excel_handler import load_level_catalog
from core.models import Holiday, SchoolSettings
from data.database import (
    add_holiday, delete_holiday, get_all_holidays,
    get_document_export_format, get_level_preferences, get_school_settings,
    save_document_export_format, save_level_preferences, save_school_settings,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

_PAGE_BG = "#f5f5f0"
_PANEL_BG = "#ffffff"
_PANEL_BORDER = "#dddccd"
_INK = "#5A5A40"

# ── Arabic strings ────────────────────────────────────────────────────────────
_TITLE          = "الإعدادات"
_GRP_INST       = "المؤسسة التعليمية"
_GRP_STAFF      = "أطر المؤسسة"
_GRP_CONTRACT   = "صفقة المطعمة"
_GRP_PRICES     = "أثمان الوجبات"
_GRP_LEVELS     = "المستويات المستعملة"
_GRP_LOGO       = "شعار المؤسسة"
_GRP_EXPORT     = "تصدير الوثائق"
_GRP_BACKUP     = "النسخ الاحتياطي"
_GRP_HOLIDAYS   = "أيام العطل"
_BTN_SAVE       = "حفظ التغييرات"
_BTN_SAVE_ICON  = "💾"
_BTN_LOGO       = "اختيار صورة الشعار"
_BTN_LOGO_ICON  = "📁"
_BTN_BACKUP     = "إنشاء نسخة احتياطية"
_BTN_BACKUP_ICON = "💾"
_MSG_SAVED      = "تم حفظ الإعدادات بنجاح."
_MSG_REQUIRED   = "الحقول التالية مطلوبة:\n• اسم المؤسسة\n• السنة الدراسية\n• اسم المدير"
_MSG_LOGO_OK    = "تم تحديث الشعار بنجاح."
_MSG_BACKUP_OK  = "تم إنشاء النسخة الاحتياطية بنجاح."

# ── Holidays ──────────────────────────────────────────────────────────────
_HOLIDAYS_NOTE = (
    "أضف الأيام التي تعرف مسبقًا أن المطعمة ستكون فيها مغلقة (عطلة، توقف "
    "استثنائي...). تساعد هذه اللائحة في تمييز \"يوم عطلة\" عن \"يوم نسي فيه "
    "إدخال البيانات\" عند توليد الوثائق لعدة أيام دفعة واحدة."
)
_HOLIDAYS_HEADERS = ["التاريخ", "السبب", ""]
_HOLIDAY_LABEL_PLACEHOLDER = "سبب العطلة (اختياري)"
_BTN_ADD_HOLIDAY = "إضافة"
_BTN_ADD_HOLIDAY_ICON = "➕"
_BTN_DELETE_HOLIDAY = "🗑"
_HOLIDAY_EMPTY = "لا توجد أيام عطل مضافة."
_HOLIDAY_DUPLICATE = "هذا التاريخ مضاف مسبقًا. تم تحديث السبب."
_HOLIDAY_DEL_CONFIRM_TITLE = "تأكيد الحذف"
_HOLIDAY_DEL_CONFIRM = "حذف هذا اليوم من لائحة العطل؟"


def _field(text: str = "", placeholder: str = "") -> QLineEdit:
    w = QLineEdit(text)
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(34)
    w.setMinimumWidth(430)
    w.setMaximumWidth(860)
    w.setStyleSheet(
        f"background:white; color:{COLOR_TEXT_PRIMARY}; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
        f"padding:4px 10px; font-size:{FONT_BODY}px;"
    )
    return w


def _group(title: str) -> tuple[QGroupBox, QFormLayout]:
    box = QGroupBox(title)
    box.setMinimumWidth(760)
    box.setMaximumWidth(1120)
    box.setStyleSheet(f"""
        QGroupBox {{
            background: {_PANEL_BG};
            font-weight: bold; font-size: {FONT_BODY}px; color: {_INK};
            border: 1px solid {_PANEL_BORDER}; border-radius: 16px;
            margin-top: 14px; padding: 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; subcontrol-position: top right;
            padding: 0 8px; right: 14px;
        }}
    """)
    form = QFormLayout(box)
    form.setSpacing(10)
    form.setHorizontalSpacing(18)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    return box, form


def _section_btn(label: str, color: str, *, icon: str | None = None) -> QPushButton:
    return IconButton(
        label, icon=icon, bg=color, text_color="white",
        border_radius=12, padding_h=18, font_size=13, bold=True, min_height=38,
    )


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


class SettingsScreen(QWidget):
    """Full settings screen with editable school/supplier info, logo, and backup."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background-color: {_PAGE_BG};")
        self._build_ui()
        self._load_current_settings()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sticky top bar with title + save button
        topbar = QWidget()
        topbar.setStyleSheet(f"background:{_PANEL_BG}; border-bottom:1px solid {_PANEL_BORDER};")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(18, 12, 18, 12)

        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(16); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {_INK};")

        self._save_btn = _section_btn(_BTN_SAVE, COLOR_ACCENT, icon=_BTN_SAVE_ICON)
        self._save_btn.clicked.connect(self._on_save)

        topbar_layout.addWidget(title)
        topbar_layout.addStretch()
        topbar_layout.addWidget(self._save_btn)
        outer.addWidget(topbar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        self._form_layout = QVBoxLayout(content)
        self._form_layout.setContentsMargins(18, 16, 18, 22)
        self._form_layout.setSpacing(12)
        self._form_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._build_institution_section()
        self._build_staff_section()
        self._build_contract_section()
        self._build_prices_section()
        self._build_levels_section()
        self._build_logo_section()
        self._build_export_format_section()
        self._build_holidays_section()
        self._build_backup_section()
        self._form_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    def _build_institution_section(self) -> None:
        grp, form = _group(_GRP_INST)
        self._school_name    = _field(placeholder="اسم المؤسسة بالعربية")
        self._school_name_fr = _field(placeholder="Nom d'établissement")
        self._aref           = _field(placeholder="الأكاديمية الجهوية")
        self._dir_prov       = _field(placeholder="المديرية الإقليمية")
        self._gresa_code     = _field(placeholder="رمز GRESA")
        self._city           = _field(placeholder="الجماعة / المدينة")
        self._school_year    = _field(placeholder="مثال: 2024-2025")
        form.addRow("اسم المؤسسة *",            self._school_name)
        form.addRow("Nom d'établissement",       self._school_name_fr)
        form.addRow("الأكاديمية الجهوية (AREF)", self._aref)
        form.addRow("المديرية الإقليمية",        self._dir_prov)
        form.addRow("رمز GRESA",                 self._gresa_code)
        form.addRow("الجماعة",                   self._city)
        form.addRow("السنة الدراسية *",          self._school_year)
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_staff_section(self) -> None:
        grp, form = _group(_GRP_STAFF)
        self._director     = _field(placeholder="اسم مدير المؤسسة")
        self._gestionnaire = _field(placeholder="مسير المصالح المادية والمالية")
        self._surveillant  = _field(placeholder="الحارس العام للداخلية")
        form.addRow("اسم مدير المؤسسة *",                  self._director)
        form.addRow("مسير المصالح المادية والمالية",        self._gestionnaire)
        form.addRow("الحارس العام للداخلية",               self._surveillant)
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_contract_section(self) -> None:
        grp, form = _group(_GRP_CONTRACT)
        self._contract_number  = _field(placeholder="رقم الصفقة")
        self._contract_object  = _field(placeholder="Objet du marché")
        self._supplier_name    = _field(placeholder="اسم المزود")
        self._company_name     = _field(placeholder="Raison sociale")
        self._supplier_address = _field(placeholder="العنوان")
        form.addRow("رقم الصفقة",       self._contract_number)
        form.addRow("Objet du marché",  self._contract_object)
        form.addRow("اسم المزود",       self._supplier_name)
        form.addRow("اسم الشركة",       self._company_name)
        form.addRow("العنوان",          self._supplier_address)
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_prices_section(self) -> None:
        grp, _ = _group(_GRP_PRICES)
        price_row = QHBoxLayout()

        left  = QFormLayout()
        right = QFormLayout()
        for f in (left, right):
            f.setSpacing(10)
            f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._price_ftour         = _field(placeholder="0.00")
        self._price_ghada         = _field(placeholder="0.00")
        self._price_asha          = _field(placeholder="0.00")
        self._price_ftour_ramadan = _field(placeholder="0.00")
        self._price_asha_ramadan  = _field(placeholder="0.00")
        self._price_shour         = _field(placeholder="0.00")

        left.addRow("ثمن الفطور",        self._price_ftour)
        left.addRow("ثمن الغداء",        self._price_ghada)
        left.addRow("ثمن العشاء",        self._price_asha)
        right.addRow("ثمن فطور رمضان",   self._price_ftour_ramadan)
        right.addRow("ثمن عشاء رمضان",   self._price_asha_ramadan)
        right.addRow("ثمن السحور",        self._price_shour)

        price_row.addLayout(left)
        price_row.addSpacing(20)
        price_row.addLayout(right)
        grp.layout().addRow(price_row)  # type: ignore[union-attr]
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_levels_section(self) -> None:
        grp = QGroupBox(_GRP_LEVELS)
        grp.setMinimumWidth(760)
        grp.setMaximumWidth(1120)
        grp.setStyleSheet(f"""
            QGroupBox {{
                background:{_PANEL_BG};
                font-weight:bold; font-size:{FONT_BODY}px; color:{_INK};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:14px; padding:14px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
            QCheckBox {{
                background:transparent;
                color:{COLOR_TEXT_PRIMARY};
                font-size:{FONT_BODY}px;
                padding:4px 2px;
                spacing:10px;
            }}
        """)
        layout = QVBoxLayout(grp)
        layout.setSpacing(12)

        note = QLabel(
            "اختر فقط الأسلاك وأنواع التعليم المستعملة في مؤسستك. "
            "سيتم إخفاء الباقي من لائحة التلاميذ لتصبح الاختيارات قصيرة وسريعة."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px; font-weight:400;")
        layout.addWidget(note)

        catalog = load_level_catalog()
        cycles = _unique([option.cycle_label for option in catalog])
        education_types = _unique([option.education_type for option in catalog])

        self._cycle_checks: dict[str, QCheckBox] = {}
        self._type_checks: dict[str, QCheckBox] = {}

        columns = QHBoxLayout()
        cycle_box = QGroupBox("السلك")
        type_box = QGroupBox("نوع التعليم")
        for box in (cycle_box, type_box):
            box.setStyleSheet(
                f"QGroupBox {{ background:#fafaf6; border:1px solid {_PANEL_BORDER};"
                "border-radius:12px; margin-top:10px; padding:10px; }}"
                "QGroupBox::title { padding:0 6px; right:10px; }"
                "QCheckBox { spacing:10px; padding:5px 2px; }"
            )

        cycle_grid = QGridLayout(cycle_box)
        type_grid = QGridLayout(type_box)

        for index, label in enumerate(cycles):
            check = QCheckBox(label)
            check.setChecked(True)
            self._cycle_checks[label] = check
            cycle_grid.addWidget(check, index // 2, index % 2)

        for index, label in enumerate(education_types):
            check = QCheckBox(label)
            check.setChecked(True)
            self._type_checks[label] = check
            type_grid.addWidget(check, index // 2, index % 2)

        columns.addWidget(cycle_box)
        columns.addWidget(type_box)
        layout.addLayout(columns)

        self._levels_apply_btn = _section_btn("حفظ وتطبيق المستويات", COLOR_SUCCESS)
        self._levels_apply_btn.clicked.connect(self._on_save_level_preferences)
        layout.addWidget(self._levels_apply_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_logo_section(self) -> None:
        grp = QGroupBox(_GRP_LOGO)
        grp.setMinimumWidth(760)
        grp.setMaximumWidth(1120)
        grp.setStyleSheet(f"""
            QGroupBox {{
                background:{_PANEL_BG};
                font-weight:bold; font-size:{FONT_BODY}px; color:{_INK};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:14px; padding:14px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QHBoxLayout(grp)
        layout.setSpacing(20)

        self._logo_preview = QLabel()
        self._logo_preview.setFixedSize(96, 96)
        self._logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_preview.setStyleSheet(
            f"background:#fafaf6; border:2px dashed {_PANEL_BORDER}; border-radius:14px; color:{COLOR_TEXT_SECONDARY};"
        )
        self._logo_preview.setText("لا يوجد\nشعار")
        self._refresh_logo_preview()

        right_col = QVBoxLayout()
        note = QLabel("يستخدم الشعار في رأس المستندات الرسمية المصدّرة.")
        note.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        note.setWordWrap(True)

        logo_btn = _section_btn(_BTN_LOGO, _INK, icon=_BTN_LOGO_ICON)
        logo_btn.clicked.connect(self._on_choose_logo)

        right_col.addWidget(note)
        right_col.addWidget(logo_btn)
        right_col.addStretch()

        layout.addWidget(self._logo_preview)
        layout.addLayout(right_col)
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_export_format_section(self) -> None:
        grp = QGroupBox(_GRP_EXPORT)
        grp.setMinimumWidth(760)
        grp.setMaximumWidth(1120)
        grp.setStyleSheet(f"""
            QGroupBox {{
                background:{_PANEL_BG};
                font-weight:bold; font-size:{FONT_BODY}px; color:{_INK};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:14px; padding:14px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)
        note = QLabel(
            "عند الضغط على زر الطباعة/التصدير في ورقة الاتصال أو رسالة الطلبية، "
            "اختر هل يسألك التطبيق PDF أو Word في كل مرة، أو يستعمل صيغة ثابتة دائماً."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px; font-weight:400;")

        self._export_format_combo = QComboBox()
        self._export_format_combo.setMinimumHeight(36)
        self._export_format_combo.setStyleSheet(
            f"background:white; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
            f"padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        for value in (EXPORT_FORMAT_ASK, EXPORT_FORMAT_PDF, EXPORT_FORMAT_DOCX):
            self._export_format_combo.addItem(EXPORT_FORMAT_LABELS[value], value)
        self._export_format_combo.currentIndexChanged.connect(self._on_export_format_changed)

        layout.addWidget(note)
        layout.addWidget(self._export_format_combo)
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_backup_section(self) -> None:
        grp = QGroupBox(_GRP_BACKUP)
        grp.setMinimumWidth(760)
        grp.setMaximumWidth(1120)
        grp.setStyleSheet(f"""
            QGroupBox {{
                background:{_PANEL_BG};
                font-weight:bold; font-size:{FONT_BODY}px; color:{_INK};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:14px; padding:14px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)
        note = QLabel(
            f"يمكنك حفظ نسخة من قاعدة البيانات ({DB_PATH.name}) في أي مكان تختاره.\n"
            "احتفظ بهذه النسخة في مكان آمن لاستعادة البيانات عند الحاجة."
        )
        note.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        note.setWordWrap(True)

        backup_btn = _section_btn(_BTN_BACKUP, COLOR_SUCCESS, icon=_BTN_BACKUP_ICON)
        backup_btn.clicked.connect(self._on_backup)

        layout.addWidget(note)
        layout.addWidget(backup_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _build_holidays_section(self) -> None:
        grp = QGroupBox(_GRP_HOLIDAYS)
        grp.setMinimumWidth(760)
        grp.setMaximumWidth(1120)
        grp.setStyleSheet(f"""
            QGroupBox {{
                background:{_PANEL_BG};
                font-weight:bold; font-size:{FONT_BODY}px; color:{_INK};
                border:1px solid {_PANEL_BORDER}; border-radius:16px;
                margin-top:14px; padding:14px;
            }}
            QGroupBox::title {{
                subcontrol-origin:margin; subcontrol-position:top right;
                padding:0 8px; right:14px;
            }}
        """)
        layout = QVBoxLayout(grp)
        layout.setSpacing(10)

        note = QLabel(_HOLIDAYS_NOTE)
        note.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        add_row = QHBoxLayout()
        self._holiday_date = DateInput()
        self._holiday_label = QLineEdit()
        self._holiday_label.setPlaceholderText(_HOLIDAY_LABEL_PLACEHOLDER)
        self._holiday_label.setStyleSheet(
            f"background:white; color:{COLOR_TEXT_PRIMARY}; border:1px solid {_PANEL_BORDER};"
            f"border-radius:10px; padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        add_btn = _section_btn(_BTN_ADD_HOLIDAY, COLOR_ACCENT, icon=_BTN_ADD_HOLIDAY_ICON)
        add_btn.clicked.connect(self._on_add_holiday)
        add_row.addWidget(self._holiday_date)
        add_row.addWidget(self._holiday_label, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self._holidays_table = QTableWidget(0, len(_HOLIDAYS_HEADERS))
        self._holidays_table.setHorizontalHeaderLabels(_HOLIDAYS_HEADERS)
        self._holidays_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._holidays_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._holidays_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._holidays_table.verticalHeader().setVisible(False)
        self._holidays_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._holidays_table.horizontalHeader().setStretchLastSection(True)
        self._holidays_table.setMinimumHeight(160)
        self._holidays_table.setStyleSheet(f"""
            QTableWidget {{
                border:1px solid {_PANEL_BORDER}; border-radius:8px;
                font-size:{FONT_LABEL}px; background:white;
                gridline-color:{_PANEL_BORDER};
            }}
            QHeaderView::section {{
                background:{COLOR_ACCENT}; color:white;
                padding:8px 8px; border:none; font-weight:bold;
            }}
            QTableWidget::item {{ padding:5px 8px; }}
        """)
        layout.addWidget(self._holidays_table)

        self._holidays_empty_lbl = QLabel(_HOLIDAY_EMPTY)
        self._holidays_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._holidays_empty_lbl.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px; padding:8px;"
        )
        layout.addWidget(self._holidays_empty_lbl)

        self._form_layout.addWidget(grp, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._refresh_holidays_table()

    # ── Load / Save ────────────────────────────────────────────────────────

    def _load_current_settings(self) -> None:
        self._load_export_format_preference()
        s = get_school_settings()
        if s is None:
            self._load_level_preferences()
            return
        self._school_name.setText(s.school_name)
        self._school_name_fr.setText(s.school_name_fr)
        self._aref.setText(s.aref)
        self._dir_prov.setText(s.direction_provinciale)
        self._gresa_code.setText(s.gresa_code)
        self._city.setText(s.city)
        self._school_year.setText(s.school_year)
        self._director.setText(s.director)
        self._gestionnaire.setText(s.gestionnaire)
        self._surveillant.setText(s.surveillant_general)
        self._contract_number.setText(s.contract_number)
        self._contract_object.setText(s.contract_object)
        self._supplier_name.setText(s.supplier_name)
        self._company_name.setText(s.company_name)
        self._supplier_address.setText(s.supplier_address)
        self._price_ftour.setText(s.price_ftour)
        self._price_ghada.setText(s.price_ghada)
        self._price_asha.setText(s.price_asha)
        self._price_ftour_ramadan.setText(s.price_ftour_ramadan)
        self._price_asha_ramadan.setText(s.price_asha_ramadan)
        self._price_shour.setText(s.price_shour)
        self._load_level_preferences()

    def _load_level_preferences(self) -> None:
        prefs = get_level_preferences()
        cycles = set(prefs.get("cycles", []))
        education_types = set(prefs.get("education_types", []))
        if hasattr(self, "_cycle_checks"):
            for label, check in self._cycle_checks.items():
                check.setChecked(not cycles or label in cycles)
        if hasattr(self, "_type_checks"):
            for label, check in self._type_checks.items():
                check.setChecked(not education_types or label in education_types)

    def _load_export_format_preference(self) -> None:
        value = get_document_export_format()
        index = self._export_format_combo.findData(value)
        self._export_format_combo.blockSignals(True)
        self._export_format_combo.setCurrentIndex(index if index >= 0 else 0)
        self._export_format_combo.blockSignals(False)

    def _on_export_format_changed(self, _index: int) -> None:
        value = self._export_format_combo.currentData()
        save_document_export_format(value)

    def _selected_level_preferences(self) -> tuple[list[str], list[str]] | None:
        cycle_checks = getattr(self, "_cycle_checks", {})
        type_checks = getattr(self, "_type_checks", {})
        selected_cycles = [
            label for label, check in cycle_checks.items()
            if check.isChecked()
        ]
        selected_types = [
            label for label, check in type_checks.items()
            if check.isChecked()
        ]
        if cycle_checks and not selected_cycles:
            QMessageBox.warning(self, "اختيار مطلوب", "اختر سلكاً واحداً على الأقل.")
            return None
        if type_checks and not selected_types:
            QMessageBox.warning(self, "اختيار مطلوب", "اختر نوع تعليم واحداً على الأقل.")
            return None
        return (
            [] if cycle_checks and len(selected_cycles) == len(cycle_checks) else selected_cycles,
            [] if type_checks and len(selected_types) == len(type_checks) else selected_types,
        )

    def _on_save_level_preferences(self) -> None:
        prefs = self._selected_level_preferences()
        if prefs is None:
            return
        try:
            save_level_preferences(*prefs)
            QMessageBox.information(
                self,
                "تم",
                "تم تطبيق المستويات. افتح نافذة إضافة تلميذ من جديد لترى الاختيارات المختصرة.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر حفظ المستويات:\n{exc}")

    def _on_save(self) -> None:
        if not self._school_name.text().strip() or \
           not self._school_year.text().strip() or \
           not self._director.text().strip():
            QMessageBox.warning(self, "حقول مطلوبة", _MSG_REQUIRED)
            return

        level_prefs = self._selected_level_preferences()
        if level_prefs is None:
            return

        settings = SchoolSettings(
            school_name=self._school_name.text().strip(),
            school_name_fr=self._school_name_fr.text().strip(),
            aref=self._aref.text().strip(),
            direction_provinciale=self._dir_prov.text().strip(),
            gresa_code=self._gresa_code.text().strip(),
            city=self._city.text().strip(),
            academy=self._aref.text().strip(),
            director=self._director.text().strip(),
            school_year=self._school_year.text().strip(),
            gestionnaire=self._gestionnaire.text().strip(),
            surveillant_general=self._surveillant.text().strip(),
            contract_number=self._contract_number.text().strip(),
            contract_object=self._contract_object.text().strip(),
            supplier_name=self._supplier_name.text().strip(),
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
            save_level_preferences(*level_prefs)
            QMessageBox.information(self, "تم", _MSG_SAVED)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    # ── Logo ───────────────────────────────────────────────────────────────

    def _refresh_logo_preview(self) -> None:
        if LOGO_PATH.exists():
            pix = QPixmap(str(LOGO_PATH)).scaled(
                90, 90,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._logo_preview.setPixmap(pix)
            self._logo_preview.setText("")
        else:
            self._logo_preview.clear()
            self._logo_preview.setText("لا يوجد\nشعار")

    def _on_choose_logo(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "اختر صورة الشعار", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.svg)"
        )
        if not path_str:
            return
        try:
            shutil.copy2(path_str, str(LOGO_PATH))
            self._refresh_logo_preview()
            QMessageBox.information(self, "تم", _MSG_LOGO_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر نسخ الصورة:\n{exc}")

    # ── Backup ─────────────────────────────────────────────────────────────

    def _on_backup(self) -> None:
        if not DB_PATH.exists():
            QMessageBox.warning(self, "تنبيه", "لم يتم العثور على قاعدة البيانات.")
            return
        dest_str, _ = QFileDialog.getSaveFileName(
            self, "حفظ النسخة الاحتياطية",
            f"matama_backup_{__import__('datetime').date.today()}.db",
            "Database (*.db)"
        )
        if not dest_str:
            return
        try:
            shutil.copy2(str(DB_PATH), dest_str)
            QMessageBox.information(self, "تم", _MSG_BACKUP_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    # ── Holidays ───────────────────────────────────────────────────────────

    def _refresh_holidays_table(self) -> None:
        holidays = get_all_holidays()
        self._holidays_empty_lbl.setVisible(not holidays)
        self._holidays_table.setVisible(bool(holidays))
        self._holidays_table.setRowCount(len(holidays))
        self._holidays_table.verticalHeader().setDefaultSectionSize(34)
        for row, holiday in enumerate(holidays):
            self._holidays_table.setItem(row, 0, QTableWidgetItem(holiday.date))
            self._holidays_table.setItem(row, 1, QTableWidgetItem(holiday.label))
            delete_btn = IconButton(
                _BTN_DELETE_HOLIDAY, bg=COLOR_DANGER, text_color="white",
                border_radius=6, padding_h=8, font_size=12, bold=False, min_height=24,
            )
            delete_btn.setFixedWidth(40)
            delete_btn.clicked.connect(lambda _checked=False, d=holiday.date: self._on_delete_holiday(d))
            self._holidays_table.setCellWidget(row, 2, delete_btn)

    def _on_add_holiday(self) -> None:
        date_str = self._holiday_date.date().toString("yyyy-MM-dd")
        label = self._holiday_label.text().strip()
        was_duplicate = any(h.date == date_str for h in get_all_holidays())
        add_holiday(Holiday(date=date_str, label=label))
        self._holiday_label.clear()
        self._refresh_holidays_table()
        if was_duplicate:
            QMessageBox.information(self, "تنبيه", _HOLIDAY_DUPLICATE)

    def _on_delete_holiday(self, date_str: str) -> None:
        reply = QMessageBox.question(
            self, _HOLIDAY_DEL_CONFIRM_TITLE, _HOLIDAY_DEL_CONFIRM,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_holiday(date_str)
            self._refresh_holidays_table()
