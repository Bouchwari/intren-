# CLAUDE.md — Instructions for Claude Code

> This file is permanent context. Read it before every response.
> If a request conflicts with this file, follow this file and ask the user.

---

## 1. PROJECT OVERVIEW

**Name:** نظام المطعمة (Matama System)
**Type:** Offline Windows desktop application
**Purpose:** Automate paperwork and daily tracking for school cafeteria management in Moroccan public schools (الإطعام المدرسي). Based on the Ministry of National Education's official procedural guide.

**Final delivery:** A single `.exe` file built with PyInstaller, runs offline on Windows, no install needed.

**End users:** School staff (مسير المصالح المادية والمالية, الحارس العام للداخلية, etc.) — not technical people.

---

## 2. USER PROFILE (the developer you're talking to)

- Arabic-native speaker, English is second language → reply in **clear, simple English**
- If the user writes in Arabic, you may reply in Arabic
- **Beginner-level programmer** → explain new concepts in one short line
- Code, file names, variables, comments → **English only**
- UI strings shown to end users → **Arabic only**, and only in the `ui/` layer
- The user works in VS Code with the Claude Code extension

---

## 3. TECH STACK — DO NOT DEVIATE

Use **only** these libraries. Never suggest alternatives unless the user explicitly asks.

| Purpose      | Library                            |
| ------------ | ---------------------------------- |
| Language     | Python 3.11+                       |
| UI framework | PySide6 (with RTL enabled)         |
| Database     | `sqlite3` (Python stdlib)          |
| Excel I/O    | `openpyxl`                         |
| Heavy data   | `pandas` — only if openpyxl can't  |
| PDF export   | `QPdfWriter` + `QPainter` (PySide6 native — not reportlab; reportlab was the original plan but every document screen ended up hand-drawing PDF pages directly with Qt instead, and it's never been added to `requirements.txt`) |
| Word export  | Fill real `.docx` templates in `templets/` via raw XML (zipfile + `xml.etree`) — not `python-docx` |
| Final build  | PyInstaller                        |

**Forbidden:** Flask, Django, Tkinter, PyQt5, SQLAlchemy, Electron, any web framework, any other UI toolkit.

---

## 4. ARCHITECTURE — STRICT LAYER RULES

```
src/
├── ui/      ← PySide6 windows, widgets, screens
├── core/    ← business logic, models, use cases
└── data/    ← SQLite repository, Excel handlers
config/
└── settings.py   ← ALL constants and paths
```

**Dependency rule (NEVER violate):**
- `ui/` may import from `core/` and `data/`
- `core/` may import from `data/`
- `core/` and `data/` **MUST NOT** import PySide6 — ever
- `ui/` **MUST NOT** contain SQL statements — ever
- Never skip layers (UI does not talk to SQLite directly)

**When adding a feature, decide which layer each piece belongs in.**
If unsure → ASK before writing code.

---

## 5. CODE STYLE — NON-NEGOTIABLE

- **Type hints on every function signature** — parameters and return type
- **Small functions** — max ~30 lines, one responsibility
- **Descriptive names** — no `tmp`, `data2`, `x`, `foo`
- **Constants UPPER_CASE** at the top of the file
- **Comments explain WHY, not WHAT**
- **No magic numbers or hardcoded strings** — everything goes in `config/settings.py`
- **Arabic UI strings live only in `ui/` files**
- **Path handling** — always use `pathlib.Path`, never string concatenation
- **Errors** — wrap risky operations in try/except, show user-friendly Arabic message via QMessageBox; log technical details

---

## 6. UI / UX REQUIREMENTS

The user wants a **clean, modern, professional** look — not basic gray Qt default.

- **RTL layout** enabled app-wide (`Qt.RightToLeft`)
- **Arabic font** that looks clean on Windows (Segoe UI works for Arabic too)
- **Sidebar navigation** with icons + labels (already built — see `main_window.py`)
- **Consistent colors** — define a palette in `config/settings.py` (primary, accent, danger, success)
- **Tables** — use `QTableView` with a model for any list of >20 rows, support search/filter/sort
- **Forms** — clear labels, validation feedback, required-field markers
- **Confirmation dialogs** for destructive actions (delete, overwrite)
- **Loading states** for slow operations (Excel import, PDF export)
- **Empty states** — when a table is empty, show a helpful message + action button
- **No emoji-only buttons** — always pair an icon with text

---

## 7. FEATURES — THE FULL APP

Status as of 2026-08-08. See `AI_HANDOFF.md` for session-by-session detail —
this list is the standing "what exists" summary, updated whenever a feature's
status changes. For the full document dependency chain (what triggers what,
who signs each step) see `.claude/skills/matama/references/document_chain.md`
— read it before touching any document-generation code.

### ✅ Done
- [x] Project skeleton (folders, main entry, DB init)
- [x] Setup wizard (school identity: name, city, academy, director, school year)
- [x] Main window with sidebar navigation
- [x] **يوم العمل** (Work Day) — the app's landing screen. Status cards for
      the day's 4 documents (contact/absence/report/order letter) + one
      "توليد شامل لعدة أيام" button that batch-generates any combination of
      them for a date range in one shot. Not in the original plan — added
      this session, inspired by a reference UI the user shared, RTL/teal
      styling native to this app.
- [x] **Student management** (لائحة التلاميذ) — Excel import, searchable/
      filterable table, add/edit/delete, monitors (معلمو الداخلية) as a tab
      within the same screen rather than a separate one.
- [x] **Weekly meal program** (البرنامج الغذائي الأسبوعي) — grid entry,
      Ramadan variant, multiple saved programs.
- [x] **Daily contact sheet** (ورقة الاتصال اليومية) — full ممنوح/مؤدي/متمم
      breakdown per cycle, auto-fill from historical estimator, official
      رقم الوثيقة numbering, PDF/Word export, batch combined-PDF export.
- [x] **Daily absence sheet** (ورقة الغياب اليومي) — same shape as contact.
- [x] **Daily report** (التقرير اليومي) — auto-computed from contact +
      absence, preserves manual overrides once saved, hygiene checklist.
- [x] **Monthly summary** (المحضر الشهري) — `monthly_report_screen.py`,
      aggregates net meals served + total cost for the month. Confirmed
      by the user this is a **different document** from محضر التسلم
      الشهري below, not an overlap.
- [x] **Order letter** (رسالة الطلبية) — reworked this session into a real
      daily document per the ministry process (was period-based before):
      auto-fills from that day's real ورقة الاتصال numbers, own sequential
      رقم الوثيقة per letter (editable before saving), PDF matches the real
      templets/رسالة الطلبية.docx exactly (plain black-and-white table, no
      invented fields), and يوم العمل's "توليد شامل" can now generate one
      independently-numbered letter per day across a whole range.
- [x] **Daily reception record** (محضر التسلم اليومي) — `daily_reception_screen.py`,
      built 2026-08-08. Confirms a day's delivered meals, quantities
      prefilled from that day's ورقة الاتصال (editable if reality
      differed, never silently recomputed once saved — same guarantee as
      the other daily screens). Fills the real bilingual FR/AR
      `templets/المحضر اليومي لتسلم الخدمة.docx` (3 separate `<w:tbl>`
      elements — signers/items/remarks — and real Word MERGEFIELD codes,
      not plain placeholder text; see `_set_mergefield_value`'s docstring
      for why a naive "first `<w:t>` in the paragraph" approach silently
      clobbers the closing "FAIT A TAGLEFT. LE" label). PDF is hand-drawn
      as usual. Wired into يوم العمل (status card + batch generation) and
      the sidebar (index 8, right after التقرير اليومي).
