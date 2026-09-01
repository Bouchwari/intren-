"""
src/ui/staff_export.py
The printable لائحة طاقم المطبخ — a card per person, meant to be pinned up in
the office and read across a room.

There is no official ministry form for kitchen staff, so nothing here is
reproducing a template: this is our own layout, and it is built to be SCANNED
rather than read line by line — big names, one card each, and the شهادة طبية
state spelled out in words as well as colour so it survives a black-and-white
printer and a reader who cannot tell the colours apart.
"""
import datetime
from pathlib import Path
from typing import List, Sequence, Tuple

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter,
    QPen,
)

from config.settings import (
    COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_WARNING,
)
from core.models import SchoolSettings, StaffMember
from core.staff_certificates import (
    STATE_EXPIRED, STATE_EXPIRING, STATE_MISSING, STATE_VALID,
    certificate_state, days_until_expiry,
)
from ui.document_header import draw_official_pdf_header

_TITLE = "لائحة طاقم المطبخ"
_SUBTITLE = "التعريف بالعاملين بمطعم المؤسسة ومراقبة صلاحية الشواهد الطبية"
_LBL_SHIFT = "فترة العمل"
_LBL_PHONE = "الهاتف"
_LBL_PRINTED = "تاريخ الطبع"
_LBL_COUNT = "عدد أعضاء الطاقم"
_LBL_COMPANY = "الشركة النائلة"
_NONE = "—"

_CERT_LABELS = {
    STATE_VALID: "الشهادة الطبية سارية",
    STATE_EXPIRING: "الشهادة الطبية تنتهي قريباً",
    STATE_EXPIRED: "الشهادة الطبية منتهية",
    STATE_MISSING: "لا توجد شهادة طبية",
}
_CERT_COLORS = {
    STATE_VALID: COLOR_SUCCESS,
    STATE_EXPIRING: COLOR_WARNING,
    STATE_EXPIRED: COLOR_DANGER,
    STATE_MISSING: COLOR_TEXT_SECONDARY,
}

# Two columns of cards on A4 portrait reads comfortably at arm's length; three
# would shrink the names past the point of being useful pinned to a wall.
_COLUMNS = 2
# Padding inside a card, and the fixed gaps between its parts. The card's
# HEIGHT is not a constant: it is measured from the tallest member's real
# content (see _card_height) because guessing it twice already produced a
# badge that overflowed the card, then one that overlapped the details line.
_CARD_PAD_TOP = 12.0
_CARD_PAD_BOTTOM = 10.0
_GAP_NAME_ROLE = 3.0
_GAP_ROLE_RULE = 8.0
_GAP_RULE_DETAILS = 8.0
_GAP_DETAILS_BADGE = 8.0
_BADGE_PAD = 8.0
_CARD_GAP = 14.0
_MARGIN = 42.0
_CARD_RADIUS = 10.0
_ACCENT_BAR = 4.0

_NAME_SIZE = 13
_ROLE_SIZE = 10
_DETAIL_SIZE = 9
_CERT_SIZE = 9
_META_SIZE = 9


def _display_date(iso: str) -> str:
    try:
        year, month, day = iso.split("-")
        return f"{day}/{month}/{year}"
    except ValueError:
        return iso


def _text(painter: QPainter, rect: QRectF, value: str, *, size: int,
          color: str, bold: bool = False,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight) -> float:
    """Draw wrapped text and return the height it actually used.

    drawText(QRectF, ...) CLIPS to the rect it is handed, so a guessed height
    silently loses the tail of a long name — measure first, then draw.
    """
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    flags = int(align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)
    metrics = QFontMetricsF(font)
    needed = metrics.boundingRect(
        QRectF(rect.left(), rect.top(), rect.width(), 10000.0), flags, value)
    height = max(rect.height(), needed.height())
    painter.drawText(
        QRectF(rect.left(), rect.top(), rect.width(), height), flags, value)
    return height


