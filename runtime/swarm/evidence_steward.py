from __future__ import annotations

import re
from typing import Any

from runtime.swarm.conclusion_claims import blocked_conclusion_match_for_text
from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    data_gate_conclusion_permission,
    effective_conclusion_permissions,
)
from runtime.swarm.legacy_data_gate_permissions import (
    legacy_formal_valuation_allowed_field,
    legacy_formal_valuation_conclusion_target,
)
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_evidence_steward_report(
    state: dict[str, Any],
    receiver_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Link normalized claims to deterministic evidence and flag weak claims."""

    receiver = receiver_report if isinstance(receiver_report, dict) else state.get("receiver_normalizer_report")
    receiver = receiver if isinstance(receiver, dict) else {}
    claims = receiver.get("claims") if isinstance(receiver.get("claims"), list) else []
    metric_registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    metric_terms = metric_tokens(metric_registry)
    blocked_output_permissions = [
        str(permission.get("canonical_target") or permission.get("target"))
        for permission in blocked_conclusion_permissions(data_gate)
        if permission.get("canonical_target") or permission.get("target")
    ]
    conclusion_permissions = conclusion_permission_constraints(data_gate)
    allowed_output_permissions = [
        item["target"] for item in conclusion_permissions if item.get("allowed") is True and item.get("target")
    ]

    linked: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        content = str(claim.get("content") or "")
        refs = [str(item) for item in claim.get("evidence_refs") or [] if str(item)]
        metric_matches = [token for token in metric_terms if token and token in content.lower()]
        record = {
            "claim_id": claim.get("id"),
            "agent": claim.get("agent"),
            "content": content,
            "evidence_refs": refs,
            "metric_matches": metric_matches,
            "support_status": "linked" if refs or metric_matches else "unsupported",
        }
        blocked_match = blocked_conclusion_match_for_text(content, state, data_gate)
        if blocked_match:
            record["support_status"] = "blocked_by_data_gate"
            record["blocked_target"] = blocked_match["target"]
            record["blocked_target_source"] = blocked_match["source"]
            record["writer_action"] = blocked_match.get("writer_action")
            blocked.append(record)
        elif refs or metric_matches:
            linked.append(record)
        else:
            unsupported.append(record)

    status = "blocked_claims" if blocked else "unsupported_claims" if unsupported else "linked"
    writer_constraints = {
        "drop_unsupported_claims": True,
        "do_not_convert_data_defects_into_output_claims": True,
        "blocked_output_permissions": blocked_output_permissions,
        "allowed_output_permissions": allowed_output_permissions,
        "conclusion_permissions": conclusion_permissions,
    }
    formal_valuation_allowed = data_gate_conclusion_permission(data_gate, legacy_formal_valuation_conclusion_target())
    if formal_valuation_allowed is not None:
        legacy_field = legacy_formal_valuation_allowed_field()
        writer_constraints[legacy_field] = formal_valuation_allowed
        writer_constraints["legacy_conclusion_permission_fields"] = [legacy_field]

    return {
        "schema_version": "pheroos.evidence_steward.v1",
        "status": status,
        "linked_claims": linked,
        "unsupported_claims": unsupported,
        "blocked_claims": blocked,
        "linked_claim_count": len(linked),
        "unsupported_claim_count": len(unsupported),
        "blocked_claim_count": len(blocked),
        "metric_evidence_available": bool(metric_terms),
        "writer_constraints": writer_constraints,
    }


def conclusion_permission_constraints(data_gate: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = []
    for permission in effective_conclusion_permissions(data_gate):
        target = str(permission.get("canonical_target") or permission.get("target") or "").strip()
        if not target:
            continue
        constraints.append(
            {
                "target": target,
                "allowed": bool(permission.get("allowed")),
                "label": str(permission.get("label") or target),
            }
        )
    return constraints


def evidence_steward_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    if report.get("linked_claim_count"):
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.EVIDENCE,
                target="evidence_graph:claim_links",
                content=f"Evidence Steward linked {report.get('linked_claim_count')} agent claims.",
                strength=0.7,
                confidence=0.78,
                verification_state=VerificationState.VERIFIED,
                source_module="evidence_steward",
                metadata={"linked_claim_count": report.get("linked_claim_count")},
            )
        )
    for claim in report.get("unsupported_claims") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.ARTIFACT_CUE,
                target="artifact:agent_claim",
                content=f"Unsupported claim from {claim.get('agent')} must not enter final report.",
                strength=0.66,
                confidence=0.74,
                verification_state=VerificationState.VERIFIED,
                source_module="evidence_steward",
                evidence_ref=str(claim.get("claim_id") or ""),
                metadata={"claim_id": claim.get("claim_id"), "agent": claim.get("agent")},
            )
        )
    for claim in report.get("blocked_claims") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.ARTIFACT_CUE,
                target=str(claim.get("blocked_target") or "decision:blocked_output"),
                content=f"Claim from {claim.get('agent')} conflicts with Data Gate output permissions.",
                strength=0.82,
                confidence=0.82,
                verification_state=VerificationState.VERIFIED,
                source_module="evidence_steward",
                evidence_ref=str(claim.get("claim_id") or ""),
                metadata={
                    "claim_id": claim.get("claim_id"),
                    "agent": claim.get("agent"),
                    "blocked_target_source": claim.get("blocked_target_source"),
                    "writer_action": claim.get("writer_action"),
                },
            )
        )
    return signals


def metric_tokens(registry: dict[str, Any]) -> set[str]:
    metrics = registry.get("metrics") if isinstance(registry.get("metrics"), list) else []
    tokens: set[str] = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        for key in ("name", "metric"):
            value = str(metric.get(key) or "").strip().lower()
            if value:
                tokens.add(value)
                tokens.update(part for part in re.split(r"[\s_:/.-]+", value) if len(part) >= 3)
    return tokens
