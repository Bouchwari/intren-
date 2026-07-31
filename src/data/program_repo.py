"""Weekly meal program CRUD — moved out of database.py (Stage 1.5, Prompt 6)."""
from typing import List

from core.models import MealEntry, MealProgram
from data.database import _connection


def get_all_programs() -> List[MealProgram]:
    """Return all meal programs ordered by creation date."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, name, school_year, is_ramadan FROM meal_programs ORDER BY id"
        ).fetchall()
    return [
        MealProgram(
            id=r["id"],
            name=r["name"],
            school_year=r["school_year"] or "",
            is_ramadan=bool(r["is_ramadan"]),
        )
        for r in rows
    ]


def create_program(name: str, school_year: str = "", is_ramadan: bool = False) -> int:
    """Insert a new empty meal program. Returns the new id."""
    with _connection() as conn:
        cur = conn.execute(
            "INSERT INTO meal_programs (name, school_year, is_ramadan) VALUES (?,?,?)",
            (name, school_year, int(is_ramadan)),
        )
        return int(cur.lastrowid)  # type: ignore[arg-type]


def rename_program(program_id: int, new_name: str) -> None:
    with _connection() as conn:
        conn.execute(
            "UPDATE meal_programs SET name=? WHERE id=?", (new_name, program_id)
        )


def set_program_ramadan_mode(program_id: int, is_ramadan: bool) -> None:
    """Persist whether a meal program uses the Ramadan meal layout."""
    with _connection() as conn:
        conn.execute(
            "UPDATE meal_programs SET is_ramadan=? WHERE id=?",
            (int(is_ramadan), program_id),
        )


def delete_program(program_id: int) -> None:
    """Delete program and all its entries (CASCADE handles entries)."""
    with _connection() as conn:
        conn.execute("DELETE FROM meal_programs WHERE id=?", (program_id,))


def get_program_entries(program_id: int) -> List[MealEntry]:
    """Return all entries for one program."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, program_id, day_of_week, meal_type, menu_text "
            "FROM meal_program_entries WHERE program_id=?",
            (program_id,),
        ).fetchall()
    return [
        MealEntry(
            id=r["id"],
            program_id=r["program_id"],
            day_of_week=r["day_of_week"],
            meal_type=r["meal_type"],
            menu_text=r["menu_text"] or "",
        )
        for r in rows
    ]


def save_program_entries(program_id: int, entries: List[MealEntry]) -> None:
    """Replace all entries for a program with the provided list."""
    with _connection() as conn:
        conn.execute(
            "DELETE FROM meal_program_entries WHERE program_id=?", (program_id,)
        )
        conn.executemany(
            "INSERT INTO meal_program_entries (program_id, day_of_week, meal_type, menu_text) "
            "VALUES (?,?,?,?)",
            [(e.program_id, e.day_of_week, e.meal_type, e.menu_text) for e in entries],
        )
