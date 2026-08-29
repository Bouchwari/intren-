"""
src/ui/feedback_export.py
تقرير آراء التلاميذ — the printable summary of what pupils thought of the
meals, for the لجنة التتبع والمراقبة.

There is no official form for this: the ministry guide has no pupil-feedback
document, so this is our own layout. What it will NOT do is present an opinion
as harder evidence than it is — every average is printed with the number of
pupils behind it, and a dish rated by too few to mean anything is listed under
its own heading rather than ranked.
"""
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter,
    QPen,
)

from config.settings import (
    COLOR_BORDER, COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY, COLOR_WARNING, MEAL_LABELS,
)
from core.feedback import (
    MIN_RATINGS_FOR_RANKING, MIN_RESPONSES_FOR_PATTERN, RATING_LEVELS,
    RATING_MAX, DishSummary, average_by_meal_type, biggest_gaps,
    favourite_per_group, overall_average, response_counts, response_total,
    summarize_by_attribute, summarize_by_dish, ungrouped_responses,
)
from core.models import MealFeedback, SchoolSettings, Student
from core.student_stats import (
    GroupProfile, StudentStats, profile_by_cycle, profile_by_gender,
    sorted_counts, summarize_students,
)
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header

_TITLE = "تقرير آراء التلاميذ حول الوجبات"
_SUBTITLE = "يعرض على لجنة التتبع والمراقبة"
_LBL_PERIOD = "الفترة"
_LBL_OVERALL = "المتوسط العام"
_LBL_RESPONSES = "عدد التلاميذ المعبّرين"
_LBL_MEALS = "عدد الوجبات المسجلة"
_LBL_BY_MEAL = "المتوسط حسب الوجبة"
_LBL_RANKED = "الأطباق مرتبة حسب التقييم"
_LBL_TOO_FEW = "أطباق بعدد آراء غير كاف للترتيب"
_LBL_NONE = "لا توجد تقييمات مسجلة"
_COUNT_SUFFIX = "تلميذ"

_HDR = ["الطبق", "المتوسط", "عدد المعبّرين", "التوزيع"]
_RATING_LABELS = {5: "ممتاز", 4: "جيد", 3: "متوسط", 2: "ضعيف", 1: "سيء"}
_SIGN_ROLES = ["الحارس(ة) العام(ة) للداخلية",
               "مسير المصالح المادية والمالية", "مدير(ة) المؤسسة"]

# ── page 2: indicators and charts ───────────────────────────────────────────
_LBL_KPI = "المؤشرات الأساسية"
_KPI_AVERAGE = "المتوسط العام"
_KPI_RESPONSES = "آراء مسجلة"
_KPI_POSITIVE = "آراء إيجابية"
_KPI_NEGATIVE = "آراء سلبية"
_KPI_DISHES = "أطباق مقيَّمة"
_KPI_BEST = "أحسن طبق"
_KPI_WORST = "أضعف طبق"
_KPI_COVERAGE = "معدل التعبير"
_KPI_COVERAGE_HINT = "رأي لكل تلميذ"
_CHART_SPREAD = "توزيع الآراء حسب المستوى"
_CHART_WEEKS = "تطور المتوسط حسب الأسبوع"
_CHART_DISHES = "المتوسط حسب الطبق"
_LBL_NO_TREND = "لا تتوفر أسابيع كافية لرسم التطور"

# ── page 3: who the opinions are about ──────────────────────────────────────
_LBL_POPULATION = "التلاميذ المستفيدون من الخدمة"
_LBL_TOTAL_STUDENTS = "مجموع المستفيدين"
_LBL_MONITORS = "معلمو الداخلية"
_LBL_AVG_AGE = "متوسط السن"
_CHART_GENDER = "حسب الجنس"
_CHART_CYCLE = "حسب السلك"
_CHART_CLASS = "حسب القسم"
_CHART_AGE = "حسب السن"
_LBL_NO_AGES = "لم تُسجَّل تواريخ الازدياد، لذلك لا يمكن عرض توزيع الأسنان"
_LBL_UNKNOWN_AGE = "بدون تاريخ ازدياد: {count}"
_GENDER_LABELS = {"male": "ذكور", "female": "إناث", "": "غير محدد"}
_CYCLE_LABELS = {"primary": "ابتدائي", "collegial": "إعدادي",
                 "qualifying": "تأهيلي", "monitors": "معلمو الداخلية",
                 "": "غير محدد"}
