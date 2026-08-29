"""
src/ui/feedback_collect.py
Getting pupils' opinions OFF the refectory floor and into the app.

Two routes, both chosen by the user on 2026-08-29 over a QR/phone flow — the
pupils have phones but no WiFi that reaches the office PC, so a served page
would have been built and never used:

  ورقة تفريغ الآراء — a printed sheet listing the WEEK'S DISHES with five wide
      tally boxes each. Someone marks it in the refectory, then types the five
      totals per dish into the app.
  Excel round-trip — the same rows as a workbook with empty count columns,
      filled anywhere (including from a form's own export) and imported back.

The unit is one DISH PER WEEK, not per day: a week serves ~12 distinct dishes
against 21 day-slots, and a dish served twice is asked about once.

The import NEVER invents a row: a line whose counts are all empty is skipped
and reported, not saved as a meal nobody liked.
"""
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter,
    QPen,
)

from config.settings import (
    COLOR_BORDER, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, MEAL_LABELS,
)
from core.feedback import (
    COUNT_FIELDS, RATING_LEVELS, normalize_dish, week_end_of, week_start_of,
)
from core.models import SchoolSettings, WeekFeedback
from core.ramadan import meals_for_date
from data.database import (
    get_all_programs, get_program_entries, get_ramadan_overrides,
    get_school_settings, get_week_feedback, save_week_feedback,
)
from ui.document_header import draw_official_pdf_footer, draw_official_pdf_header

# ── Arabic strings ──────────────────────────────────────────────────────────
_TALLY_TITLE = "ورقة تفريغ آراء التلاميذ"
_TALLY_SUBTITLE = ("ضع علامة لكل تلميذ حسب رأيه في الوجبة، ثم أدخل المجاميع "
                   "في التطبيق")
_SHEET_NAME = "آراء التلاميذ"
_LBL_PERIOD = "الفترة"
_LBL_WEEK_KEY = "الأسبوع"
_LBL_GROUP_KEY = "الفئة"
_GROUP_ANY = "غير محدد"
_CYCLE_LABELS = {"primary": "ابتدائي", "collegial": "إعدادي",
                 "qualifying": "تأهيلي"}
_GENDER_LABELS = {"male": "ذكور", "female": "إناث"}
_MSG_BAD_GROUP = ("ورقة «{sheet}»: الفئة «{group}» غير معروفة — صحّح الخانة D2 "
                  "أو أعد تصدير الورقة من التطبيق.")
_MSG_NO_WEEK = "الملف لا يحمل تاريخ الأسبوع في الخانة B2."
_HDR_DISH = "الطبق"
_LBL_WEEK = "أسبوع"
_ARABIC_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر",
]
_RATING_LABELS = {5: "ممتاز", 4: "جيد", 3: "متوسط", 2: "ضعيف", 1: "سيء"}
_NO_MENU = "—"

_EXCEL_HDR = [_HDR_DISH] + [_RATING_LABELS[level] for level in RATING_LEVELS]

_DAY_NAMES = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة",
              "السبت", "الأحد"]

_MARGIN = 40.0
_ROW_HEIGHT = 40.0          # room to actually write tally marks
_HEADER_ROW_HEIGHT = 24.0
_BODY_SIZE = 9
_META_SIZE = 9
# the dish, then one wide box per level
_FIXED_SHARE = (0.34,)
_LEVEL_SHARE = (1.0 - sum(_FIXED_SHARE)) / len(RATING_LEVELS)

_LOGGER = logging.getLogger(__name__)


# ── The period's served meals ───────────────────────────────────────────────

def _menu_index() -> Dict[Tuple[bool, int, str], str]:
    """Every program's menu, keyed by (is_ramadan, day_of_week, meal)."""
    index: Dict[Tuple[bool, int, str], str] = {}
    for program in get_all_programs():
        if program.id is None:
            continue
        for entry in get_program_entries(program.id):
            key = (bool(program.is_ramadan), entry.day_of_week, entry.meal_type)
            index.setdefault(key, entry.menu_text.strip())
    return index


