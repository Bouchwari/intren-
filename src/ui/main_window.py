"""
src/ui/main_window.py
Main application window — sidebar navigation + stacked screens.
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from config.settings import (
    APP_NAME, APP_VERSION,
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
_NAV_ITEMS: list[tuple[str, str, int]] = [
    ("🏠", "يوم العمل",              0),
    ("📈", "الإحصائيات",            1),
    ("👥", "لائحة التلاميذ",        2),
    ("🍽️", "البرنامج الغذائي",      3),
    ("📋", "ورقة الاتصال اليومية",  4),
    ("📉", "ورقة الغياب اليومي",    5),
    ("✉️", "رسالة الطلبية",         6),
    ("📄", "التقرير اليومي",        7),
    ("🧾", "محضر التسلم اليومي",    8),
    ("📚", "محضر التسلم الشهري",    9),
    ("📜", "الوثائق الفصلية",       10),
    ("📊", "الملخص الشهري",         11),
    ("⚖️", "محضر المخالفة",         12),
    ("⚙️", "الإعدادات",            13),
]

_SIDEBAR_WIDTH = 235
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

    def __init__(self, icon_emoji: str, label: str) -> None:
        super().__init__(
            label, icon=icon_emoji, bg="transparent", text_color=_NAV_TEXT,
            border_radius=14, padding_h=14, font_size=13, bold=True,
            min_height=44, icon_size=18, hover_bg=COLOR_SIDEBAR_HOVER,
        )
        self.setCheckable(True)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.set_style(
            bg=_NAV_ACTIVE if active else "transparent",
            text_color=COLOR_TEXT_SIDEBAR_ACTIVE if active else _NAV_TEXT,
            border=_NAV_ACTIVE if active else None,
            hover_bg="transparent" if active else COLOR_SIDEBAR_HOVER,
        )



class MainWindow(QMainWindow):
    """Main window: RTL sidebar (right side) + stacked content area."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._nav_buttons: list[_NavButton] = []
        self._sidebar_visible = True
        self._build_ui()
        self._navigate(0)   # start on يوم العمل (work pipeline)

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

        # Title — shows the school name once configured, falls back to the
        # generic app name before setup.
        self._title_label = QLabel(f"M  {APP_NAME}")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._title_label.setWordWrap(True)
        f = QFont(); f.setPointSize(13); f.setBold(True)
        self._title_label.setFont(f)
        self._title_label.setStyleSheet(
            f"color: {COLOR_TEXT_SIDEBAR_ACTIVE}; padding: 8px 6px 18px 6px;"
        )
        layout.addWidget(self._title_label)

        # Nav buttons
        for icon_emoji, label, index in _NAV_ITEMS:
            btn = _NavButton(icon_emoji, label)
            btn.clicked.connect(lambda _c, i=index: self._navigate(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Version
        ver = QLabel(f"v{APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color: {_NAV_TEXT}; font-size: {FONT_CAPTION}px; padding: 10px;")
        layout.addWidget(ver)
        return sidebar

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {_APP_BG}; border: none;")

        # Index 0 — يوم العمل (Work Day pipeline) — the app's landing screen
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

        # Index 13 — Settings
        self._stack.addWidget(SettingsScreen())                         # 13

        return self._stack

    # ── Navigation ─────────────────────────────────────────────────────────

    def _navigate(self, index: int) -> None:
        """Switch visible screen and highlight the matching sidebar button."""
        self._stack.setCurrentIndex(index)
        self._set_sidebar_visible(index != _MEAL_PROGRAM_INDEX)
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index)
            
        current = self._stack.widget(index)
        if hasattr(current, "refresh"):
            current.refresh()
            
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        """Update dynamic elements in the sidebar."""
        try:
            from data.database import get_student_counts
            counts = get_student_counts()
            total = counts.get("total", 0)
            for position, (_icon, label, _index) in enumerate(_NAV_ITEMS):
                if label == _STUDENTS_NAV_LABEL:
                    self._nav_buttons[position].setText(f"{label} ({total})")
                    break
        except Exception:
            _LOGGER.exception("Failed to refresh sidebar student count")

        try:
            from data.settings_repo import get_school_settings
            settings = get_school_settings()
            school_name = settings.school_name.strip() if settings else ""
            self._title_label.setText(f"M  {school_name if school_name else APP_NAME}")
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
