from __future__ import annotations

from ._dasops_bridge import import_dasops_module


_dasops_adopt = import_dasops_module("adopt")

AuditResult = _dasops_adopt.AuditResult
audit_repo = _dasops_adopt.audit_repo
normalize_repo = _dasops_adopt.normalize_repo

__all__ = [
    "AuditResult",
    "audit_repo",
    "normalize_repo",
]
