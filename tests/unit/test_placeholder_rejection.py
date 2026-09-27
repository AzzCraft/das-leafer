"""Regression tests for placeholder pattern rejection in das-leafer template artifacts."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "templates" / "das-leafer-product"
PLACEHOLDER_RE = re.compile(r"<ORG>|<DAS_SUITE_REPO_URL>|<PRODUCT_REPO>")


class TestLeaferPlaceholderRejection(unittest.TestCase):
    """Scan leafer template governed files for residual placeholders."""

    SCAN_TARGETS = [
        "tooling_lock.json",
        "scripts/install_cadence_vendor.sh",
        "README.md",
        "prompts/orchestrator.md",
    ]

    def test_no_placeholder_in_template_files(self):
        for rel in self.SCAN_TARGETS:
            path = TEMPLATE_ROOT / rel
            if not path.exists():
                continue
            with self.subTest(file=rel):
                content = path.read_text()
                matches = PLACEHOLDER_RE.findall(content)
                self.assertEqual(
                    matches,
                    [],
                    f"template {rel} contains forbidden placeholder(s): {matches}",
                )

    def test_orchestrator_has_five_statuses(self):
        orch = TEMPLATE_ROOT / "prompts" / "orchestrator.md"
        if not orch.exists():
            self.skipTest("orchestrator.md not found")
        content = orch.read_text()
        for status in ("TODO", "IN_PROGRESS", "DONE", "BLOCKED", "PROPOSED"):
            self.assertIn(status, content, f"orchestrator.md missing status: {status}")

    def test_tasks_template_has_five_statuses(self):
        tasks = TEMPLATE_ROOT / "openspec" / "schemas" / "das-standard" / "templates" / "tasks.md"
        if not tasks.exists():
            self.skipTest("tasks.md template not found")
        content = tasks.read_text()
        for status in ("TODO", "IN_PROGRESS", "DONE", "BLOCKED", "PROPOSED"):
            self.assertIn(status, content, f"tasks.md missing status: {status}")


if __name__ == "__main__":
    unittest.main()
