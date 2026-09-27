#!/usr/bin/env python3
"""Fail closed unless Leafer is using its declared DASOps release source."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from urllib.error import HTTPError, URLError
from typing import Callable
from pathlib import Path
from typing import Any


SHA1 = re.compile(r"[0-9a-f]{40}$")
SHA256 = re.compile(r"[0-9a-f]{64}$")
EXPECTED = {
    "component": "dasops",
    "version": "1.0.0",
    "sourceDescriptor": "release/descriptors/dasops/v1.0.0.json",
    "sourceDescriptorCommit": "7273247985e69bcf3765410bce9243d070c1dd2c",
}


def load_lock(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    pin = value.get("dependencies", {}).get("dasops") if isinstance(value, dict) else None
    if not isinstance(pin, dict) or any(pin.get(key) != expected for key, expected in EXPECTED.items()):
        raise ValueError("dependency lock does not bind the expected DASOps v1.0.0 descriptor")
    identity = pin.get("releaseIdentity")
    if not isinstance(identity, dict):
        raise ValueError("dependency lock is missing DASOps releaseIdentity")
    if identity.get("remote") != "https://github.com/AzzCraft/dasops.git" or identity.get("tag") != "v1.0.0":
        raise ValueError("dependency lock does not bind the expected DASOps public remote/tag")
    for key in ("tagObject", "targetCommit", "tree"):
        if not isinstance(identity.get(key), str) or SHA1.fullmatch(str(identity[key])) is None:
            raise ValueError(f"dependency lock has invalid DASOps {key}")
    digest = pin.get("candidateTreeSha256")
    if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
        raise ValueError("dependency lock has invalid DASOps candidateTreeSha256")
    publication = value.get("publication")
    if not isinstance(publication, dict) or publication.get("status") not in {"blocked", "eligible"}:
        raise ValueError("dependency lock must record a structured publication status")
    if not isinstance(publication.get("reason"), str) or not publication["reason"].strip():
        raise ValueError("dependency lock publication status needs a reason")
    return {"pin": pin, "identity": identity, "publication": publication}


# The pinned v1.0.0 tag is already observed as unsigned. A signed successor
# requires a new, reviewed dependency identity; this exact lock can only use
# the historical exception granted on the independent policy issue.
DASOPS_API = "https://api.github.com/repos/AzzCraft/dasops/"


def github_json(url: str, token: str) -> dict[str, Any]:
    if not token:
        raise ValueError("DASOPS_APPROVAL_TOKEN is required to authenticate the private approval issue")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.load(response)
    except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot authenticate GitHub publication evidence at {url}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"invalid GitHub publication evidence at {url}")
    return value


def remote_tag_identity(identity: dict[str, str]) -> tuple[str, str]:
    result = subprocess.run(["git", "ls-remote", identity["remote"], "refs/tags/" + identity["tag"],
                             "refs/tags/" + identity["tag"] + "^{}"],
                            check=True, text=True, capture_output=True, timeout=30)
    rows = dict(line.split("\t", 1)[::-1] for line in result.stdout.splitlines())
    return (rows.get("refs/tags/" + identity["tag"], ""),
            rows.get("refs/tags/" + identity["tag"] + "^{}", ""))


def require_publication_eligible(
    lock: dict[str, Any], *,
    fetch: Callable[[str], dict[str, Any]] | None = None,
    resolve_tag: Callable[[dict[str, str]], tuple[str, str]] = remote_tag_identity,
    approved_approvers: set[str] | None = None,
    validation_workflow_id: int | None = None,
    approval_issue_url: str | None = None,
) -> None:
    publication = lock["publication"]
    if publication["status"] != "eligible":
        raise ValueError("DASOps dependency is not publication-eligible: " + str(publication["reason"]))
    identity = lock["identity"]
    evidence = publication.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("releaseIdentity") != identity:
        raise ValueError("publication evidence must bind the exact DASOps release identity")
    signature = evidence.get("signature")
    if not isinstance(signature, dict) or signature.get("status") != "historical-unsigned-exception":
        raise ValueError("the pinned unsigned DASOps tag requires an independently approved historical exception")
    if approved_approvers is None:
        approved_approvers = {item.strip() for item in os.environ.get("DASOPS_APPROVED_APPROVERS", "").split(",") if item.strip()}
    if validation_workflow_id is None:
        raw_id = os.environ.get("DASOPS_VALIDATION_WORKFLOW_ID", "")
        validation_workflow_id = int(raw_id) if raw_id.isdecimal() else None
    if approval_issue_url is None:
        approval_issue_url = os.environ.get("DASOPS_APPROVAL_ISSUE_URL", "")
    issue_match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)", approval_issue_url)
    if issue_match is None:
        raise ValueError("protected exact DASOps approval issue URL is required")
    issue_owner, issue_repo, issue_number = issue_match.groups()
    issue_api = f"https://api.github.com/repos/{issue_owner}/{issue_repo}/issues/{issue_number}"
    comment_api = f"https://api.github.com/repos/{issue_owner}/{issue_repo}/issues/comments/"
    if not approved_approvers or "azzcraft" in {name.casefold() for name in approved_approvers} or not validation_workflow_id:
        raise ValueError("protected independent approver and DASOps validation workflow ID are required")
    if fetch is None:
        token = os.environ.get("DASOPS_APPROVAL_TOKEN", "")
        if not token:
            raise ValueError("DASOPS_APPROVAL_TOKEN is required to authenticate the private approval issue")
        fetch = lambda url: github_json(url, token)
    release_url = "https://github.com/AzzCraft/dasops/releases/tag/" + identity["tag"]
    if evidence.get("githubRelease") != release_url:
        raise ValueError("publication evidence must name the exact DASOps GitHub Release")
    run_url = evidence.get("validationRun")
    run_prefix = "https://github.com/AzzCraft/dasops/actions/runs/"
    if not isinstance(run_url, str) or not run_url.startswith(run_prefix) or not run_url[len(run_prefix):].isdecimal():
        raise ValueError("publication evidence must name an exact DASOps validation run")
    approval_url = evidence.get("approval")
    comment_prefix = approval_issue_url + "#issuecomment-"
    if not isinstance(approval_url, str) or not approval_url.startswith(comment_prefix) or not approval_url[len(comment_prefix):].isdecimal() or signature.get("approval") != approval_url:
        raise ValueError("publication evidence must name the exact independent approval comment")
    exception_id = signature.get("exceptionId")
    if not isinstance(exception_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{8,80}", exception_id):
        raise ValueError("historical exception needs a bounded identifier")
    approval = fetch(comment_api + approval_url[len(comment_prefix):])
    author = approval.get("user", {}).get("login") if isinstance(approval.get("user"), dict) else None
    if (approval.get("html_url") != approval_url or approval.get("issue_url") != issue_api or
        not isinstance(author, str) or author.casefold() not in {name.casefold() for name in approved_approvers} or approval.get("author_association") not in {"OWNER", "MEMBER", "COLLABORATOR"}):
        raise ValueError("approval comment is not from an independently approved DAS Tools maintainer")
    try:
        statement = json.loads(approval["body"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("approval comment must contain a structured exact-identity statement") from exc
    expected = {"schemaVersion": "das-leafer.dasops-exception.v1", "component": "dasops",
                "version": lock["pin"]["version"], "tag": identity["tag"],
                "tagObject": identity["tagObject"], "targetCommit": identity["targetCommit"],
                "exceptionId": exception_id, "scope": "historical-unsigned-tag-only",
                "approver": author, "approvalIssue": approval_issue_url}
    if statement != expected or approval.get("updated_at") != approval.get("created_at"):
        raise ValueError("approval statement was modified or does not bind the exact tag and scope")
    try:
        datetime.fromisoformat(approval["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("approval time is invalid") from exc
    release = fetch(DASOPS_API + "releases/tags/" + identity["tag"])
    if (release.get("html_url") != release_url or release.get("tag_name") != identity["tag"] or
        release.get("draft") is not False or not release.get("published_at")):
        raise ValueError("DASOps GitHub Release is absent, draft, or for another tag")
    run = fetch(DASOPS_API + "actions/runs/" + run_url[len(run_prefix):])
    repository = run.get("repository")
    if (run.get("html_url") != run_url or not isinstance(repository, dict) or
        repository.get("full_name") != "AzzCraft/dasops" or
        run.get("head_sha") != identity["targetCommit"] or
        run.get("workflow_id") != validation_workflow_id or
        run.get("status") != "completed" or run.get("conclusion") != "success"):
        raise ValueError("DASOps validation run is not a successful exact-commit approved workflow")
    if resolve_tag(identity) != (identity["tagObject"], identity["targetCommit"]):
        raise ValueError("public DASOps tag no longer matches its approved object and commit")


def candidate_tree_digest(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if ".git" in path.relative_to(root).parts:
            continue
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            payload = os.readlink(path).encode("utf-8")
            mode = "120000"
        else:
            payload = path.read_bytes()
            mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        value.update(rel.encode("utf-8") + b"\0")
        value.update(mode.encode("ascii") + b"\0")
        value.update(str(len(payload)).encode("ascii") + b"\0")
        value.update(hashlib.sha256(payload).hexdigest().encode("ascii") + b"\0")
    return value.hexdigest()


def controlled_workspace_exception(root: Path, *, requested: bool) -> bool:
    """Allow only the explicit monorepo-development exception.

    The source workspace intentionally contains newer DASOps work, so it is
    not a release candidate. The exception must be requested through the
    verifier's explicit ``--workspace`` mode and cannot be inherited through
    ambient process state by public candidate builds.
    """
    if not requested:
        return False
    workspace = root.parent.resolve()
    if root.resolve() != workspace / "dasops" or not (workspace / "workspace.yaml").is_file():
        raise ValueError("the unpinned DASOps exception is restricted to the DAS Tools workspace sibling")
    result = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode or Path(result.stdout.strip()).resolve() != workspace:
        raise ValueError("the unpinned DASOps exception requires the DAS Tools Git workspace root")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--lock", default=str(root / "release" / "DEPENDENCY_LOCK.json"))
    parser.add_argument("--dasops-root", default=str(root.parent / "dasops"))
    parser.add_argument(
        "--prepared-dependencies",
        default=os.environ.get("DAS_RELEASE_PINNED_DEPENDENCIES", ""),
        help="optional candidate-builder dependency metadata that must match the lock",
    )
    parser.add_argument("--require-publication-eligible", action="store_true")
    parser.add_argument(
        "--workspace",
        action="store_true",
        help="allow the newer sibling DASOps tree only inside the declared DAS Tools root monorepo",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        lock = load_lock(Path(args.lock))
        dependency_root = Path(args.dasops_root).resolve()
        if not (dependency_root / "pyproject.toml").is_file():
            raise ValueError(f"expected the pinned DASOps source: {dependency_root}")
        version = (dependency_root / "VERSION").read_text(encoding="utf-8").strip()
        pin = lock["pin"]
        exception = controlled_workspace_exception(dependency_root, requested=args.workspace)
        if args.prepared_dependencies:
            prepared = json.loads(args.prepared_dependencies)
            if not isinstance(prepared, list):
                raise ValueError("prepared dependency metadata must be a JSON list")
            matched = [item for item in prepared if isinstance(item, dict) and item.get("component") == "dasops"]
            if len(matched) != 1 or matched[0].get("sourceCommit") != pin["sourceDescriptorCommit"]:
                raise ValueError("prepared DASOps dependency does not match release/DEPENDENCY_LOCK.json")
        if not exception and version != pin["version"]:
            raise ValueError(f"DASOps VERSION {version} does not match locked version {pin['version']}")
        if not exception:
            actual = candidate_tree_digest(dependency_root)
            if actual != pin["candidateTreeSha256"]:
                raise ValueError("DASOps source tree does not match the locked public candidate digest")
        publication = lock["publication"]
        if args.require_publication_eligible:
            require_publication_eligible(lock)
        report = {
            "component": "dasops",
            "status": "development-exception" if exception else "locked-candidate-verified",
            "version": pin["version"],
            "candidateTreeSha256": pin["candidateTreeSha256"],
            "publicationStatus": publication["status"],
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, sort_keys=True) if args.json else report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
