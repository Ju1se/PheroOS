from __future__ import annotations

from collections import Counter
from time import time
from typing import Any, Iterable

from runtime.swarm.contracts import signal_contract
from runtime.swarm.event_log import swarm_event
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.types import PheromoneSignal, SignalType, enum_value


class PheromoneFieldManager:
    """Run-level typed signal field used to govern multi-agent collaboration."""

    def __init__(self, signals: Iterable[PheromoneSignal | dict[str, Any]] | None = None) -> None:
        self._signals: dict[str, PheromoneSignal] = {}
        self._trace: list[dict[str, Any]] = []
        for signal in signals or []:
            self.add(signal)

    def add(self, signal: PheromoneSignal | dict[str, Any]) -> PheromoneSignal:
        parsed = signal if isinstance(signal, PheromoneSignal) else PheromoneSignal.from_dict(signal)
        existing = self._signals.get(parsed.id)
        if existing is not None:
            existing.reinforce(parsed.strength * parsed.confidence * 0.2)
            self._trace.append(
                swarm_event(
                    event_type="pheromone.signal.reinforced",
                    run_id=existing.run_id,
                    actor=existing.source_module or existing.source_agent or "swarm",
                    target=existing.target,
                    lifecycle_state=str(existing.lifecycle_state.value if hasattr(existing.lifecycle_state, "value") else existing.lifecycle_state),
                    summary=f"Reinforced {enum_value(existing.type)} signal for {existing.target}.",
                    payload={"signal": existing.to_dict(), "contract": signal_contract(existing.to_dict())},
                )
            )
            return existing
        self._signals[parsed.id] = parsed
        self._trace.append(
            swarm_event(
                event_type="pheromone.signal.created",
                run_id=parsed.run_id,
                actor=parsed.source_module or parsed.source_agent or "swarm",
                target=parsed.target,
                lifecycle_state=str(parsed.lifecycle_state.value if hasattr(parsed.lifecycle_state, "value") else parsed.lifecycle_state),
                summary=f"Created {enum_value(parsed.type)} signal for {parsed.target}.",
                payload={"signal": parsed.to_dict(), "contract": signal_contract(parsed.to_dict())},
            )
        )
        return parsed

    def update_many(self, signals: Iterable[PheromoneSignal | dict[str, Any]]) -> list[PheromoneSignal]:
        return [self.add(signal) for signal in signals]

    def signals(self, *, include_expired: bool = False) -> list[PheromoneSignal]:
        now = time()
        items = list(self._signals.values())
        if include_expired:
            return items
        return [signal for signal in items if not signal.is_expired(now=now)]

    def by_type(self, signal_type: SignalType | str) -> list[PheromoneSignal]:
        expected = enum_value(signal_type)
        return [signal for signal in self.signals() if enum_value(signal.type) == expected]

    def by_target(self, target: str) -> list[PheromoneSignal]:
        expected = canonical_target(target)
        return [signal for signal in self.signals() if canonical_target(signal.target) == expected]

    def blocking_signals(self, *, targets: Iterable[str] | None = None) -> list[PheromoneSignal]:
        target_set = {canonical_target(target) for target in targets or []}
        return [
            signal
            for signal in self.signals()
            if is_active_blocker(signal.to_dict()) and (not target_set or canonical_target(signal.target) in target_set)
        ]

    def has_blocking_signal(self, *, targets: Iterable[str] | None = None) -> bool:
        return bool(self.blocking_signals(targets=targets))

    def snapshot(self) -> dict[str, Any]:
        signals = [signal.to_dict() for signal in self.signals()]
        counts = Counter(signal["type"] for signal in signals)
        blocking = [signal for signal in signals if is_active_blocker(signal)]
        return {
            "signal_count": len(signals),
            "type_counts": dict(sorted(counts.items())),
            "blocking_targets": sorted({canonical_target(signal.get("target")) for signal in blocking}),
            "signals": signals,
            "stop_signals": [signal for signal in signals if signal.get("type") == SignalType.STOP_SIGNAL.value],
            "constraint_signals": [signal for signal in signals if signal.get("type") == SignalType.CONSTRAINT.value],
            "evidence_signals": [signal for signal in signals if signal.get("type") == SignalType.EVIDENCE.value],
        }

    def trace(self) -> list[dict[str, Any]]:
        return list(self._trace)


def field_from_state(state: dict[str, Any]) -> PheromoneFieldManager:
    signals = state.get("pheromone_field_snapshot")
    if isinstance(signals, dict) and isinstance(signals.get("signals"), list):
        return PheromoneFieldManager(signals.get("signals"))
    if isinstance(state.get("pheromone_trace"), list):
        trace_signals = []
        for event in state.get("pheromone_trace") or []:
            if isinstance(event, dict) and isinstance(event.get("signal"), dict):
                trace_signals.append(event["signal"])
            elif (
                isinstance(event, dict)
                and isinstance(event.get("payload"), dict)
                and isinstance(event["payload"].get("signal"), dict)
            ):
                trace_signals.append(event["payload"]["signal"])
            elif isinstance(event, dict) and event.get("type") and event.get("target"):
                trace_signals.append(event)
        return PheromoneFieldManager(trace_signals)
    return PheromoneFieldManager()
