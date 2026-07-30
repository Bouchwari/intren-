"""
src/ui/main_window.py
Main application window — sidebar navigation + stacked screens.
"""
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from config.settings import (
    APP_NAME, APP_VERSION,
    COLOR_ACCENT, COLOR_SIDEBAR_ACTIVE, COLOR_SIDEBAR_BG,
    COLOR_SIDEBAR_BORDER, COLOR_SIDEBAR_HOVER, COLOR_SURFACE,
    COLOR_TEXT_SIDEBAR, COLOR_TEXT_SIDEBAR_ACTIVE,
    WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH,
)
from ui.daily_absence_screen import DailyAbsenceScreen
from ui.daily_contact_screen import DailyContactScreen
from ui.daily_report_screen import DailyReportScreen
from ui.dashboard_screen import DashboardScreen
from ui.expense_statement_screen import ExpenseStatementScreen
from ui.incident_log_screen import IncidentLogScreen
from ui.meal_program_screen import MealProgramScreen
from ui.monthly_report_screen import MonthlyReportScreen
from ui.order_letter_screen import OrderLetterScreen
from ui.students_screen import StudentsScreen
from ui.settings_screen import SettingsScreen

# Nav items: (Arabic label, screen_index)
# Indices must match the order screens are added to _build_stack()
_NAV_ITEMS: list[tuple[str, int]] = [
    ("🏠  الرئيسية",              0),
    ("👥  لائحة التلاميذ",        1),
    ("🍽️  البرنامج الغذائي",      2),
    ("📋  ورقة الاتصال اليومية",  3),
    ("📉  ورقة الغياب اليومي",    4),
    ("📄  التقرير اليومي",        5),
    ("📊  المحضر الشهري",         6),
    ("✉️  رسالة الطلبية",         7),
    ("💰  بيان المصاريف",         8),
    ("📕  دفتر المخالفات",        9),
    ("⚙️  الإعدادات",            10),
]

_SIDEBAR_WIDTH = 235
_APP_BG = "#f5f5f0"
_NAV_PANEL_BG = "#E4E4D7"
_NAV_PANEL_BORDER = "#d6d6c8"
_NAV_ACTIVE = "#5A5A40"
_NAV_TEXT = "#475569"
_MENU_HIDE = "☰ إخفاء الصفحات"
_MENU_SHOW = "☰ إظهار الصفحات"
_MEAL_PROGRAM_INDEX = 2
_LOGGER = logging.getLogger(__name__)


class _NavButton(QPushButton):
    """Sidebar navigation button with active/inactive styling."""

    _STYLE = """
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {border_color};
            border-radius: 14px;
            padding: 11px 14px;
            font-size: 13px;
            font-weight: 700;
            text-align: right;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 255, 255, 0.65);
            color: #0f172a;
        }}
    """

    def __init__(self, label: str) -> None:
        super().__init__(label)
        self.setCheckable(True)
        self.setMinimumHeight(44)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.setStyleSheet(self._STYLE.format(
            bg=_NAV_ACTIVE if active else "transparent",
            fg=COLOR_TEXT_SIDEBAR_ACTIVE if active else _NAV_TEXT,
            border_color=_NAV_ACTIVE if active else "transparent",
            COLOR_SIDEBAR_HOVER=COLOR_SIDEBAR_HOVER,
            COLOR_TEXT_SIDEBAR_ACTIVE=COLOR_TEXT_SIDEBAR_ACTIVE,
        ))



class MainWindow(QMainWindow):
    """Main window: RTL sidebar (right side) + stacked content area."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._nav_buttons: list[_NavButton] = []
        self._sidebar_visible = True
        self._build_ui()
        self._navigate(0)   # start on dashboard

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
        self._menu_toggle = QPushButton(_MENU_HIDE)
        self._menu_toggle.setMinimumHeight(34)
        self._menu_toggle.setStyleSheet(
            f"background-color: {_NAV_ACTIVE}; color: white;"
            "border: none; border-radius: 12px; padding: 0 14px;"
            "font-size: 13px; font-weight: 900;"
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

        # Title
        title = QLabel(f"M  {APP_NAME}")
        title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(
            f"color: {_NAV_ACTIVE}; padding: 8px 6px 18px 6px;"
        )
        layout.addWidget(title)

        # Nav buttons
        for label, index in _NAV_ITEMS:
            btn = _NavButton(label)
            btn.clicked.connect(lambda _c, i=index: self._navigate(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Version
        ver = QLabel(f"v{APP_VERSION}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color: {_NAV_TEXT}; font-size: 11px; padding: 10px;")
        layout.addWidget(ver)
        return sidebar

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {_APP_BG}; border: none;")

        # Index 0 — Dashboard (passes navigate callback so quick-action buttons work)
        self._dashboard = DashboardScreen(navigate_to=self._navigate)
        self._stack.addWidget(self._dashboard)                          # 0

        # Index 1 — Students
        self._stack.addWidget(StudentsScreen())                         # 1

        # Indices 2-9 — mix of built and placeholder screens
        self._stack.addWidget(MealProgramScreen())                          # 2 — built
        self._stack.addWidget(DailyContactScreen())                         # 3 — built
        self._stack.addWidget(DailyAbsenceScreen())                          # 4 — built
        self._stack.addWidget(DailyReportScreen())                           # 5 — built
        self._stack.addWidget(MonthlyReportScreen())                          # 6 — built
        self._stack.addWidget(OrderLetterScreen())                            # 7 — built
        self._stack.addWidget(ExpenseStatementScreen())                       # 8 — built
        self._stack.addWidget(IncidentLogScreen())                            # 9 — built

        # Index 10 — Settings
        self._stack.addWidget(SettingsScreen())                         # 10

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
            self._nav_buttons[1].setText(f"👥  لائحة التلاميذ ({total})")
        except Exception:
            _LOGGER.exception("Failed to refresh sidebar student count")

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