_LBL_PATTERNS = "من أبدى الرأي — الروابط بين الفئات والأطباق"
_LBL_PATTERN_INTRO = (
    "تُقارَن هنا آراء الفئات بعضها ببعض. لا تدخل الفئة في المقارنة إلا إذا "
    "بلغت آراؤها في الطبق {minimum} على الأقل، ولا يُقارَن طبق عبّرت عنه فئة "
    "واحدة فقط — ذلك نقص في الجمع لا اختلاف في الرأي.")
_LBL_BY_CYCLE = "متوسط التقييم حسب السلك"
_LBL_BY_GENDER = "متوسط التقييم حسب الجنس"
_LBL_GAPS = "أطباق تختلف حولها الأسلاك"
_LBL_GAPS_GENDER = "أطباق يختلف حولها الذكور والإناث"
_LBL_FAVOURITES = "الطبق المفضل لدى كل فئة"
_GAP_HDR = ["الطبق", "الأعلى تقييماً", "الأدنى تقييماً", "الفارق"]
_FAV_HDR = ["الفئة", "الطبق المفضل", "المتوسط", "عدد الآراء"]
_LBL_NO_GROUPS = ("لم تُسجَّل آراء موزّعة على الأسلاك والجنس بعد. اختر السلك "
                  "والجنس في شاشة التقييم قبل إدخال الأعداد لتظهر هذه المقارنات.")
_LBL_NO_GAPS = "لا يوجد طبق قارنته فئتان بعدد آراء كافٍ بعد."
_LBL_UNGROUPED = "آراء بدون تصنيف (غير داخلة في المقارنة): {count:,}"
_LBL_AGE_OF = "{average} سنة"
_GROUP_COUNT = "{count:,} تلميذ"
_OPINION_SUFFIX = "رأي"
_SECTION_LABELS = {"internat": "داخلي", "cantine": "مطعم", "": "غير محدد"}
_AGE_SUFFIX = "سنة"
_STUDENT_SUFFIX = "تلميذ"

_CHART_BAR_HEIGHT = 15.0
_CHART_BAR_GAP = 6.0
_CHART_LABEL_SHARE = 0.28
_CHART_VALUE_SHARE = 0.16
_KPI_BOX_HEIGHT = 46.0
_KPI_GAP = 8.0
_KPI_PER_ROW = 4

_MARGIN = 44.0
_ROW_HEIGHT = 20.0
_HEADER_ROW_HEIGHT = 22.0
_SECTION_GAP = 14.0
_BODY_SIZE = 9
_META_SIZE = 9
_SECTION_SIZE = 10
# The distribution column carries the most text, so it takes the most room.
_COLUMN_SHARE = (0.30, 0.13, 0.17, 0.40)


def _rating_color(average: float) -> str:
    if average >= 4:
        return COLOR_SUCCESS
    if average >= 3:
        return COLOR_WARNING
    return COLOR_DANGER


