from __future__ import annotations

from collections import Counter
from typing import Any

from runtime.legacy_agent_registry import legacy_committee_agent_catalog_from_metadata
from runtime.swarm.event_log import swarm_event
from runtime.swarm.pheromone_field import field_from_state
from runtime.swarm.signal_extractor import agent_emitted_signals
from runtime.swarm.target_registry import canonical_target, target_kind
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState, enum_value


EXECUTION_LOOP_SCHEMA_VERSION = "pheroos.execution_loop.v1"


def run_swarm_execution_loop(state: dict[str, Any], *, max_rounds: int = 2) -> dict[str, Any]:
    """Run a deterministic PheroOS observe/propose/verify/schedule loop.

    The loop is a governance surface, not domain execution. It lets recruited
    agent plugins observe canonical goals and propose typed signals, while the
    protocol keeps every agent proposal unverified/contested until another
    deterministic gate promotes it.
    """

    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    allocations = [item for item in swarm_plan.get("agent_allocation") or [] if isinstance(item, dict)]
    activated = [item for item in allocations if item.get("activated")]
    targets = goal_targets_from_swarm_plan(swarm_plan)
    agents = agent_manifest_index(metadata)
    recovery_protocols = [item for item in swarm_plan.get("recovery_protocols") or [] if isinstance(item, dict)]
    configured_max_rounds = safe_int(swarm_plan.get("max_rounds"), max_rounds)

    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str(metadata.get("tenant_id") or "default")
    if not activated or not targets:
        return {
            "schema_version": EXECUTION_LOOP_SCHEMA_VERSION,
            "status": "skipped",
            "reason": "no activated agents or no canonical goal targets",
            "rounds": [],
            "signals": [],
            "events": [
                swarm_event(
                    event_type="swarm.execution.skipped",
                    run_id=run_id,
                    tenant_id=tenant_id,
                    actor="pheroos.execution_loop",
                    summary="Skipped swarm execution loop because no activated agents or targets were available.",
                    payload={
                        "activated_agent_count": len(activated),
                        "target_count": len(targets),
                    },
                )
            ],
        }

    all_signals: list[PheromoneSignal] = []
    rounds: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    current_wave = activated
    prior_signal_keys: set[tuple[str, str, str]] = set()

    for round_index in range(1, max(1, configured_max_rounds) + 1):
        field = field_from_state({**state, "pheromone_field_snapshot": merged_snapshot(state, all_signals)})
        observe_rows: list[dict[str, Any]] = []
        proposal_rows: list[dict[str, Any]] = []
        verification_rows: list[dict[str, Any]] = []
        accepted_round_signals: list[PheromoneSignal] = []

        for allocation in current_wave:
            agent_key = str(allocation.get("agent") or "").strip()
            if not agent_key:
                continue
            spec = agents.get(agent_key) or minimal_agent_spec(allocation)
            local_view = agent_local_view(agent_key=agent_key, allocation=allocation, targets=targets, field=field)
            observe_rows.append(local_view)
            raw_proposals = propose_agent_signals(
                agent_key=agent_key,
                allocation=allocation,
                spec=spec,
                local_view=local_view,
                round_index=round_index,
            )
            proposal_rows.extend(raw_proposals)
            validated = agent_emitted_signals(
                raw_proposals,
                agent_key=agent_key,
                spec=spec,
                run_id=run_id,
                tenant_id=tenant_id,
            )
            for signal in validated["accepted_signals"]:
                signal.source_module = "swarm_execution_loop"
                signal.metadata = {
                    **signal.metadata,
                    "execution_loop": True,
                    "round": round_index,
                    "local_view": {
                        "observed_target_count": len(local_view.get("observed_targets") or []),
                        "active_blocker_count": len(local_view.get("active_blockers") or []),
                    },
                }
                key = (str(signal.source_agent or ""), canonical_target(signal.target), enum_value(signal.type))
                if key in prior_signal_keys:
                    verification_rows.append(loop_verification_row(signal, status="deduped", reason="same agent already proposed this signal type for this target"))
                    continue
                prior_signal_keys.add(key)
                accepted_round_signals.append(signal)
                verification_rows.append(verify_loop_signal(signal, local_view=local_view))
            for diagnostic in validated["diagnostics"]:
                if diagnostic.get("status") != "accepted":
                    verification_rows.append(
                        {
                            "agent": diagnostic.get("agent"),
                            "target": diagnostic.get("target"),
                            "signal_type": diagnostic.get("type"),
                            "status": "rejected",
                            "reason": diagnostic.get("reason"),
                        }
                    )

        all_signals.extend(accepted_round_signals)
        next_wave = schedule_next_wave(
            allocations=allocations,
            accepted_signals=accepted_round_signals,
            round_index=round_index,
            recovery_protocols=recovery_protocols,
        )
        round_record = {
            "round": round_index,
            "wave_agents": [str(item.get("agent") or "") for item in current_wave if item.get("agent")],
            "observe": observe_rows,
            "proposals": proposal_rows,
            "verification": verification_rows,
            "accepted_signal_count": len(accepted_round_signals),
            "scheduled_next_wave": [str(item.get("agent") or "") for item in next_wave if item.get("agent")],
        }
        rounds.append(round_record)
        events.append(
            swarm_event(
                event_type="swarm.execution.round_completed",
                run_id=run_id,
                tenant_id=tenant_id,
                actor="pheroos.execution_loop",
                summary=f"PheroOS execution loop completed round {round_index}.",
                payload=round_record,
            )
        )
        if not next_wave:
            break
        current_wave = next_wave

    return {
        "schema_version": EXECUTION_LOOP_SCHEMA_VERSION,
        "status": "completed",
        "intent": os_plan.get("intent") or os_plan.get("task_type"),
        "max_rounds": configured_max_rounds,
        "round_count": len(rounds),
        "protocol_source": swarm_plan.get("protocol_source"),
        "capability_protocols": swarm_plan.get("capability_protocols", []),
        "candidate_policy": swarm_plan.get("candidate_policy", {}),
        "quorum_policy": swarm_plan.get("quorum_policy", {}),
        "stop_signal_policy": swarm_plan.get("stop_signal_policy", {}),
        "recovery_protocols": recovery_protocols,
        "activated_agents": [str(item.get("agent") or "") for item in activated if item.get("agent")],
        "target_count": len(targets),
        "targets": targets,
        "accepted_signal_count": len(all_signals),
        "rounds": rounds,
        "signals": all_signals,
        "events": events,
    }


