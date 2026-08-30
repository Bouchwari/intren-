"""
src/ui/dashboard_export.py
تقرير الإحصائيات — the statistics screen as a signed PDF the مسير can file.

Everything on الإحصائيات that is worth carrying on paper: the month's headline
figures, how the months compare, when absence happens and to whom, who rated
the meals, and which days still owe paperwork.

The drawing primitives are IMPORTED from ui/feedback_export.py rather than
copied. They already carry three fixes that took a render each to find — text
rects are measured before drawing (QPainter clips silently), a bar's value gets
its own column (a long bar covered it), and a rating chart can pin its scale so
small differences are not exaggerated. Same precedent as monthly_reception_
screen.py reusing daily_reception_screen.py's helpers.
"""
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

from config.settings import (
    COLOR_ACCENT, COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_WARNING,
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA,
)
from core.analytics import (
    AbsencePatterns, Completeness, MonthPoint, absence_patterns,
    document_completeness, monthly_trend,
)
from core.feedback import summarize_by_attribute, ungrouped_responses
from core.models import SchoolSettings
from core.student_stats import (
    profile_by_cycle, profile_by_gender, summarize_students,
)
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header
from ui.feedback_export import _bar_chart, _cell, _kpi_box, _section, _text

_TITLE = "تقرير الإحصائيات"
_SUBTITLE = "ملخص تدبير المطعمة المدرسية"
_LBL_MONTH = "الشهر"
_LBL_GENERATED = "تاريخ التقرير"

_SEC_HEADLINE = "أرقام الشهر"
_SEC_TREND = "اتجاهات شهرية"
_SEC_ABSENCE = "أنماط الغياب"
_SEC_FEEDBACK = "من أبدى الرأي"
_SEC_COMPLETENESS = "اكتمال الوثائق"
_SEC_CLASSES = "التلاميذ حسب القسم"
_CLASS_HDR = ["القسم", "ذكور", "إناث", "المجموع"]
_CLASS_UNSPECIFIED = "غير محدد"
_CLASS_TOTAL_LINE = ("المجموع العام: {total:,} تلميذ  ·  {male:,} ذكور  ·  "
                     "{female:,} إناث")
_STACK_BAR_H = 17.0
_STACK_GAP = 5.0
# Kept in step with dashboard_deep._GENDER_COLORS — the same split on paper
# and on screen must read as the same two colours.
_GENDER_COLORS = {"male": COLOR_ACCENT, "female": "#8C6BB1", "": "#B8B8AC"}
_NO_STUDENTS = "لم تُستورد لائحة التلاميذ بعد."
_CLASS_UNKNOWN_GENDER = "تلاميذ بدون جنس مسجَّل: {count:,}"

_KPI_STUDENTS = "المستفيدون"
_KPI_MEALS = "وجبات الشهر"
_KPI_PER_DAY = "المعدل اليومي"
_KPI_DAYS = "أيام الخدمة"
_KPI_ABSENCE = "نسبة الغياب"
_KPI_COMPLETE = "اكتمال الوثائق"

_TREND_HDR = ["الشهر", "الوجبات", "أيام", "المعدل اليومي", "التكلفة"]
_COST_PARTIAL_MARK = "*"
_COST_PARTIAL_NOTE = ("* لا تشمل التكلفة وجبات رمضان — لم يُحدَّد لها ثمن في "
                      "الإعدادات.")
_ABSENCE_BY_DAY = "حسب يوم الأسبوع"
_ABSENCE_BY_CYCLE = "حسب السلك"
_COMPLETENESS_NOTE = ("تُحتسب الأيام التي سُجِّلت فيها ورقة اتصال أو غياب فقط.")
_GAPS_TITLE = "أيام ينقصها توثيق"
_GAP_MORE = "… و{count} يوماً آخر"
_NONE = "—"
_NO_DATA = "لا توجد بيانات لهذا الشهر."
_NO_ABSENCE = "لم يُسجَّل غياب في هذا الشهر."
_NO_FEEDBACK = "لم تُسجَّل آراء موزَّعة على الفئات."
_NO_GAPS = "كل الأيام المسجَّلة موثَّقة بالكامل."
_UNGROUPED = "آراء بدون تصنيف: {count:,}"

