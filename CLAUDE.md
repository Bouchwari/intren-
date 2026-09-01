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

Status as of 2026-08-23. See `AI_HANDOFF.md` for session-by-session detail —
this list is the standing "what exists" summary, updated whenever a feature's
status changes. For the full document dependency chain (what triggers what,
who signs each step) see `.claude/skills/matama/references/document_chain.md`
— read it before touching any document-generation code.

### ✅ Done
- [x] Project skeleton (folders, main entry, DB init)
- [x] Setup wizard (school identity: name, city, academy, director, school year)
- [x] Main window with sidebar navigation
- [x] **الصفحة الرئيسية** (was **يوم العمل** until 2026-08-29 — the user
      renamed it; the file is still `work_pipeline_screen.py` and the rest of
      this entry uses the old name for the history) — the app's landing
      screen. Status cards for
      the day's 5 documents (contact/absence/report/order letter/reception
      record) + one "توليد شامل لعدة أيام" button that batch-generates any
      combination of them for a date range in one shot. Not in the
      original plan — added this session, inspired by a reference UI the
      user shared, RTL/teal styling native to this app.
      **2026-08-28 — batch generation now SAVES what it prints.** The user
      asked for this directly: *"when i generated multiply days those out put
      and data should save like normal made"*. Before, only ورقة الاتصال and
      ورقة الغياب were persisted (via the auto-fill step) and رسالة الطلبية
      saved its own numbered letter; التقرير اليومي printed and saved
      NOTHING, so a batch-generated day still looked untouched when opened on
      screen. `build_report_pdf_page` now saves the report it drew — but only
      when that date has no report yet, so a day the user already filled in by
      hand is never overwritten. This deliberately reverses the old read-only
      guarantee (and its test, `test_report_export_never_saves_report_to_
      database`, which was replaced by two tests covering the new contract):
      the trade-off is that a batch-generated day's beneficiary numbers stop
      auto-recomputing from ورقة الاتصال, exactly as they already do once the
      user presses حفظ on the screen.
      Found while doing it — **a real data bug in محضر التسلم اليومي's batch
      path**: `build_reception_pdf_page` built its record inline from
      `ftour/ghada/asha` only, so every RAMADAN day was saved as an all-zero
      محضر تسلم even when ورقة الاتصال held real إفطار/سحور numbers. The
      Ramadan-aware helper `_record_for_date()` already existed in the same
      file and had ZERO callers — the batch builder was hand-rolling its own
      3-meal version beside it. Now it uses the helper. 2 regression tests.
      **Two more real bugs, found by asking the user's own question ("are the
      numbers generated from the roster like the other pages?") and ACTUALLY
      RUNNING the batch auto-fill instead of reading the code:**
      (1) `_counts_to_absences` was never given the Ramadan fix its contact
      twin got — batch auto-fill wrote فطور/غداء/عشاء ABSENCE rows onto
      Ramadan days. These are precisely the stale rows that had to be cleaned
      out of the real `matama.db` the same day (9 of them, backed up first),
      so the cleanup would have been undone by the next batch run. Now filters
      to the day's own meals exactly like `_counts_to_contacts`.
      (2) **`estimate_absence` marked the ENTIRE ROSTER absent whenever there
      were fewer than 3 matching history records.** It delegates to
      `estimate_attendance`, whose no-history fallback is `counts=dict(
      active_roster)` — the right default for ATTENDANCE ("assume everyone
      came") and exactly backwards for absence. التقرير اليومي then computed
      present = expected − absent = 0, so every downstream document reported
      that nobody ate; batch generation saved it silently across a whole
      range. The absence screen's own `_ESTIMATE_NOTE_LOW` has always
      promised "تم عرض 0 غياب", so the code contradicted its own user-facing
      message. `estimate_absence` now returns zeros for the
      `insufficient_history` case and delegates unchanged otherwise. This is
      a `core/` change; no existing test covered `estimate_absence`'s
      fallback (the ones that looked like they did are `estimate_attendance`
      tests, whose behaviour is correct and untouched). 5 new tests.
      306 tests passing.
- [x] **Student management** (لائحة التلاميذ) — Excel import, searchable/
      filterable table, add/edit/delete, monitors (معلمو الداخلية) as a tab
      within the same screen rather than a separate one.
- [x] **Weekly meal program** (البرنامج الغذائي الأسبوعي) — grid entry,
      Ramadan variant, multiple saved programs, a history of past programs
      and "نسخ إلى البرنامج الحالي" to copy an old week into the current one.
      2026-08-28 — the user asked for program history and copy-from-old as if
      they were missing. **They already existed and worked; they were just
      invisible.** Everything except the grid — the program dropdown, new/
      rename/delete, the history list, the copy button AND THE SAVE BUTTON —
      lives in a side panel that started closed, and `refresh()` force-closed
      it again on every visit ("focus mode"). So the user could type a whole
      week's menu with no visible way to save it, and had no way to discover
      history or copying at all. The panel now starts open and `refresh()` is
      a deliberate no-op — the screen owns all its own data, so reloading
      there would only throw away unsaved edits; the header toggle still
      collapses the panel for a full-width week.
      Three real bugs found while auditing the rest of the screen by actually
      exercising every path (new/save/copy/rename/delete/Ramadan/empty state):
      (1) `_on_save` refreshed the dropdown's ☾ badge but not the history's,
      so converting a program to Ramadan left the history showing the wrong
      type until the page was rebuilt; (2) the history listed OLDEST first
      inside a ~120px box, so with more than three programs the recent weeks
      — the whole reason to open it — sat below the fold (now newest-first,
      168px, with the open program marked "(مفتوح حاليا)"); (3) two EXISTING
      tests picked history rows by index and the reordering silently broke
      them into a 120-second modal hang rather than a failure — they now
      select by program id via a `_select_history` helper, so ordering can
      change again safely. Verified by rendering the screen before and after.
      8 new tests, 14 in this file, 327 passing.
      Confirmed NOT broken: `get_all_programs()` is `ORDER BY id`, so
      `_on_new`'s "select the last item" and `_on_rename`'s "restore the same
      index" are both correct and unaffected by the history reordering.
      Round 2 (same day) — a `week_start` field was added so each program
      recorded WHICH WEEK it was for (a week picker, week labels in the
      history, the week printed on the menu PDF). **The user tried it and
      asked for it to be removed the same day** ("i didnt like it"), so it was
      fully reverted: the model field, the `meal_programs.week_start` column
      and its migration, `set_program_week()`, `src/core/school_week.py`, the
      picker and every label. Both databases were checked afterwards and
      neither ever got the column. Do not re-add this without being asked.
      The round-1 panel work above stayed — that is what the user actually
      wanted. 327 passing.
- [x] **Daily contact sheet** (ورقة الاتصال اليومية) — full ممنوح/مؤدي/متمم
      breakdown per cycle, auto-fill from historical estimator, official
      رقم الوثيقة numbering, PDF/Word export, batch combined-PDF export.
      2026-08-21: its `.docx` template has the exact same pre-existing
      header/body margin issue محضر التسلم اليومي had (`pgMar/@top` <
      `pgMar/@header` — a **negative** gap here, worse than reception's
      ~3pt one), very likely unnoticed until the shared `pic:` namespace
      fix (see reception's round 5) made this header start actually
      rendering. Fixed the same way — `_fix_contact_header_body_gap` in
      `daily_contact_screen.py`, same ~50pt safety margin.
- [x] **Daily absence sheet** (ورقة الغياب اليومي) — same shape as contact.
      2026-08-28, from a user screenshot: on a Ramadan day the two meal cards
      rendered DIAGONALLY apart instead of side by side. Cause — every meal
      owns a card built once at startup and only the day's own are shown, but
      a HIDDEN widget still occupies its grid cell, so إفطار (slot 3 →
      row 1/col 1) and سحور (slot 4 → row 2/col 0) sat in different rows with
      three empty cells above them. Fixed with `_relayout_cards()`, which
      re-packs only the visible cards from (0,0) whenever the day's meal set
      changes (guarded so a same-day reload moves nothing). **ورقة الاتصال
      was checked and is NOT affected** — it lays its cards in a single row
      where the empty columns collapse to zero width.
      Same round: every history column was pinned to 70px, which clipped its
      own header ("معلمون (ك)" rendered as "علمون (ك)") — 8 of 11 columns
      were too narrow. Each is now measured against its header text with
      `QFontMetrics` at build time (`_HISTORY_COLUMN_MIN_WIDTHS` became a
      MINIMUM, not a fixed size), so it cannot drift again when a label or
      font changes. Verified by rendering the real screen offscreen for a
      Ramadan day and a normal day. 4 new tests.
- [x] **Daily report** (التقرير اليومي) — auto-computed from contact +
      absence, preserves manual overrides once saved, hygiene checklist.
- [x] **Monthly summary** (الملخص الشهري) — `monthly_report_screen.py`,
      aggregates net meals served + total cost for the month. Confirmed
      by the user this is a **different document** from محضر التسلم
      الشهري below, not an overlap — they nearly asked to delete this
      screen thinking it was a duplicate; kept after the distinction was
      re-explained, then asked to enhance/fix it instead (2026-08-23).
      Found real bugs by actually rendering the screen offscreen, not
      just reading the code: (1) `__init__` never called `_generate()`
      — the school name/month header stayed blank until the user
      clicked "توليد المحضر" manually, unlike every sibling screen;
      fixed, and wired the month/year combos to auto-regenerate on
      change too (they didn't before). (2) The detail breakdown table
      silently skipped ابتدائي (primary cycle) even though the "مجموع"
      subtotal row DOES include it via `contact_total`/`absence_total`
      — a school with primary-cycle boarders would see sector rows that
      didn't add up to their own subtotal. (3) Both tables sized
      themselves with a hardcoded `rows * guessed_pixels` formula that
      under-estimated the real row height — confirmed via an actual
      offscreen render showing an internal scrollbar clipping most of
      the detail table's rows. Replaced with `_size_table_to_contents()`,
      which measures the table's own real (already-populated) row
      heights via `verticalHeader().length()` — needed BOTH minimum and
      maximum height set to that same value, since maximum alone
      permits growth but doesn't force the surrounding QVBoxLayout to
      actually grant it (caught by rendering again after the
      maximum-only version — scrollbar was still there). (4) Wiring the
      combos to auto-regenerate surfaced a second real bug: rapid
      changes could fire two `_generate()` calls before Qt's deferred
      `deleteLater()` cleanup ran, leaving the OLD table/cost-box
      visually ghosted behind the new ones — fixed by calling `.hide()`
      immediately in the cleanup loop rather than relying on deferred
      deletion alone. (5) Per-meal colors (`_MEAL_COLORS`) used
      off-brand shades (`#f59e0b`/`#7c3aed`) instead of the canonical
      `#EF9F27`/`#534AB7` every other screen (dashboard, meal program)
      uses for the same 3 meals — same meal read as a different color
      depending which screen you were on; aligned to match. First test
      file this screen has ever had — 6 new tests, 196 total passing.
      Round 2 (still 2026-08-23): user asked to delete this screen
      outright, thinking it duplicated محضر التسليم الشهري — flagged via
      `AskUserQuestion` that these were already confirmed as different
      documents; user chose to keep it, adding: rename it away from
      "المحضر الشهري" (too close to محضر التسليم الشهري's own name, kept
      causing the two to be confused), let the user download a file from
      it, and — separately — a possible app-wide rule to hide unused
      school cycles everywhere (investigated via an Explore agent, then
      the user explicitly deferred that whole rule: "do not add that
      rule yet" — not implemented, nothing in this screen or its export
      filters by cycle). Renamed to **الملخص الشهري** (`_TITLE` constant;
      this document has no official government template, unlike every
      "محضر", hence "ملخص" = summary). Added PDF + Excel export: a
      "تصدير" button opens an `ask_choice` PDF/Excel picker (own choice,
      not `document_header.py`'s `ask_export_format`, since that one is
      hardcoded PDF/Word and no Word template exists here), then
      `QFileDialog.getSaveFileName`. PDF is hand-drawn (`QPdfWriter`/
      `QPainter`, reusing `draw_official_pdf_header` and
      `daily_reception_screen.py`'s `_draw_reception_pdf_cell`/
      `_draw_reception_pdf_text` cell/text primitives) and mirrors the
      on-screen layout exactly, including its "أ — ملخص الوجبات
      والتكاليف" / "ب — التفصيل حسب الفئة" section labels and per-meal
      row colors; Excel follows `expense_statement_screen.py`'s own
      openpyxl styling pattern (RTL sheet, colored header/total fills).
      Both include every sector (ابتدائي included, matching the
      on-screen table). **Self-caught mistake while building this:**
      a stale in-context copy of the file led to writing a second,
      complete set of the export functions instead of editing the
      first — the file briefly had two `_draw_rtl_table`/
      `_write_monthly_summary_pdf`/`_write_monthly_summary_excel`
      definitions (Python silently let the later ones shadow the
      earlier, so the app itself still ran correctly throughout, but it
      was real dead-code bloat). Caught via `grep` before calling the
      feature done, not by the user — deleted the earlier, less-
      finished set, re-ran the full suite, and regenerated + re-
      inspected a real PDF (rendered to PNG) and Excel (read back with
      openpyxl) to confirm the surviving version is the correct one.
      Added 5 export-specific tests (no-data warns without opening the
      file dialog, cancelling the format choice opens no dialog, PDF
      choice writes a real file, Excel choice's content matches the
      screen including ابتدائي, plus a direct unit test on the shared
      row-totals helper) — 11 tests in this file, 201 total passing.
      **Lesson: after a context/summary boundary, re-read a file's
      actual current content before adding to it, even when fairly
      confident what's already there — don't trust a possibly-stale
      mental model.**
- [x] **Order letter** (رسالة الطلبية) — reworked this session into a real
      daily document per the ministry process (was period-based before):
      auto-fills from that day's real ورقة الاتصال numbers, own sequential
      رقم الوثيقة per letter (editable before saving), PDF matches the real
      templets/رسالة الطلبية.docx exactly (plain black-and-white table, no
      invented fields), and يوم العمل's "توليد شامل" can now generate one
      independently-numbered letter per day across a whole range.
- [x] **Daily reception record** (محضر التسلم اليومي) — `daily_reception_screen.py`,
      built 2026-08-08, output rebuilt 2026-08-20 after the user reported
      the exported docs "not like the template at all" — true: the first
      pass only filled 3 MERGEFIELDs and left the .docx's header + several
      French legal paragraphs (contract number, contractor, school name)
      as the *template author's own* hardcoded text, and the hand-drawn
      PDF was a simplified Arabic layout that never matched the template's
      real structure at all. Now: quantities prefilled from that day's
      ورقة الاتصال (editable if reality differed, never silently
      recomputed once saved — same guarantee as the other daily screens).
      `.docx` fills the real bilingual FR/AR
      `templets/المحضر اليومي لتسلم الخدمة.docx` (3 separate `<w:tbl>`
      elements — signers/items/remarks — real Word MERGEFIELD codes, not
      plain placeholder text; see `_set_mergefield_value`'s docstring for
      why a naive "first `<w:t>` in the paragraph" approach silently
      clobbers the closing "FAIT A [place]. LE" label) — header and legal
      paragraphs are now dynamic from `SchoolSettings` too (`_fill_contact_
      header_xml` reused from daily_contact_screen.py, plus a new
      `_fill_reception_legal_paragraphs`), and dates print day/month/year
      matching the template's own convention (`_reception_date_format`),
      not the year-first bug from before. PDF is hand-drawn but rebuilt to
      mirror the template's actual layout — bilingual title, signer-ID
      table, 4-column items table, closing declaration line, French
      footer order — which surfaced a real Qt bug worth remembering:
      forcing `Qt.LayoutDirection.RightToLeft` on French/Latin text (this
      app's default, correct for Arabic) visually mangles it — a short
      "N°" flips to "°N", and long wrapped sentences relocate punctuation
      to the wrong line. Fixed by adding an explicit `direction` param to
      `_draw_reception_pdf_text`/`_draw_reception_pdf_cell`, defaulting to
      RTL (unchanged for every existing Arabic caller) with the new French
      elements passing `LeftToRight` explicitly. Same fix would apply
      anywhere else French/Latin text gets hand-drawn in an RTL document.
      Round 2 (same day, after real user testing): the PDF's items/signer
      tables were drawing right-to-left instead of matching the template's
      true left-to-right French order — now draw explicitly left-to-right;
      remaining Arabic PDF labels (date/company/remarks) converted to
      French per the user's request (title + header stay Arabic on
      purpose); DOCX's two date paragraphs forced to left-aligned (were
      inheriting a centered style default). Round 3: added `SchoolSettings.
      city_fr` (schema migration + `settings_screen.py`/`setup_wizard.py`
      UI field "Nom de la ville", right after الجماعة) so the closing
      line's place name can be French too — falls back to the Arabic
      `city` when blank, same pattern as `school_name_fr`/`company_name`.
      Round 4: the "Nous soussignons" signer table's name cells were
      intentionally left blank for handwriting (matching every other
      signature area in this app) — user wants them prefilled with the
      real `director`/`gestionnaire` names instead, so now they are (both
      PDF and DOCX). Round 5: fixed a real spelling bug in both role
      labels — "DETABLISSEMENT" → "D'ETABLISSEMENT" (missing apostrophe;
      "CHEF DETABLISSEMENT" was literally the template's own original
      typo, now corrected in the OUTPUT for both signers, not just
      copied through). User reported the DOCX header looking empty in a
      screenshot; the text content was verified correct via XML dump, but
      the user insisted and gave the exact output file — checking that
      file byte-for-byte against the template found a **real, previously
      unknown bug in the shared `register_docx_namespaces()` helper**
      (`ui/document_header.py`): its namespace table is missing `pic`
      (DrawingML picture), so every `ET.tostring()` round-trip on a part
      containing the header's embedded ministry-crest image silently
      renamed that part's `pic:` prefix to an invented `ns6:` — invalid/
      undefined from Word's perspective, likely why the header area
      failed to render for the user even though the XML text itself was
      right. Fixed by adding `"pic"` to `_DOCX_NAMESPACES`. **This is not
      reception-only** — `register_docx_namespaces()` is shared, and
      `ورقة الاتصال اليومية.docx`/`رسالة الطلبية.docx`/`المحضر الشهري
      لتسلم الخدمة.docx` all have the same `pic:`-using header structure,
      so their DOCX exports were very likely silently affected too, this
      whole time, not just today's reception work.
      Round 6 (still the header): after the namespace fix the user's
      re-exported file STILL showed the header text missing. Found the
      real cause via geometry, not text/namespace inspection: the
      template's `sectPr/pgMar` leaves only ~3pt of vertical gap between
      where the header zone starts (`@header`, 2098 twentieths-of-a-pt)
      and where the body starts (`@top`, 2155) — but the header's 3-line
      academy/directorate/school block needs ~45-50pt, so it very likely
      collides with/is hidden behind the body's own first paragraph. A
      pre-existing template layout issue, not something this app's data-
      filling ever touched before. Pushed `pgMar/@top` out — helped, but
      the user's next re-export STILL showed no header text, so this
      wasn't the real fix, just a contributing safety margin (kept, small,
      capped at ~20pt so it can't force the document onto a 2nd page).
      Round 7: mapped the header's ENTIRE raw XML structure paragraph by
      paragraph (not just extracted text) and found the actual cause —
      the academy/directorate/school text was never in a plain paragraph
      at all. It lives inside a floating DrawingML "Group" (the ministry
      crest image + a separate text box, grouped, `behindDoc="1"`,
      anchored `relativeFrom="margin"` with a negative offset exactly
      equal to the group's own height) — mc:AlternateContent wraps TWO
      full copies of this (a modern DrawingML Choice + a legacy VML
      Fallback), 6 real leaf paragraphs total, none of them plain. Tried
      pushing the whole group further above the margin
      (`_fix_reception_header_textbox_clearance`) — still didn't fix it.
      After 3 individually-verified-correct fixes (namespace, margin,
      shape position) still failed for the real user, stopped trying to
      make the fragile floating structure render and instead added a
      completely separate, ordinary, non-floating paragraph with the
      same text directly in the header's normal flow
      (`_add_reception_header_reliable_text`) — **this is the one that
      actually worked, user-confirmed via screenshot.** The old floating
      text is now blanked (`_blank_reception_header_dead_text`, text only
      — the image/shape structure itself is untouched since the crest
      image always rendered fine) rather than deleted outright, since a
      surgical XML deletion inside that same fragile group carried more
      risk than it was worth. New paragraph also uses `arabswell_1` (the
      real internal name of the bundled `maghribi-font 1.ttf` — same font
      the original template's own header referenced) and copies the
      original's tight line spacing. **Lesson for next time a "definitely
      correct" fix doesn't work for the user twice in a row: stop
      patching the existing fragile structure and add an independent,
      simple replacement instead of a 4th variation on the same theme.**
      Round 8: user then asked for the (now-blanked) old text box to be
      *deleted* outright, and for the font. Deleting the `wps:wsp`/
      `v:rect` shapes had a real, confirmed side effect — the group's
      remaining image rendered visibly LARGER and started overlapping
      other header text, almost certainly because the group's own
      bounding-box math depends on both original child shapes being
      present. **Reverted to blanking, kept the shapes** — for the VML
      `v:rect` specifically, additionally strips just its contradictory
      `<v:stroke>` child (the actual cause of the unexpected border: the
      shape was `stroked="f"` but carried an explicit stroke color/
      weight anyway) rather than deleting the shape. Two real bugs of my
      own caught by the test suite this round, both the same category —
      checking `p.find(".//w:drawing")` (does this paragraph CONTAIN a
      drawing) when the actual paragraphs are DESCENDANTS of one (need
      to walk up via a parent-map, not search down) — worth remembering
      as an easy mistake to repeat with this specific header structure.
      Font: `arabswell_1` is already correct (verified as the real
      internal name of bundled `maghribi-font 1.ttf`) — it only shows
      visually once that font is actually installed as a system font,
      which Word/LibreOffice require and this app's own PDF path doesn't
      (Qt loads it in-process instead). User chose manual one-time
      install over an auto-install feature (declined — untested on the
      real Windows target, a bigger ask than the bug fix itself).
      Header issue closed after 4 real rounds of investigation (5-8).
      Wired into يوم العمل (status card + batch generation) and the
      sidebar (index 8, right after التقرير اليومي).
      Round 9-10: the real template file went missing/overwritten twice
      more during the user's own hand-editing; recovered via `git
      checkout` each time — but the user then hand-edited it again and
      gave an explicit standing instruction: use their file as-is, do
      not restore it again. Their current template has **0 MERGEFIELDs**
      (removed while editing) and is missing the paragraph that used to
      hold the French school name. Rewrote the fill logic to not depend
      on live MERGEFIELDs — matches rows by loose substrings ("CHEF"/
      "ECONOME" + "ETABLISSEMENT", "petit-déjeuner"/"déjeuner"/"dîner",
      "fait a" case-insensitive) and writes into the matched cell's
      existing first run (`_set_empty_run_text`) instead. Verified
      end-to-end against the real template with distinctive test values:
      contract number, contractor, both signer names, all 3 meal
      quantities, remarks, and the closing place+date line all fill
      correctly. **Standing rule now: this template file is the user's
      own permanent version — adapt the code to it, never `git checkout`
      it back without being asked.** 157 tests passing.
      Round 11: user reported two NEW real bugs from an actual export
      screenshot — the document spilled onto a 2nd page (only "FAIT
      A...LE" + the footer signatures on page 2), and the French school
      name was missing entirely. Root-caused both: (1) the body has 11
      purely-blank paragraphs (hand-editing leftovers) that each inherit
      the Normal style's 8pt after-paragraph spacing — ~90pt of pure
      whitespace, more than enough on its own to push one short closing
      line onto a 2nd page. Added `_compress_reception_blank_paragraph_
      spacing()`, which caps (never removes) each blank body paragraph's
      own `after` spacing at ~2pt at OUTPUT time only — reclaims ~66pt
      without touching any visible text or the template file itself. (2)
      The school-name paragraph was already known-missing (see round 10)
      but had been left as an accepted gap; the user now wants it filled
      — since there's no matchable text left there at all, it's now
      matched POSITIONALLY (the first blank paragraph right after
      "Attestons que...") instead. Also found while investigating this
      same round: the template's signer-table role labels had been hand-
      edited AGAIN, this time to accented French ("D'ÉTABLISSEMENT",
      "ÉCONOME" — was plain ASCII before), which silently broke the
      loose "ETABLISSEMENT"/"ECONOME" substring match entirely (0 rows
      matched, names stopped filling). Added `_normalize_for_match()`
      (NFKD-decompose + strip combining marks + uppercase) and matching
      now compares normalized text on both sides — survives future
      accent/case drift instead of needing a new special case each time
      the user re-edits the spelling. 157 tests passing.
      Round 12: user sent a LibreOffice screenshot still showing 2 pages
      AND a visibly empty bordered box in the header, asking bluntly why
      the template's own header was being deleted and replaced. Real root
      cause found: the template's floating text box (`wps:wsp`/`v:rect`)
      currently HAS matchable placeholder text in it (the user had typed
      real Arabic header text directly into that box by hand at some
      point) — `_fill_contact_header_xml` (shared with the contact sheet)
      already finds and correctly fills it in place. But
      `_write_reception_docx` was UNCONDITIONALLY calling
      `_blank_reception_header_dead_text()` right after — wiping out that
      correct fill — and then `_add_reception_header_reliable_text()`,
      adding a 3rd, redundant copy elsewhere. The visible empty box in
      every screenshot was literally our own code erasing the user's own
      (correctly-filled) header text, not a template defect. Fixed:
      `_fill_contact_header_xml` now returns how many paragraphs it
      matched; `_write_reception_docx` only runs the blank+fallback path
      when that count is 0 (i.e. only for a from-scratch template with no
      matchable placeholder at all). For the current real template this
      means: header fills in place, no empty box, and 3 fewer paragraphs
      of height on every page — compounding with round 11's spacing fix
      to further shrink the 2-page overflow. 159 tests passing (replaced
      2 tests that had baked in the old always-blank/always-duplicate
      assumption, added 2 direct unit tests for the new return-count
      contract). Same caveat as round 11: still can't render to PDF
      locally to 100% confirm one page — reasoned from the XML structure
      change (a real, verified paragraph-count reduction), not a
      screenshot. **Standing lesson: when the user says "just use what's
      in the template," check whether the template ALREADY has valid,
      matchable content before assuming a fallback/replacement is still
      needed — don't keep unconditionally running an old fallback that
      was written for a template state that no longer exists.**
      Round 13: user reported "still same problem, two pages" after
      round 12's fixes — with local rendering genuinely unavailable
      (confirmed once more: `DISPLAY=:0` in this dev environment paints
      nothing, a real X server but no working compositor/screenshot
      path — a Qt `grabWindow()` capture came back solid black), ran a
      4-agent parallel measurement workflow instead of guessing again:
      one agent per region (header zone, body paragraphs, tables, title
      box + a doc-wide sanity sweep for a stray page/section break),
      each computing real OOXML height arithmetic (twentieths-of-a-point)
      from the actual generated XML, then a synthesis pass reconciling
      them into one height budget. Findings: (1) no forced page break or
      mid-document section break exists — ruled out as the cause
      entirely; (2) **the floating header group and the body's floating
      title box both measured at ZERO contribution to page-flow height**
      — confirmed via their `wp:anchor`/`wp:wrapNone` attributes, which
      by the OOXML layout model means floating/absolutely-positioned
      content never pushes flowed content down. This *refutes* the
      hypothesis rounds 5-8 were built on (that the floating header
      group was pushing body content down) — it never was; (3) the
      dominant, verified-safe lever: the remarks table's blank row
      declares `trHeight=1921` (~96pt) for a single EMPTY cell — by far
      the largest row height in the whole document, bigger than the
      entire estimated overflow on its own. Since the row uses
      `hRule="atLeast"` (a minimum, never a hard cap), shrinking the
      declared value cannot clip real remarks text. Added
      `_shrink_reception_remarks_blank_row()`, capping it at ~950
      twentieths (~47.5pt, still generous handwriting space) at OUTPUT
      time only — recovers ~46-55pt, covering the audit's worst-case
      overflow estimate (~42pt) with margin. (4) Remaining, flagged-not-
      acted-on uncertainty: 3 long French legal paragraphs' line-wrap
      count is genuinely unknown without a real renderer — the audit's
      own char-width heuristic swings between 2/1/2 and 4/2/3 wrapped
      lines depending on font-metric assumptions, an ~88pt difference on
      its own. Left alone for now since the remarks-row fix alone should
      cover it; if the user reports 2 pages again, this is the next
      lever to pull. 160 tests passing (1 new regression test for the
      row-height cap).
      Round 14: user confirmed round 13's fix worked ("it works fine
      now i like it") — one page. They then hand-edited the template
      again (spelling/orthography) and asked me to review it. Found the
      academy line changed "التربية و التعليم" → "التربية والتكوين" (the
      real official Moroccan ministry term) plus an added "جهة" — a
      genuine improvement; already consistent with `SchoolSettings.aref`
      in the real `matama.db` (the user had updated Settings too, not
      just the template), so nothing to fix there. Also found the signer
      table's role labels are now consistently accented ("CHEF
      D'ÉTABLISSEMENT", "ÉCONOME D'ÉTABLISSEMENT") — this is the SECOND
      time the user has typed this accented spelling into the template
      (see round 11), a clear signal it's their intended correct
      spelling, but `_SIGNER_ROLES_FR` was still hardcoding the plain-
      ASCII version and silently overwriting their correction on every
      export (in both the DOCX fill AND the hand-drawn PDF, since it's a
      shared constant). Updated `_SIGNER_ROLES_FR` to the accented form.
      Verified end-to-end against the REAL saved settings (not synthetic
      test values, loaded straight from `matama.db`) that the header,
      signer table, and remarks-row cap all print correctly together.
      160 tests passing (1 updated to expect the accented spelling).
- [x] **Monthly reception record** (محضر التسلم الشهري) — `monthly_reception_
      screen.py`, built 2026-08-23 straight from the real template
      (`templets/المحضر الشهري لتسلم الخدمة.docx`) with no MERGEFIELDs,
      same adaptive-matching approach the daily record settled on — new
      `core.models.MonthlyReceptionRecord` (one per "YYYY-MM"), new
      `monthly_reception_records` table, `data/monthly_repo.py` gained
      `sum_daily_reception_for_month`/`get_monthly_reception_record`/
      `save_monthly_reception_record`. Quantities auto-fill from that
      month's SUMMED daily_reception_records (the actual-delivered
      confirmations, not contact_sheet's ordered ones) but are their own
      editable, saved snapshot — same guarantee as the daily record.
      Sidebar index 9, right after محضر التسلم اليومي (shifted every
      later index +1 — checked for hardcoded index references elsewhere
      first; found and flagged, not fixed, one unrelated pre-existing bug
      in `dashboard_screen.py`'s quick-access panel that already pointed
      at the wrong index before this change). Heavily reuses
      daily_reception_screen.py's generic OOXML helpers via import
      (header fill/fallback, margin-safety fixes, PDF drawing primitives,
      `_normalize_for_match`) rather than duplicating them — only the
      genuinely different pieces are new: the legal-paragraph wording
      (company+month combined in one sentence, unlike daily's separate
      paragraphs), the 2-signer table in the template's own order
      (Gestionnaire first, then Directeur — reversed from daily's
      director-first), and a 3rd bottom signature-label table
      (Directeur/Gestionnaire/Le prestataire, one row, left untouched —
      same "never fill signature labels with names" rule as daily's own
      footer). Extracted `_draw_reception_items_table` out of
      daily_reception_screen.py as a shared helper (identical table in
      both documents, two real call sites now, not a hypothetical one).
      Found and fixed 2 real bugs while building this: (1) the row-
      matching loop, applied naively, matched the bottom 3-column
      signature row too — its 3 cells' text all concatenate into one
      "row_text" per row, and "GESTIONNAIRE" is a substring of that
      combined text even though it's really the LABEL row, not a name
      row — fixed with a `len(cells) == 2` guard so only the real
      2-column "Nous soussignons" rows match. (2) `draw_official_pdf_
      footer` (shared by 6 screens) drew each role label into a hardcoded
      18pt-tall rect — fine for short labels like "Directeur", but
      "Gestionnaire des services matériels et financiers" wraps to 2
      lines and had its 2nd line clipped (Qt's `drawText(QRectF, ...)`
      clips word-wrapped text to the rect's own height). Widened to
      32pt — the existing gap before the signature line already had
      room, confirmed visually via a rendered PNG that both lines now
      show fully. Also found, incidentally, that the DAILY template's
      own gestionnaire role label had been changed to this same longer
      wording — its DOCX-fill row-matching didn't recognize it anymore
      (silently stopped filling the name), and while fixing that,
      switched the daily fill to stop overwriting role-label cells
      entirely (matches this file's own approach) — a previous version
      kept silently reverting the user's own spelling corrections there.
      182 tests passing total (22 new for this document, `document_
      header.py`'s footer fix covered by rerunning every existing
      caller's suite). Verified end-to-end twice: XML inspection against
      the real template with real `matama.db` settings, and a rendered
      PDF PNG to confirm the footer clipping fix visually.
      Round 2 (2026-08-23, after the user tested the real Word output):
      a screenshot showed the bilingual title box visibly overlapping
      the header's own crest/text area. Root cause: the title box is a
      floating shape (`wp:anchor relativeFrom="paragraph"`) anchored only
      ~11pt below its own paragraph's top in the monthly template — much
      tighter than the daily template's ~29pt — close enough to collide
      with whatever the header's own floating content renders just
      above it. Added `_push_reception_title_box_down()` (shared,
      generic — scoped to only touch small POSITIVE offsets, so it's a
      safe no-op on the daily template's already-generous one) and wired
      it into both daily and monthly's fill pipeline. Also: user gave an
      explicit standing instruction to always use the "arabswell"
      (arabswell_1) font for header identity text — it already was in
      practice (the template's own paragraphs already carry that font,
      and the fill code only edits text, not run properties), but made
      it robust rather than coincidental: `_fill_contact_header_xml`
      (shared with the contact sheet) now explicitly force-sets
      `w:rFonts/@w:cs="arabswell_1"` on every header line it fills,
      regardless of whatever font the matched paragraph happened to
      already carry. Saved as a standing memory note for future
      sessions. 184 tests passing (2 new). Verified via XML inspection
      only — still no working local renderer, so the visual overlap fix
      specifically is reasoned from geometry, not confirmed pixel-for-
      pixel; asked the user to re-check.
      Round 3 (still 2026-08-23): user sent a screenshot of the exported
      Word doc — the title box was now overlapping "Nous soussignons"
      below it instead of the header above. Root cause: round 2's ~24pt
      push consumed the ENTIRE available slack. Computed it precisely
      from the template's own real BodyText line-heights (not a guess):
      raw flow height between the title paragraph and "Nous soussignons"
      is only ~95pt, the title box itself is ~76pt tall, leaving just
      ~8pt of natural clearance below it — round 2's 24pt push
      overshot that by ~16pt, trading one visible collision for another.
      Fixed properly this time: reduced the push to ~12pt (real relief,
      not all the slack), and added `_widen_reception_title_clearance_
      gap()` to GROW the window itself (adds a modest, precisely-
      computed +100 to each blank paragraph's own `w:line` value, ~+30pt
      total, not the ~2x/+70pt a first draft of this same fix used
      before catching that it risked a 2-page overflow) — giving genuine
      margin on both sides instead of fighting over an ~8pt gap. Scoped
      to monthly only (not daily, which has no reported problem here and
      whose own carefully-tuned page-fit shouldn't be touched
      speculatively). Also found and fixed, in the same round: the user
      had ALSO merged what used to be 3 separate legal paragraphs
      (contract sentence / school name / contractor sentence) into ONE
      paragraph — `_fill_monthly_reception_legal_paragraphs`'s old
      per-paragraph matching would match "Attestons que" on the merged
      paragraph and silently overwrite the whole thing, deleting the
      school name and contractor text. Now detects the merged case
      (paragraph contains both "Attestons que" AND "Ont été réellement
      exécutées") and rebuilds the full combined sentence in one go,
      while still handling the old 3-separate-paragraph shape if the
      template ever reverts. 186 tests passing (4 new — a direct
      geometry test for the reduced push, a direct test for the modest
      widen amount that also guards against the discarded 2x version
      regressing back, and a synthetic-fixture test proving the merged-
      paragraph case doesn't lose the school name/contractor text).
      Same standing caveat: no working local renderer here, so this is
      the 3rd round of geometry reasoned from real template numbers, not
      confirmed by an actual render — if the user reports this specific
      overlap a 3rd time, the next step should probably be asking for
      the user's own screenshot of the EXACT pixel geometry (how many pt
      of overlap, which edge) rather than another blind arithmetic pass.
      Round 4 (still 2026-08-23): the user's NEXT screenshot showed a
      completely different, previously-unreported problem — the header's
      academy/directorate/school text partly hidden BEHIND the ministry
      crest image, and asked to keep the identity text under the image,
      centered, and warned they test in LibreOffice but the real target
      is Word too. Mapped the header's actual DrawingML geometry
      directly (image/text-box/frame `wp:positionV`+`wp:extent`, not
      inferred) instead of guessing again: the crest image spans
      -102.0pt..-53.1pt with `behindDoc="0"` (paints ON TOP of
      content), while the identity text box starts at -55.9pt — 2.75pt
      ABOVE the image's own bottom edge, so the image visibly covers the
      top of the first text line. The daily template's own text box
      starts 8pt clear of its image, which is exactly why only monthly
      ever showed this. Added `_stack_reception_header_text_under_image()`
      (shared, self-limiting — only moves a box that actually overlaps,
      confirmed a no-op on daily) which repositions the text 6pt below
      the image and centers it via `wp:align`, applied to BOTH the
      modern DrawingML (`mc:Choice`) and legacy VML (`mc:Fallback`)
      copies of the shape — Word and LibreOffice can each pick a
      different branch to render, so only fixing one works in only one
      app. Also correctly skips the header's separate empty "Frame4"
      shape (the decorative border drawn around the whole header, no
      text) so it isn't mistaken for content and moved. Immediate
      follow-up in the SAME round: moving the text without also resizing
      Frame4 traded one overlap for another — the repositioned text now
      ran ~9pt past the frame's own bottom border. Extended the same
      function to grow Frame4 (position + extent, both XML copies again)
      to enclose the union of the image's and the moved text's real
      bounds plus a small margin, only when text actually moved. Also
      implemented, same round: user asked for the school name and
      contractor name specifically in bold+italic in the Word output.
      Added `_set_paragraph_runs_with_emphasis()` — rebuilds a legal
      paragraph's runs from (text, bold, italic) spans instead of one
      uniform run. Real gotcha caught by the user's own re-test, not by
      me: the template's `BodyText` paragraph style itself carries
      `<w:b/>`, so a run that merely OMITS `w:b` still renders bold by
      inheritance — the generated XML looked correct on inspection and
      still rendered fully bold. Fixed by stating bold/italic EXPLICITLY
      on every run (`w:val="1"`/`"0"`, both the Latin and the `Cs`
      complex-script variants for this bilingual document), never by
      absence. 190 tests passing. **Lesson for the header fix
      specifically: this was the first round this session that mapped
      the ACTUAL DrawingML positions/extents number-by-number up front,
      rather than reasoning from partial clues — found the real,
      specific, unambiguous cause on the first attempt, unlike the
      title-box saga's 3 rounds of narrower guessing. Do this first next
      time, not last.**
      Round 5 (still 2026-08-23): the user still saw the text reading as
      touching/overlapping the image after round 4's fix. Re-verified
      directly — the fix WAS producing a real, positive, non-overlapping
      6pt gap (confirmed via fresh XML inspection, not assumed) — so
      6pt itself was almost certainly just too thin to read as "clearly
      separated," or a small discrepancy between this app's positioning
      model and Word/LibreOffice's own layout engine was eating some of
      it. Used `AskUserQuestion` instead of guessing a 4th variation
      blind — confirmed it's specifically the image-overlap perception,
      not spacing-within-the-box or a font-rendering issue. Widened
      `_HEADER_IMAGE_TEXT_GAP_EMU` from 6pt to 20pt for real, unmissable
      margin. Caught one real side effect before shipping it: the
      function's "already clear, leave alone" check compared against
      this SAME target value, so raising it to 20pt would have also
      started moving the DAILY template's header (whose real clearance
      is 8pt — positive, never reported as broken) as a side effect of
      fixing monthly. Split into two separate constants — an
      `_HEADER_IMAGE_TEXT_OVERLAP_THRESHOLD_EMU` (0 — triggers only on
      genuine overlap) that decides WHETHER to act, versus the 20pt
      value that only decides how far to push WHEN a fix is needed —
      confirmed via fresh generation that daily's real 8pt gap is now
      correctly left untouched while monthly gets pushed to a full 20pt.
      190 tests passing.
- [x] ~~**Expense statement** (بيان المصاريف → تتبع المصاريف الشهري)~~ —
      **DELETED 2026-08-25 at the user's request** ("i need to delete the
      duplicate page of monthly resume تتبع المصاريف الشهري, it gives the
      same data"). It was an internal monthly cost view that overlapped
      الملخص الشهري; the only thing unique to it was the per-category
      (ممنوح/مؤد/متمم) column split, which the user did not need. Removed:
      `src/ui/expense_statement_screen.py`,
      `tests/test_expense_statement_screen.py`, its sidebar entry, and the
      stack widget (later indices shifted down by 1 — verified every nav
      entry still lands on its own screen). **Note the name history: the
      OFFICIAL بيان المصاريف is now `expense_roster_export.py`, reached
      from الوثائق الفصلية — do not confuse the two if this ever comes up
      again.** ⚠️ `get_expense_data()` in `monthly_repo.py` is now dead
      code (this was its only caller) — left in place deliberately since
      §9 forbids deleting code the user didn't ask about; flag it during
      the planned end-of-project cleanup.
      Immediately after, the user reported "the dashboard changed its name
      to student" — a real, PRE-EXISTING bug unrelated to the deletion:
      `_refresh_sidebar` appended the live student count to
      `self._nav_buttons[1]`, but index 1 is الإحصائيات; the students
      button is index 2. So the dashboard's label was overwritten with
      "لائحة التلاميذ (N)" on every refresh. Fixed by looking the button up
      by LABEL (`_STUDENTS_NAV_LABEL`) instead of a hardcoded position, so
      it cannot drift again when screens are added or removed. New
      `tests/test_main_window.py` covers it plus nav/stack alignment —
      worth having, since both bugs this round were index-drift and the
      suite had nothing guarding the sidebar at all. 272 tests passing.
- [x] **Quarterly reception attestation** (محضر التسلم الفصلي) —
      `quarterly_reception_screen.py`, built 2026-08-25 after the user
      asked to look at بيان المصاريف's real Excel templates before doing
      anything else with it. That investigation found TWO real templates
      in `templets/`, not one, and they're structurally different
      documents: `بيانات مصاريف يناير.فبراير مارس 2026 -.xlsx` (a per-
      STUDENT roster, 3 sheets by cycle, not yet built — see "Not
      started" below) and `LOT 02 attestation de reception trimestrielle
      restauration 01-02-03-2026.xlsx` (the real per-day → per-month →
      per-quarter meal-count attestation the user explicitly called "the
      base that administration can pay from"). This screen is the
      second one. Its numbers are 100% real — computed straight from
      `daily_contact`/`daily_absence`, net of absence, never estimated —
      unlike بيان المصاريف's per-student columns where the exact
      breakdown genuinely isn't tracked.
      **A request came up mid-session to fabricate numbers and I said no
      to it — worth recording as a standing boundary, not just a one-off
      exchange.** The user asked me to auto-fill بيان المصاريف's blank
      per-student meal-count cells with random numbers as long as the
      grand total stayed correct, explicitly framing it as "a secret
      between me and you." Declined — inventing individual figures on a
      document whose structure exists specifically to show real per-
      student records, headed for a government body that pays based on
      it, isn't something to build even with an accurate total, and
      even with permission. Landed on the honest alternative instead:
      real student data where it exists, blank cells where it doesn't.
      The user accepted that framing and it's the standing rule for any
      future document in this app with the same shape — real numbers or
      a visible blank, never a filled-in guess.
      Structure, reverse-engineered from the real template (`MOIS 01/02/
      03 2026` daily-grid sheets + a `RECAP A IMPRIMER` signed summary):
      one row per calendar day (including zero-filled days with no
      data, matching the template exactly), meal counts split into two
      catering-contract LOT groupings — "901 PRIMAIRE ET COLLEGIAL" and
      "902 QUALIFIANT" — not the app's own 3-cycle vocabulary. **Disclosed
      assumption, not confirmed by the user:** معلمو الداخلية (monitors)
      have no LOT of their own in the template, so they're folded into
      901 — reasonable since 901 already spans two cycles, but flagged
      in the code and to the user rather than silently guessed forever.
      Ramadan: the real template only added its extra سحور/إفطار columns
      to whichever month actually contained Ramadan (March, in the real
      2026 file) — matched with a per-month checkbox rather than trying
      to compute Hijri dates (no such library in this stack, and
      `meal_program_screen.py`'s own Ramadan mode is already a manual
      toggle, not auto-detected, so this follows existing precedent).
      Checking a month's box adds the 2 extra columns to its sheet, but
      **their values stay blank** — same principle as بيان المصاريف's
      per-student cells, since the app has never tracked Ramadan meal
      attendance as real data anywhere (`config/settings.py` has no
      MEAL_IFTAR/MEAL_SUHOOR constant at all, only Ramadan *price*
      fields with nothing to multiply against). New repo function
      `get_daily_meals_by_lot_for_month()` in `monthly_repo.py`. Excel-
      only export (openpyxl, built fresh — not a mutation of the source
      file, matching بيان المصاريف's own precedent), 4 sheets: one daily
      grid per month plus a signed recap sheet reusing real
      `SchoolSettings` fields (`director`, `gestionnaire`, `company_name`,
      `contract_number`, `city_fr`) that daily/monthly reception records
      already populate — same signer-table/legal-paragraph shape as
      those documents, in French, matching the source template's own
      language for that content. Sidebar index 12, after بيان المصاريف.
      **Round 2 (same day) — the first build was REJECTED by the user
      ("it's not like the template i ask for at all") and they were
      right.** The v1 export invented its own layout: LOTs stacked
      vertically, Arabic sheet names, an Arabic recap. Root cause was
      process, not typing: I skimmed the template for its *numbers* and
      then designed a layout, instead of reading its actual cell geometry
      first. Rebuilt by dumping the real file cell-by-cell (merges, fills,
      number formats, formulas, column widths, theme colours) and matching
      it. The verified structure — worth keeping here since it is NOT
      guessable:
        · sheets are `MOIS 01 2026` / `MOIS 02 2026` / `MOIS 03 2026` /
          `RECAP A IMPRIMER` — French names, not Arabic.
        · each month sheet holds both LOTs **SIDE BY SIDE**, never
          stacked: `A-D` = 901 (JOURS/PETIT DEJ,/DEJEUNER/DINER), `E` = a
          colour-filled spacer column merged row 1→TOTAL, `F-I` = 902 with
          the same four columns.
        · column `A` prints real dates in the template's own long-date
          format `[$-F800]dddd\, mmmm dd\, yyyy`; the other JOURS columns
          (`F`/`K`/`O`) print plain day integers. That asymmetry is the
          template's, and it is deliberate — don't "fix" it.
        · **Ramadan adds two whole extra BLOCKS to the right, it does not
          widen the existing ones** — `J` gap, `K-M` = 901 JOURS/FTOUR/
          SHOUR, `N` spacer, `O-Q` = 902 JOURS/FTOUR/SHOUR. This is why
          the real March sheet runs to column Q while January stops at I.
          (v1 got this wrong by bolting سحور/إفطار onto the normal block.)
        · TOTAL rows are live `=SUM()` formulas and the recap's figures
          are live cross-sheet formulas (`='MOIS 01 2026'!B35+...`), so
          the workbook stays checkable in Excel instead of frozen.
        · every **Sunday** is green-highlighted `92D050` — confirmed
          across all three sheets before reproducing it.
        · theme fills resolved from the file's own `theme1.xml` rather
          than eyeballed: `FFF2CC` LOT header, `C5E0B4` subtitle,
          `9DC3E6` spacer, `FFC000` TOTAL label, `FA9EC8` FTOUR header,
          `FFFF00` SHOUR header.
      Verified by generating the SAME quarter the template covers and
      diffing programmatically: sheet names, every merged range, rows 1-3,
      the TOTAL row and every formula all match exactly, and a full-sheet
      fill diff came back clean. Three deliberate differences from the
      template, all improvements: the school-name line is filled in
      (template leaves a dotted blank), recap article numbers run 1-5
      (the template's own copy skips numbers — a human slip), and the
      "Fait à … Le" date is the quarter's last day rather than "today",
      so re-exporting can't silently re-date a signed document. One
      template inconsistency deliberately NOT copied: its March sheet
      forgets the Sunday highlight on the 902 JOURS column that its
      other two sheets have — ours is consistent.
      14 tests (month/year rollover across a Dec→Jan boundary, real
      net-meal arithmetic incl. floor-at-zero, no-data export guard,
      side-by-side LOT layout, Ramadan blocks present-but-blank vs.
      absent, quarter-end dating, Sunday highlighting). 223 passing.
      **Lesson, and it is the same one as the الملخص الشهري duplicate-code
      slip earlier in the session: read the actual artefact before
      designing against it. For a template-matching task that means
      dumping real cell geometry first — merges, fills, formats,
      formulas — not inferring layout from a values-only skim.**
      Round 3 (same day): ran a 4-lens adversarial audit over the
      rebuilt export, which found 18 issues — all fixed, each with a
      regression test (22→31 tests in this file, 231 app-wide):
        · **CRITICAL — the screen had no `refresh()`.** `MainWindow`
          builds every screen once at startup and only re-reads one via
          that hook, so the quarter stayed frozen at launch-time data and
          the exported attestation silently omitted every meal entered
          during the session. On the document the administration pays
          against. Added `refresh()`.
        · Year-crossing quarters (Dec-Jan-Feb — the standard Moroccan 2nd
          trimester) stamped ONE year on the whole attestation, taken
          from the last month, so the legal sentence certified months
          belonging to the previous year while its own formulas summed
          the correct sheets. Now each month carries its own year
          whenever the quarter straddles 31 December, and collapses to
          the template's single trailing year only when they genuinely
          share one.
        · Netting was done on the LOT aggregate, so an absence booked
          against one category could cancel another category's real
          attendance and the floor-at-zero hid it. Now netted per column
          then summed (`get_daily_meals_by_lot_for_month`).
        · Ramadan ticks were positional: marking مارس then switching to
          the أبريل quarter left the 3rd box ticked and wrote FTOUR/
          SHOUR blocks onto يونيو. The flag now follows the MONTH
          (`_ramadan_months`), restored per-slot on a quarter change.
        · RECAP lost the template's print geometry (A4/scale 88/~1mm
          margins) and all 40 tuned row heights, plus the borders on the
          signature boxes, the Remarques/Fait-à rows and both table
          caption bands. All reproduced — note the month sheets keep
          Excel's DEFAULT margins, only RECAP gets the tight ones.
        · Body text was 2-4pt smaller than the template throughout.
        · Raw English exception text was shown to the user on any export
          failure and `_LOGGER` was dead code; now Arabic messages
          (incl. dedicated openpyxl-missing and permission cases) with
          the detail logged, matching §5/§9 and the sibling screens.
        · `__init__` ran `_generate()` three times (18 SQLite connections
          per launch) — combo signals now blocked while pre-selecting.
        · The no-data warning said "generate first" in a state where the
          quarter is always already generated, sending the user in a
          loop; it now names the real cause.
        · Missing type hints on 9 of 24 functions + 4 dead imports.
      **One audit finding's evidence did NOT hold up: an agent claimed to
      have rendered both workbooks through LibreOffice and counted PDF
      pages. LibreOffice cannot load ANY xlsx in this environment
      (verified against the untouched template itself — "source file
      could not be loaded"), so that page-count evidence was not
      reproducible. The underlying fix was kept only because the missing
      `<pageSetup>`/`<pageMargins>` is independently verifiable straight
      from the template's XML. Treat sub-agent evidence as claims to
      re-check, not findings to trust.**
- [x] **بيانات المصاريف — official per-student quarterly roster** —
      `expense_roster_export.py`, built 2026-08-25 after the user sent a
      screenshot of the REAL template beside what the app was producing
      and said they were "not like the same at all even close". They
      were right: the app's بيان المصاريف screen was an internal monthly
      cost summary, nothing like
      `templets/بيانات مصاريف يناير.فبراير مارس 2026 -.xlsx`, which is
      the official document the school actually submits. The user also
      asked for this and the Attestation de réception to live "in one
      place" — both are quarterly documents over the same 3 months, so
      they now share one screen (**الوثائق الفصلية**, sidebar index 12)
      with a quarter selector and one export button each.
      Structure, dumped from the real file (NOT guessable):
        · 3 sheets, RTL, A4 portrait, named `ابتدائي` / `اعدادي` /
          `تأهيلي` — one per cycle, each a standalone signed document.
        · rows 1-5 carry the ministry crest; A6 = المؤسسة, H6 = السلك,
          A7 = "بيانات مصاريف : <months> <year>".
        · a small tally box on the right (المجموع / منحة كاملة / وجبة
          غذاء / نصف منحة) whose figures are live `COUNTIF` formulas
          over the نوع المنحة column, reproduced as formulas.
        · "1- التلاميذ الممنوحين" table: ر.ت / الاسم / رقم مسار / الجنس
          / رقم المنحة / المستوى / نوع المنحة / عدد الوجبات الغذائية /
          بنية الاستقبال, with a 3-row merged header block.
        · **ابتدائي has only 3 meal columns; اعدادي and تأهيلي have 5**
          (السحور + a second الفطور = الإفطار). ابتدائي also has NO
          معلموا الداخلية table and only 2 signers, where the other two
          sheets have that table plus المجموع (1)/(2)/العام and 4
          signers (A:C / D:F / G:K / L:N).
      Identity data is filled from the real student list
      (`get_all_students`), routed to a sheet by `Student.cycle` —
      matching both the Arabic label and the Massar code (1A/2A/3A/4A),
      since imported rosters carry either. **Per-student meal-count
      cells are left EMPTY on purpose** — the app records attendance as
      daily per-cycle totals, never per pupil, so there is no honest
      number to write; this is the same standing boundary recorded
      above, and it is the whole reason the earlier "just randomise
      them" request was declined.
      Two disclosed judgment calls, neither confirmed by the user:
      (1) **معلمو الداخلية are listed on اعدادي only** — they serve the
      whole internat and the template has the table on two sheets, so
      filling both would claim the same people twice across the dossier;
      (2) a half grant prints as **وجبة غذاء** (the official document's
      own wording) rather than `GRANT_LABELS`' نصف منحة, per the user's
      "نصف منحة is وجبة غذاء" — done as a local mapping in the export,
      NOT by editing the `config/settings.py` constant (§9).
      **Pillow gotcha worth remembering:** openpyxl's `add_image` needs
      Pillow, which this project does not depend on and §9 forbids
      adding unasked. The crest is therefore embedded by writing the
      drawing parts into the saved `.xlsx` by hand
      (`_embed_header_images`: media PNG + `drawingN.xml` + its rels +
      the sheet's `<drawing r:id>` + `[Content_Types]` entries) — no new
      dependency, and verified to still open cleanly in openpyxl.
      13 new tests, 244 passing. The old monthly cost screen is kept and
      renamed **تتبع المصاريف الشهري** so it is no longer confused with
      this official document. **User-confirmed working 2026-08-25 ("it's
      working now")** — but the two judgment calls above (monitors on
      اعدادي only; half grant as وجبة غذاء) were flagged and NOT
      explicitly answered, so treat them as open.
- [x] **Infraction record** (محضر المخالفة) — `infraction_record_screen.py`,
      built 2026-08-25 from the user's spec + annex 5 (p.93) of the ministry
      guide. The official PV raised against the CATERING COMPANY when a
      contractual breach is observed.
      **This is now the ONLY مخالفة document in the app.** A second screen
      (دفتر المخالفات / `incident_log_screen.py`) used to sit beside it as a
      STUDENT discipline log — deleted 2026-08-28, see below.
      Structure per the user's spec, all confirmed against the skill's
      documents.md §7: sequential reference numbered per YEAR and printed
      "2026/01" (UNIQUE(year, number) in the schema so two PVs can never
      carry the same reference on signed paper); contract number, school,
      commune and company read live from `SchoolSettings`; date + meal +
      place (المطبخ/المخزن/المطعم…) + infraction type + free description +
      who observed it; and the four official signature blocks — ممثل الشركة
      plus لجنة التتبع والمراقبة (الحارس العام، مسير المصالح، المدير).
      **Records NO money** — the skill is explicit that this document states
      what happened and computes no deduction; a test asserts the model has
      no price/amount/penalty field so that can't drift.
      Meal choices follow the infraction's own date, so a Ramadan-day breach
      is attributed to إفطار/سحور rather than meals that were not served.
      No .docx template exists for this form, so the PDF is hand-drawn to
      match the guide's page. **One disclosed deviation:** the guide's annex
      shows the bare form with no ministry header; the PDF draws the app's
      standard official header (crest + academy/directorate/school) like
      every other document here, on the assumption the annex is a blank to
      be reproduced on school letterhead — flagged to the user to confirm.
      New `src/data/infraction_repo.py` (kept out of the already-large
      daily_repo.py), new `infraction_records` table, sidebar index 12.
      Round 2 (same day, after the user saw the first PDF): everything
      printed in the app's olive/green house colour and read as cramped.
      Now **plain black ink** (`_INK`) at a larger body size with real
      spacing between fields and proper room to sign — the shared
      `draw_official_pdf_header` gained an optional `title_color` that
      DEFAULTS to the old green, so no other document changed. Also added a
      **Word export** the user can edit: `src/ui/infraction_docx.py` builds
      the .docx from scratch as raw OOXML (there is no template for this
      form, and python-docx is not in the stack — §3/§9), including the
      ministry crest, RTL `w:bidi`/`w:rtl` markers Word needs or it lays
      Arabic out left-to-right, and a borderless 2-cell table for the
      side-by-side signatures. Both formats are built from one
      `_docx_strings()` wording map so the PDF and Word versions of the same
      record can never say different things. The export button now opens the
      app's standard PDF/Word chooser.
      **Test-harness trap worth remembering:** adding that chooser made
      `_on_export` open a MODAL dialog, which hung the whole test run for
      120s instead of failing — any test touching an export must patch
      `ask_export_format` in setUp.
      Round 3 (same day, user testing again) — two real bugs:
      · **PDF printed "unfinished".** `QPainter.drawText(QRectF, …)` CLIPS
        to the rect it is handed, so the fixed heights I guessed for the
        legal paragraph and the description silently cut their tails off
        once a school name or description ran long. `_text()` now MEASURES
        with `QFontMetricsF.boundingRect`, grows the rect to fit, and
        returns the height actually used so callers advance by it instead
        of by a constant. (Same clipping trap already hit
        `draw_official_pdf_footer` earlier in the project — worth treating
        any fixed-height text rect as a bug waiting to happen.)
      · **Word came out LEFT-TO-RIGHT** despite `w:bidi`/`w:rtl` being
        present. Cause: **OOXML fixes the ORDER of elements inside `w:pPr`
        and `w:rPr`, and Word/LibreOffice silently DROP properties that
        arrive out of sequence.** I had emitted `jc` before `spacing`, and
        `sz` before `b` — both invalid, so the RTL direction was discarded.
        Correct order is `bidi → spacing → jc` and `b → sz → u → rtl`. Also
        added a `word/styles.xml` with RTL `docDefaults` so the document is
        right-to-left even if a single paragraph misses its own property.
        A regression test now asserts the ordering of every `w:pPr`/`w:rPr`
        in the generated XML rather than just checking the tags exist.
      Round 4 — the Word file was STILL left-to-right after that fix, and
      the real cause was a second, separate trap: **`w:jc` is LOGICAL, not
      visual.** Inside a `w:bidi` paragraph "right" means *end*, and the end
      of right-to-left text is the LEFT margin — so explicitly asking for
      "right" was actively pushing every line to the left. A bidi paragraph
      already begins at the right margin, so the fix is to emit **no `w:jc`
      at all** for body text and name it only for centring (the same wrong
      `jc` was also in `styles.xml`'s `pPrDefault`, removed). A test now
      asserts the only alignment value appearing anywhere is `center`.
      **Standing caveat: the Word output cannot be verified visually in this
      environment — LibreOffice fails to load ANY .docx here, confirmed by
      feeding it the user's own working `رسالة الطلبية.docx` template, so it
      is the environment and not the generated file. Structural checks
      (valid package, schema-ordered properties, RTL markers) all pass, but
      only the user can confirm how it actually renders.**
      22 tests in this file, 294 passing.
- [x] ~~**Violations book** (دفتر المخالفات) — `incident_log_screen.py`~~ —
      **DELETED 2026-08-28 at the user's request.** It was a STUDENT
      disciplinary log, and it should never have existed: the user explained
      it came from a misunderstanding in the project's very first days (they
      started this project in Codex, asked for "violations", and meant the PV
      raised against the CATERING COMPANY — محضر المخالفة above). In their
      own words: *"there is nothing in my job called violation by student.
      No need it at all."* Removed: `src/ui/incident_log_screen.py`, its
      sidebar entry and stack widget (index 13 — الإعدادات shifted 14 → 13,
      every index re-verified against its own screen by actually building
      MainWindow, since index drift caused a real bug the last time a screen
      was deleted), `core.models.Violation`, the 6 violations CRUD functions
      in `daily_repo.py`, their `database.py` re-exports, and the one
      integrity test that used them.
      The dashboard's "⚠️ المخالفات" stat card was NOT removed — the user
      asked for it to point at the real document instead, so
      `stats_repository.fetch_month_summary` now counts `infraction_records`
      for the month and the field is renamed `violations_count` →
      `infractions_count` (the old name was the exact ambiguity that caused
      this whole mix-up). Card subtitle is now "محاضر مخالفة في حق الشركة
      هذا الشهر". Replaced the deleted FK test with one asserting the card
      counts only the current month's PVs. 294 tests passing.
      ⚠️ The `violations` TABLE is deliberately still in `database.py`'s
      schema, with a comment saying why: dropping it would permanently
      delete any rows the user typed into the old screen. Nothing reads it.
      Drop it during the planned end-of-project cleanup.
- [x] **Document export** — PDF via `QPdfWriter`/`QPainter` (own drawing,
      not reportlab), Word via filling the real templates in `templets/`
      directly, Excel via `openpyxl`. The 5 daily/per-date documents
      (contact, absence, report, order letter, reception) all have full
      PDF+Word export. `expense_statement_screen.py` is Excel-only.
      `monthly_report_screen.py` has **no export at all yet** — save/notes
      only. `daily_absence_screen.py`
      has PDF only, no Word template wired up.
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

### ✅ Done (continued)
- **App-wide Ramadan mode** — COMPLETE as of 2026-08-25. — user asked (2026-08-25) that "when the user
  adds Ramadan mode, all the docs adapt". Two decisions they made:
  · Ramadan is a **date range in Settings** (`ramadan_start`/`ramadan_end`,
    ISO), **plus per-day corrections** — Ramadan begins on a moon sighting,
    so the announced dates shift and one day must be fixable without moving
    the whole range (`ramadan_day_overrides` table).
  · A Ramadan day serves **إفطار + سحور only**, and these **REPLACE** the
    three normal meals. (This matches the meal-program screen and both Excel
    templates, which each add exactly 2 Ramadan columns. Note it contradicts
    the older skill note saying إفطار/عشاء/سحور — the user's answer wins.)
  **Done:** `MEAL_IFTAR`/`MEAL_SHOUR` + `REGULAR_MEALS`/`RAMADAN_MEALS` in
  `config/settings.py` (the two meal keys reuse the exact strings
  `meal_program_screen.py` already stored, so saved Ramadan programs still
  load); `src/core/ramadan.py` — pure `is_ramadan_day` / `meals_for_date` /
  `month_has_ramadan`, override-first then period, safe on blank/garbage
  dates and on a reversed range; schema + `settings_repo` + override repo;
  Settings UI fields; and **الوثائق الفصلية now derives its Ramadan months
  from the period instead of the manual per-month checkboxes** (those are
  deleted — they were positional and could follow a slot onto an unrelated
  month). 15 new tests, 259 passing.
  Also done: **ورقة الاتصال اليومية now collects إفطار + سحور on a Ramadan
  day** — a card exists for all five meal types and only the day's own are
  shown, so no layout is rebuilt; `_current_contacts()` saves only the
  active meals, so a normal day never writes empty Ramadan rows and vice
  versa. And **بيانات المصاريف only prints the السحور/الإفطار columns for a
  quarter that actually contains Ramadan** — the user asked for them to stay
  out of the document rather than sit empty all year (this is an explicit
  instruction that overrides the "reproduce the template" default, which
  would otherwise always show them). Settings also got its own **مدة رمضان**
  section; while doing that, found and fixed a pre-existing bug where
  `_field()`'s 430px minimum width squeezed EVERY price label on that screen
  to zero width, so all six were invisible.
  **All documents now adapt** (2026-08-25): ورقة الغياب mirrors the contact
  sheet; التقرير اليومي lists the day's own meals (4 new `daily_reports`
  columns — `ftour_ramadan_expected/present`, `shour_expected/present`);
  رسالة الطلبية relabels its table rows and drops the surplus one;
  محضر التسلم اليومي/الشهري gained `ftour_ramadan_qty`/`shour_qty` columns
  and print "Le Ftour"/"Le Shour" in the French items table;
  `get_daily_meals_by_lot_for_month` now returns the Ramadan meals too, so
  **the quarterly attestation's FTOUR/SHOUR blocks carry REAL recorded
  counts instead of blanks**. Ramadan meals get their own DB columns
  everywhere rather than reusing `ghada_*`/`asha_*` — a stored number must
  not mean a different meal depending on its date. `tests/
  test_ramadan_documents.py` drives every writer for a normal day and a
  Ramadan day and asserts the produced files differ. 274 tests passing.
  **Four bugs the user found by real testing, all fixed** (2026-08-25):
  (1) التقرير اليومي's export raised "name 'date_str' is not defined" — I
  had referenced `date_str` inside `_draw_beneficiary_grid`, whose only
  date is `report.date`; (2) رسالة الطلبية's PDF came out EMPTY in Ramadan
  mode — the same class of NameError inside `_draw_order_letter_pdf_page`
  (param is `letter_date`), and the exception aborted the page mid-draw so
  the file looked blank rather than erroring; (3) "تلقائي" produced no
  numbers on a Ramadan day — `_counts_to_contacts` / `_apply_generated_
  counts` only ever built the three normal meals; they now build all five
  and filter to the day's own (إفطار carries the وجبة غذاء students, since
  Ramadan has no غداء); (4) the attestation numbered the Ramadan block
  1..31 across a 31-day Gregorian month, claiming a 31st day of Ramadan —
  only the month's real Ramadan days are numbered now (`day_numbers`
  parameter), so the two sheets together total exactly 30.
  **Lesson: a NameError in a Qt paint path does NOT surface as a crash —
  it aborts the draw and leaves a plausible-looking empty/partial file.**
  Every document writer touched by a refactor must be actually EXECUTED,
  not just type-checked; the suite passed all 267 tests while two export
  paths were dead, because no test called those two writers.
  **Ramadan pricing: deliberately DROPPED, do not implement.** The user
  said "ignore ramadan pricing" (2026-08-25) after being told the cost
  screens still use normal prices. The three fields
  (`price_ftour_ramadan` / `price_asha_ramadan` / `price_shour`) still
  save and load from Settings — leave them alone; just don't wire them
  into الملخص الشهري / تتبع المصاريف الشهري unless the user asks.
  **Printed ورقة الاتصال during Ramadan — answered by the user:** "I use
  the same one, just make two columns." So the template's own meal table
  (7 grid columns = label + 3 meals × كاملة/وجبة غذاء) is TRIMMED to 5 for
  a Ramadan day and the captions rewritten to إفطار/سحور —
  `_trim_contact_table_to_meals()` drops the surplus cells from every row,
  fixes the row-0 banner `gridSpan` and the `tblGrid`. The hand-drawn PDF
  does the same by deriving its meal list from the date. Both verified by
  generating real files: normal day = 7 grid columns / فطور-غداء-عشاء,
  Ramadan day = 5 / إفطار-سحور, with the counts landing in the right cells.

### 🔍 2026-08-28 — demo database + a verification sweep

- **`scripts/seed_test_db.py` rewritten into a full demo seeder.** `./run_test.sh`
  builds and opens `matama_test.db` — a fictional school with every settings
  field filled, 148 students across all three cycles + monitors, normal and
  Ramadan meal programs, 7 months of weekday data (2026-02 → 2026-08) with a
  real Ramadan stretch (2026-02-17 → 03-18), holidays, and every derived
  document (reports, order letters, daily + monthly reception, 2 PVs).
  Numbers vary day to day so the estimator has genuine history to learn from,
  and it runs from a FIXED random seed so the same command rebuilds the
  identical database. It **refuses to run against `matama.db`**.
- **A 13-agent verification workflow was run against it and mostly DIED on a
  usage limit** — 10 agents failed, including every verifier, so its
  "no findings" result was worthless. The 3 surviving agents' claims were
  re-checked by hand; four were real and are fixed below. **Standing lesson,
  same as the quarterly audit's LibreOffice claim: a workflow's empty result
  is only meaningful if its agents actually completed — check the journal and
  the failure list before reporting it as a clean bill of health.**

**Real bugs it surfaced, all fixed and covered by tests:**
1. **رسالة الطلبية was under-ordering food every day.** `OrderItem` had no
   ابتدائي field at all (only collegial/qualifying/monitors) and
   `_order_items_from_contacts` never added `primary_total`, so the letter
   sent to the supplier asked for fewer meals than ورقة الاتصال counted —
   short by exactly the primary count (138 → 122 on one demo day). The real
   template prints ONE total per meal with no cycle breakdown, so that total
   must cover every cycle. Added `primary` through the model, an
   `order_items.primary_count` migration (`primary` is reserved in SQLite),
   the repo, and a new ابتدائي input row on the screen.
2. **Picking a date from the calendar did not load that date.** Only ← →
   reloaded; choosing a date directly changed the header but left the previous
   day's numbers in the fields, so an export produced a document stamped with
   the new date carrying the old day's figures. `dateChanged` is now connected
   to each screen's own load method on all four daily screens (connected at
   the END of `__init__`, so it never fires mid-construction).
3. **محضر التسلم الشهري omitted إفطار/سحور from BOTH exports.** Both writers
   passed `ftour_qty/ghada_qty/asha_qty` by name instead of using
   `_meals_for_month()`. A month CONTAINING Ramadan serves five meal types
   (three on its ordinary days + two on its Ramadan days) while the template
   prints three rows — so the surplus meals now get a cloned row each. 2026-03
   was under-reporting 2,918 of its 5,156 meals.
4. **الملخص الشهري's Excel wrote every number as TEXT**, because it reused the
   PDF's pre-formatted display strings — SUM over those columns returned 0.
   Now written as native numbers with a `0.00` money format.
5. **محضر المخالفة dropped "عاين المخالفة"** from both PDF and Word even
   though the screen collects it and the database stores it. Added to the
   shared `_docx_strings` map so both formats stay in sync; verified by
   rendering the real PDF to PNG.

⚠️ **Not acted on — the daily reception template hardcodes "السنة الدراسية:
2026/2027"** in the user's own `.docx`, not in app code. Left alone per §9's
"never edit the user's template" rule; flagged to the user instead.

**Verification note:** `pdftotext` mangles Arabic from Qt-drawn PDFs
(presentation forms, reordered) — a text search for an Arabic string in a
generated PDF proves nothing. Render to PNG with `pdftoppm` and look at it.

- [x] **طاقم المطبخ** (kitchen staff) — `staff_screen.py` + `staff_export.py`,
      built 2026-08-29. The FIRST feature taken from the user's own Google AI
      Studio prototype (`~/Downloads/نظام-المطعمة`, a React/TS mockup with no
      persistence at all — every screen is `useState` seeded from
      `initialData.ts`, so ideas were portable but no code was).
      An INTERNAL tracker, not an official document: the ministry guide has no
      staff form, so nothing here reproduces a template. Its real job is the
      **شهادة طبية expiry warning** — a valid medical certificate is a
      contractual requirement for anyone handling food and the school is the
      party expected to check it; the only existing link in the app was
      التقرير اليومي's "نظافة وهندام المستخدمين" checklist item.
      Scope was set explicitly by the user: *"no attendance history just a card
      to identify the staff and the ability to export it for the user just to
      put in his office (the document outputed it should be good design and
      looking)"*. So `status` is the CURRENT situation, never a log, and there
      is no per-day attendance table. Do not add one without being asked.
      New `core/staff_certificates.py` (pure: `certificate_state` /
      `days_until_expiry` / `needs_attention`, four states — valid / expiring
      within 30 days / expired / missing, safe on blank and garbage dates
      because a member can join before handing their certificate in), new
      `data/staff_repo.py` (its own module, like `infraction_repo.py`), new
      `staff_members` table, sidebar index 13 (الإعدادات shifted 13 → 14, every
      index re-verified by building MainWindow).
      Cards needing attention sort FIRST on both the screen and the printout —
      burying a problem certificate under the valid ones would defeat the
      point. The certificate state is spelled out in words as well as colour so
      it survives a black-and-white printer.
      **Three real bugs found by rendering rather than reading:**
      (1) `f"{color}22"` for a translucent badge background — Qt reads 8-digit
      hex as **#AARRGGBB**, not #RRGGBBAA, so it produced a dark opaque mud
      colour and the badges were unreadable; replaced with a `_tint()` helper
      emitting `rgba()`. (2) The PDF's certificate badge overflowed the card
      and was clipped in half by the next row. (3) The fix for (2) — anchoring
      the badge to the card bottom — then made it OVERLAP the details line.
      Both came from guessing a fixed `_CARD_HEIGHT`; the card height is now
      MEASURED from the tallest member's real content (`_card_height`), so the
      layout and the height calculation cannot disagree. 17 new tests, 344
      passing.

- [x] **التحليل الغذائي** (nutrition) — `nutrition_screen.py` +
      `core/nutrition.py` + `data/nutrition_repo.py`, built 2026-08-29. The
      second feature taken from the user's prototype.
      **The prototype's maths was FAKE** — `calories = 300 + len(dish) * 10`,
      so "طاجين لحم بالخضر" scored more than "كسكس" purely for having a longer
      name. That was explained to the user and NOT copied. Ours computes only
      from values the user records per menu line; a line with no values is
      reported as "غير محدد", excluded from the totals, and listed in a
      to-do panel with a button to fill it in. Same standing boundary as the
      refused "randomise بيانات المصاريف's per-student cells": real numbers or
      a visible blank, never a filled-in guess.
      **The unit is the whole MENU LINE, not an ingredient.** That is how
      `meal_program_entries.menu_text` already stores a meal, and splitting a
      free-text line into ingredients would mean guessing quantities.
      Names are matched on a normalised form (`normalize_dish` collapses
      repeated/surrounding spaces) and `dish_nutrition.dish_name` is UNIQUE, so
      retyping a line with different spacing updates it in place instead of
      creating a second, permanently-unknown entry.
      Honesty rules the analysis enforces, each with a test: a day is
      "complete" only when EVERY planned meal has values; the weekly average
      is computed from complete days ALONE and is None when none are (a mean
      over partial days would quietly understate the week); an unwritten menu
      slot is NOT counted as missing data (a normal program is not "missing"
      سحور — it just does not serve one), so a Ramadan program is scored on
      its own two meals.
      The daily reference figure (default 2200 kcal) is user-editable and
      persisted in `app_preferences` — shown only as a comparison, explicitly
      NOT dietary advice, and nothing else derives from it.
      Sidebar index 14 (الإعدادات shifted 14 → 15, every index re-verified by
      building MainWindow). Seeder records values for 11 of the 15 demo menu
      lines on purpose, so the "غير محدد" path is visible without breaking
      anything. 18 new tests, 362 passing.
      **Round 2 (same day) — rebuilt around PRODUCTS + RECIPES**, at the
      user's request and backed by the official guide. Reading
      `~/Downloads/الدليل المسطري...pdf` p.5 found this, on the regional
      committee that prepares the weekly program:
      *"إرفاق مكونات البرنامج الغذائي المعتمد بالتوزيع الكمي لمكونات الوجبات
      الغذائية"* — the approved program must be submitted WITH a quantity
      breakdown of each meal's components, respecting
      "الحاجيات الغذائية لكل فئة عمرية على حدة", and the contracted doctors
      sign it. So per-component quantities are an OFFICIAL requirement, not a
      UI nicety. The guide states the requirement but supplies no template and
      no figures (annex 5 holds only the reception PV, daily report and
      infraction PV — all already built), so the numbers still come from the
      user.
      New: `FoodProduct` (values against a BASIS — per 100g / per 100ml / per
      countable unit, because that is how labels state them) and
      `MealComponent` (how much of a product goes into a menu line), with
      `food_products` + `meal_components` tables and the editing UI extracted
      into `ui/nutrition_editor.py` (ProductLibraryPanel + RecipeEditorPanel)
      so neither file grew unmanageable.
      Resolution order per menu line: **recipe → whole-line value → unknown**
      (`resolve_dish`). The user chose to KEEP the old whole-line values as a
      fallback, so nothing entered in round 1 was lost; the week grid marks
      which of the two a number came from ("من المكونات" / "قيمة مباشرة").
      A recipe pointing at a deleted product returns None rather than a
      partial sum — but that cannot happen anyway, since deleting a product
      cascades its recipe lines away.
      **New document: `ui/nutrition_export.py` prints التوزيع الكمي** — one
      component table per composed meal with quantities, per-component
      calories and a meal total, signed by المدير / المسير / الطبيب المتعاقد
      معه. Meals with no components are OMITTED rather than printed empty.
      Two user decisions recorded: **one quantity set for everyone** (no
      per-cycle variants — the guide's "فئة عمرية" wording would have tripled
      data entry and they declined), and **build the export**.
      18 more tests (36 in the file), 399 passing.

- [x] **تقييم التلاميذ** (meal feedback) — `feedback_screen.py` +
      `core/feedback.py` + `data/feedback_repo.py`, built 2026-08-29. The last
      of the three features taken from the user's prototype.
      **The QR-code flow was NOT built** and should not be: it needs a web
      server reachable from pupils' phones, and this app is offline on one PC.
      That was explained to the user and accepted — ratings are ENTERED IN THE
      APP by the مسير or الحارس العام after a meal. Do not add the phone flow.
      Honesty rules, each with a test: a dish with no ratings has NO rating
      rather than a zero (`overall_average` returns None, never 0.0 — "nobody
      rated it" and "everyone rated it zero" are different claims); an invalid
      rating (0 or >5) is IGNORED rather than counted as the worst possible
      score; and every average is displayed WITH the number of opinions behind
      it, because 5.0 from one rating is not the claim 5.0 from twenty is.
      **`MIN_RATINGS_FOR_RANKING = 3`** — a dish needs at least three ratings
      before it can appear as most/least popular, so one five-star entry can
      never make something "the school's favourite". The panels say so in
      their own hint text.
      Ratings are grouped on the normalised dish name (same `normalize_dish`
      idea as التحليل الغذائي), the meal list follows the DATE's own meals so
      a rating cannot be filed against a meal that was never served (Ramadan
      days offer إفطار/سحور), and the dish is suggested from that day's weekly
      program so the name matches instead of being retyped slightly
      differently each time.
      Sidebar index 15 (الإعدادات shifted 15 → 16, every index re-verified by
      building MainWindow). Seeder records ~44 ratings across the last 30
      weekdays, weighted so some dishes genuinely outperform others and the
      ranking panels have real data. 19 new tests, 381 passing.
      **Round 2 (same day) — rebuilt around a RESPONSE COUNT PER LEVEL.** The
      user said the screen "needs more work"; checking the data showed the real
      flaw: a meal eaten by ~140 pupils carried exactly ONE recorded opinion
      (all 44 demo rows were 1-per-meal), so calling it تقييم التلاميذ
      overstated what it was — the prototype's QR code had just hidden the same
      flaw by implying many submissions arrived.
      Now each served meal records HOW MANY pupils gave each level
      (`count_excellent` … `count_bad`), which is collectable in practice — a
      show of hands, or slips at the door — and yields a genuinely weighted
      average plus a real response count. The five old single-`rating` rows are
      kept and read as exactly ONE response at that level (`response_counts`),
      so nothing earlier is lost or inflated; a row carrying counts ignores its
      legacy rating.
      Consequences carried through: `MIN_RATINGS_FOR_RANKING` now counts
      RESPONSES not rows (one row with 100 opinions can rank; three rows with
      one each still cannot), the summary card shows pupils not saved entries
      (a real bug caught by its own test — it was still showing `len(rows)`),
      and the counts are labelled تلميذ rather than تقييم.
      **New document: `ui/feedback_export.py`** — تقرير آراء التلاميذ for
      لجنة التتبع: period, overall average, per-meal averages, then every dish
      ranked with its average, its response count and its full distribution.
      Dishes with too few opinions are listed under their own heading rather
      than ranked. Row heights are MEASURED, after a first version let the
      distribution text spill out of the table — the same fixed-row-height trap
      as the staff cards.
      The user declined a period filter, quick entry, and linking a badly rated
      dish to محضر المخالفة. Do not add them unasked. 10 more tests (29 in the
      file), 409 passing.
      Round 3 (same day) — **how the opinions get collected**, in
      `ui/feedback_collect.py`. The user asked whether a QR/phone flow was
      possible. It is technically (Python's stdlib `http.server` needs no web
      framework, so §3 is not violated in letter), but they confirmed the
      pupils **have phones and NO usable WiFi reaching the office PC**, so it
      would have been built and never used. NOT BUILT — do not revisit without
      that changing.
      Built instead, both chosen by the user:
      · **ورقة تفريغ الآراء** — a landscape sheet listing every meal actually
        served in a chosen range (Ramadan-aware, with that day's planned dish)
        and five WIDE empty boxes per row to tally into. Someone marks it in
        the refectory, then types the five totals in.
      · **Excel round-trip** — the same rows as a workbook with EMPTY count
        columns, filled anywhere (including from a form's own export) and
        imported back. Reuses openpyxl; no new dependency.
      Import rules, each with a test: a row nobody filled in is SKIPPED and
      counted, never stored as a meal nobody liked; an unreadable or negative
      count is REPORTED, never guessed; a row with counts but no dish is
      refused with a message telling the user to write the dish (the column is
      editable); and **re-importing the same sheet updates the meal rather than
      doubling its counts** (`get_feedback_for` matches on date+meal+dish) —
      that is the most likely user mistake.
      Two bugs found by running the round-trip rather than reading it: the
      tally sheet's two-line date cell overflowed into the row below (now one
      line, column widened), and the import reported every UNTOUCHED row as
      "no dish name" because the dish check ran before the counts check —
      burying real problems in noise. 11 more tests (40 in the file),
      420 passing.
      **Round 4 (same day) — the unit became ONE DISH PER WEEK.** The user
      rejected the day-by-day shape outright ("those days you make i didn't
      like them") and asked to rate the WEEK'S MENU instead. They chose: one
      rating per dish per week (not one for the whole week), and the old
      per-day rows KEPT and shown separately.
      A week's menu has ~13 distinct dishes against 21 day-slots and a dish
      served twice is asked about once, so the collecting is roughly half the
      work and happens once a week. New `WeekFeedback` + `week_feedback` table
      (UNIQUE(week_start, dish)), and `week_start_of()` in core snaps any day
      to its Monday so two ratings for one week cannot disagree about which
      week that is. **Note: this is NOT the meal-program week field the user
      rejected earlier — different feature, and they asked for this one.**
      `WeekFeedback` deliberately carries the SAME count fields and `dish` as
      `MealFeedback`, so `summarize_by_dish` / `overall_average` /
      `most_popular` work on either with no special-casing; the screen feeds
      both into the averages and rankings. `average_by_meal_type` is the one
      exception — it now SKIPS records with no `meal_type` (a week rating
      covers a dish across the week and cannot be filed under فطور or غداء).
      That was a real crash, found by generating the report over both sources.
      The screen is now the week's whole menu in one editable table — a row per
      dish with its five count boxes, live per-dish responses/average and a
      week total — instead of a form submitted once per meal. The tally sheet
      and the Excel round-trip follow the same shape (one row per dish; the
      week is stored in cell B2 so the import knows which week the file is for
      and jumps the screen to it). A dish rated earlier but no longer on the
      menu keeps its row, or its numbers would silently vanish.
      One bug found by rendering: stale QSpinBox cell widgets from the previous
      render left a ghost "0" under every value — `clearContents()` before
      rebuilding, and a fixed row height instead of `resizeRowsToContents()`.
      Tests rewritten for the new shape; 41 in the file, 422 passing.
      **Round 5 (same day) — the REPORT.** The user called it weak and asked
      for KPIs, graphs, the school population (numbers, gender, class, age),
      and page 1 KEPT as it was. Page 1 is untouched; two pages follow it.
      · **Indicators + charts** — eight KPI boxes (overall average, responses,
        % positive (4-5) / % negative (1-2), dishes rated, opinions per pupil,
        best and worst dish), then three charts drawn with QPainter (no chart
        library, no new dependency): the response spread across the five
        levels, the average per WEEK as a zero-based column chart (a truncated
        axis makes a flat run look like a collapse), and per-dish averages.
      · **التلاميذ المستفيدون** — total, monitors, average age, class count,
        then bars by gender, cycle, class and AGE. Age comes from
        `Student.birth_date` via new pure `core/student_stats.py`.
      **`birth_date` is empty in the demo but filled 160/160 in the real
      database**, so the seeder now sets plausible ages; a roster with no dates
      prints "لم تُسجَّل تواريخ الازدياد" rather than an empty chart, and a
      pupil without one is counted under `unknown_age`, never given an age.
      Three layout bugs found by rendering, all the same family as before:
      bar VALUES were drawn inside the track and vanished under long bars (they
      now have their own column); the trend chart's values and labels sat half
      a slot right of their columns because `_text` defaults to right-aligned;
      and in the narrow half-width charts "52 تلميذ (35%)" wrapped and collided
      with the row below (the share is dropped when it does not fit on one
      line, measured not guessed).
      One real design flaw caught by a failing test: `_MAX_PLAUSIBLE_AGE` was
      30, which would have silently dropped the adult معلمو الداخلية — who are
      on the same roster and DO have birth dates in the real database — from
      the age chart. Raised to 75, still rejecting typo'd years.
      15 new tests (new `tests/test_student_stats.py`), 437 passing.
      **Round 6 (same day) — WHO gave the opinion.** The user asked to
      "make a link like student of this age like this meal or let's say the
      rank this or gender make patterns". They chose **by cycle AND gender**
      (6 groups) and to keep everything already recorded as **غير محدد**.
      Storage is a ROW PER GROUP, not 30 more columns: `WeekFeedback` gained
      `cycle` and `gender`, and the table's key widened from
      `UNIQUE(week_start, dish)` to `UNIQUE(week_start, dish, cycle, gender)`.
      **That constraint change needs a real migration, not an ALTER TABLE** —
      SQLite cannot widen a UNIQUE, so a database made before this keeps the
      old two-column key and every save then fails on a conflict target that
      matches nothing. `_widen_week_feedback_unique()` detects the old index
      and rebuilds the table, copying every row across (their cycle/gender stay
      blank). Covered by a test that builds the OLD schema by hand and checks
      the row survives.
      Collecting follows the same split: **choosing no group prints/exports
      ALL SIX** (one tally page-set per group, one Excel sheet per group), and
      choosing one exports just that one — the point of the paper route is one
      print run, not six clicks. The group is printed on the page and written
      into the sheet's D2, so a filled sheet knows where its numbers belong.
      **A sheet whose group name was hand-edited into something unrecognised is
      REFUSED, not filed under a guess** — the same standing boundary as the
      refused "randomise بيانات المصاريف" request.
      The report gained a 4th page, **من أبدى الرأي**: average per cycle and
      per gender (each bar labelled with that group's REAL AVERAGE AGE from the
      roster — that is what turns "تأهيلي rate it higher" into "the oldest
      pupils rate it higher"), the dishes the cycles and the genders most
      disagree about, and each group's favourite. `MIN_RESPONSES_FOR_PATTERN
      = 10` and a dish only ONE group rated is skipped entirely — that is
      missing collection, not a disagreement. Ungrouped opinions are counted
      and printed as excluded rather than quietly folded in.
      The group's age comes from `profile_by_cycle()`, which routes pupils
      through the app's own `student_category()` — so the roster and the
      feedback groups line up by construction instead of via a second mapping
      that could drift.
      Three fixes found by rendering, not reading: the two group charts were
      half-width and their labels wrapped into the row below (now full-width
      stacked); the rating bars were scaled to the largest bar present, turning
      3.66 vs 3.75 into a landslide (now scaled to 5 — `_bar_chart` gained a
      `maximum`); and the screen's own `_field_style()` was a bare property
      list, so the spin buttons drew as a detached bordered box beside every
      count cell (now real selectors). The two new combos deliberately carry
      NO stylesheet — `theme.py` already styles every combo in the app, and
      overriding it removed the arrow.
      Seeder now records all six groups with a real difference of taste, so
      the patterns page has something true to show on first run.
      25 new tests (71 in the file), 462 passing.

- [x] **Four Settings fields removed** (2026-08-29, at the user's request):
      **رمز GRESA** (`gresa_code`), **الحارس العام للداخلية**
      (`surveillant_general`), **Objet du marché** (`contract_object`) and the
      Arabic **اسم المزود** (`supplier_name`). Gone from `SchoolSettings`,
      `settings_repo`, the Settings screen and the setup wizard.
      **All four were BLANK in the real `matama.db`**, which is what made this
      safe — checked before touching anything, and it decided the one
      conditional the user attached ("الحارس العام — if his name is not used in
      any doc just delete it"): the field only ever pre-filled محضر المخالفة's
      عاين المخالفة box, and being empty it pre-filled nothing, so his name was
      on no document. That box is now typed in.
      The other three had live readers, all of which already fell through to
      something else because the fields were empty:
      · `contract_object` printed inside محضر التسلم اليومي's French legal
        sentence with a hardcoded fallback — now the constant
        `_CONTRACT_OBJECT_FR`, so the sentence is unchanged;
      · `supplier_name` printed on رسالة الطلبية as "المزود — الشركة" and was
        the second choice behind `company_name` on محضر التسلم اليومي/الشهري,
        محضر المخالفة and طاقم المطبخ — `company_name` is now the ONE company
        field everywhere.
      **Verified by generating every affected document from the real settings
      with the code before AND after, then diffing:** محضر التسلم اليومي (PDF
      *and* the .docx body), رسالة الطلبية, محضر المخالفة and بطاقات طاقم
      المطبخ all came back **byte-identical**. 462 tests still passing.
      The four DB columns are deliberately LEFT in place on existing databases
      (removed only from the migration list, so new databases never get them) —
      same reasoning as the retired `violations` table: dropping a column
      destroys whatever it holds, and nothing reads these any more.

- [x] **الإحصائيات المعمقة + وصول سريع** (2026-08-29). The user asked for
      "a page just for very deep statistics and KPIs and patterns" plus "a home
      page with quick access". **Both pages already existed** — يوم العمل is the
      home screen and الإحصائيات the statistics one — so after showing them what
      each already did, they chose to DEEPEN THE TWO rather than add a third and
      fourth competing for the same job. Menu stays at 7 rows.
      New `src/data/analytics_repo.py` (month/weekday/cycle aggregates, document
      coverage), new `src/core/analytics.py` (the arithmetic), new
      `src/ui/dashboard_deep.py` (the three sections — kept OUT of
      dashboard_screen.py, which was already 673 lines).
      Three sections, all chosen by the user:
      · **اتجاهات شهرية** — meals, days, per-day average and cost for every
        month with data, as a zero-based column chart plus a table.
      · **أنماط الغياب** — rate, worst weekday, and bars per weekday and per
        cycle. `worst_weekday` compares RATES, not counts: a weekday the school
        serves more often would otherwise always win.
      · **اكتمال الوثائق** — which of the five daily documents each served day
        has, per-document coverage bars, and the specific days still missing
        something (capped at 8, then counted).
      Plus **من أبدى الرأي** on screen at last — the cycle/gender feedback
      patterns with each group's real average age, which until now existed only
      inside the exported PDF.
      **A real bug caught before shipping it, by checking the numbers rather
      than trusting them:** the first trend used `get_monthly_summaries`, which
      hardcodes فطور/غداء/عشاء — so February and March (Ramadan) came back at
      3,552 and 2,242 meals against a true 5,608 and 5,203, and the chart showed
      a collapse that never happened. `get_monthly_meal_totals()` now counts
      EVERY meal type, netted per meal then floored (an absence on one meal must
      not cancel another's attendance). Since the user dropped Ramadan pricing
      (2026-08-25), those meals are counted but not costed, and the month is
      marked `cost_is_partial` with a footnote rather than printing a total that
      quietly understates it. ⚠️ **الملخص الشهري still has this bug** — flagged
      to the user, not fixed here, because it needs two decisions from them
      (Ramadan pricing, and the row layout).
      Honesty rules with tests: a month with no recorded days has NO average;
      an absence rate with nothing expected is None, not zero; and completeness
      counts ONLY days the school actually served — counting weekends and
      holidays as missing paperwork would make the number meaningless.
      **Also fixed, found by rendering the screen:** all four dashboard donut
      legends were drawn BELOW the widget's own bottom edge (the donut was
      centred in the full height and the legend placed after it), so every label
      was invisible and the colours meant nothing; and the fixed 80px legend
      stride ran wide labels off the card. Now the legend gets a reserved strip,
      widths are measured, it wraps to as many rows as it needs, and it packs
      right-to-left with each swatch on the right of its own label.
      **يوم العمل** gained a وصول سريع grid to the 11 pages that are not one of
      its five daily documents — it linked only to those five, and the lower
      half of the screen was empty.
      Round 2 (same day, from two screenshots): the user asked for the green
      school banner and the وصول سريع row to LEAVE الإحصائيات — the banner
      moved to يوم العمل, the quick row was deleted outright (يوم العمل's own
      grid replaces it), and `_build_welcome_panel`/`_build_quick_actions`/
      `_quick_button` are gone from dashboard_screen.py. On الإحصائيات the
      banner always showed TODAY; on يوم العمل it follows the DATE PICKER,
      since a banner reading "الأحد 30 غشت" above cards describing the 15th
      would be wrong. الإحصائيات now opens straight onto its KPI cards.
      Round 3 (same day, from a screenshot): **يوم العمل's five document cards
      rendered crushed to ~25px each**, title, status and buttons on top of
      one another. Same cause as the sidebar earlier the same day — the banner
      and the quick-access grid pushed the content to 934px in a 700px window,
      and `_PipelineCard` declared NO minimum height (0), so the QVBoxLayout
      was free to squeeze it to nothing. Fixed twice over: the screen is inside
      a QScrollArea, and a card now declares `_CARD_MIN_HEIGHT`.
      **Lesson: adding anything to a screen that already fills its height needs
      a render at WINDOW_MIN_HEIGHT (1100×700), not at a comfortable size — Qt
      does not warn, it just violates the minimums it was given.**
      Same round: **تقرير الإحصائيات** — `ui/dashboard_export.py`, a signed PDF
      of the page (headline figures, the monthly trend table, absence patterns,
      who rated what, document completeness), exported for the month selected
      in the deep panel via a تصدير التقرير button in a new page header. The
      drawing primitives are imported from `feedback_export.py` rather than
      copied — they already carry three fixes that each took a render to find.
      28 new tests, 496 passing.
      Round 4 (same day, from a sidebar screenshot): three small user requests —
      the stray "M" prefix on the sidebar's school title is gone (it was a
      hardcoded `f"M  {…}"`, not initials of anything); **يوم العمل was renamed
      الصفحة الرئيسية** everywhere in `src/` and `tests/` (the file keeps its
      name); and **التلاميذ حسب القسم** was added to الإحصائيات and to the
      exported report — every class with its own ذكور/إناث split and a
      المجموع العام row. New `breakdown_by_class()` in core/student_stats.py
      orders classes through the app's own `student_category` rather than by
      parsing "الأولى"/"الثانية" out of a name the school typed into Excel; a
      pupil with no recorded gender is counted and reported separately, never
      assigned to one of the two columns. The report's table is built from the
      SCREEN's own row builder, so the two can never disagree.
      Round 5 (same day): the user asked for that class table to be **a graph**
      — it is now a stacked bar per class (ذكور green, إناث purple, غير محدد
      grey), each segment carrying its own number INSIDE it when it is wide
      enough to hold one, measured with QFontMetrics so a narrow segment drops
      its label rather than spilling over its neighbour. Bars are scaled to the
      largest class, so their lengths compare across rows; the total sits in
      its own column where no bar can cover it. Drawn the same way on screen
      and in the PDF, from the same `class_chart_rows()`. The table builder it
      replaced was deleted rather than left as dead code.
      36 new tests, 504 passing.

- [x] **Setup wizard remade** (2026-08-29) — `setup_wizard.py` +
      new `setup_steps.py`. The user asked for a remake "considering what needs
      modification", so it was audited first. Two things checked and found
      FINE: the four deleted Settings fields were already gone from it, and the
      level picker's `Liste_internes.xlsx` really does ship in the packaged
      build (in `Matama.spec`'s datas, present in `dist/`).
      Four real problems, all fixed:
      · **The Ramadan fields were backwards.** It asked for three Ramadan
        PRICES — dropped by the user on 2026-08-25, read by nothing — and never
        asked for the Ramadan DATES, which every document reads to decide
        whether a day serves إفطار/سحور. Prices removed, `مدة رمضان` added
        behind a checkbox ("مؤسستي تقدّم وجبات رمضان"), so an untouched wizard
        never writes a period nobody meant.
      · **It ended in an empty app.** Three new SKIPPABLE steps: import
        لائحة التلاميذ from Excel (same reader لائحة التلاميذ uses), record
        العطل as date ranges, and type the first weekly menu. Every one says on
        the page that it is optional — setup must never become a wall a
        beginner cannot get past.
      · **Prices were not validated.** "12,50" or a typo saved as text and then
        read as 0.00 in every cost figure downstream, silently. Refused now,
        naming the field; a BLANK price is still allowed, because not knowing a
        price yet is normal and nonsense is not.
      · **No sense of progress.** Six numbered chips across the header, and a
        final **تم الإعداد** page that reports what was saved AND what was left
        empty — a summary listing only successes would hide the gaps.
      Settings are now written when LEAVING step 2, not at the very end: every
      step after it is optional, and someone who closes the window on one
      should still keep the identity they typed.
      Guards worth keeping: a holiday range that ends before it starts, or runs
      longer than 120 days (a mistyped year), or carries no reason, is refused
      rather than writing thousands of rows; an untouched menu grid creates no
      program at all, since an empty slot means "not served", not "a meal with
      no name".
      **The wizard had NO tests before this** — 21 new ones in a new
      `tests/test_setup_wizard.py`. 525 passing.

### 📋 Not started
- Nothing outstanding from the prototype. The remaining ideas in it were
  discussed with the user on 2026-08-29 and NOT chosen: المخزون (stock),
  التتبع المالي (budget ledger), الأرشيف (document archive), التقارير الدورية,
  and the pipeline blocking/prerequisites idea for يوم العمل. The user picked
  طاقم المطبخ only from that list, then added التحليل الغذائي and
  تقييم التلاميذ. Do not build the others without being asked.

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

🚫 **Never "improve" what a template does — reproduce it.** Standing
instruction from the user (2026-08-25): *"always respect what is in the
template until I tell you so."* These are the official documents their
administration accepts, so a difference that looks like a fix to us reads
as a wrong document to whoever receives it. That includes things that
genuinely look like human slips — odd article numbering, an inconsistent
highlight, a spelling — reproduce them anyway and, if it seems worth
changing, ASK rather than deciding. The only things to fill in are the
blanks the template is asking for (a dotted line for the school name is a
placeholder, not a deviation). Deviating requires the user to say so
first, and any deviation still in the code must be listed explicitly to
them, never left silent.

🚫 **Never `git checkout` a file under `templets/` to "restore" it because it looks broken (missing fields, edited text).** These are the user's real Word templates, hand-edited directly in LibreOffice/Word as part of their own workflow — a restore silently discards that editing. If a template's structure changed, make the fill code adapt to the new structure instead. Only restore a template file if the user explicitly asks for it. (This happened with `templets/المحضر اليومي لتسلم الخدمة.docx` — see CLAUDE.md §7's محضر التسلم اليومي entry and `AI_HANDOFF.md`.)

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

### 2026-09-01 — setup cycle choices now control data-entry screens

The setup wizard's selected school cycles are now operational, not decorative.
If the user selects only الثانوي الإعدادي, the primary and qualifying rows are
hidden from the daily contact, daily absence, order-letter, daily-report and
student-feedback screens. معلمو الداخلية remains visible because it is staff,
not a school cycle. Official printed templates are deliberately unchanged and
retain all required rows. Safety rule: any cycle with existing non-zero daily
data is always shown even when it is unticked, so saved numbers can never become
invisible. No selected cycle preference means all three cycles remain visible
for old installations. The absence history table follows the same filter; its
unused columns are removed, not merely left empty. The shared rule lives in
`core/active_cycles.py`; the SQL evidence query lives in
`data/students_repo.py`. 533 tests plus 9 subtests.

### 2026-09-01 — pre-release diagnostic and cleanup

The full release audit found and fixed two real Ramadan under-counts: the
daily-report detail tables hardcoded the normal three meals, and the monthly
summary omitted Ramadan rows entirely. Both now use the date/month's real meal
types. Monthly إفطار/سحور are counted but remain unpriced (0.00), preserving
the user's standing “ignore Ramadan pricing” decision. Ordinary months do not
gain empty Ramadan rows. The monthly page also reloads fresh data without
discarding unsaved notes.

Other release fixes: SQLite's backup API replaces raw file copying; malformed
QGroupBox CSS and unsupported `box-sizing` were removed; deprecated Qt table
alignment calls were updated; all 17 screens now open with zero stylesheet
errors; PyInstaller now produces one portable file; runtime resource paths
support one-file extraction; unused pandas was removed; and a Windows GitHub
Actions build/release workflow was added. Final source result: 538 tests plus
9 subtests, no warnings. The Linux one-file smoke build is 86 MB and starts
successfully; the real Windows `.exe` must be produced by the Windows workflow.
