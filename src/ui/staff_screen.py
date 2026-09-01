"""
src/ui/staff_screen.py
طاقم المطبخ — who works in the school's kitchen, on a card each.

An INTERNAL tracker, not an official document: the ministry guide has no staff
form, so nothing here is submitted anywhere. Its real job is the شهادة طبية
expiry warning — a valid medical certificate is a contractual requirement for
anyone handling food, and the school is the party expected to check it.

Deliberately records NO attendance history (the user asked for identification
only) — `status` is the current situation, not a log.
"""
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_PAPER, COLOR_SUCCESS,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_WARNING,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.models import StaffMember
from core.staff_certificates import (
    STATE_EXPIRED, STATE_EXPIRING, STATE_MISSING, STATE_VALID,
    certificate_state, days_until_expiry, needs_attention,
)
from data.database import (
    delete_staff_member, get_all_staff, get_school_settings, save_staff_member,
)
from ui.staff_export import write_staff_pdf
from ui.widgets.date_input import DateInput
from ui.widgets.icon_button import IconButton

# ── Arabic strings ──────────────────────────────────────────────────────────
_TITLE = "طاقم المطبخ"
_SUBTITLE = ("التعريف بالعاملين في مطعم المؤسسة ومراقبة صلاحية شواهدهم الطبية — "
             "سجل داخلي للتتبع، لا يُوجَّه إلى أي جهة")

_LBL_NAME = "الاسم الكامل"
_LBL_ROLE = "المهمة"
_LBL_SHIFT = "فترة العمل"
_LBL_PHONE = "الهاتف"
_LBL_CERT = "انتهاء الشهادة الطبية"
_LBL_STATUS = "الحالة"
_LBL_NOTES = "ملاحظات"

_BTN_ADD = "إضافة عضو"
_BTN_ADD_ICON = "➕"
_BTN_SAVE = "حفظ"
_BTN_SAVE_ICON = "💾"
_BTN_CANCEL = "إلغاء"
_BTN_EXPORT = "تصدير اللائحة"
_BTN_EXPORT_ICON = "📄"
_BTN_EDIT = "تعديل"
_BTN_DELETE = "حذف"

_MSG_SAVED = "تم حفظ بيانات العضو."
_MSG_DELETED = "تم حذف العضو من اللائحة."
_MSG_NAME_REQUIRED = "أدخل اسم العضو أولاً."
_MSG_DELETE_CONFIRM = "حذف هذا العضو من لائحة الطاقم نهائياً؟"
_MSG_EXPORT_SAVED = "تم تصدير لائحة الطاقم إلى:\n"
_MSG_EXPORT_FAILED = "تعذر تصدير اللائحة. تحقق من المكان المختار ثم أعد المحاولة."
_MSG_EXPORT_EMPTY = "لا يوجد أي عضو في اللائحة بعد — أضف عضواً أولاً."
_MSG_NO_SETTINGS = "أكمل بيانات المؤسسة من «الإعدادات» أولاً."

_EMPTY_TITLE = "لا يوجد أي عضو في الطاقم بعد"
_EMPTY_HINT = "أضف العاملين في المطبخ للتعرف عليهم ومتابعة شواهدهم الطبية."

_PDF_DIALOG_TITLE = "تصدير لائحة طاقم المطبخ"
_PDF_DEFAULT_NAME = "لائحة_طاقم_المطبخ"
_PDF_FILTER = "PDF (*.pdf)"

_ROLES = [
    "رئيس الطباخين",
    "مساعد طباخ",
    "عامل نظافة",
    "نادل",
    "حارس المخزن",
    "مهمة أخرى",
]
_SHIFTS = ["صباحي", "مسائي", "تناوب"]
_STATUSES = ["حاضر", "غائب", "في عطلة"]

# Certificate state → (Arabic label, colour). The four states come from
# core.staff_certificates; only the wording and colour belong here.
_CERT_LABELS: Dict[str, str] = {
    STATE_VALID: "الشهادة سارية",
    STATE_EXPIRING: "تنتهي قريباً",
    STATE_EXPIRED: "الشهادة منتهية",
    STATE_MISSING: "لا توجد شهادة",
}
_CERT_COLORS: Dict[str, str] = {
    STATE_VALID: COLOR_SUCCESS,
    STATE_EXPIRING: COLOR_WARNING,
    STATE_EXPIRED: COLOR_DANGER,
    STATE_MISSING: COLOR_TEXT_SECONDARY,
}
_STATUS_COLORS: Dict[str, str] = {
    "حاضر": COLOR_SUCCESS,
    "غائب": COLOR_DANGER,
    "في عطلة": COLOR_WARNING,
}

