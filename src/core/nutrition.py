"""Weekly nutrition analysis for the meal program.

Works ONLY from values the user recorded for each menu line. A line with no
recorded values is reported as unknown and excluded from the totals — it is
never estimated, and nothing is ever derived from the dish's name.

Pure logic: no Qt, no database, no Arabic (labels live in ui/).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.models import DishNutrition, FoodProduct, MealComponent, MealEntry

# How a product's recorded values scale to a quantity. Per-100 bases divide by
# 100; a "unit" product (an egg, a loaf) is counted, so it multiplies directly.
BASIS_PER_100G = "100g"
BASIS_PER_100ML = "100ml"
BASIS_PER_UNIT = "unit"
UNIT_BASES = (BASIS_PER_100G, BASIS_PER_100ML, BASIS_PER_UNIT)

# Where a menu line's values came from — shown on screen so the user can tell
# a computed meal from one typed in wholesale.
SOURCE_RECIPE = "recipe"     # summed from its components
SOURCE_DIRECT = "direct"     # a whole-line value entered before recipes existed
SOURCE_NONE = "none"


def scale_factor(unit_basis: str, quantity: float) -> float:
    """How many times a product's recorded values apply to `quantity`."""
    if unit_basis == BASIS_PER_UNIT:
        return float(quantity)
    return float(quantity) / 100.0


def normalize_dish(name: str) -> str:
    """The key a menu line is matched on.

    Collapses surrounding and repeated whitespace so "طاجين  لحم " and
    "طاجين لحم" are the same dish — a user retyping a line should not silently
    create a second, unknown entry.
    """
    return " ".join((name or "").split())


@dataclass
class NutritionValues:
    """A resolved set of values for one menu line, and where they came from."""
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fats: float = 0.0
    source: str = SOURCE_NONE

    @property
    def is_known(self) -> bool:
        return self.source != SOURCE_NONE


def component_values(product: FoodProduct, quantity: float) -> NutritionValues:
    """What `quantity` of one product contributes."""
    factor = scale_factor(product.unit_basis, quantity)
    return NutritionValues(
        calories=product.calories * factor,
        protein=product.protein * factor,
        carbs=product.carbs * factor,
        fats=product.fats * factor,
        source=SOURCE_RECIPE,
    )


def recipe_values(components: Sequence[MealComponent],
                  products: Dict[int, FoodProduct]) -> Optional[NutritionValues]:
    """A meal's totals summed from its components.

    Returns None when the recipe references a product that no longer exists —
    a partial sum would be a plausible-looking wrong number, which is exactly
    what this screen refuses to produce.
    """
    if not components:
        return None
    total = NutritionValues(source=SOURCE_RECIPE)
    for component in components:
        product = products.get(component.product_id)
        if product is None:
            return None
        part = component_values(product, component.quantity)
        total.calories += part.calories
        total.protein += part.protein
        total.carbs += part.carbs
        total.fats += part.fats
    return total


def resolve_dish(
    dish_name: str,
    recipes: Dict[str, Sequence[MealComponent]],
    products: Dict[int, FoodProduct],
    direct: Dict[str, DishNutrition],
) -> NutritionValues:
    """A menu line's values: its recipe first, then a whole-line value.

    The recipe wins because it is the more precise record AND the one the
    ministry's التوزيع الكمي attachment is built from; the direct value stays
    as a fallback so the entries made before recipes existed are not lost.
    """
    key = normalize_dish(dish_name)
    if not key:
        return NutritionValues()
    from_recipe = recipe_values(recipes.get(key, ()), products)
    if from_recipe is not None:
        return from_recipe
    row = direct.get(key)
    if row is None:
        return NutritionValues()
    return NutritionValues(
        calories=row.calories, protein=row.protein,
        carbs=row.carbs, fats=row.fats, source=SOURCE_DIRECT,
    )


@dataclass
class MealAnalysis:
    """One cell of the week: what is on the menu and what it is worth."""
    meal_type: str
    dish_name: str
    nutrition: NutritionValues = field(default_factory=NutritionValues)

    @property
    def is_known(self) -> bool:
        return self.nutrition.is_known

    @property
    def is_empty(self) -> bool:
        """No menu written for this slot at all — not the same as a menu whose
        nutrition has not been recorded yet."""
        return not normalize_dish(self.dish_name)


