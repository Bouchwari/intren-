"""
config/settings.py
All paths and constants live here. Code never hardcodes these values.
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

# Root of the project (two levels up from this file)
import sys

if getattr(sys, 'frozen', False):
    # PyInstaller bundle: store DB next to the executable
    BASE_DIR: Path = Path(sys.executable).resolve().parent
else:
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

# Where the SQLite database lives (next to the exe when packaged)
DB_PATH: Path = BASE_DIR / "matama.db"

# School logo (copied here when the user uploads one via Settings)
LOGO_PATH: Path = BASE_DIR / "matama_logo.png"

# ── App identity ─────────────────────────────────────────────────────────────

APP_NAME: str = "نظام المطعمة"
APP_VERSION: str = "1.0.0"

# ── Window defaults ──────────────────────────────────────────────────────────

WINDOW_MIN_WIDTH: int = 1100
WINDOW_MIN_HEIGHT: int = 700

# ── Meal types (used as DB keys — never change these values) ─────────────────

MEAL_FTOUR: str = "ftour"       # فطور
MEAL_GHADA: str = "ghada"       # غداء
MEAL_ASHA: str = "asha"         # عشاء

MEAL_LABELS: dict[str, str] = {
    MEAL_FTOUR: "فطور",
    MEAL_GHADA: "غداء",
    MEAL_ASHA:  "عشاء",
}

# ── Beneficiary types ────────────────────────────────────────────────────────

GRANT_FULL: str = "full"        # منحة كاملة
GRANT_HALF: str = "half"        # نصف منحة

GRANT_LABELS: dict[str, str] = {
    GRANT_FULL: "منحة كاملة",
    GRANT_HALF: "نصف منحة",
}

# ── Section types ────────────────────────────────────────────────────────────

SECTION_INTERNAT: str = "internat"      # القسم الداخلي
SECTION_DAR_TALIB: str = "dar_talib"    # دار الطالب/ة
SECTION_CANTINE: str = "cantine"        # المطعم

SECTION_LABELS: dict[str, str] = {
    SECTION_INTERNAT: "القسم الداخلي",
    SECTION_DAR_TALIB: "دار الطالب/ة",
    SECTION_CANTINE:  "المطعم",
}

# ── Color palette (used in stylesheets across all screens) ────────────────────

COLOR_SIDEBAR_BG: str      = "#1e293b"
COLOR_SIDEBAR_HOVER: str   = "#334155"
COLOR_SIDEBAR_ACTIVE: str  = "#0f172a"
COLOR_SIDEBAR_BORDER: str  = "#334155"
COLOR_ACCENT: str          = "#38bdf8"
COLOR_DANGER: str          = "#ef4444"
COLOR_SUCCESS: str         = "#22c55e"
COLOR_SURFACE: str         = "#f8fafc"
COLOR_BORDER: str          = "#e2e8f0"
COLOR_TEXT_PRIMARY: str    = "#0f172a"
COLOR_TEXT_SECONDARY: str  = "#64748b"
COLOR_TEXT_SIDEBAR: str    = "#94a3b8"
COLOR_TEXT_SIDEBAR_ACTIVE: str = "#f1f5f9"

# ── Extended palette (used by charts dashboard) ───────────────────────────────
COLOR_PRIMARY:   str = "#1e3a5f"   # dark navy
COLOR_PURPLE:    str = "#8e44ad"   # purple (asha)
COLOR_TEAL:      str = "#16a085"   # teal
COLOR_WARNING:   str = "#e67e22"   # orange
COLOR_LIGHT_BG:  str = "#f4f6f9"   # page background
COLOR_TEXT_DARK: str = "#2c3e50"   # primary text
COLOR_TEXT_MID:  str = "#7f8c8d"   # secondary text

# ── Arabic date labels ────────────────────────────────────────────────────────
# Index 0 is a placeholder so ARABIC_MONTHS[1] == "يناير"
ARABIC_MONTHS: list = [
    "",
    "يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو",
    "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر",
]

# Matches Python's date.weekday(): 0 = Monday … 6 = Sunday
ARABIC_DAY_NAMES: list = [
    "الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
    "الجمعة", "السبت", "الأحد",
]