_ALERT_EXPIRED = "شهادة منتهية"
_ALERT_EXPIRING = "شهادة تنتهي قريباً"
_ALERT_MISSING = "بدون شهادة"
_ALERT_TOTAL = "مجموع الطاقم"

_PAGE_BG = COLOR_PAPER
_PANEL_BG = "#ffffff"
_CARD_MIN_WIDTH = 300
_CARDS_PER_ROW = 3

_LOGGER = logging.getLogger(__name__)


def _tint(hex_color: str, alpha: float = 0.13) -> str:
    """A translucent version of a palette colour, as Qt-stylesheet rgba().

    NOT `f"{color}22"`: Qt reads an 8-digit hex string as #AARRGGBB, so
    appending the alpha produced a dark opaque mud colour instead of a light
    tint, and the certificate badges came out unreadable.
    """
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _field_style() -> str:
    return (
        f"background:white; color:{COLOR_TEXT_PRIMARY};"
        f"border:1px solid {COLOR_BORDER}; border-radius:8px;"
        f"padding:6px 10px; font-size:{FONT_BODY}px;"
    )


class _StaffCard(QFrame):
    """One person, at a glance: who they are and whether their شهادة طبية
    still holds."""

    def __init__(self, member: StaffMember, today: datetime.date,
                 on_edit, on_delete) -> None:
        super().__init__()
        self._member = member
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(_CARD_MIN_WIDTH)

        state = certificate_state(member.health_cert_expiry, today)
        accent = _CERT_COLORS[state]
        self.setStyleSheet(f"""
            QFrame {{
                background:{_PANEL_BG};
                border:1px solid {COLOR_BORDER};
                border-top:3px solid {accent};
                border-radius:14px;
            }}
        """)
        self._build(member, state, today, on_edit, on_delete)

    def _build(self, member: StaffMember, state: str, today: datetime.date,
               on_edit, on_delete) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        name = QLabel(member.full_name)
        name_font = QFont()
        name_font.setPointSize(FONT_SECTION)
        name_font.setBold(True)
        name.setFont(name_font)
        name.setWordWrap(True)
        name.setStyleSheet(f"background:transparent; color:{COLOR_TEXT_PRIMARY}; border:none;")
        layout.addWidget(name)

        role_row = QHBoxLayout()
        role_row.setSpacing(6)
        role = QLabel(member.role or "—")
        role.setStyleSheet(
            f"background:transparent; border:none; color:{COLOR_TEXT_SECONDARY};"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        role_row.addWidget(role)
        if member.status:
            role_row.addWidget(self._chip(
                member.status, _STATUS_COLORS.get(member.status, COLOR_TEXT_SECONDARY)))
        role_row.addStretch()
        layout.addLayout(role_row)

        layout.addWidget(self._separator())

        for label, value in (
            (_LBL_SHIFT, member.shift),
            (_LBL_PHONE, member.phone),
        ):
            layout.addLayout(self._detail_row(label, value or "—"))

        layout.addWidget(self._cert_line(member, state, today))

        if member.notes.strip():
            notes = QLabel(member.notes.strip())
            notes.setWordWrap(True)
            notes.setStyleSheet(
                f"background:transparent; border:none; color:{COLOR_TEXT_SECONDARY};"
                f"font-size:{FONT_CAPTION}px;")
            layout.addWidget(notes)

        layout.addStretch()

        actions = QHBoxLayout()
        actions.setSpacing(6)
        edit_btn = QPushButton(_BTN_EDIT)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(self._small_button_style(COLOR_ACCENT))
        edit_btn.clicked.connect(lambda: on_edit(member))
        delete_btn = QPushButton(_BTN_DELETE)
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(self._small_button_style(COLOR_DANGER))
        delete_btn.clicked.connect(lambda: on_delete(member))
        actions.addWidget(edit_btn)
        actions.addWidget(delete_btn)
        actions.addStretch()
        layout.addLayout(actions)

    def _small_button_style(self, color: str) -> str:
        return (
            f"QPushButton {{ background:transparent; color:{color};"
            f"border:1px solid {color}; border-radius:8px;"
            f"padding:4px 12px; font-size:{FONT_CAPTION}px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:{color}; color:white; }}"
        )

    def _chip(self, text: str, color: str) -> QLabel:
        chip = QLabel(text)
        chip.setStyleSheet(
            f"background:{color}; color:white; border:none; border-radius:7px;"
            f"padding:2px 8px; font-size:{FONT_CAPTION}px; font-weight:bold;")
        return chip

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{COLOR_BORDER}; border:none; background:{COLOR_BORDER};")
        line.setFixedHeight(1)
        return line

    def _detail_row(self, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        key = QLabel(f"{label}:")
        key.setStyleSheet(
            f"background:transparent; border:none; color:{COLOR_TEXT_SECONDARY};"
            f"font-size:{FONT_CAPTION}px;")
        val = QLabel(value)
        val.setStyleSheet(
            f"background:transparent; border:none; color:{COLOR_TEXT_PRIMARY};"
            f"font-size:{FONT_LABEL}px; font-weight:bold;")
        row.addWidget(key)
        row.addWidget(val)
        row.addStretch()
        return row

    def _cert_line(self, member: StaffMember, state: str,
                   today: datetime.date) -> QWidget:
        """The reason this screen exists — spelled out, not just colour-coded,
        so it still reads correctly in a black-and-white printout or to
        someone who cannot distinguish the colours."""
        remaining = days_until_expiry(member.health_cert_expiry, today)
        text = _CERT_LABELS[state]
        if state == STATE_EXPIRED and remaining is not None:
            text = f"{text} — منذ {abs(remaining)} يوم"
        elif state == STATE_EXPIRING and remaining is not None:
            text = f"{text} — بقي {remaining} يوم" if remaining else f"{text} — تنتهي اليوم"
        elif state == STATE_VALID and member.health_cert_expiry:
            text = f"{text} — إلى {_display_date(member.health_cert_expiry)}"

        holder = QWidget()
        holder.setStyleSheet("background:transparent; border:none;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)
        badge = QLabel(text)
        badge.setWordWrap(True)
        badge.setStyleSheet(
            f"background:{_tint(_CERT_COLORS[state])}; color:{_CERT_COLORS[state]};"
            f"border:1px solid {_CERT_COLORS[state]}; border-radius:8px;"
            f"padding:4px 10px; font-size:{FONT_CAPTION}px; font-weight:bold;")
        row.addWidget(badge)
        row.addStretch()
        return holder


def _display_date(iso: str) -> str:
    """ISO to the dd/mm/yyyy the user reads on paper."""
    try:
        year, month, day = iso.split("-")
        return f"{day}/{month}/{year}"
    except ValueError:
        return iso


class StaffScreen(QWidget):
    """طاقم المطبخ — cards, an add/edit form, and a printable list."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"background:{_PAGE_BG};")
        self._members: List[StaffMember] = []
        self._editing: Optional[StaffMember] = None
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
        inner.setSpacing(18)

        inner.addLayout(self._build_header())
        inner.addWidget(self._build_alerts())
        inner.addWidget(self._build_form())
        inner.addWidget(self._build_cards_area(), 1)

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

        self._export_btn = IconButton(
            _BTN_EXPORT, icon=_BTN_EXPORT_ICON, bg=COLOR_ACCENT, min_height=38)
        self._export_btn.clicked.connect(self._on_export)
        row.addWidget(self._export_btn)
        return row

    def _build_alerts(self) -> QWidget:
        """Four counters — the whole point of opening this screen is spotting
        a certificate problem without reading every card."""
        panel = QWidget()
        panel.setStyleSheet("background:transparent;")
        row = QHBoxLayout(panel)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self._alert_labels: Dict[str, QLabel] = {}
        for key, label, color in (
            ("total", _ALERT_TOTAL, COLOR_ACCENT),
            (STATE_EXPIRED, _ALERT_EXPIRED, COLOR_DANGER),
            (STATE_EXPIRING, _ALERT_EXPIRING, COLOR_WARNING),
            (STATE_MISSING, _ALERT_MISSING, COLOR_TEXT_SECONDARY),
        ):
            card = QFrame()
            card.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            card.setStyleSheet(
                f"QFrame {{ background:{_PANEL_BG}; border:1px solid {COLOR_BORDER};"
                f"border-right:4px solid {color}; border-radius:12px; }}")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 10, 14, 10)
            box.setSpacing(2)
            value = QLabel("0")
            value_font = QFont()
            value_font.setPointSize(FONT_SECTION + 4)
            value_font.setBold(True)
            value.setFont(value_font)
            value.setStyleSheet(f"color:{color}; background:transparent; border:none;")
            caption = QLabel(label)
            caption.setStyleSheet(
                f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
                f"font-size:{FONT_CAPTION}px;")
            box.addWidget(value)
            box.addWidget(caption)
            self._alert_labels[key] = value
            row.addWidget(card, 1)
        return panel

    def _build_form(self) -> QWidget:
        panel = QFrame()
        panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        panel.setStyleSheet(
            f"QFrame {{ background:{_PANEL_BG}; border:1px solid {COLOR_BORDER};"
            f"border-radius:14px; }}")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setMinimumHeight(34)
        self._name_edit.setStyleSheet(_field_style())

        self._role_combo = QComboBox()
        self._role_combo.addItems(_ROLES)
        self._role_combo.setMinimumHeight(34)
        self._role_combo.setStyleSheet(_field_style())

        self._shift_combo = QComboBox()
        self._shift_combo.addItems(_SHIFTS)
        self._shift_combo.setMinimumHeight(34)
        self._shift_combo.setStyleSheet(_field_style())

        self._phone_edit = QLineEdit()
        self._phone_edit.setMinimumHeight(34)
        self._phone_edit.setStyleSheet(_field_style())

        self._cert_input = DateInput()
        self._cert_input.setMinimumHeight(34)
        self._cert_input.setStyleSheet(_field_style())

        self._status_combo = QComboBox()
        self._status_combo.addItems(_STATUSES)
        self._status_combo.setMinimumHeight(34)
        self._status_combo.setStyleSheet(_field_style())

        self._notes_edit = QLineEdit()
        self._notes_edit.setMinimumHeight(34)
        self._notes_edit.setStyleSheet(_field_style())

        fields = [
            (_LBL_NAME, self._name_edit),
            (_LBL_ROLE, self._role_combo),
            (_LBL_SHIFT, self._shift_combo),
            (_LBL_PHONE, self._phone_edit),
            (_LBL_CERT, self._cert_input),
            (_LBL_STATUS, self._status_combo),
        ]
        for index, (label, widget) in enumerate(fields):
            column = index % 3
            row = (index // 3) * 2
            grid.addWidget(self._form_label(label), row, column)
            grid.addWidget(widget, row + 1, column)

        notes_row = (len(fields) // 3) * 2
        grid.addWidget(self._form_label(_LBL_NOTES), notes_row, 0, 1, 3)
        grid.addWidget(self._notes_edit, notes_row + 1, 0, 1, 3)
        outer.addLayout(grid)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._save_btn = IconButton(
            _BTN_SAVE, icon=_BTN_SAVE_ICON, bg=COLOR_ACCENT, min_height=36)
        self._save_btn.clicked.connect(self._on_save)
        self._cancel_btn = QPushButton(_BTN_CANCEL)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setMinimumHeight(36)
        self._cancel_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{COLOR_TEXT_SECONDARY};"
            f"border:1px solid {COLOR_BORDER}; border-radius:8px;"
            f"padding:6px 18px; font-size:{FONT_LABEL}px; }}")
        self._cancel_btn.clicked.connect(self._clear_form)
        buttons.addWidget(self._save_btn)
        buttons.addWidget(self._cancel_btn)
        buttons.addStretch()
        outer.addLayout(buttons)
        return panel

    def _form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:transparent; border:none;"
            f"font-size:{FONT_CAPTION}px; font-weight:bold;")
        return label

    def _build_cards_area(self) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background:transparent;")
        self._cards_layout = QGridLayout(holder)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(14)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._empty_label = QLabel(f"{_EMPTY_TITLE}\n{_EMPTY_HINT}")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color:{COLOR_TEXT_SECONDARY}; background:{_PANEL_BG};"
            f"border:1px dashed {COLOR_BORDER}; border-radius:14px;"
            f"padding:34px; font-size:{FONT_LABEL}px;")
        return holder

    # ── Data ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Re-read the team when the page is opened."""
        self._reload()

    def _today(self) -> datetime.date:
        return datetime.date.today()

    def _reload(self) -> None:
        self._members = get_all_staff()
        self._rebuild_cards()
        self._update_alerts()

    def _rebuild_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()          # deleteLater() is deferred; hide now so
                widget.setParent(None)  # the old cards cannot ghost behind
                widget.deleteLater()

        if not self._members:
            self._cards_layout.addWidget(self._empty_label, 0, 0, 1, _CARDS_PER_ROW)
            self._empty_label.show()
            return

        self._empty_label.hide()
        today = self._today()
        # Anything needing attention first — the reason to open this screen.
        ordered = sorted(
            self._members,
            key=lambda m: (not needs_attention(m.health_cert_expiry, today),
                           m.full_name),
        )
        for position, member in enumerate(ordered):
            card = _StaffCard(member, today, self._on_edit, self._on_delete)
            self._cards_layout.addWidget(
                card, position // _CARDS_PER_ROW, position % _CARDS_PER_ROW)

    def _update_alerts(self) -> None:
        today = self._today()
        counts = {STATE_EXPIRED: 0, STATE_EXPIRING: 0, STATE_MISSING: 0}
        for member in self._members:
            state = certificate_state(member.health_cert_expiry, today)
            if state in counts:
                counts[state] += 1
        self._alert_labels["total"].setText(str(len(self._members)))
        for key, value in counts.items():
            self._alert_labels[key].setText(str(value))

    # ── Actions ─────────────────────────────────────────────────────────────

    def _clear_form(self) -> None:
        self._editing = None
        self._name_edit.clear()
        self._phone_edit.clear()
        self._notes_edit.clear()
        self._role_combo.setCurrentIndex(0)
        self._shift_combo.setCurrentIndex(0)
        self._status_combo.setCurrentIndex(0)

    def _on_edit(self, member: StaffMember) -> None:
        self._editing = member
        self._name_edit.setText(member.full_name)
        self._phone_edit.setText(member.phone)
        self._notes_edit.setText(member.notes)
        if member.role in _ROLES:
            self._role_combo.setCurrentText(member.role)
        if member.shift in _SHIFTS:
            self._shift_combo.setCurrentText(member.shift)
        if member.status in _STATUSES:
            self._status_combo.setCurrentText(member.status)
        expiry = member.health_cert_expiry
        if expiry:
            from PySide6.QtCore import QDate
            parsed = QDate.fromString(expiry, "yyyy-MM-dd")
            if parsed.isValid():
                self._cert_input.setDate(parsed)

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.information(self, _TITLE, _MSG_NAME_REQUIRED)
            return
        member = self._editing or StaffMember(full_name=name)
        member.full_name = name
        member.role = self._role_combo.currentText()
        member.shift = self._shift_combo.currentText()
        member.phone = self._phone_edit.text().strip()
        member.health_cert_expiry = self._cert_input.date().toString("yyyy-MM-dd")
        member.status = self._status_combo.currentText()
        member.notes = self._notes_edit.text().strip()
        try:
            save_staff_member(member)
        except Exception:
            _LOGGER.exception("saving a staff member failed")
            QMessageBox.critical(self, _TITLE, _MSG_EXPORT_FAILED)
            return
        self._clear_form()
        self._reload()
        QMessageBox.information(self, _TITLE, _MSG_SAVED)

    def _on_delete(self, member: StaffMember) -> None:
        reply = QMessageBox.question(
            self, _TITLE, f"{member.full_name}\n\n{_MSG_DELETE_CONFIRM}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if member.id is not None:
            delete_staff_member(member.id)
        if self._editing is member:
            self._clear_form()
        self._reload()
        QMessageBox.information(self, _TITLE, _MSG_DELETED)

    def _on_export(self) -> None:
        if not self._members:
            QMessageBox.information(self, _TITLE, _MSG_EXPORT_EMPTY)
            return
        settings = get_school_settings()
        if settings is None:
            QMessageBox.information(self, _TITLE, _MSG_NO_SETTINGS)
            return
        path_str, _filter = QFileDialog.getSaveFileName(
            self, _PDF_DIALOG_TITLE, _PDF_DEFAULT_NAME, _PDF_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            write_staff_pdf(path, self._members, settings, self._today())
        except Exception:
            _LOGGER.exception("exporting the staff list failed")
            QMessageBox.critical(self, _TITLE, _MSG_EXPORT_FAILED)
            return
        QMessageBox.information(self, _TITLE, f"{_MSG_EXPORT_SAVED}{path}")
