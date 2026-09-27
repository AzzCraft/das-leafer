from __future__ import annotations

from ._dasops_bridge import import_dasops_module


_dasops_tasks = import_dasops_module("tasks")

DRAFT_MARKER = _dasops_tasks.DRAFT_MARKER
DRAFT_MARKER_LINE = _dasops_tasks.DRAFT_MARKER_LINE


def __getattr__(name: str):
    return getattr(_dasops_tasks, name)


__all__ = [
    "DRAFT_MARKER",
    "DRAFT_MARKER_LINE",
]