- [x] **Expense statement** (بيان المصاريف)
- [x] **Violations book** (دفتر المخالفات) — `incident_log_screen.py`
- [x] **Document export** — PDF via `QPdfWriter`/`QPainter` (own drawing,
      not reportlab), Word via filling the real templates in `templets/`
      directly, Excel via `openpyxl`. Every document screen has this.
- [x] **Build & package** — `Matama.spec` + PyInstaller. Builds and runs
      correctly on Linux for normal use (verified with a real, configured
      database). ⚠️ One unresolved finding: on a **completely fresh
      install** (empty database, so the first-run setup wizard shows), the
      packaged Linux binary exits right after the wizard appears instead of
      waiting for input — reproduced twice, isolated to the packaged build
      specifically (dev-mode `python src/main.py` handles the exact same
      empty-database case correctly). Very likely a Qt/Wayland platform-
      plugin quirk specific to this Linux dev machine, not the app's code —
      **needs verifying on an actual Windows machine**, which is the real
      target and wasn't available to test this from. See `AI_HANDOFF.md`
      for the full diagnosis.

### 📋 Not started
- **محضر التسلم الشهري** (`monthly_reception_record`) — real template at
  `templets/المحضر الشهري لتسلم الخدمة.docx`. Same shape as the daily one
  but for a whole month, 3 signers (HEADMASTER + STEWARD + CONTRACTOR).
  Confirmed a genuinely separate document from the existing المحضر الشهري
  screen — see `document_chain.md` for the full breakdown. Not built yet.
