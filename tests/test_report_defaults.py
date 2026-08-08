import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.report_defaults import suggest_rating_index


class SuggestRatingIndexTests(unittest.TestCase):
    def test_never_returns_an_excluded_index(self) -> None:
        for _ in range(300):
            index = suggest_rating_index(6, excluded_indices=[0, 1], weight_overrides={2: 15, 3: 8, 4: 35, 5: 42})
            self.assertNotIn(index, (0, 1))
            self.assertIn(index, (2, 3, 4, 5))

    def test_respects_relative_weights(self) -> None:
        """A heavily-weighted index should come up meaningfully more often
        than a lightly-weighted one — not an exact ratio, just a real
        skew, over enough draws."""
        counts = Counter(
            suggest_rating_index(3, excluded_indices=[0], weight_overrides={1: 20, 2: 80})
            for _ in range(1000)
        )
        self.assertGreater(counts[2], counts[1] * 2)

    def test_unlisted_index_falls_back_to_default_weight(self) -> None:
        # Index 2 has no explicit weight — must still be reachable.
        seen = {suggest_rating_index(3, excluded_indices=[], weight_overrides={0: 1, 1: 1}) for _ in range(200)}
        self.assertIn(2, seen)

    def test_raises_when_every_index_is_excluded(self) -> None:
        with self.assertRaises(ValueError):
            suggest_rating_index(2, excluded_indices=[0, 1])


if __name__ == "__main__":
    unittest.main()
