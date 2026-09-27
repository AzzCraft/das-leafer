"""Exercise the real archive and complete-asset comparison workflow steps."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("artifact_builder_tests", SOURCE / "scripts/release/build_release_artifacts.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


def fixture_report() -> dict:
    """Synthetic pip metadata for offline build/comparison tests, not approvals."""
    decisions = json.loads((SOURCE / "release/dependency_license_decisions.json").read_text())
    rows = [row for row in decisions["dependencies"] if row["name"].lower() != "dasops"]
    rows.append({"name": "fixture-dependency", "version": "1.0", "license": "MIT"})
    return {"version": "1", "environment": {"platform_version": "runner one"}, "install": [
        {"metadata": {"name": row["name"], "version": row["version"], "license_expression": row["license"]},
         "download_info": {"url": "https://example.invalid/" + row["name"] + ".whl",
                           "archive_info": {"hashes": {"sha256": hashlib.sha256((row["name"] + row["version"]).encode()).hexdigest()}}}}
        for row in rows]}


def test_trusted_archive_and_source_bound_dependency_sbom(tmp_path: Path) -> None:
    repo = tmp_path / "public-source"
    shutil.copytree(SOURCE, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache", "node_modules", "build", "dist", "*.egg-info"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Artifact test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "test source"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Artifact test", "-c", "user.email=test@example.invalid", "-c", "tag.gpgsign=false", "tag", "-a", "v1.0.0", "-m", "local fixture"], check=True)
    artifacts = tmp_path / "artifacts"
    commit = git(repo, "rev-parse", "HEAD")
    tag_object = git(repo, "rev-parse", "v1.0.0")

    def build(output: Path, report: dict, *, indent=None) -> None:
        report_path = output.with_suffix(".report.json")
        report_path.write_text(json.dumps(report, indent=indent))
        subprocess.run([sys.executable, str(repo / "scripts/release/build_release_artifacts.py"), "--source", str(repo), "--out", str(output), "--version", "1.0.0", "--tag", "v1.0.0", "--tag-object", tag_object, "--commit", commit, "--resolved-dependencies", str(report_path)], check=True, capture_output=True, text=True)

    report = fixture_report()
    build(artifacts, report)
    workflow = yaml.safe_load((repo / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    steps = {step.get("id"): step for step in workflow["jobs"]["attest"]["steps"]}
    environment = {**os.environ, "VERSION": "1.0.0", "COMMIT": commit, "TAG_OBJECT": tag_object, "ARTIFACT_DIR": str(artifacts), "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "step-output")}
    subprocess.run(["bash", "-e", "-o", "pipefail"], input=steps["trusted_artifact"]["run"], cwd=repo, env=environment, check=True, capture_output=True, text=True)
    assert (artifacts / "das-leafer-1.0.0-source.tar.gz").read_bytes() == (tmp_path / "rebuilt-source.tar.gz").read_bytes()
    sbom = json.loads((artifacts / "das-leafer-1.0.0-dependencies.spdx.json").read_text(encoding="utf-8"))
    package = next(row for row in sbom["packages"] if row["name"] == "dasops")
    lock = json.loads((repo / "release/DEPENDENCY_LOCK.json").read_text(encoding="utf-8"))["dependencies"]["dasops"]
    identity = lock["releaseIdentity"]
    assert package["downloadLocation"] == f"git+https://github.com/AzzCraft/dasops.git@{identity['targetCommit']}"
    source = json.loads(package["sourceInfo"])
    assert source["candidateTreeSha256"] == lock["candidateTreeSha256"]
    assert source["tagObjectSha1"] == identity["tagObject"]
    assert source["gitTreeSha1"] == identity["tree"]

    independent = copy.deepcopy(report)
    independent["environment"] = {"platform_version": "runner two", "platform_release": "different kernel"}
    independent["install"].reverse()
    for row in independent["install"]:
        row["download_info"]["url"] = row["download_info"]["url"].replace("example.invalid", "mirror.invalid")
    rebuilt = tmp_path / "rebuilt"
    build(rebuilt, independent, indent=4)

    def compare(output: Path):
        return subprocess.run(["bash", "-e", "-o", "pipefail"], input=steps["trusted_release_artifacts"]["run"], cwd=repo, env={**environment, "REBUILT_ARTIFACT_DIR": str(output)}, capture_output=True, text=True)

    comparison = compare(rebuilt)
    assert comparison.returncode == 0, comparison.stdout + comparison.stderr
    assert {p.name: p.read_bytes() for p in artifacts.iterdir()} == {p.name: p.read_bytes() for p in rebuilt.iterdir()}
    manifest = json.loads((artifacts / "release-manifest.json").read_text())
    assert manifest["resolvedDependenciesSha256"] == hashlib.sha256((artifacts / "resolved-dependencies.json").read_bytes()).hexdigest()
    assert "resolvedDependenciesReportSha256" not in manifest
    for field in ("version", "sha256"):
        drifted = copy.deepcopy(report)
        row = next(row for row in drifted["install"] if row["metadata"]["name"] == "fixture-dependency")
        if field == "version":
            row["metadata"]["version"] = "2.0"
        else:
            row["download_info"]["archive_info"]["hashes"]["sha256"] = "f" * 64
        changed = tmp_path / ("changed-" + field)
        build(changed, drifted)
        assert compare(changed).returncode != 0, f"changed package {field} must fail trusted comparison"


@pytest.mark.parametrize("mutation", [
    lambda report: report.update(version="unsupported"),
    lambda report: report.update(install=[]),
    lambda report: report["install"][0].pop("download_info"),
    lambda report: report["install"][0]["download_info"]["archive_info"].update(hashes={}),
    lambda report: report["install"][0]["download_info"]["archive_info"]["hashes"].update(sha256="not-a-digest"),
    lambda report: report["install"].append(copy.deepcopy(report["install"][0])),
])
def test_unbound_dependency_inputs_are_rejected(tmp_path, mutation):
    report = fixture_report()
    mutation(report)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        builder.resolved_dependency_inputs(path)
