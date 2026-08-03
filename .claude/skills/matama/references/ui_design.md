# UI design tokens — نظام المطعمة

Written from what was already consistent across six screens
(`daily_contact_screen.py`, `daily_absence_screen.py`, `order_letter_screen.py`,
`students_screen.py`, `settings_screen.py`, `dialogs.py`), plus new tokens to
fill the gaps. Approved by the user before Stage 2 implementation started.

Single visual world — the app runs in one paper theme, not a switchable dark
mode. No dark variant is planned.

## 1. Color

### Base — already in use, unchanged

| Token | Hex | Use |
|---|---|---|
| `COLOR_PAPER` | `#f5f5f0` | Page background, every screen |
| `COLOR_PANEL` | `#ffffff` | Card / form background |
| `COLOR_BORDER` | `#dddccd` | Card & divider borders |
| `COLOR_OLIVE` (ink / primary text) | `#5A5A40` | Headings, primary text |

### New — fills gaps the base tokens didn't cover

| Token | Hex | Use |
|---|---|---|
| `COLOR_PANEL_ALT` | `#eef0e4` | Subtle section split inside a card |
| `COLOR_TEXT_SECONDARY` | `#8B8A6F` | Hints, captions, muted labels |
| `COLOR_ACCENT` | `#7C8F4F` | Primary buttons, active nav, table headers — replaces old sky-blue `#38bdf8` |
| `COLOR_ACCENT_DEEP` | `#5F7239` | Hover / pressed state for accent |
| `COLOR_DANGER` | `#B3452C` | Delete / destructive — warm terracotta, not a cold red |
| `COLOR_SUCCESS` | `#4B7F52` | Saved / confirmed states |
| `COLOR_SIDEBAR_BG` | `#3F4A2F` | Sidebar background — replaces navy `#1e293b` |
| `COLOR_SIDEBAR_ACTIVE` | `#566B3A` | Active sidebar item |
| `COLOR_SIDEBAR_HOVER` | `#4C5A37` | Sidebar item hover |
| `COLOR_TEXT_SIDEBAR` | `#C9C9B0` | Sidebar label (inactive) |
| `COLOR_TEXT_SIDEBAR_ACTIVE` | `#E8E6DA` | Sidebar label (active) |

The old navy/slate names in `config/settings.py` (`COLOR_SIDEBAR_BG`,
`COLOR_ACCENT`, `COLOR_DANGER`, `COLOR_SUCCESS`, `COLOR_SURFACE`,
`COLOR_BORDER`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_SECONDARY`, etc.) keep their
names — every screen that imports them keeps working — but now point at these
new values instead of the old navy/slate ones.

The "Extended palette (used by charts dashboard)" block in
`config/settings.py` (`COLOR_PRIMARY`, `COLOR_PURPLE`, `COLOR_TEAL`,
`COLOR_WARNING`) is out of scope here — those are categorical chart-series
colors, not UI chrome, and changing them is a separate decision.

## 2. Type

Two faces, deliberately different roles:

- **Maghribi** (`assets/fonts/maghribi-font 1.ttf`) — official/title face only.
  Screen titles, official-document headers on printed PDFs. Used sparingly;
  it's decorative and doesn't hold up at small sizes or in dense tables.
- **Cairo** (`assets/fonts/Cairo-Regular.ttf`, `Cairo-SemiBold.ttf`,
  `Cairo-Bold.ttf`) — body face for everything else: forms, tables, buttons,
  labels. Falls back to `Segoe UI` if the bundled font fails to load for any
  reason (never fail silently to a serif/mismatched fallback).

### Sizes

| Token | Size |
|---|---|
| `FONT_TITLE` | 20px |
| `FONT_SECTION` | 15px |
| `FONT_BODY` | 13px |
| `FONT_LABEL` | 12px |
| `FONT_CAPTION` | 11px |

## 3. Spacing

| Token | Value |
|---|---|
| `SPACE_XS` | 4px |
| `SPACE_SM` | 8px |
| `SPACE_MD` | 12px |
| `SPACE_LG` | 16px |
| `SPACE_XL` | 24px |

## 4. RTL rules

- App runs `Qt.RightToLeft` throughout.
- Numbers must stay left-to-right even inside RTL text — this is a known
  problem class (already hit and fixed multiple times in the PDF export
  code); the live Qt screens need the same audit. Set
  `setLayoutDirection(Qt.LayoutDirection.LeftToRight)` on spin boxes / count
  fields, or set explicit alignment for numeric table columns.
- When centering or right-aligning text drawn with `QPainter` +
  `QTextOption`, plain `AlignRight`/`AlignLeft` are direction-relative under
  RTL and land mirrored — combine with `Qt.AlignmentFlag.AlignAbsolute` to
  force true visual left/right.

## 5. Shared widgets (Stage 2.3, not built yet)

Planned: `StatusChip`, `Card`, `PrimaryButton`, `GhostButton`, `DangerButton`,
`CountField`, `EmptyState`, `SectionHeader`, `Toast` — one file each under
`src/ui/widgets/`, colors/sizes from `config/settings.py` only, no hardcoded
Arabic strings inside a widget (caller passes text in).
