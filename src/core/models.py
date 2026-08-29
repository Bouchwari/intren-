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
    city: str = ""                      # الجماعة / المدينة (Arabic)
    city_fr: str = ""                   # Nom de la ville (French — used on bilingual documents)
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
    # Ramadan period, ISO YYYY-MM-DD. Blank = the app behaves as if Ramadan
    # were never configured. See core/ramadan.py for how days are classified.
    ramadan_start: str = ""             # بداية رمضان
    ramadan_end: str = ""               # نهاية رمضان
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
    created_at: str = ""        # YYYY-MM-DD, set by the DB on insert
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
class DailyReport:
    """The مسير's daily inspection report (التقرير اليومي للمصالح المادية
    والمالية). Attendance/absence numbers are read from daily_contact and
    daily_absence; everything here is the checklist that has no other home.

    Rating fields are an index into the matching scale, -1 meaning not yet
    rated. Item order and exact Arabic labels match the real accepted form
    (templets/التقرير اليومي للمصالح المادية والمالية.docx), not the
    ministry guide's blank annex."""
    date: str       # YYYY-MM-DD
    notes: str = ""

    # 1 — تتبع النظافة (hygiene) — 6-point scale: 0=ضعيفة .. 5=جيدة
    hygiene_staff: int = -1          # نظافة وهندام المستخدمين
    hygiene_utensils: int = -1       # نظافة الأواني وأدوات العمل
    hygiene_dining_hall: int = -1    # نظافة أرضيات وأسطح قاعة الأكل
    hygiene_kitchen: int = -1        # نظافة أرضيات وأسطح المطعم
    hygiene_storage: int = -1        # نظافة المخازن والثلاجات
    hygiene_waste: int = -1          # طريقة التخلص من بقايا الطعام
    hygiene_dorms: int = -1          # نظافة المراقد

    # 2 — تتبع المستفيدين من خدمة المطعمة (beneficiary tracking, per meal)
    ftour_expected: int = 0
    ftour_present: int = 0
    ghada_expected: int = 0
    ghada_present: int = 0
    asha_expected: int = 0
    asha_present: int = 0
    # Ramadan meals — a day serves either these or the three above.
    ftour_ramadan_expected: int = 0
    ftour_ramadan_present: int = 0
    shour_expected: int = 0
    shour_present: int = 0

    # 3 — تتبع الوجبات المقدمة (meal quality) — 3-point scale: 0=ناقصة .. 2=جيدة
    quality_supplies: int = -1        # جودة السلع والتزود
    quality_storage: int = -1         # ظروف التخزين
    quality_program: int = -1         # احترام البرنامج الغذائي
    quality_quantities: int = -1      # احترام الكميات المحددة
    quality_sample_kept: int = -1     # الاحتفاظ بالوجبة الشاهد
    quality_prep: int = -1            # ظروف وطريقة التحضير
    quality_serving: int = -1         # طريقة تقديم الوجبات

    # 4 — مراقبة وصيانة التجهيزات والبنايات — 3-point scale: 0=ناقصة .. 2=جيدة
    building_condition: int = -1      # حالة وصيانة البنايات
    equipment_condition: int = -1     # حالة التجهيزات والأدوات

    id: Optional[int] = None


@dataclass
class DailyReceptionRecord:
    """محضر تسليم الخدمة اليومي — confirms a day's delivered meals were
    received and accepted, signed by STEWARD/HEADMASTER/CONTRACTOR. One per
    date, covering all 3 meals on a single form (unlike contact_sheet /
    absence_sheet, which are one row per date+meal).

    Quantities default from that date's contact_sheet totals but are their
    own stored, independently-editable snapshot — not just a live read of
    contact_sheet — because this document is meant to confirm what was
    *actually* delivered, which occasionally differs from what was ordered.
    monthly_expense_statement cross-checks against this record and must
    flag any day where the two disagree rather than silently picking one
    (see matama skill documents.md §8)."""
    date: str
    ftour_qty: int = 0
    ghada_qty: int = 0
    asha_qty: int = 0
    # Ramadan meals — a date serves either these or the three above.
    ftour_ramadan_qty: int = 0
    shour_qty: int = 0
    remarks: str = ""
    id: Optional[int] = None