def _text(painter: QPainter, rect: QRectF, value: str, *, size: int,
          color: str, bold: bool = False,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight) -> float:
    """Draw wrapped text and return the height used — drawText CLIPS."""
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))
    flags = int(align | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
    metrics = QFontMetricsF(font)
    needed = metrics.boundingRect(
        QRectF(rect.left(), rect.top(), rect.width(), 10000.0), flags, value)
    height = max(rect.height(), needed.height())
    painter.drawText(
        QRectF(rect.left(), rect.top(), rect.width(), height), flags, value)
    return height


def _cell(painter: QPainter, rect: QRectF, value: str, *, bold: bool = False,
          fill: str = "", color: str = COLOR_TEXT_PRIMARY) -> None:
    if fill:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRect(rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.drawRect(rect)
    _text(painter, QRectF(rect.left() + 5, rect.top(), rect.width() - 10,
                          rect.height()),
          value, size=_BODY_SIZE, color=color, bold=bold,
          align=Qt.AlignmentFlag.AlignCenter)


def _distribution_text(records: Sequence[MealFeedback], dish: str) -> str:
    """"ممتاز 40 · جيد 55 · ..." across every record for one dish."""
    from core.feedback import normalize_dish
    totals: Dict[int, int] = {level: 0 for level in RATING_LEVELS}
    for record in records:
        if normalize_dish(record.dish) != dish:
            continue
        for level, count in response_counts(record).items():
            totals[level] += count
    parts = [f"{_RATING_LABELS[level]} {totals[level]}"
             for level in RATING_LEVELS if totals[level]]
    return "  ·  ".join(parts) or "—"


def _measured_height(text: str, width: float, size: int,
                     bold: bool = False) -> float:
    """How tall wrapped text will actually be — drawText CLIPS to its rect."""
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    flags = int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                | Qt.TextFlag.TextWordWrap)
    return QFontMetricsF(font).boundingRect(
        QRectF(0, 0, width, 10000.0), flags, text).height()


def _row_height(summary: DishSummary, distribution: str,
                widths: Sequence[float]) -> float:
    """A row is as tall as its tallest cell.

    The distribution ("ممتاز 189 · جيد 202 · …") wraps to two lines for most
    dishes, and a fixed row height let it spill out of the table entirely.
    """
    tallest = _ROW_HEIGHT
    for text, width in ((summary.dish, widths[0]), (distribution, widths[3])):
        tallest = max(tallest, _measured_height(text, width - 10, _BODY_SIZE) + 8)
    return tallest


def _kpi_box(painter: QPainter, rect: QRectF, value: str, caption: str,
             color: str) -> None:
    """One indicator: the number big, what it means underneath."""
    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(rect, 6.0, 6.0)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(
        QRectF(rect.right() - 3.0, rect.top() + 4.0, 3.0, rect.height() - 8.0),
        1.5, 1.5)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    inner = QRectF(rect.left() + 8, rect.top() + 5, rect.width() - 18, 18)
    _text(painter, inner, value, size=12, color=color, bold=True,
          align=Qt.AlignmentFlag.AlignRight)
    _text(painter, QRectF(inner.left(), rect.top() + 24, inner.width(), 14),
          caption, size=8, color=COLOR_TEXT_SECONDARY,
          align=Qt.AlignmentFlag.AlignRight)


def _bar_chart(painter: QPainter, left: float, top: float, width: float,
               items: Sequence[tuple], *, color: str,
               suffix: str = "", show_share: bool = False,
               maximum: Optional[float] = None) -> float:
    """Horizontal bars: label on the right, bar in the middle, value on the
    left — each in its OWN column.

    The value used to be drawn inside the track, where a long bar covered it
    and left the number unreadable. Bars are scaled to the largest value
    present, and a zero row draws no bar rather than a misleading sliver.
    """
    if not items:
        return 0.0
    label_w = width * _CHART_LABEL_SHARE
    value_w = width * _CHART_VALUE_SHARE
    track_w = width - label_w - value_w - 8.0
    # Ratings are scaled to 5, not to the biggest bar present: rescaling
    # 3.8 vs 4.2 to full width turns a small difference into a landslide.
    largest = maximum or max(value for _label, value in items) or 1
    total = sum(value for _label, value in items) or 1
    y = top
    for label, value in items:
        _text(painter, QRectF(left + value_w + track_w + 8.0, y, label_w,
                              _CHART_BAR_HEIGHT),
              str(label), size=_BODY_SIZE, color=COLOR_TEXT_PRIMARY,
              align=Qt.AlignmentFlag.AlignRight)

        track = QRectF(left + value_w + 4.0, y + 2, track_w,
                       _CHART_BAR_HEIGHT - 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F1F1EC"))
        painter.drawRoundedRect(track, 2.0, 2.0)
        if value > 0:
            filled = track_w * value / largest
            # RTL: the bar grows from the right edge leftward.
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(
                QRectF(track.right() - filled, track.top(), filled,
                       track.height()), 2.0, 2.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        caption = f"{value:,}{(' ' + suffix) if suffix else ''}"
        if show_share:
            with_share = f"{caption}  ({value / total * 100:.0f}%)"
            # In a narrow (half-width) chart the share does not fit on one
            # line; wrapping it collided with the row below, so it is dropped
            # rather than allowed to overlap.
            if _measured_height(with_share, value_w, 8, True) <= _CHART_BAR_HEIGHT:
                caption = with_share
        _text(painter, QRectF(left, y, value_w, _CHART_BAR_HEIGHT), caption,
              size=8, color=COLOR_TEXT_SECONDARY, bold=True,
              align=Qt.AlignmentFlag.AlignLeft)
        y += _CHART_BAR_HEIGHT + _CHART_BAR_GAP
    return y - top


def _column_chart(painter: QPainter, left: float, top: float, width: float,
                  height: float, items: Sequence[tuple], *,
                  maximum: float, color: str) -> float:
    """Vertical columns for a trend, with the value above each column.

    The scale starts at ZERO, not at the smallest value — a truncated axis
    makes a flat run of weeks look like a collapse.
    """
    if not items:
        return 0.0
    plot_h = height - 26.0
    slot = width / len(items)
    bar_w = min(slot * 0.55, 30.0)
    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.drawLine(QRectF(left, top + plot_h, width, 0).topLeft(),
                     QRectF(left, top + plot_h, width, 0).topRight())
    for index, (label, value) in enumerate(items):
        # RTL: the earliest week on the right.
        centre = left + width - (index + 0.5) * slot
        bar_h = (value / maximum) * (plot_h - 12.0) if maximum else 0.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(
            QRectF(centre - bar_w / 2, top + plot_h - bar_h, bar_w, bar_h),
            2.0, 2.0)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Centred explicitly: _text defaults to right-aligned, which pushed
        # every value and label half a slot away from its own column.
        _text(painter, QRectF(centre - slot / 2, top + plot_h - bar_h - 13,
                              slot, 12),
              f"{value:.2f}", size=8, color=COLOR_TEXT_PRIMARY, bold=True,
              align=Qt.AlignmentFlag.AlignHCenter)
        _text(painter, QRectF(centre - slot / 2, top + plot_h + 3, slot, 12),
              str(label), size=7, color=COLOR_TEXT_SECONDARY,
              align=Qt.AlignmentFlag.AlignHCenter)
    return height


def _section(painter: QPainter, left: float, y: float, width: float,
             title: str) -> float:
    _cell(painter, QRectF(left, y, width, _HEADER_ROW_HEIGHT), title,
          bold=True, fill="#EFF4F0")
    return y + _HEADER_ROW_HEIGHT


def _table_header(painter: QPainter, left: float, y: float,
                  widths: Sequence[float]) -> float:
    def column_left(index: int) -> float:
        return left + sum(widths[index + 1:])
    for index, header in enumerate(_HDR):
        _cell(painter, QRectF(column_left(index), y, widths[index],
                              _HEADER_ROW_HEIGHT),
              header, bold=True, fill="#F7F7F4")
    return y + _HEADER_ROW_HEIGHT


def _summary_row(painter: QPainter, left: float, y: float,
                 widths: Sequence[float], summary: DishSummary,
                 distribution: str) -> float:
    def column_left(index: int) -> float:
        return left + sum(widths[index + 1:])
    height = _row_height(summary, distribution, widths)
    values = [
        summary.dish,
        f"{summary.average:.2f}",
        f"{summary.count:,} {_COUNT_SUFFIX}",
        distribution,
    ]
    for index, value in enumerate(values):
        _cell(painter, QRectF(column_left(index), y, widths[index], height),
              value, bold=(index == 1),
              color=_rating_color(summary.average) if index == 1
              else COLOR_TEXT_PRIMARY)
    return y + height


def _weekly_averages(records: Sequence) -> List[tuple]:
    """(week label, average) oldest first, for weeks that were actually rated."""
    buckets: Dict[str, List[int]] = {}
    for record in records:
        week = getattr(record, "week_start", "")
        if not week:
            continue                      # a legacy per-day row has no week
        responses = response_total(record)
        if not responses:
            continue
        totals = buckets.setdefault(week, [0, 0])
        totals[0] += sum(level * count
                         for level, count in response_counts(record).items())
        totals[1] += responses
    return [(week[5:], total / count)          # "MM-DD" is enough on an axis
            for week, (total, count) in sorted(buckets.items()) if count]


def _positive_negative(records: Sequence) -> Tuple[int, int, int]:
    """(positive, negative, total) responses — 4-5 good, 1-2 poor, 3 neither."""
    positive = negative = total = 0
    for record in records:
        for level, count in response_counts(record).items():
            total += count
            if level >= 4:
                positive += count
            elif level <= 2:
                negative += count
    return positive, negative, total


def _draw_indicator_page(painter: QPainter, page_w: float, page_h: float,
                         settings: SchoolSettings, records: Sequence,
                         summaries: Sequence[DishSummary],
                         students: int) -> None:
    """Page 2 — the indicators and the charts."""
    content_w = page_w - (_MARGIN * 2)
    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=_MARGIN, top=16.0,
        settings=settings, title=_TITLE)
    y += 4.0

    average = overall_average(records)
    positive, negative, responses = _positive_negative(records)
    rankable = [s for s in summaries if s.is_rankable]
    best = rankable[0] if rankable else None
    worst = rankable[-1] if rankable else None

    y = _section(painter, _MARGIN, y, content_w, _LBL_KPI)
    y += 6.0
    boxes = [
        (f"{average:.2f} / 5" if average is not None else "—", _KPI_AVERAGE,
         _rating_color(average) if average is not None else COLOR_TEXT_SECONDARY),
        (f"{responses:,}", _KPI_RESPONSES, COLOR_TEXT_PRIMARY),
        (f"{positive / responses * 100:.0f}%" if responses else "—",
         _KPI_POSITIVE, COLOR_SUCCESS),
        (f"{negative / responses * 100:.0f}%" if responses else "—",
         _KPI_NEGATIVE, COLOR_DANGER),
        (f"{len(summaries):,}", _KPI_DISHES, COLOR_TEXT_PRIMARY),
        (f"{responses / students:.1f}" if students else "—",
         f"{_KPI_COVERAGE} ({_KPI_COVERAGE_HINT})", COLOR_TEXT_PRIMARY),
        (best.dish if best else "—",
         f"{_KPI_BEST} ({best.average:.2f})" if best else _KPI_BEST, COLOR_SUCCESS),
        (worst.dish if worst else "—",
         f"{_KPI_WORST} ({worst.average:.2f})" if worst else _KPI_WORST, COLOR_DANGER),
    ]
    box_w = (content_w - _KPI_GAP * (_KPI_PER_ROW - 1)) / _KPI_PER_ROW
    for index, (value, caption, color) in enumerate(boxes):
        row, column = divmod(index, _KPI_PER_ROW)
        # RTL: the first box on the right.
        left = _MARGIN + (_KPI_PER_ROW - 1 - column) * (box_w + _KPI_GAP)
        _kpi_box(painter, QRectF(left, y + row * (_KPI_BOX_HEIGHT + _KPI_GAP),
                                 box_w, _KPI_BOX_HEIGHT),
                 value, caption, color)
    rows = (len(boxes) + _KPI_PER_ROW - 1) // _KPI_PER_ROW
    y += rows * (_KPI_BOX_HEIGHT + _KPI_GAP) + _SECTION_GAP

    # how the opinions were spread across the five levels
    y = _section(painter, _MARGIN, y, content_w, _CHART_SPREAD)
    y += 8.0
    totals = {level: 0 for level in RATING_LEVELS}
    for record in records:
        for level, count in response_counts(record).items():
            totals[level] += count
    y += _bar_chart(painter, _MARGIN, y, content_w,
                    [(_RATING_LABELS[level], totals[level])
                     for level in RATING_LEVELS],
                    color=COLOR_SUCCESS, suffix=_COUNT_SUFFIX,
                    show_share=True) + _SECTION_GAP

    # the trend across weeks
    y = _section(painter, _MARGIN, y, content_w, _CHART_WEEKS)
    y += 8.0
    weekly = _weekly_averages(records)
    if len(weekly) >= 2:
        y += _column_chart(painter, _MARGIN, y, content_w, 124.0, weekly,
                           maximum=5.0, color=COLOR_TEXT_PRIMARY) + _SECTION_GAP
    else:
        y += _text(painter, QRectF(_MARGIN, y, content_w, 16.0), _LBL_NO_TREND,
                   size=_BODY_SIZE, color=COLOR_TEXT_SECONDARY) + _SECTION_GAP

    # per-dish averages, best first
    if summaries:
        y = _section(painter, _MARGIN, y, content_w, _CHART_DISHES)
        y += 8.0
        room = int((page_h - _MARGIN - 40.0 - y)
                   // (_CHART_BAR_HEIGHT + _CHART_BAR_GAP))
        _bar_chart(painter, _MARGIN, y, content_w,
                   [(s.dish, round(s.average, 2)) for s in summaries[:max(0, room)]],
                   color=COLOR_WARNING)


def _draw_population_page(painter: QPainter, page_w: float, page_h: float,
                          settings: SchoolSettings, stats: StudentStats) -> None:
    """Page 3 — who the opinions are actually about."""
    content_w = page_w - (_MARGIN * 2)
    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=_MARGIN, top=16.0,
        settings=settings, title=_TITLE)
    y += 4.0

    y = _section(painter, _MARGIN, y, content_w, _LBL_POPULATION)
    y += 6.0
    boxes = [
        (f"{stats.total:,}", _LBL_TOTAL_STUDENTS, COLOR_TEXT_PRIMARY),
        (f"{stats.monitors:,}", _LBL_MONITORS, COLOR_TEXT_PRIMARY),
        (f"{stats.average_age:.1f} {_AGE_SUFFIX}" if stats.average_age else "—",
         _LBL_AVG_AGE, COLOR_TEXT_PRIMARY),
        (f"{len(stats.by_class):,}", _CHART_CLASS, COLOR_TEXT_PRIMARY),
    ]
    box_w = (content_w - _KPI_GAP * (len(boxes) - 1)) / len(boxes)
    for index, (value, caption, color) in enumerate(boxes):
        left = _MARGIN + (len(boxes) - 1 - index) * (box_w + _KPI_GAP)
        _kpi_box(painter, QRectF(left, y, box_w, _KPI_BOX_HEIGHT),
                 value, caption, color)
    y += _KPI_BOX_HEIGHT + _SECTION_GAP

    half = (content_w - 14.0) / 2
    for title, items, color, left in (
        (_CHART_GENDER,
         [(_GENDER_LABELS.get(key, key or _GENDER_LABELS[""]), count)
          for key, count in sorted_counts(stats.by_gender)],
         COLOR_SUCCESS, _MARGIN + half + 14.0),
        (_CHART_CYCLE, sorted_counts(stats.by_cycle), COLOR_WARNING, _MARGIN),
    ):
        _section(painter, left, y, half, title)
        _bar_chart(painter, left, y + _HEADER_ROW_HEIGHT + 6.0, half, items,
                   color=color, suffix=_STUDENT_SUFFIX, show_share=True)
    tallest = max(len(stats.by_gender), len(stats.by_cycle))
    y += (_HEADER_ROW_HEIGHT + 6.0
          + tallest * (_CHART_BAR_HEIGHT + _CHART_BAR_GAP) + _SECTION_GAP)

    y = _section(painter, _MARGIN, y, content_w, _CHART_CLASS)
    y += 8.0
    y += _bar_chart(painter, _MARGIN, y, content_w,
                    sorted_counts(stats.by_class, limit=8),
                    color=COLOR_TEXT_PRIMARY, suffix=_STUDENT_SUFFIX) + _SECTION_GAP

    y = _section(painter, _MARGIN, y, content_w, _CHART_AGE)
    y += 8.0
    if stats.has_ages:
        ages = [(f"{age} {_AGE_SUFFIX}", count)
                for age, count in sorted(stats.by_age.items())]
        y += _bar_chart(painter, _MARGIN, y, content_w, ages,
                        color=COLOR_SUCCESS, suffix=_STUDENT_SUFFIX)
        if stats.unknown_age:
            _text(painter, QRectF(_MARGIN, y + 4, content_w, 14.0),
                  _LBL_UNKNOWN_AGE.format(count=stats.unknown_age),
                  size=8, color=COLOR_TEXT_SECONDARY)
    else:
        # Say the dates are missing rather than print an empty chart.
        _text(painter, QRectF(_MARGIN, y, content_w, 16.0), _LBL_NO_AGES,
              size=_BODY_SIZE, color=COLOR_TEXT_SECONDARY)


def _group_caption(code: str, labels: Dict[str, str],
                   profile: Optional[GroupProfile]) -> str:
    """"ابتدائي · 12.3 سنة" — the group named, and how old it actually is.

    The age comes from the ROSTER, never from the ratings: it is what turns
    "this cycle scores it lowest" into "the youngest pupils score it lowest".
    """
    name = labels.get(code, code)
    if profile is None or profile.average_age is None:
        return name
    return (f"{name} · "
            f"{_LBL_AGE_OF.format(average=f'{profile.average_age:.1f}')}")


def _group_table(painter: QPainter, left: float, y: float,
                 widths: Sequence[float], headers: Sequence[str],
                 rows: Sequence[Sequence[str]]) -> float:
    """A small fixed-height table. Every cell is short by construction."""
    def column_left(index: int) -> float:
        return left + sum(widths[index + 1:])

    for index, header in enumerate(headers):
        _cell(painter, QRectF(column_left(index), y, widths[index],
                              _HEADER_ROW_HEIGHT),
              header, bold=True, fill="#F7F7F4")
    y += _HEADER_ROW_HEIGHT
    for values in rows:
        for index, value in enumerate(values):
            _cell(painter, QRectF(column_left(index), y, widths[index],
                                  _ROW_HEIGHT), str(value))
        y += _ROW_HEIGHT
    return y


def _draw_patterns_page(painter: QPainter, page_w: float, page_h: float,
                        settings: SchoolSettings, records: Sequence,
                        students: Sequence[Student],
                        today: datetime.date) -> None:
    """Page 4 — which group said what, and how old that group is."""
    content_w = page_w - (_MARGIN * 2)
    y = draw_official_pdf_header(
        painter, page_width=page_w, margin=_MARGIN, top=16.0,
        settings=settings, title=_TITLE)
    y += 4.0

    y = _section(painter, _MARGIN, y, content_w, _LBL_PATTERNS)
    y += 4.0
    y += _text(painter, QRectF(_MARGIN, y, content_w, 26.0),
               _LBL_PATTERN_INTRO.format(minimum=MIN_RESPONSES_FOR_PATTERN),
               size=8, color=COLOR_TEXT_SECONDARY) + 8.0

    by_cycle = summarize_by_attribute(records, "cycle")
    by_gender = summarize_by_attribute(records, "gender")
    if not by_cycle and not by_gender:
        # Say the collecting has not been split yet, rather than print four
        # empty comparison boxes.
        _text(painter, QRectF(_MARGIN, y, content_w, 30.0), _LBL_NO_GROUPS,
              size=_BODY_SIZE, color=COLOR_TEXT_SECONDARY)
        return

    cycle_ages = profile_by_cycle(students, today)
    gender_ages = profile_by_gender(students, today)

    # Full width, one under the other. Side by side, the group label — name,
    # age and opinion count — wrapped onto a second line and collided with
    # the row below it.
    charts = [
        (_LBL_BY_CYCLE, by_cycle, _CYCLE_LABELS, cycle_ages, COLOR_WARNING),
        (_LBL_BY_GENDER, by_gender, _GENDER_LABELS, gender_ages, COLOR_SUCCESS),
    ]
    for title, table, labels, profiles, color in charts:
        if not table:
            continue
        y = _section(painter, _MARGIN, y, content_w, title) + 6.0
        items = [(f"{_group_caption(code, labels, profiles.get(code))}  ·  "
                  f"{summary.count:,} {_OPINION_SUFFIX}",
                  round(summary.average, 2))
                 for code, summary in sorted(
                     table.items(), key=lambda item: -item[1].average)]
        y += _bar_chart(painter, _MARGIN, y, content_w, items, color=color,
                        suffix=f"/ {RATING_MAX}", maximum=RATING_MAX)
        y += _SECTION_GAP

    gap_widths = [content_w * share for share in (0.30, 0.26, 0.26, 0.18)]
    for title, attribute, labels in ((_LBL_GAPS, "cycle", _CYCLE_LABELS),
                                     (_LBL_GAPS_GENDER, "gender",
                                      _GENDER_LABELS)):
        gaps = biggest_gaps(records, attribute, limit=4)
        y = _section(painter, _MARGIN, y, content_w, title)
        if not gaps:
            _cell(painter, QRectF(_MARGIN, y, content_w, _ROW_HEIGHT),
                  _LBL_NO_GAPS, color=COLOR_TEXT_SECONDARY)
            y += _ROW_HEIGHT + _SECTION_GAP
            continue
        rows = [
            [gap.dish,
             f"{labels.get(gap.high_group, gap.high_group)} "
             f"{gap.high_average:.2f} ({gap.high_count:,})",
             f"{labels.get(gap.low_group, gap.low_group)} "
             f"{gap.low_average:.2f} ({gap.low_count:,})",
             f"{gap.gap:.2f}"]
            for gap in gaps
        ]
        y = _group_table(painter, _MARGIN, y, gap_widths, _GAP_HDR, rows)
        y += _SECTION_GAP

    favourites = favourite_per_group(records, "cycle")
    favourites.update({f"g:{key}": value for key, value
                       in favourite_per_group(records, "gender").items()})
    y = _section(painter, _MARGIN, y, content_w, _LBL_FAVOURITES)
    if favourites:
        fav_widths = [content_w * share for share in (0.30, 0.34, 0.18, 0.18)]
        rows = []
        for code, summary in favourites.items():
            plain = code[2:] if code.startswith("g:") else code
            labels = _GENDER_LABELS if code.startswith("g:") else _CYCLE_LABELS
            profiles = gender_ages if code.startswith("g:") else cycle_ages
            rows.append([_group_caption(plain, labels, profiles.get(plain)),
                         summary.dish, f"{summary.average:.2f}",
                         f"{summary.count:,}"])
        y = _group_table(painter, _MARGIN, y, fav_widths, _FAV_HDR, rows)
    else:
        _cell(painter, QRectF(_MARGIN, y, content_w, _ROW_HEIGHT),
              _LBL_NO_GAPS, color=COLOR_TEXT_SECONDARY)
        y += _ROW_HEIGHT

    unclassified = ungrouped_responses(records)
    if unclassified:
        # Stated plainly: the comparisons above do not cover these.
        _text(painter, QRectF(_MARGIN, y + 6, content_w, 14.0),
              _LBL_UNGROUPED.format(count=unclassified),
              size=8, color=COLOR_TEXT_SECONDARY)


def write_feedback_report_pdf(
    path: Path,
    settings: SchoolSettings,
    records: Sequence[MealFeedback],
    period_label: str,
    students: Optional[Sequence[Student]] = None,
    today: Optional[datetime.date] = None,
) -> None:
    """Render the whole feedback summary as one signed report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TITLE)

    summaries = summarize_by_dish(records)
    rankable = [s for s in summaries if s.is_rankable]
    too_few = [s for s in summaries if not s.is_rankable]

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        page_w = float(writer.width())
        page_h = float(writer.height())
        content_w = page_w - (_MARGIN * 2)
        widths = [content_w * share for share in _COLUMN_SHARE]
        usable_bottom = page_h - _MARGIN - 95.0

        y = draw_official_pdf_header(
            painter, page_width=page_w, margin=_MARGIN, top=16.0,
            settings=settings, title=_TITLE)
        y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0), _SUBTITLE,
                   size=_META_SIZE, color=COLOR_TEXT_SECONDARY,
                   align=Qt.AlignmentFlag.AlignCenter) + 4.0

        average = overall_average(records)
        responses = sum(sum(response_counts(r).values()) for r in records)
        meta = [f"{_LBL_PERIOD}: {period_label}",
                f"{_LBL_MEALS}: {len(records):,}",
                f"{_LBL_RESPONSES}: {responses:,}"]
        if average is not None:
            meta.insert(1, f"{_LBL_OVERALL}: {average:.2f} / 5")
        y += _text(painter, QRectF(_MARGIN, y, content_w, 14.0),
                   "    ·    ".join(meta), size=_META_SIZE,
                   color=COLOR_TEXT_PRIMARY, bold=True,
                   align=Qt.AlignmentFlag.AlignCenter) + 10.0

        by_meal = average_by_meal_type(records)
        if by_meal:
            parts = [f"{MEAL_LABELS.get(meal, meal)}: {s.average:.2f} "
                     f"({s.count:,} {_COUNT_SUFFIX})"
                     for meal, s in by_meal.items()]
            y = _section(painter, _MARGIN, y, content_w, _LBL_BY_MEAL)
            _cell(painter, QRectF(_MARGIN, y, content_w, _ROW_HEIGHT),
                  "    ·    ".join(parts))
            y += _ROW_HEIGHT + _SECTION_GAP

        if not summaries:
            _cell(painter, QRectF(_MARGIN, y, content_w, _ROW_HEIGHT), _LBL_NONE,
                  color=COLOR_TEXT_SECONDARY)
        for title, group in ((_LBL_RANKED, rankable), (_LBL_TOO_FEW, too_few)):
            if not group:
                continue
            if y + _HEADER_ROW_HEIGHT * 2 + _ROW_HEIGHT > usable_bottom:
                writer.newPage()
                y = _MARGIN
            y = _section(painter, _MARGIN, y, content_w, title)
            y = _table_header(painter, _MARGIN, y, widths)
            for summary in group:
                distribution = _distribution_text(records, summary.dish)
                height = _row_height(summary, distribution, widths)
                if y + height > usable_bottom:
                    writer.newPage()
                    y = _MARGIN
                    y = _table_header(painter, _MARGIN, y, widths)
                y = _summary_row(painter, _MARGIN, y, widths, summary,
                                 distribution)
            y += _SECTION_GAP

        # Page 1 above is left exactly as it was; the indicators, the charts
        # and the population go on their own pages after it.
        stats = summarize_students(students or [],
                                   today or datetime.date.today())
        writer.newPage()
        _draw_indicator_page(painter, page_w, page_h, settings, records,
                             summaries, stats.total)
        if stats.total:
            writer.newPage()
            _draw_population_page(painter, page_w, page_h, settings, stats)
        writer.newPage()
        _draw_patterns_page(painter, page_w, page_h, settings, records,
                            students or [], today or datetime.date.today())

        draw_official_pdf_footer(
            painter, page_width=page_w, margin=_MARGIN,
            top=page_h - _MARGIN - 70.0, settings=settings, roles=_SIGN_ROLES)
    finally:
        painter.end()