_SIGN_ROLES = ["الحارس(ة) العام(ة) للداخلية",
               "مسير المصالح المادية والمالية", "مدير(ة) المؤسسة"]

_WEEKDAY_LABELS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة",
                   "السبت", "الأحد"]
_CYCLE_LABELS = {"primary": "ابتدائي", "collegial": "إعدادي",
                 "qualifying": "تأهيلي", "monitors": "معلمو الداخلية"}
_GENDER_LABELS = {"male": "ذكور", "female": "إناث"}
_DOCUMENT_LABELS = {
    "contact": "ورقة الاتصال", "absence": "ورقة الغياب",
    "report": "التقرير اليومي", "order_letter": "رسالة الطلبية",
    "reception": "محضر التسلم",
}
_ARABIC_MONTHS = ["", "يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو",
                  "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر"]

_MARGIN = 44.0
_ROW_HEIGHT = 19.0
_HEADER_ROW_HEIGHT = 22.0
_SECTION_GAP = 12.0
_BODY_SIZE = 9
_META_SIZE = 9
_KPI_BOX_HEIGHT = 46.0
_KPI_GAP = 8.0
_BAR_ROW_H = 21.0
_GAP_LIMIT = 10
_TREND_SHARE = (0.24, 0.20, 0.14, 0.20, 0.22)


def month_label(month: str) -> str:
    try:
        year, number = month.split("-")
        return f"{_ARABIC_MONTHS[int(number)]} {year}"
    except (ValueError, IndexError):
        return month


def month_bounds(month: str) -> tuple:
    year, number = (int(part) for part in month.split("-"))
    first = datetime.date(year, number, 1)
    last = (datetime.date(year + (number == 12), (number % 12) + 1, 1)
            - datetime.timedelta(days=1))
    return first.isoformat(), last.isoformat()


def _row(painter: QPainter, left: float, y: float, widths: Sequence[float],
         values: Sequence[str], *, header: bool = False) -> float:
    def column_left(index: int) -> float:
        return left + sum(widths[index + 1:])

    height = _HEADER_ROW_HEIGHT if header else _ROW_HEIGHT
    for index, value in enumerate(values):
        _cell(painter, QRectF(column_left(index), y, widths[index], height),
              str(value), bold=header, fill="#F7F7F4" if header else "")
    return y + height


def _draw_headline(painter: QPainter, left: float, y: float, width: float,
                   *, students: int, point: Optional[MonthPoint],
                   patterns: AbsencePatterns,
                   completeness: Completeness) -> float:
    """The month's six headline figures.

    A figure that cannot honestly be produced prints "—", never a zero: an
    average over no days and a rate with no roster behind it are not numbers.
    """
    y = _section(painter, left, y, width, _SEC_HEADLINE) + 6.0
    rate = patterns.rate
    complete = completeness.rate
    per_day = point.meals_per_day if point else None
    boxes = [
        (f"{students:,}", _KPI_STUDENTS, COLOR_TEXT_PRIMARY),
        (f"{point.meals:,}" if point else _NONE, _KPI_MEALS, COLOR_ACCENT),
        (f"{per_day:,.0f}" if per_day is not None else _NONE, _KPI_PER_DAY,
         COLOR_TEXT_PRIMARY),
        (f"{point.days:,}" if point else _NONE, _KPI_DAYS, COLOR_TEXT_PRIMARY),
        (f"{rate:.1%}" if rate is not None else _NONE, _KPI_ABSENCE,
         COLOR_DANGER if rate and rate > 0.1 else COLOR_WARNING),
        (f"{complete:.0%}" if complete is not None else _NONE, _KPI_COMPLETE,
         COLOR_SUCCESS if complete == 1 else COLOR_WARNING),
    ]
    per_row = 3
    box_w = (width - _KPI_GAP * (per_row - 1)) / per_row
    for index, (value, caption, color) in enumerate(boxes):
        column = index % per_row
        row = index // per_row
        # RTL: the first box on the right.
        box_left = left + (per_row - 1 - column) * (box_w + _KPI_GAP)
        _kpi_box(painter,
                 QRectF(box_left, y + row * (_KPI_BOX_HEIGHT + _KPI_GAP),
                        box_w, _KPI_BOX_HEIGHT),
                 value, caption, color)
    rows = (len(boxes) + per_row - 1) // per_row
    return y + rows * (_KPI_BOX_HEIGHT + _KPI_GAP) + _SECTION_GAP


