from __future__ import annotations

import unittest

from dasleafer.hfvi import describe_hfvi_requirements, validate_hfvi_gate, REQUIRED_ASSET_SECTION, REQUIRED_LAYOUT_SECTION


class HfviTests(unittest.TestCase):
    def test_describe_returns_profile(self):
        reqs = describe_hfvi_requirements()
        self.assertEqual(reqs["interactionProfile"], "hfvi_canvas_webgl_game")
        self.assertIsInstance(reqs["requiredAppendixSections"], list)
        self.assertEqual(len(reqs["requiredAppendixSections"]), 2)

    def test_validate_gate_all_present(self):
        doc = f"# Doc\n{REQUIRED_ASSET_SECTION}\nAssets...\n{REQUIRED_LAYOUT_SECTION}\nLayout...\n"
        missing = validate_hfvi_gate(doc)
        self.assertEqual(missing, [])

    def test_validate_gate_missing_both(self):
        doc = "# Just a title"
        missing = validate_hfvi_gate(doc)
        self.assertEqual(len(missing), 2)

    def test_validate_gate_missing_layout(self):
        doc = f"# Doc\n{REQUIRED_ASSET_SECTION}\nAssets..."
        missing = validate_hfvi_gate(doc)
        self.assertEqual(missing, [REQUIRED_LAYOUT_SECTION])


if __name__ == "__main__":
    unittest.main()
