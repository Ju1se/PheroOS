from __future__ import annotations

import json
import re
from typing import Any

from runtime.swarm.agent_outputs import runtime_agent_output_artifacts
from runtime.swarm.data_gate_permissions import blocked_conclusion_permissions
from runtime.swarm.legacy_social_immunity_policy import (
    legacy_social_immunity_arousal_signal_template,
    legacy_social_immunity_policy_source,
    legacy_social_immunity_recommendation,
    render_social_immunity_arousal_signal_template,
)
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


SWARM_LOOP_SOCIAL_IMMUNITY_POLICY_SOURCE = "capability_swarm_loop_policy"

INJECTION_PATTERNS = (
    re.compile(r"ignore (all )?(previous|prior) instructions", re.I),
    re.compile(r"reveal (the )?(system|developer) prompt", re.I),
    re.compile(r"exfiltrate|leak.*(token|secret|api key|password)", re.I),
    re.compile(r"disable (guardrails|safety|policy)", re.I),
    re.compile(r"\b(api[_ -]?key|authorization|bearer token|password)\s*[:=]\s*['\"]?[\w.\-]{12,}", re.I),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{16,}|xox[baprs]-[A-Za-z0-9\-]{16,})\b", re.I),
)


def build_social_immunity_report(state: dict[str, Any]) -> dict[str, Any]:
    artifacts = scan_artifacts(state)
    contaminants = [item for item in artifacts if item.get("contaminated")]
    arousal = arousal_level(state, contaminants)
    status = "quarantine_required" if contaminants else "heightened" if arousal >= 0.6 else "clear"
    recommendation, recommendation_source = recommendation_for(status, state=state)
    return {
        "status": status,
        "contaminants": contaminants,
        "quarantine_count": len(contaminants),
        "arousal_level": round(arousal, 3),
        "recommendation": recommendation,
        "recommendation_source": recommendation_source,
    }


def social_immunity_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    for item in report.get("contaminants") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.CONTAMINATION,
                target=f"artifact:{item.get('artifact_id')}",
                content=str(item.get("reason") or "Potential prompt-injection contamination detected."),
                strength=0.95,
                confidence=0.85,
                priority="hard",
                blocking=True,
                verification_state=VerificationState.BLOCKING,
                source_module="social_immunity",
                evidence_ref=str(item.get("source") or "artifact_scan"),
                metadata={"matched_pattern": item.get("pattern")},
            )
        )
    if report.get("arousal_level", 0) >= 0.6:
        content, content_source = social_immunity_arousal_signal_content(report, state=state)
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.AROUSAL,
                target="system:verification_intensity",
                content=content,
                strength=float(report.get("arousal_level") or 0.6),
                confidence=0.8,
                verification_state=VerificationState.VERIFIED,
                source_module="social_immunity",
                evidence_ref="data_gate/review/contamination_scan",
                metadata={
                    "recommendation": report.get("recommendation"),
                    "recommendation_source": report.get("recommendation_source"),
                    "signal_template_source": content_source,
                },
            )
        )
    return signals


def scan_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for index, entry in enumerate(state.get("execution_log") if isinstance(state.get("execution_log"), list) else []):
        artifacts.extend(scan_value(f"execution_log:{index}", entry, source="execution_log"))
    for name in ("research_brief", "wrds_result"):
        value = state.get(name)
        if value:
            artifacts.extend(scan_value(name, value, source=name))
    for artifact in runtime_agent_output_artifacts(state):
        artifacts.extend(
            scan_value(
                str(artifact.get("artifact_id") or "agent_outputs"),
                artifact.get("value"),
                source=str(artifact.get("source") or "agent_outputs"),
            )
        )
    return artifacts


def scan_value(artifact_id: str, value: Any, *, source: str) -> list[dict[str, Any]]:
    text = json.dumps(value, ensure_ascii=False, default=str)[:12000]
    findings = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(
                {
                    "artifact_id": artifact_id,
                    "source": source,
                    "contaminated": True,
                    "pattern": pattern.pattern,
                    "reason": "Possible prompt-injection or secret-exfiltration instruction detected.",
                }
            )
    return findings


def arousal_level(state: dict[str, Any], contaminants: list[dict[str, Any]]) -> float:
    score = 0.0
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    review = state.get("review") if isinstance(state.get("review"), dict) else {}
    if contaminants:
        score += 0.75
    if blocked_conclusion_permissions(data_gate):
        score += 0.25
    if state.get("stop_signals"):
        score += 0.2
    if str(review.get("status") or "").upper() in {"REJECT_CONDITIONAL", "REJECT_FATAL"}:
        score += 0.35
    return min(1.0, score)


def recommendation_for(status: str, *, state: dict[str, Any]) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state)
    recommendations = (
        policy.get("social_immunity_recommendations")
        if isinstance(policy.get("social_immunity_recommendations"), dict)
        else {}
    )
    declared = str(recommendations.get(status) or "").strip()
    if declared:
        return declared, SWARM_LOOP_SOCIAL_IMMUNITY_POLICY_SOURCE
    return legacy_social_immunity_recommendation(status), legacy_social_immunity_policy_source()


def social_immunity_arousal_signal_content(report: dict[str, Any], *, state: dict[str, Any]) -> tuple[str, str]:
    policy = swarm_loop_policy_from_state(state)
    declared = str(policy.get("social_immunity_arousal_signal_template") or "").strip()
    if declared:
        return (
            render_social_immunity_arousal_signal_template(declared, report),
            SWARM_LOOP_SOCIAL_IMMUNITY_POLICY_SOURCE,
        )
    return (
        render_social_immunity_arousal_signal_template(
            legacy_social_immunity_arousal_signal_template(),
            report,
        ),
        legacy_social_immunity_policy_source(),
    )


def swarm_loop_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    return policy


def sanitize_artifact_text(text: str) -> str:
    sanitized = str(text or "")
    for pattern in INJECTION_PATTERNS:
        sanitized = pattern.sub("[quarantined-instruction]", sanitized)
    return sanitized