@dataclass
class MonthlyReceptionRecord:
    """محضر تسليم الخدمة الشهري — the month's collected reception
    confirmation, signed by STEWARD + HEADMASTER + CONTRACTOR and sent to
    المديرية الإقليمية together with monthly_expense_statement. One per
    month (stored as "YYYY-MM").

    Quantities default from that month's summed DailyReceptionRecord
    totals — the actual-delivered confirmations, not contact_sheet's
    ordered/estimated ones, since this document itself is a reception
    confirmation — but are their own stored, independently-editable
    snapshot, same guarantee as DailyReceptionRecord."""
    month: str
    ftour_qty: int = 0
    ghada_qty: int = 0
    asha_qty: int = 0
    # Ramadan meals — a date serves either these or the three above.
    ftour_ramadan_qty: int = 0
    shour_qty: int = 0
    remarks: str = ""
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
    document_number: Optional[int] = None  # assigned when first saved, never reassigned
    id: Optional[int] = None


@dataclass
class OrderItem:
    """One meal row in an order letter."""
    letter_id: int
    meal_type: str          # ftour / ghada / asha
    collegial: int = 0      # إعدادي count
    qualifying: int = 0     # تأهيلي count
    monitors: int = 0       # معلمو الداخلية count
    # ابتدائي. Added 2026-08-28: this cycle was missing entirely, so every
    # order letter asked the supplier for fewer meals than ورقة الاتصال had
    # counted — short by exactly the primary count, every single day.
    primary: int = 0
    id: Optional[int] = None

    @property
    def total(self) -> int:
        return self.primary + self.collegial + self.qualifying + self.monitors


@dataclass
class MealFeedback:
    """One recorded opinion about a meal that was served (تقييم التلاميذ).

    ENTERED IN THE APP by the مسير or الحارس العام after a meal. The prototype
    this came from collected ratings by QR code from pupils' phones; that needs
    a web server and this app is offline on a single PC, so the flow is a
    person typing what they were told rather than a pretend online form.

    `rating` is 1..5. There is no anonymous-submission concept here and no
    pupil is identified — it is feedback about the FOOD.
    """
    date: str                   # YYYY-MM-DD
    meal_type: str              # ftour / ghada / asha / ftour_ramadan / shour
    dish: str = ""              # the menu line this rating is about

    # HOW MANY pupils gave each level. A meal is eaten by a whole school, so
    # one opinion per meal was never a measurement — these counts are.
    count_excellent: int = 0    # ممتاز (5)
    count_good: int = 0         # جيد (4)
    count_average: int = 0      # متوسط (3)
    count_poor: int = 0         # ضعيف (2)
    count_bad: int = 0          # سيء (1)

    # LEGACY: the single 1..5 rating recorded before the counts existed. Rows
    # that still carry it are read as exactly one response at that level, so
    # nothing entered earlier is lost or double-counted.
    rating: int = 0

    note: str = ""
    recorded_by: str = ""
    created_at: str = ""
    id: Optional[int] = None


@dataclass
class FoodProduct:
    """One raw foodstuff in the school's product library (مادة غذائية).

    Values are recorded against a BASIS (per 100g, per 100ml, or per unit for
    things counted rather than weighed — an egg, a loaf), because that is how
    food labels and composition tables state them.
    """
    name: str
    unit_basis: str = "100g"    # 100g / 100ml / unit — see core.nutrition
    calories: int = 0
    protein: int = 0
    carbs: int = 0
    fats: int = 0
    id: Optional[int] = None


@dataclass
class MealComponent:
    """One line of a meal's recipe: how much of a product goes into it.

    The guide requires the approved weekly program to be submitted with
    "التوزيع الكمي لمكونات الوجبات الغذائية" (p.5), so these quantities are
    not just an app convenience — they are the content of an official
    attachment.
    """
    dish_name: str              # the menu line this belongs to, normalised
    product_id: int
    quantity: float = 0.0       # in the product's own basis unit (g / ml / unit)
    id: Optional[int] = None


