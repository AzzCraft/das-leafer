from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_leafer_verification_workflow_uses_the_immutable_tool_lock() -> None:
    workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
    assert "pip install --upgrade pip" not in workflow
    assert "--disable-pip-version-check -r requirements-verify.txt" in workflow
    assert "pip-audit --progress-spinner off --strict -r requirements-verify.txt" in workflow
    assert "bandit -q -lll -r dasleafer" in workflow
