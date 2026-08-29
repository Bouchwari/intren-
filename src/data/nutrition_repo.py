"""Recorded nutrition values per menu line (التحليل الغذائي).

One row per distinct menu line, keyed by its normalised text so the same dish
typed with different spacing does not become two entries.
"""
import sqlite3
from typing import Dict, List, Optional

from core.models import DishNutrition, FoodProduct, MealComponent
from core.nutrition import normalize_dish
from data.database import _connection

_COLUMNS = ("dish_name", "calories", "protein", "carbs", "fats")


def _row_to_dish(row: sqlite3.Row) -> DishNutrition:
    return DishNutrition(id=row["id"], **{c: row[c] for c in _COLUMNS})


def get_all_dish_nutrition() -> List[DishNutrition]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM dish_nutrition ORDER BY dish_name COLLATE NOCASE"
        ).fetchall()
    return [_row_to_dish(row) for row in rows]


def get_dish_nutrition(dish_name: str) -> Optional[DishNutrition]:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM dish_nutrition WHERE dish_name=?",
            (normalize_dish(dish_name),),
        ).fetchone()
    return _row_to_dish(row) if row else None


def save_dish_nutrition(dish: DishNutrition) -> int:
    """Insert or update the values for one menu line, matched on its name.

    Matching on the NAME rather than the id means editing a dish that already
    has values updates it in place, instead of leaving a stale duplicate the
    weekly analysis could pick up instead.
    """
    name = normalize_dish(dish.dish_name)
    values = (name, dish.calories, dish.protein, dish.carbs, dish.fats)
    with _connection() as conn:
        conn.execute("""
            INSERT INTO dish_nutrition (dish_name, calories, protein, carbs, fats)
            VALUES (?,?,?,?,?)
            ON CONFLICT(dish_name) DO UPDATE SET
                calories=excluded.calories, protein=excluded.protein,
                carbs=excluded.carbs, fats=excluded.fats
        """, values)
        row = conn.execute(
            "SELECT id FROM dish_nutrition WHERE dish_name=?", (name,)
        ).fetchone()
        return int(row["id"])


def delete_dish_nutrition(dish_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM dish_nutrition WHERE id=?", (dish_id,))


# ── Food products (المواد الغذائية) ──────────────────────────────────────────

_PRODUCT_COLUMNS = ("name", "unit_basis", "calories", "protein", "carbs", "fats")


def _row_to_product(row: sqlite3.Row) -> FoodProduct:
    return FoodProduct(id=row["id"], **{c: row[c] for c in _PRODUCT_COLUMNS})


def get_all_food_products() -> List[FoodProduct]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM food_products ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [_row_to_product(row) for row in rows]


def save_food_product(product: FoodProduct) -> int:
    """Insert or update one product, matched on its name.

    Matching on the name means correcting a product's values updates it in
    place rather than leaving a stale duplicate that some recipe still points
    at.
    """
    name = normalize_dish(product.name)
    values = (name, product.unit_basis, product.calories, product.protein,
              product.carbs, product.fats)
    with _connection() as conn:
        conn.execute("""
            INSERT INTO food_products (name, unit_basis, calories, protein, carbs, fats)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                unit_basis=excluded.unit_basis, calories=excluded.calories,
                protein=excluded.protein, carbs=excluded.carbs,
                fats=excluded.fats
        """, values)
        row = conn.execute(
            "SELECT id FROM food_products WHERE name=?", (name,)).fetchone()
        return int(row["id"])


def delete_food_product(product_id: int) -> None:
    """Removing a product also removes it from every recipe (ON DELETE
    CASCADE), which is why a recipe can never point at a missing product."""
    with _connection() as conn:
        conn.execute("DELETE FROM food_products WHERE id=?", (product_id,))


# ── Meal components (التوزيع الكمي) ──────────────────────────────────────────

def _row_to_component(row: sqlite3.Row) -> MealComponent:
    return MealComponent(
        id=row["id"], dish_name=row["dish_name"],
        product_id=row["product_id"], quantity=row["quantity"],
    )


def get_meal_components(dish_name: str) -> List[MealComponent]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meal_components WHERE dish_name=? ORDER BY id",
            (normalize_dish(dish_name),),
        ).fetchall()
    return [_row_to_component(row) for row in rows]


def get_all_meal_components() -> Dict[str, List[MealComponent]]:
    """Every recipe at once, keyed by dish — one query for a whole week."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM meal_components ORDER BY dish_name, id").fetchall()
    recipes: Dict[str, List[MealComponent]] = {}
    for row in rows:
        recipes.setdefault(row["dish_name"], []).append(_row_to_component(row))
    return recipes


def save_meal_component(component: MealComponent) -> int:
    """Add or update how much of a product goes into a meal."""
    dish = normalize_dish(component.dish_name)
    with _connection() as conn:
        conn.execute("""
            INSERT INTO meal_components (dish_name, product_id, quantity)
            VALUES (?,?,?)
            ON CONFLICT(dish_name, product_id) DO UPDATE SET
                quantity=excluded.quantity
        """, (dish, component.product_id, float(component.quantity)))
        row = conn.execute(
            "SELECT id FROM meal_components WHERE dish_name=? AND product_id=?",
            (dish, component.product_id),
        ).fetchone()
        return int(row["id"])


def delete_meal_component(component_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM meal_components WHERE id=?", (component_id,))