- Otherwise nothing major — remaining work is fixes/polish on the above, or
  whatever the user asks for next. Update this list as that changes.

---

## 8. WORKING STYLE — HOW TO RESPOND

### When the user asks for a new feature

1. **State the plan** in 2–3 sentences first
2. **List the files** you will create or modify and why
3. **Identify the layer** for each new piece (ui / core / data)
4. **Wait for "go"** if the plan touches >3 files or restructures anything
5. Then write the code

### When showing code

- For a **new file**: show the full contents
- For a **small edit**: show only the changed function/block with a few lines of context
- Always tell the user the file path

### When the user reports a bug

1. **Diagnose first, fix second**
2. Ask for the exact error message and what they did
3. **Do not rewrite working code elsewhere "while you're at it"**
4. Fix the minimum that resolves the bug
5. Explain in one line what was wrong

### When the user asks an open question

- If multiple valid answers exist, give **2–3 options with trade-offs**, then recommend one
- Don't dump every possibility

---

## 9. CRITICAL RULES — DO NOT VIOLATE

These rules exist because past mistakes made the codebase break. Follow them strictly.

🚫 **Never rewrite a file just to fix one function in it.** Edit only the function.

🚫 **Never delete code you didn't write in this turn** unless the user explicitly asks. The user may have edited it.

🚫 **Never change `config/settings.py` constants without asking.** Other files depend on them.

🚫 **Never reorganize folders** (move/rename files) without explicit permission.

🚫 **Never add a library to `requirements.txt`** without asking. Justify why the existing stack can't do it.

🚫 **Never put SQL in a `ui/` file.** SQL lives only in `src/data/`.

🚫 **Never import PySide6 in `core/` or `data/`.**

🚫 **Never invent UI strings in English.** End-user-facing text is always Arabic, defined as a constant.

🚫 **Never assume the database is empty.** Always handle: empty table, one row, many rows, missing fields.

🚫 **Never use `print()` for errors** in production code. Use logging or QMessageBox.

🚫 **Never add a new folder under `assets/` without adding it to `Matama.spec`'s `datas` list too.** The packaged build only bundles what's listed there — a new asset folder works fine in dev mode (`python src/main.py`) but silently goes missing from the built `.exe`/binary. This exact bug happened with `assets/icons/`.

✅ **Always read the existing file first** before editing it, to preserve what's already there.

✅ **Always run a mental test:** "If a teacher with no programming knowledge clicks this, what happens?"

✅ **Always handle the empty case** — empty student list, no meals today, no settings yet, etc.

---

## 10. WHAT TO AVOID

- ❌ Over-engineering: this is a personal tool, not enterprise software
- ❌ Premature optimization
- ❌ "While I'm here, let me also..." features the user didn't ask for
- ❌ Long theoretical lectures when the user asked a practical question
- ❌ Acronyms without spelling them out first (CRUD, ORM, MVC, etc.)
- ❌ Suggesting "modern best practices" if they violate the tech stack rules above

---

## 11. CONVERSATION CHECKLIST (silent — apply every turn)

Before sending a response, verify:

- [ ] Plan stated before code (for new features)
- [ ] Files to touch listed explicitly
- [ ] Correct layer for each piece (ui / core / data)
- [ ] Type hints on every function
- [ ] No PySide6 in core/ or data/
- [ ] No SQL in ui/
- [ ] No new library added without justification
- [ ] Existing code preserved (not rewritten unnecessarily)
- [ ] Empty / error cases handled
- [ ] Arabic strings only in ui/
- [ ] Path uses `pathlib.Path`

---

## 12. CURRENT HANDOFF

Before continuing recent UI/UX work, read `AI_HANDOFF.md`.

**Keep both files current — every session, not just when asked.** When a
feature's status changes, update its line in §7 above. When a session ends
(or context is about to run out), update `AI_HANDOFF.md` with what was done,
where things were left, and any new rule/convention established along the
way (add it to §9 too if it's a standing rule, not just this-session context).
The user relies on these files to pick up work across sessions without
re-explaining everything each time.

**End of file. When in doubt → ASK.**
