"""
src/ui/dashboard_screen.py
Statistics dashboard with custom painted charts (no QtCharts dependency).
Layout:
  1. Header        — school name + date
  2. KPI row       — 4 stat cards
  3. Bar chart     — last 7 days (ftour / ghada / asha)
  4. Trend line    — 30-day total meals
  5. Donut row     — beneficiary split + grants split
  6. Meal pills    — monthly totals per meal type
"""

from __future__ import annotations
from typing import Callable

import logging
import math
from pathlib import Path

from PySide6.QtCore import QMargins, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QBrush,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from config.settings import (
    COLOR_ACCENT, COLOR_BORDER, COLOR_LIGHT_BG, COLOR_PRIMARY,
    COLOR_PURPLE, COLOR_SUCCESS, COLOR_TEAL,
    COLOR_TEXT_DARK, COLOR_TEXT_MID, COLOR_WARNING,
    COLOR_DANGER,
    FONT_BODY, FONT_CAPTION, FONT_LABEL, FONT_SECTION,
)
from core.stats_service import DashboardData, load_dashboard
from data.database import get_school_settings
from ui.widgets.icon_button import IconButton

_PAGE_TITLE = "الإحصائيات"
_BTN_EXPORT = "تصدير التقرير"
_BTN_EXPORT_ICON = "📄"
_PDF_DIALOG_TITLE = "تصدير تقرير الإحصائيات"
_PDF_DEFAULT_NAME = "تقرير_الإحصائيات"
_PDF_FILTER = "PDF (*.pdf)"
_MSG_EXPORT_SAVED = "تم تصدير التقرير إلى:\n"
_MSG_EXPORT_FAILED = "تعذر تصدير التقرير. تحقق من المكان المختار ثم أعد المحاولة."
_MSG_EXPORT_LOCKED = ("تعذر الحفظ في هذا الملف — قد يكون مفتوحاً في برنامج آخر. "
                      "أغلقه ثم أعد المحاولة.")
_MSG_EXPORT_EMPTY = "لا توجد بيانات شهرية بعد، فلا شيء لتصديره."
_MSG_NO_SETTINGS = "أدخل بيانات المؤسسة في الإعدادات أولاً."

_LOGGER = logging.getLogger(__name__)


def _tint(hex_color: str, alpha: float) -> str:
    """hex_color at the given opacity (0-1), as an unambiguous rgba() string.
    Qt's QColor/QSS parse an 8-digit hex as #AARRGGBB (alpha first), not the
    web convention of #RRGGBBAA (alpha last) — appending alpha digits onto a
    hex string silently produces a completely different, wrong color."""
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


# ── Custom chart widgets ──────────────────────────────────────────────────────