def _draw_trend(painter: QPainter, left: float, y: float, width: float,
                points: Sequence[MonthPoint]) -> float:
    y = _section(painter, left, y, width, _SEC_TREND)
    if not points:
        _cell(painter, QRectF(left, y, width, _ROW_HEIGHT), _NO_DATA,
              color=COLOR_TEXT_SECONDARY)
        return y + _ROW_HEIGHT + _SECTION_GAP

    widths = [width * share for share in _TREND_SHARE]
    y = _row(painter, left, y, widths, _TREND_HDR, header=True)
    for point in reversed(points):          # newest first
        per_day = point.meals_per_day
        y = _row(painter, left, y, widths, [
            month_label(point.month),
            f"{point.meals:,}",
            f"{point.days}",
            f"{per_day:,.0f}" if per_day is not None else _NONE,
            f"{point.cost:,.2f}"
            + (_COST_PARTIAL_MARK if point.cost_is_partial else ""),
        ])
    if any(point.cost_is_partial for point in points):
        y += _text(painter, QRectF(left, y + 3, width, 14.0),
                   _COST_PARTIAL_NOTE, size=8,
                   color=COLOR_TEXT_SECONDARY) + 3
    return y + _SECTION_GAP


def _draw_stacked_bars(painter: QPainter, left: float, y: float, width: float,
                       rows: Sequence[tuple],
                       legend: Sequence[tuple]) -> float:
    """One bar per row, split into coloured segments, drawn right-to-left.

    A segment carries its own number only when it is wide enough to hold it —
    measured with QFontMetricsF, since QPainter would otherwise spill the text
    over the neighbouring segment. Bars are scaled to the largest row total so
    their lengths compare across rows.
    """
    from PySide6.QtGui import QColor, QFont, QFontMetricsF

    if not rows:
        return 0.0
    top = y
    label_font = QFont(); label_font.setPointSize(_BODY_SIZE)
    value_font = QFont(); value_font.setPointSize(8)
    label_metrics = QFontMetricsF(label_font)
    value_metrics = QFontMetricsF(value_font)

    painter.setFont(value_font)
    right = left + width
    for text, colour in legend:
        text_w = value_metrics.horizontalAdvance(text)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.drawRoundedRect(QRectF(right - 9, y + 3, 9, 9), 2, 2)
        painter.setPen(QColor(COLOR_TEXT_SECONDARY))
        painter.drawText(QRectF(right - 12 - text_w, y, text_w, _STACK_BAR_H),
                         int(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter), text)
        right -= text_w + 12 + 12
    y += _STACK_BAR_H

    label_w = max(label_metrics.horizontalAdvance(str(row[0]))
                  for row in rows) + 10
    total_w = max(label_metrics.horizontalAdvance(f"{row[2]:,}")
                  for row in rows) + 10
    track_w = max(30.0, width - label_w - total_w - 12)
    largest = max((row[2] for row in rows), default=1) or 1

    for label, segments, total in rows:
        painter.setFont(label_font)
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        painter.drawText(QRectF(left + width - label_w, y, label_w,
                                _STACK_BAR_H),
                         int(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter), str(label))

        track_x = left + total_w + 6
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#EFEFE8"))
        painter.drawRoundedRect(
            QRectF(track_x, y + 3, track_w, _STACK_BAR_H - 6), 3, 3)

        right_edge = track_x + track_w      # RTL: first segment on the right
        for value, colour in segments:
            if value <= 0:
                continue
            segment_w = track_w * value / largest
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colour))
            painter.drawRoundedRect(
                QRectF(right_edge - segment_w, y + 3, segment_w,
                       _STACK_BAR_H - 6), 3, 3)
            text = f"{value:,}"
            if value_metrics.horizontalAdvance(text) + 8 <= segment_w:
                painter.setFont(value_font)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(
                    QRectF(right_edge - segment_w, y, segment_w, _STACK_BAR_H),
                    int(Qt.AlignmentFlag.AlignHCenter
                        | Qt.AlignmentFlag.AlignVCenter), text)
            right_edge -= segment_w
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.setFont(label_font)
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        painter.drawText(QRectF(left, y, total_w, _STACK_BAR_H),
                         int(Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignVCenter), f"{total:,}")
        y += _STACK_BAR_H + _STACK_GAP
    return y - top


