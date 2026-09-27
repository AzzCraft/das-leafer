from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generated_workflow_is_pinned_and_credentialless() -> None:
    workflow = (
        ROOT / "templates" / "das-leafer-product" / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")
    requirements = (ROOT / "templates" / "das-leafer-product" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "permissions:\n  contents: read" in workflow
    assert "actions/checkout@692973e3d937129bcbf40652eb9f2f61becf3332" in workflow
    assert "actions/setup-python@82c7e631bb3cdc910f68e0081d67478d79c6982d" in workflow
    assert "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020" in workflow
    assert "persist-credentials: false" in workflow
    assert "pip install --upgrade pip" not in workflow
    assert "PyYAML==6.0.3" in requirements
    assert "node-version: '22.23.1'" in workflow
    assert "cache-dependency-path: frontend/package-lock.json" in workflow
    assert "npm ci --prefix frontend --ignore-scripts --no-audit --fund=false" in workflow
    assert "HFVI_BROWSER_URL: https://storage.googleapis.com/chrome-for-testing-public/147.0.7727.55/linux64/chrome-linux64.zip" in workflow
    assert "HFVI_BROWSER_BYTES: '179123229'" in workflow
    assert "HFVI_BROWSER_MD5: 65f3a8ba6c79c7e099937c887335a8e9" in workflow
    assert "md5sum --check --status" in workflow
    assert "HFVI_BROWSER_BINARY=$PWD/.hfvi-toolchain/chrome-linux64/chrome" in workflow


def test_generated_workflow_no_longer_relies_on_a_policy_exception() -> None:
    # This contract belongs to the exported workflow, not an internal parent policy.
    workflow = (ROOT / "templates/das-leafer-product/.github/workflows/ci.yml").read_text()
    assert "contents: write" not in workflow
    assert "pull_request_target" not in workflow



def test_hfvi_browser_and_frontend_inputs_are_locked() -> None:
    template = ROOT / "templates" / "das-leafer-product"
    browser = json.loads((template / "hfvi" / "browser.lock.json").read_text(encoding="utf-8"))
    package = json.loads((template / "frontend" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((template / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    runner = (template / "scripts" / "hfvi_replay.py").read_text(encoding="utf-8")

    assert browser["engine"] == "chrome-for-testing"
    assert browser["productVersion"] == "147.0.7727.55"
    assert browser["archive"] == {
        "url": "https://storage.googleapis.com/chrome-for-testing-public/147.0.7727.55/linux64/chrome-linux64.zip",
        "contentLength": 179123229,
        "md5": "65f3a8ba6c79c7e099937c887335a8e9",
    }
    assert browser["viewport"] == {"width": 1024, "height": 768, "deviceScaleFactor": 1}
    assert browser["pixelThreshold"] == {"maxPixels": 0, "maxChannelDelta": 0}
    assert package["dependencies"] == {"leafer-ui": "1.12.2"}
    assert package["devDependencies"] == {"typescript": "5.6.3", "vite": "7.3.6"}
    assert package_lock["packages"][""]["dependencies"] == package["dependencies"]
    assert package_lock["packages"][""]["devDependencies"] == package["devDependencies"]
    assert "Page.captureScreenshot" in runner
    assert "dataset.hfviReplay" in runner
    assert "--remote-debugging-pipe" in runner
    assert "HFVI pixel diff" in runner
    assert "frontend build did not produce dist/index.html" in runner