class BarChartWidget(QWidget):
    """Grouped bar chart for last-7-days meal attendance."""

    def __init__(self, data: DashboardData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 40
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_t - pad_b

        days = self._data.weekly
        n = len(days)
        if n == 0:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "لا توجد بيانات")
            return

        max_val = max((max(d.ftour, d.ghada, d.asha) for d in days), default=1) or 1

        group_w = chart_w / n
        bar_w   = group_w * 0.22
        gap     = group_w * 0.04
        colors  = [QColor(_MEAL_COLOR_FTOUR), QColor(_MEAL_COLOR_GHADA), QColor(_MEAL_COLOR_ASHA)]

        # grid lines
        p.setPen(QPen(QColor(COLOR_BORDER), 1))
        for i in range(5):
            y = pad_t + i * chart_h // 4
            p.drawLine(pad_l, y, pad_l + chart_w, y)

        # bars
        label_font = QFont("Segoe UI", 8)
        label_metrics = QFontMetrics(label_font)
        sample_w = label_metrics.horizontalAdvance("00/00")
        label_stride = max(1, math.ceil((sample_w + 6) / group_w))

        for gi, day in enumerate(days):
            vals = [day.ftour, day.ghada, day.asha]
            for bi, (val, col) in enumerate(zip(vals, colors)):
                bh = int((val / max_val) * chart_h)
                bx = int(pad_l + gi * group_w + bi * (bar_w + gap) + gap)
                by = pad_t + chart_h - bh
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(col))
                p.drawRoundedRect(bx, by, int(bar_w), bh, 3, 3)

            # x label (DD/MM) — thinned out when the chart is too narrow to
            # fit one per day without overlapping.
            if gi % label_stride != 0:
                continue
            parts = day.log_date.split("-")
            lbl = f"{parts[2]}/{parts[1]}"
            lbl_w = label_metrics.horizontalAdvance(lbl)
            fx = int(pad_l + gi * group_w + group_w / 2 - lbl_w / 2)
            p.setPen(QColor(COLOR_TEXT_MID))
            p.setFont(label_font)
            p.drawText(fx, pad_t + chart_h + 18, lbl)

        # y labels
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(COLOR_TEXT_MID))
        for i in range(5):
            val = int(max_val * (4 - i) / 4)
            y   = pad_t + i * chart_h // 4
            p.drawText(0, y + 4, pad_l - 4, 16, Qt.AlignmentFlag.AlignRight, str(val))

        # legend
        legend = [("فطور", _MEAL_COLOR_FTOUR), ("غداء", _MEAL_COLOR_GHADA), ("عشاء", _MEAL_COLOR_ASHA)]
        lx = pad_l
        for name, col in legend:
            p.setBrush(QBrush(QColor(col)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(lx, h - 14, 12, 10, 2, 2)
            p.setPen(QColor(COLOR_TEXT_MID))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(lx + 14, h - 4, name)
            lx += 55


class TrendLineWidget(QWidget):
    """30-day total meals trend line."""

    def __init__(self, data: DashboardData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 32
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_t - pad_b

        trend = self._data.trend
        n = len(trend)
        if n < 2:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "لا توجد بيانات كافية")
            return

        max_val = max((d.total for d in trend), default=1) or 1

        # grid lines
        p.setPen(QPen(QColor(COLOR_BORDER), 1))
        for i in range(5):
            y = pad_t + i * chart_h // 4
            p.drawLine(pad_l, y, pad_l + chart_w, y)

        # gradient fill under the line
        path = QPainterPath()
        pts = []
        for i, day in enumerate(trend):
            x = pad_l + int(i * chart_w / (n - 1))
            y = pad_t + chart_h - int((day.total / max_val) * chart_h)
            pts.append((x, y))

        path.moveTo(pts[0][0], pad_t + chart_h)
        for x, y in pts:
            path.lineTo(x, y)
        path.lineTo(pts[-1][0], pad_t + chart_h)
        path.closeSubpath()

        grad = QLinearGradient(0, pad_t, 0, pad_t + chart_h)
        grad.setColorAt(0, QColor(COLOR_ACCENT + "55"))
        grad.setColorAt(1, QColor(COLOR_ACCENT + "00"))
        p.fillPath(path, grad)

        # line
        pen = QPen(QColor(COLOR_ACCENT), 2)
        p.setPen(pen)
        for i in range(1, len(pts)):
            p.drawLine(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1])

        # dots at data points
        p.setBrush(QBrush(QColor(COLOR_ACCENT)))
        p.setPen(QPen(QColor("white"), 1))
        for x, y in pts:
            if self._data.trend[pts.index((x, y))].total > 0:
                p.drawEllipse(x - 4, y - 4, 8, 8)

        # y labels
        p.setPen(QColor(COLOR_TEXT_MID))
        p.setFont(QFont("Segoe UI", 8))
        for i in range(5):
            val = int(max_val * (4 - i) / 4)
            y   = pad_t + i * chart_h // 4
            p.drawText(0, y + 4, pad_l - 4, 16, Qt.AlignmentFlag.AlignRight, str(val))


_DONUT_LEGEND_ROW_H = 15
_DONUT_LEGEND_GAP = 10
_DONUT_SWATCH_W = 13


class DonutWidget(QWidget):
    """Simple donut chart."""

    def __init__(self, slices: list[tuple[str, int, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._slices = slices
        self.setMinimumSize(130, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        total = sum(v for _, v, _ in self._slices)
        has_data = total > 0

        # The legend gets its own reserved strip. It used to be drawn at
        # oy + size + 8 with the donut centred in the FULL height, which put
        # it past the bottom edge — every label on all four donuts was
        # clipped away and only the colour swatches showed.
        legend_font = QFont("Segoe UI", 8)
        rows = self._legend_rows(QFontMetrics(legend_font), w - 8)
        legend_h = len(rows) * _DONUT_LEGEND_ROW_H + 4 if rows else 0

        size = max(40, min(w, h - legend_h) - 20)
        ox   = (w - size) // 2
        oy   = max(0, (h - legend_h - size) // 2)
        rect = QRectF(ox, oy, size, size)
        hole = QRectF(ox + size * 0.3, oy + size * 0.3, size * 0.4, size * 0.4)

        if not has_data:
            p.setBrush(QBrush(QColor(COLOR_BORDER)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(rect)
            p.setBrush(QBrush(QColor("white")))
            p.drawEllipse(hole)
            p.setPen(QColor(COLOR_TEXT_MID))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "لا بيانات")
            return

        angle = 90 * 16  # start at top
        for label, value, color in self._slices:
            span = int((value / total) * 360 * 16)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPie(rect, angle, span)
            angle += span

        # cut hole
        p.setBrush(QBrush(QColor("white")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(hole)

        # legend below, laid out from MEASURED widths — a fixed 80px stride
        # ran the later entries off the card whenever a label was long.
        p.setFont(legend_font)
        legend_y = oy + size + 6
        # Packed RIGHT to LEFT, each swatch on the right of its own label:
        # this is an RTL page, so the first slice belongs at the right edge.
        for row in rows:
            right = self.width() - 4
            for text, color, width in row:
                p.setBrush(QBrush(QColor(color)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(right - 10, legend_y + 1, 10, 10, 2, 2)
                p.setPen(QColor(COLOR_TEXT_MID))
                p.drawText(right - width, legend_y + 10, text)
                right -= width + _DONUT_LEGEND_GAP
            legend_y += _DONUT_LEGEND_ROW_H

    def _legend_rows(self, metrics: QFontMetrics, available: int) -> list:
        """Pack the legend into as many rows as it needs, so nothing is cut
        off and nothing runs past the card."""
        total = sum(value for _label, value, _color in self._slices)
        if total <= 0:
            return []
        rows: list = []
        current: list = []
        used = 0
        for label, value, color in self._slices:
            text = f"{label} {round(value / total * 100)}٪"
            width = metrics.horizontalAdvance(text) + _DONUT_SWATCH_W
            if current and used + width > available:
                rows.append(current)
                current, used = [], 0
            current.append((text, color, width))
            used += width + _DONUT_LEGEND_GAP
        if current:
            rows.append(current)
        return rows


# ── Helper widgets ────────────────────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, icon: str, title: str, value: str, subtitle: str, color: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFixedHeight(86)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            #statCard {{
                background-color: white;
                border: 1px solid #e3e0d2;
                border-radius: 16px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        text_w = QWidget()
        text_w.setStyleSheet("background: transparent; border: none;")
        text_l = QVBoxLayout(text_w)
        text_l.setContentsMargins(0, 0, 0, 0)
        text_l.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(f"color: {COLOR_TEXT_MID}; font-size: {FONT_CAPTION}px; font-weight: 700; background: transparent;")

        v = QLabel(value)
        f = QFont(); f.setPointSize(17); f.setBold(True)
        v.setFont(f)
        v.setStyleSheet(f"color: {COLOR_TEXT_DARK}; background: transparent;")

        s = QLabel(subtitle)
        s.setStyleSheet(f"color: {color}; font-size: {FONT_CAPTION}px; font-weight: 700; background: transparent;")
        s.setWordWrap(True)

        text_l.addWidget(t); text_l.addWidget(v); text_l.addWidget(s)

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedSize(38, 38)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"background-color: {_tint(color, 0.13)}; color: {color}; border: none;"
            "border-radius: 19px; font-size: 17px;"
        )

        layout.addWidget(text_w, stretch=1)
        layout.addWidget(icon_lbl)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18); shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(shadow)


def _card(title: str, widget: QWidget) -> QFrame:
    """Wrap any widget in a white rounded card."""
    card = QFrame()
    card.setObjectName("dashboardCard")
    card.setStyleSheet("""
        #dashboardCard {
            background: white;
            border: 1px solid #e3e0d2;
            border-radius: 14px;
        }
    """)
    shadow = QGraphicsDropShadowEffect(card)
    shadow.setBlurRadius(14); shadow.setOffset(0, 3)
    shadow.setColor(QColor(0, 0, 0, 18))
    card.setGraphicsEffect(shadow)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(6)

    t = QLabel(title)
    t.setStyleSheet(f"font-size: {FONT_LABEL}px; font-weight: bold; color: {COLOR_TEXT_DARK}; background: transparent;")
    layout.addWidget(t)
    layout.addWidget(widget)
    return card


# ── Section builders ──────────────────────────────────────────────────────────

def _build_header(data: DashboardData) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(4, 0, 4, 4)

    greeting = QLabel(f"مرحباً — {data.school_name}" if data.school_name else "لوحة المعلومات")
    f = QFont(); f.setPointSize(17); f.setBold(True)
    greeting.setFont(f)
    greeting.setStyleSheet(f"color: {COLOR_PRIMARY};")

    date_lbl = QLabel(data.today_label)
    date_lbl.setStyleSheet(f"color: {COLOR_TEXT_MID}; font-size: {FONT_BODY}px;")

    layout.addWidget(greeting)
    layout.addStretch()
    layout.addWidget(date_lbl)
    return widget


def _build_kpi_row(data: DashboardData) -> QWidget:
    row = QWidget()
    layout = QGridLayout(row)
    layout.setSpacing(10)
    layout.setContentsMargins(0, 0, 0, 0)

    if data.last_log_date:
        parts = data.last_log_date.split("-")
        last_log = f"{parts[2]}/{parts[1]}/{parts[0]}"
    else:
        last_log = "—"

    cards = [
        StatCard("👥", "إجمالي المستفيدين", f"{data.students.total:,}",
                 f"داخلي {data.students.internat_count}  •  دار الطالب {data.students.dar_talib_count}  •  مطعم {data.students.cantine_count}",
                 COLOR_PRIMARY),
        StatCard("🍽️", f"وجبات {data.month_label}", f"{data.month.total_meals:,}",
                 f"{data.month.days_logged} يوم مسجَّل هذا الشهر", COLOR_ACCENT),
        StatCard("📊", "متوسط يومي", f"{data.month.avg_daily:,.0f}",
                 "وجبة في اليوم (هذا الشهر)", COLOR_SUCCESS),
        StatCard("📅", "آخر تسجيل", last_log,
                 "تاريخ آخر إدخال في النظام", COLOR_WARNING),
        StatCard("✅", "نسبة الحضور", f"{data.month.attendance_rate:,.0f}%",
                 "من إجمالي الحضور والغياب (هذا الشهر)", COLOR_TEAL),
        StatCard("⚠️", "المخالفات", f"{data.month.infractions_count:,}",
                 "محاضر مخالفة في حق الشركة هذا الشهر", COLOR_DANGER),
    ]
    for i, card in enumerate(cards):
        layout.addWidget(card, i // 3, i % 3)
    return row


def _build_charts_row_1(data: DashboardData) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setSpacing(14)
    layout.setContentsMargins(0, 0, 0, 0)

    bar_card = _card("الحضور خلال الأسبوع الأخير — فطور / غداء / عشاء",
                     BarChartWidget(data))
    donut_card = _card("توزيع المستفيدين",
                       DonutWidget([
                           ("داخلي",  data.students.internat_count,  COLOR_PRIMARY),
                           ("دار الطالب", data.students.dar_talib_count, COLOR_WARNING),
                           ("مطعم",   data.students.cantine_count,   COLOR_ACCENT),
                           ("أساتذة", data.students.teachers_count,  COLOR_TEAL),
                       ]))
    cycle_slices = [
        (label, count, _CYCLE_PALETTE[i % len(_CYCLE_PALETTE)])
        for i, (label, count) in enumerate(data.cycle_breakdown)
    ]
    cycle_card = _card("توزيع حسب السلك", DonutWidget(cycle_slices))
    layout.addWidget(bar_card,   stretch=1)
    layout.addWidget(donut_card, stretch=1)
    layout.addWidget(cycle_card, stretch=1)
    return row


def _build_charts_row_2(data: DashboardData) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setSpacing(14)
    layout.setContentsMargins(0, 0, 0, 0)

    line_card = _card("منحنى إجمالي الوجبات — آخر 30 يوماً",
                      TrendLineWidget(data))
    grant_card = _card("توزيع المنح",
                       DonutWidget([
                           ("منحة كاملة", data.students.full_grant_count, COLOR_SUCCESS),
                           ("نصف منحة",   data.students.half_grant_count, COLOR_WARNING),
                       ]))
    gender_card = _card("توزيع حسب الجنس",
                       DonutWidget([
                           ("ذكور",  data.students.male_count,   COLOR_TEAL),
                           ("إناث",  data.students.female_count, COLOR_PURPLE),
                       ]))
    layout.addWidget(line_card,   stretch=1)
    layout.addWidget(grant_card,  stretch=1)
    layout.addWidget(gender_card, stretch=1)
    return row


# Dedicated meal colors — amber/teal/navy, matching the meal program table's
# convention (ui_design.md). Kept separate from COLOR_ACCENT/COLOR_SUCCESS:
# those both became shades of green in the Stage 3 palette migration, which
# made فطور and غداء indistinguishable when this reused them.
_MEAL_COLOR_FTOUR = "#EF9F27"
_MEAL_COLOR_GHADA = "#1D9E75"
_MEAL_COLOR_ASHA  = "#534AB7"

_CYCLE_PALETTE = [COLOR_ACCENT, COLOR_TEAL, COLOR_WARNING, COLOR_PURPLE, COLOR_PRIMARY, COLOR_DANGER]


def _build_meal_pills(data: DashboardData) -> QWidget:
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setSpacing(14)
    layout.setContentsMargins(0, 0, 0, 0)

    pills = [
        ("🌅", "فطور", data.month.ftour_total, _MEAL_COLOR_FTOUR),
        ("☀️", "غداء", data.month.ghada_total, _MEAL_COLOR_GHADA),
        ("🌙", "عشاء", data.month.asha_total,  _MEAL_COLOR_ASHA),
    ]
    for icon, label, count, color in pills:
        pill = QFrame()
        pill.setStyleSheet(f"""
            QFrame {{
                background-color: {_tint(color, 0.08)};
                border: 1px solid {_tint(color, 0.33)};
                border-radius: 12px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(pill)
        shadow.setBlurRadius(10); shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 15))
        pill.setGraphicsEffect(shadow)

        pl = QHBoxLayout(pill)
        pl.setContentsMargins(16, 10, 16, 10)
        pl.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 15px; background: transparent;")

        meal_lbl = QLabel(label)
        meal_lbl.setStyleSheet(f"color: {color}; font-size: {FONT_LABEL}px; font-weight: bold; background: transparent;")

        count_lbl = QLabel(f"{count:,}")
        f = QFont(); f.setPointSize(16); f.setBold(True)
        count_lbl.setFont(f)
        count_lbl.setStyleSheet(f"color: {COLOR_TEXT_DARK}; background: transparent;")

        unit_lbl = QLabel("وجبة")
        unit_lbl.setStyleSheet(f"color: {COLOR_TEXT_MID}; font-size: {FONT_LABEL}px; background: transparent;")

        pl.addWidget(icon_lbl); pl.addWidget(meal_lbl); pl.addStretch()
        pl.addWidget(count_lbl); pl.addWidget(unit_lbl)
        layout.addWidget(pill, stretch=1)

    return widget


# ── Main DashboardScreen ──────────────────────────────────────────────────────

class DashboardScreen(QWidget):
    """
    Full statistics home screen.
    navigate_to: callback to switch screens (kept for API compatibility).
    """

    def __init__(self, navigate_to: Callable[[int], None]) -> None:
        super().__init__()
        self._navigate = navigate_to
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._render()

    def _build_header_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        title = QLabel(_PAGE_TITLE)
        font = QFont(); font.setPointSize(15); font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(
            f"background: transparent; color: {COLOR_TEXT_DARK};")
        row.addWidget(title)
        row.addStretch()
        # COLOR_ACCENT, matching every other export button in the app.
        export = IconButton(
            _BTN_EXPORT, icon=_BTN_EXPORT_ICON, bg=COLOR_ACCENT,
            text_color="white", border_radius=10, padding_h=14, font_size=12,
            bold=True, min_height=36)
        export.clicked.connect(self._on_export)
        row.addWidget(export)
        return row

    def _on_export(self) -> None:
        """Save الإحصائيات as a signed PDF for the month on screen."""
        month = getattr(self, "_deep", None) and self._deep.current_month()
        if not month:
            QMessageBox.information(self, _PAGE_TITLE, _MSG_EXPORT_EMPTY)
            return
        settings = get_school_settings()
        if settings is None:
            QMessageBox.information(self, _PAGE_TITLE, _MSG_NO_SETTINGS)
            return

        default = f"{_PDF_DEFAULT_NAME}_{month}.pdf"
        path_str, _filter = QFileDialog.getSaveFileName(
            self, _PDF_DIALOG_TITLE, default, _PDF_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            from ui.dashboard_export import write_statistics_report_pdf
            write_statistics_report_pdf(path, settings, month)
        except PermissionError:
            _LOGGER.exception("statistics report: destination not writable")
            QMessageBox.critical(self, _PAGE_TITLE, _MSG_EXPORT_LOCKED)
            return
        except Exception:
            # Arabic for the user, the technical detail in the log — §5.
            _LOGGER.exception("statistics report export failed")
            QMessageBox.critical(self, _PAGE_TITLE, _MSG_EXPORT_FAILED)
            return
        QMessageBox.information(self, _PAGE_TITLE, f"{_MSG_EXPORT_SAVED}{path}")

    def refresh(self) -> None:
        while self._outer_layout.count():
            item = self._outer_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._render()

    def _render(self) -> None:
        data = load_dashboard()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {COLOR_LIGHT_BG};")

        container = QWidget()
        container.setStyleSheet(f"background-color: {COLOR_LIGHT_BG};")
        inner = QVBoxLayout(container)
        inner.setContentsMargins(18, 14, 18, 18)
        inner.setSpacing(12)

        # The school-name banner moved to الصفحة الرئيسية and the وصول سريع row was
        # removed outright (2026-08-29, user's request) — الصفحة الرئيسية is the home
        # screen and now carries both; this page is for the numbers.
        inner.addLayout(self._build_header_row())
        inner.addWidget(_build_kpi_row(data))
        inner.addWidget(_build_charts_row_1(data))
        inner.addWidget(_build_charts_row_2(data))

        pills_title = QLabel(f"إجمالي الوجبات حسب النوع  —  {data.month_label}")
        pills_title.setStyleSheet(f"font-size: {FONT_LABEL}px; font-weight: bold; color: {COLOR_TEXT_DARK};")
        inner.addWidget(pills_title)
        inner.addWidget(_build_meal_pills(data))

        # The deep half — trends, absence patterns, who rated what,
        # and which days still owe paperwork. Its own module: this
        # file was already long before it.
        from ui.dashboard_deep import DeepStatsPanel
        self._deep = DeepStatsPanel()
        inner.addWidget(self._deep)

        scroll.setWidget(container)
        self._outer_layout.addWidget(scroll)
