"""
src/ui/main_window.py
Main application window — sidebar navigation + stacked screens.
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from config.settings import (
    APP_ICON_PATH, APP_NAME, APP_VERSION,
    COLOR_ACCENT, COLOR_SIDEBAR_ACTIVE, COLOR_SIDEBAR_BG,
    COLOR_SIDEBAR_BORDER, COLOR_SIDEBAR_HOVER, COLOR_SURFACE,
    COLOR_TEXT_SIDEBAR, COLOR_TEXT_SIDEBAR_ACTIVE,
    FONT_CAPTION,
    WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH,
)
from ui.daily_absence_screen import DailyAbsenceScreen
from ui.daily_contact_screen import DailyContactScreen
from ui.daily_reception_screen import DailyReceptionScreen
from ui.daily_report_screen import DailyReportScreen
from ui.dashboard_screen import DashboardScreen
from ui.infraction_record_screen import InfractionRecordScreen
from ui.feedback_screen import FeedbackScreen
from ui.nutrition_screen import NutritionScreen
from ui.staff_screen import StaffScreen
from ui.meal_program_screen import MealProgramScreen
from ui.monthly_reception_screen import MonthlyReceptionScreen
from ui.monthly_report_screen import MonthlyReportScreen
from ui.order_letter_screen import OrderLetterScreen
from ui.quarterly_reception_screen import QuarterlyReceptionScreen
from ui.students_screen import StudentsScreen
from ui.settings_screen import SettingsScreen
from ui.widgets.icon_button import IconButton
from ui.work_pipeline_screen import WorkPipelineScreen

# Nav items: (icon emoji, Arabic label, screen_index)
# Indices must match the order screens are added to _build_stack()
# The sidebar as the user reads it: a few standalone pages, and sections that
# slide open. Grouped 2026-08-29 — 17 flat rows had become more list than menu.
# A section's third element is its CHILDREN; a page's is its stack index.
#
# Stack indices are deliberately NOT in reading order here (الملخص الشهري is 11
# but sits between 9 and 10 on screen). The stack is built once in
# _build_stack and its order is history; this list is the ORDER THE USER SEES.
# Everything downstream keys off the index carried on each row, never off the
# row's position — that is what let the two drift apart in the past.
_NAV_TREE: list[tuple[str, str, object]] = [
    ("🏠", "الصفحة الرئيسية",                0),
    ("📈", "الإحصائيات",              1),
    ("📋", "الوثائق اليومية", [
        ("📋", "ورقة الاتصال اليومية",  4),
        ("📉", "ورقة الغياب اليومي",    5),
        ("✉️", "رسالة الطلبية",         6),
        ("📄", "التقرير اليومي",        7),
        ("🧾", "محضر التسلم اليومي",    8),
    ]),
    ("📚", "الوثائق الشهرية والفصلية", [
        ("📚", "محضر التسلم الشهري",    9),
        ("📊", "الملخص الشهري",         11),
        ("📜", "الوثائق الفصلية",       10),
    ]),
    ("👥", "اللوائح والبرامج", [
        ("👥", "لائحة التلاميذ",        2),
        ("🍽️", "البرنامج الغذائي",      3),
        ("👨‍🍳", "طاقم المطبخ",           13),
    ]),
    ("⚖️", "المتابعة والجودة", [
        ("⚖️", "محضر المخالفة",         12),
        ("🥗", "التحليل الغذائي",       14),
        ("💬", "تقييم التلاميذ",        15),
    ]),
    ("⚙️", "الإعدادات",               16),
]


def _nav_pages(tree: list[tuple[str, str, object]]
               ) -> list[tuple[str, str, int]]:
    """Every page in the tree, sections flattened — one entry per screen."""
    pages: list[tuple[str, str, int]] = []
    for icon, label, target in tree:
        if isinstance(target, list):
            pages.extend(target)
        else:
            pages.append((icon, label, target))
    return pages


# Kept as the flat view of the tree: the stack is checked against it, and it is
# the list to read when asking "which screens exist".
_NAV_ITEMS: list[tuple[str, str, int]] = _nav_pages(_NAV_TREE)

_SIDEBAR_WIDTH = 235
# A section's pages are a little smaller and set in from the reading edge, so
# the eye reads them as belonging to the header above them.
_NAV_CHILD_INDENT = 12
_NAV_CHILD_SPACING = 4
_NAV_CHILD_HEIGHT = 36
_ARROW_OPEN = "▾"
_ARROW_CLOSED = "◂"
_APP_BG = COLOR_SURFACE
_NAV_PANEL_BG = COLOR_SIDEBAR_BG
_NAV_PANEL_BORDER = COLOR_SIDEBAR_BORDER
_NAV_ACTIVE = COLOR_SIDEBAR_ACTIVE
_NAV_TEXT = COLOR_TEXT_SIDEBAR
_MENU_HIDE = "إخفاء الصفحات"
_MENU_SHOW = "إظهار الصفحات"
_MENU_ICON = "☰"
_MEAL_PROGRAM_INDEX = 3
# The sidebar button that gets a live student count appended. Looked up by
# LABEL, not position: it used to be a hardcoded index that pointed one button
# too high, so the live count overwrote الإحصائيات and the dashboard appeared
# to rename itself to "لائحة التلاميذ".
_STUDENTS_NAV_LABEL = "لائحة التلاميذ"
_LOGGER = logging.getLogger(__name__)


class _NavButton(IconButton):
    """Sidebar navigation button with active/inactive styling. Icon+label
    are laid out manually (see IconButton) so they reliably hug the right
    edge instead of floating near the left on this wide button."""

    def __init__(self, icon_emoji: str, label: str, *,
                 page_index: int = -1, min_height: int = 44,
                 font_size: int = 13) -> None:
        super().__init__(
            label, icon=icon_emoji, bg="transparent", text_color=_NAV_TEXT,
            border_radius=14, padding_h=14, font_size=font_size, bold=True,
            min_height=min_height, icon_size=18, hover_bg=COLOR_SIDEBAR_HOVER,
        )
        # The screen this button opens, carried ON the button. Highlighting
        # used to compare a button's POSITION in the list against the stack
        # index, which only worked while the two happened to match — grouping
        # the menu breaks that, and it would have broken silently.
        self.page_index = page_index
        self.page_label = label
        self.setCheckable(True)
        self._active = False
        self.set_active(False)

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active
        self.set_style(
            bg=_NAV_ACTIVE if active else "transparent",
            text_color=COLOR_TEXT_SIDEBAR_ACTIVE if active else _NAV_TEXT,
            border=_NAV_ACTIVE if active else None,
            hover_bg="transparent" if active else COLOR_SIDEBAR_HOVER,
        )



class _NavSection(QWidget):
    """A sidebar section whose pages slide open underneath its header.

    The header is a _NavButton like any other so the section reads as part of
    the same menu; it carries a chevron pointing DOWN when open and LEFT when
    shut (left is "forward" in this right-to-left layout).

    When the section is shut but holds the page you are on, the HEADER takes
    the active highlight — otherwise closing a section would hide every trace
    of where you are.
    """

    def __init__(self, icon_emoji: str, label: str) -> None:
        super().__init__()
        self.setStyleSheet("background: transparent;")
        self._label = label
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_NAV_CHILD_SPACING)

        self.header = _NavButton(icon_emoji, label)
        layout.addWidget(self.header)

        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(self._body)
        # Indented on the RIGHT — that is the reading edge here, so the indent
        # is where the eye actually looks for it.
        self._body_layout.setContentsMargins(0, 0, _NAV_CHILD_INDENT, 0)
        self._body_layout.setSpacing(_NAV_CHILD_SPACING)
        layout.addWidget(self._body)
        self._body.setVisible(False)
        self._sync_header()

    def add_page(self, button: "_NavButton") -> None:
        self._body_layout.addWidget(button)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._body.setVisible(expanded)
        self._sync_header()

    def set_holds_current(self, holds_current: bool) -> None:
        """Highlight the header only while the section is shut: open, the
        child button already shows where you are."""
        self.header.set_active(holds_current and not self._expanded)

    def _sync_header(self) -> None:
        arrow = _ARROW_OPEN if self._expanded else _ARROW_CLOSED
        # RTL puts the appended chevron on the LEFT edge, opposite the label.
        self.header.setText(f"{self._label}   {arrow}")


class MainWindow(QMainWindow):
    """Main window: RTL sidebar (right side) + stacked content area."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._nav_buttons: list[_NavButton] = []
        self._nav_sections: list[_NavSection] = []
        self._stack: QStackedWidget | None = None
        self._sidebar_visible = True
        self._build_ui()
        self._navigate(0)   # start on الصفحة الرئيسية (work pipeline)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self._root = root
        self.setCentralWidget(root)
        root.setStyleSheet(f"background-color: {_APP_BG};")
        layout = QHBoxLayout(root)
        self._root_layout = layout
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)
        # In RTL mode: first widget → RIGHT, second → LEFT
        self._sidebar = self._build_sidebar()
        layout.addWidget(self._sidebar)
        self._content_area = self._build_content_area()
        self._content_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._content_area, 1)

    def _build_content_area(self) -> QWidget:
        content = QWidget()
        content.setStyleSheet(f"background-color: {_APP_BG}; border: none;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        self._menu_toggle = IconButton(
            _MENU_HIDE, icon=_MENU_ICON, bg=_NAV_ACTIVE, text_color="white",
            border_radius=12, padding_h=14, font_size=13, bold=True, min_height=34,
        )
        self._menu_toggle.clicked.connect(self._toggle_sidebar)
        top_bar.addWidget(self._menu_toggle)
        top_bar.addStretch()

        layout.addLayout(top_bar)
        layout.addWidget(self._build_stack(), 1)
        return content

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setFixedWidth(_SIDEBAR_WIDTH)
        sidebar.setStyleSheet(
            f"background-color: {_NAV_PANEL_BG};"
            f"border: 1px solid {_NAV_PANEL_BORDER};"
            "border-radius: 24px;"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)

        # Product identity — the text becomes the configured school name after
        # setup, while the application mark remains stable.
        identity = QHBoxLayout()
        identity.setContentsMargins(4, 2, 4, 10)
        identity.setSpacing(9)

        icon_label = QLabel()
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if APP_ICON_PATH.exists():
            icon_label.setPixmap(QPixmap(str(APP_ICON_PATH)).scaled(
                38, 38,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

        self._title_label = QLabel(APP_NAME)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._title_label.setWordWrap(True)
        f = QFont(); f.setPointSize(13); f.setBold(True)
        self._title_label.setFont(f)
        self._title_label.setStyleSheet(
            f"color: {COLOR_TEXT_SIDEBAR_ACTIVE};"
        )
        identity.addWidget(self._title_label, 1)
        identity.addWidget(icon_label)
        layout.addLayout(identity)

        # The menu scrolls. Without this the QVBoxLayout has to fit an open
        # section into whatever height is left and starts violating the
        # buttons' own minimum heights — at the 700px minimum window the five
        # الوثائق اليومية pages rendered stacked ON TOP of each other.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A slim, quiet scrollbar: it only appears when a long section is
        # open, and the app-wide one is too heavy against the sidebar.
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 6px;"
            " margin: 0; }"
            f"QScrollBar::handle:vertical {{ background: {COLOR_SIDEBAR_HOVER};"
            " border-radius: 3px; min-height: 30px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            " { height: 0; background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        nav_holder = QWidget()
        nav_holder.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_holder)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)
        scroll.setWidget(nav_holder)
        layout.addWidget(scroll, 1)

        # Nav buttons, built from the tree: a page becomes a button, a section
        # becomes a header with its own pages underneath.
        for icon_emoji, label, target in _NAV_TREE:
            if not isinstance(target, list):
                nav_layout.addWidget(
                    self._page_button(icon_emoji, label, target))
                continue
            section = _NavSection(icon_emoji, label)
            for child_icon, child_label, child_index in target:
                section.add_page(self._page_button(
                    child_icon, child_label, child_index,
                    min_height=_NAV_CHILD_HEIGHT, font_size=12))
            section.header.clicked.connect(
                lambda _c, sec=section: self._toggle_section(sec))
            self._nav_sections.append(section)
            nav_layout.addWidget(section)

        nav_layout.addStretch()

        # Version
        ver = QLabel(f"v{APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color: {_NAV_TEXT}; font-size: {FONT_CAPTION}px; padding: 10px;")
        layout.addWidget(ver)
        return sidebar

    def _page_button(self, icon_emoji: str, label: str, index: int,
                     *, min_height: int = 44,
                     font_size: int = 13) -> "_NavButton":
        button = _NavButton(icon_emoji, label, page_index=index,
                            min_height=min_height, font_size=font_size)
        button.clicked.connect(lambda _c, i=index: self._navigate(i))
        self._nav_buttons.append(button)
        return button

    def _toggle_section(self, section: "_NavSection") -> None:
        """Open one section at a time. With every section open the menu is as
        long as the flat list it replaced, and taller than the window at its
        minimum size."""
        opening = not section.is_expanded()
        for other in self._nav_sections:
            other.set_expanded(other is section and opening)
        self._sync_sections()

    def _sync_sections(self) -> None:
        """Open the section holding the current page, and mark shut sections
        that hold it. Navigation also arrives from الصفحة الرئيسية and the dashboard
        quick actions, so this cannot live in the click handler alone."""
        current = self._stack.currentIndex() if self._stack else -1
        for section, (_icon, _label, children) in zip(
                self._nav_sections, self._sections_in_tree()):
            section.set_holds_current(
                any(index == current for _i, _l, index in children))

    @staticmethod
    def _sections_in_tree() -> list[tuple[str, str, list]]:
        return [row for row in _NAV_TREE if isinstance(row[2], list)]

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {_APP_BG}; border: none;")

        # Index 0 — الصفحة الرئيسية (Work Day pipeline) — the app's landing screen
        self._pipeline = WorkPipelineScreen(navigate_to=self._navigate)
        self._stack.addWidget(self._pipeline)                           # 0

        # Index 1 — Dashboard / statistics (passes navigate callback so quick-action buttons work)
        self._dashboard = DashboardScreen(navigate_to=self._navigate)
        self._stack.addWidget(self._dashboard)                          # 1

        # Index 2 — Students
        self._stack.addWidget(StudentsScreen())                         # 2

        # Indices 3-12 — mix of built and placeholder screens
        self._stack.addWidget(MealProgramScreen())                          # 3 — built
        self._stack.addWidget(DailyContactScreen())                         # 4 — built
        self._stack.addWidget(DailyAbsenceScreen())                          # 5 — built
        self._stack.addWidget(OrderLetterScreen())                            # 6 — built
        self._stack.addWidget(DailyReportScreen())                           # 7 — built
        self._stack.addWidget(DailyReceptionScreen())                         # 8 — built
        self._stack.addWidget(MonthlyReceptionScreen())                       # 9 — built
        self._stack.addWidget(QuarterlyReceptionScreen())                     # 10 — built
        self._stack.addWidget(MonthlyReportScreen())                          # 11 — built
        self._stack.addWidget(InfractionRecordScreen())                       # 12 — built
        self._stack.addWidget(StaffScreen())                                  # 13 — built
        self._stack.addWidget(NutritionScreen())                              # 14 — built
        self._stack.addWidget(FeedbackScreen())                               # 15 — built

        # Index 16 — Settings
        self._stack.addWidget(SettingsScreen())                         # 16

        return self._stack

    # ── Navigation ─────────────────────────────────────────────────────────

    def _navigate(self, index: int) -> None:
        """Switch visible screen and highlight the matching sidebar button."""
        self._stack.setCurrentIndex(index)
        self._set_sidebar_visible(index != _MEAL_PROGRAM_INDEX)
        for btn in self._nav_buttons:
            btn.set_active(btn.page_index == index)
        self._open_section_holding(index)
            
        current = self._stack.widget(index)
        if hasattr(current, "refresh"):
            current.refresh()
            
        self._refresh_sidebar()

    def _open_section_holding(self, index: int) -> None:
        """Slide open the section that owns the page being shown, so arriving
        from الصفحة الرئيسية or a dashboard quick action lands somewhere visible."""
        for section, (_icon, _label, children) in zip(
                self._nav_sections, self._sections_in_tree()):
            if any(child_index == index for _i, _l, child_index in children):
                for other in self._nav_sections:
                    other.set_expanded(other is section)
                break
        self._sync_sections()

    def _refresh_sidebar(self) -> None:
        """Update dynamic elements in the sidebar."""
        try:
            from data.database import get_student_counts
            counts = get_student_counts()
            total = counts.get("total", 0)
            # Found by the button's OWN label, never by a position: writing a
            # live label to a hardcoded index is what once made الإحصائيات
            # rename itself to "لائحة التلاميذ (N)".
            for button in self._nav_buttons:
                if button.page_label == _STUDENTS_NAV_LABEL:
                    button.setText(f"{button.page_label} ({total})")
                    break
        except Exception:
            _LOGGER.exception("Failed to refresh sidebar student count")

        try:
            from data.settings_repo import get_school_settings
            settings = get_school_settings()
            school_name = settings.school_name.strip() if settings else ""
            self._title_label.setText(school_name if school_name else APP_NAME)
        except Exception:
            _LOGGER.exception("Failed to refresh sidebar school name")

    def _toggle_sidebar(self) -> None:
        """Hide the navigation when the current page needs more working space."""
        self._set_sidebar_visible(not self._sidebar_visible)

    def _set_sidebar_visible(self, visible: bool) -> None:
        """Apply sidebar visibility and keep the toggle label in sync."""
        self._sidebar_visible = visible
        self._root.setProperty("sidebarHidden", not self._sidebar_visible)
        if self._sidebar_visible:
            self._sidebar.setVisible(True)
            self._sidebar.setFixedWidth(_SIDEBAR_WIDTH)
            self._sidebar.setMinimumWidth(_SIDEBAR_WIDTH)
            self._sidebar.setMaximumWidth(_SIDEBAR_WIDTH)
        else:
            self._sidebar.setMinimumWidth(0)
            self._sidebar.setMaximumWidth(0)
            self._sidebar.setFixedWidth(0)
            self._sidebar.setVisible(False)
        self._content_area.setMinimumWidth(0)
        self._root_layout.invalidate()
        self._menu_toggle.setText(_MENU_HIDE if self._sidebar_visible else _MENU_SHOW)
