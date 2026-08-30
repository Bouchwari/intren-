"""
src/ui/dashboard_deep.py
الإحصائيات المعمقة — the deep half of the statistics screen.

Kept out of dashboard_screen.py, which is already long: three sections the
user asked for on 2026-08-29 — how the months compare, when absence happens
and to whom, and which days are still missing paperwork.

All arithmetic lives in core/analytics.py and core/feedback.py; this file only
draws. Where a figure cannot honestly be produced (a month with no recorded
days, an absence rate with no roster behind it, a cost that excludes meals
nobody priced) the section SAYS SO instead of printing a number that looks
complete.
"""
import datetime
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_DANGER, COLOR_LIGHT_BG, COLOR_SUCCESS,
    COLOR_TEXT_DARK, COLOR_TEXT_MID, COLOR_WARNING,
    FONT_BODY, FONT_CAPTION, FONT_LABEL,
    MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA,
)
from core.analytics import (
    Completeness, MonthPoint, absence_patterns, document_completeness,
    monthly_trend,
)
from core.feedback import (
    CYCLES, GENDERS, summarize_by_attribute, ungrouped_responses,
)
from core.student_stats import profile_by_cycle, profile_by_gender

# ── Arabic strings ──────────────────────────────────────────────────────────
_HEADING = "إحصائيات معمقة"
_LBL_MONTH = "الشهر"
_SEC_TREND = "اتجاهات شهرية"
_SEC_ABSENCE = "أنماط الغياب"
_SEC_FEEDBACK = "من أبدى الرأي"
_SEC_COMPLETENESS = "اكتمال الوثائق"
_SEC_CLASSES = "التلاميذ حسب القسم"
_CLASS_COLS = ["القسم", "ذكور", "إناث", "المجموع"]
_CLASS_TOTAL = "المجموع العام"
_CLASS_UNKNOWN = "بدون قسم"
_CLASS_UNSPECIFIED = "غير محدد"
_CLASS_TOTAL_LINE = ("المجموع العام: {total:,} تلميذ  ·  {male:,} ذكور  ·  "
                     "{female:,} إناث")
GENDER_MALE_KEY = "male"
GENDER_FEMALE_KEY = "female"
_CLASS_HINT = ("عدد التلاميذ في كل قسم وتوزيعهم حسب الجنس، من لائحة التلاميذ.")
_CLASS_UNKNOWN_GENDER = "تلاميذ بدون جنس مسجَّل: {count:,}"
_NO_STUDENTS = "لم تُستورد لائحة التلاميذ بعد."

_TREND_HINT = ("عدد الوجبات المقدمة فعلياً في كل شهر (بعد خصم الغياب)، "
               "بما فيها وجبات رمضان.")
_TREND_COLS = ["الشهر", "الوجبات", "أيام", "المعدل اليومي", "التكلفة"]
_COST_PARTIAL_MARK = "*"
_COST_PARTIAL_NOTE = ("* لا تشمل التكلفة وجبات رمضان — لم يُحدَّد لها ثمن في "
                      "الإعدادات، فتُحتسب ضمن الوجبات دون التكلفة.")
_NO_MONTHS = "لا توجد بيانات شهرية بعد."
_NO_AVERAGE = "—"

_ABSENCE_RATE = "نسبة الغياب"
_ABSENCE_TOTAL = "مجموع الغياب"
_ABSENCE_EXPECTED = "المتوقع حضورهم"
_ABSENCE_WORST = "أعلى يوم غياباً"
_ABSENCE_BY_DAY = "الغياب حسب يوم الأسبوع"
_ABSENCE_BY_CYCLE = "الغياب حسب السلك"
_NO_ABSENCE = "لم يُسجَّل غياب في هذا الشهر."
_RATE_UNKNOWN = "لا يمكن حساب النسبة — لم تُسجَّل أرقام الحضور المتوقع."

_COMPLETE_DAYS = "أيام مكتملة"
_SERVED_DAYS = "أيام قُدِّمت فيها الخدمة"
_COMPLETE_RATE = "نسبة الاكتمال"
_COMPLETENESS_HINT = ("تُحتسب الأيام التي سُجِّلت فيها ورقة اتصال أو غياب فقط — "
                      "العطل والأيام التي لم تُفتح فيها المطعمة ليست نقصاً في "
                      "الوثائق.")