@dataclass
class WeekFeedback:
    """What the pupils thought of ONE DISH over a whole week.

    The unit is the week's MENU, not a day: a week serves ~12 distinct dishes
    against 21 day-slots, a dish served twice is asked about once, and the
    collecting happens once a week instead of after every meal. The user asked
    for this on 2026-08-29 after finding the day-by-day version too much work.

    Deliberately carries the same count fields and `dish` as MealFeedback, so
    core.feedback's aggregation works on either without special-casing.
    """
    week_start: str             # the week's MONDAY, ISO
    dish: str = ""

    # WHO gave these opinions. One row per (week, dish, cycle, gender), so the
    # report can say "تأهيلي rate it 3.9 where ابتدائي rate it 2.1" from real
    # counts instead of inferring it. Both blank on rows recorded before the
    # grouping existed — those are reported as غير محدد, never assigned to a
    # group that may not have given them.
    cycle: str = ""             # primary / collegial / qualifying — or blank
    gender: str = ""            # male / female — or blank

    count_excellent: int = 0    # ممتاز (5)
    count_good: int = 0         # جيد (4)
    count_average: int = 0      # متوسط (3)
    count_poor: int = 0         # ضعيف (2)
    count_bad: int = 0          # سيء (1)

    # Never set here; present so the shared aggregation can read it uniformly.
    rating: int = 0

    note: str = ""
    recorded_by: str = ""
    created_at: str = ""
    id: Optional[int] = None


@dataclass
class DishNutrition:
    """The nutrition values of ONE menu line, as the user recorded them.

    The unit is the whole menu line ("طاجين لحم بالخضر"), not an individual
    food: that is how the weekly program stores a meal, and trying to split a
    free-text line into ingredients would mean guessing at quantities.

    Every number here is entered or confirmed by the user. Nothing is derived
    from the dish NAME — the prototype this screen came from computed
    `calories = 300 + len(name) * 10`, so a longer name scored more calories.
    A menu line with no row in this table is reported as unknown, never
    estimated.
    """
    dish_name: str
    calories: int = 0       # per portion, kcal
    protein: int = 0        # grams
    carbs: int = 0          # grams
    fats: int = 0           # grams
    id: Optional[int] = None


@dataclass
class StaffMember:
    """One member of the catering company's kitchen team (طاقم المطبخ).

    An INTERNAL tracking record, not an official document: the ministry guide
    has no staff form. It exists so the school can identify who works in its
    kitchen and — the real reason — see when someone's شهادة طبية is about to
    expire, since a valid medical certificate is a contractual requirement for
    anyone handling food.

    No attendance history by design (the user asked for identification only);
    `status` is the current situation, not a log.
    """
    full_name: str
    role: str = ""              # المهمة — see ui/staff_screen._ROLES
    shift: str = ""             # فترة العمل — صباحي / مسائي / تناوب
    phone: str = ""
    # ISO YYYY-MM-DD, or blank when the certificate has not been provided.
    health_cert_expiry: str = ""
    status: str = ""            # الحالة — حاضر / غائب / في عطلة
    notes: str = ""
    created_at: str = ""
    id: Optional[int] = None


@dataclass
class InfractionRecord:
    """محضر المخالفة — the official PV raised against the catering company
    when a contractual breach is observed (annex 5 of the ministry's
    procedural guide).

    This is the ONLY kind of مخالفة the app records. An earlier student-
    discipline log (دفتر المخالفات) existed by mistake — it came from a
    misunderstanding at the very start of the project, the user confirmed
    no such document exists in their job, and it was removed 2026-08-28.

    The subject is the CONTRACTOR breaching the صفقة, and it is signed by the
    company's representative plus the three-member follow-up committee. It
    records what happened and computes NO money — any deduction is decided
    elsewhere.

    The school/commune/contract/company identity is not stored here; it is
    read live from SchoolSettings when the document is produced, the same
    way every other official document in this app does it.
    """
    date: str                    # تاريخ المخالفة — YYYY-MM-DD
    document_number: int = 0     # sequential within its year → "2026/01"
    year: int = 0                # the year the number belongs to
    meal_type: str = ""          # وجبة المخالفة — ftour/ghada/asha/ramadan
    place: str = ""              # مكان المخالفة — المطبخ / المخزن / المطعم
    infraction_type: str = ""    # نوع المخالفة (short label)
    description: str = ""        # تفاصيل الإخلال المرصود
    reported_by: str = ""        # من عاين المخالفة
    written_date: str = ""       # حرر المحضر بتاريخ — YYYY-MM-DD
    created_at: str = ""
    id: Optional[int] = None

    @property
    def reference(self) -> str:
        """The number as it is printed on the document: "2026/01"."""
        return f"{self.year}/{self.document_number:02d}"


@dataclass
class Holiday:
    """A day the cafeteria is known to be closed in advance (weekend,
    ministry-set break, or a rare exception like roads blocked by snow).
    One row per calendar date — used to tell "closed" apart from "someone
    forgot to enter data" in batch exports and monthly summaries."""
    date: str    # YYYY-MM-DD
    label: str = ""  # e.g. "عطلة نصف السنة"
