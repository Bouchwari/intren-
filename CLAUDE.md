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
| PDF export   | `reportlab` (when we get there)    |
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

Build these **one at a time, in this order**. Do not work on multiple at once.

### ✅ Done
- [x] Project skeleton (folders, main entry, DB init)
- [x] Setup wizard (school identity: name, city, academy, director, school year)
- [x] Main window with sidebar navigation

### 📋 To Build
1. **Student management** (لائحة التلاميذ)
   - Import from Excel (mapping common formats from مسار / Massar)
   - Fields: full name, class, birth date, birth place, grant number, section (internat / cantine), grant type (full / half)
   - View as a searchable, filterable table
   - Add / edit / delete individual students
   - Sample Excel templates the user can download

2. **Internal teachers** (معلمو الداخلية)
   - Add / edit / delete teachers who eat at the school
   they are also student

3. **Weekly meal program** (البرنامج الغذائي الأسبوعي)
   - 7 days × 3 meals (فطور / غداء / عشاء) grid
   - Manual entry OR auto-generate from CPC meal templates
   - Separate program for Ramadan (السحور / الإفطار)
   - Save multiple programs and switch between them

4. **Daily contact sheet** (ورقة الاتصال اليومية للولوج للمطعم)
   - For each meal, count beneficiaries:
     - إعدادي → ممنوح / مؤد / متمم
     - تأهيلي → ممنوح / مؤد / متمم
     - معلمو الداخلية
   - Auto-compute totals
   - One row per (date, meal) — enforce uniqueness

5. **Daily absence sheet** (ورقة الغياب اليومي)
   - Same structure as the contact sheet but for absences

6. **Daily report** (التقرير اليومي)
   - Auto-generated from the day's contact + absence data
   - Notes field for the مسير

7. **Monthly summary** (المحضر الشهري / المدخر الشهري)
   - Aggregate counts per meal across the month
   - Export as the official "Procès-verbal de réception mensuel" form

8. **Order letter** (رسالة الطلبية)
   - Generated from the meal program + expected attendance

9. **Expense statement** (بيان المصاريف)
   - Per-meal unit prices × quantities → totals

10. **Violations book** (دفتر المخالفات)
    - Date, description, who reported, who signed off

11. **Document export**
    - PDF (using reportlab) — for official forms with the proper headers
    - Excel — for raw data
    - All output documents must include school header + signatures section

12. **Build & package**
    - `build.bat` script that runs PyInstaller to produce `matama.exe`

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

**End of file. When in doubt → ASK.**
