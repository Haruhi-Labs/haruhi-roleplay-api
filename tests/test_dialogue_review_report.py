from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_haruhi_dialogue_review import _rate, _wilson_interval  # noqa: E402


class DialogueReviewReportTests(unittest.TestCase):
    def test_wilson_interval_contains_observed_rate(self) -> None:
        interval = _wilson_interval(95, 100)

        assert interval is not None
        self.assertLess(interval[0], 0.95)
        self.assertGreater(interval[1], 0.95)
        self.assertEqual(_rate(95, 100), 0.95)

    def test_empty_denominator_is_explicit(self) -> None:
        self.assertIsNone(_rate(0, 0))
        self.assertIsNone(_wilson_interval(0, 0))


if __name__ == "__main__":
    unittest.main()
