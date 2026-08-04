# Document specifications

One section per official document. Each says: what feeds it, what it holds,
what it produces, and who signs it.

Every printed document starts with the **school header** (school name, city,
academy / AREF, provincial directorate, school year) taken from the setup
wizard settings, and ends with a **signature block** using the role labels
from `SKILL.md` section 1.

## Contents

1. [roster_status](#1-roster_status)
2. [contact_sheet](#2-contact_sheet)
3. [order_letter](#3-order_letter)
4. [absence_sheet](#4-absence_sheet)
5. [daily_report](#5-daily_report)
6. [daily_reception_record](#6-daily_reception_record)
7. [infraction_record](#7-infraction_record)
8. [monthly_expense_statement](#8-monthly_expense_statement)
9. [monthly_reception_record](#9-monthly_reception_record)

---

## 1. roster_status
**ÙØ¶Ø¹ÙØ© Ø§ÙØªÙØ§ÙÙØ° Ø§ÙØ¯Ø§Ø®ÙÙÙÙ**

Feeds everything else. Build this first.

Per student: full name, class, birth date, birth place, grant number,
`cycle` (`MIDDLE`/`HIGH`), `benefit_type` (`GRANTED`/`PAYING`/`SUPPLEMENTARY`),
`scholarship_scope` (`FULL_GRANT`/`LUNCH_ONLY`), `roster_state`
(`RETURNING`/`NEW`/`NOT_JOINED`/`LEFT`).

Import from Excel (Massar / ÙØ³Ø§Ø± export). Column names differ between exports,
so the importer must show a **mapping screen** â the user picks which spreadsheet
column is which field â and remember the mapping for next time.

Output: a table grouped by `roster_state` with a count per group, plus the
active total.

Signatures: WARDEN, HEADMASTER.

---

## 2. contact_sheet
**ÙØ±ÙØ© Ø§ÙØ§ØªØµØ§Ù Ø§ÙÙÙÙÙØ© ÙÙÙÙÙØ¬ ÙÙÙØ·Ø¹Ù**

The daily starting point. One row per `(date, meal)` â unique.

Holds, for one meal on one date, the expected count broken down by:

- `MIDDLE` Ã (`GRANTED` / `PAYING` / `SUPPLEMENTARY`)
- `HIGH` Ã (`GRANTED` / `PAYING` / `SUPPLEMENTARY`)
- `internal_teachers`

Plus the computed total. See `calculations.md` Â§1.

The default counts are pre-filled from `roster_status` so the user only edits
the exceptions. This is the single biggest time-saver in the whole app â do not
make the user type all seven numbers every morning.

Signatures: HEADMASTER, STEWARD, WARDEN — corrected from the original
WARDEN/HEADMASTER-only note after checking the real accepted template
(`templets/ورقة الاتصال  اليومية.docx`), which has all 3 signature lines.

---

## 3. order_letter
**Ø±Ø³Ø§ÙØ© Ø§ÙØ·ÙØ¨ÙØ© Ø§ÙÙÙÙÙØ©**

Generated from the `contact_sheet` of the day plus the approved weekly meal
program. Sent to the contractor.

**No time rule.** The user has excluded the 18:00 deadline â do not build a
cutoff, a countdown, or a warning.

If counts change after sending, the user creates a **modified order letter**
(Ø±Ø³Ø§ÙØ© Ø·ÙØ¨ÙØ© ÙØ¹Ø¯ÙØ©) â a new version linked to the original, never an edit of it.
Keep both; the monthly file needs the trail.

Signatures: STEWARD, HEADMASTER.

---

## 4. absence_sheet
**ÙØ±ÙØ© Ø§ÙØºÙØ§Ø¨ Ø§ÙÙÙÙÙ ÙÙÙØ·Ø¹Ù**

Same breakdown as the contact sheet, but counting who did **not** show up.
One row per `(date, meal)` â unique. Only created when there is an absence.

Triggers the portion redistribution rule â see `calculations.md` Â§2.

Signatures: WARDEN.

---

## 5. daily_report
**Ø§ÙØªÙØ±ÙØ± Ø§ÙÙÙÙÙ ÙÙÙØµØ§ÙØ­ Ø§ÙÙØ§Ø¯ÙØ© ÙØ§ÙÙØ§ÙÙØ©**

An inspection checklist, not a count. Fields:

- **Hygiene** (Ø§ÙÙØ¸Ø§ÙØ©): staff, utensils, kitchen, stores, grease trap
- **Meal quality** (Ø§ÙÙØ¬Ø¨Ø§Øª): temperature, gramage, cooking, timing,
  individual distribution
- **Building and equipment** (Ø§ÙØ¨ÙØ§ÙØ© ÙØ§ÙØªØ¬ÙÙØ²Ø§Øª): damage, maintenance needed
- Free notes field

Each item is rated. `CONFIRM:` what scale â pass/fail, or a 1â5 rating?

If any item fails, the app offers to create an `infraction_record` from it,
pre-filled. That link is the point of this screen.

Signatures: STEWARD, HEADMASTER.

---

## 6. daily_reception_record
**ÙØ­Ø¶Ø± ØªØ³ÙÙ Ø§ÙØ®Ø¯ÙØ© Ø§ÙÙÙÙÙ**

Confirms the meals were delivered and accepted. One per `(date, meal)`.
**Printed in two identical copies (ÙÙ ÙØ¸ÙØ±ÙÙ)** â the PDF export must produce
two pages, or two copies on one page.

Holds: date, meal, delivered quantity, accepted quantity, remarks.

Signatures: STEWARD, HEADMASTER, CONTRACTOR.

---

## 7. infraction_record
**ÙØ­Ø¶Ø± Ø§ÙÙØ®Ø§ÙÙØ©**

Created only when a breach is found. Fields: date, meal concerned, infraction
type, description, who reported.

**No money.** This document records what happened; it does not compute a
deduction. See `calculations.md` Â§3.

Signatures: STEWARD, WARDEN, HEADMASTER, CONTRACTOR.

---

## 8. monthly_expense_statement
**Ø¨ÙØ§Ù Ø§ÙÙØµØ§Ø±ÙÙ Ø§ÙØ´ÙØ±Ù** (RelevÃ© des dÃ©penses)

Aggregates the month's actual attendance, meal by meal, day by day.
Cross-checks against the daily reception records â the app must **flag any day
where the two disagree** rather than silently picking one.

Money math in `calculations.md` Â§4.

Signatures: WARDEN, STEWARD.

---

## 9. monthly_reception_record
**ÙØ­Ø¶Ø± ØªØ³ÙÙ Ø§ÙØ®Ø¯ÙØ© Ø§ÙØ´ÙØ±Ù** (ProcÃ¨s-verbal de rÃ©ception mensuel)

The final official form sent to the provincial directorate / AREF, together
with the expense statement, the daily records and any infraction records.

**Printed in two copies.** The layout must match the official ministry form.
`CONFIRM:` the user should supply a scan or blank copy of the official form so
the PDF layout matches exactly.

Signatures: STEWARD, HEADMASTER.