_GAPS_TITLE = "أيام ينقصها توثيق"
_NO_GAPS = "كل الأيام المسجَّلة موثَّقة بالكامل. ✅"
_NO_SERVED = "لا توجد أيام مسجَّلة في هذا الشهر."
_GAP_MORE = "… و{count} يوماً آخر"

_DOCUMENT_LABELS = {
    "contact": "ورقة الاتصال",
    "absence": "ورقة الغياب",
    "report": "التقرير اليومي",
    "order_letter": "رسالة الطلبية",
    "reception": "محضر التسلم",
}
_WEEKDAY_LABELS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة",
                   "السبت", "الأحد"]
_CYCLE_LABELS = {"primary": "ابتدائي", "collegial": "إعدادي",
                 "qualifying": "تأهيلي", "monitors": "معلمو الداخلية"}
_GENDER_LABELS = {"male": "ذكور", "female": "إناث"}
_ARABIC_MONTHS = ["", "يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو",
                  "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر"]

_FEEDBACK_HINT = ("متوسط تقييم كل فئة، وإلى جانبه متوسط سنّها الحقيقي من لائحة "
                  "التلاميذ.")
_NO_FEEDBACK = ("لم تُسجَّل آراء موزَّعة على الفئات بعد — اختر السلك والجنس في "
                "شاشة تقييم التلاميذ قبل إدخال الأعداد.")
_UNGROUPED = "آراء بدون تصنيف: {count:,}"
_OPINION_SUFFIX = "رأي"
_AGE_SUFFIX = "سنة"
_MEAL_SUFFIX = "وجبة"
_DAY_SUFFIX = "يوم"

_CARD_BG = "#ffffff"
_SECTION_GAP = 12
_BAR_HEIGHT = 18
_BAR_GAP = 6
_TREND_CHART_HEIGHT = 190
# Days listed individually before the rest are summarised as a count.
_GAP_LIMIT = 8
_STACK_BAR_H = 22
_STACK_GAP = 7
_STACK_LEGEND_H = 20
_STACK_LEGEND_GAP = 14
# ذكور / إناث / غير محدد — the app's own male and female colours, and a plain
# grey for "not recorded" so it never reads as a third gender.
_GENDER_COLORS = {"male": COLOR_ACCENT, "female": "#8C6BB1", "": "#B8B8AC"}


def _month_label(month: str) -> str:
    """"2026-05" → "ماي 2026"."""
    try:
        year, number = month.split("-")
        return f"{_ARABIC_MONTHS[int(number)]} {year}"
    except (ValueError, IndexError):
        return month


def _card(title: str = "") -> tuple:
    frame = QFrame()
    frame.setStyleSheet(
        f"background: {_CARD_BG}; border: 1px solid {COLOR_BORDER};"
        "border-radius: 14px;")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 14)
    layout.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setStyleSheet(
            f"background: transparent; border: none; color: {COLOR_TEXT_DARK};"
            f"font-size: {FONT_LABEL}px; font-weight: bold;")
        layout.addWidget(label)
    return frame, layout


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(
        f"background: transparent; border: none; color: {COLOR_TEXT_MID};"
        f"font-size: {FONT_CAPTION}px;")
    return label


def _stat(value: str, caption: str, color: str = COLOR_TEXT_DARK) -> QWidget:
    box = QFrame()
    box.setStyleSheet(
        f"background: {COLOR_LIGHT_BG}; border: 1px solid {COLOR_BORDER};"
        "border-radius: 10px;")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(2)
    number = QLabel(value)
    number.setStyleSheet(
        f"background: transparent; border: none; color: {color};"
        f"font-size: {FONT_LABEL + 5}px; font-weight: bold;")
    text = QLabel(caption)
    text.setWordWrap(True)
    text.setStyleSheet(
        f"background: transparent; border: none; color: {COLOR_TEXT_MID};"
        f"font-size: {FONT_CAPTION}px;")
    layout.addWidget(number)
    layout.addWidget(text)
    return box


