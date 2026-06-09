from __future__ import annotations

from typing import Any, Iterable

from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    is_publication_target,
    publication_conclusion_permission_target,
)
from runtime.swarm.action_policy import (
    source_policy_block_message,
    source_policy_blocked_tool_targets,
    source_policy_constraint_message,
)
from runtime.swarm.authority import AGENT_PROPOSAL_MODULE
from runtime.swarm.pheromone_field import PheromoneFieldManager, field_from_state
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.tool_plan_policy import web_tools_disabled_for_state
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def update_state_with_signals(
    state: dict[str, Any],
    signals: Iterable[PheromoneSignal | dict[str, Any]],
) -> dict[str, Any]:
    field = field_from_state(state)
    field.update_many(signals)
    snapshot = field.snapshot()
    return {
        "pheromone_field_snapshot": snapshot,
        "pheromone_trace": field.trace(),
        "stop_signals": snapshot["stop_signals"],
        "constraint_signals": snapshot["constraint_signals"],
        "swarm_metrics": swarm_metrics(snapshot),
    }


def initial_signals_from_state(state: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    signals: list[PheromoneSignal] = []

    signals.extend(input_preflight_signals(metadata, run_id=run_id, tenant_id=tenant_id))
    signals.extend(os_plan_goal_signals(metadata, run_id=run_id, tenant_id=tenant_id))
    signals.extend(runtime_capability_signals(metadata, run_id=run_id, tenant_id=tenant_id))

    if web_tools_disabled_for_state(state):
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.CONSTRAINT,
                target="data_source_policy",
                content=source_policy_constraint_message(state),
                strength=1.0,
                confidence=1.0,
                decay_rate=0.0,
                priority="hard",
                verification_state=VerificationState.VERIFIED,
                source_module="os_kernel",
            )
        )
        blocked_tool_targets = sorted(source_policy_blocked_tool_targets(state))
        for target in blocked_tool_targets:
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.STOP_SIGNAL,
                    target=target,
                    content=source_policy_block_message(state, target, initial_signal=True),
                    strength=1.0,
                    confidence=1.0,
                    decay_rate=0.0,
                    priority="hard",
                    verification_state=VerificationState.BLOCKING,
                    source_module="os_kernel",
                    blocking=True,
                    metadata={"source_policy_blocked_tool_targets": blocked_tool_targets},
                )
            )

    permission_grants = metadata.get("permission_grants")
    if isinstance(permission_grants, list):
        signals.extend(permission_signals(permission_grants, run_id=run_id, tenant_id=tenant_id))

    for issue in metadata.get("runtime_validation_issues") or []:
        if not isinstance(issue, dict):
            continue
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.RISK,
                target=str(issue.get("code") or "runtime_validation"),
                content=str(issue.get("message") or issue),
                strength=0.8,
                confidence=0.9,
                source_module="runtime_materializer",
                metadata={"issue": issue},
            )
        )
    return signals


def input_preflight_signals(metadata: dict[str, Any], *, run_id: str, tenant_id: str) -> list[PheromoneSignal]:
    report = metadata.get("input_preflight") if isinstance(metadata.get("input_preflight"), dict) else {}
    signals: list[PheromoneSignal] = []
    for risk in report.get("input_risks") or []:
        if not isinstance(risk, dict):
            continue
        code = str(risk.get("code") or "input_risk")
        signal_type = SignalType.CONTAMINATION if "prompt_injection" in code or "secret" in code else SignalType.RISK
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=signal_type,
                target=f"input:{code}",
                content=f"Input preflight detected {code}.",
                strength=0.95,
                confidence=0.95,
                priority="hard" if signal_type == SignalType.CONTAMINATION else "high",
                decay_rate=0.0,
                verification_state=VerificationState.BLOCKING if signal_type == SignalType.CONTAMINATION else VerificationState.VERIFIED,
                source_module="input_preflight",
                blocking=signal_type == SignalType.CONTAMINATION,
                metadata={"risk": risk},
            )
        )
    for artifact in report.get("quarantine_artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.QUARANTINE,
                target=f"artifact:{artifact.get('artifact_id') or 'input'}",
                content=str(artifact.get("reason") or "Input artifact quarantined by preflight."),
                strength=1.0,
                confidence=0.95,
                priority="hard",
                decay_rate=0.0,
                verification_state=VerificationState.BLOCKING,
                source_module="input_preflight",
                blocking=True,
                metadata={"artifact": artifact},
            )
        )
    for constraint in report.get("detected_constraints") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.CONSTRAINT,
                target=f"constraint:{constraint}",
                content=f"User constraint detected at input preflight: {constraint}.",
                strength=0.9,
                confidence=0.9,
                priority="high",
                verification_state=VerificationState.VERIFIED,
                source_module="input_preflight",
                metadata={"constraint": constraint},
            )
        )
    return signals


