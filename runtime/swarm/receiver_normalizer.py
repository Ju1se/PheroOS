from __future__ import annotations

from typing import Any

from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_receiver_normalizer_report(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize agent prose/JSON into claim, evidence, risk, and gap objects.

    This is the receiver caste: analysts can produce diverse artifacts, but the
    rest of PheroOS should consume stable governance objects.
    """

    outputs = runtime_agent_outputs(state)
    claims: list[dict[str, Any]] = []
    evidence_refs: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    candidate_signals: list[dict[str, Any]] = []

    for agent, output in sorted(outputs.items()):
        if not isinstance(output, dict):
            continue
        agent_key = str(agent)
        claim_text = first_text(output, "thesis", "long_term_quality_judgment", "core_thesis", "bear_case", "summary")
        if claim_text:
            claims.append(
                {
                    "id": f"claim:{agent_key}:thesis",
                    "agent": agent_key,
                    "kind": "thesis",
                    "content": claim_text,
                    "evidence_refs": normalize_string_items(output.get("evidence_used")),
                    "score": output.get("score"),
                    "confidence": output.get("confidence"),
                }
            )
        for index, ref in enumerate(normalize_string_items(output.get("evidence_used"))):
            evidence_refs.append(
                {
                    "id": f"evidence_ref:{agent_key}:{index}",
                    "agent": agent_key,
                    "ref": ref,
                    "claim_id": f"claim:{agent_key}:thesis",
                }
            )
        for index, item in enumerate(normalize_string_items(output.get("risks") or output.get("risk_items"))):
            risks.append(
                {
                    "id": f"risk:{agent_key}:{index}",
                    "agent": agent_key,
                    "content": item,
                    "severity": "high" if output.get("hard_veto") else "medium",
                }
            )
        for index, item in enumerate(normalize_string_items(output.get("missing_data") or output.get("open_questions"))):
            gaps.append(
                {
                    "id": f"gap:{agent_key}:{index}",
                    "agent": agent_key,
                    "content": item,
                }
            )
        candidate_signals.append(
            {
                "agent": agent_key,
                "score": output.get("score"),
                "confidence": output.get("confidence"),
                "hard_veto": bool(output.get("hard_veto")),
                "status": output.get("status") or "unknown",
            }
        )

    unsupported = [
        claim
        for claim in claims
        if not claim.get("evidence_refs")
    ]
    status = "backlog_detected" if unsupported or gaps else "normalized"
    return {
        "schema_version": "pheroos.receiver_normalizer.v1",
        "status": status,
        "claim_count": len(claims),
        "evidence_ref_count": len(evidence_refs),
        "risk_count": len(risks),
        "gap_count": len(gaps),
        "claims": claims,
        "evidence_refs": evidence_refs,
        "risks": risks,
        "missing_data": gaps,
        "candidate_signals": candidate_signals,
        "unsupported_claims": unsupported,
        "handoff_contract": {
            "writer_must_use_normalized_claims": True,
            "raw_agent_outputs_are_not_final_ready": True,
        },
    }


def receiver_normalizer_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals: list[PheromoneSignal] = []
    if report.get("claim_count"):
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.PROGRESS,
                target="handoff:agent_claims",
                content=f"Receiver normalized {report.get('claim_count')} agent claims.",
                strength=0.62,
                confidence=0.8,
                verification_state=VerificationState.VERIFIED,
                source_module="receiver_normalizer",
                metadata={"claim_count": report.get("claim_count"), "risk_count": report.get("risk_count")},
            )
        )
    for claim in report.get("unsupported_claims") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.BOTTLENECK,
                target="handoff:evidence_verification",
                content=f"Claim from {claim.get('agent')} lacks evidence references.",
                strength=0.68,
                confidence=0.72,
                verification_state=VerificationState.VERIFIED,
                source_module="receiver_normalizer",
                evidence_ref=str(claim.get("id") or ""),
                metadata={"claim_id": claim.get("id"), "agent": claim.get("agent")},
            )
        )
    return signals


def first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_string_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list | tuple | set):
        output: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("source") or item.get("ref") or item.get("content") or "").strip()
            else:
                text = str(item).strip()
            if text:
                output.append(text)
        return output
    return []