class _BarRows(QWidget):
    """Labelled horizontal bars: label on the right, bar in the middle, value
    on the left — each in its own column, so a long bar can never cover its
    own number.

    `maximum` fixes the scale. Scaling to the largest bar present turns 3.66
    against 3.75 into a landslide, which is why rating charts pass it.
    """

    def __init__(self, rows: Sequence[tuple], *, color: str,
                 maximum: Optional[float] = None) -> None:
        super().__init__()
        self._rows = list(rows)          # (label, value, display) triples
        self._color = color
        self._maximum = maximum
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(
            max(1, len(self._rows)) * (_BAR_HEIGHT + _BAR_GAP))
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        if not self._rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        width = self.width()
        label_w = max(metrics.horizontalAdvance(str(row[0]))
                      for row in self._rows) + 12
        value_w = max(metrics.horizontalAdvance(str(row[2]))
                      for row in self._rows) + 12
        track_w = max(20, width - label_w - value_w - 12)
        largest = self._maximum or max(
            (row[1] for row in self._rows), default=1) or 1

        y = 0
        for label, value, display in self._rows:
            # RTL: label at the right edge, value at the left.
            painter.setPen(QColor(COLOR_TEXT_DARK))
            painter.drawText(width - label_w, y, label_w, _BAR_HEIGHT,
                             int(Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignVCenter), str(label))

            track_x = value_w + 6
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#EFEFE8"))
            painter.drawRoundedRect(track_x, y + 3, track_w,
                                    _BAR_HEIGHT - 6, 3, 3)
            if value > 0:
                filled = max(2.0, track_w * min(1.0, value / largest))
                painter.setBrush(QColor(self._color))
                # RTL: the bar grows from the right edge leftward.
                painter.drawRoundedRect(
                    int(track_x + track_w - filled), y + 3, int(filled),
                    _BAR_HEIGHT - 6, 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.setPen(QColor(COLOR_TEXT_MID))
            painter.drawText(0, y, value_w, _BAR_HEIGHT,
                             int(Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignVCenter),
                             str(display))
            y += _BAR_HEIGHT + _BAR_GAP


class _StackedBars(QWidget):
    """One bar per row, split into coloured segments.

    Each segment carries its own number INSIDE it when it is wide enough to
    hold it — measured, not guessed, so a narrow segment drops its label
    instead of spilling over its neighbour. The row's total sits in its own
    column on the left, where no bar can ever cover it.

    Every bar is scaled to the LARGEST ROW TOTAL, so the lengths are
    comparable between rows rather than each row filling its own width.
    """

    def __init__(self, rows: Sequence[tuple],
                 legend: Sequence[tuple] = ()) -> None:
        super().__init__()
        self._rows = list(rows)      # (label, [(value, colour)], total)
        self._legend = list(legend)  # (label, colour)
        self.setStyleSheet("background: transparent;")
        rows_h = max(1, len(self._rows)) * (_STACK_BAR_H + _STACK_GAP)
        self.setMinimumHeight(rows_h + (_STACK_LEGEND_H if legend else 0))
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        if not self._rows:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        width = self.width()

        y = 0
        if self._legend:
            right = width - 4
            for label, colour in self._legend:
                text_w = metrics.horizontalAdvance(label)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colour))
                painter.drawRoundedRect(right - 10, y + 3, 10, 10, 2, 2)
                painter.setPen(QColor(COLOR_TEXT_MID))
                painter.drawText(right - 13 - text_w, y, text_w, _STACK_LEGEND_H,
                                 int(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter), label)
                right -= text_w + 13 + _STACK_LEGEND_GAP
            y += _STACK_LEGEND_H

        label_w = max(metrics.horizontalAdvance(str(row[0]))
                      for row in self._rows) + 12
        total_w = max(metrics.horizontalAdvance(str(row[2]))
                      for row in self._rows) + 12
        track_w = max(30, width - label_w - total_w - 12)
        largest = max((row[2] for row in self._rows), default=1) or 1

        small = QFont("Segoe UI", 8)
        small_metrics = QFontMetrics(small)
        for label, segments, total in self._rows:
            painter.setFont(font)
            painter.setPen(QColor(COLOR_TEXT_DARK))
            painter.drawText(width - label_w, y, label_w, _STACK_BAR_H,
                             int(Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignVCenter), str(label))

            track_x = total_w + 6
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#EFEFE8"))
            painter.drawRoundedRect(track_x, y + 3, track_w,
                                    _STACK_BAR_H - 6, 3, 3)

            # RTL: the first segment starts at the RIGHT edge of the track.
            right_edge = track_x + track_w
            for value, colour in segments:
                if value <= 0:
                    continue
                segment_w = track_w * value / largest
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colour))
                painter.drawRoundedRect(int(right_edge - segment_w), y + 3,
                                        int(segment_w), _STACK_BAR_H - 6, 3, 3)
                text = f"{value:,}"
                if small_metrics.horizontalAdvance(text) + 8 <= segment_w:
                    painter.setFont(small)
                    painter.setPen(QColor("white"))
                    painter.drawText(int(right_edge - segment_w), y,
                                     int(segment_w), _STACK_BAR_H,
                                     int(Qt.AlignmentFlag.AlignHCenter
                                         | Qt.AlignmentFlag.AlignVCenter), text)
                right_edge -= segment_w
            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.setFont(font)
            painter.setPen(QColor(COLOR_TEXT_DARK))
            painter.drawText(0, y, total_w, _STACK_BAR_H,
                             int(Qt.AlignmentFlag.AlignLeft
                                 | Qt.AlignmentFlag.AlignVCenter),
                             f"{total:,}")
            y += _STACK_BAR_H + _STACK_GAP


