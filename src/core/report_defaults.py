"""
src/core/report_defaults.py
Weighted-random defaults for التقرير اليومي's checklist ratings — lets
"توليد التقرير" pre-fill a plausible day instead of leaving every item
blank, while the مسير can still override anything that's actually wrong.
No PySide6, no Arabic strings — ui/daily_report_screen.py owns the scale
text and decides which index means what.
"""
import random
from typing import Dict, List, Optional


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
