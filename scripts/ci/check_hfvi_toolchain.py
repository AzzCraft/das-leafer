#!/usr/bin/env python3
"""Require the locked browser and supported Node runtime for release acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    lock = json.loads((root / "templates/das-leafer-product/hfvi/browser.lock.json").read_text())
    browser = shutil.which(os.environ.get("HFVI_BROWSER_BINARY", "google-chrome"))
    if not browser:
        raise SystemExit("Locked Chrome is required; run scripts/ci/install_hfvi_browser.sh and set HFVI_BROWSER_BINARY")
    actual = subprocess.check_output([browser, "--product-version"], text=True).strip()
    if actual != lock["productVersion"]:
        raise SystemExit(f"Chrome {actual} does not match browser lock {lock['productVersion']}")
    if not shutil.which("node") or not shutil.which("npm"):
        raise SystemExit("Node.js 22.12+ and npm are required")
    version = subprocess.check_output(["node", "--version"], text=True).strip().lstrip("v")
    parts = tuple(int(x) for x in version.split("."))
    if parts[0] != 22 or parts < (22, 12, 0):
        raise SystemExit(f"Node.js 22.12+ (major 22) required; found {version}")
    print(json.dumps({"browser": actual, "node": version, "status": "passed"}))


if __name__ == "__main__":
    main()
