from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from select_haruhi_dialogue_adjudication import _sampled  # noqa: E402


class DialogueAdjudicationSelectionTests(unittest.TestCase):
    def test_sampling_is_deterministic(self) -> None:
        first = _sampled("span-1", seed="seed", rate=0.5)
        second = _sampled("span-1", seed="seed", rate=0.5)

        self.assertEqual(first, second)
        self.assertFalse(_sampled("span-1", seed="seed", rate=0.0))
        self.assertTrue(_sampled("span-1", seed="seed", rate=1.0))


if __name__ == "__main__":
    unittest.main()
