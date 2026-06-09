from __future__ import annotations

from typing import Any

from runtime.swarm.candidate_registry import (
    fallbackish_candidate_text,
    legacy_fallbackish_candidate_allowed,
    normalized_candidate_label,
)
from runtime.swarm.legacy_quorum_targets import (
    legacy_blocked_conclusion_targets_from_quorum_flags,
    legacy_quorum_flags_from_report,
)
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_quorum_marshal_report(state: dict[str, Any], quorum_trace: dict[str, Any] | None = None) -> dict[str, Any]:
    quorum = quorum_trace if isinstance(quorum_trace, dict) else state.get("quorum_trace")
    quorum = quorum if isinstance(quorum, dict) else {}
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    candidates = quorum.get("candidates") if isinstance(quorum.get("candidates"), list) else []
    blocked = [item for item in candidates if isinstance(item, dict) and item.get("blocked")]
    stop_count = int(quorum.get("blocking_stop_signal_count") or 0)
    legacy_block_flags = legacy_quorum_flags_from_report(quorum)
    blocked_conclusion_targets = blocked_conclusion_targets_for_quorum(quorum)
    evidence_graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else {}
    summary = evidence_graph.get("summary") if isinstance(evidence_graph.get("summary"), dict) else {}
    committed_label = str(committed.get("label") or "Pending")
    fallback_candidate = fallback_candidate_for_quorum(quorum, candidates, committed)
    committed_is_fallback = bool(fallback_candidate and candidate_matches(committed, fallback_candidate))
    status = "blocked_to_fallback" if committed_is_fallback and blocked_conclusion_targets else "committed"
    return {
        "schema_version": "pheroos.quorum_marshal.v1",
        "status": status,
        "committed_candidate": committed,
        "blocked_candidates": blocked,
        "blocking_stop_signal_count": stop_count,
        "blocked_conclusion_targets": blocked_conclusion_targets,
        **legacy_block_flags,
        "quorum_margin": quorum.get("quorum_margin"),
        "evidence_coverage": {
            "fact_count": summary.get("fact_count"),
            "proposal_count": summary.get("proposal_count"),
            "blocker_count": summary.get("blocker_count"),
        },
        "fallback_candidate": fallback_candidate,
        "why_committed": why_committed(
            committed_label,
            blocked_conclusion_targets,
            stop_count,
            committed_is_fallback=committed_is_fallback,
        ),
        "authority": {
            "commit_logic": "deterministic_quorum_with_stop_signal_override",
            "cio_can_propose_but_not_commit": True,
        },
    }


def quorum_marshal_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    committed = report.get("committed_candidate") if isinstance(report.get("committed_candidate"), dict) else {}
    return [
        PheromoneSignal(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=str((state.get("metadata") or {}).get("tenant_id") or "default"),
            type=SignalType.QUORUM,
            target="quorum:committed_candidate",
            content=f"Quorum Marshal committed {committed.get('label') or 'Pending'}: {report.get('why_committed')}",
            strength=0.86,
            confidence=0.86,
            verification_state=VerificationState.VERIFIED,
            source_module="quorum_marshal",
            metadata={"status": report.get("status"), "quorum_margin": report.get("quorum_margin")},
        )
    ]


def fallback_candidate_for_quorum(
    quorum: dict[str, Any],
    candidates: list[Any],
    committed: dict[str, Any],
) -> dict[str, Any] | None:
    declared = quorum.get("fallback_candidate") if isinstance(quorum.get("fallback_candidate"), dict) else {}
    if declared:
        return candidate_by_reference(declared, candidates) or dict(declared)
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("safe_fallback"):
            return dict(candidate)
    if legacy_fallbackish_candidate_allowed(quorum):
        for candidate in candidates:
            if isinstance(candidate, dict) and fallbackish_candidate_text(f"{candidate.get('id')} {candidate.get('label')}"):
                return dict(candidate)
        if committed and fallbackish_candidate_text(f"{committed.get('id')} {committed.get('label')}"):
            return dict(committed)
    return None


def candidate_by_reference(reference: dict[str, Any], candidates: list[Any]) -> dict[str, Any] | None:
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate_matches(candidate, reference):
            return dict(candidate)
    return None


def candidate_matches(candidate: dict[str, Any], reference: dict[str, Any] | None) -> bool:
    if not reference:
        return False
    return bool(candidate_keys(candidate).intersection(candidate_keys(reference)))


def candidate_keys(value: dict[str, Any]) -> set[str]:
    return {
        key
        for key in (
            normalized_candidate_label(value.get("candidate")),
            normalized_candidate_label(value.get("id")),
            normalized_candidate_label(value.get("label")),
        )
        if key
    }


def blocked_conclusion_targets_for_quorum(quorum: dict[str, Any]) -> list[str]:
    targets = [
        canonical_target(target)
        for target in quorum.get("blocked_conclusion_targets") or []
        if str(target or "").strip()
    ]
    if targets:
        return sorted(set(targets))
    return legacy_blocked_conclusion_targets_from_quorum_flags(quorum)


def why_committed(
    label: str,
    blocked_conclusion_targets: list[str],
    stop_count: int,
    *,
    committed_is_fallback: bool,
) -> str:
    if committed_is_fallback and blocked_conclusion_targets:
        targets = ", ".join(blocked_conclusion_targets)
        return f"Stop-signal override forced {label} ({stop_count} active blockers: {targets})."
    if not label or label == "Pending":
        return "No candidate reached a committed quorum yet."
    return f"{label} retained the strongest quorum support after governance adjustments."
