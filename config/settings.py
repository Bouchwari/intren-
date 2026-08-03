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

# Bundled fonts — loaded offline via ui.theme.load_fonts(), never rely on a
# font being installed on Windows.
FONTS_DIR: Path = BASE_DIR / "assets" / "fonts"

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
# Olive/paper design system — see
# .claude/skills/matama/references/ui_design.md for the full rationale.
# Old names are kept so every existing import keeps working; they now point
# at the new olive/paper values instead of the original navy/slate ones.

# Base tokens — already consistent across six screens before this migration
COLOR_PAPER: str      = "#f5f5f0"
COLOR_PANEL: str      = "#ffffff"
COLOR_PANEL_ALT: str  = "#eef0e4"
COLOR_OLIVE: str      = "#5A5A40"

COLOR_SIDEBAR_BG: str      = "#3F4A2F"
COLOR_SIDEBAR_HOVER: str   = "#4C5A37"
COLOR_SIDEBAR_ACTIVE: str  = "#566B3A"
COLOR_SIDEBAR_BORDER: str  = "#4C5A37"
COLOR_ACCENT: str          = "#7C8F4F"
COLOR_ACCENT_DEEP: str     = "#5F7239"
COLOR_DANGER: str          = "#B3452C"
COLOR_SUCCESS: str         = "#4B7F52"
COLOR_SURFACE: str         = COLOR_PAPER
COLOR_BORDER: str          = "#dddccd"
COLOR_TEXT_PRIMARY: str    = COLOR_OLIVE
COLOR_TEXT_SECONDARY: str  = "#8B8A6F"
COLOR_TEXT_SIDEBAR: str    = "#C9C9B0"
COLOR_TEXT_SIDEBAR_ACTIVE: str = "#E8E6DA"

# ── Type scale ───────────────────────────────────────────────────────────────
# Two faces: Maghribi is the official/title face (screen titles, printed
# document headers) — decorative, used sparingly. Cairo is the body face for
# everything else. Both bundled in assets/fonts/; the true family name is
# only known after ui.theme.load_fonts() registers them (fonts don't always
# report the name their filename suggests), so screens read it from
# ui.theme.body_font_family() / official_font_family(), not from a constant
# here.

FONT_TITLE: int   = 20
FONT_SECTION: int = 15
FONT_BODY: int    = 13
FONT_LABEL: int   = 12
FONT_CAPTION: int = 11

# ── Spacing scale ────────────────────────────────────────────────────────────

SPACE_XS: int = 4
SPACE_SM: int = 8
SPACE_MD: int = 12
SPACE_LG: int = 16
SPACE_XL: int = 24

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

# ── Document export format preference ─────────────────────────────────────────
# Controls what the single "طباعة/تصدير" button on each document screen does:
# ASK shows a PDF-or-Word popup every click; PDF/DOCX skip the popup and
# always export in that format. Stored in app_preferences (see settings_repo).

EXPORT_FORMAT_ASK: str  = "ask"
EXPORT_FORMAT_PDF: str  = "pdf"
EXPORT_FORMAT_DOCX: str = "docx"

EXPORT_FORMAT_DEFAULT: str = EXPORT_FORMAT_ASK

EXPORT_FORMAT_LABELS: dict[str, str] = {
    EXPORT_FORMAT_ASK:  "اسأل في كل مرة",
    EXPORT_FORMAT_PDF:  "PDF",
    EXPORT_FORMAT_DOCX: "Word",
}
