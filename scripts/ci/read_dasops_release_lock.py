#!/usr/bin/env python3
"""Validate and expose the immutable DASOps identity used by Leafer CI."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from verify_dasops_release_lock import load_lock, require_publication_eligible


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default=str(Path(__file__).resolve().parents[2] / "release" / "DEPENDENCY_LOCK.json"))
    parser.add_argument("--github-output")
    parser.add_argument("--require-publication-eligible", action="store_true")
    args = parser.parse_args()
    try:
        value = load_lock(Path(args.lock))
        publication = value["publication"]
        if args.require_publication_eligible:
            require_publication_eligible(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    identity = value["identity"]
    assert isinstance(identity, dict)
    output = {
        "repository": "AzzCraft/dasops",
        "tag": identity["tag"],
        "tag_object": identity["tagObject"],
        "target_commit": identity["targetCommit"],
        "tree": identity["tree"],
    }
    if args.github_output:
        Path(args.github_output).open("a", encoding="utf-8").write(
            "".join(f"{key}={value}\n" for key, value in output.items())
        )
    else:
        print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
