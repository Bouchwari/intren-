# UI design tokens — نظام المطعمة

Stage 3 palette (2026-08-04): teal/cream, replacing the Stage 2 olive/paper
system. First built as one-off local constants in `dashboard_screen.py` and
`meal_program_screen.py` during that page's redesign, then centralized here
into `config/settings.py` so the rest of the app picks it up automatically.

Single visual world — the app runs in one paper theme, not a switchable dark
mode. No dark variant is planned.

## 1. Color

### Base

| Token | Hex | Use |
|---|---|---|
| `COLOR_PAPER` | `#F6F4EF` | Page background, every screen |
| `COLOR_PANEL` | `#ffffff` | Card / form background |
| `COLOR_BORDER` | `#E4E1D8` | Card & divider borders |
| `COLOR_OLIVE` (ink / primary text) | `#085041` | Headings, primary text |

### Supporting tokens

| Token | Hex | Use |
|---|---|---|
| `COLOR_PANEL_ALT` | `#E1F5EE` | Subtle section split inside a card |
| `COLOR_TEXT_SECONDARY` | `#6B7280` | Hints, captions, muted labels |
| `COLOR_ACCENT` | `#1D9E75` | Primary buttons, active nav, table headers |
| `COLOR_ACCENT_DEEP` | `#177E5E` | Hover / pressed state for accent |
| `COLOR_DANGER` | `#B3452C` | Delete / destructive — warm terracotta, not a cold red |
| `COLOR_SUCCESS` | `#16a34a` | Saved / confirmed states |
| `COLOR_SIDEBAR_BG` | `#3F4A2F` | Sidebar background — unchanged, not part of this migration |
| `COLOR_SIDEBAR_ACTIVE` | `#566B3A` | Active sidebar item |
| `COLOR_SIDEBAR_HOVER` | `#4C5A37` | Sidebar item hover |
| `COLOR_TEXT_SIDEBAR` | `#C9C9B0` | Sidebar label (inactive) |
| `COLOR_TEXT_SIDEBAR_ACTIVE` | `#E8E6DA` | Sidebar label (active) |

Per-meal accent colors (used on the meal program table and the dashboard's
meal-breakdown chart/pills — reuse anywhere a screen breaks numbers down by
فطور/غداء/عشاء): amber `#EF9F27` (فطور), teal `#1D9E75` (غداء), navy `#534AB7`
(عشاء). Not yet promoted to `config/settings.py` tokens — still local
constants per file (`_MEAL_ACCENTS` in `meal_program_screen.py`,
`_MEAL_COLOR_*` in `dashboard_screen.py`). Don't reuse `COLOR_ACCENT`/
`COLOR_SUCCESS`/`COLOR_PURPLE` for this — `COLOR_ACCENT` and `COLOR_SUCCESS`
are both green in this palette, so فطور/غداء become indistinguishable (hit
this exact bug in the Stage 3 migration, fixed in `dashboard_screen.py`).

**Known follow-up, not yet done:** `dashboard_screen.py`'s own header panel
(`_build_header`/`_build_welcome_panel`) still hardcodes the old olive/khaki
colors directly — it didn't move when `config/settings.py`'s tokens changed,
because it never referenced them. Same treatment daily_contact_screen.py just
got (swap local hardcoded hex for the shared tokens) still needs to happen
here; tracked as part of the larger dashboard redesign, not done yet.

The old olive/paper names in `config/settings.py` (`COLOR_SIDEBAR_BG`,
`COLOR_ACCENT`, `COLOR_DANGER`, `COLOR_SUCCESS`, `COLOR_SURFACE`,
`COLOR_BORDER`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_SECONDARY`, etc.) keep their
names — every screen that imports them keeps working — but now point at these
new teal/cream values instead.

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