def _draw_classes(painter: QPainter, left: float, y: float, width: float,
                  students: Sequence) -> float:
    """Every class as a stacked bar — ذكور and إناث in one length.

    Rows come from the SCREEN's own builder (ui.dashboard_deep), so the
    printed chart and الإحصائيات can never disagree about a class.
    """
    from ui.dashboard_deep import class_chart_rows

    y = _section(painter, left, y, width, _SEC_CLASSES)
    if not students:
        _cell(painter, QRectF(left, y, width, _ROW_HEIGHT), _NO_STUDENTS,
              color=COLOR_TEXT_SECONDARY)
        return y + _ROW_HEIGHT + _SECTION_GAP
    y += 4.0

    rows, totals = class_chart_rows(students)
    legend = [(_CLASS_HDR[1], _GENDER_COLORS["male"]),
              (_CLASS_HDR[2], _GENDER_COLORS["female"])]
    if totals["unknown"]:
        legend.append((_CLASS_UNSPECIFIED, _GENDER_COLORS[""]))
    y += _draw_stacked_bars(painter, left, y, width, rows, legend)

    y += _text(painter, QRectF(left, y + 2, width, 14.0),
               _CLASS_TOTAL_LINE.format(total=totals["all"],
                                        male=totals["male"],
                                        female=totals["female"]),
               size=8, color=COLOR_TEXT_PRIMARY, bold=True) + 2
    if totals["unknown"]:
        y += _text(painter, QRectF(left, y, width, 14.0),
                   _CLASS_UNKNOWN_GENDER.format(count=totals["unknown"]),
                   size=8, color=COLOR_TEXT_SECONDARY)
    return y + _SECTION_GAP


def _draw_absence(painter: QPainter, left: float, y: float, width: float,
                  patterns: AbsencePatterns) -> float:
    y = _section(painter, left, y, width, _SEC_ABSENCE)
    if not patterns.total_absent:
        _cell(painter, QRectF(left, y, width, _ROW_HEIGHT), _NO_ABSENCE,
              color=COLOR_TEXT_SECONDARY)
        return y + _ROW_HEIGHT + _SECTION_GAP
    y += 4.0

    by_day = []
    for weekday in sorted(patterns.by_weekday):
        day_rate = patterns.weekday_rate(weekday)
        by_day.append((
            _WEEKDAY_LABELS[weekday] if 0 <= weekday < 7 else str(weekday),
            patterns.by_weekday[weekday]))
    if by_day:
        y += _text(painter, QRectF(left, y, width, 14.0), _ABSENCE_BY_DAY,
                   size=8, color=COLOR_TEXT_SECONDARY) + 2
        y += _bar_chart(painter, left, y, width, by_day, color=COLOR_WARNING)

    by_cycle = [(_CYCLE_LABELS.get(cycle, cycle), count)
                for cycle, count in sorted(patterns.by_cycle.items(),
                                           key=lambda item: -item[1])]
    if by_cycle:
        y += _text(painter, QRectF(left, y + 2, width, 14.0),
                   _ABSENCE_BY_CYCLE, size=8, color=COLOR_TEXT_SECONDARY) + 2
        y += _bar_chart(painter, left, y, width, by_cycle, color=COLOR_DANGER)
    return y + _SECTION_GAP


