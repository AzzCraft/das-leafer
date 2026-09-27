from __future__ import annotations

from pathlib import Path

from .locks import (
    claim_ready_task,
    claim_task,
    complete_task,
    lock_path_for,
    read_lock,
    release_task,
)
from .tasks import list_tasks as _list_tasks, print_status, read_task_hints


def list_tasks(*, repo_root: Path, change_id: str):
    return _list_tasks(
        repo_root=repo_root,
        change_id=change_id,
        lock_reader=read_lock,
        lock_path_for=lock_path_for,
    )


__all__ = [
    "claim_ready_task",
    "claim_task",
    "complete_task",
    "list_tasks",
    "print_status",
    "read_task_hints",
    "release_task",
]
