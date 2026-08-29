"""When a kitchen worker's شهادة طبية needs renewing.

A valid medical certificate is a contractual requirement for anyone handling
food, and the school is the party expected to check it — so the whole point of
the staff screen is noticing an expiry BEFORE it lapses, not after.

Pure logic, no Qt and no Arabic: the labels and colours live in ui/.
"""
import datetime
from typing import Optional

# How long before the expiry date a certificate starts being flagged. A month
# is roughly how long renewing one takes in practice.
EXPIRY_WARNING_DAYS = 30

STATE_MISSING = "missing"    # no date recorded at all
STATE_EXPIRED = "expired"    # the date has passed
STATE_EXPIRING = "expiring"  # within EXPIRY_WARNING_DAYS
STATE_VALID = "valid"


def parse_iso_date(value: str) -> Optional[datetime.date]:
    """A date from an ISO string, or None for blank/garbage.

    Values come from the database and from Qt widgets, and a member whose
    certificate was never recorded stores an empty string, so this must never
    raise.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def days_until_expiry(expiry: str, today: datetime.date) -> Optional[int]:
    """Days remaining, negative once the date has passed, None if unknown."""
    day = parse_iso_date(expiry)
    if day is None:
        return None
    return (day - today).days


def certificate_state(expiry: str, today: datetime.date) -> str:
    """One of the STATE_* constants for a certificate's expiry date.

    Expiry day itself still counts as valid — a certificate is good through
    the end of the day it names.
    """
    remaining = days_until_expiry(expiry, today)
    if remaining is None:
        return STATE_MISSING
    if remaining < 0:
        return STATE_EXPIRED
    if remaining <= EXPIRY_WARNING_DAYS:
        return STATE_EXPIRING
    return STATE_VALID


def needs_attention(expiry: str, today: datetime.date) -> bool:
    """True for anything the user should act on — missing, expiring or expired."""
    return certificate_state(expiry, today) != STATE_VALID