def period_rows(start: datetime.date, end: datetime.date,
                settings: Optional[SchoolSettings] = None) -> List[Tuple[str, str, str]]:
    """(date, meal_type, dish) for every meal served in the range.

    A day's meals come from its OWN date, so a Ramadan day contributes
    إفطار/سحور rather than the three normal meals; the dish is that day's
    planned menu line when the program has one.
    """
    settings = settings or get_school_settings()
    overrides = get_ramadan_overrides()
    menus = _menu_index()
    rows: List[Tuple[str, str, str]] = []
    day = start
    while day <= end:
        date_str = day.isoformat()
        meals = meals_for_date(date_str, settings, overrides)
        # The program grid stores السبت as 0; Python's weekday() starts at
        # Monday, hence the same +2 shift the other screens use.
        code = (day.weekday() + 2) % 7
        for meal in meals:
            is_ramadan_meal = meal not in ("ftour", "ghada", "asha")
            dish = menus.get((is_ramadan_meal, code, meal), "")
            rows.append((date_str, meal, dish))
        day += datetime.timedelta(days=1)
    return rows


def week_label(week_start: str) -> str:
    """"أسبوع 11 - 17 مايو 2026", naming both months only when the week
    straddles one and both years only when it straddles a year."""
    monday, sunday = week_start_of(week_start), week_end_of(week_start)
    if not monday:
        return ""
    start = datetime.date.fromisoformat(monday)
    end = datetime.date.fromisoformat(sunday)
    start_month = _ARABIC_MONTHS[start.month - 1]
    end_month = _ARABIC_MONTHS[end.month - 1]
    if start.year != end.year:
        return (f"{_LBL_WEEK} {start.day} {start_month} {start.year} - "
                f"{end.day} {end_month} {end.year}")
    if start.month != end.month:
        return (f"{_LBL_WEEK} {start.day} {start_month} - "
                f"{end.day} {end_month} {end.year}")
    return f"{_LBL_WEEK} {start.day} - {end.day} {start_month} {start.year}"


def dishes_for_week(week_start: str,
                    settings: Optional[SchoolSettings] = None) -> List[str]:
    """The DISTINCT menu lines served in one week, in the order they appear.

    A dish served twice in the week appears once — that is the whole point of
    rating the menu rather than the days.
    """
    monday = week_start_of(week_start)
    if not monday:
        return []
    start = datetime.date.fromisoformat(monday)
    rows = period_rows(start, start + datetime.timedelta(days=6), settings)
    dishes: List[str] = []
    for _date, _meal, dish in rows:
        name = normalize_dish(dish)
        if name and name not in dishes:
            dishes.append(name)
    return dishes


# ── The printed tally sheet ─────────────────────────────────────────────────

def _text(painter: QPainter, rect: QRectF, value: str, *, size: int,
          color: str, bold: bool = False,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter) -> float:
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


def _cell(painter: QPainter, rect: QRectF, value: str = "", *,
          bold: bool = False, fill: str = "",
          color: str = COLOR_TEXT_PRIMARY) -> None:
    if fill:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fill))
        painter.drawRect(rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(COLOR_BORDER), 1))
    painter.drawRect(rect)
    if value:
        _text(painter, QRectF(rect.left() + 4, rect.top(), rect.width() - 8,
                              rect.height()),
              value, size=_BODY_SIZE, color=color, bold=bold)


def _column_widths(content_w: float) -> List[float]:
    return ([content_w * share for share in _FIXED_SHARE]
            + [content_w * _LEVEL_SHARE] * len(RATING_LEVELS))


def group_label(cycle: str, gender: str) -> str:
    """"ابتدائي / ذكور", or غير محدد when neither is named."""
    parts = [_CYCLE_LABELS.get(cycle, ""), _GENDER_LABELS.get(gender, "")]
    named = " / ".join(part for part in parts if part)
    return named or _GROUP_ANY


def parse_group_label(label: str) -> Optional[Tuple[str, str]]:
    """The reverse. None when the text is not a group this app wrote —
    filing opinions under a guessed group is exactly what must not happen."""
    text = (label or "").strip()
    if not text or text == _GROUP_ANY:
        return "", ""
    cycles = {value: key for key, value in _CYCLE_LABELS.items()}
    genders = {value: key for key, value in _GENDER_LABELS.items()}
    cycle = gender = ""
    for part in (piece.strip() for piece in text.split("/")):
        if part in cycles:
            cycle = cycles[part]
        elif part in genders:
            gender = genders[part]
        elif part:
            return None
    return cycle, gender


def groups_to_collect(cycle: str, gender: str) -> List[Tuple[str, str]]:
    """Which groups one export covers.

    With a group chosen on screen, just that one. With none chosen, EVERY
    group — the point of the paper route is one print run, not six.
    """
    if cycle or gender:
        return [(cycle, gender)]
    return [(one_cycle, one_gender)
            for one_cycle in _CYCLE_LABELS for one_gender in _GENDER_LABELS]


