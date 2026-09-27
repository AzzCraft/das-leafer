#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASOPS_ROOT="${DASLEAFER_DASOPS_ROOT:-$ROOT/../dasops}"
test -f "$DASOPS_ROOT/pyproject.toml" || {
  echo "expected the pinned DASOps source beside Leafer: $DASOPS_ROOT" >&2
  exit 1
}

temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
wheels="$temp/wheels"
python3 - "$DASOPS_ROOT" "$ROOT" "$temp/dasops" "$temp/das-leafer" <<'PY'
import shutil
import sys
from pathlib import Path

for source, destination in zip(sys.argv[1:3], sys.argv[3:]):
    shutil.copytree(
        Path(source),
        Path(destination),
        ignore=shutil.ignore_patterns(".git", "build", "dist", "__pycache__", ".pytest_cache", ".venv", ".release-dependencies", "node_modules", "*.egg-info"),
    )
PY
python3 -m venv "$temp/tooling"
env -u PYTHONPATH "$temp/tooling/bin/python" -m pip install --disable-pip-version-check \
  "setuptools==83.0.0" "wheel==0.46.2" "build==1.2.2"
env -u PYTHONPATH "$temp/tooling/bin/python" -m pip wheel --disable-pip-version-check --no-deps --no-build-isolation --wheel-dir "$wheels" \
  "PyYAML==6.0.3" "$temp/dasops" "$temp/das-leafer"
env -u PYTHONPATH "$temp/tooling/bin/python" -m build --sdist --no-isolation --outdir "$temp/sdist" "$temp/das-leafer"
env -u PYTHONPATH "$temp/tooling/bin/python" -m pip wheel --disable-pip-version-check --no-deps --no-build-isolation --wheel-dir "$temp/sdist-wheel" "$temp"/sdist/dasleafer-*.tar.gz
python3 -m venv "$temp/venv"
env -u PYTHONPATH "$temp/venv/bin/python" -m pip install --disable-pip-version-check --no-index --no-deps \
  "$wheels"/pyyaml-*.whl "$wheels"/dasops-*.whl "$wheels"/dasleafer-*.whl
verify_installed() {
(
  cd "$temp"
  env -u PYTHONPATH "$temp/venv/bin/python" - <<'PY'
from pathlib import Path
import subprocess
import sys
import tempfile

import dasleafer

assert hasattr(dasleafer, "__all__")
with tempfile.TemporaryDirectory() as work:
    root = Path(work)
    master_doc = root / "master_doc.md"
    ui_spec = root / "ui_spec.md"
    master_doc.write_text(
        "# Master Doc\n\n"
        "## Conformance profile\n\n"
        "## Repo topology\n\n"
        "## Contracts\n\n"
        "## Traceability\n\n"
        "## Verification\n\n"
        "## Execution plan\n\n"
        "interactionProfile: hfvi_canvas_webgl_game\n",
        encoding="utf-8",
    )
    ui_spec.write_text("# UI Spec\n", encoding="utf-8")
    license_file = root / "LICENSE-APACHE-2.0.txt"
    license_file.write_text(
        "Licensed under the Apache License, Version 2.0; you may not use this file except in compliance with the License.\n",
        encoding="utf-8",
    )
    destination = root / "product"
    subprocess.run(
        [
            sys.executable, "-m", "dasleafer", "create", "--dest", str(destination),
            "--master-doc", str(master_doc), "--ui-spec", str(ui_spec),
            "--project-id", "wheel-hfvi-product",
            "--namespace", "io.examplecorp.wheelhfvi",
            "--display-name", "Wheel HFVI Product",
            "--initial-version", "0.1.0",
            "--license-id", "Apache-2.0",
            "--license-file", str(license_file),
            "--copyright", "2026 Example Corp",
        ],
        check=True,
    )
    assert (destination / "templates").exists() is False
    assert (destination / "tooling_lock.json").exists()
    assert subprocess.run(
        ["git", "-C", str(destination), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""
    subprocess.run(["bash", "scripts/verify"], cwd=destination, check=True)
PY
)
}
verify_installed
env -u PYTHONPATH "$temp/venv/bin/python" -m pip install --disable-pip-version-check --no-index --no-deps --force-reinstall "$temp"/sdist-wheel/dasleafer-*.whl
verify_installed
printf '{"task":"DAS-03-011","scenario":"das-leafer clean wheel install","status":"ok"}\n'
