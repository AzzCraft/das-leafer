from __future__ import annotations

import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._root_contract import repository_root_for_test_file


REPO_ROOT = repository_root_for_test_file(__file__)
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

from verify_dasops_release_lock import controlled_workspace_exception  # noqa: E402


class WorkspaceVerificationModeTests(unittest.TestCase):
    def test_workspace_exception_requires_explicit_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            dasops_root = workspace / "dasops"
            dasops_root.mkdir()
            with mock.patch.dict(os.environ, {"DASLEAFER_ALLOW_UNPINNED_WORKSPACE_DASOPS": "1"}):
                self.assertFalse(controlled_workspace_exception(dasops_root, requested=False))
            with self.assertRaises(ValueError):
                controlled_workspace_exception(dasops_root, requested=True)
            (workspace / "workspace.yaml").write_text('{}\n')
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            self.assertTrue(controlled_workspace_exception(dasops_root, requested=True))
            with self.assertRaises(ValueError):
                controlled_workspace_exception(workspace / "arbitrary", requested=True)

    def test_verify_script_exposes_workspace_mode_without_hidden_environment(self) -> None:
        text = (REPO_ROOT / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertIn("--workspace", text)
        self.assertIn('export PYTHONPATH="$DASOPS_ROOT${PYTHONPATH:+:$PYTHONPATH}"', text)
        self.assertNotIn("DASLEAFER_ALLOW_UNPINNED_WORKSPACE_DASOPS", text)


if __name__ == "__main__":
    unittest.main()
