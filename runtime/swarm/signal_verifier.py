from __future__ import annotations

from typing import Any

from runtime.swarm.data_gate_permissions import data_gate_conclusion_permission, is_publication_target
from runtime.swarm.target_registry import TARGET_DATA_GATE, canonical_target
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def verify_agent_signal_proposals(state: dict[str, Any]) -> dict[str, Any]:
    """Promote or retain agent-emitted signal proposals using deterministic gates."""

    signals = (
        (state.get("pheromone_field_snapshot") or {}).get("signals")
        if isinstance(state.get("pheromone_field_snapshot"), dict)
        else []
    )
    if not isinstance(signals, list):
        signals = []
    promoted: list[PheromoneSignal] = []
    trace: list[dict[str, Any]] = []
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    existing_verified_targets = {
        canonical_target(str(signal.get("target") or ""))
        for signal in signals
        if signal.get("blocking") and signal.get("source_module") == "swarm_signal_verifier"
    }
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
        if not metadata.get("agent_emitted"):
            continue
        signal_id = str(signal.get("id") or "")
        signal_type = str(signal.get("type") or "")
        target = canonical_target(str(signal.get("target") or ""))
        if signal_type != SignalType.STOP_SIGNAL.value:
            trace.append(
                {
                    "signal_id": signal_id,
                    "target": target,
                    "status": "observed",
                    "reason": "non-stop agent proposal remains governed by normal signal strength",
                }
            )
            continue
        supported, reason = deterministic_stop_support(signal, state)
        if supported:
            if target in existing_verified_targets:
                trace.append(
                    {
                        "signal_id": signal_id,
                        "target": target,
                        "status": "already_promoted",
                        "reason": reason,
                    }
                )
                continue
            promoted_signal = PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.STOP_SIGNAL,
                target=target,
                content=f"Verified agent stop-signal proposal: {signal.get('content') or reason}",
                strength=max_float(signal.get("strength"), 0.9),
                confidence=max_float(signal.get("confidence"), 0.85),
                decay_rate=0.0,
                priority="hard",
                verification_state=VerificationState.BLOCKING,
                source_agent=empty_to_none(signal.get("source_agent")),
                source_module="swarm_signal_verifier",
                evidence_ref=signal_id or None,
                blocking=True,
                metadata={
                    "promoted_from_agent_signal": signal_id,
                    "promotion_reason": reason,
                },
            )
            promoted.append(promoted_signal)
            existing_verified_targets.add(target)
            trace.append(
                {
                    "signal_id": signal_id,
                    "target": target,
                    "status": "promoted",
                    "promoted_signal_id": promoted_signal.id,
                    "reason": reason,
                }
            )
        else:
            trace.append(
                {
                    "signal_id": signal_id,
                    "target": target,
                    "status": "retained_contested",
                    "reason": reason,
                }
            )
    return {"signals": promoted, "trace": trace}


def deterministic_stop_support(signal: dict[str, Any], state: dict[str, Any]) -> tuple[bool, str]:
    target = canonical_target(str(signal.get("target") or ""))
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    permission = data_gate_conclusion_permission(gate, target)
    if permission is False:
        return True, f"Data Gate conclusion permission blocks {target}."
    if permission is True:
        if is_publication_target(target):
            review = state.get("review") if isinstance(state.get("review"), dict) else {}
            status = str(review.get("status") or "").upper()
            if status in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
                return True, f"Critic status {status} blocks {target}."
        return False, f"Data Gate conclusion permission allows {target}."
    if is_publication_target(target):
        review = state.get("review") if isinstance(state.get("review"), dict) else {}
        status = str(review.get("status") or "").upper()
        if status in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
            return True, f"Critic status {status} blocks {target}."
        return False, f"No Data Gate or Critic publication block supports {target}."
    if target == TARGET_DATA_GATE:
        if gate.get("blocking") or str(gate.get("status") or "").upper() == "FAIL":
            return True, "Data Gate is already blocking."
        return False, "Data Gate is not in a blocking state."
    if target.startswith("tool:"):
        if any(
            isinstance(item, dict) and canonical_target(item.get("target")) == target and item.get("blocking")
            for item in state.get("stop_signals") or []
        ):
            return True, f"Existing system stop-signal already blocks {target}."
        return False, "No existing system tool stop-signal supports this proposal."
    return False, f"No deterministic promotion rule exists for target {target}."


def max_float(value: Any, floor: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = floor
    return max(floor, number)


def empty_to_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
