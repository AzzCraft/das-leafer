from __future__ import annotations

import importlib
import importlib.util


def ensure_dasops_importable() -> None:
    if importlib.util.find_spec("dasops") is not None:
        return
    raise ModuleNotFoundError(
        "dasops is required for delegated Leafer workflows. "
        "Install the declared dasops package release before running Leafer."
    )


def import_dasops_module(module_name: str):
    ensure_dasops_importable()
    return importlib.import_module(f"dasops.{module_name}")
