"""
src/ui/settings_screen.py
Application settings: edit school info, supplier info, logo, and backup.
"""
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS,
    COLOR_SURFACE, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY,
    DB_PATH, LOGO_PATH,
    EXPORT_FORMAT_ASK, EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF, EXPORT_FORMAT_LABELS,
    FONT_BODY, FONT_CAPTION, FONT_LABEL,
)
from core.excel_handler import load_level_catalog
from core.models import Holiday, SchoolSettings
from data.database import (
    get_pdf_print_layout, save_pdf_print_layout,
    add_holiday, backup_database, delete_holiday, get_all_holidays,
    get_document_export_format, get_level_preferences, get_school_settings,
    save_document_export_format, save_level_preferences, save_school_settings,
)
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton
from ui.report_options import ReportPreferencesWidget
from data.settings_repo import save_report_preferences
from ui import document_branding as branding
from ui.document_header import _template_header_image
from ui.header_editor import HeaderEditorDialog

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
_GRP_RAMADAN    = "مدة رمضان"
_GRP_LEVELS     = "المستويات المستعملة"
_RAMADAN_HINT   = ("حدّد مدة رمضان بصيغة YYYY-MM-DD. خلال هذه المدة تتحول كل "
                   "الوثائق تلقائياً إلى وجبتي الإفطار والسحور بدل الوجبات "
                   "الثلاث العادية. يمكنك تصحيح يوم واحد من ورقة الاتصال "
                   "اليومية إذا اختلف الهلال.")
_GRP_LOGO       = "ترويسة الوثائق الرسمية"
_GRP_EXPORT     = "تصدير الوثائق"
_GRP_BACKUP     = "النسخ الاحتياطي"
_GRP_HOLIDAYS   = "أيام العطل"
_BTN_SAVE       = "حفظ التغييرات"
_BTN_SAVE_ICON  = "💾"
_BTN_LOGO       = "اختيار صورة الترويسة"
_BTN_LOGO_ICON  = "📁"
_BTN_BACKUP     = "إنشاء نسخة احتياطية"
_BTN_BACKUP_ICON = "💾"
_MSG_SAVED      = "تم حفظ الإعدادات بنجاح."
_MSG_REQUIRED   = "الحقول التالية مطلوبة:\n• اسم المؤسسة\n• السنة الدراسية\n• اسم المدير"
_MSG_LOGO_OK    = "تم تحديث الترويسة. ستظهر في الوثائق المصدرة من الآن؛ الملفات القديمة لا تتغير."
_MSG_BACKUP_OK  = "تم إنشاء النسخة الاحتياطية بنجاح."

# ── Holidays ──────────────────────────────────────────────────────────────
_HOLIDAYS_NOTE = (
    "أضف الأيام التي تعرف مسبقًا أن المطعمة ستكون فيها مغلقة (عطلة، توقف "
    "استثنائي...). تساعد هذه اللائحة في تمييز \"يوم عطلة\" عن \"يوم نسي فيه "
    "إدخال البيانات\" عند توليد الوثائق لعدة أيام دفعة واحدة."
)
_HOLIDAYS_HEADERS = ["التاريخ", "السبب", ""]
_HOLIDAY_LABEL_PLACEHOLDER = "سبب العطلة (اختياري)"
_LBL_FROM = "من:"
_LBL_TO = "إلى:"
_BTN_ADD_HOLIDAY = "إضافة"
_BTN_ADD_HOLIDAY_ICON = "➕"
_BTN_DELETE_HOLIDAY = "🗑"
_HOLIDAY_EMPTY = "لا توجد أيام عطل مضافة."
_HOLIDAY_ADDED_FMT = "تمت إضافة {added} يوم/أيام عطلة. (تحديث السبب لـ {updated} يوم مضاف مسبقًا)"
_HOLIDAY_RANGE_ORDER_ERR = "تاريخ \"إلى\" يجب أن يكون بعد تاريخ \"من\"."
_HOLIDAY_DEL_CONFIRM_TITLE = "تأكيد الحذف"
_HOLIDAY_DEL_CONFIRM = "حذف هذا اليوم من لائحة العطل؟"
_HOLIDAY_DEL_CONFIRM_RANGE = "حذف كل الأيام ({count}) من لائحة العطل؟"