class _TrendChart(QWidget):
    """Meals per month as zero-based columns.

    The axis starts at ZERO deliberately: a truncated axis makes a steady run
    of months look like a collapse, which is exactly the false story this
    chart existed to avoid in the first place.
    """

    def __init__(self, points: Sequence[MonthPoint]) -> None:
        super().__init__()
        self._points = list(points)
        self.setMinimumHeight(_TREND_CHART_HEIGHT)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        if not self._points:
            painter.setPen(QColor(COLOR_TEXT_MID))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             _NO_MONTHS)
            return

        width, height = self.width(), self.height()
        plot_h = height - 40
        largest = max(point.meals for point in self._points) or 1
        slot = width / len(self._points)
        bar_w = min(slot * 0.55, 46.0)

        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.drawLine(0, plot_h, width, plot_h)

        for index, point in enumerate(self._points):
            # RTL: the earliest month on the right.
            centre = width - (index + 0.5) * slot
            bar_h = (point.meals / largest) * (plot_h - 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLOR_ACCENT))
            painter.drawRoundedRect(int(centre - bar_w / 2),
                                    int(plot_h - bar_h), int(bar_w),
                                    int(bar_h), 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(COLOR_TEXT_DARK))
            painter.drawText(int(centre - slot / 2), int(plot_h - bar_h - 15),
                             int(slot), 14,
                             int(Qt.AlignmentFlag.AlignHCenter
                                 | Qt.AlignmentFlag.AlignVCenter),
                             f"{point.meals:,}")
            painter.setPen(QColor(COLOR_TEXT_MID))
            painter.drawText(int(centre - slot / 2), plot_h + 4, int(slot), 14,
                             int(Qt.AlignmentFlag.AlignHCenter
                                 | Qt.AlignmentFlag.AlignVCenter),
                             _month_label(point.month))