def os_plan_goal_signals(metadata: dict[str, Any], *, run_id: str, tenant_id: str) -> list[PheromoneSignal]:
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    signals: list[PheromoneSignal] = []
    for goal in swarm_plan.get("target_signals") or []:
        if not isinstance(goal, dict):
            continue
        target = str(goal.get("canonical_target") or goal.get("target") or "run")
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.DEMAND,
                target=target,
                content=str(goal.get("content") or f"Goal demand for {target}."),
                strength=float(goal.get("demand_strength") or 0.6),
                confidence=0.9,
                decay_rate=0.02,
                priority="high",
                verification_state=VerificationState.VERIFIED,
                source_module="os_kernel",
                metadata={"goal": goal, "intent": os_plan.get("intent")},
            )
        )
    for allocation in swarm_plan.get("agent_allocation") or []:
        if not isinstance(allocation, dict) or not allocation.get("activated"):
            continue
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.LANE_ASSIGNMENT,
                target=f"agent:{allocation.get('agent')}",
                content=str(allocation.get("activation_reason") or "Agent activated by PheroOS goal router."),
                strength=float(allocation.get("utility") or 0.5),
                confidence=0.85,
                source_module="os_kernel",
                metadata={"allocation": allocation},
            )
        )
    return signals


def runtime_capability_signals(metadata: dict[str, Any], *, run_id: str, tenant_id: str) -> list[PheromoneSignal]:
    signals: list[PheromoneSignal] = []
    for capability in metadata.get("enabled_capabilities") or []:
        if not isinstance(capability, dict):
            continue
        capability_id = str(capability.get("id") or "capability")
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.CAPABILITY,
                target=f"capability:{capability_id}",
                content=f"Capability enabled for runtime: {capability_id}.",
                strength=0.8,
                confidence=0.9,
                verification_state=VerificationState.VERIFIED,
                source_module="runtime_materializer",
                metadata={"capability": {"id": capability_id, "risk_level": capability.get("risk_level")}},
            )
        )
    routing = metadata.get("model_routing_policy") if isinstance(metadata.get("model_routing_policy"), dict) else {}
    selected_models = routing.get("selected_models") if isinstance(routing.get("selected_models"), dict) else {}
    for role, model in selected_models.items():
        if not model:
            continue
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.MODEL_ROUTE,
                target=f"model:{role}",
                content=f"Model route for {role} uses configured gateway handle.",
                strength=0.65,
                confidence=0.8,
                verification_state=VerificationState.VERIFIED,
                source_module="runtime_materializer",
                metadata={"role": role, "model": str(model)},
            )
        )
    return signals


def permission_signals(permission_decisions: list[dict[str, Any]], *, run_id: str, tenant_id: str) -> list[PheromoneSignal]:
    signals: list[PheromoneSignal] = []
    for decision in permission_decisions:
        if not isinstance(decision, dict):
            continue
        capability_id = str(decision.get("capability_id") or "capability")
        for permission in decision.get("permission_grants") or []:
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.PERMISSION,
                    target=str(permission),
                    content=f"{permission} granted for {capability_id}.",
                    strength=1.0,
                    confidence=1.0,
                    decay_rate=0.0,
                    priority="hard",
                    verification_state=VerificationState.VERIFIED,
                    source_module="permission_policy",
                    metadata={"capability_id": capability_id},
                )
            )
        for permission in decision.get("blocked_permissions") or []:
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.STOP_SIGNAL,
                    target=str(permission),
                    content=f"{permission} requires explicit user confirmation before execution.",
                    strength=1.0,
                    confidence=1.0,
                    decay_rate=0.0,
                    priority="hard",
                    verification_state=VerificationState.BLOCKING,
                    source_module="permission_policy",
                    blocking=True,
                    metadata={"capability_id": capability_id},
                )
            )
    return signals