def write_tally_sheet_pdf(path: Path, settings: SchoolSettings,
                          dishes: Sequence[str], week_start: str,
                          groups: Optional[Sequence[Tuple[str, str]]] = None
                          ) -> None:
    """A sheet someone can carry into the refectory and mark up.

    One row per DISH in the week's menu — a dish served twice is asked about
    once — with five wide boxes to tally into. One PAGE SET per group, so the
    person collecting ticks the page of the class in front of them.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(_TALLY_TITLE)

    painter = QPainter(writer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        page_w = float(writer.width())
        page_h = float(writer.height())
        content_w = page_w - (_MARGIN * 2)
        widths = _column_widths(content_w)
        headers = [_HDR_DISH] + [_RATING_LABELS[level] for level in RATING_LEVELS]

        def column_left(index: int) -> float:
            # RTL: the first column sits on the RIGHT.
            return _MARGIN + sum(widths[index + 1:])

        targets = list(groups) if groups else [("", "")]
        started = False
        for cycle, gender in targets:
            index = 0
            first_page = True
            while index < len(dishes) or first_page:
                if started:
                    writer.newPage()
                started = True
                y = draw_official_pdf_header(
                    painter, page_width=page_w, margin=_MARGIN, top=14.0,
                    settings=settings, title=_TALLY_TITLE)
                y += _text(painter, QRectF(_MARGIN, y, content_w, 13.0),
                           f"{_TALLY_SUBTITLE}    ·    {week_label(week_start)}",
                           size=_META_SIZE, color=COLOR_TEXT_SECONDARY) + 4.0
                # WHOSE page this is, stated on the page itself — a stack of
                # identical sheets is impossible to file afterwards.
                y += _text(painter, QRectF(_MARGIN, y, content_w, 15.0),
                           f"{_LBL_GROUP_KEY}: {group_label(cycle, gender)}",
                           size=_BODY_SIZE + 1, color=COLOR_TEXT_PRIMARY,
                           bold=True) + 8.0

                for position, header in enumerate(headers):
                    _cell(painter, QRectF(column_left(position), y,
                                          widths[position], _HEADER_ROW_HEIGHT),
                          header, bold=True, fill="#EFF4F0")
                y += _HEADER_ROW_HEIGHT

                while (index < len(dishes)
                       and y + _ROW_HEIGHT <= page_h - _MARGIN - 60.0):
                    _cell(painter, QRectF(column_left(0), y, widths[0],
                                          _ROW_HEIGHT), dishes[index])
                    # The five tally boxes are left EMPTY on purpose — this
                    # sheet is the thing that gets written on.
                    for offset in range(len(RATING_LEVELS)):
                        position = 1 + offset
                        _cell(painter, QRectF(column_left(position), y,
                                              widths[position], _ROW_HEIGHT))
                    y += _ROW_HEIGHT
                    index += 1

                first_page = False
                if index >= len(dishes):
                    break

            draw_official_pdf_footer(
                painter, page_width=page_w, margin=_MARGIN,
                top=page_h - _MARGIN - 46.0, settings=settings,
                roles=["الحارس(ة) العام(ة) للداخلية"])
    finally:
        painter.end()


# ── The Excel round-trip ────────────────────────────────────────────────────

def _sheet_title(cycle: str, gender: str) -> str:
    """Excel forbids / in a sheet name, so the group reads with a dash here."""
    if not cycle and not gender:
        return _SHEET_NAME
    return group_label(cycle, gender).replace(" / ", "-")


def write_feedback_workbook(path: Path, dishes: Sequence[str],
                            week_start: str,
                            groups: Optional[Sequence[Tuple[str, str]]] = None
                            ) -> None:
    """The week's dishes as a workbook with EMPTY count columns to fill in.

    One SHEET per group, so a single file collects the whole week.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    targets = list(groups) if groups else [("", "")]
    for cycle, gender in targets:
        _write_group_sheet(workbook, dishes, week_start, cycle, gender,
                           Alignment=Alignment, Font=Font,
                           PatternFill=PatternFill,
                           get_column_letter=get_column_letter)

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _write_group_sheet(workbook, dishes: Sequence[str], week_start: str,
                       cycle: str, gender: str, *, Alignment, Font,
                       PatternFill, get_column_letter) -> None:
    sheet = workbook.create_sheet(_sheet_title(cycle, gender))
    sheet.sheet_view.rightToLeft = True

    sheet["A1"] = f"{_TALLY_TITLE} — {week_label(week_start)}"
    sheet["A1"].font = Font(bold=True, size=13)
    sheet.merge_cells(start_row=1, start_column=1,
                      end_row=1, end_column=len(_EXCEL_HDR))
    sheet["A1"].alignment = Alignment(horizontal="center")

    # Row 2 carries the week in ISO and the group, so the import knows where
    # the numbers belong without the user having to say. Do not move these.
    sheet["A2"] = _LBL_WEEK_KEY
    sheet["B2"] = week_start_of(week_start)
    sheet["C2"] = _LBL_GROUP_KEY
    sheet["D2"] = group_label(cycle, gender)
    for key in ("A2", "C2"):
        sheet[key].font = Font(bold=True)

    header_fill = PatternFill("solid", fgColor="EFF4F0")
    for column, title in enumerate(_EXCEL_HDR, start=1):
        cell = sheet.cell(row=3, column=column, value=title)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for offset, dish in enumerate(dishes):
        row = 4 + offset
        sheet.cell(row=row, column=1, value=dish)
        # Counts deliberately left blank — an empty cell means "not collected",
        # which the import treats as nothing rather than as zero pupils.
        for level_offset in range(len(RATING_LEVELS)):
            sheet.cell(row=row, column=2 + level_offset).alignment = Alignment(
                horizontal="center")

    widths = [38] + [12] * len(RATING_LEVELS)
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width


