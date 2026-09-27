#!/usr/bin/env python3
"""Materialize the exact public DASOps tag without importing an internal workspace."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import shutil

from verify_dasops_release_lock import candidate_tree_digest, load_lock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", required=True, type=Path)
    args = parser.parse_args()
    lock = load_lock(Path(__file__).resolve().parents[2] / "release/DEPENDENCY_LOCK.json")
    identity = lock["identity"]
    dest = args.dest.resolve()
    if dest.exists():
        if candidate_tree_digest(dest) == lock["pin"]["candidateTreeSha256"]:
            print(dest)
            return
        raise SystemExit("destination exists and does not match the locked dependency; choose a new directory")
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "checkout"
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "fetch", "--depth=1", identity["remote"], f"refs/tags/{identity['tag']}:refs/tags/{identity['tag']}"], check=True)
        def git(*arguments):
            return subprocess.check_output(["git", "-C", str(checkout), *arguments], text=True).strip()
        checks = {identity["tag"]: identity["tagObject"], identity["tag"] + "^{commit}": identity["targetCommit"], identity["tag"] + "^{tree}": identity["tree"]}
        if git("cat-file", "-t", identity["tag"]) != "tag" or any(git("rev-parse", ref) != expected for ref, expected in checks.items()):
            raise SystemExit("remote dependency does not match the locked annotated tag identity")
        archive = subprocess.check_output(["git", "-C", str(checkout), "archive", identity["targetCommit"]])
        staged = Path(tmp) / "source"
        staged.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            for member in package.getmembers():
                if not (staged / member.name).resolve().is_relative_to(staged) or not (member.isfile() or member.isdir()):
                    raise SystemExit("unsafe dependency archive member")
            package.extractall(staged)
        if candidate_tree_digest(staged) != lock["pin"]["candidateTreeSha256"]:
            raise SystemExit("public dependency tree differs from the locked digest")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, dest)
    print(dest)


if __name__ == "__main__":
    main()
