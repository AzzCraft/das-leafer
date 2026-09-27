from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests._root_contract import repository_root_for_test_file

from dasleafer.preset import create_product_repo


REPO_ROOT = repository_root_for_test_file(__file__)
DASOPS_ROOT = Path(os.environ.get("DASLEAFER_DASOPS_ROOT", str(REPO_ROOT.parent / "dasops")))


def _release_builder_module():
    path = REPO_ROOT / "scripts" / "release" / "build_release_artifacts.py"
    spec = importlib.util.spec_from_file_location("das_leafer_release_builder", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load the release artifact builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{DASOPS_ROOT}"
    return env


def _write_minimum_docs(root: Path) -> tuple[Path, Path]:
    master_doc = root / "master_doc.md"
    ui_spec = root / "ui_spec.md"
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
    return master_doc, ui_spec


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


class LeaferRemediationSpecTests(unittest.TestCase):
    # --- LEAFER-008: public-release artifacts are self-contained and fail closed ---
    def test_leafer_008_release_builder_reads_python_310_compatible_exact_dependencies(self) -> None:
        builder = _release_builder_module()
        dependencies = builder.load_license_decisions(REPO_ROOT, None)
        names = {row["name"].lower(): row["version"] for row in dependencies}
        self.assertEqual(names["dasops"], "1.0.0")
        self.assertEqual(names["pyyaml"], "6.0.3")
        self.assertEqual(names["build"], "1.2.2")
        self.assertNotIn("import tomllib", (REPO_ROOT / "scripts" / "release" / "build_release_artifacts.py").read_text(encoding="utf-8"))

    def test_release_inventory_binds_source_runtime_when_pip_only_reports_tools(self) -> None:
        builder = _release_builder_module()
        rows = builder.load_license_decisions(REPO_ROOT, None)
        report = {"install": [{"metadata": {"name": row["name"], "version": row["version"]}} for row in rows if row["name"] != "dasops"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resolved.json"
            path.write_text(json.dumps(report))
            resolved = builder.load_license_decisions(REPO_ROOT, path)
            runtime = next(row for row in resolved if row["name"] == "dasops")
            self.assertIn("Source SHA256:", runtime["notice"])
            report["install"] = [row for row in report["install"] if row["metadata"]["name"] != "build"]
            path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                builder.load_license_decisions(REPO_ROOT, path)

    def test_leafer_008_release_builder_uses_the_bound_git_archive(self) -> None:
        text = (REPO_ROOT / "scripts" / "release" / "build_release_artifacts.py").read_text(encoding="utf-8")
        for required in (
            "release tag object does not match requested tag object",
            "release tag must be annotated",
            "release tag does not target the requested commit",
            "extract_archived_source(source_tar, first_root)",
            "extract_archived_source(source_tar, second_root)",
            "Python sdist/wheel builds are not reproducible",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

    def test_leafer_008_release_workflow_requires_signer_rebuild_and_attestation(self) -> None:
        text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for required in (
            "verify_tag_signer.py",
            "RELEASE_SIGNER_FINGERPRINT",
            "RELEASE_SIGNER_PUBLIC_KEY",
            "--resolved-dependencies",
            "build_release_artifacts.py",
            "Independently rebuild all release assets",
            "Bind independently rebuilt release assets",
            "subject-path: \"${{ steps.trusted_release_artifacts.outputs.manifest }}\"",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        self.assertNotIn("pip install --upgrade pip", text)

    def test_leafer_008_removes_stale_nonowning_public_artifacts(self) -> None:
        stale_paths = (
            "SBOM.spdx.json",
            "attestations/release.intoto.jsonl",
            "update_repo/manifest.json",
            "update_repo/metadata/root.json",
            "pilot/gov/README.md",
            "docs/release/COMMERCIAL_GO_NO_GO.md",
            "docs/customer/SUPPLIER_TOOLKIT/README.md",
            "training/certification/README.md",
        )
        for relative in stale_paths:
            with self.subTest(relative=relative):
                self.assertFalse((REPO_ROOT / relative).exists(), f"stale non-owning artifact remains: {relative}")

    def test_leafer_008_notices_and_license_policy_point_to_exact_release_input(self) -> None:
        notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        matrix = (REPO_ROOT / "docs" / "legal" / "LICENSE_MATRIX.md").read_text(encoding="utf-8")
        self.assertIn("build_release_artifacts.py", notices)
        self.assertIn("dependency_license_decisions.json", matrix)

    def test_leafer_008_declared_dasops_v1_does_not_require_newer_factory_api(self) -> None:
        factory = (REPO_ROOT / "dasleafer" / "repo_factory.py").read_text(encoding="utf-8")
        self.assertIn('getattr(_dasops_repo_factory, "finalize_bootstrap_provenance", None)', factory)
        self.assertIn("Leafer cannot claim that it supports that exact", factory)

    def test_leaf_001_git_bootstrap_pin_is_reachable_and_tree_is_clean_after_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            master_doc, ui_spec = _write_minimum_docs(tmp_root)
            repo = create_product_repo(
                factory_root=REPO_ROOT,
                dest_dir=tmp_root / "product",
                master_doc_path=master_doc,
                ui_spec_path=ui_spec,
                init_git=True,
                **_identity_kwargs(),
            )

            payload = json.loads((repo / "tooling_lock.json").read_text(encoding="utf-8"))
            pin_value = payload["sourceOfTruth"]["pinValue"]
            head = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                text=True,
            ).strip()

            self.assertNotEqual(pin_value, head)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(repo), "merge-base", "--is-ancestor", pin_value, head],
                    check=False,
                ).returncode,
                0,
            )
            self.assertNotEqual(pin_value, "replace-with-product-commit")
            self.assertEqual(
                subprocess.check_output(
                    ["git", "-C", str(repo), "status", "--porcelain"],
                    text=True,
                ),
                "",
            )

    def test_leaf_002_verify_and_doctor_reject_placeholder_pin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            master_doc, ui_spec = _write_minimum_docs(tmp_root)
            repo = create_product_repo(
                factory_root=REPO_ROOT,
                dest_dir=tmp_root / "product",
                master_doc_path=master_doc,
                ui_spec_path=ui_spec,
                init_git=False,
                **_identity_kwargs(),
            )

            lock_path = repo / "tooling_lock.json"
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            payload["sourceOfTruth"]["pinValue"] = "replace-with-product-commit"
            lock_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            verify = subprocess.run(
                ["bash", "scripts/verify"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            doctor = subprocess.run(
                [sys.executable, "-m", "dasops", "doctor", "--repo-root", str(repo)],
                cwd=DASOPS_ROOT,
                env=_base_env(),
                check=False,
                capture_output=True,
                text=True,
            )

            combined = verify.stdout + verify.stderr + doctor.stdout + doctor.stderr
            self.assertNotEqual(verify.returncode, 0, combined)
            self.assertNotEqual(doctor.returncode, 0, combined)
            self.assertIn("pinValue", combined)

    def test_leaf_001_no_git_generation_marks_pin_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            master_doc, ui_spec = _write_minimum_docs(tmp_root)
            repo = create_product_repo(
                factory_root=REPO_ROOT,
                dest_dir=tmp_root / "product",
                master_doc_path=master_doc,
                ui_spec_path=ui_spec,
                init_git=False,
                **_identity_kwargs(),
            )

            payload = json.loads((repo / "tooling_lock.json").read_text(encoding="utf-8"))
            source = payload["sourceOfTruth"]
            self.assertEqual(source.get("pinState"), "pending")
            self.assertNotIn("pinValue", source)

    def test_leaf_003_verify_rejects_template_docs_placeholder_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            repo = create_product_repo(
                factory_root=REPO_ROOT,
                dest_dir=tmp_root / "product",
                master_doc_path=REPO_ROOT / "templates" / "das-leafer-product" / "docs" / "master_doc.md",
                ui_spec_path=REPO_ROOT / "templates" / "das-leafer-product" / "docs" / "ui_spec.md",
                init_git=False,
                **_identity_kwargs(),
            )

            result = subprocess.run(
                ["bash", "scripts/verify"],
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
            )
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, combined)
            self.assertTrue(
                "unresolved" in combined
                or "pinState is pending" in combined
                or "must be a real git commit" in combined,
                combined,
            )

    # --- LEAF-VENDOR-001 (completed): template lock has no placeholder pins ---
    def test_leaf_vendor_001_template_lock_no_placeholder_pins(self) -> None:
        lock_path = REPO_ROOT / "templates" / "das-leafer-product" / "tooling_lock.json"
        self.assertTrue(lock_path.exists(), "template tooling_lock.json missing")
        text = lock_path.read_text(encoding="utf-8")
        forbidden = ["replace-with-product-commit", "fake-sha256", "0000000", "PLACEHOLDER", "TODO"]
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, text, f"Lock file contains placeholder: {pattern}")
        lock = json.loads(text)
        sot = lock.get("sourceOfTruth", {})
        self.assertNotIn("pinValue", sot)
        self.assertEqual(sot.get("pinState"), "template")

    def test_leaf_vendor_001_vendor_install_script_fail_closed(self) -> None:
        script_path = REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "install_cadence_vendor.sh"
        self.assertTrue(script_path.exists(), "install_cadence_vendor.sh missing")
        text = script_path.read_text(encoding="utf-8")
        self.assertIn(
            "Clone mode requires --git-base, --org, or DAS_SUITE_GIT_BASE.",
            text,
        )
        self.assertNotIn("https://github.com/<ORG>", text)

    # --- LEAFER-005: exact release identities and explicit local-only override ---
    def test_leafer_005_vendor_boundary_is_locked_and_fail_closed(self) -> None:
        template = REPO_ROOT / "templates" / "das-leafer-product"
        installer = (template / "scripts" / "install_cadence_vendor.sh").read_text(encoding="utf-8")
        wrapper = (template / "cadencew").read_text(encoding="utf-8")
        lock = json.loads((template / "tooling_lock.json").read_text(encoding="utf-8"))

        for required in (
            "mktemp -d",
            "targetCommit",
            "tagObject",
            "release/vendor-identity.json",
            "trustedIdentitySigners",
            "--unsafe-development-override",
            "development-override",
            "canonical_content_sha256",
        ):
            with self.subTest(required=required):
                self.assertIn(required, installer)
        self.assertNotIn('rm -rf "$VENDOR_DIR"', installer)
        self.assertNotIn("command -v cadence", wrapper)
        for required in (".cadence-vendor-lock.json", "sha256sum", "DAS_LEAFER_ALLOW_UNSAFE_VENDOR"):
            with self.subTest(wrapper_required=required):
                self.assertIn(required, wrapper)

        identity = lock["cadenceVendor"]["repositories"]["cadence-oss"]
        self.assertEqual(identity["publication"]["status"], "blocked")
        for field in ("tag", "tagObject", "targetCommit", "tree"):
            with self.subTest(lock_field=field):
                self.assertTrue(identity[field])

    # --- LEAFER-006: generated projects must bind user-selected identities ---
    def test_leafer_006_identity_version_and_license_are_required_and_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            master_doc, ui_spec = _write_minimum_docs(tmp_root)
            invalid = _identity_kwargs()
            invalid["namespace"] = "org.example.project"
            with self.assertRaisesRegex(ValueError, "non-example dotted namespace"):
                create_product_repo(
                    factory_root=REPO_ROOT,
                    dest_dir=tmp_root / "invalid",
                    master_doc_path=master_doc,
                    ui_spec_path=ui_spec,
                    init_git=False,
                    **invalid,
                )

            repo = create_product_repo(
                factory_root=REPO_ROOT,
                dest_dir=tmp_root / "product",
                master_doc_path=master_doc,
                ui_spec_path=ui_spec,
                init_git=True,
                **_identity_kwargs(),
            )
            identity = json.loads((repo / "project_identity.json").read_text(encoding="utf-8"))
            self.assertEqual(identity["projectId"], "sample-hfvi-product")
            self.assertEqual((repo / "VERSION").read_text(encoding="utf-8").strip(), "0.1.0")
            self.assertIn("SPDX-License-Identifier: Apache-2.0", (repo / "LICENSE").read_text(encoding="utf-8"))
            self.assertNotIn("{{", (repo / "README.md").read_text(encoding="utf-8"))
            self.assertEqual(
                subprocess.run(["bash", "scripts/verify"], cwd=repo, check=False, capture_output=True, text=True).returncode,
                0,
            )

            frontend_path = repo / "frontend" / "package.json"
            frontend = json.loads(frontend_path.read_text(encoding="utf-8"))
            frontend["license"] = "UNLICENSED"
            frontend_path.write_text(json.dumps(frontend, indent=2) + "\n", encoding="utf-8")
            tampered = subprocess.run(["bash", "scripts/verify"], cwd=repo, check=False, capture_output=True, text=True)
            self.assertNotEqual(tampered.returncode, 0, tampered.stdout + tampered.stderr)
            self.assertIn("frontend/package.json does not match", tampered.stdout + tampered.stderr)

    def test_leafer_006_cli_requires_identity_and_license_inputs(self) -> None:
        help_proc = subprocess.run(
            [sys.executable, "-m", "dasleafer", "create", "--help"],
            cwd=REPO_ROOT,
            env=_base_env(),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(help_proc.returncode, 0, help_proc.stdout + help_proc.stderr)
        for option in ("--project-id", "--namespace", "--display-name", "--initial-version", "--license-id", "--license-file", "--copyright"):
            with self.subTest(option=option):
                self.assertIn(option, help_proc.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            master_doc, ui_spec = _write_minimum_docs(tmp_root)
            license_path = tmp_root / "APACHE-LICENSE.txt"
            license_path.write_text(
                "Licensed under the Apache License, Version 2.0; you may not use this file except in compliance with the License.\n",
                encoding="utf-8",
            )
            created = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "dasleafer",
                    "create",
                    "--dest",
                    str(tmp_root / "product"),
                    "--master-doc",
                    str(master_doc),
                    "--ui-spec",
                    str(ui_spec),
                    "--project-id",
                    "cli-hfvi-product",
                    "--namespace",
                    "io.examplecorp.clihfvi",
                    "--display-name",
                    "CLI HFVI Product",
                    "--initial-version",
                    "0.2.0",
                    "--license-id",
                    "Apache-2.0",
                    "--license-file",
                    str(license_path),
                    "--copyright",
                    "2026 Example Corp",
                ],
                cwd=REPO_ROOT,
                env=_base_env(),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            self.assertEqual(
                json.loads((tmp_root / "product" / "project_identity.json").read_text(encoding="utf-8"))["projectId"],
                "cli-hfvi-product",
            )

    # --- DL-002/DL-003 (historical closure): no unresolved template URIs ---
    def test_dl_002_003_no_unresolved_template_uris(self) -> None:
        factory_py = REPO_ROOT / "dasleafer" / "repo_factory.py"
        self.assertTrue(factory_py.exists())
        text = factory_py.read_text(encoding="utf-8")
        self.assertNotIn("<ORG>/<PRODUCT_REPO>", text)
        self.assertNotIn("<ORG>/", text)

    # --- LEAF-002 deep: verify script has semantic pin validation code ---
    def test_leaf_002_verify_script_has_pin_validation(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertIn("sourceOfTruth", text)
        self.assertIn("pinValue", text)
        self.assertIn("commit", text)

    # --- LEAF-003 deep: verify script scans APPENDIX_K_VIS ---
    def test_leaf_003_verify_script_scans_appendix_k(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertIn("APPENDIX_K_VIS", text)
        self.assertIn("unresolved", text)

    # --- LEAF-001 matrix exact: template tooling_lock pinValue != placeholder ---
    def test_leaf_001_template_tooling_lock_pin_not_placeholder(self) -> None:
        payload = json.loads(
            (REPO_ROOT / "templates" / "das-leafer-product" / "tooling_lock.json").read_text(encoding="utf-8")
        )
        pin = payload.get("sourceOfTruth", {}).get("pinValue", "")
        self.assertNotEqual(pin, "replace-with-product-commit")

    # --- LEAF depth: das-leafer has LICENSE ---
    def test_leaf_license_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "LICENSE").exists())

    # --- LEAF depth: CHANGELOG exists ---
    def test_leaf_changelog_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "CHANGELOG.md").exists())

    # --- LEAF depth: template verify script uses safe path handling ---
    def test_leaf_verify_uses_safe_paths(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertTrue(
            "ROOT" in text or "REPO_ROOT" in text or "resolve" in text,
            "verify script must reference repo root for path safety",
        )

    # --- LEAF depth: template docs directory has master_doc.md ---
    def test_leaf_template_docs_have_master_doc(self) -> None:
        self.assertTrue(
            (REPO_ROOT / "templates" / "das-leafer-product" / "docs" / "master_doc.md").exists()
        )

    # --- LEAF depth: das-leafer has LICENSE ---
    def test_leaf_license_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "LICENSE").exists())

    # --- LEAF depth: CHANGELOG exists ---
    def test_leaf_changelog_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "CHANGELOG.md").exists())

    # --- LEAF depth: template verify script uses safe path handling ---
    def test_leaf_verify_uses_safe_paths(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertTrue(
            "ROOT" in text or "REPO_ROOT" in text or "resolve" in text,
            "verify script must reference repo root for path safety",
        )

    # --- LEAF depth: template docs directory has master_doc.md ---
    def test_leaf_template_docs_have_master_doc(self) -> None:
        self.assertTrue(
            (REPO_ROOT / "templates" / "das-leafer-product" / "docs" / "master_doc.md").exists()
        )

    # --- V9 Item 05: das-leafer is thin overlay over dasops ---

    def test_v9_05_readme_states_dasops_delegation(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue(
            "delegate to `dasops`" in readme or "delegate to dasops" in readme.lower(),
            "README no longer states dasops delegation",
        )

    def test_v9_05_main_has_delegated_commands(self) -> None:
        main_py = (REPO_ROOT / "dasleafer" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn("DELEGATED_COMMANDS", main_py)

    def test_v9_05_expected_delegated_commands(self) -> None:
        main_py = (REPO_ROOT / "dasleafer" / "__main__.py").read_text(encoding="utf-8")
        expected = [
            "init", "new-change", "status", "doctor", "list-tasks",
            "claim-task", "claim-ready", "complete-task", "release-task",
            "lock-status", "start-task", "prompt",
        ]
        for cmd in expected:
            with self.subTest(cmd=cmd):
                self.assertIn(f'"{cmd}"', main_py)

    def test_v9_05_delegates_to_python_m_dasops(self) -> None:
        main_py = (REPO_ROOT / "dasleafer" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn(
            'python_delegate = [sys.executable, "-m", "dasops"',
            main_py,
            "__main__.py must use exact delegation pattern: python_delegate = [sys.executable, '-m', 'dasops']",
        )

    # --- V9 Item 06 (P1-02): AGENTS.override.md references STANDARD_REF.md ---

    def test_v9_06_agents_override_no_old_standard_path(self) -> None:
        agents = REPO_ROOT / "templates" / "das-leafer-product" / "AGENTS.override.md"
        text = agents.read_text(encoding="utf-8")
        self.assertNotIn("docs/standards/DAS_STANDARD.md", text)

    def test_v9_06_agents_override_references_standard_ref(self) -> None:
        agents = REPO_ROOT / "templates" / "das-leafer-product" / "AGENTS.override.md"
        text = agents.read_text(encoding="utf-8")
        self.assertIn("STANDARD_REF.md", text)

    def test_v9_06_no_copied_standard_in_template(self) -> None:
        self.assertFalse(
            (REPO_ROOT / "templates" / "das-leafer-product" / "docs" / "standards" / "DAS_STANDARD.md").exists(),
            "template still contains copied standard document",
        )

    def test_v9_06_template_files_consistent_standard_ref(self) -> None:
        template = REPO_ROOT / "templates" / "das-leafer-product"
        files = {
            "README.md": template / "README.md",
            "VERIFY_REQUIREMENTS.md": template / "VERIFY_REQUIREMENTS.md",
            "openspec/config.yaml": template / "openspec" / "config.yaml",
            "AGENTS.override.md": template / "AGENTS.override.md",
        }
        for name, path in files.items():
            if path.exists():
                text = path.read_text(encoding="utf-8")
                with self.subTest(file=name):
                    self.assertIn("STANDARD_REF.md", text)

    # --- Additional Item 05 tests ---

    def test_v9_05_repo_factory_delegates_or_wraps_dasops(self) -> None:
        factory = REPO_ROOT / "dasleafer" / "repo_factory.py"
        if factory.exists():
            text = factory.read_text(encoding="utf-8")
            self.assertTrue(
                "dasops" in text or "from dasops" in text,
                "repo_factory.py should reference dasops, not be a standalone fork",
            )

    # --- Additional Item 06 / P1-02 tests ---

    def test_v9_06_verify_script_audits_agents_override(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertIn("AGENTS.override.md", text,
            "template verify script does not audit AGENTS.override.md")

    def test_v9_06_verify_script_guards_standard_ref(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertIn("STANDARD_REF.md", text,
            "template verify script does not enforce STANDARD_REF.md linkage")

    def test_v9_06_verify_script_guards_legacy_standard_path(self) -> None:
        text = (REPO_ROOT / "templates" / "das-leafer-product" / "scripts" / "verify").read_text(encoding="utf-8")
        self.assertIn("docs/standards/DAS_STANDARD.md", text,
            "template verify script does not guard against legacy copied standard path")

    def test_p1_02_test_leafer_covers_agents_override(self) -> None:
        test_text = (REPO_ROOT / "tests" / "test_leafer.py").read_text(encoding="utf-8")
        self.assertIn("AGENTS.override.md", test_text,
            "test_leafer.py does not cover AGENTS.override.md")
        self.assertIn("STANDARD_REF.md", test_text,
            "test_leafer.py does not verify STANDARD_REF.md reference")

    def test_p1_02_no_expected_failure_masks_remediation_specs(self) -> None:
        test_text = (REPO_ROOT / "tests" / "test_remediation_specs.py").read_text(encoding="utf-8")
        self.assertNotIn("@unittest." + "expectedFailure", test_text)

    def test_v9_06_vendor_readme_references_standard_ref(self) -> None:
        vendor_readme = REPO_ROOT / "templates" / "das-leafer-product" / "vendor" / "README.md"
        self.assertTrue(vendor_readme.exists(), "vendor README.md missing")
        text = vendor_readme.read_text(encoding="utf-8")
        self.assertIn("STANDARD_REF.md", text)


if __name__ == "__main__":
    unittest.main()
