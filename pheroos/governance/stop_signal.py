from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StopSignal:
    target: str
    action: str
    reason: str
    blocking: bool = True


@dataclass(frozen=True)
class StopResolution:
    target: str
    action: str
    blocked: bool
    reason: str = ""


def resolve_stop_signal(signal: StopSignal) -> StopResolution:
    return StopResolution(target=signal.target, action=signal.action, blocked=signal.blocking, reason=signal.reason)
