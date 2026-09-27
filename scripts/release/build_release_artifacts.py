#!/usr/bin/env python3
"""Build deterministic DAS Leafer source and Python release artifacts.

This program is deliberately repository-local: it never delegates release,
notice, SBOM, or provenance generation to a sibling DAS Suite checkout.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
NAME_RE = re.compile(r"[A-Za-z0-9_.-]+\Z")


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.run(command, cwd=str(cwd), env=env, check=True, text=True, capture_output=True).stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def resolved_dependency_inputs(path: Path) -> dict[str, object]:
    """Bind installed package bytes independently of the reporting runner.

    The raw pip report is separate job evidence. Only normalized package names,
    exact versions, and distribution SHA256 hashes enter reproducible assets.
    A report without distribution hashes cannot establish this identity.
    """
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("version") != "1":
        raise ValueError("unsupported pip installation report version")
    installed = report.get("install")
    if not isinstance(installed, list) or not installed:
        raise ValueError("pip installation report has no distributions")
    packages = {}
    for item in installed:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(metadata, dict):
            raise ValueError("pip installation report has invalid package metadata")
        name, version = metadata.get("name"), metadata.get("version")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or not isinstance(version, str) or not version.strip():
            raise ValueError("pip installation report lacks a valid package name/version")
        name = re.sub(r"[-_.]+", "-", name).lower()
        if name in packages:
            raise ValueError(f"pip installation report repeats {name}")
        download = item.get("download_info")
        archive = download.get("archive_info") if isinstance(download, dict) else None
        hashes = archive.get("hashes") if isinstance(archive, dict) else None
        digest = hashes.get("sha256") if isinstance(hashes, dict) else None
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"pip distribution {name} requires an archive SHA256")
        packages[name] = {"name": name, "version": version, "sha256": digest}
    return {"schemaVersion": "1.0.0", "packages": [packages[name] for name in sorted(packages)]}


def read_exact_requirements(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"verification dependency must be exactly pinned: {line!r}")
        name, version = (part.strip() for part in line.split("==", 1))
        if not NAME_RE.fullmatch(name) or not version:
            raise ValueError(f"invalid pinned verification dependency: {line!r}")
        values[re.sub(r"[-_.]+", "-", name).lower()] = version
    return values


def read_project_dependencies(path: Path) -> dict[str, str]:
    """Read the deliberately exact runtime dependency list on Python 3.10+.

    ``tomllib`` is only in the Python 3.11 standard library, while DAS Leafer
    supports Python 3.10.  This intentionally small parser accepts the pinned
    ``dependencies`` array used by this repository and fails closed for any
    unrecognised shape rather than adding a build-time parser dependency.
    """
    in_dependencies = False
    project_dependencies: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "dependencies = [":
            if in_dependencies:
                raise ValueError("pyproject.toml repeats the project dependency array")
            in_dependencies = True
            continue
        if not in_dependencies:
            continue
        if line == "]":
            break
        match = re.fullmatch(r'"([^"\\]+)"(?:,)?', line)
        if match is None:
            raise ValueError(f"unrecognised runtime dependency declaration: {line!r}")
        project_dependencies.append(match.group(1))
    else:
        if in_dependencies:
            raise ValueError("pyproject.toml has an unterminated dependency array")
    if not in_dependencies:
        raise ValueError("pyproject.toml has no project dependency array")
    values: dict[str, str] = {}
    for raw in project_dependencies:
        if "==" not in raw:
            raise ValueError(f"runtime dependency must be exactly pinned: {raw!r}")
        name, version = (part.strip() for part in raw.split("==", 1))
        if not NAME_RE.fullmatch(name) or not version:
            raise ValueError(f"invalid runtime dependency: {raw!r}")
        values[re.sub(r"[-_.]+", "-", name).lower()] = version
    return values


def load_license_decisions(root: Path, resolved_report: Path | None) -> list[dict[str, str]]:
    requirements = read_exact_requirements(root / "requirements-verify.txt")
    requirements.update(read_project_dependencies(root / "pyproject.toml"))
    decisions_path = root / "release" / "dependency_license_decisions.json"
    document = json.loads(decisions_path.read_text(encoding="utf-8"))
    allowed = document.get("allowedLicenses")
    rows = document.get("dependencies")
    if document.get("schemaVersion") != "1.0.0" or not isinstance(allowed, list) or not isinstance(rows, list):
        raise ValueError("release/dependency_license_decisions.json has an invalid schema")
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("dependency-license decision must be an object")
        name, version, license_id, notice = (row.get(key) for key in ("name", "version", "license", "notice"))
        if not all(isinstance(value, str) and value for value in (name, version, license_id, notice)):
            raise ValueError("dependency-license decision is incomplete")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in result or license_id not in allowed:
            raise ValueError(f"invalid or denied dependency-license decision: {name!r}")
        result[normalized] = {"name": name, "version": version, "license": license_id, "notice": notice}
    missing = sorted(name for name, version in requirements.items() if result.get(name, {}).get("version") != version)
    extras = sorted(name for name in result if name not in requirements)
    if missing or extras:
        raise ValueError(f"dependency license decisions do not exactly match pinned dependencies; missing={missing}, extras={extras}")
    direct = [result[name] for name in sorted(result)]
    if resolved_report is None:
        return direct
    report = json.loads(resolved_report.read_text(encoding="utf-8"))
    installed = report.get("install") if isinstance(report, dict) else None
    if not isinstance(installed, list) or not installed:
        raise ValueError("pip resolved-dependencies report has no installed distributions")
    aliases = {
        "apache software license": "Apache-2.0",
        "apache license 2.0": "Apache-2.0",
        "apache 2.0": "Apache-2.0",
        "psfl": "PSF-2.0",
        "bsd license": "BSD-3-Clause",
        "mit license": "MIT",
        "psf-2.0": "PSF-2.0",
        "python software foundation license": "PSF-2.0",
    }
    resolved: dict[str, dict[str, str]] = {}
    for item in installed:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(metadata, dict):
            raise ValueError("pip resolved-dependencies report has invalid metadata")
        name, version = metadata.get("name"), metadata.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ValueError("pip resolved-dependencies report lacks name/version")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in resolved:
            raise ValueError(f"pip resolved-dependencies report repeats {name}")
        decided = result.get(normalized)
        if decided:
            if decided["version"] != version:
                raise ValueError(f"resolved {name} version differs from reviewed decision")
            resolved[normalized] = decided
            continue
        candidate = metadata.get("license_expression") or metadata.get("license")
        if not isinstance(candidate, str) or not candidate.strip():
            classifiers = metadata.get("classifier", [])
            candidate = next((entry.rsplit(" :: ", 1)[-1] for entry in classifiers if isinstance(entry, str) and entry.startswith("License :: ")), "")
        if re.sub(r"\s+", " ", str(candidate)).strip().startswith("Apache License Version 2.0, January 2004"):
            candidate = "Apache-2.0"
        normalized_license = aliases.get(str(candidate).strip().lower(), str(candidate).strip())
        if normalized_license not in allowed:
            raise ValueError(f"resolved dependency {name} has unknown or denied license {candidate!r}")
        resolved[normalized] = {"name": name, "version": version, "license": normalized_license, "notice": f"License resolved from the exact pip report: {normalized_license}."}
    # The verification venv deliberately imports DASOps from the independently
    # hash-verified source tree; it is not installed from an arbitrary registry.
    # Bind its SBOM row to the source lock rather than claiming pip installed it.
    if "dasops" not in resolved:
        lock = json.loads((root / "release/DEPENDENCY_LOCK.json").read_text())
        pin = lock.get("dependencies", {}).get("dasops", {})
        if pin.get("version") != result["dasops"]["version"] or not SHA256_RE.fullmatch(str(pin.get("candidateTreeSha256", ""))):
            raise ValueError("DASOps runtime SBOM requires the reviewed source dependency lock")
        resolved["dasops"] = {**result["dasops"], "notice": result["dasops"]["notice"] + " Source SHA256: " + pin["candidateTreeSha256"]}
    missing_direct = sorted(name for name in result if name not in resolved)
    if missing_direct:
        raise ValueError(f"resolved-dependencies report omitted direct reviewed dependencies: {missing_direct}")
    return [resolved[name] for name in sorted(resolved)]


def source_inventory(root: Path, commit: str, repository: str, version: str, source_epoch: int) -> dict[str, object]:
    entries = subprocess.check_output(["git", "ls-tree", "-r", "-z", "--full-tree", commit], cwd=str(root)).split(b"\0")
    files: list[dict[str, object]] = []
    relationships: list[dict[str, str]] = []
    sha1s: list[str] = []
    for index, entry in enumerate(item for item in entries if item):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        if object_type != "blob":
            continue
        data = subprocess.check_output(["git", "cat-file", "blob", object_id], cwd=str(root))
        sha1 = hashlib.sha1(data).hexdigest()
        sha256 = hashlib.sha256(data).hexdigest()
        sha1s.append(sha1)
        spdx_id = f"SPDXRef-File-{index:06d}"
        files.append(
            {
                "SPDXID": spdx_id,
                "checksums": [{"algorithm": "SHA1", "checksumValue": sha1}, {"algorithm": "SHA256", "checksumValue": sha256}],
                "copyrightText": "NOASSERTION",
                "fileName": "./" + raw_path.decode("utf-8", "surrogateescape"),
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
                "noticeText": f"git mode {mode}",
            }
        )
        relationships.append({"spdxElementId": "SPDXRef-Package-Source", "relationshipType": "CONTAINS", "relatedSpdxElement": spdx_id})
    created = datetime.fromtimestamp(source_epoch, timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {"created": created, "creators": ["Tool: DAS Leafer deterministic source SBOM generator"]},
        "dataLicense": "CC0-1.0",
        "documentNamespace": f"https://github.com/AzzCraft/{repository}/sbom/{version}/{commit}",
        "files": files,
        "name": f"{repository}-{version}-source-inventory",
        "packages": [{"SPDXID": "SPDXRef-Package-Source", "copyrightText": "NOASSERTION", "downloadLocation": "NOASSERTION", "filesAnalyzed": True, "licenseConcluded": "Apache-2.0", "licenseDeclared": "Apache-2.0", "name": repository, "packageVerificationCode": {"packageVerificationCodeValue": hashlib.sha1("".join(sorted(sha1s)).encode()).hexdigest()}, "supplier": "Organization: AzzCraft Inc. (重庆艾之舟科技有限公司)", "versionInfo": version}],
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-Source"}, *relationships],
        "spdxVersion": "SPDX-2.3",
    }


def dependency_inventory(repository: str, version: str, dependencies: list[dict[str, str]], source_epoch: int, source_lock: dict[str, Any]) -> dict[str, object]:
    created = datetime.fromtimestamp(source_epoch, timezone.utc).isoformat().replace("+00:00", "Z")
    packages = []
    relationships = [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Package-das-leafer"}]
    pin = source_lock.get("dependencies", {}).get("dasops", {})
    identity = pin.get("releaseIdentity", {})
    for key in ("remote", "tag", "tagObject", "targetCommit", "tree"):
        if not isinstance(identity.get(key), str) or not identity[key]:
            raise ValueError("DASOps SPDX package requires the exact source-release identity")
    tree_digest = pin.get("candidateTreeSha256")
    if not isinstance(tree_digest, str) or not SHA256_RE.fullmatch(tree_digest):
        raise ValueError("DASOps SPDX package requires the governed source-tree digest")
    for index, dependency in enumerate(dependencies):
        spdx_id = f"SPDXRef-Dependency-{index:03d}"
        package = {"SPDXID": spdx_id, "copyrightText": "NOASSERTION", "downloadLocation": "https://pypi.org/project/" + dependency["name"] + "/", "filesAnalyzed": False, "licenseConcluded": dependency["license"], "licenseDeclared": dependency["license"], "name": dependency["name"], "supplier": "NOASSERTION", "versionInfo": dependency["version"]}
        if dependency["name"].lower() == "dasops":
            if dependency["version"] != pin.get("version"):
                raise ValueError("DASOps SPDX package version differs from the source lock")
            # SPDX 2.3 permits a VCS download location. The governed tree digest
            # is a path/mode-aware source inventory hash, not a raw package blob
            # checksum; keep its algorithm and Git identities in sourceInfo.
            package["downloadLocation"] = identity["remote"][:-4].replace("https://", "git+https://") + ".git@" + identity["targetCommit"]
            package["sourceInfo"] = json.dumps({
                "source": "locked-public-git-tree", "tag": identity["tag"],
                "tagObjectSha1": identity["tagObject"], "commitSha1": identity["targetCommit"],
                "gitTreeSha1": identity["tree"], "candidateTreeSha256": tree_digest,
                "candidateTreeHashAlgorithm": "sorted path, git mode, byte length, SHA256 content",
            }, sort_keys=True, separators=(",", ":"))
        packages.append(package)
        relationships.append({"spdxElementId": "SPDXRef-Package-das-leafer", "relationshipType": "DEPENDS_ON", "relatedSpdxElement": spdx_id})
    packages.insert(0, {"SPDXID": "SPDXRef-Package-das-leafer", "copyrightText": "NOASSERTION", "downloadLocation": "NOASSERTION", "filesAnalyzed": False, "licenseConcluded": "Apache-2.0", "licenseDeclared": "Apache-2.0", "name": repository, "supplier": "Organization: AzzCraft Inc. (重庆艾之舟科技有限公司)", "versionInfo": version})
    return {"SPDXID": "SPDXRef-DOCUMENT", "creationInfo": {"created": created, "creators": ["Tool: DAS Leafer dependency/license SBOM generator"]}, "dataLicense": "CC0-1.0", "documentNamespace": f"https://github.com/AzzCraft/{repository}/dependency-sbom/{version}", "name": f"{repository}-{version}-resolved-dependencies", "packages": packages, "relationships": relationships, "spdxVersion": "SPDX-2.3"}


def extract_archived_source(source_tar: bytes, destination: Path) -> None:
    """Materialize only the exact Git tree bound to the release tag."""
    with tarfile.open(fileobj=io.BytesIO(source_tar), mode="r:") as archive:
        members = archive.getmembers()
        if any(member.issym() or member.islnk() or Path(member.name).is_absolute() or ".." in Path(member.name).parts for member in members):
            raise ValueError("git archive contained an unsafe source path")
        archive.extractall(destination, members=members)


def build_python_distributions(source: Path, destination: Path, source_epoch: int) -> tuple[Path, Path]:
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(source_epoch)
    run([sys.executable, "-m", "build", "--no-isolation", "--sdist", "--wheel", "--outdir", str(destination)], cwd=source, env=environment)
    sdists = sorted(destination.glob("dasleafer-*.tar.gz"))
    wheels = sorted(destination.glob("dasleafer-*.whl"))
    if len(sdists) != 1 or len(wheels) != 1:
        raise ValueError("build did not produce exactly one DAS Leafer sdist and wheel")
    normalize_sdist(sdists[0], source_epoch)
    return sdists[0], wheels[0]


def normalize_sdist(path: Path, source_epoch: int) -> None:
    """Rewrite setuptools' clock-stamped sdist into a deterministic gzip/tar.

    Wheels already honor ``SOURCE_DATE_EPOCH`` with the pinned build backend,
    while setuptools' sdist gzip header and tar member mtimes can still carry
    the local build time.  Release evidence must compare byte-for-byte, so the
    file contents, member order, ownership and permissions are retained while
    all time and owner metadata is canonicalized.
    """
    normalized = path.with_name(path.name + ".normalized")
    with gzip.open(path, "rb") as input_gzip:
        with tarfile.open(fileobj=input_gzip, mode="r:") as input_tar:
            with normalized.open("wb") as output_file:
                with gzip.GzipFile(filename="", mode="wb", fileobj=output_file, mtime=0) as output_gzip:
                    with tarfile.open(fileobj=output_gzip, mode="w", format=tarfile.PAX_FORMAT) as output_tar:
                        for member in input_tar:
                            canonical = copy.copy(member)
                            canonical.gid = 0
                            canonical.gname = ""
                            canonical.mtime = source_epoch
                            canonical.pax_headers = {}
                            canonical.uid = 0
                            canonical.uname = ""
                            data = input_tar.extractfile(member) if member.isfile() else None
                            output_tar.addfile(canonical, data)
    os.replace(normalized, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=".")
    parser.add_argument("--out", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--tag-object", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--resolved-dependencies", help="pip --report JSON for the exact release environment")
    args = parser.parse_args()
    root = Path(args.source).resolve()
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"release output must be empty: {out}")
    if not (root / "pyproject.toml").is_file() or (root / "VERSION").read_text(encoding="utf-8").strip() != args.version:
        raise SystemExit("source and requested version do not agree")
    if args.tag != f"v{args.version}" or not re.fullmatch(r"[0-9a-f]{40}", args.tag_object) or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("release identity is invalid")
    if run(["git", "rev-parse", "HEAD^{commit}"], cwd=root).strip() != args.commit:
        raise SystemExit("checked-out source does not match requested commit")
    if run(["git", "rev-parse", f"refs/tags/{args.tag}"], cwd=root).strip() != args.tag_object:
        raise SystemExit("release tag object does not match requested tag object")
    if run(["git", "cat-file", "-t", args.tag_object], cwd=root).strip() != "tag":
        raise SystemExit("release tag must be annotated")
    if run(["git", "rev-parse", f"{args.tag}^{{commit}}"], cwd=root).strip() != args.commit:
        raise SystemExit("release tag does not target the requested commit")
    source_epoch = int(run(["git", "show", "-s", "--format=%ct", args.commit], cwd=root).strip())
    resolved_report = Path(args.resolved_dependencies).resolve() if args.resolved_dependencies else None
    dependency_inputs = resolved_dependency_inputs(resolved_report) if resolved_report else None
    dependencies = load_license_decisions(root, resolved_report)
    out.mkdir(parents=True)
    source_archive = out / f"das-leafer-{args.version}-source.tar.gz"
    source_tar = subprocess.check_output(["git", "archive", "--format=tar", f"--prefix=das-leafer-{args.version}/", args.commit], cwd=str(root))
    with source_archive.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0, compresslevel=9) as compressed:
            compressed.write(source_tar)
    with tempfile.TemporaryDirectory(prefix="das-leafer-release-build-") as temp_dir:
        temp = Path(temp_dir)
        first_root, second_root = temp / "first-root", temp / "second-root"
        first_out, second_out = temp / "first-out", temp / "second-out"
        first_root.mkdir(); second_root.mkdir()
        extract_archived_source(source_tar, first_root)
        extract_archived_source(source_tar, second_root)
        first_source = first_root / f"das-leafer-{args.version}"
        second_source = second_root / f"das-leafer-{args.version}"
        first_out.mkdir(); second_out.mkdir()
        first_sdist, first_wheel = build_python_distributions(first_source, first_out, source_epoch)
        second_sdist, second_wheel = build_python_distributions(second_source, second_out, source_epoch)
        if sha256_file(first_sdist) != sha256_file(second_sdist) or sha256_file(first_wheel) != sha256_file(second_wheel):
            raise SystemExit("Python sdist/wheel builds are not reproducible")
        shutil.copy2(first_sdist, out / first_sdist.name)
        shutil.copy2(first_wheel, out / first_wheel.name)
    source_sbom = out / f"das-leafer-{args.version}-source.spdx.json"
    dependencies_sbom = out / f"das-leafer-{args.version}-dependencies.spdx.json"
    source_sbom.write_bytes(canonical_json(source_inventory(root, args.commit, "das-leafer", args.version, source_epoch)) + b"\n")
    dependencies_sbom.write_bytes(canonical_json(dependency_inventory("das-leafer", args.version, dependencies, source_epoch, json.loads((root / "release/DEPENDENCY_LOCK.json").read_text(encoding="utf-8")))) + b"\n")
    notices = out / "THIRD_PARTY_NOTICES.md"
    notices.write_text("# Third-party notices — DAS Leafer " + args.version + "\n\n" + "This file is generated from the exact reviewed dependency-license decisions for this release.\n\n" + "\n".join(f"- **{row['name']} {row['version']}** — `{row['license']}`. {row['notice']}" for row in dependencies) + "\n", encoding="utf-8")
    dependency_inputs_path = out / "resolved-dependencies.json"
    if dependency_inputs is not None:
        dependency_inputs_path.write_bytes(canonical_json(dependency_inputs) + b"\n")
    subjects = [{"name": path.name, "digest": {"sha256": sha256_file(path)}} for path in sorted(out.iterdir()) if path.is_file()]
    provenance = out / "provenance.intoto.jsonl"
    provenance.write_bytes(canonical_json({"_type": "https://in-toto.io/Statement/v1", "predicateType": "https://slsa.dev/provenance/v1", "subject": subjects, "predicate": {"buildDefinition": {"buildType": "https://das-standard.dev/build/das-leafer-python-release/v1", "externalParameters": {"commit": args.commit, "tag": args.tag, "tagObject": args.tag_object, "version": args.version}, "internalParameters": {"sourceDateEpoch": source_epoch}, "resolvedDependencies": [{"uri": "git+https://github.com/AzzCraft/das-leafer@" + args.commit, "digest": {"gitCommit": args.commit}}]}, "runDetails": {"builder": {"id": "das-leafer/scripts/release/build_release_artifacts.py"}, "metadata": {"invocationId": "local-or-ci", "startedOn": datetime.fromtimestamp(source_epoch, timezone.utc).isoformat().replace("+00:00", "Z"), "finishedOn": datetime.fromtimestamp(source_epoch, timezone.utc).isoformat().replace("+00:00", "Z")}}}}) + b"\n")
    artifacts = [{"name": path.name, "sha256": sha256_file(path)} for path in sorted(out.iterdir()) if path.is_file()]
    manifest = {"schemaVersion": "1.0.0", "repository": "das-leafer", "version": args.version, "tag": args.tag, "tagObject": args.tag_object, "commit": args.commit, "sourceDateEpoch": source_epoch, "dependencyLicenseDecisionsSha256": sha256_file(root / "release" / "dependency_license_decisions.json"), "resolvedDependenciesSha256": sha256_file(dependency_inputs_path) if dependency_inputs is not None else None, "artifacts": artifacts}
    manifest_path = out / "release-manifest.json"
    manifest_path.write_bytes(canonical_json(manifest) + b"\n")
    checksums = sorted(path for path in out.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_text("".join(f"{sha256_file(path)}  {path.name}\n" for path in checksums), encoding="utf-8")
    print(json.dumps({"artifactDirectory": str(out), "artifacts": [path.name for path in checksums], "status": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