def data_gate_signals(state: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    if not gate:
        return []
    signals: list[PheromoneSignal] = []
    if gate.get("blocking") or str(gate.get("status") or "").upper() == "FAIL":
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.STOP_SIGNAL,
                target="data_gate",
                content="Data Gate failed; downstream governed decisions and publication outputs are blocked.",
                strength=1.0,
                confidence=1.0,
                decay_rate=0.0,
                priority="hard",
                verification_state=VerificationState.BLOCKING,
                source_module="data_gate",
                blocking=True,
            )
        )
    for permission in blocked_conclusion_permissions(gate):
        target = str(permission.get("canonical_target") or permission.get("target") or "")
        if not target:
            continue
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.STOP_SIGNAL,
                target=target,
                content=data_gate_conclusion_block_message(permission),
                strength=1.0,
                confidence=1.0,
                decay_rate=0.0,
                priority="hard",
                verification_state=VerificationState.BLOCKING,
                source_module="data_gate",
                blocking=True,
                metadata={"conclusion_permission": permission},
            )
        )
    for issue in (gate.get("critical_errors") or []) + (gate.get("decision_blockers") or []):
        if isinstance(issue, dict):
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.RISK,
                    target=f"data_issue:{issue.get('code') or 'unknown'}",
                    content=str(issue.get("message") or issue.get("issue") or issue),
                    strength=0.9,
                    confidence=0.9,
                    source_module="data_gate",
                    verification_state=VerificationState.VERIFIED,
                    metadata={"issue": issue},
                )
            )
    for gap in gate.get("evidence_gaps") or []:
        if isinstance(gap, dict):
            signals.append(
                PheromoneSignal(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    type=SignalType.RISK,
                    target=f"evidence_gap:{gap.get('code') or 'unknown'}",
                    content=str(gap.get("message") or gap.get("issue") or gap),
                    strength=0.7,
                    confidence=0.75,
                    decay_rate=0.03,
                    source_module="data_gate",
                    metadata={"gap": gap},
                )
            )
    return signals


def data_gate_conclusion_block_message(permission: dict[str, Any]) -> str:
    target = str(permission.get("canonical_target") or permission.get("target") or "")
    label = str(permission.get("label") or target or "declared conclusion")
    if is_publication_target(target):
        if label.strip().lower() == " ".join(("report", "publication")):
            label = "publication"
        return f"Data Gate blocked {label}; a defect/readiness memo must be returned instead."
    return f"Data Gate blocked {label}; writer may only produce outputs whose conclusion permissions are allowed."


