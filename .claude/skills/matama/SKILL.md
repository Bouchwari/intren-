---
name: matama
description: Domain knowledge and build rules for the Matama System (Ù†Ø¸Ø§Ù… Ø§Ù„Ù…Ø·Ø¹Ù…Ø©) â€” the offline PySide6 desktop app that produces official Moroccan school cafeteria paperwork. Use this skill for ANY work on this project, even small ones: adding or fixing a screen, writing a database table, counting beneficiaries, generating a document (ÙˆØ±Ù‚Ø© Ø§Ù„Ø§ØªØµØ§Ù„ØŒ Ø±Ø³Ø§Ù„Ø© Ø§Ù„Ø·Ù„Ø¨ÙŠØ©ØŒ Ù…Ø­Ø¶Ø± Ø¨ÙŠØ§Ù† Ø§Ù„Ù…ØµØ§Ø±ÙŠÙ), naming a variable, exporting PDF or Excel, or answering a question about how the cafeteria process works. Also use it when the user speaks Arabic about the app, mentions Ø§Ù„ØªÙ„Ø§Ù…ÙŠØ° Ø§Ù„Ø¯Ø§Ø®Ù„ÙŠÙˆÙ†ØŒ Ø§Ù„Ù…Ù†Ø­ØŒ Ø§Ù„ÙˆØ¬Ø¨Ø§ØªØŒ Ø§Ù„ØºØ±Ø§Ù…Ø§ØªØŒ or asks "where does this code go".
---

# Matama System â€” domain and build rules

This project automates the paperwork of a Moroccan public-school cafeteria
(Ø§Ù„Ø¥Ø·Ø¹Ø§Ù… Ø§Ù„Ù…Ø¯Ø±Ø³ÙŠ). `CLAUDE.md` holds the stack and coding rules. **This skill
holds the business rules** â€” what the documents are, how numbers are counted,
and what words map to what code identifiers.

Read `CLAUDE.md` first. If this skill and `CLAUDE.md` disagree, ask the user.

---

## 1. The one rule that matters most

**One user.** The app is used by a single person on one Windows PC, offline.
There is **no login, no accounts, no permissions system**.

The four roles below exist only as **printed signature labels** on documents:

| Role | Arabic | Signs |
|---|---|---|
| `WARDEN` | Ø§Ù„Ø­Ø§Ø±Ø³ Ø§Ù„Ø¹Ø§Ù… Ù„Ù„Ø¯Ø§Ø®Ù„ÙŠØ© | contact sheet, absence sheet, monthly expense statement |
| `STEWARD` | Ù…Ø³ÙŠØ± Ø§Ù„Ù…ØµØ§Ù„Ø­ Ø§Ù„Ù…Ø§Ø¯ÙŠØ© ÙˆØ§Ù„Ù…Ø§Ù„ÙŠØ© | order letter, daily report, reception records |
| `HEADMASTER` | Ù…Ø¯ÙŠØ± Ø§Ù„Ù…Ø¤Ø³Ø³Ø© | approves everything |
| `CONTRACTOR` | Ù…Ù…Ø«Ù„ Ø§Ù„Ø´Ø±ÙƒØ© Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© | reception records, infraction records |

Never build a users table, a login screen, or a permission check.

---

## 2. Vocabulary â€” Arabic to code

Use these exact English identifiers everywhere in code. Never invent a synonym.
Never write the Arabic in `core/` or `data/` â€” Arabic belongs only in `ui/`.

### Cycle (Ø§Ù„Ø³Ù„Ùƒ) â€” three, not two

The existing database uses these exact prefixes. Do not rename them.

| Arabic | Identifier | Columns in `daily_contact` / `daily_absence` |
|---|---|---|
| Ø§Ø¨ØªØ¯Ø§Ø¦ÙŠ | `primary` | `primary_granted`, `primary_complement` |
| Ø¥Ø¹Ø¯Ø§Ø¯ÙŠ | `collegial` | `collegial_granted`, `collegial_paying`, `collegial_complement` |
| ØªØ£Ù‡ÙŠÙ„ÙŠ | `qualifying` | `qualifying_granted`, `qualifying_paying`, `qualifying_complement` |

`CONFIRM:` `primary` has no `paying` column while the other two do. Is that
correct â€” do primary pupils never pay? Ask before changing any count.

Ù…Ø¹Ù„Ù…Ùˆ Ø§Ù„Ø¯Ø§Ø®Ù„ÙŠØ© use `monitors` and `monitors_complement`.

