"""Which school cycles this school actually uses.

A school that only runs an إعدادي section had to type 0 into the ابتدائي and
تأهيلي rows of every meal, on every daily form, every day. This module answers
"which cycle rows should a data-entry screen show?" so those rows can be left
out.

Two rules, and the second one is the important one:

  1. The answer follows the المستويات المستعملة the user ticked in the wizard
     or in الإعدادات. Nothing ticked means "all of them" — a school that never
     opened that screen must not suddenly lose rows.

  2. A cycle that ALREADY HAS DATA is always shown, whatever the ticks say.
     Hiding a row whose numbers are already saved would strand them: invisible
     on screen, still counted in every total and every document. Ticking the
     wrong box must never be able to do that.

DOCUMENTS ARE NOT FILTERED BY THIS. The printed ورقة الاتصال and its siblings
reproduce their ministry template row for row, zeros included — CLAUDE.md §9,
and the user confirmed it again on 2026-08-29. This is for screens only.

Pure logic plus repository reads: no Qt, no Arabic (labels live in ui/).
"""
from typing import Dict, List, Optional, Set

from core.contact_counts import (
    CATEGORY_COLLEGIAL, CATEGORY_MONITORS, CATEGORY_PRIMARY,
    CATEGORY_QUALIFYING,
)

# The three school cycles, in the order every form lists them. معلمو الداخلية
# is deliberately NOT here: they are staff, not a cycle, and every school with
# an internat has them.
SCHOOL_CYCLES: tuple = (CATEGORY_PRIMARY, CATEGORY_COLLEGIAL,
                        CATEGORY_QUALIFYING)

def _normalize(text: str) -> str:
    """Strip the hamza variants so "الإعدادي" and "الاعدادي" match."""
    return (text or "").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")


def cycle_from_label(label: str) -> Optional[str]:
    """Map a catalog cycle LABEL ("الإعدادي") to the app's own category code.

    The labels come from the level workbook the school imported, so they are
    matched loosely — the same way core.contact_counts classifies a pupil.
    """
    normalized = _normalize(label)
    if "ابتدائي" in normalized:
        return CATEGORY_PRIMARY
    if "اعدادي" in normalized:
        return CATEGORY_COLLEGIAL
    if "تاهيلي" in normalized:
        return CATEGORY_QUALIFYING
    return None


def chosen_cycles(preferences: Dict) -> Set[str]:
    """The cycles the user ticked, as category codes.

    An empty set means NOTHING was ticked, which the caller reads as "show
    everything" — never as "show nothing".
    """
    codes = set()
    for label in preferences.get("cycles", []) or []:
        code = cycle_from_label(str(label))
        if code:
            codes.add(code)
    return codes


def cycles_with_data() -> Set[str]:
    """Cycles that already have a non-zero count saved anywhere.

    These stay visible no matter what is ticked — see rule 2 above.
    """
    from data.database import get_cycles_with_daily_data
    return get_cycles_with_daily_data()


def visible_cycles(preferences: Optional[Dict] = None) -> List[str]:
    """The cycle rows a data-entry screen should show, in form order."""
    if preferences is None:
        from data.database import get_level_preferences
        preferences = get_level_preferences()

    chosen = chosen_cycles(preferences)
    if not chosen:
        return list(SCHOOL_CYCLES)          # nothing ticked = the school uses all
    keep = chosen | cycles_with_data()
    return [cycle for cycle in SCHOOL_CYCLES if cycle in keep]


def is_visible(cycle: str, preferences: Optional[Dict] = None) -> bool:
    return cycle in visible_cycles(preferences)
