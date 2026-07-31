"""School settings CRUD — moved out of database.py (Stage 1.5, Prompt 6)."""
from typing import Optional

from core.models import SchoolSettings
from data.database import _connection


def save_school_settings(s: SchoolSettings) -> None:
    """Upsert all school settings (always stored as row id=1)."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO school_settings (
                id, school_name, school_name_fr, aref, direction_provinciale,
                gresa_code, city, academy, director, school_year,
                gestionnaire, surveillant_general,
                contract_number, contract_object, supplier_name,
                company_name, supplier_address,
                price_ftour, price_ghada, price_asha,
                price_ftour_ramadan, price_asha_ramadan, price_shour
            ) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                school_name=excluded.school_name,
                school_name_fr=excluded.school_name_fr,
                aref=excluded.aref,
                direction_provinciale=excluded.direction_provinciale,
                gresa_code=excluded.gresa_code,
                city=excluded.city,
                academy=excluded.academy,
                director=excluded.director,
                school_year=excluded.school_year,
                gestionnaire=excluded.gestionnaire,
                surveillant_general=excluded.surveillant_general,
                contract_number=excluded.contract_number,
                contract_object=excluded.contract_object,
                supplier_name=excluded.supplier_name,
                company_name=excluded.company_name,
                supplier_address=excluded.supplier_address,
                price_ftour=excluded.price_ftour,
                price_ghada=excluded.price_ghada,
                price_asha=excluded.price_asha,
                price_ftour_ramadan=excluded.price_ftour_ramadan,
                price_asha_ramadan=excluded.price_asha_ramadan,
                price_shour=excluded.price_shour
        """, (
            s.school_name, s.school_name_fr, s.aref, s.direction_provinciale,
            s.gresa_code, s.city, s.academy, s.director, s.school_year,
            s.gestionnaire, s.surveillant_general,
            s.contract_number, s.contract_object, s.supplier_name,
            s.company_name, s.supplier_address,
            s.price_ftour, s.price_ghada, s.price_asha,
            s.price_ftour_ramadan, s.price_asha_ramadan, s.price_shour,
        ))


def get_school_settings() -> Optional[SchoolSettings]:
    """Return the saved school settings, or None if not yet configured."""
    with _connection() as conn:
        row = conn.execute("SELECT * FROM school_settings WHERE id = 1").fetchone()
    if row is None:
        return None

    def _r(key: str) -> str:
        try:
            return row[key] or ""
        except IndexError:
            return ""

    return SchoolSettings(
        school_name=_r("school_name"),
        school_name_fr=_r("school_name_fr"),
        aref=_r("aref"),
        direction_provinciale=_r("direction_provinciale"),
        gresa_code=_r("gresa_code"),
        city=_r("city"),
        academy=_r("academy"),
        director=_r("director"),
        school_year=_r("school_year"),
        gestionnaire=_r("gestionnaire"),
        surveillant_general=_r("surveillant_general"),
        contract_number=_r("contract_number"),
        contract_object=_r("contract_object"),
        supplier_name=_r("supplier_name"),
        company_name=_r("company_name"),
        supplier_address=_r("supplier_address"),
        price_ftour=_r("price_ftour"),
        price_ghada=_r("price_ghada"),
        price_asha=_r("price_asha"),
        price_ftour_ramadan=_r("price_ftour_ramadan"),
        price_asha_ramadan=_r("price_asha_ramadan"),
        price_shour=_r("price_shour"),
    )