def _draw_feedback(painter: QPainter, left: float, y: float, width: float,
                   records: Sequence, students: Sequence,
                   today: datetime.date) -> float:
    y = _section(painter, left, y, width, _SEC_FEEDBACK)
    by_cycle = summarize_by_attribute(records, "cycle")
    by_gender = summarize_by_attribute(records, "gender")
    if not by_cycle and not by_gender:
        _cell(painter, QRectF(left, y, width, _ROW_HEIGHT), _NO_FEEDBACK,
              color=COLOR_TEXT_SECONDARY)
        return y + _ROW_HEIGHT + _SECTION_GAP
    y += 4.0

    for table, labels, profiles, color in (
        (by_cycle, _CYCLE_LABELS, profile_by_cycle(students, today),
         COLOR_WARNING),
        (by_gender, _GENDER_LABELS, profile_by_gender(students, today),
         COLOR_SUCCESS),
    ):
        rows = []
        for code, summary in sorted(table.items(),
                                    key=lambda item: -item[1].average):
            profile = profiles.get(code)
            name = labels.get(code, code)
            # The group's real average age from the roster — what turns
            # "تأهيلي rate it higher" into "the oldest pupils do".
            if profile is not None and profile.average_age is not None:
                name = f"{name} · {profile.average_age:.1f} سنة"
            rows.append((f"{name}  ({summary.count:,} رأي)",
                         round(summary.average, 2)))
        if rows:
            # Pinned to 5: rescaling 3.66 against 3.75 would read as a rout.
            y += _bar_chart(painter, left, y, width, rows, color=color,
                            suffix="/ 5", maximum=5.0)

    unclassified = ungrouped_responses(records)
    if unclassified:
        y += _text(painter, QRectF(left, y + 2, width, 14.0),
                   _UNGROUPED.format(count=unclassified), size=8,
                   color=COLOR_TEXT_SECONDARY) + 2
    return y + _SECTION_GAP


def _draw_completeness(painter: QPainter, left: float, y: float, width: float,
                       summary: Completeness) -> float:
    y = _section(painter, left, y, width, _SEC_COMPLETENESS)
    y += _text(painter, QRectF(left, y + 2, width, 14.0), _COMPLETENESS_NOTE,
               size=8, color=COLOR_TEXT_SECONDARY) + 4
    if not summary.served_days:
        _cell(painter, QRectF(left, y, width, _ROW_HEIGHT), _NO_DATA,
              color=COLOR_TEXT_SECONDARY)
        return y + _ROW_HEIGHT + _SECTION_GAP

    rows = [(_DOCUMENT_LABELS.get(key, key), summary.per_document.get(key, 0))
            for key in _DOCUMENT_LABELS]
    y += _bar_chart(painter, left, y, width, rows, color=COLOR_ACCENT,
                    suffix=f"/ {summary.served_days}",
                    maximum=float(summary.served_days))

    if not summary.gaps:
        y += _text(painter, QRectF(left, y + 2, width, 14.0), _NO_GAPS,
                   size=8, color=COLOR_SUCCESS) + 2
        return y + _SECTION_GAP

    y += _text(painter, QRectF(left, y + 2, width, 14.0), _GAPS_TITLE,
               size=8, color=COLOR_TEXT_SECONDARY) + 2
    for gap in summary.gaps[:_GAP_LIMIT]:
        missing = "، ".join(_DOCUMENT_LABELS.get(key, key)
                            for key in gap.missing)
        y += _text(painter, QRectF(left, y, width, 13.0),
                   f"{gap.date}  —  {missing}", size=8, color=COLOR_DANGER)
    if len(summary.gaps) > _GAP_LIMIT:
        y += _text(painter, QRectF(left, y, width, 13.0),
                   _GAP_MORE.format(count=len(summary.gaps) - _GAP_LIMIT),
                   size=8, color=COLOR_TEXT_SECONDARY)
    return y + _SECTION_GAP


