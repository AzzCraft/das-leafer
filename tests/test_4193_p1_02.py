"""P1-02: das-leafer must not mask template standard reference debt with expectedFailure.

Tests derived from das_repos_4193_unresolved_priority_fix_list.md P1-02.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tests._root_contract import repository_root_for_test_file


REPO_ROOT = repository_root_for_test_file(__file__)  # das-leafer
TEMPLATE = REPO_ROOT / "templates" / "das-leafer-product"


def _clean_pycache(root: Path) -> None:
    """Remove __pycache__ directories so the verify script residue check passes."""
    for d in list(root.rglob("__pycache__")):
        shutil.rmtree(d, ignore_errors=True)
    for f in list(root.rglob("*.pyc")):
        f.unlink(missing_ok=True)


class P102LeaferStandardRefDebtTests(unittest.TestCase):
    """P1-02: das-leafer template has no masked STANDARD_REF debt and no expectedFailure."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.agents = (TEMPLATE / "AGENTS.override.md").read_text(encoding="utf-8")
        cls.vendor = (TEMPLATE / "vendor" / "README.md").read_text(encoding="utf-8")
        cls.verify_script = (TEMPLATE / "scripts" / "verify").read_text(encoding="utf-8")
        cls.test_text = (REPO_ROOT / "tests" / "test_remediation_specs.py").read_text(encoding="utf-8")

    # 1. AGENTS.override.md must not reference the legacy copied standard path.
    def test_p1_02_agents_no_legacy_standard_path(self) -> None:
        self.assertNotIn("docs/standards/DAS_STANDARD.md", self.agents,
                         "AGENTS.override.md still references legacy copied standard")

    # 2. AGENTS.override.md must reference STANDARD_REF.md.
    def test_p1_02_agents_references_standard_ref(self) -> None:
        self.assertIn("STANDARD_REF.md", self.agents,
                       "AGENTS.override.md does not reference STANDARD_REF.md")

    # 3. vendor/README.md must reference STANDARD_REF.md.
    def test_p1_02_vendor_readme_references_standard_ref(self) -> None:
        self.assertIn("STANDARD_REF.md", self.vendor,
                       "vendor/README.md must reference STANDARD_REF.md")

    # 4. test_remediation_specs.py must NOT use @unittest.expectedFailure.
    def test_p1_02_no_expected_failure_in_test_suite(self) -> None:
        self.assertNotIn("@unittest.expectedFailure", self.test_text,
                         "test suite still masks a known v9 failure with expectedFailure")

    # 5. Template verify script must enforce vendor README STANDARD_REF linkage.
    def test_p1_02_verify_script_enforces_vendor_readme_standard_ref(self) -> None:
        self.assertIn("vendor/README.md", self.verify_script,
                       "template verify script must check vendor/README.md")
        self.assertIn("STANDARD_REF.md", self.verify_script,
                       "template verify script must enforce STANDARD_REF.md linkage")

    # 6. das-leafer scripts/verify must pass.
    def test_p1_02_scripts_verify_passes(self) -> None:
        _clean_pycache(REPO_ROOT)
        proc = subprocess.run(
            ["bash", "scripts/verify", "--" + os.environ.get("DASLEAFER_VERIFY_MODE", "standalone")],
            cwd=REPO_ROOT,
            env={**os.environ, "DASLEAFER_VERIFY_SKIP_TESTS": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, "das-leafer scripts/verify failed:\n" + proc.stdout)

    # 7. das-leafer verify output must not show expected failures.
    def test_p1_02_verify_no_expected_failures(self) -> None:
        _clean_pycache(REPO_ROOT)
        proc = subprocess.run(
            ["bash", "scripts/verify", "--" + os.environ.get("DASLEAFER_VERIFY_MODE", "standalone")],
            cwd=REPO_ROOT,
            env={**os.environ, "DASLEAFER_VERIFY_SKIP_TESTS": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
        self.assertNotIn("expected failures", proc.stdout.lower(),
                         "das-leafer verify still passes with expected failures:\n" + proc.stdout)

    # --- L2 Plan §12: legacy DAS_STANDARD.md must not exist in template ---
    def test_p1_02_no_copied_standard_in_template(self) -> None:
        legacy = TEMPLATE / "docs" / "standards" / "DAS_STANDARD.md"
        self.assertFalse(legacy.exists(),
                         "template still contains copied standard document")

    # --- L2 Plan §14: template has STANDARD_REF.md ---
    def test_p1_02_template_has_standard_ref(self) -> None:
        self.assertTrue((TEMPLATE / "STANDARD_REF.md").exists(),
                        "template missing STANDARD_REF.md")

    # --- L2 Plan §14: template verify guards legacy standard path ---
    def test_p1_02_verify_guards_legacy_standard_path(self) -> None:
        self.assertIn("docs/standards/DAS_STANDARD.md", self.verify_script,
                       "template verify must guard against legacy copied standard path")

    # --- L2 Plan §11 LEAF-002: template has HFVI profile ---
    def test_p1_02_template_has_hfvi_profile(self) -> None:
        master_doc = (TEMPLATE / "docs" / "master_doc.md").read_text(encoding="utf-8")
        self.assertIn("hfvi", master_doc.lower(),
                       "master_doc.md must mention HFVI profile")

    # --- L2 Plan §14: template README references STANDARD_REF.md ---
    def test_p1_02_template_readme_references_standard_ref(self) -> None:
        readme = TEMPLATE / "README.md"
        if readme.exists():
            text = readme.read_text(encoding="utf-8")
            self.assertIn("STANDARD_REF.md", text)

    # --- L2 Plan §8: das-leafer has root verify/tests/changelog shell ---
    def test_p1_02_leafer_has_root_verify(self) -> None:
        self.assertTrue((REPO_ROOT / "scripts" / "verify").exists())

    def test_p1_02_leafer_has_changelog(self) -> None:
        self.assertTrue((REPO_ROOT / "CHANGELOG.md").exists())

    def test_p1_02_leafer_has_tests_dir(self) -> None:
        self.assertTrue((REPO_ROOT / "tests").is_dir())

    # --- L2 Plan §18: template verify enforces AGENTS.override.md audit ---
    def test_p1_02_verify_audits_agents_override(self) -> None:
        self.assertIn("AGENTS.override.md", self.verify_script,
                       "template verify must audit AGENTS.override.md")

    # --- 00C §5.3: template must seed tooling_lock.json ---
    def test_p1_02_template_has_tooling_lock(self) -> None:
        self.assertTrue((TEMPLATE / "tooling_lock.json").exists(),
                        "template missing tooling_lock.json")

    # --- 00C §5.3: template must seed local_extension_manifest.json ---
    def test_p1_02_template_has_local_extension_manifest(self) -> None:
        self.assertTrue((TEMPLATE / "local_extension_manifest.json").exists(),
                        "template missing local_extension_manifest.json")

    # --- 00F: no current-baseline old name in template ---
    def test_p1_02_no_old_baseline_name_in_template(self) -> None:
        for f in TEMPLATE.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".json", ".yaml", ".yml"):
                text = f.read_text(encoding="utf-8", errors="replace")
                self.assertNotIn("unified" + "-current-baseline", text,
                                 f"{f.relative_to(TEMPLATE)} still references old baseline name")

    # --- 00G E-003: no copied standard doc anywhere in das-leafer ---
    def test_p1_02_no_copied_standard_anywhere(self) -> None:
        for f in REPO_ROOT.rglob("DAS_STANDARD.md"):
            self.fail(f"copied standard found at {f.relative_to(REPO_ROOT)}")

    # --- 00B: das-leafer must not copy dasops core logic ---
    def test_p1_02_no_dasops_core_duplication(self) -> None:
        for py in REPO_ROOT.rglob("*.py"):
            if "test" in py.name.lower():
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("class DasOpsCore", text,
                             f"{py.name} duplicates dasops core logic")

    # --- 00C §5.3: template STANDARD_REF.md references lock-based pinning ---
    def test_p1_02_standard_ref_mentions_lock_pinning(self) -> None:
        ref = TEMPLATE / "STANDARD_REF.md"
        if ref.exists():
            text = ref.read_text(encoding="utf-8")
            self.assertTrue(
                "tooling_lock" in text or "suite closure" in text.lower() or "das-standard" in text,
                "STANDARD_REF.md must reference lock-based version pinning or das-standard",
            )

    # --- 00D: das-leafer scripts/verify is executable ---
    def test_p1_02_verify_is_executable(self) -> None:
        verify = REPO_ROOT / "scripts" / "verify"
        self.assertTrue(os.access(verify, os.X_OK), "scripts/verify not executable")


if __name__ == "__main__":
    unittest.main()