def _read_count(value) -> Optional[int]:
    """A count cell: blank means not collected, a bad value means refuse."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def import_feedback_workbook(path: Path) -> Tuple[int, int, List[str], str]:
    """Read a filled week workbook back in — every group sheet it holds.

    Returns (saved, skipped, problems, week_start). A dish whose counts are
    all empty is SKIPPED, not stored as a dish nobody rated; a row that cannot
    be read is reported rather than guessed at, and a sheet whose group name
    was edited into something unrecognised is refused outright rather than
    filed under a group that may not have said it.
    """
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True)
    saved = 0
    skipped = 0
    problems: List[str] = []
    week_start = ""
    for sheet in workbook.worksheets:
        sheet_week = _sheet_week(sheet)
        if not sheet_week:
            continue
        week_start = week_start or sheet_week
        group = parse_group_label(str(sheet["D2"].value or ""))
        if group is None:
            problems.append(_MSG_BAD_GROUP.format(
                sheet=sheet.title, group=sheet["D2"].value))
            continue
        sheet_saved, sheet_skipped, sheet_problems = _import_group_sheet(
            sheet, sheet_week, group)
        saved += sheet_saved
        skipped += sheet_skipped
        problems.extend(sheet_problems)

    if not week_start:
        return 0, 0, [_MSG_NO_WEEK], ""
    return saved, skipped, problems, week_start


def _sheet_week(sheet) -> str:
    raw_week = sheet["B2"].value
    if isinstance(raw_week, (datetime.datetime, datetime.date)):
        raw_week = (raw_week.date() if isinstance(raw_week, datetime.datetime)
                    else raw_week).isoformat()
    return week_start_of(str(raw_week or ""))


def _import_group_sheet(sheet, week_start: str, group: Tuple[str, str]
                        ) -> Tuple[int, int, List[str]]:
    cycle, gender = group
    saved = 0
    skipped = 0
    problems: List[str] = []
    existing_rows = get_week_feedback(week_start)
    for row_number, values in enumerate(
        sheet.iter_rows(min_row=4, values_only=True), start=4
    ):
        if values is None or all(v is None for v in values):
            continue
        dish = normalize_dish(str(values[0])) if values[0] else ""

        # Counts BEFORE anything else: a line nobody filled in is not a
        # mistake, and reporting it would bury the real problems in noise.
        counts: Dict[int, int] = {}
        bad = False
        for offset, level in enumerate(RATING_LEVELS):
            raw = values[1 + offset] if len(values) > 1 + offset else None
            number = _read_count(raw)
            if number is None:
                problems.append(f"{sheet.title} — سطر {row_number}: عدد غير صالح")
                bad = True
                break
            counts[level] = number
        if bad:
            continue
        if not sum(counts.values()):
            skipped += 1
            continue
        if not dish:
            problems.append(
                f"{sheet.title} — سطر {row_number}: اكتب اسم الطبق في العمود الأول")
            continue

        record = next(
            (r for r in existing_rows
             if r.dish == dish and r.cycle == cycle and r.gender == gender),
            None) or WeekFeedback(week_start=week_start, dish=dish,
                                  cycle=cycle, gender=gender)
        for level, field in COUNT_FIELDS.items():
            setattr(record, field, counts[level])
        save_week_feedback(record)
        saved += 1
    return saved, skipped, problems
