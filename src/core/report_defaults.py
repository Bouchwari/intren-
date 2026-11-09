"""Configurable, date-stable daily report suggestions for human review.

Saved observations stay authoritative. The UI owns rating labels; this module
only works with the corresponding numeric indices.
"""
import random
import dataclasses
import hashlib
from typing import Dict, List, Optional

from core.models import DailyReport


REPORT_SCALES = {
    **{name: 6 for name in (
        "hygiene_staff", "hygiene_utensils", "hygiene_dining_hall", "hygiene_kitchen",
        "hygiene_storage", "hygiene_waste", "hygiene_dorms")},
    **{name: 3 for name in (
        "quality_supplies", "quality_storage", "quality_program", "quality_quantities",
        "quality_sample_kept", "quality_prep", "quality_serving",
        "building_condition", "equipment_condition")},
}


def default_report_preferences() -> dict:
    return {
        "variation": 15,
        "rules": {field: {"base": size - 1,
                          "alternatives": [4, 3] if field in (
                              "hygiene_dining_hall", "hygiene_dorms") else []}
                  for field, size in REPORT_SCALES.items()},
    }


def normalize_report_preferences(value: object) -> dict:
    """Validate persisted/user-supplied rules without silently accepting typos."""
    if not isinstance(value, dict):
        raise ValueError("Report preferences must be an object")
    result = default_report_preferences()
    variation = value.get("variation", result["variation"])
    if type(variation) is not int or not 0 <= variation <= 100:
        raise ValueError("Variation must be an integer between 0 and 100")
    result["variation"] = variation
    rules = value.get("rules", {})
    if not isinstance(rules, dict) or set(rules) - REPORT_SCALES.keys():
        raise ValueError("Invalid report fields")
    for field, rule in rules.items():
        if not isinstance(rule, dict):
            raise ValueError("Invalid report rule")
        base, alternatives = rule.get("base"), rule.get("alternatives", [])
        if type(base) is not int or not -1 <= base < REPORT_SCALES[field]:
            raise ValueError("Invalid preferred rating")
        if not isinstance(alternatives, list) or len(alternatives) > 2 or any(
            type(item) is not int or not 0 <= item < REPORT_SCALES[field]
            for item in alternatives
        ):
            raise ValueError("Invalid alternative ratings")
        alternatives = list(dict.fromkeys(i for i in alternatives if i != base))
        result["rules"][field] = {"base": base,
                                     "alternatives": alternatives if base >= 0 else []}
    return result


def fill_report_defaults(report: DailyReport, preferences: dict) -> DailyReport:
    """Date-stable suggestions for new reports only, never saved observations."""
    if report.id is not None:
        return report
    prefs = normalize_report_preferences(preferences)
    updates = {}
    for field, rule in prefs["rules"].items():
        if getattr(report, field) != -1:
            continue
        rating = rule["base"]
        alternatives = rule["alternatives"]
        seed = hashlib.sha256(f"report-v1:{report.date}:{field}".encode()).digest()
        rng = random.Random(seed)
        if rating >= 0 and alternatives and rng.random() < prefs["variation"] / 100:
            rating = rng.choices(alternatives, weights=[2, 1][:len(alternatives)], k=1)[0]
        updates[field] = rating
    return dataclasses.replace(report, **updates)


def apply_report_overrides(report: DailyReport, overrides: dict | None) -> DailyReport:
    """Only checklist/notes may be overridden; attendance stays source-derived."""
    if not overrides:
        return report
    if set(overrides) - (set(REPORT_SCALES) | {"notes"}):
        raise ValueError("Unsupported report override")
    for field, value in overrides.items():
        if field == "notes":
            if not isinstance(value, str):
                raise ValueError("Notes must be text")
        elif type(value) is not int or not -1 <= value < REPORT_SCALES[field]:
            raise ValueError("Invalid rating override")
    return dataclasses.replace(report, **overrides)


def suggest_rating_index(
    scale_length: int,
    excluded_indices: List[int],
    weight_overrides: Optional[Dict[int, float]] = None,
    default_weight: float = 10.0,
) -> int:
    """Pick a plausible rating index into a scale of `scale_length` options.

    Indices in `excluded_indices` are never chosen. Every remaining index
    is weighted by `weight_overrides` (index -> weight), falling back to
    `default_weight` for any index not listed there."""
    weight_overrides = weight_overrides or {}
    candidates = [i for i in range(scale_length) if i not in excluded_indices]
    if not candidates:
        raise ValueError("no candidate indices left after exclusions")
    weights = [weight_overrides.get(i, default_weight) for i in candidates]
    return random.choices(candidates, weights=weights, k=1)[0]
