from __future__ import annotations

from typing import Any

from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    data_gate_conclusion_permission,
    effective_conclusion_permissions,
)
from runtime.swarm.legacy_arousal_policy import (
    legacy_arousal_signal_template,
    legacy_arousal_signal_template_source,
    render_arousal_signal_template,
)
from runtime.swarm.legacy_data_gate_permissions import legacy_formal_valuation_conclusion_target
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.target_registry import canonical_target, target_kind
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


SWARM_LOOP_AROUSAL_SIGNAL_TEMPLATE_SOURCE = "capability_swarm_loop_policy"


def build_arousal_report(state: dict[str, Any]) -> dict[str, Any]:
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    quorum = state.get("quorum_trace") if isinstance(state.get("quorum_trace"), dict) else {}
    raw_stop_signals = state.get("stop_signals") if isinstance(state.get("stop_signals"), list) else []
    stop_signals = [signal for signal in raw_stop_signals if isinstance(signal, dict) and is_active_blocker(signal)]
    permissions = permission_pressure(state)
    blocked_conclusions = blocked_conclusion_permissions(data_gate)
    evidence_coverage = evidence_coverage_score(state)
    conclusion_recommendations = conclusion_permission_recommendations(data_gate, stop_signals)
    triggers: list[str] = []
    score = 0.0
    if blocked_conclusions:
        score += min(0.5, 0.25 * len(blocked_conclusions))
        triggers.extend(f"{item['label']} constrained by Data Gate" for item in blocked_conclusions)
    if stop_signals:
        score += min(0.3, 0.18 + (0.04 * len(stop_signals)))
        triggers.append("active stop-signals")
    if evidence_coverage < 0.5:
        score += 0.2
        triggers.append("low evidence coverage")
    if conflicting_quorum(quorum):
        score += 0.18
        triggers.append("conflicting quorum candidates")
    if permissions:
        score += 0.22
        triggers.append("high-risk permission boundary")
    level = min(1.0, score)
    return {
        "status": "elevated" if level >= 0.66 else "watch" if level >= 0.35 else "normal",
        "arousal_level": round(level, 3),
        "triggers": triggers,
        "evidence_coverage": round(evidence_coverage, 3),
        "high_risk_permissions": permissions,
        "blocked_conclusion_targets": [item["canonical_target"] for item in blocked_conclusions],
        "recommendations": {
            "verifier_strictness": "high" if level >= 0.66 else "medium" if level >= 0.35 else "normal",
            "writer_temperature_cap": 0.0 if level >= 0.35 else 0.2,
            "quorum_threshold_delta": round(0.15 if level >= 0.66 else 0.08 if level >= 0.35 else 0.0, 3),
            **conclusion_recommendations,
            "allow_formal_conclusion": data_gate_conclusion_permission(
                data_gate,
                legacy_formal_valuation_conclusion_target(),
            )
            is not False
            and not stop_signals,
        },
    }


def conclusion_permission_recommendations(
    data_gate: dict[str, Any],
    stop_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    blocked_targets = {
        str(item.get("canonical_target") or item.get("target"))
        for item in blocked_conclusion_permissions(data_gate)
        if item.get("canonical_target") or item.get("target")
    }
    stop_blocked_targets = {
        canonical_target(signal.get("target"))
        for signal in stop_signals
        if target_kind(canonical_target(signal.get("target"))) == "decision"
    }
    blocked_targets.update(stop_blocked_targets)
    allowed_targets = [
        str(item.get("canonical_target") or item.get("target"))
        for item in effective_conclusion_permissions(data_gate)
        if item.get("allowed") is True
        and str(item.get("canonical_target") or item.get("target"))
        and str(item.get("canonical_target") or item.get("target")) not in stop_blocked_targets
    ]
    allowed_targets = list(dict.fromkeys(allowed_targets))
    blocked_targets_list = sorted(target for target in blocked_targets if target)
    return {
        "allowed_conclusion_targets": allowed_targets,
        "blocked_conclusion_targets": blocked_targets_list,
        "allow_conclusion_targets": allowed_targets,
    }


def arousal_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if report.get("arousal_level", 0) < 0.35:
        return []
    content, content_source = arousal_signal_content(report, state=state)
    return [
        PheromoneSignal(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=str((state.get("metadata") or {}).get("tenant_id") or "default"),
            type=SignalType.AROUSAL,
            target="system:verification_intensity",
            content=content,
            strength=float(report.get("arousal_level") or 0.0),
            confidence=0.82,
            verification_state=VerificationState.VERIFIED,
            source_module="arousal_controller",
            evidence_ref="data_gate/stop_signals/quorum/permissions",
            metadata={
                "triggers": report.get("triggers", []),
                "recommendations": report.get("recommendations", {}),
                "signal_template_source": content_source,
            },
        )
    ]


def arousal_signal_content(report: dict[str, Any], *, state: dict[str, Any]) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state)
    declared = str(policy.get("arousal_signal_template") or "").strip()
    if declared:
        return (
            render_arousal_signal_template(declared, report),
            SWARM_LOOP_AROUSAL_SIGNAL_TEMPLATE_SOURCE,
        )
    return (
        render_arousal_signal_template(legacy_arousal_signal_template(), report),
        legacy_arousal_signal_template_source(),
    )


def swarm_loop_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    return policy


def permission_pressure(state: dict[str, Any]) -> list[str]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    decisions = metadata.get("permission_decisions") or metadata.get("permission_grants") or []
    high_risk = []
    for item in decisions if isinstance(decisions, list) else []:
        payload = item if isinstance(item, dict) else {}
        permission = str(payload.get("permission") or payload.get("name") or payload.get("permission_name") or "")
        status = str(payload.get("status") or payload.get("decision") or "")
        if permission in {"trade:execute", "database:write", "filesystem:write", "shell:execute"} or status in {
            "pending_confirmation",
            "denied",
        }:
            high_risk.append(permission or status)
    return high_risk


def evidence_coverage_score(state: dict[str, Any]) -> float:
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    if isinstance(data_gate.get("evidence_coverage"), (int, float)):
        return max(0.0, min(1.0, float(data_gate["evidence_coverage"])))
    registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    metrics = registry.get("metrics") if isinstance(registry.get("metrics"), list) else []
    gaps = data_gate.get("evidence_gaps") if isinstance(data_gate.get("evidence_gaps"), list) else []
    return max(0.0, min(1.0, len(metrics) / max(len(metrics) + len(gaps), 1)))


def conflicting_quorum(quorum: dict[str, Any]) -> bool:
    candidates = quorum.get("candidates") if isinstance(quorum.get("candidates"), list) else []
    if len(candidates) < 2:
        return False
    scores = sorted((float(item.get("support_score") or 0.0) for item in candidates if isinstance(item, dict)), reverse=True)
    return len(scores) >= 2 and (scores[0] - scores[1]) < 0.12
