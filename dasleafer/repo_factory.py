from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ._dasops_bridge import import_dasops_module
from .project_identity import ProjectIdentity, materialize_project_identity


_dasops_repo_factory = import_dasops_module("repo_factory")

ensure_product_repo_permissions = _dasops_repo_factory.ensure_product_repo_permissions
maybe_git_init = _dasops_repo_factory.maybe_git_init
init_repo = _dasops_repo_factory.init_repo
new_change = _dasops_repo_factory.new_change


def factory_template_dir(factory_root: Path) -> Path:
    return factory_root / "templates" / "das-leafer-product"


def _mark_lock_pin_pending(repo_root: Path) -> None:
    """Make a no-Git Leafer scaffold explicitly fail closed on its source pin."""
    lock_path = repo_root / "tooling_lock.json"
    if not lock_path.is_file():
        return
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    source = lock.get("sourceOfTruth")
    if not isinstance(source, dict):
        return
    if source.get("pinValue") == "replace-with-product-commit":
        source.pop("pinValue", None)
    if not source.get("pinValue"):
        source["pinState"] = "pending"
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def finalize_bootstrap_provenance(repo_root: Path) -> str | None:
    """Record a generated scaffold's bootstrap commit on every supported DASOps API.

    The declared DASOps v1.0.0 release predates the helper added by newer
    development snapshots.  Leafer cannot claim that it supports that exact
    public dependency while importing an undeclared newer API, so it delegates
    when available and otherwise performs the same narrow, local provenance
    update itself.
    """
    delegated = getattr(_dasops_repo_factory, "finalize_bootstrap_provenance", None)
    if callable(delegated):
        return delegated(repo_root)
    lock_path = repo_root / "tooling_lock.json"
    if not lock_path.is_file() or not (repo_root / ".git").exists():
        return None
    try:
        bootstrap_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    source = lock.get("sourceOfTruth")
    if not isinstance(source, dict):
        return None
    source["pinValue"] = bootstrap_commit
    source.pop("pinState", None)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    try:
        subprocess.run(["git", "add", "tooling_lock.json"], cwd=str(repo_root), check=True)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(repo_root), check=False)
        if staged.returncode:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=das-leafer",
                    "-c",
                    "user.email=das-leafer@local",
                    "commit",
                    "-m",
                    "chore: record bootstrap source identity",
                ],
                cwd=str(repo_root),
                check=True,
            )
    except (OSError, subprocess.CalledProcessError):
        return None
    return bootstrap_commit


def create_product_repo_from_template(
    *,
    template_dir: Path,
    dest_dir: Path,
    master_doc_path: Path,
    ui_spec_path: Path,
    change_id: Optional[str] = None,
    intent: str = "",
    init_git: bool = True,
    overwrite: bool = False,
    change_empty: bool = False,
    project_id: str,
    namespace: str,
    display_name: str,
    initial_version: str,
    license_id: str,
    copyright: str,
    license_text: str,
) -> Path:
    if not template_dir.exists():
        raise SystemExit(
            "Factory template not found. Expected: "
            f"{template_dir}.\n\n"
            "Run this command from the cloned das-leafer repo, or pass --factory-root explicitly."
        )

    dest_dir = dest_dir.expanduser().resolve()
    if dest_dir.exists() and any(dest_dir.iterdir()):
        if not overwrite:
            raise SystemExit(
                f"Destination directory is not empty: {dest_dir}\n"
                "Refusing to overwrite. Use --overwrite if you really want this."
            )
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)

    identity = ProjectIdentity.create(
        project_id=project_id,
        namespace=namespace,
        display_name=display_name,
        initial_version=initial_version,
        license_id=license_id,
        copyright=copyright,
        license_text=license_text,
    )

    # The checked-in template owns source inputs only.  Browser HFVI builds
    # create frontend/dist, node_modules, and review receipts locally; copying
    # any of those into a newly generated repository would make its initial
    # Git state non-reproducible and could accidentally package host binaries.
    shutil.copytree(
        template_dir,
        dest_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("node_modules", "dist", ".cadence"),
    )

    init_repo(
        repo_root=dest_dir,
        master_doc_path=master_doc_path,
        ui_spec_path=ui_spec_path,
    )
    materialize_project_identity(dest_dir, identity)

    if change_id:
        new_change(
            repo_root=dest_dir,
            change_id=change_id,
            intent=intent,
            empty=change_empty,
        )

    marker = dest_dir / ".dasops_product_repo"
    if not marker.exists():
        marker.write_text(
            "This is a DAS + OpenSpec PRODUCT repo generated by das-leafer.\n"
            "Use dasops for generic product-repo workflows and das-leafer for Leafer/HFVI-specific overlays.\n",
            encoding="utf-8",
        )

    ensure_product_repo_permissions(dest_dir)

    if init_git:
        maybe_git_init(dest_dir)
        finalize_bootstrap_provenance(dest_dir)
    else:
        _mark_lock_pin_pending(dest_dir)

    return dest_dir


def create_product_repo(
    *,
    factory_root: Path,
    dest_dir: Path,
    master_doc_path: Path,
    ui_spec_path: Path,
    change_id: Optional[str] = None,
    intent: str = "",
    init_git: bool = True,
    overwrite: bool = False,
    change_empty: bool = False,
    project_id: str,
    namespace: str,
    display_name: str,
    initial_version: str,
    license_id: str,
    copyright: str,
    license_text: str,
) -> Path:
    return create_product_repo_from_template(
        template_dir=factory_template_dir(factory_root),
        dest_dir=dest_dir,
        master_doc_path=master_doc_path,
        ui_spec_path=ui_spec_path,
        change_id=change_id,
        intent=intent,
        init_git=init_git,
        overwrite=overwrite,
        change_empty=change_empty,
        project_id=project_id,
        namespace=namespace,
        display_name=display_name,
        initial_version=initial_version,
        license_id=license_id,
        copyright=copyright,
        license_text=license_text,
    )


def __getattr__(name: str):
    return getattr(_dasops_repo_factory, name)


__all__ = [
    "create_product_repo",
    "create_product_repo_from_template",
    "ensure_product_repo_permissions",
    "factory_template_dir",
    "finalize_bootstrap_provenance",
    "init_repo",
    "maybe_git_init",
    "new_change",
]