@dataclass
class DayAnalysis:
    """A day's meals and the totals of the ones we actually know."""
    day_of_week: int
    meals: List[MealAnalysis] = field(default_factory=list)

    @property
    def planned_meals(self) -> List[MealAnalysis]:
        return [meal for meal in self.meals if not meal.is_empty]

    @property
    def known_meals(self) -> List[MealAnalysis]:
        return [meal for meal in self.planned_meals if meal.is_known]

    @property
    def is_complete(self) -> bool:
        """True when every planned meal has recorded values, so the totals
        below describe the whole day rather than part of it."""
        planned = self.planned_meals
        return bool(planned) and len(self.known_meals) == len(planned)

    def _total(self, attribute: str) -> float:
        return sum(getattr(meal.nutrition, attribute) for meal in self.known_meals)

    @property
    def calories(self) -> float:
        return self._total("calories")

    @property
    def protein(self) -> float:
        return self._total("protein")

    @property
    def carbs(self) -> float:
        return self._total("carbs")

    @property
    def fats(self) -> float:
        return self._total("fats")


@dataclass
class WeekAnalysis:
    days: List[DayAnalysis] = field(default_factory=list)

    @property
    def planned_count(self) -> int:
        return sum(len(day.planned_meals) for day in self.days)

    @property
    def known_count(self) -> int:
        return sum(len(day.known_meals) for day in self.days)

    @property
    def is_complete(self) -> bool:
        return self.planned_count > 0 and self.known_count == self.planned_count

    @property
    def average_calories(self) -> Optional[float]:
        """Mean calories over the days that are FULLY known.

        None when no day is complete: averaging partial days would quietly
        understate the week, which is exactly the kind of plausible-but-wrong
        number this screen exists to avoid.
        """
        complete = [day for day in self.days if day.is_complete]
        if not complete:
            return None
        return sum(day.calories for day in complete) / len(complete)


def build_nutrition_index(
    rows: Sequence[DishNutrition],
) -> Dict[str, DishNutrition]:
    """Recorded values keyed by normalised dish name."""
    return {normalize_dish(row.dish_name): row for row in rows}


def analyse_week(
    entries: Sequence[MealEntry],
    nutrition: Sequence[DishNutrition],
    meal_types: Sequence[str],
    days: int = 7,
    recipes: Optional[Dict[str, Sequence[MealComponent]]] = None,
    products: Optional[Dict[int, FoodProduct]] = None,
) -> WeekAnalysis:
    """Match every menu line in the program against its values.

    A line's values come from its recipe when it has one, otherwise from a
    whole-line entry, otherwise it is unknown — see resolve_dish.
    """
    direct = build_nutrition_index(nutrition)
    recipes = recipes or {}
    products = products or {}
    by_slot: Dict[Tuple[int, str], str] = {
        (entry.day_of_week, entry.meal_type): entry.menu_text
        for entry in entries
    }
    week = WeekAnalysis()
    for day_of_week in range(days):
        day = DayAnalysis(day_of_week=day_of_week)
        for meal_type in meal_types:
            dish = by_slot.get((day_of_week, meal_type), "")
            day.meals.append(MealAnalysis(
                meal_type=meal_type,
                dish_name=dish,
                nutrition=resolve_dish(dish, recipes, products, direct),
            ))
        week.days.append(day)
    return week


def unknown_dishes(
    entries: Sequence[MealEntry],
    nutrition: Sequence[DishNutrition],
    recipes: Optional[Dict[str, Sequence[MealComponent]]] = None,
    products: Optional[Dict[int, FoodProduct]] = None,
) -> List[str]:
    """Distinct menu lines with no recorded values, in first-seen order.

    This is the screen's to-do list: until it is empty the weekly totals only
    describe part of the program, and the screen has to say so.
    """
    direct = build_nutrition_index(nutrition)
    recipes = recipes or {}
    products = products or {}
    missing: List[str] = []
    seen = set()
    for entry in entries:
        key = normalize_dish(entry.menu_text)
        if not key or key in seen:
            continue
        seen.add(key)
        if not resolve_dish(key, recipes, products, direct).is_known:
            missing.append(key)
    return missing
