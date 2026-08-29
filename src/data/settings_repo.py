"""School settings CRUD — moved out of database.py (Stage 1.5, Prompt 6)."""
from typing import Optional

from config.settings import EXPORT_FORMAT_ASK, EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF
from core.models import SchoolSettings
from data.database import _connection

_EXPORT_FORMAT_KEY = "document_export_format"
_VALID_EXPORT_FORMATS = {EXPORT_FORMAT_ASK, EXPORT_FORMAT_PDF, EXPORT_FORMAT_DOCX}


def save_school_settings(s: SchoolSettings) -> None:
    """Upsert all school settings (always stored as row id=1)."""
    with _connection() as conn:
        conn.execute("""
            INSERT INTO school_settings (
                id, school_name, school_name_fr, aref, direction_provinciale,
                gresa_code, city, city_fr, academy, director, school_year,
                gestionnaire, surveillant_general,
                contract_number, contract_object, supplier_name,
                company_name, supplier_address,
                price_ftour, price_ghada, price_asha,
                price_ftour_ramadan, price_asha_ramadan, price_shour,
                ramadan_start, ramadan_end
            ) VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                school_name=excluded.school_name,
                school_name_fr=excluded.school_name_fr,
                aref=excluded.aref,
                direction_provinciale=excluded.direction_provinciale,
                gresa_code=excluded.gresa_code,
                city=excluded.city,
                city_fr=excluded.city_fr,
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
                price_shour=excluded.price_shour,
                ramadan_start=excluded.ramadan_start,
                ramadan_end=excluded.ramadan_end
        """, (
            s.school_name, s.school_name_fr, s.aref, s.direction_provinciale,
            s.gresa_code, s.city, s.city_fr, s.academy, s.director, s.school_year,
            s.gestionnaire, s.surveillant_general,
            s.contract_number, s.contract_object, s.supplier_name,
            s.company_name, s.supplier_address,
            s.price_ftour, s.price_ghada, s.price_asha,
            s.price_ftour_ramadan, s.price_asha_ramadan, s.price_shour,
            s.ramadan_start, s.ramadan_end,
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
        city_fr=_r("city_fr"),
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
        ramadan_start=_r("ramadan_start"),
        ramadan_end=_r("ramadan_end"),
        price_shour=_r("price_shour"),
    )


def get_document_export_format() -> str:
    """Return the saved export-format preference (EXPORT_FORMAT_ASK/PDF/DOCX),
    defaulting to asking every time when nothing has been saved yet."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT value FROM app_preferences WHERE key=?", (_EXPORT_FORMAT_KEY,)
        ).fetchone()
    value = row["value"] if row else ""
    return value if value in _VALID_EXPORT_FORMATS else EXPORT_FORMAT_ASK


def save_document_export_format(value: str) -> None:
    """Persist which format the export button should use (or ask each time)."""
    if value not in _VALID_EXPORT_FORMATS:
        value = EXPORT_FORMAT_ASK
    with _connection() as conn:
        conn.execute("""
            INSERT INTO app_preferences (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (_EXPORT_FORMAT_KEY, value))
