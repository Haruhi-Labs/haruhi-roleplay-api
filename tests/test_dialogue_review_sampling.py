from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sample_haruhi_dialogue_review import _rank  # noqa: E402


class DialogueReviewSamplingTests(unittest.TestCase):
    def test_rank_is_repeatable_and_seeded(self) -> None:
        self.assertEqual(_rank("span", seed="a"), _rank("span", seed="a"))
        self.assertNotEqual(_rank("span", seed="a"), _rank("span", seed="b"))


if __name__ == "__main__":
    unittest.main()
