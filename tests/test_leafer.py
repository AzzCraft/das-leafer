from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests._root_contract import repository_root_for_test_file

import dasleafer.adopt as leafer_adopt
import dasleafer._dasops_bridge as dasops_bridge
import dasleafer.doctor as leafer_doctor
import dasleafer.locks as leafer_locks
import dasleafer.repo_factory as leafer_repo_factory
import dasleafer.tasks as leafer_tasks
import dasleafer.__main__ as leafer_main
from dasleafer.preset import create_product_repo


REPO_ROOT = repository_root_for_test_file(__file__)


def _locked_hfvi_browser_available() -> bool:
    browser = shutil.which(os.environ.get("HFVI_BROWSER_BINARY", "google-chrome"))
    if browser is None:
        return False
    lock_path = REPO_ROOT / "templates" / "das-leafer-product" / "hfvi" / "browser.lock.json"
    try:
        expected = json.loads(lock_path.read_text(encoding="utf-8"))["productVersion"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    result = subprocess.run([browser, "--product-version"], check=False, capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == expected


def _identity_kwargs() -> dict[str, str]:
    return {
        "project_id": "sample-hfvi-product",
        "namespace": "com.examplecorp.samplehfvi",
        "display_name": "Sample HFVI Product",
        "initial_version": "0.1.0",
        "license_id": "Apache-2.0",
        "copyright": "2026 Example Corp",
        "license_text": "Licensed under the Apache License, Version 2.0; you may not use this file except in compliance with the License.",
    }


class LeaferTemplateTests(unittest.TestCase):
    def _create_repo(self, tmp_root: Path) -> Path:
        master_doc = tmp_root / "master_doc.md"
        ui_spec = tmp_root / "ui_spec.md"
        master_doc.write_text(
            "# Master Doc\n\n"
            "## Conformance profile\n\n"
            "## Repo topology\n\n"
            "## Contracts\n\n"
            "## Traceability\n\n"
            "## Verification\n\n"
            "## Execution plan\n\n"
            "interactionProfile: hfvi_canvas_webgl_game\n",
            encoding="utf-8",
        )
        ui_spec.write_text("# UI Spec\n", encoding="utf-8")
        dest = tmp_root / "product"
        return create_product_repo(
            factory_root=REPO_ROOT,
            dest_dir=dest,
            master_doc_path=master_doc,
            ui_spec_path=ui_spec,
            change_id="chg-001",
            intent="Initial scaffold",
            init_git=True,
            **_identity_kwargs(),
        )

    def test_cli_help_and_template_seed_contract(self) -> None:
        help_proc = subprocess.run(
            ["python3", "-m", "dasleafer", "--help"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.assertEqual(help_proc.returncode, 0, help_proc.stdout)
        self.assertIn("create", help_proc.stdout)

        delegate_help = subprocess.run(
            ["python3", "-m", "dasleafer", "lock-status", "--help"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.assertEqual(delegate_help.returncode, 0, delegate_help.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._create_repo(Path(tmp_dir))
            self.assertTrue((repo / "STANDARD_REF.md").exists())
            self.assertTrue((repo / "tooling_lock.json").exists())
            self.assertTrue((repo / "local_extension_manifest.json").exists())
            self.assertFalse((repo / "docs" / "standards" / "DAS_STANDARD.md").exists())
            agents_override = (repo / "AGENTS.override.md").read_text(encoding="utf-8")
            self.assertIn("STANDARD_REF.md", agents_override)
            self.assertNotIn("docs/standards/DAS_STANDARD.md", agents_override)
            cadence_yaml = (repo / "cadence.yaml").read_text(encoding="utf-8")
            self.assertIn("core-v140-baseline", cadence_yaml)
            legacy_baseline = "unified" + "-current-baseline"
            self.assertNotIn(legacy_baseline, cadence_yaml)

    def test_legacy_modules_delegate_to_dasops(self) -> None:
        self.assertTrue(leafer_adopt.audit_repo.__module__.startswith("dasops."))
        self.assertTrue(leafer_doctor.run_doctor.__module__.startswith("dasops."))
        self.assertTrue(leafer_locks.claim_task.__module__.startswith("dasops."))
        self.assertTrue(leafer_tasks.read_task_hints.__module__.startswith("dasops."))
        self.assertTrue(leafer_repo_factory.new_change.__module__.startswith("dasops."))
        self.assertEqual(
            leafer_repo_factory.create_product_repo_from_template.__module__,
            "dasleafer.repo_factory",
        )
        self.assertEqual(leafer_tasks.DRAFT_MARKER, "DASOPS:DRAFT")

    def test_delegate_executes_exactly_one_locked_python_module_command(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        class Result:
            returncode = 23

        def fake_run(command: list[str], **kwargs: object) -> Result:
            calls.append((command, kwargs))
            return Result()

        with patch.object(leafer_main.subprocess, "run", side_effect=fake_run):
            self.assertEqual(leafer_main._delegate_to_dasops(["status"]), 23)

        self.assertEqual(calls, [([sys.executable, "-m", "dasops", "status"], {"check": False})])

    def test_missing_dasops_dependency_never_falls_back_to_a_sibling_checkout(self) -> None:
        with patch.object(dasops_bridge.importlib.util, "find_spec", return_value=None):
            with self.assertRaisesRegex(ModuleNotFoundError, "declared dasops package release"):
                dasops_bridge.ensure_dasops_importable()

    @unittest.skipUnless(_locked_hfvi_browser_available(), "requires the exact browser version in hfvi/browser.lock.json")
    def test_generated_repo_root_verify_and_hfvi_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._create_repo(Path(tmp_dir))

            verify = subprocess.run(
                ["bash", "./scripts/verify"],
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stdout)

            contracts = subprocess.run(
                ["bash", "./scripts/verify-contracts"],
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertEqual(contracts.returncode, 0, contracts.stdout)
            self.assertIn("starter HFVI contract", contracts.stdout)

            hfvi = subprocess.run(
                ["bash", "./scripts/verify-hfvi"],
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertEqual(hfvi.returncode, 0, hfvi.stdout)

            vis = repo / "docs" / "appendices" / "APPENDIX_K_VIS.md"
            text = vis.read_text(encoding="utf-8")
            vis.write_text(text.replace("## 8. HFVI asset declarations", "## 8. Removed"), encoding="utf-8")

            broken = subprocess.run(
                ["bash", "./scripts/verify-hfvi"],
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertNotEqual(broken.returncode, 0)
            self.assertIn("required VIS section", broken.stdout)

    @unittest.skipUnless(_locked_hfvi_browser_available(), "requires the exact browser version in hfvi/browser.lock.json")
    def test_hfvi_browser_replay_rejects_event_and_ui_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._create_repo(Path(tmp_dir))
            tape_path = repo / "hfvi" / "tapes" / "baseline.json"
            frontend_path = repo / "frontend" / "src" / "main.ts"

            tape = json.loads(tape_path.read_text(encoding="utf-8"))
            tape["events"][0]["dx"] = 3
            tape_path.write_text(json.dumps(tape, indent=2) + "\n", encoding="utf-8")
            changed_event = subprocess.run(
                ["bash", "./scripts/verify-hfvi"],
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertNotEqual(changed_event.returncode, 0, changed_event.stdout)
            self.assertIn("HFVI state diff", changed_event.stdout)

            tape["events"][0]["dx"] = 2
            tape_path.write_text(json.dumps(tape, indent=2) + "\n", encoding="utf-8")
            frontend = frontend_path.read_text(encoding="utf-8")
            self.assertIn("'#0b5fff'", frontend)
            frontend_path.write_text(frontend.replace("'#0b5fff'", "'#ff00ff'"), encoding="utf-8")
            changed_ui = subprocess.run(
                ["bash", "./scripts/verify-hfvi"],
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self.assertNotEqual(changed_ui.returncode, 0, changed_ui.stdout)
            self.assertIn("HFVI pixel diff", changed_ui.stdout)
            self.assertTrue((repo / ".cadence" / "out" / "hfvi" / "baseline.diff.png").is_file())

    def test_vendor_installer_preserves_existing_vendor_until_a_locked_stage_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo = self._create_repo(root)
            release_root = root / "release"
            (release_root / "das-suite").mkdir(parents=True)
            source = release_root / "cadence-oss"
            source.mkdir()
            (source / "README.md").write_text("local-only Cadence source\n", encoding="utf-8")

            existing = repo / "vendor" / "cadence"
            existing.mkdir(parents=True)
            sentinel = existing / "preserve-me"
            sentinel.write_text("do not replace before validation", encoding="utf-8")

            normal = subprocess.run(
                ["bash", "./scripts/install_cadence_vendor.sh", "--from-suite", str(release_root / "das-suite"), "--tier", "oss", "--force"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(normal.returncode, 0, normal.stdout + normal.stderr)
            self.assertTrue(sentinel.exists(), normal.stdout + normal.stderr)

            ci_env = os.environ.copy()
            ci_env.update({"CI": "1", "DAS_LEAFER_ALLOW_UNSAFE_VENDOR": "1"})
            prohibited = subprocess.run(
                ["bash", "./scripts/install_cadence_vendor.sh", "--from-suite", str(release_root / "das-suite"), "--tier", "oss", "--force", "--unsafe-development-override"],
                cwd=repo,
                env=ci_env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(prohibited.returncode, 0, prohibited.stdout + prohibited.stderr)
            self.assertIn("Unsafe Cadence vendoring is prohibited", prohibited.stderr)
            self.assertTrue(sentinel.exists(), prohibited.stdout + prohibited.stderr)

            developer_env = os.environ.copy()
            # This phase models a local developer, independent of the test runner.
            developer_env.pop("CI", None)
            developer_env.pop("DAS_RELEASE_PROFILE", None)
            developer_env["DAS_LEAFER_ALLOW_UNSAFE_VENDOR"] = "1"
            installed = subprocess.run(
                ["bash", "./scripts/install_cadence_vendor.sh", "--from-suite", str(release_root / "das-suite"), "--tier", "oss", "--force", "--unsafe-development-override"],
                cwd=repo,
                env=developer_env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            receipt = json.loads((repo / "vendor" / "cadence" / ".cadence-vendor-lock.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["mode"], "development-override")
            self.assertTrue((repo / "vendor" / "cadence" / "cadence-oss" / "README.md").exists())
            self.assertFalse((repo / "vendor" / "cadence" / "cadence-oss" / ".git").exists())

            wrapper = subprocess.run(
                ["bash", "./cadencew", "version"],
                cwd=repo,
                env=developer_env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(wrapper.returncode, 0, wrapper.stdout + wrapper.stderr)
            self.assertNotIn("globally", wrapper.stdout + wrapper.stderr)

    def test_created_repo_passes_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = self._create_repo(Path(tmp_dir))
            audit_result = leafer_adopt.audit_repo(repo)
            self.assertEqual(
                audit_result.findings,
                [],
                f"generated repo has audit findings: {audit_result.findings}",
            )
