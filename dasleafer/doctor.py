from __future__ import annotations

from ._dasops_bridge import import_dasops_module


_dasops_doctor = import_dasops_module("doctor")

DoctorReport = _dasops_doctor.DoctorReport
run_doctor = _dasops_doctor.run_doctor

__all__ = [
    "DoctorReport",
    "run_doctor",
]
