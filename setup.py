"""Package the Leafer scaffold with the installed CLI distribution.

The Python modules live under ``dasleafer/`` while the scaffold remains at the
repository root for source-tree review.  ``data_files`` places the complete
template under the active Python environment's share directory so an installed
wheel can create a project without a sibling checkout.
"""
from __future__ import annotations

from pathlib import Path

from setuptools import setup


TEMPLATE_ROOT = Path("templates") / "das-leafer-product"
TEMPLATE_FILES = [path for path in sorted(TEMPLATE_ROOT.rglob("*")) if path.is_file()]
DATA_FILES: list[tuple[str, list[str]]] = []
for path in TEMPLATE_FILES:
    relative_parent = path.relative_to(TEMPLATE_ROOT).parent
    target = Path("share") / "dasleafer" / "templates" / "das-leafer-product" / relative_parent
    DATA_FILES.append((str(target), [str(path)]))


setup(data_files=DATA_FILES)