def _cert_text(member: StaffMember, state: str, today: datetime.date) -> str:
    """Spelled out, never colour alone — this has to work in greyscale."""
    label = _CERT_LABELS[state]
    remaining = days_until_expiry(member.health_cert_expiry, today)
    if state == STATE_EXPIRED and remaining is not None:
        return f"{label} منذ {abs(remaining)} يوم ({_display_date(member.health_cert_expiry)})"
    if state == STATE_EXPIRING and remaining is not None:
        if remaining == 0:
            return f"{label} — تنتهي اليوم"
        return f"{label} — بقي {remaining} يوم ({_display_date(member.health_cert_expiry)})"
    if state == STATE_VALID:
        return f"{label} إلى غاية {_display_date(member.health_cert_expiry)}"
    return label


def _measured_height(text: str, width: float, size: int, bold: bool = False) -> float:
    """How tall wrapped text will actually be — drawText CLIPS to its rect."""
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    flags = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap)
    return QFontMetricsF(font).boundingRect(
        QRectF(0, 0, width, 10000.0), flags, text).height()


def _card_parts(member: StaffMember, inner_width: float,
                today: datetime.date) -> Tuple[str, str, str, float, float, float, float]:
    """Every line of a card plus its measured height, in one place so the
    layout and the height calculation can never disagree."""
    state = certificate_state(member.health_cert_expiry, today)
    role_line = member.role or _NONE
    if member.status:
        role_line = f"{role_line}  ·  {member.status}"
    details = (f"{_LBL_SHIFT}: {member.shift or _NONE}"
               f"    ·    {_LBL_PHONE}: {member.phone or _NONE}")
    badge_text = _cert_text(member, state, today)
    return (
        state, role_line, details,
        _measured_height(member.full_name, inner_width, _NAME_SIZE, True),
        _measured_height(role_line, inner_width, _ROLE_SIZE, True),
        _measured_height(details, inner_width, _DETAIL_SIZE),
        _measured_height(badge_text, inner_width - 16.0, _CERT_SIZE, True),
    )


def _card_height(members: Sequence[StaffMember], inner_width: float,
                 today: datetime.date) -> float:
    """One height for every card — the tallest member's real requirement, so
    the grid stays even AND nothing is ever clipped or overlapped."""
    tallest = 0.0
    for member in members:
        _state, _role, _details, name_h, role_h, details_h, badge_h = _card_parts(
            member, inner_width, today)
        tallest = max(tallest, (
            _CARD_PAD_TOP + name_h + _GAP_NAME_ROLE + role_h + _GAP_ROLE_RULE
            + 1.0 + _GAP_RULE_DETAILS + details_h + _GAP_DETAILS_BADGE
            + badge_h + _BADGE_PAD + _CARD_PAD_BOTTOM
        ))
    return tallest


def _draw_card(painter: QPainter, rect: QRectF, member: StaffMember,
               today: datetime.date) -> None:
    state = certificate_state(member.health_cert_expiry, today)
    accent = QColor(_CERT_COLORS[state])

    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(rect, _CARD_RADIUS, _CARD_RADIUS)

    # A coloured bar down the leading (right, in RTL) edge — the fastest thing
    # to spot when scanning a wall of cards.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(accent)
    painter.drawRoundedRect(
        QRectF(rect.right() - _ACCENT_BAR, rect.top() + 6.0,
               _ACCENT_BAR, rect.height() - 12.0),
        _ACCENT_BAR / 2, _ACCENT_BAR / 2)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    inner_left = rect.left() + 14.0
    inner_width = rect.width() - 28.0 - _ACCENT_BAR
    _state, role_line, details, name_h, role_h, details_h, badge_body_h = _card_parts(
        member, inner_width, today)
    badge_text = _cert_text(member, state, today)

    y = rect.top() + _CARD_PAD_TOP
    _text(painter, QRectF(inner_left, y, inner_width, name_h),
          member.full_name, size=_NAME_SIZE, color=COLOR_TEXT_PRIMARY, bold=True)
    y += name_h + _GAP_NAME_ROLE

    _text(painter, QRectF(inner_left, y, inner_width, role_h), role_line,
          size=_ROLE_SIZE, color=COLOR_TEXT_SECONDARY, bold=True)
    y += role_h + _GAP_ROLE_RULE

    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.drawLine(QRectF(inner_left, y, inner_width, 0).topLeft(),
                     QRectF(inner_left, y, inner_width, 0).topRight())
    y += 1.0 + _GAP_RULE_DETAILS

    _text(painter, QRectF(inner_left, y, inner_width, details_h), details,
          size=_DETAIL_SIZE, color=COLOR_TEXT_PRIMARY)
    y += details_h + _GAP_DETAILS_BADGE

    badge_rect = QRectF(inner_left, y, inner_width, badge_body_h + _BADGE_PAD)
    painter.setPen(QPen(accent, 1))
    fill = QColor(accent)
    fill.setAlpha(28)
    painter.setBrush(fill)
    painter.drawRoundedRect(badge_rect, 6.0, 6.0)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _text(painter, QRectF(badge_rect.left() + 8.0, badge_rect.top() + 4.0,
                          badge_rect.width() - 16.0, badge_body_h),
          badge_text, size=_CERT_SIZE, color=_CERT_COLORS[state], bold=True)


