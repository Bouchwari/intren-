"""
config/settings.py
All paths and constants live here. Code never hardcodes these values.
"""

import os
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

# Root of the project (two levels up from this file)
IS_FROZEN: bool = bool(getattr(sys, "frozen", False))


def _resolve_app_data_dir(
    *,
    frozen: bool,
    base_dir: Path,
    local_app_data: str | None,
    home_dir: Path,
) -> Path:
    """Return writable app storage without depending on import-time globals."""
    if not frozen:
        return base_dir
    windows_data = (
        Path(local_app_data)
        if local_app_data
        else home_dir / "AppData" / "Local"
    )
    return windows_data / "TadbirInternat"


if IS_FROZEN:
    BASE_DIR: Path = Path(sys.executable).resolve().parent
    RESOURCE_DIR: Path = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    RESOURCE_DIR: Path = BASE_DIR

APP_DATA_DIR: Path = _resolve_app_data_dir(
    frozen=IS_FROZEN,
    base_dir=BASE_DIR,
    local_app_data=os.environ.get("LOCALAPPDATA"),
    home_dir=Path.home(),
)

# Where the SQLite database lives (next to the exe when packaged).
# MATAMA_DB_PATH lets a separate test launcher (see run_test.sh) point the
# app at a throwaway database instead, so trying things out never touches
# the real one. Source mode keeps the historical project-local filename;
# installed builds use per-user storage that survives application updates.
DB_PATH: Path = (
    Path(os.environ["MATAMA_DB_PATH"])
    if os.environ.get("MATAMA_DB_PATH")
    else APP_DATA_DIR / ("tadbir_internat.db" if IS_FROZEN else "matama.db")
)

# School logo (copied here when the user uploads one via Settings)
LOGO_PATH: Path = APP_DATA_DIR / (
    "school_logo.png" if IS_FROZEN else "matama_logo.png"
)

# Bundled fonts — loaded offline via ui.theme.load_fonts(), never rely on a
# font being installed on Windows. Frozen builds extract bundled resources to
# sys._MEIPASS, so fall back there when the source-tree path does not exist.
FONTS_DIR: Path = BASE_DIR / "assets" / "fonts"
if getattr(sys, 'frozen', False) and not FONTS_DIR.exists():
    FONTS_DIR = RESOURCE_DIR / "assets" / "fonts"

# Checkbox checkmark glyph — QCheckBox::indicator loses Qt's native check
# mark once ui/theme.py styles its background/border, so the stylesheet
# draws this image back in for the checked state. Same frozen-build fallback.
CHECK_ICON_PATH: Path = BASE_DIR / "assets" / "icons" / "check.svg"
if getattr(sys, 'frozen', False) and not CHECK_ICON_PATH.exists():
    CHECK_ICON_PATH = RESOURCE_DIR / "assets" / "icons" / "check.svg"

# Application artwork used by Qt, Windows Explorer, and the installer.
APP_ICON_PATH: Path = RESOURCE_DIR / "assets" / "app_icon.png"

# ── App identity ─────────────────────────────────────────────────────────────

APP_NAME: str = "تدبير الداخلية المدرسية"
APP_NAME_LATIN: str = "Tadbir Internat"
APP_VERSION: str = "1.1.0"

# Public release feed used for the optional, non-blocking update check.
UPDATE_API_URL: str = (
    "https://api.github.com/repos/Bouchwari/intren-/releases/latest"
)
UPDATE_INSTALLER_ASSET_NAME: str = "TadbirInternatSetup.exe"
UPDATE_TIMEOUT_MS: int = 8_000

# ── Window defaults ──────────────────────────────────────────────────────────

WINDOW_MIN_WIDTH: int = 1100
WINDOW_MIN_HEIGHT: int = 700

# ── Meal types (used as DB keys — never change these values) ─────────────────

MEAL_FTOUR: str = "ftour"       # فطور
MEAL_GHADA: str = "ghada"       # غداء
MEAL_ASHA: str = "asha"         # عشاء

# Ramadan meals. These two string values are NOT new — meal_program_screen.py
# has stored programs under them since before this constant existed, so they
# must stay exactly as they are or saved Ramadan programs stop loading.
MEAL_IFTAR: str = "ftour_ramadan"   # إفطار
MEAL_SHOUR: str = "shour"           # سحور

MEAL_LABELS: dict[str, str] = {
    MEAL_FTOUR: "فطور",
    MEAL_GHADA: "غداء",
    MEAL_ASHA:  "عشاء",
    MEAL_IFTAR: "إفطار",
    MEAL_SHOUR: "سحور",
}

# A day is either a normal day or a Ramadan day — never a mix of both.
# Confirmed by the user (2026-08-25): during Ramadan the school serves
# إفطار + سحور only, and these two REPLACE the three normal meals rather
# than being added alongside them. This also matches what the meal-program
# screen has always done and what both official Excel templates expect
# (each adds exactly two Ramadan columns).
REGULAR_MEALS: list[str] = [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA]
RAMADAN_MEALS: list[str] = [MEAL_IFTAR, MEAL_SHOUR]

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
# Teal/cream design system — see
# .claude/skills/matama/references/ui_design.md for the full rationale.
# Old names are kept so every existing import keeps working; they now point
# at the new teal/cream values instead of the older olive/paper ones.

# Base tokens
COLOR_PAPER: str      = "#F6F4EF"
COLOR_PANEL: str      = "#ffffff"
COLOR_PANEL_ALT: str  = "#E1F5EE"
COLOR_OLIVE: str      = "#085041"

COLOR_SIDEBAR_BG: str      = "#3F4A2F"
COLOR_SIDEBAR_HOVER: str   = "#4C5A37"
COLOR_SIDEBAR_ACTIVE: str  = "#566B3A"
COLOR_SIDEBAR_BORDER: str  = "#4C5A37"
COLOR_ACCENT: str          = "#1D9E75"
COLOR_ACCENT_DEEP: str     = "#177E5E"
COLOR_DANGER: str          = "#B3452C"
COLOR_SUCCESS: str         = "#16a34a"
COLOR_SURFACE: str         = COLOR_PAPER
COLOR_BORDER: str          = "#E4E1D8"
COLOR_TEXT_PRIMARY: str    = COLOR_OLIVE
COLOR_TEXT_SECONDARY: str  = "#6B7280"
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