def review_signals(state: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    review = state.get("review") if isinstance(state.get("review"), dict) else {}
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    status = str(review.get("status") or "").upper()
    if status not in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
        return []
    return [
        PheromoneSignal(
            run_id=run_id,
            tenant_id=tenant_id,
            type=SignalType.STOP_SIGNAL,
            target=publication_conclusion_permission_target(gate),
            content=f"Critic blocked publication with status {status}.",
            strength=1.0,
            confidence=0.95,
            decay_rate=0.0,
            priority="hard",
            verification_state=VerificationState.BLOCKING,
            source_agent="critic",
            source_module="critic",
            blocking=True,
            metadata={"review": review},
        )
    ]


def agent_emitted_signals_from_outputs(
    state: dict[str, Any],
    outputs: dict[str, Any],
    specs_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate capability-agent signal proposals against swarm manifest policy.

    Capability agents may propose typed signals, but they cannot verify their
    own claims or silently create blocking system facts. System modules such as
    Data Gate, permission policy, critic, and final judge remain the only sources
    of verified/blocking enforcement.
    """

    accepted: list[PheromoneSignal] = []
    diagnostics: list[dict[str, Any]] = []
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    for agent_key, output in (outputs or {}).items():
        if not isinstance(output, dict):
            continue
        spec = specs_by_key.get(str(agent_key)) or {}
        result = agent_emitted_signals(
            output.get("emitted_signals"),
            agent_key=str(agent_key),
            spec=spec,
            run_id=run_id,
            tenant_id=tenant_id,
        )
        accepted.extend(result["accepted_signals"])
        diagnostics.extend(result["diagnostics"])
    return {"signals": accepted, "diagnostics": diagnostics}


def agent_emitted_signals(
    raw_signals: Any,
    *,
    agent_key: str,
    spec: dict[str, Any],
    run_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    swarm = spec.get("swarm") if isinstance(spec.get("swarm"), dict) else {}
    allowed_types = {str(item).strip().lower() for item in swarm.get("signal_emit_permissions") or []}
    can_block = bool(swarm.get("can_block"))
    if raw_signals in (None, ""):
        return {"accepted_signals": [], "diagnostics": []}
    if isinstance(raw_signals, dict):
        candidates = [raw_signals]
    elif isinstance(raw_signals, list):
        candidates = raw_signals
    else:
        return {
            "accepted_signals": [],
            "diagnostics": [
                rejected_agent_signal(agent_key, None, "emitted_signals must be a list of objects or an object")
            ],
        }

    accepted: list[PheromoneSignal] = []
    diagnostics: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            diagnostics.append(rejected_agent_signal(agent_key, index, "signal proposal must be an object"))
            continue
        parsed_type = parse_signal_type(candidate.get("type") or candidate.get("signal_type"))
        if parsed_type is None:
            diagnostics.append(rejected_agent_signal(agent_key, index, "unknown or missing signal type"))
            continue
        if parsed_type.value not in allowed_types:
            diagnostics.append(
                rejected_agent_signal(
                    agent_key,
                    index,
                    f"{parsed_type.value} is not allowed by this agent manifest",
                    signal_type=parsed_type.value,
                )
            )
            continue
        if parsed_type == SignalType.STOP_SIGNAL and not can_block:
            diagnostics.append(
                rejected_agent_signal(
                    agent_key,
                    index,
                    "agent is not allowed to propose stop_signals",
                    signal_type=parsed_type.value,
                )
            )
            continue
        target = str(candidate.get("target") or "").strip()
        content = str(candidate.get("content") or candidate.get("reason") or "").strip()
        if not target or not content:
            diagnostics.append(
                rejected_agent_signal(
                    agent_key,
                    index,
                    "signal proposal requires target and content",
                    signal_type=parsed_type.value,
                )
            )
            continue
        requested_verification = str(candidate.get("verification_state") or "").strip().lower()
        requested_blocking = parse_boolish(candidate.get("blocking")) or parse_boolish(candidate.get("hard_veto"))
        proposed_blocking = bool(requested_blocking or parsed_type == SignalType.STOP_SIGNAL)
        signal = PheromoneSignal(
            run_id=run_id,
            tenant_id=tenant_id,
            type=parsed_type,
            target=target,
            content=content,
            strength=candidate.get("strength", 0.65 if parsed_type == SignalType.STOP_SIGNAL else 0.5),
            confidence=candidate.get("confidence", 0.55),
            priority=normalize_priority(candidate.get("priority"), parsed_type=parsed_type),
            verification_state=agent_signal_verification_state(parsed_type),
            source_agent=agent_key,
            source_module=AGENT_PROPOSAL_MODULE,
            evidence_ref=empty_string_to_none(candidate.get("evidence_ref")),
            blocking=False,
            metadata={
                "agent_emitted": True,
                "agent_can_block": can_block,
                "proposed_blocking": proposed_blocking,
                "requested_verification_state": requested_verification or None,
                "verification_downgraded": requested_verification in {"verified", "blocking"} or requested_blocking,
                "committee_role": spec.get("committee_role"),
            },
        )
        accepted.append(signal)
        diagnostics.append(
            {
                "agent": agent_key,
                "index": index,
                "status": "accepted",
                "signal_id": signal.id,
                "type": parsed_type.value,
                "target": signal.target,
                "raw_target": target,
                "verification_state": signal.verification_state.value
                if hasattr(signal.verification_state, "value")
                else str(signal.verification_state),
                "blocking": False,
                "proposed_blocking": proposed_blocking,
                "reason": "accepted as an unverified/contested agent signal proposal",
            }
        )
    return {"accepted_signals": accepted, "diagnostics": diagnostics}


def parse_signal_type(value: Any) -> SignalType | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return SignalType(text)
    except ValueError:
        return None


def agent_signal_verification_state(signal_type: SignalType) -> VerificationState:
    if signal_type in {SignalType.STOP_SIGNAL, SignalType.RISK, SignalType.NEGATIVE}:
        return VerificationState.CONTESTED
    return VerificationState.UNVERIFIED


def normalize_priority(value: Any, *, parsed_type: SignalType) -> str:
    priority = str(value or "").strip().lower()
    if priority in {"low", "normal", "high", "hard"}:
        if priority == "hard":
            return "high"
        return priority
    if parsed_type == SignalType.STOP_SIGNAL:
        return "high"
    return "normal"


def parse_boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"true", "yes", "y", "1", "hard_veto"}


def empty_string_to_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def rejected_agent_signal(
    agent_key: str,
    index: int | None,
    reason: str,
    *,
    signal_type: str | None = None,
) -> dict[str, Any]:
    return {
        "agent": agent_key,
        "index": index,
        "status": "rejected",
        "type": signal_type,
        "target": None,
        "reason": reason,
    }


def swarm_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    signals = snapshot.get("signals") if isinstance(snapshot.get("signals"), list) else []
    stop_signals = snapshot.get("stop_signals") if isinstance(snapshot.get("stop_signals"), list) else []
    constraints = snapshot.get("constraint_signals") if isinstance(snapshot.get("constraint_signals"), list) else []
    return {
        "signal_count": len(signals),
        "stop_signal_count": len(stop_signals),
        "blocking_signal_count": len([signal for signal in signals if signal.get("blocking")]),
        "constraint_count": len(constraints),
        "blocking_targets": [canonical_target(target) for target in snapshot.get("blocking_targets", [])],
        "constraint_violations": 0,
    }
