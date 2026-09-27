#!/usr/bin/env python3
"""Verify an annotated release tag against an independently configured SSH or OpenPGP key."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def verify(tag: str, fingerprint: str, public_key: Path) -> str:
    key = public_key.read_text(encoding="utf-8").strip()
    if subprocess.check_output(["git", "cat-file", "-t", f"refs/tags/{tag}"], text=True).strip() != "tag":
        raise ValueError("release tag must be annotated")
    with tempfile.TemporaryDirectory(prefix="leafer-signer-") as temporary:
        directory = Path(temporary)
        if fingerprint.startswith("SHA256:"):
            if not key.startswith("ssh-ed25519 ") or "\n" in key:
                raise ValueError("SSH release signing requires one trusted ED25519 public key")
            actual = subprocess.check_output(["ssh-keygen", "-l", "-E", "sha256", "-f", str(public_key)], text=True).split()[1]
            if actual != fingerprint:
                raise ValueError("SSH public key does not match the approved fingerprint")
            allowed = directory / "allowed_signers"
            allowed.write_text("release@das-leafer " + key + "\n", encoding="utf-8")
            command = ["git", "-c", "gpg.format=ssh", "-c", f"gpg.ssh.allowedSignersFile={allowed}", "verify-tag", "--raw", tag]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode:
                raise ValueError("release tag signature is absent, invalid, or not made by the approved SSH signer")
            return "ssh-ed25519"
        expected = fingerprint.replace(" ", "").upper()
        if not re.fullmatch(r"[0-9A-F]{40,64}", expected) or "BEGIN PGP PUBLIC KEY BLOCK" not in key:
            raise ValueError("expected a full OpenPGP fingerprint and armored public key")
        if shutil.which("gpg") is None:
            raise ValueError("gpg is required to verify the release signer")
        environment = {**os.environ, "GNUPGHOME": temporary}
        directory.chmod(0o700)
        imported = subprocess.run(["gpg", "--batch", "--import", str(public_key)], env=environment, text=True, capture_output=True, check=False)
        if imported.returncode:
            raise ValueError("could not import trusted release signer key")
        checked = subprocess.run(["git", "-c", "gpg.format=openpgp", "verify-tag", "--raw", tag], env=environment, text=True, capture_output=True, check=False)
        matches = re.findall(r"\[GNUPG:\] VALIDSIG ([0-9A-F]{40,64})", checked.stdout + checked.stderr)
        if checked.returncode or expected not in {value.upper() for value in matches}:
            raise ValueError("release tag signature is absent, invalid, or not made by the configured signer")
        return "openpgp"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--public-key", required=True, help="trusted SSH ED25519 or armored OpenPGP public key")
    args = parser.parse_args()
    try:
        kind = verify(args.tag, args.fingerprint, Path(args.public_key).resolve())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({"fingerprint": args.fingerprint, "signatureKind": kind, "status": "verified", "tag": args.tag}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
