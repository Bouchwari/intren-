"""Data models — plain Python objects, zero external dependencies."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LevelOption:
    """One selectable school level, grouped by cycle and education type."""
    cycle_code: str
    cycle_label: str
    education_type: str
    level_name: str


@dataclass
class SchoolSettings:
    """Complete school identity and supplier contract settings."""
    # ── Required fields ───────────────────────────────────────────────────
    school_name: str        # اسم المؤسسة (Arabic)
    school_year: str        # السنة الدراسية
    director: str           # اسم مدير المؤسسة
    # ── Institution (wizard page 1) ───────────────────────────────────────
    school_name_fr: str = ""            # Nom d'établissement
    aref: str = ""                      # الأكاديمية الجهوية (AREF)
    direction_provinciale: str = ""     # المديرية الإقليمية
    gresa_code: str = ""                # رمز GRESA
    city: str = ""                      # الجماعة / المدينة
    academy: str = ""                   # legacy — same concept as aref
    gestionnaire: str = ""              # مسير المصالح المادية والمالية
    surveillant_general: str = ""       # الحارس العام للداخلية
    # ── Supplier / صفقة المطعمة (wizard page 2) ──────────────────────────
    contract_number: str = ""           # رقم الصفقة
    contract_object: str = ""           # Objet du marché
    supplier_name: str = ""             # اسم المزود
    company_name: str = ""              # اسم الشركة / Raison sociale
    supplier_address: str = ""          # العنوان
    price_ftour: str = ""               # ثمن وجبة الفطور
    price_ghada: str = ""               # ثمن وجبة الغداء
    price_asha: str = ""                # ثمن وجبة العشاء
    price_ftour_ramadan: str = ""       # ثمن فطور رمضان
    price_asha_ramadan: str = ""        # ثمن عشاء رمضان
    price_shour: str = ""               # ثمن السحور
    id: Optional[int] = None


@dataclass
class Student:
    """A cafeteria beneficiary — regular student or monitor (معلم داخلية)."""
    full_name: str
    massar_number: str = ""       # رقم مسار
    gender: str = ""              # "male" | "female" | ""
    cycle: str = ""               # السلك
    education_type: str = ""      # نوع التعليم
    student_class: str = ""
    birth_date: str = ""
    birth_place: str = ""
    grant_number: str = ""
    section: str = "cantine"       # "cantine" | "internat"
    grant_type: str = "full"       # "full" | "half"
    is_monitor: bool = False       # True = معلم داخلية / رقيب
    phone: str = ""                # optional phone number
    id: Optional[int] = None


@dataclass
class MealProgram:
    """A named weekly meal plan (regular or Ramadan mode)."""
    name: str                   # e.g. "البرنامج الأسبوعي 1"
    school_year: str = ""
    is_ramadan: bool = False    # True → show Ramadan meals
    id: Optional[int] = None


@dataclass
class MealEntry:
    """One cell in the weekly meal grid (day × meal type)."""
    program_id: int
    day_of_week: int    # 0=السبت … 6=الجمعة
    meal_type: str      # ftour / ghada / asha / ftour_ramadan / shour
    menu_text: str = ""
    id: Optional[int] = None


@dataclass
class DailyContact:
    """One meal row in the daily contact sheet (ورقة الاتصال اليومية)."""
    date: str           # YYYY-MM-DD
    meal_type: str      # ftour / ghada / asha

    # الابتدائي
    primary_granted: int = 0        # منحة كاملة
    primary_complement: int = 0     # وجبة غذاء

    # إعدادي (collegial)
    collegial_granted: int = 0      # منحة كاملة
    collegial_paying: int = 0       # قديم: مؤدى، يدمج في منحة كاملة
    collegial_complement: int = 0   # وجبة غذاء

    # تأهيلي (qualifying)
    qualifying_granted: int = 0     # منحة كاملة
    qualifying_paying: int = 0      # قديم: مؤدى، يدمج في منحة كاملة
    qualifying_complement: int = 0  # وجبة غذاء

    # معلمو الداخلية
    monitors: int = 0
    monitors_complement: int = 0

    id: Optional[int] = None

    @property
    def primary_total(self) -> int:
        return self.primary_granted + self.primary_complement

    @property
    def collegial_total(self) -> int:
        return self.collegial_granted + self.collegial_paying + self.collegial_complement

    @property
    def qualifying_total(self) -> int:
        return self.qualifying_granted + self.qualifying_paying + self.qualifying_complement

    @property
    def monitors_total(self) -> int:
        return self.monitors + self.monitors_complement

    @property
    def grand_total(self) -> int:
        return self.primary_total + self.collegial_total + self.qualifying_total + self.monitors_total


@dataclass
class DailyContactDocumentLog:
    """One saved/printed official daily contact document event."""
    date: str
    document_number: int
    action: str
    ftour_total: int = 0
    ghada_total: int = 0
    asha_total: int = 0
    grand_total: int = 0
    file_path: str = ""
    created_at: str = ""
    id: Optional[int] = None


@dataclass
class DailyAbsence:
    """One meal row in the daily absence sheet (ورقة الغياب اليومي).
    Same structure as DailyContact but tracks absences, not attendance."""
    date: str           # YYYY-MM-DD
    meal_type: str      # ftour / ghada / asha

    # إعدادي (collegial)
    collegial_granted: int = 0      # ممنوح
    collegial_paying: int = 0       # مؤد
    collegial_complement: int = 0   # متمم

    # تأهيلي (qualifying)
    qualifying_granted: int = 0     # ممنوح
    qualifying_paying: int = 0      # مؤد
    qualifying_complement: int = 0  # متمم

    # معلمو الداخلية
    monitors: int = 0

    id: Optional[int] = None

    @property
    def collegial_total(self) -> int:
        return self.collegial_granted + self.collegial_paying + self.collegial_complement

    @property
    def qualifying_total(self) -> int:
        return self.qualifying_granted + self.qualifying_paying + self.qualifying_complement

    @property
    def grand_total(self) -> int:
        return self.collegial_total + self.qualifying_total + self.monitors


@dataclass
class DailyReport:
    """Stores the مسير's notes for a given day. Report data is read from
    daily_contact and daily_absence tables — we only persist the notes."""
    date: str       # YYYY-MM-DD
    notes: str = ""
    id: Optional[int] = None


@dataclass
class MonthlyMealSummary:
    """Aggregated totals for one meal type across a full month.
    Computed on the fly — never stored in DB."""
    meal_type: str
    days_count: int = 0          # distinct days that have data for this meal

    # Contact (attendance) subtotals by sector
    contact_primary: int = 0     # ابتدائي
    contact_collegial: int = 0   # إعدادي
    contact_qualifying: int = 0  # تأهيلي
    contact_monitors: int = 0    # معلمون

    # Absence subtotals by sector
    absence_primary: int = 0
    absence_collegial: int = 0
    absence_qualifying: int = 0
    absence_monitors: int = 0

    # Price per meal (loaded from settings)
    unit_price: float = 0.0

    @property
    def contact_total(self) -> int:
        return self.contact_primary + self.contact_collegial + self.contact_qualifying + self.contact_monitors

    @property
    def absence_total(self) -> int:
        return self.absence_primary + self.absence_collegial + self.absence_qualifying + self.absence_monitors

    @property
    def net_total(self) -> int:
        """Meals actually served = contact − absence (floor at 0)."""
        return max(0, self.contact_total - self.absence_total)

    @property
    def total_cost(self) -> float:
        return self.net_total * self.unit_price


@dataclass
class OrderLetter:
    """Header info for a supplier order letter (رسالة الطلبية)."""
    letter_date: str    # YYYY-MM-DD — date printed on the letter
    period_start: str   # YYYY-MM-DD — start of the supply period
    period_end: str     # YYYY-MM-DD — end of the supply period
    notes: str = ""
    id: Optional[int] = None


@dataclass
class OrderItem:
    """One meal row in an order letter."""
    letter_id: int
    meal_type: str          # ftour / ghada / asha
    collegial: int = 0      # إعدادي count
    qualifying: int = 0     # تأهيلي count
    monitors: int = 0       # معلمو الداخلية count
    id: Optional[int] = None

    @property
    def total(self) -> int:
        return self.collegial + self.qualifying + self.monitors


@dataclass
class Violation:
    """One incident record in the disciplinary log (دفتر المخالفات)."""
    date: str                   # YYYY-MM-DD
    student_name: str           # full name (denormalised for fast display)
    student_class: str = ""     # class/section
    violation_type: str = ""    # predefined or free text
    description: str = ""       # free text details
    action_taken: str = ""      # disciplinary action
    reported_by: str = ""       # staff member who reported it
    student_id: Optional[int] = None   # FK → students.id (nullable)
    id: Optional[int] = None