class DeepStatsPanel(QWidget):
    """The three deep sections, with one month picker driving the two that
    are month-scoped. The trend spans every month that has data."""

    def __init__(self) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet("background: transparent;")
        self._months: List[str] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(_SECTION_GAP)

        self._month_combo = QComboBox()
        self._month_combo.setMinimumHeight(32)
        self._month_combo.setMinimumWidth(160)
        self._month_combo.currentIndexChanged.connect(self._render_for_month)

        self._trend_holder = QVBoxLayout()
        self._month_holder = QVBoxLayout()
        for holder in (self._trend_holder, self._month_holder):
            holder.setContentsMargins(0, 0, 0, 0)
            holder.setSpacing(_SECTION_GAP)

        self._layout.addLayout(self._build_header())
        self._layout.addLayout(self._trend_holder)
        self._layout.addLayout(self._month_holder)
        self.refresh()

    def current_month(self) -> Optional[str]:
        """The month the sections below are showing — what a report exported
        from this page has to cover."""
        return self._month_combo.currentData()

    # ── build ───────────────────────────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        heading = QLabel(_HEADING)
        heading.setStyleSheet(
            f"background: transparent; color: {COLOR_TEXT_DARK};"
            f"font-size: {FONT_LABEL + 2}px; font-weight: bold;")
        row.addWidget(heading)
        row.addStretch()
        caption = QLabel(_LBL_MONTH)
        caption.setStyleSheet(
            f"background: transparent; color: {COLOR_TEXT_MID};"
            f"font-size: {FONT_CAPTION}px; font-weight: bold;")
        row.addWidget(caption)
        row.addWidget(self._month_combo)
        return row

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # hide() as well as deleteLater(): deletion is deferred, and a
                # quick second refresh otherwise leaves the old section
                # ghosted behind the new one.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def refresh(self) -> None:
        from data.database import get_months_with_data

        self._months = sorted(get_months_with_data(), reverse=True)
        previous = self._month_combo.currentData()
        self._month_combo.blockSignals(True)
        self._month_combo.clear()
        for month in self._months:
            self._month_combo.addItem(_month_label(month), month)
        if previous in self._months:
            self._month_combo.setCurrentIndex(self._months.index(previous))
        self._month_combo.blockSignals(False)
        self._month_combo.setEnabled(bool(self._months))

        self._clear(self._trend_holder)
        self._trend_holder.addWidget(self._build_trend())
        self._render_for_month()

    def _render_for_month(self) -> None:
        self._clear(self._month_holder)
        month = self._month_combo.currentData()
        if not month:
            self._month_holder.addWidget(self._empty_card(_NO_MONTHS))
            return
        start, end = _month_bounds(month)
        self._month_holder.addWidget(self._build_classes())
        self._month_holder.addWidget(self._build_absence(start, end))
        self._month_holder.addWidget(self._build_feedback())
        self._month_holder.addWidget(self._build_completeness(start, end))

    def _empty_card(self, text: str) -> QWidget:
        card, layout = _card()
        layout.addWidget(_hint(text))
        return card

    # ── اتجاهات شهرية ───────────────────────────────────────────────────────

    def _build_trend(self) -> QWidget:
        from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
        from data.database import get_school_settings

        settings = get_school_settings()
        prices = {
            MEAL_FTOUR: settings.price_ftour if settings else "",
            MEAL_GHADA: settings.price_ghada if settings else "",
            MEAL_ASHA: settings.price_asha if settings else "",
        }
        points = monthly_trend(prices)

        card, layout = _card(_SEC_TREND)
        layout.addWidget(_hint(_TREND_HINT))
        if not points:
            layout.addWidget(_hint(_NO_MONTHS))
            return card
        layout.addWidget(_TrendChart(points))
        layout.addWidget(_trend_table(points))
        if any(point.cost_is_partial for point in points):
            layout.addWidget(_hint(_COST_PARTIAL_NOTE))
        return card

    # ── التلاميذ حسب القسم ──────────────────────────────────────────────────

    def _build_classes(self) -> QWidget:
        """Every class with its own gender split. The roster is the one thing
        every other figure on this page is measured against, so it is stated
        exactly rather than left to a donut."""
        from data.database import get_all_students

        card, layout = _card(_SEC_CLASSES)
        students = get_all_students()
        if not students:
            layout.addWidget(_hint(_NO_STUDENTS))
            return card

        layout.addWidget(_hint(_CLASS_HINT))
        rows, totals = class_chart_rows(students)
        legend = [(_CLASS_COLS[1], _GENDER_COLORS["male"]),
                  (_CLASS_COLS[2], _GENDER_COLORS["female"])]
        if totals["unknown"]:
            legend.append((_CLASS_UNSPECIFIED, _GENDER_COLORS[""]))
        layout.addWidget(_StackedBars(rows, legend))
        layout.addWidget(_hint(_CLASS_TOTAL_LINE.format(
            total=totals["all"], male=totals[GENDER_MALE_KEY],
            female=totals[GENDER_FEMALE_KEY])))
        if totals["unknown"]:
            # Counted, never split between the two columns.
            layout.addWidget(_hint(
                _CLASS_UNKNOWN_GENDER.format(count=totals["unknown"])))
        return card

    # ── أنماط الغياب ────────────────────────────────────────────────────────

    def _build_absence(self, start: str, end: str) -> QWidget:
        patterns = absence_patterns(start, end)
        card, layout = _card(_SEC_ABSENCE)
        if not patterns.total_absent:
            layout.addWidget(_hint(_NO_ABSENCE))
            return card

        stats = QHBoxLayout()
        stats.setSpacing(8)
        rate = patterns.rate
        stats.addWidget(_stat(
            f"{rate:.1%}" if rate is not None else _NO_AVERAGE,
            _ABSENCE_RATE,
            COLOR_DANGER if rate and rate > 0.1 else COLOR_TEXT_DARK))
        stats.addWidget(_stat(f"{patterns.total_absent:,}", _ABSENCE_TOTAL))
        stats.addWidget(_stat(f"{patterns.total_expected:,}",
                              _ABSENCE_EXPECTED))
        worst = patterns.worst_weekday
        stats.addWidget(_stat(
            _WEEKDAY_LABELS[worst] if worst is not None else _NO_AVERAGE,
            _ABSENCE_WORST, COLOR_WARNING))
        layout.addLayout(stats)

        if patterns.rate is None:
            layout.addWidget(_hint(_RATE_UNKNOWN))

        by_day = []
        for weekday in sorted(patterns.by_weekday):
            day_rate = patterns.weekday_rate(weekday)
            display = (f"{patterns.by_weekday[weekday]:,}"
                       + (f"  ·  {day_rate:.1%}" if day_rate is not None else ""))
            by_day.append((_WEEKDAY_LABELS[weekday],
                           patterns.by_weekday[weekday], display))
        if by_day:
            layout.addWidget(_hint(_ABSENCE_BY_DAY))
            layout.addWidget(_BarRows(by_day, color=COLOR_WARNING))

        by_cycle = [(_CYCLE_LABELS.get(cycle, cycle), count, f"{count:,}")
                    for cycle, count in sorted(patterns.by_cycle.items(),
                                               key=lambda item: -item[1])]
        if by_cycle:
            layout.addWidget(_hint(_ABSENCE_BY_CYCLE))
            layout.addWidget(_BarRows(by_cycle, color=COLOR_DANGER))
        return card

    # ── من أبدى الرأي ───────────────────────────────────────────────────────

    def _build_feedback(self) -> QWidget:
        """The cycle/gender patterns from تقييم التلاميذ, which until now
        only existed inside the exported PDF."""
        from data.database import (
            get_all_feedback, get_all_students, get_all_week_feedback,
        )

        card, layout = _card(_SEC_FEEDBACK)
        records = list(get_all_week_feedback()) + list(get_all_feedback())
        by_cycle = summarize_by_attribute(records, "cycle")
        by_gender = summarize_by_attribute(records, "gender")
        if not by_cycle and not by_gender:
            layout.addWidget(_hint(_NO_FEEDBACK))
            return card

        layout.addWidget(_hint(_FEEDBACK_HINT))
        students = get_all_students()
        today = datetime.date.today()
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
                # The group's REAL average age, from the roster — that is what
                # turns "تأهيلي rate it higher" into "the oldest pupils do".
                if profile is not None and profile.average_age is not None:
                    name = f"{name} · {profile.average_age:.1f} {_AGE_SUFFIX}"
                rows.append((name, summary.average,
                             f"{summary.average:.2f}  ·  {summary.count:,} "
                             f"{_OPINION_SUFFIX}"))
            if rows:
                # Scaled to 5, not to the best group: rescaling 3.66 against
                # 3.75 to full width would read as a landslide.
                layout.addWidget(_BarRows(rows, color=color, maximum=5.0))

        unclassified = ungrouped_responses(records)
        if unclassified:
            layout.addWidget(_hint(_UNGROUPED.format(count=unclassified)))
        return card

    # ── اكتمال الوثائق ──────────────────────────────────────────────────────

    def _build_completeness(self, start: str, end: str) -> QWidget:
        summary = document_completeness(start, end)
        card, layout = _card(_SEC_COMPLETENESS)
        layout.addWidget(_hint(_COMPLETENESS_HINT))
        if not summary.served_days:
            layout.addWidget(_hint(_NO_SERVED))
            return card

        stats = QHBoxLayout()
        stats.setSpacing(8)
        rate = summary.rate
        stats.addWidget(_stat(
            f"{rate:.0%}" if rate is not None else _NO_AVERAGE,
            _COMPLETE_RATE,
            COLOR_SUCCESS if rate == 1 else COLOR_WARNING))
        stats.addWidget(_stat(f"{summary.complete_days:,}", _COMPLETE_DAYS))
        stats.addWidget(_stat(f"{summary.served_days:,}", _SERVED_DAYS))
        layout.addLayout(stats)

        rows = []
        for key, label in _DOCUMENT_LABELS.items():
            done = summary.per_document.get(key, 0)
            share = summary.document_rate(key)
            rows.append((label, done,
                         f"{done}/{summary.served_days}"
                         + (f"  ·  {share:.0%}" if share is not None else "")))
        layout.addWidget(_BarRows(rows, color=COLOR_ACCENT,
                                  maximum=float(summary.served_days)))

        if not summary.gaps:
            layout.addWidget(_hint(_NO_GAPS))
            return card

        layout.addWidget(_hint(_GAPS_TITLE))
        for gap in summary.gaps[:_GAP_LIMIT]:
            missing = "، ".join(_DOCUMENT_LABELS.get(key, key)
                                for key in gap.missing)
            row = QLabel(f"{gap.date}  —  {missing}")
            row.setWordWrap(True)
            row.setStyleSheet(
                f"background: transparent; border: none; color: {COLOR_DANGER};"
                f"font-size: {FONT_CAPTION}px;")
            layout.addWidget(row)
        if len(summary.gaps) > _GAP_LIMIT:
            layout.addWidget(_hint(
                _GAP_MORE.format(count=len(summary.gaps) - _GAP_LIMIT)))
        return card