def _draw_meta_line(painter: QPainter, left: float, top: float, width: float,
                    settings: SchoolSettings, count: int,
                    today: datetime.date) -> float:
    company = (settings.company_name or "").strip()
    parts = [f"{_LBL_COUNT}: {count}"]
    if company:
        parts.append(f"{_LBL_COMPANY}: {company}")
    parts.append(f"{_LBL_PRINTED}: {_display_date(today.isoformat())}")
    return _text(painter, QRectF(left, top, width, 14.0),
                 "    ·    ".join(parts), size=_META_SIZE,
                 color=COLOR_TEXT_SECONDARY)


def _sorted_for_print(members: Sequence[StaffMember],
                      today: datetime.date) -> List[StaffMember]:
    """Certificates needing attention first, so the top of page 1 is the part
    that actually needs doing something about."""
    priority = {STATE_EXPIRED: 0, STATE_EXPIRING: 1, STATE_MISSING: 2, STATE_VALID: 3}
    return sorted(
        members,
        key=lambda m: (priority[certificate_state(m.health_cert_expiry, today)],
                       m.full_name),
    )


def write_staff_pdf(path: Path, members: Sequence[StaffMember],
                    settings: SchoolSettings,
                    today: datetime.date) -> None:
    """Render the whole team as a multi-page card sheet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TITLE)

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        page_w = float(writer.width())
        page_h = float(writer.height())
        content_w = page_w - (_MARGIN * 2)
        card_w = (content_w - _CARD_GAP * (_COLUMNS - 1)) / _COLUMNS

        ordered = _sorted_for_print(members, today)
        card_height = _card_height(ordered, card_w - 28.0 - _ACCENT_BAR, today)
        index = 0
        first_page = True
        while index < len(ordered):
            if not first_page:
                writer.newPage()
            first_page = False

            y = draw_official_pdf_header(
                painter, page_width=page_w, margin=_MARGIN, top=16.0,
                settings=settings, title=_TITLE,
            )
            y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0), _SUBTITLE,
                       size=_META_SIZE, color=COLOR_TEXT_SECONDARY) + 4.0
            y += _draw_meta_line(painter, _MARGIN, y, content_w, settings,
                                 len(ordered), today) + 14.0

            while index < len(ordered) and y + card_height <= page_h - _MARGIN:
                for column in range(_COLUMNS):
                    if index >= len(ordered):
                        break
                    # RTL: the first card of a row sits on the RIGHT.
                    left = _MARGIN + (_COLUMNS - 1 - column) * (card_w + _CARD_GAP)
                    _draw_card(painter,
                               QRectF(left, y, card_w, card_height),
                               ordered[index], today)
                    index += 1
                y += card_height + _CARD_GAP
    finally:
        painter.end()