def public_execution_loop_report(loop: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "schema_version": loop.get("schema_version"),
            "status": loop.get("status"),
            "reason": loop.get("reason"),
            "intent": loop.get("intent"),
            "max_rounds": loop.get("max_rounds"),
            "round_count": loop.get("round_count", 0),
            "activated_agents": loop.get("activated_agents", []),
            "target_count": loop.get("target_count", 0),
            "targets": loop.get("targets", []),
            "accepted_signal_count": loop.get("accepted_signal_count", 0),
            "rounds": loop.get("rounds", []),
            "events": loop.get("events", []),
            "protocol_source": loop.get("protocol_source"),
            "capability_protocols": loop.get("capability_protocols", []),
            "candidate_policy": loop.get("candidate_policy", {}),
            "quorum_policy": loop.get("quorum_policy", {}),
            "stop_signal_policy": loop.get("stop_signal_policy", {}),
            "recovery_protocols": loop.get("recovery_protocols", []),
            "accepted_signals": [
                signal.to_dict() if isinstance(signal, PheromoneSignal) else signal
                for signal in loop.get("signals") or []
            ],
        }.items()
        if value is not None
    }


def goal_targets_from_swarm_plan(swarm_plan: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in swarm_plan.get("target_signals") or []:
        if not isinstance(item, dict):
            continue
        canonical = canonical_target(item.get("canonical_target") or item.get("target") or "run")
        if canonical in seen:
            continue
        seen.add(canonical)
        targets.append(
            {
                "target": canonical,
                "target_kind": target_kind(canonical),
                "demand_strength": safe_float(item.get("demand_strength"), 0.6),
                "content": str(item.get("content") or f"Goal demand for {canonical}."),
            }
        )
    return targets


def agent_manifest_index(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: list[Any] = []
    registry = metadata.get("agent_registry") if isinstance(metadata.get("agent_registry"), dict) else {}
    candidates.extend(registry.get("agents") or [])
    candidates.extend(metadata.get("agent_catalog") or [])
    candidates.extend(legacy_committee_agent_catalog_from_metadata(metadata))
    output: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key:
            output[key] = item
    return output


def minimal_agent_spec(allocation: dict[str, Any]) -> dict[str, Any]:
    key = str(allocation.get("agent") or "")
    return {
        "key": key,
        "name": allocation.get("name") or key,
        "agent_type": allocation.get("agent_type"),
        "committee_role": allocation.get("committee_role"),
        "swarm": {"signal_emit_permissions": ["progress"], "can_block": False},
    }


def agent_local_view(
    *,
    agent_key: str,
    allocation: dict[str, Any],
    targets: list[dict[str, Any]],
    field: Any,
) -> dict[str, Any]:
    matched_targets = matched_targets_for_allocation(allocation, targets)
    active_blockers = [signal.to_dict() for signal in field.blocking_signals()]
    signal_counts = Counter(enum_value(signal.type) for signal in field.signals())
    return {
        "agent": agent_key,
        "observed_targets": matched_targets,
        "active_blockers": [
            {
                "target": item.get("target"),
                "type": item.get("type"),
                "source_module": item.get("source_module"),
            }
            for item in active_blockers
        ],
        "signal_counts": dict(sorted(signal_counts.items())),
        "activation_reason": allocation.get("activation_reason"),
        "utility": allocation.get("utility"),
    }


def matched_targets_for_allocation(allocation: dict[str, Any], targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_matches = allocation.get("matched_targets") if isinstance(allocation.get("matched_targets"), list) else []
    matched = {canonical_target(item.get("canonical_target") or item.get("target")) for item in raw_matches if isinstance(item, dict)}
    if not matched:
        matched = {str(target.get("target")) for target in targets}
    return [target for target in targets if canonical_target(target.get("target")) in matched]


def propose_agent_signals(
    *,
    agent_key: str,
    allocation: dict[str, Any],
    spec: dict[str, Any],
    local_view: dict[str, Any],
    round_index: int,
) -> list[dict[str, Any]]:
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    allowed = {str(item).strip().lower() for item in swarm.get("signal_emit_permissions") or []}
    proposals: list[dict[str, Any]] = []
    for target in local_view.get("observed_targets") or []:
        if not isinstance(target, dict):
            continue
        canonical = canonical_target(target.get("target"))
        signal_type = choose_signal_type_for_agent(allowed=allowed, canonical_target_value=canonical)
        if signal_type is None:
            continue
        proposals.append(
            {
                "type": signal_type.value,
                "target": canonical,
                "content": proposal_content(
                    agent_key=agent_key,
                    allocation=allocation,
                    signal_type=signal_type,
                    target=target,
                    round_index=round_index,
                ),
                "strength": proposal_strength(target, round_index=round_index),
                "confidence": proposal_confidence(signal_type),
                "priority": "high" if signal_type in {SignalType.RISK, SignalType.NEGATIVE, SignalType.STOP_SIGNAL} else "normal",
            }
        )
    return proposals


def choose_signal_type_for_agent(*, allowed: set[str], canonical_target_value: str) -> SignalType | None:
    kind = target_kind(canonical_target_value)
    if kind in {"gate", "issue", "constraint"}:
        for candidate in (SignalType.RISK, SignalType.NEGATIVE, SignalType.STOP_SIGNAL, SignalType.EVIDENCE, SignalType.PROGRESS):
            if candidate.value in allowed:
                return candidate
    if kind in {"decision", "candidate"}:
        for candidate in (SignalType.EVIDENCE, SignalType.RISK, SignalType.PROGRESS):
            if candidate.value in allowed:
                return candidate
    for candidate in (SignalType.EVIDENCE, SignalType.PROGRESS, SignalType.RISK, SignalType.NEGATIVE, SignalType.STOP_SIGNAL):
        if candidate.value in allowed:
            return candidate
    return None


def proposal_content(
    *,
    agent_key: str,
    allocation: dict[str, Any],
    signal_type: SignalType,
    target: dict[str, Any],
    round_index: int,
) -> str:
    target_name = str(target.get("target") or "run")
    if signal_type == SignalType.RISK:
        return f"{agent_key} flags that {target_name} needs protocol attention before synthesis."
    if signal_type == SignalType.NEGATIVE:
        return f"{agent_key} challenges overconfident use of {target_name}."
    if signal_type == SignalType.STOP_SIGNAL:
        return f"{agent_key} proposes a stop-signal for {target_name}; deterministic verifier must decide."
    if signal_type == SignalType.EVIDENCE:
        return f"{agent_key} contributes an unverified work signal toward {target_name}."
    return f"{agent_key} made progress on {target_name} in swarm loop round {round_index}."


def proposal_strength(target: dict[str, Any], *, round_index: int) -> float:
    demand = safe_float(target.get("demand_strength"), 0.55)
    round_bonus = 0.04 if round_index == 1 else 0.0
    return min(0.86, max(0.35, demand * 0.7 + round_bonus))


def proposal_confidence(signal_type: SignalType) -> float:
    if signal_type in {SignalType.RISK, SignalType.NEGATIVE, SignalType.STOP_SIGNAL}:
        return 0.52
    return 0.58


def verify_loop_signal(signal: PheromoneSignal, *, local_view: dict[str, Any]) -> dict[str, Any]:
    if signal.type == SignalType.STOP_SIGNAL:
        return loop_verification_row(
            signal,
            status="retained_contested",
            reason="agent stop-signal proposals require deterministic support before promotion",
        )
    if signal.type in {SignalType.RISK, SignalType.NEGATIVE}:
        return loop_verification_row(
            signal,
            status="accepted_contested",
            reason="risk/challenge proposal accepted into field but cannot block without system support",
        )
    return loop_verification_row(
        signal,
        status="accepted_unverified",
        reason="work/evidence proposal accepted into field as unverified swarm signal",
    )


def loop_verification_row(signal: PheromoneSignal, *, status: str, reason: str) -> dict[str, Any]:
    return {
        "signal_id": signal.id,
        "agent": signal.source_agent,
        "target": canonical_target(signal.target),
        "signal_type": enum_value(signal.type),
        "verification_state": enum_value(signal.verification_state),
        "blocking": bool(signal.blocking),
        "status": status,
        "reason": reason,
    }


def schedule_next_wave(
    *,
    allocations: list[dict[str, Any]],
    accepted_signals: list[PheromoneSignal],
    round_index: int,
    recovery_protocols: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    max_recovery_rounds = max([safe_int(item.get("max_rounds"), 2) for item in recovery_protocols or []] or [2])
    if round_index >= max_recovery_rounds:
        return []
    pressure_targets = {
        canonical_target(signal.target)
        for signal in accepted_signals
        if signal.type in {SignalType.RISK, SignalType.NEGATIVE, SignalType.STOP_SIGNAL}
    }
    if not pressure_targets:
        return []
    protocol_targets = {
        canonical_target(target.get("canonical_target") or target.get("target"))
        for protocol in recovery_protocols or []
        for target in protocol.get("targets", [])
        if isinstance(target, dict)
    }
    if protocol_targets:
        pressure_targets.update(protocol_targets)
    next_wave = []
    for allocation in allocations:
        if not allocation.get("activated"):
            continue
        matched = {
            canonical_target(item.get("canonical_target") or item.get("target"))
            for item in allocation.get("matched_targets") or []
            if isinstance(item, dict)
        }
        if matched & pressure_targets:
            next_wave.append(allocation)
    return sorted(next_wave, key=lambda item: (-safe_float(item.get("utility"), 0.0), str(item.get("agent") or "")))[:4]


def merged_snapshot(state: dict[str, Any], extra_signals: list[PheromoneSignal]) -> dict[str, Any]:
    snapshot = state.get("pheromone_field_snapshot") if isinstance(state.get("pheromone_field_snapshot"), dict) else {}
    signals = list(snapshot.get("signals") or [])
    signals.extend(signal.to_dict() for signal in extra_signals)
    return {**snapshot, "signals": signals}


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