def write_statistics_report_pdf(path: Path, settings: SchoolSettings,
                                month: str,
                                today: Optional[datetime.date] = None) -> None:
    """Render الإحصائيات as a signed report for the chosen month.

    Sections are measured before they are drawn and moved to a new page when
    they do not fit, rather than being clipped at the bottom margin.
    """
    from data.database import (
        get_all_feedback, get_all_students, get_all_week_feedback,
    )

    today = today or datetime.date.today()
    start, end = month_bounds(month)
    prices = {
        MEAL_FTOUR: settings.price_ftour if settings else "",
        MEAL_GHADA: settings.price_ghada if settings else "",
        MEAL_ASHA: settings.price_asha if settings else "",
    }
    points = monthly_trend(prices)
    this_month = next((point for point in points if point.month == month), None)
    patterns = absence_patterns(start, end)
    completeness = document_completeness(start, end)
    students = get_all_students()
    records = list(get_all_week_feedback()) + list(get_all_feedback())

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
        usable_bottom = page_h - _MARGIN - 95.0

        def new_page() -> float:
            top = draw_official_pdf_header(
                painter, page_width=page_w, margin=_MARGIN, top=16.0,
                settings=settings, title=_TITLE)
            return top + 4.0

        y = new_page()
        y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0), _SUBTITLE,
                   size=_META_SIZE, color=COLOR_TEXT_SECONDARY,
                   align=Qt.AlignmentFlag.AlignCenter) + 2.0
        y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0),
                   f"{_LBL_MONTH}: {month_label(month)}    ·    "
                   f"{_LBL_GENERATED}: {today.isoformat()}",
                   size=_META_SIZE, color=COLOR_TEXT_PRIMARY, bold=True,
                   align=Qt.AlignmentFlag.AlignCenter) + 10.0

        stats = summarize_students(students, today)
        y = _draw_headline(painter, _MARGIN, y, content_w,
                           students=stats.total, point=this_month,
                           patterns=patterns, completeness=completeness)
        y = _draw_trend(painter, _MARGIN, y, content_w, points)

        # Each remaining section is given a fresh page when what it needs will
        # not fit — drawText CLIPS at the rect it is handed, so a section that
        # overflows simply loses its tail without any error.
        for draw, needed in (
            (lambda top: _draw_classes(painter, _MARGIN, top, content_w,
                                       students),
             _HEADER_ROW_HEIGHT + 10 * _ROW_HEIGHT),
            (lambda top: _draw_absence(painter, _MARGIN, top, content_w,
                                       patterns),
             _HEADER_ROW_HEIGHT + 8 * _BAR_ROW_H),
            (lambda top: _draw_feedback(painter, _MARGIN, top, content_w,
                                        records, students, today),
             _HEADER_ROW_HEIGHT + 6 * _BAR_ROW_H),
            (lambda top: _draw_completeness(painter, _MARGIN, top, content_w,
                                            completeness),
             _HEADER_ROW_HEIGHT + 7 * _BAR_ROW_H),
        ):
            if y + needed > usable_bottom:
                writer.newPage()
                y = new_page()
            y = draw(y)

        draw_official_pdf_footer(
            painter, page_width=page_w, margin=_MARGIN,
            top=page_h - _MARGIN - 70.0, settings=settings,
            roles=_SIGN_ROLES)
    finally:
        painter.end()
