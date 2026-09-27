#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${1:?Usage: install_hfvi_browser.sh DESTINATION_OUTSIDE_SOURCE}"
python3 - "$ROOT" "$DEST" <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

root, dest = (Path(p).resolve() for p in sys.argv[1:])
if dest == root or root in dest.parents:
    raise SystemExit("browser destination must be outside the source tree")
lock = json.loads((root / "templates/das-leafer-product/hfvi/browser.lock.json").read_text())
archive = lock["archive"]
if not archive["url"].startswith("https://storage.googleapis.com/chrome-for-testing-public/"):
    raise SystemExit("unsupported browser source")
dest.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    downloaded = Path(tmp) / "chrome.zip"
    with urllib.request.urlopen(archive["url"], timeout=120) as response, downloaded.open("wb") as output:
        shutil.copyfileobj(response, output)
    if downloaded.stat().st_size != archive["contentLength"] or hashlib.md5(downloaded.read_bytes()).hexdigest() != archive["md5"]:
        raise SystemExit("browser archive does not match lock")
    with zipfile.ZipFile(downloaded) as package:
        for item in package.infolist():
            path = dest / item.filename
            if not path.resolve().is_relative_to(dest):
                raise SystemExit("unsafe browser archive path")
            package.extract(item, dest)
            mode = (item.external_attr >> 16) & 0o777
            if mode and path.is_file():
                path.chmod(mode)
print(dest / "chrome-linux64/chrome")
PY