def _month_bounds(month: str) -> tuple:
    """First and last calendar day of a YYYY-MM month."""
    year, number = (int(part) for part in month.split("-"))
    first = datetime.date(year, number, 1)
    last = (datetime.date(year + (number == 12), (number % 12) + 1, 1)
            - datetime.timedelta(days=1))
    return first.isoformat(), last.isoformat()


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]], *,
           bold_last_row: bool = False) -> QWidget:
    """A small read-off table. Charts show shape; these numbers get copied
    into other documents, so they have to be exact."""
    table = QWidget()
    table.setStyleSheet("background: transparent;")
    grid = QVBoxLayout(table)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(0)

    def line(values: Sequence[str], *, header: bool = False,
             strong: bool = False) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            f"background: {COLOR_LIGHT_BG if header or strong else 'transparent'};"
            "border: none;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)
        for index, value in enumerate(values):
            cell = QLabel(str(value))
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weight = "bold" if header or strong or index == 0 else "normal"
            colour = COLOR_TEXT_DARK if header or strong else COLOR_TEXT_MID
            cell.setStyleSheet(
                f"background: transparent; border: none; color: {colour};"
                f"font-size: {FONT_CAPTION}px; font-weight: {weight};")
            layout.addWidget(cell, 1)
        return row

    grid.addWidget(line(headers, header=True))
    for index, values in enumerate(rows):
        grid.addWidget(line(
            values, strong=bold_last_row and index == len(rows) - 1))
    return table


