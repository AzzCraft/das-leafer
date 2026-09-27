from __future__ import annotations

from ._dasops_bridge import import_dasops_module


_dasops_locks = import_dasops_module("locks")

DEFAULT_LEASE_SECONDS = _dasops_locks.DEFAULT_LEASE_SECONDS
TaskLock = _dasops_locks.TaskLock


def __getattr__(name: str):
    return getattr(_dasops_locks, name)


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "TaskLock",
]