### Grant type (Ù†ÙˆØ¹ Ø§Ù„Ù…Ù†Ø­Ø©) â€” only two exist

The user confirmed there are **exactly two** live categories. Do not invent more.

| Arabic | Identifier | Covers |
|---|---|---|
| Ù…Ù†Ø­Ø© ÙƒØ§Ù…Ù„Ø© | `FULL_GRANT` | all meals of the day |
| ÙˆØ¬Ø¨Ø© ØºØ¯Ø§Ø¡ | `LUNCH_ONLY` | lunch only |

âš ï¸ **Legacy columns.** The database still has `collegial_paying` and
`qualifying_paying` (Ù…Ø¤Ø¯ÙŠ). These are **retired**. `models.py` marks them
"Ù‚Ø¯ÙŠÙ…: Ù…Ø¤Ø¯ÙŠØŒ ÙŠØ¯Ù…Ø¬ ÙÙŠ Ù…Ù†Ø­Ø© ÙƒØ§Ù…Ù„Ø©" and the UI merges them into the granted count
when loading old rows. Keep them so old data still adds up. Never write a new
value into them, never show them in a new screen, and never add a
`primary_paying` column.

### Roster state (ÙˆØ¶Ø¹ÙŠØ© Ø§Ù„ØªÙ„Ø§Ù…ÙŠØ° Ø§Ù„Ø¯Ø§Ø®Ù„ÙŠÙˆÙ†)

Set at the start of the year, then updated as the year goes on.

| Arabic | Identifier | When |
|---|---|---|
| Ø§Ù„Ù…ÙˆÙ†ÙˆØ­ÙŠÙ† Ø§Ù„Ù‚Ø¯Ø§Ù…Ù‰ | `RETURNING` | opening the year |
| Ø§Ù„Ù…ÙˆÙ†ÙˆØ­ÙŠÙ† Ø§Ù„Ø¬Ø¯Ø¯ | `NEW` | opening the year |
| ØºÙŠØ± Ø§Ù„Ù…Ù„ØªØ­Ù‚ÙŠÙ† | `NOT_JOINED` | update â€” never showed up |
| Ø§Ù„Ù…ØºØ§Ø¯Ø±ÙŠÙ† | `LEFT` | update â€” left during the year |

```
active = (RETURNING + NEW) - (NOT_JOINED + LEFT)
```

The `students` table has **no column for this yet**. It must be added.

### Meals (Ø§Ù„ÙˆØ¬Ø¨Ø§Øª)

| Arabic | Identifier | Season |
|---|---|---|
| ÙØ·ÙˆØ± | `BREAKFAST` | normal |
| ØºØ¯Ø§Ø¡ | `LUNCH` | normal |
| Ø¹Ø´Ø§Ø¡ | `DINNER` | normal + Ramadan |
| Ø¥ÙØ·Ø§Ø± | `IFTAR` | Ramadan only |
| Ø³Ø­ÙˆØ± | `SUHOOR` | Ramadan only |

A day is either a normal day (`BREAKFAST/LUNCH/DINNER`) or a Ramadan day
(`IFTAR/DINNER/SUHOOR`). Never mix both in the same day.

### Other

| Arabic | Identifier |
|---|---|
| Ù…Ø¹Ù„Ù…Ùˆ Ø§Ù„Ø¯Ø§Ø®Ù„ÙŠØ© | `internal_teachers` |
| Ø§Ù„Ø´Ø±ÙƒØ© Ø§Ù„Ù‚Ø§Ø¦Ù…Ø© | `contractor` |
| Ø§Ù„Ù‚ÙŠÙ… Ø§Ù„ØºØ°Ø§Ø¦ÙŠ | `daily_food_value` |

---

## 3. Documents the app must produce

The documents form a **dependency chain**, and the product goal is one button
that generates all of them. **Read `references/document_chain.md` before touching
any document code** â€” the architecture depends on it.

Field-by-field specs are in `references/documents.md`.

Short list, with the code name to use:

