from __future__ import annotations

import argparse
import subprocess
import sys
import sysconfig
from pathlib import Path

from .preset import create_product_repo


DELEGATED_COMMANDS = {
    "init": "Delegate product-repo initialization to dasops.",
    "new-change": "Delegate OpenSpec change creation to dasops.",
    "status": "Delegate product-repo status reporting to dasops.",
    "doctor": "Delegate generic repo doctoring to dasops.",
    "list-tasks": "Delegate task listing to dasops.",
    "claim-task": "Delegate task claiming to dasops.",
    "claim-ready": "Delegate pull-mode task claiming to dasops.",
    "complete-task": "Delegate task completion to dasops.",
    "release-task": "Delegate task release to dasops.",
    "lock-status": "Delegate structured lock inspection to dasops.",
    "start-task": "Delegate worktree/branch claiming flow to dasops.",
    "prompt": "Delegate generic prompt rendering to dasops.",
}


def _default_factory_root() -> Path:
    source_root = Path(__file__).resolve().parents[1]
    if (source_root / "templates" / "das-leafer-product").is_dir():
        return source_root

    data_root = sysconfig.get_path("data")
    if data_root:
        installed_root = Path(data_root) / "share" / "dasleafer"
        if (installed_root / "templates" / "das-leafer-product").is_dir():
            return installed_root
    return source_root


def _delegate_to_dasops(argv: list[str]) -> int:
    python_delegate = [sys.executable, "-m", "dasops", *argv]
    return subprocess.run(python_delegate, check=False).returncode


def build_parser() -> argparse.ArgumentParser:
    delegated = "\n".join(f"  - {name}: {desc}" for name, desc in DELEGATED_COMMANDS.items())
    parser = argparse.ArgumentParser(
        prog="dasleafer",
        description="DAS + Leafer HFVI factory tooling",
        epilog=(
            "Factory-first commands remain local to das-leafer.\n"
            "Generic product-repo workflows delegate to dasops.\n\n"
            "Delegated commands:\n"
            f"{delegated}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")

    p_create = sub.add_parser(
        "create",
        help="Create a NEW HFVI product repo from the Leafer preset template",
    )
    p_create.add_argument("--dest", required=True, help="Destination directory for the new product repo")
    p_create.add_argument("--master-doc", required=True, help="Path to master_doc.md")
    p_create.add_argument("--ui-spec", required=True, help="Path to ui_spec.md")
    p_create.add_argument("--project-id", required=True, help="Lowercase hyphenated repository/product identifier")
    p_create.add_argument("--namespace", required=True, help="Owning dotted namespace, not org.example")
    p_create.add_argument("--display-name", required=True, help="Human-readable product name")
    p_create.add_argument("--initial-version", required=True, help="Initial semantic version, for example 0.1.0")
    p_create.add_argument("--license-id", required=True, help="Selected SPDX-style license identifier (UNLICENSED is rejected)")
    p_create.add_argument("--license-file", required=True, help="Path to the full selected license terms")
    p_create.add_argument("--copyright", required=True, help="Copyright holder and year(s) for the generated project")
    p_create.add_argument("--change-id", default=None, help="Optional initial change id, e.g. initial")
    p_create.add_argument("--intent", default="", help="Optional intent string for the initial change")
    p_create.add_argument("--factory-root", default=None, help="Factory repo root (defaults to this source tree)")
    p_create.add_argument("--no-git", action="store_true", help="Do not run 'git init' in the new repo")
    p_create.add_argument("--overwrite", action="store_true", help="Allow writing into a non-empty destination directory")
    p_create.add_argument(
        "--allow-inside-factory",
        action="store_true",
        help="Allow creating the product repo inside the factory repo (NOT recommended)",
    )
    p_create.add_argument(
        "--change-empty",
        action="store_true",
        help="If --change-id is provided: create an EMPTY change folder (OPSX generates artifacts)",
    )
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in DELEGATED_COMMANDS:
        return _delegate_to_dasops(argv)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd != "create":
        parser.print_help()
        return 0

    factory_root = (
        Path(args.factory_root).expanduser().resolve()
        if args.factory_root
        else _default_factory_root()
    )
    dest_dir = Path(args.dest).expanduser().resolve()
    license_path = Path(args.license_file).expanduser().resolve()
    if not license_path.is_file():
        raise SystemExit(f"License file does not exist: {license_path}")

    if not args.allow_inside_factory:
        try:
            dest_dir.relative_to(factory_root)
        except ValueError:
            pass
        else:
            raise SystemExit(
                f"Refusing to create a product repo inside the factory repo:\n"
                f"- factory: {factory_root}\n"
                f"- dest:    {dest_dir}\n"
                "Pass --allow-inside-factory to override."
            )

    create_product_repo(
        factory_root=factory_root,
        dest_dir=dest_dir,
        master_doc_path=Path(args.master_doc).expanduser().resolve(),
        ui_spec_path=Path(args.ui_spec).expanduser().resolve(),
        change_id=args.change_id,
        intent=args.intent,
        init_git=not args.no_git,
        overwrite=args.overwrite,
        change_empty=args.change_empty,
        project_id=args.project_id,
        namespace=args.namespace,
        display_name=args.display_name,
        initial_version=args.initial_version,
        license_id=args.license_id,
        copyright=args.copyright,
        license_text=license_path.read_text(encoding="utf-8"),
    )
    print(f"Created Leafer HFVI product repo at: {dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
