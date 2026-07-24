from __future__ import annotations

from dataclasses import dataclass
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.errors import GovernanceError
from pheroos.governance.signal import SignalVerification
from pheroos.governance.signal import signal_verification_matches
from typing import Any
import math


@dataclass(frozen=True)
class ScoutReport:
    scout_id: str
    candidate_id: str
    evidence_id: str
    provenance: str
    support: float = 1.0
    target: str = ""
    trace_event_id: str = ""
    verification: SignalVerification | None = None


@dataclass(frozen=True)
class RecruitmentSignal:
    source_id: str
    candidate_id: str
    strength: float = 1.0
    target: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    verification: SignalVerification | None = None


@dataclass(frozen=True)
class InhibitionSignal:
    source_id: str
    candidate_id: str
    strength: float = 1.0
    target: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    verification: SignalVerification | None = None


def validate_scout_report(
    report: ScoutReport,
    *,
    target: str | None,
    require_verification: bool,
    maximum_strength: float,
) -> None:
    if not is_nonblank_string(report.scout_id):
        raise GovernanceError("scout report scout_id is required")
    if not is_nonblank_string(report.evidence_id):
        raise GovernanceError("scout report evidence_id is required")
    if not is_nonblank_string(report.provenance):
        raise GovernanceError(
            f"scout report evidence is missing provenance: {report.evidence_id}"
        )
    require_finite_bounded_strength(
        report.support,
        "scout report support",
        maximum_strength,
    )
    if target is not None and report.target and report.target != target:
        raise GovernanceError(
            f"scout report targets {report.target}, not active target {target}"
        )
    if require_verification:
        if report.target != target:
            raise GovernanceError(
                "verified swarm scout report must declare the active target"
            )
        if not is_nonblank_string(report.trace_event_id):
            raise GovernanceError(
                "verified swarm scout report trace_event_id is required"
            )
        if not signal_verification_matches(
            report.verification,
            target=target or "",
            source_id=report.scout_id,
            subject_id=report.candidate_id,
        ):
            raise GovernanceError("swarm scout report is not governance-verified")


def validate_collective_signal(
    signal: RecruitmentSignal | InhibitionSignal,
    *,
    target: str | None,
    require_verification: bool,
    signal_name: str,
    maximum_strength: float,
) -> None:
    if not is_nonblank_string(signal.source_id):
        raise GovernanceError(f"{signal_name} signal source_id is required")
    require_finite_bounded_strength(
        signal.strength,
        f"{signal_name} signal strength",
        maximum_strength,
    )
    if target is not None and signal.target and signal.target != target:
        raise GovernanceError(
            f"{signal_name} signal targets {signal.target}, not active target {target}"
        )
    if require_verification:
        if signal.target != target:
            raise GovernanceError(
                f"verified swarm {signal_name} signal must declare the active target"
            )
        if not is_nonblank_string(signal.provenance):
            raise GovernanceError(f"swarm {signal_name} signal provenance is required")
        if not is_nonblank_string(signal.trace_event_id):
            raise GovernanceError(
                f"swarm {signal_name} signal trace_event_id is required"
            )
        if not signal_verification_matches(
            signal.verification,
            target=target or "",
            source_id=signal.source_id,
            subject_id=signal.candidate_id,
        ):
            raise GovernanceError(
                f"swarm {signal_name} signal is not governance-verified"
            )


def require_finite_non_negative(value: Any, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise GovernanceError(f"{name} must be a finite number")
    if value < 0:
        raise GovernanceError(f"{name} must be non-negative")


def require_finite_bounded_strength(value: Any, name: str, maximum: float) -> None:
    require_finite_non_negative(value, name)
    require_finite_non_negative(maximum, f"{name} maximum")
    if float(value) > float(maximum):
        raise GovernanceError(f"{name} exceeds the declared collective threshold bound")


for _compat_function in (
    validate_scout_report,
    validate_collective_signal,
    require_finite_non_negative,
    require_finite_bounded_strength,
):
    _compat_function.__module__ = "pheroos.governance.collective"
del _compat_function
for _compat_type in (
    ScoutReport,
    RecruitmentSignal,
    InhibitionSignal,
):
    _compat_type.__module__ = "pheroos.governance.collective"
    for _compat_descriptor in _compat_type.__dict__.values():
        if isinstance(_compat_descriptor, (staticmethod, classmethod)):
            _compat_member = _compat_descriptor.__func__
        else:
            _compat_member = _compat_descriptor
        if callable(_compat_member) and hasattr(_compat_member, "__module__"):
            _compat_member.__module__ = "pheroos.governance.collective"
del _compat_descriptor, _compat_member, _compat_type

__all__ = (
    "InhibitionSignal",
    "RecruitmentSignal",
    "ScoutReport",
    "require_finite_bounded_strength",
    "require_finite_non_negative",
    "validate_collective_signal",
    "validate_scout_report",
)
