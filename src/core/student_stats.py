"""Who the school's beneficiaries are — counts by gender, cycle, class and age.

Used to give the feedback report its context: "4,056 opinions" means something
different in a school of 40 than in one of 400.

Nothing is estimated. A pupil with no recorded birth date is counted under
`unknown_age` rather than being given a plausible one, and a blank gender or
cycle is reported as blank rather than guessed from the name or the class.

Pure logic: no Qt, no database, no Arabic (labels live in ui/).
"""
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from core.models import Student

GENDER_MALE = "male"
GENDER_FEMALE = "female"
UNKNOWN = ""

# Wide enough to include the adult معلمو الداخلية, who are on the same roster
# and do have birth dates — capping at a pupil's age would have silently
# dropped real staff from the chart. Still narrow enough that a typo'd year
# (1900 → age 126) is rejected rather than stretching the axis to nonsense.
_MIN_PLAUSIBLE_AGE = 3
_MAX_PLAUSIBLE_AGE = 75


def parse_iso_date(value: str) -> Optional[datetime.date]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def age_on(birth_date: str, today: datetime.date) -> Optional[int]:
    """Age in whole years, or None when it is unknown or implausible."""
    born = parse_iso_date(birth_date)
    if born is None:
        return None
    years = today.year - born.year - (
        (today.month, today.day) < (born.month, born.day))
    if years < _MIN_PLAUSIBLE_AGE or years > _MAX_PLAUSIBLE_AGE:
        return None
    return years


@dataclass
class StudentStats:
    """A roster summarised. Every dict is label → count."""
    total: int = 0
    by_gender: Dict[str, int] = field(default_factory=dict)
    by_cycle: Dict[str, int] = field(default_factory=dict)
    by_class: Dict[str, int] = field(default_factory=dict)
    by_section: Dict[str, int] = field(default_factory=dict)
    by_grant: Dict[str, int] = field(default_factory=dict)
    by_age: Dict[int, int] = field(default_factory=dict)
    unknown_age: int = 0
    monitors: int = 0

    @property
    def has_ages(self) -> bool:
        """False when no pupil has a usable birth date — the report says so
        instead of printing an empty chart."""
        return bool(self.by_age)

    @property
    def average_age(self) -> Optional[float]:
        if not self.by_age:
            return None
        total = sum(age * count for age, count in self.by_age.items())
        return total / sum(self.by_age.values())


def _bump(bucket: Dict, key) -> None:
    bucket[key] = bucket.get(key, 0) + 1


def summarize_students(students: Sequence[Student],
                       today: datetime.date) -> StudentStats:
    """Count a roster every way the report needs it, in one pass."""
    stats = StudentStats(total=len(students))
    for student in students:
        if getattr(student, "is_monitor", False):
            stats.monitors += 1
        _bump(stats.by_gender, (student.gender or UNKNOWN).strip())
        _bump(stats.by_cycle, (student.cycle or UNKNOWN).strip())
        _bump(stats.by_class, (student.student_class or UNKNOWN).strip())
        _bump(stats.by_section, (student.section or UNKNOWN).strip())
        _bump(stats.by_grant, (student.grant_type or UNKNOWN).strip())
        age = age_on(student.birth_date, today)
        if age is None:
            stats.unknown_age += 1
        else:
            _bump(stats.by_age, age)
    return stats


def sorted_counts(bucket: Dict[str, int],
                  limit: Optional[int] = None) -> List[tuple]:
    """(label, count) biggest first — the order a chart should draw."""
    ordered = sorted(bucket.items(), key=lambda item: (-item[1], str(item[0])))
    return ordered[:limit] if limit else ordered


# ── Who each feedback group actually is ─────────────────────────────────────
# Opinions are recorded per (cycle, gender). To say "the pupils who rate عدس
# lowest are the 9-year-olds" the report needs the AGE of those groups, and
# that comes from the roster, never from the ratings themselves.

@dataclass
class GroupProfile:
    """One group of the roster: how many, and how old."""
    count: int = 0
    by_age: Dict[int, int] = field(default_factory=dict)
    unknown_age: int = 0

    @property
    def average_age(self) -> Optional[float]:
        if not self.by_age:
            return None
        total = sum(age * number for age, number in self.by_age.items())
        return total / sum(self.by_age.values())

    @property
    def age_range(self) -> Optional[tuple]:
        """(youngest, oldest) among those with a usable birth date."""
        if not self.by_age:
            return None
        return min(self.by_age), max(self.by_age)


def _profile_by(students: Sequence[Student], today: datetime.date,
                key_of) -> Dict[str, GroupProfile]:
    profiles: Dict[str, GroupProfile] = {}
    for student in students:
        key = key_of(student)
        if not key:
            continue
        profile = profiles.setdefault(key, GroupProfile())
        profile.count += 1
        age = age_on(student.birth_date, today)
        if age is None:
            profile.unknown_age += 1
        else:
            _bump(profile.by_age, age)
    return profiles


def profile_by_cycle(students: Sequence[Student],
                     today: datetime.date) -> Dict[str, GroupProfile]:
    """Keyed by the same primary/collegial/qualifying codes the feedback
    groups use, via the app's own classifier — so the two line up by
    construction instead of by a second, drifting mapping."""
    from core.contact_counts import student_category
    return _profile_by(students, today, student_category)


def profile_by_gender(students: Sequence[Student],
                      today: datetime.date) -> Dict[str, GroupProfile]:
    return _profile_by(students, today,
                       lambda student: (student.gender or "").strip())


# ── Who is in each class ────────────────────────────────────────────────────

@dataclass
class ClassBreakdown:
    """One class (قسم): how many pupils, split by gender."""
    name: str
    by_gender: Dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.by_gender.values())

    def count(self, gender: str) -> int:
        return self.by_gender.get(gender, 0)

    @property
    def unknown_gender(self) -> int:
        """Pupils whose gender is not recorded. Reported as its own number
        rather than folded into either side."""
        return self.by_gender.get(UNKNOWN, 0)


def breakdown_by_class(students: Sequence[Student]) -> List[ClassBreakdown]:
    """Every class with its gender split, ordered by cycle then by name.

    Ordered through the app's own `student_category` rather than by trying to
    parse "الأولى"/"الثانية" out of the class name — the roster is imported
    from Excel and those names are whatever the school typed.
    """
    from core.contact_counts import student_category

    # Cycle order as the school reads it, monitors last.
    order = {"primary": 0, "collegial": 1, "qualifying": 2, "monitors": 3}
    grouped: Dict[str, ClassBreakdown] = {}
    ranks: Dict[str, int] = {}
    for student in students:
        name = (student.student_class or "").strip() or UNKNOWN
        entry = grouped.setdefault(name, ClassBreakdown(name=name))
        gender = (student.gender or UNKNOWN).strip()
        entry.by_gender[gender] = entry.by_gender.get(gender, 0) + 1
        ranks.setdefault(name, order.get(student_category(student), 9))

    return sorted(grouped.values(),
                  key=lambda entry: (ranks.get(entry.name, 9), entry.name))