| Arabic | Code name | When |
|---|---|---|
| ÙˆØ¶Ø¹ÙŠØ© Ø§Ù„ØªÙ„Ø§Ù…ÙŠØ° Ø§Ù„Ø¯Ø§Ø®Ù„ÙŠÙˆÙ† | `roster_status` | start of year, updated on changes |
| ÙˆØ±Ù‚Ø© Ø§Ù„Ø§ØªØµØ§Ù„ Ø§Ù„ÙŠÙˆÙ…ÙŠØ© | `contact_sheet` | every morning |
| Ø±Ø³Ø§Ù„Ø© Ø§Ù„Ø·Ù„Ø¨ÙŠØ© Ø§Ù„ÙŠÙˆÙ…ÙŠØ© | `order_letter` | daily, **must be sent before 18:00** |
| ÙˆØ±Ù‚Ø© Ø§Ù„ØºÙŠØ§Ø¨ Ø§Ù„ÙŠÙˆÙ…ÙŠ | `absence_sheet` | daily, only when someone is absent |
| Ø§Ù„ØªÙ‚Ø±ÙŠØ± Ø§Ù„ÙŠÙˆÙ…ÙŠ | `daily_report` | daily |
| Ù…Ø­Ø¶Ø± ØªØ³Ù„ÙŠÙ… Ø§Ù„Ø®Ø¯Ù…Ø© Ø§Ù„ÙŠÙˆÙ…ÙŠ | `daily_reception_record` | daily, printed in 2 copies |
| Ù…Ø­Ø¶Ø± Ø§Ù„Ù…Ø®Ø§Ù„ÙØ© | `infraction_record` | only when a breach is found |
| Ø¨ÙŠØ§Ù† Ø§Ù„Ù…ØµØ§Ø±ÙŠÙ Ø§Ù„Ø´Ù‡Ø±ÙŠ | `monthly_expense_statement` | end of month |
| Ù…Ø­Ø¶Ø± ØªØ³Ù„ÙŠÙ… Ø§Ù„Ø®Ø¯Ù…Ø© Ø§Ù„Ø´Ù‡Ø±ÙŠ | `monthly_reception_record` | end of month, sent to the directorate |

---

## 4. Calculations

All counting, redistribution, penalty and billing formulas are in
`references/calculations.md`. **Read it before writing any function that
produces a number.**

Hard rules that apply everywhere:

- Money is stored in **centimes as `int`**, never as `float`. Format to dirhams
  only in `ui/`.
- Every count function lives in `core/`, takes plain data, returns plain data,
  and has a unit test. Never compute inside a PySide6 widget.
- Never let a count be negative. Clamp at zero and log a warning.

---

## 4b. How the app must look

The user rejected the current cold navy/slate look. The replacement palette,
typography, RTL rules and shared widgets are in `references/ui_design.md`.
**Read it before writing any UI code.** Never invent a colour or a font size.

## 5. Where code goes

Before writing anything, place each piece:

| Piece | Layer |
|---|---|
| A screen, dialog, table view, Arabic label | `src/ui/` |
| A counting rule, a penalty formula, a validation rule | `src/core/` |
| A SQL query, an Excel read/write, a PDF write | `src/data/` |
| A constant, a path, a colour, a unit price key | `config/settings.py` |

If a piece does not fit clearly in one layer, **stop and ask the user.**

---

## 6. Workflow for every task

1. Say the plan in 2â€“3 sentences.
2. List the files you will touch and the layer of each.
3. If it touches more than 3 files, wait for "go".
4. Read each existing file before editing it.
5. Edit only the function that needs changing â€” never rewrite a whole file to
   fix one part.
6. After the code, give the user a short **click-through test**: the exact
   buttons to press and the exact result to expect. The user is a beginner and
   tests by clicking, not by reading code.

---

## 7. Things that are easy to get wrong here

- **The empty case.** No students imported yet, no meal program for today, no
  settings saved. Every screen must show a helpful Arabic message plus a button,
  not a crash and not a blank table.
- **One row per (date, meal).** Contact sheet, absence sheet and reception record
  are unique per date and meal. Enforce this with a database constraint, not only
  in the UI.
- **Dates.** Store as ISO `YYYY-MM-DD` text in SQLite. Display in the user's
  format only in `ui/`.
- **Ramadan.** Any date-based logic must handle a Ramadan day having different
  meal names.
- **A document once signed is history.** Changing a past contact sheet changes a
  monthly total that may already have been sent. Warn before editing anything
  older than today.

---

## 8. When the rules are unclear

This skill was written from the user's own process document. Some details were
inferred. If a rule here contradicts what the user knows from the official
ministry guide, **the user is right** â€” ask, then update this skill file.

Anything marked `CONFIRM:` in the reference files has not been verified yet.
Ask the user before relying on it.