def _field(text: str = "", placeholder: str = "", min_width: int = 220) -> QLineEdit:
    """Keep a usable input width without forcing the whole page to scroll sideways."""
    w = QLineEdit(text)
    w.setPlaceholderText(placeholder)
    w.setMinimumHeight(34)
    w.setMinimumWidth(min_width)
    w.setMaximumWidth(860)
    w.setStyleSheet(
        f"background:white; color:{COLOR_TEXT_PRIMARY}; border:1px solid {_PANEL_BORDER}; border-radius:10px;"
        f"padding:4px 10px; font-size:{FONT_BODY}px;"
    )
    return w


class _SettingsFormLayout(QFormLayout):
    def addRow(self, *args) -> None:
        super().addRow(*args)
        if len(args) == 2 and isinstance(args[0], str):
            label = self.labelForField(args[1])
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
                               | Qt.AlignmentFlag.AlignVCenter)
            label.setMinimumHeight(label.fontMetrics().height() + 8)
            label.setStyleSheet("background:transparent; border:0; padding:0;")


def _group(title: str) -> tuple[QGroupBox, QFormLayout]:
    box = QGroupBox(title)
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
    form = _SettingsFormLayout(box)
    form.setSpacing(10)
    form.setHorizontalSpacing(18)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
                           | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    return box, form


def _section_btn(label: str, color: str, *, icon: str | None = None) -> QPushButton:
    return IconButton(
        label, icon=icon, bg=color, text_color="white",
        border_radius=12, padding_h=18, font_size=13, bold=True, min_height=38,
    )