def _trend_table(points: Sequence[MonthPoint]) -> QWidget:
    rows = []
    for point in reversed(points):          # newest first, like every table here
        per_day = point.meals_per_day
        rows.append([
            _month_label(point.month),
            f"{point.meals:,}",
            f"{point.days}",
            f"{per_day:,.0f}" if per_day is not None else _NO_AVERAGE,
            f"{point.cost:,.2f}"
            + (_COST_PARTIAL_MARK if point.cost_is_partial else ""),
        ])
    return _table(_TREND_COLS, rows)


def class_chart_rows(students) -> tuple:
    """(rows, totals) shaped for _StackedBars: one bar per class, split into
    ذكور / إناث / غير محدد."""
    from core.student_stats import (
        GENDER_FEMALE, GENDER_MALE, breakdown_by_class,
    )

    rows = []
    totals = {GENDER_MALE: 0, GENDER_FEMALE: 0, "unknown": 0, "all": 0}
    for entry in breakdown_by_class(students):
        males = entry.count(GENDER_MALE)
        females = entry.count(GENDER_FEMALE)
        unknown = entry.unknown_gender
        totals[GENDER_MALE] += males
        totals[GENDER_FEMALE] += females
        totals["unknown"] += unknown
        totals["all"] += entry.total
        rows.append((
            entry.name or _CLASS_UNKNOWN,
            [(males, _GENDER_COLORS["male"]),
             (females, _GENDER_COLORS["female"]),
             (unknown, _GENDER_COLORS[""])],
            entry.total,
        ))
    return rows, totals
