"""التحليل الغذائي — the weekly analysis and the values it is built from.

The rule this whole feature exists to hold: a menu line with no recorded
values is reported as unknown and left out of the totals. It is never
estimated, and nothing is ever derived from the dish's NAME — the prototype
this came from used `calories = 300 + len(name) * 10`.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import MEAL_ASHA, MEAL_FTOUR, MEAL_GHADA
from core.models import (
    DishNutrition, FoodProduct, MealComponent, MealEntry, SchoolSettings,
)
from core.nutrition import (
    BASIS_PER_100G, BASIS_PER_100ML, BASIS_PER_UNIT, SOURCE_DIRECT,
    SOURCE_NONE, SOURCE_RECIPE, analyse_week, build_nutrition_index,
    component_values, normalize_dish, recipe_values, resolve_dish,
    scale_factor, unknown_dishes,
)
from data import database
from ui import nutrition_screen as nut

MEALS = [MEAL_FTOUR, MEAL_GHADA, MEAL_ASHA]


def _entry(day: int, meal: str, text: str) -> MealEntry:
    return MealEntry(program_id=1, day_of_week=day, meal_type=meal, menu_text=text)


class NormalizeTests(unittest.TestCase):
    def test_surrounding_and_repeated_spaces_collapse(self) -> None:
        """Retyping a line with different spacing must not silently create a
        second, unknown dish."""
        self.assertEqual(normalize_dish("  طاجين   لحم "), "طاجين لحم")
        self.assertEqual(normalize_dish(""), "")
        self.assertEqual(normalize_dish("   "), "")

    def test_the_index_is_keyed_on_the_normalised_name(self) -> None:
        index = build_nutrition_index(
            [DishNutrition(dish_name="  كسكس  بالخضر ", calories=540)])
        self.assertIn("كسكس بالخضر", index)


class WeekAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = [
            DishNutrition(dish_name="طاجين لحم", calories=620, protein=34,
                          carbs=52, fats=26),
            DishNutrition(dish_name="خبز وشاي", calories=300, protein=8,
                          carbs=46, fats=11),
        ]

    def test_a_day_with_every_meal_known_is_complete(self) -> None:
        entries = [
            _entry(0, MEAL_FTOUR, "خبز وشاي"),
            _entry(0, MEAL_GHADA, "طاجين لحم"),
        ]
        week = analyse_week(entries, self.table, [MEAL_FTOUR, MEAL_GHADA], days=1)
        day = week.days[0]

        self.assertTrue(day.is_complete)
        self.assertEqual(day.calories, 920)
        self.assertEqual(day.protein, 42)

    def test_an_unknown_dish_is_excluded_and_the_day_is_incomplete(self) -> None:
        """The number must never quietly become a partial total presented as
        a whole one."""
        entries = [
            _entry(0, MEAL_FTOUR, "خبز وشاي"),
            _entry(0, MEAL_GHADA, "سمك وأرز"),      # no recorded values
        ]
        week = analyse_week(entries, self.table, [MEAL_FTOUR, MEAL_GHADA], days=1)
        day = week.days[0]

        self.assertFalse(day.is_complete)
        self.assertEqual(len(day.planned_meals), 2)
        self.assertEqual(len(day.known_meals), 1)
        self.assertEqual(day.calories, 300)          # only the known meal

    def test_an_unwritten_menu_slot_is_not_counted_as_missing_data(self) -> None:
        """An empty slot means the day serves nothing then — that is different
        from a named meal whose values have not been recorded."""
        entries = [_entry(0, MEAL_FTOUR, "خبز وشاي")]
        week = analyse_week(entries, self.table, [MEAL_FTOUR, MEAL_GHADA], days=1)
        day = week.days[0]

        self.assertEqual(len(day.planned_meals), 1)
        self.assertTrue(day.is_complete)
        self.assertTrue(day.meals[1].is_empty)

    def test_no_calories_are_derived_from_the_dish_name(self) -> None:
        """A long name must score nothing at all when it has no values —
        exactly what the prototype got wrong."""
        entries = [_entry(0, MEAL_GHADA, "طاجين لحم بالخضر والبطاطس والجزر واللفت")]
        week = analyse_week(entries, self.table, [MEAL_GHADA], days=1)

        self.assertEqual(week.days[0].calories, 0)
        self.assertEqual(week.known_count, 0)

    def test_the_average_uses_complete_days_only(self) -> None:
        entries = [
            _entry(0, MEAL_FTOUR, "خبز وشاي"), _entry(0, MEAL_GHADA, "طاجين لحم"),
            _entry(1, MEAL_FTOUR, "خبز وشاي"), _entry(1, MEAL_GHADA, "غير معروف"),
        ]
        week = analyse_week(entries, self.table, [MEAL_FTOUR, MEAL_GHADA], days=2)

        # Day 0 = 920 and complete; day 1 is partial and must not drag it down.
        self.assertEqual(week.average_calories, 920)

    def test_the_average_is_none_when_no_day_is_complete(self) -> None:
        entries = [_entry(0, MEAL_GHADA, "غير معروف")]
        week = analyse_week(entries, self.table, [MEAL_FTOUR, MEAL_GHADA], days=1)

        self.assertIsNone(week.average_calories)

    def test_coverage_counts_planned_meals_not_slots(self) -> None:
        entries = [
            _entry(0, MEAL_FTOUR, "خبز وشاي"),
            _entry(0, MEAL_GHADA, "سمك وأرز"),
        ]
        week = analyse_week(entries, self.table, MEALS, days=1)

        self.assertEqual(week.planned_count, 2)      # عشاء is simply unwritten
        self.assertEqual(week.known_count, 1)
        self.assertFalse(week.is_complete)


class UnknownDishTests(unittest.TestCase):
    def test_distinct_unknown_lines_are_listed_once_in_order(self) -> None:
        table = [DishNutrition(dish_name="خبز وشاي", calories=300)]
        entries = [
            _entry(0, MEAL_FTOUR, "خبز وشاي"),
            _entry(0, MEAL_GHADA, "سمك وأرز"),
            _entry(1, MEAL_GHADA, "  سمك وأرز "),   # same dish, odd spacing
            _entry(1, MEAL_ASHA, "شوربة"),
            _entry(2, MEAL_FTOUR, ""),               # empty slot, not missing
        ]
        self.assertEqual(unknown_dishes(entries, table), ["سمك وأرز", "شوربة"])


class NutritionRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_saving_the_same_dish_twice_updates_it_in_place(self) -> None:
        """Matched on the NAME, so editing a dish cannot leave a stale
        duplicate that the weekly analysis might pick up instead."""
        database.save_dish_nutrition(DishNutrition(dish_name="كسكس", calories=500))
        database.save_dish_nutrition(DishNutrition(dish_name="  كسكس ", calories=540))

        rows = database.get_all_dish_nutrition()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].calories, 540)

    def test_lookup_and_delete(self) -> None:
        dish_id = database.save_dish_nutrition(
            DishNutrition(dish_name="عدس", calories=430, protein=22))
        found = database.get_dish_nutrition("  عدس  ")
        self.assertIsNotNone(found)
        self.assertEqual(found.protein, 22)

        database.delete_dish_nutrition(dish_id)
        self.assertEqual(database.get_all_dish_nutrition(), [])

    def test_the_reference_value_round_trips_and_survives_junk(self) -> None:
        self.assertEqual(database.get_nutrition_reference_calories(2200), 2200)
        database.save_nutrition_reference_calories(1800)
        self.assertEqual(database.get_nutrition_reference_calories(2200), 1800)


class NutritionScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()
        self._info = QMessageBox.information
        QMessageBox.information = staticmethod(lambda *a, **k: None)

        self._program_id = database.create_program("أسبوع", "2025-2026", False)
        database.save_program_entries(self._program_id, [
            MealEntry(program_id=self._program_id, day_of_week=day,
                      meal_type=meal, menu_text=text)
            for day, meal, text in (
                (2, MEAL_FTOUR, "خبز وشاي"),
                (2, MEAL_GHADA, "طاجين لحم"),
                (3, MEAL_GHADA, "سمك وأرز"),
            )
        ])
        database.save_dish_nutrition(
            DishNutrition(dish_name="خبز وشاي", calories=300))
        database.save_dish_nutrition(
            DishNutrition(dish_name="طاجين لحم", calories=620))

    def tearDown(self) -> None:
        QMessageBox.information = self._info
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_the_screen_reports_partial_coverage(self) -> None:
        screen = nut.NutritionScreen()
        screen.show()

        self.assertEqual(screen._analysis.planned_count, 3)
        self.assertEqual(screen._analysis.known_count, 2)
        self.assertEqual(screen._unknown, ["سمك وأرز"])
        self.assertIn("2/3", screen._coverage_value.text())
        screen.close()

    def test_filling_in_an_unknown_dish_removes_it_from_the_list(self) -> None:
        screen = nut.NutritionScreen()
        screen.show()

        screen._start_filling("سمك وأرز")
        self.assertEqual(screen._dish_edit.text(), "سمك وأرز")
        screen._value_spins["calories"].setValue(610)
        screen._on_save_dish()

        self.assertEqual(screen._unknown, [])
        self.assertTrue(screen._analysis.is_complete)
        screen.close()

    def test_saving_a_dish_with_no_name_is_refused(self) -> None:
        screen = nut.NutritionScreen()
        screen.show()
        screen._dish_edit.setText("   ")
        screen._on_save_dish()

        self.assertEqual(len(database.get_all_dish_nutrition()), 2)
        screen.close()

    def test_a_ramadan_program_is_analysed_on_its_own_meals(self) -> None:
        """A normal program is not "missing" سحور — it simply does not serve
        one, so it must not count against coverage."""
        ramadan_id = database.create_program("رمضان", "2025-2026", True)
        database.save_program_entries(ramadan_id, [
            MealEntry(program_id=ramadan_id, day_of_week=2,
                      meal_type=nut.MEAL_IFTAR, menu_text="حريرة وتمر"),
        ])
        database.save_dish_nutrition(
            DishNutrition(dish_name="حريرة وتمر", calories=520))

        screen = nut.NutritionScreen()
        screen.show()
        for index in range(screen._program_combo.count()):
            if "رمضان" in screen._program_combo.itemText(index):
                screen._program_combo.setCurrentIndex(index)

        self.assertEqual(screen._analysis.planned_count, 1)
        self.assertTrue(screen._analysis.is_complete)
        screen.close()

    def test_the_reference_value_is_remembered(self) -> None:
        screen = nut.NutritionScreen()
        screen.show()
        screen._reference_spin.setValue(1900)
        screen.close()

        reopened = nut.NutritionScreen()
        self.assertEqual(reopened._reference_spin.value(), 1900)
        reopened.close()


if __name__ == "__main__":
    unittest.main()


class ProductScalingTests(unittest.TestCase):
    """A product's values are recorded against a basis, because that is how
    food labels state them — per 100g, per 100ml, or per countable unit."""

    def setUp(self) -> None:
        self.meat = FoodProduct(id=1, name="لحم", unit_basis=BASIS_PER_100G,
                                calories=250, protein=26, fats=15)
        self.oil = FoodProduct(id=2, name="زيت", unit_basis=BASIS_PER_100ML,
                               calories=884, fats=100)
        self.bread = FoodProduct(id=3, name="خبز", unit_basis=BASIS_PER_UNIT,
                                 calories=250, protein=8, carbs=48)

    def test_per_hundred_bases_divide_by_a_hundred(self) -> None:
        self.assertEqual(scale_factor(BASIS_PER_100G, 80), 0.8)
        self.assertEqual(scale_factor(BASIS_PER_100ML, 250), 2.5)

    def test_a_counted_unit_multiplies_directly(self) -> None:
        """Two loaves is twice one loaf, not two hundredths of one."""
        self.assertEqual(scale_factor(BASIS_PER_UNIT, 2), 2)

    def test_component_values_scale_every_nutrient(self) -> None:
        values = component_values(self.meat, 80)
        self.assertAlmostEqual(values.calories, 200)
        self.assertAlmostEqual(values.protein, 20.8)
        self.assertAlmostEqual(values.fats, 12)

    def test_a_unit_product_is_counted(self) -> None:
        self.assertAlmostEqual(component_values(self.bread, 1).calories, 250)
        self.assertAlmostEqual(component_values(self.bread, 2).calories, 500)


class RecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.products = {
            1: FoodProduct(id=1, name="لحم", unit_basis=BASIS_PER_100G,
                           calories=250, protein=26),
            2: FoodProduct(id=2, name="خضر", unit_basis=BASIS_PER_100G,
                           calories=40, carbs=8),
        }
        self.recipe = [
            MealComponent(dish_name="طاجين", product_id=1, quantity=80),
            MealComponent(dish_name="طاجين", product_id=2, quantity=150),
        ]

    def test_a_recipe_sums_its_components(self) -> None:
        values = recipe_values(self.recipe, self.products)
        self.assertAlmostEqual(values.calories, 260)     # 200 + 60
        self.assertAlmostEqual(values.protein, 20.8)
        self.assertEqual(values.source, SOURCE_RECIPE)

    def test_an_empty_recipe_is_not_a_zero_meal(self) -> None:
        self.assertIsNone(recipe_values([], self.products))

    def test_a_recipe_pointing_at_a_missing_product_gives_nothing(self) -> None:
        """A partial sum would be a plausible-looking wrong number, which is
        exactly what this screen refuses to produce."""
        broken = [MealComponent(dish_name="طاجين", product_id=99, quantity=50)]
        self.assertIsNone(recipe_values(broken, self.products))

    def test_the_recipe_wins_over_a_whole_line_value(self) -> None:
        direct = {"طاجين": DishNutrition(dish_name="طاجين", calories=999)}
        resolved = resolve_dish("طاجين", {"طاجين": self.recipe},
                                self.products, direct)
        self.assertEqual(resolved.source, SOURCE_RECIPE)
        self.assertAlmostEqual(resolved.calories, 260)

    def test_a_whole_line_value_is_still_used_when_there_is_no_recipe(self) -> None:
        """Nothing entered before recipes existed is lost."""
        direct = {"كسكس": DishNutrition(dish_name="كسكس", calories=540)}
        resolved = resolve_dish("كسكس", {}, self.products, direct)
        self.assertEqual(resolved.source, SOURCE_DIRECT)
        self.assertEqual(resolved.calories, 540)

    def test_a_dish_with_neither_is_unknown(self) -> None:
        resolved = resolve_dish("مجهول", {}, self.products, {})
        self.assertFalse(resolved.is_known)
        self.assertEqual(resolved.source, SOURCE_NONE)

    def test_the_week_uses_recipes_and_counts_them_as_known(self) -> None:
        entries = [_entry(0, MEAL_GHADA, "طاجين")]
        week = analyse_week(entries, [], [MEAL_GHADA], days=1,
                            recipes={"طاجين": self.recipe},
                            products=self.products)
        self.assertEqual(week.known_count, 1)
        self.assertAlmostEqual(week.days[0].calories, 260)

    def test_a_dish_with_a_recipe_is_not_listed_as_unknown(self) -> None:
        entries = [_entry(0, MEAL_GHADA, "طاجين"), _entry(0, MEAL_ASHA, "مجهول")]
        missing = unknown_dishes(entries, [], recipes={"طاجين": self.recipe},
                                 products=self.products)
        self.assertEqual(missing, ["مجهول"])


class ProductRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_db_path = database.DB_PATH
        database.DB_PATH = Path(self._tmpdir.name) / "test_matama.db"
        database.init_database()

    def tearDown(self) -> None:
        database.DB_PATH = self._original_db_path
        self._tmpdir.cleanup()

    def test_saving_a_product_twice_updates_it_in_place(self) -> None:
        """Correcting a product must not leave a stale duplicate that some
        recipe still points at."""
        database.save_food_product(FoodProduct(name="لحم", calories=250))
        database.save_food_product(FoodProduct(name="  لحم ", calories=260))

        products = database.get_all_food_products()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].calories, 260)

    def test_adding_the_same_product_twice_to_a_dish_updates_the_quantity(self) -> None:
        product_id = database.save_food_product(FoodProduct(name="أرز"))
        database.save_meal_component(
            MealComponent(dish_name="طبق", product_id=product_id, quantity=100))
        database.save_meal_component(
            MealComponent(dish_name="طبق", product_id=product_id, quantity=120))

        components = database.get_meal_components("طبق")
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0].quantity, 120)

    def test_deleting_a_product_removes_it_from_every_recipe(self) -> None:
        """Which is why resolve_dish can never meet a component whose product
        has vanished."""
        keep = database.save_food_product(FoodProduct(name="أرز"))
        drop = database.save_food_product(FoodProduct(name="زيت"))
        for product_id in (keep, drop):
            database.save_meal_component(
                MealComponent(dish_name="طبق", product_id=product_id, quantity=50))

        database.delete_food_product(drop)

        remaining = database.get_meal_components("طبق")
        self.assertEqual([c.product_id for c in remaining], [keep])

    def test_all_components_are_grouped_by_dish(self) -> None:
        product_id = database.save_food_product(FoodProduct(name="أرز"))
        for dish in ("طبق أ", "طبق ب"):
            database.save_meal_component(
                MealComponent(dish_name=dish, product_id=product_id, quantity=50))

        recipes = database.get_all_meal_components()
        self.assertEqual(set(recipes), {"طبق أ", "طبق ب"})


class QuantityBreakdownExportTests(unittest.TestCase):
    """التوزيع الكمي — the attachment the guide (p.5) requires with the
    approved weekly program."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._settings = SchoolSettings(
            school_name="مؤسسة", school_year="2025-2026", director="المدير")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_it_writes_a_real_pdf(self) -> None:
        from ui.nutrition_export import write_quantity_breakdown_pdf

        products = {1: FoodProduct(id=1, name="لحم", calories=250, protein=26)}
        recipes = [("طاجين", [MealComponent(dish_name="طاجين", product_id=1,
                                            quantity=80)])]
        path = Path(self._tmpdir.name) / "tawzi3.pdf"
        write_quantity_breakdown_pdf(path, self._settings, "الأسبوعي",
                                     recipes, products)

        self.assertEqual(path.read_bytes()[:4], b"%PDF")
        self.assertGreater(path.stat().st_size, 2000)

    def test_many_meals_paginate_rather_than_vanish(self) -> None:
        from ui.nutrition_export import write_quantity_breakdown_pdf

        products = {1: FoodProduct(id=1, name="لحم", calories=250)}
        recipes = [
            (f"وجبة {index}",
             [MealComponent(dish_name=f"وجبة {index}", product_id=1, quantity=80)])
            for index in range(30)
        ]
        path = Path(self._tmpdir.name) / "many.pdf"
        write_quantity_breakdown_pdf(path, self._settings, "الأسبوعي",
                                     recipes, products)

        self.assertGreater(path.read_bytes().count(b"/Type /Page"), 1)