def _group_consecutive_holidays(holidays: list[Holiday]) -> list[tuple[str, str, str, list[str]]]:
    """Collapse runs of back-to-back dates sharing the same label into one
    group — a whole marked-off week shows as one row instead of seven.
    Returns (start_date, end_date, label, every date in the group), input
    must already be sorted by date (get_all_holidays() guarantees this)."""
    groups: list[tuple[str, str, str, list[str]]] = []
    for holiday in holidays:
        if groups:
            _start, prev_end, prev_label, prev_dates = groups[-1]
            prev_date = QDate.fromString(prev_end, "yyyy-MM-dd")
            this_date = QDate.fromString(holiday.date, "yyyy-MM-dd")
            if holiday.label == prev_label and prev_date.addDays(1) == this_date:
                groups[-1] = (_start, holiday.date, prev_label, prev_dates + [holiday.date])
                continue
        groups.append((holiday.date, holiday.date, holiday.label, [holiday.date]))
    return groups


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
        self.setObjectName("settingsScreen")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(f"""
            QWidget#settingsScreen {{ background-color: {_PAGE_BG}; }}
            QLabel {{ background:transparent; border:0; }}
        """)
        self._build_ui()
        self._load_current_settings()

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sticky top bar with title + save button
        topbar = QWidget()
        topbar.setObjectName("settingsTopbar")
        topbar.setStyleSheet(f"#settingsTopbar {{ background:{_PANEL_BG}; border-bottom:1px solid {_PANEL_BORDER}; }}")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(18, 12, 18, 12)

        title = QLabel(_TITLE)
        f = QFont(); f.setPointSize(16); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {_INK}; background:transparent; border:0;")

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
        scroll.setStyleSheet("QScrollArea { background:transparent; }")

        content = QWidget()
        content.setObjectName("settingsContent")
        content.setStyleSheet("#settingsContent { background:transparent; }")
        self._form_layout = QVBoxLayout(content)
        self._form_layout.setContentsMargins(18, 16, 18, 22)
        self._form_layout.setSpacing(12)
        self._form_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self._build_institution_section()
        self._build_staff_section()
        self._build_contract_section()
        self._build_prices_section()
        self._build_ramadan_section()
        self._build_levels_section()
        self._build_logo_section()
        self._build_export_format_section()
        self._report_preferences = ReportPreferencesWidget()
        self._form_layout.addWidget(self._report_preferences)
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
        self._city           = _field(placeholder="الجماعة / المدينة")
        self._city_fr        = _field(placeholder="Nom de la ville")
        self._school_year    = _field(placeholder="مثال: 2024-2025")
        form.addRow("اسم المؤسسة *",            self._school_name)
        form.addRow("Nom d'établissement",       self._school_name_fr)
        form.addRow("الأكاديمية الجهوية (AREF)", self._aref)
        form.addRow("المديرية الإقليمية",        self._dir_prov)
        form.addRow("الجماعة",                   self._city)
        form.addRow("Nom de la ville",           self._city_fr)
        form.addRow("السنة الدراسية *",          self._school_year)
        self._form_layout.addWidget(grp)

    def _build_staff_section(self) -> None:
        grp, form = _group(_GRP_STAFF)
        self._director     = _field(placeholder="اسم مدير المؤسسة")
        self._gestionnaire = _field(placeholder="مسير المصالح المادية والمالية")
        form.addRow("اسم مدير المؤسسة *",                  self._director)
        form.addRow("مسير المصالح المادية والمالية",        self._gestionnaire)
        self._form_layout.addWidget(grp)

    def _build_contract_section(self) -> None:
        grp, form = _group(_GRP_CONTRACT)
        self._contract_number  = _field(placeholder="رقم الصفقة")
        self._company_name     = _field(placeholder="Raison sociale")
        self._supplier_address = _field(placeholder="العنوان")
        form.addRow("رقم الصفقة",       self._contract_number)
        form.addRow("اسم الشركة",       self._company_name)
        form.addRow("العنوان",          self._supplier_address)
        self._form_layout.addWidget(grp)

    def _build_prices_section(self) -> None:
        grp, _ = _group(_GRP_PRICES)
        price_row = QHBoxLayout()

        left  = _SettingsFormLayout()
        right = _SettingsFormLayout()
        for f in (left, right):
            f.setSpacing(10)
            f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # Narrow: two of these sit side by side, and at the default width
        # their labels get squeezed out of existence entirely.
        self._price_ftour         = _field(placeholder="0.00", min_width=220)
        self._price_ghada         = _field(placeholder="0.00", min_width=220)
        self._price_asha          = _field(placeholder="0.00", min_width=220)
        self._price_ftour_ramadan = _field(placeholder="0.00", min_width=220)
        self._price_asha_ramadan  = _field(placeholder="0.00", min_width=220)
        self._price_shour         = _field(placeholder="0.00", min_width=220)

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

        self._form_layout.addWidget(grp)

    def _build_ramadan_section(self) -> None:
        """Its own titled section — buried among the prices, these two dates
        gave no clue what they were for."""
        grp, form = _group(_GRP_RAMADAN)
        self._ramadan_start = _field(placeholder="2026-02-18")
        self._ramadan_end   = _field(placeholder="2026-03-19")
        form.addRow("بداية رمضان", self._ramadan_start)
        form.addRow("نهاية رمضان", self._ramadan_end)

        hint = QLabel(_RAMADAN_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_CAPTION}px;")
        form.addRow(hint)
        self._form_layout.addWidget(grp)

    def _build_levels_section(self) -> None:
        grp = QGroupBox(_GRP_LEVELS)
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

        columns = QVBoxLayout()
        cycle_box = QGroupBox("السلك")
        type_box = QGroupBox("نوع التعليم")
        for box in (cycle_box, type_box):
            box.setStyleSheet(
                f"QGroupBox {{ background:#fafaf6; border:1px solid {_PANEL_BORDER};"
                "border-radius:12px; margin-top:10px; padding:10px; }"
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

        self._form_layout.addWidget(grp)

    def _build_logo_section(self) -> None:
        grp = QGroupBox(_GRP_LOGO)
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
        self._logo_preview.setFixedSize(240, 80)
        self._logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_preview.setStyleSheet(
            f"background:#fafaf6; border:2px dashed {_PANEL_BORDER}; border-radius:14px; color:{COLOR_TEXT_SECONDARY};"
        )
        self._logo_preview.setText("لا يوجد\nشعار")
        self._refresh_logo_preview()

        right_col = QVBoxLayout()
        note = QLabel("صورة تشمل الشعار واسم الوزارة. PNG أو JPG بدقة \u20661800 × 414\u2069 بكسل أو أعلى.")
        note.setStyleSheet(f"color:{COLOR_TEXT_SECONDARY}; font-size:{FONT_LABEL}px;")
        note.setWordWrap(True)

        logo_btn = _section_btn(_BTN_LOGO, _INK, icon=_BTN_LOGO_ICON)
        logo_btn.clicked.connect(self._on_choose_logo)

        right_col.addWidget(note)
        right_col.addWidget(logo_btn)
        previous = _section_btn("تعديل الصورة الحالية أو السابقة", _INK)
        previous.clicked.connect(self._on_edit_current_header)
        right_col.addWidget(previous)
        restore = _section_btn("استعادة ترويسة النموذج", _INK)
        restore.clicked.connect(self._on_reset_header)
        right_col.addWidget(restore)
        right_col.addStretch()

        layout.addWidget(self._logo_preview)
        layout.addLayout(right_col)
        self._form_layout.addWidget(grp)

    def _build_export_format_section(self) -> None:
        grp = QGroupBox(_GRP_EXPORT)
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
        layout.addWidget(QLabel("تخطيط طباعة الوثائق اليومية (PDF)"))
        self._pdf_layout_combo = QComboBox()
        self._pdf_layout_combo.setMinimumHeight(36)
        self._pdf_layout_combo.setStyleSheet(self._export_format_combo.styleSheet())
        self._pdf_layout_combo.addItem("توفير الورق: نسختان في كل ورقة A4", "three_copies")
        self._pdf_layout_combo.addItem("التخطيط الأصلي", "standard")
        self._pdf_layout_combo.currentIndexChanged.connect(
            lambda _index: save_pdf_print_layout(self._pdf_layout_combo.currentData())
        )
        layout.addWidget(self._pdf_layout_combo)
        self._form_layout.addWidget(grp)

    def _build_backup_section(self) -> None:
        grp = QGroupBox(_GRP_BACKUP)
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
        self._form_layout.addWidget(grp)

    def _build_holidays_section(self) -> None:
        grp = QGroupBox(_GRP_HOLIDAYS)
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

        calendar_button = _section_btn("مراجعة لائحة العطل 2026/2027", COLOR_ACCENT)
        calendar_button.clicked.connect(self._open_holiday_calendar)
        layout.addWidget(calendar_button)
        self._calendar_notice = QLabel()
        self._calendar_notice.setWordWrap(True)
        layout.addWidget(self._calendar_notice)
        self._refresh_calendar_notice()

        def _date_field() -> DateInput:
            d = DateInput()
            d.setMinimumHeight(36)
            d.setMinimumWidth(150)
            d.setStyleSheet(
                f"background:white; color:{COLOR_TEXT_PRIMARY}; border:1px solid {_PANEL_BORDER};"
                f"border-radius:10px; padding:4px 10px; font-size:{FONT_BODY}px;"
            )
            return d

        add_row = QHBoxLayout()
        self._holiday_date_from = _date_field()
        self._holiday_date_to = _date_field()
        self._holiday_label = QLineEdit()
        self._holiday_label.setPlaceholderText(_HOLIDAY_LABEL_PLACEHOLDER)
        self._holiday_label.setStyleSheet(
            f"background:white; color:{COLOR_TEXT_PRIMARY}; border:1px solid {_PANEL_BORDER};"
            f"border-radius:10px; padding:4px 10px; font-size:{FONT_BODY}px;"
        )
        # Keep "to" following "from" while they're in sync, so a single day
        # just needs one click — an explicit change to "to" breaks the sync.
        self._holiday_range_synced = True
        self._holiday_date_from.dateChanged.connect(self._on_holiday_from_changed)
        self._holiday_date_to.dateChanged.connect(self._on_holiday_to_changed)

        add_btn = _section_btn(_BTN_ADD_HOLIDAY, COLOR_ACCENT, icon=_BTN_ADD_HOLIDAY_ICON)
        add_btn.clicked.connect(self._on_add_holiday)
        add_row.addWidget(QLabel(_LBL_FROM))
        add_row.addWidget(self._holiday_date_from)
        add_row.addWidget(QLabel(_LBL_TO))
        add_row.addWidget(self._holiday_date_to)
        add_row.addStretch()
        layout.addLayout(add_row)
        reason_row = QHBoxLayout()
        reason_row.addWidget(self._holiday_label, 1)
        reason_row.addWidget(add_btn)
        layout.addLayout(reason_row)

        self._holidays_table = QTableWidget(0, len(_HOLIDAYS_HEADERS))
        self._holidays_table.setHorizontalHeaderLabels(_HOLIDAYS_HEADERS)
        self._holidays_table.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._holidays_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._holidays_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._holidays_table.verticalHeader().setVisible(False)
        header = self._holidays_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # التاريخ
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)          # السبب — the empty column was
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # fixed-width but stretched
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

        self._form_layout.addWidget(grp)
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
        self._ramadan_start.setText(s.ramadan_start)
        self._ramadan_end.setText(s.ramadan_end)
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
        self._pdf_layout_combo.blockSignals(True)
        self._pdf_layout_combo.setCurrentIndex(
            self._pdf_layout_combo.findData(get_pdf_print_layout())
        )
        self._pdf_layout_combo.blockSignals(False)
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
            city=self._city.text().strip(),
            city_fr=self._city_fr.text().strip(),
            academy=self._aref.text().strip(),
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
            ramadan_start=self._ramadan_start.text().strip(),
            ramadan_end=self._ramadan_end.text().strip(),
            price_shour=self._price_shour.text().strip(),
        )
        try:
            save_school_settings(settings)
            self._refresh_calendar_notice()
            save_level_preferences(*level_prefs)
            save_report_preferences(self._report_preferences.preferences())
            QMessageBox.information(self, "تم", _MSG_SAVED)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    # ── Logo ───────────────────────────────────────────────────────────────

    def _refresh_logo_preview(self) -> None:
        try:
            image = _template_header_image()
        except (OSError, ValueError):
            self._logo_preview.setText("تعذر قراءة الترويسة")
            return
        if not image.isNull():
            pix = QPixmap.fromImage(image).scaled(
                230, 74,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._logo_preview.setPixmap(pix)
            self._logo_preview.setText("")
        else:
            self._logo_preview.clear()
            self._logo_preview.setText("لا توجد ترويسة")

    def _on_choose_logo(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "اختر صورة الترويسة الكاملة", "",
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path_str:
            return
        self._edit_header(Path(path_str))

    def _edit_header(self, path: Path) -> None:
        try:
            image = branding.load_header_source(path)
            dialog = HeaderEditorDialog(image, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._refresh_logo_preview()
                QMessageBox.information(self, "تم", _MSG_LOGO_OK)
        except (OSError, ValueError):
            QMessageBox.warning(self, "خطأ", "تعذر فتح الصورة. اختر صورة PNG أو JPG صالحة لا تتجاوز 40 مليون بكسل.")

    def _on_edit_current_header(self) -> None:
        if branding.DOCUMENT_HEADER_PATH.exists():
            self._edit_header(branding.DOCUMENT_HEADER_PATH)
        elif LOGO_PATH.exists():
            self._edit_header(LOGO_PATH)
        else:
            dialog = HeaderEditorDialog(_template_header_image(), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._refresh_logo_preview()

    def _on_reset_header(self) -> None:
        answer = QMessageBox.question(self, "استعادة الترويسة", "العودة إلى الترويسات الأصلية في النماذج؟")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            branding.reset_header()
            self._refresh_logo_preview()
        except OSError:
            QMessageBox.warning(self, "خطأ", "تعذر استعادة الترويسة. حاول مرة أخرى.")

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
            backup_database(Path(dest_str))
            QMessageBox.information(self, "تم", _MSG_BACKUP_OK)
        except Exception as exc:
            QMessageBox.critical(self, "خطأ", f"تعذر الحفظ:\n{exc}")

    # ── Holidays ───────────────────────────────────────────────────────────

    def _refresh_calendar_notice(self) -> None:
        from data.holiday_calendar_repo import calendar_notice
        self._calendar_notice.setText(calendar_notice())
        self._calendar_notice.setVisible(bool(self._calendar_notice.text()))

    def _open_holiday_calendar(self) -> None:
        from ui.holiday_calendar_dialog import HolidayCalendarDialog
        if HolidayCalendarDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._refresh_holidays_table()
            self._refresh_calendar_notice()

    def _refresh_holidays_table(self) -> None:
        holidays = get_all_holidays()
        self._holidays_empty_lbl.setVisible(not holidays)
        self._holidays_table.setVisible(bool(holidays))
        groups = _group_consecutive_holidays(holidays)
        self._holidays_table.setRowCount(len(groups))
        self._holidays_table.verticalHeader().setDefaultSectionSize(34)
        for row, (start, end, label, dates) in enumerate(groups):
            date_text = f"‎{start}‎" if start == end else f"‎{start}‎  —  ‎{end}‎"
            self._holidays_table.setItem(row, 0, QTableWidgetItem(date_text))
            self._holidays_table.setItem(row, 1, QTableWidgetItem(label))
            delete_btn = IconButton(
                _BTN_DELETE_HOLIDAY, bg=COLOR_DANGER, text_color="white",
                border_radius=6, padding_h=8, font_size=12, bold=False, min_height=24,
            )
            delete_btn.setFixedWidth(40)
            delete_btn.clicked.connect(lambda _checked=False, ds=dates: self._on_delete_holiday_group(ds))
            self._holidays_table.setCellWidget(row, 2, delete_btn)

    def _on_holiday_from_changed(self, new_date: QDate) -> None:
        if self._holiday_range_synced:
            self._holiday_date_to.blockSignals(True)
            self._holiday_date_to.setDate(new_date)
            self._holiday_date_to.blockSignals(False)

    def _on_holiday_to_changed(self, _new_date: QDate) -> None:
        self._holiday_range_synced = False

    def _on_add_holiday(self) -> None:
        start = self._holiday_date_from.date()
        end = self._holiday_date_to.date()
        if end < start:
            QMessageBox.warning(self, "تنبيه", _HOLIDAY_RANGE_ORDER_ERR)
            return

        label = self._holiday_label.text().strip()
        existing_dates = {h.date for h in get_all_holidays()}
        added = updated = 0
        date = start
        while date <= end:
            date_str = date.toString("yyyy-MM-dd")
            if date_str in existing_dates:
                updated += 1
            else:
                added += 1
            add_holiday(Holiday(date=date_str, label=label))
            date = date.addDays(1)

        self._holiday_label.clear()
        self._holiday_date_to.blockSignals(True)
        self._holiday_date_to.setDate(start)
        self._holiday_date_to.blockSignals(False)
        self._holiday_range_synced = True
        self._refresh_holidays_table()
        if added + updated > 1 or updated:
            QMessageBox.information(self, "تم", _HOLIDAY_ADDED_FMT.format(added=added, updated=updated))

    def _on_delete_holiday_group(self, dates: list[str]) -> None:
        message = _HOLIDAY_DEL_CONFIRM if len(dates) == 1 else _HOLIDAY_DEL_CONFIRM_RANGE.format(count=len(dates))
        reply = QMessageBox.question(
            self, _HOLIDAY_DEL_CONFIRM_TITLE, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for date_str in dates:
                delete_holiday(date_str)
            self._refresh_holidays_table()
