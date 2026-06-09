from __future__ import annotations

from typing import Any

from runtime.swarm.conclusion_claims import blocked_conclusion_match_for_text
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState


def build_artifact_cue_report(state: dict[str, Any]) -> dict[str, Any]:
    cues: list[dict[str, Any]] = []
    data_gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    metric_registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    review = state.get("review") if isinstance(state.get("review"), dict) else {}
    evidence_graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else {}
    final = str(state.get("final") or state.get("draft_final") or "")
    blocked_match = blocked_conclusion_match_for_text(final, state, data_gate)
    if blocked_match:
        cues.append(
            cue(
                "final",
                "unsupported_recommendation",
                "Final answer contains language for a Data Gate-blocked conclusion.",
                "high",
                target=blocked_match["target"],
                blocked_target_source=blocked_match["source"],
                writer_action=blocked_match["writer_action"],
            )
        )
    if data_gate.get("required_caveats") and not contains_any(final, data_gate.get("required_caveats")):
        cues.append(cue("final", "missing_caveat", "Final answer may be missing a required Data Gate caveat.", "medium"))
    if data_gate.get("evidence_gaps"):
        cues.append(cue("data_gate", "unresolved_evidence_gap", "Data Gate still reports unresolved evidence gaps.", "medium"))
    metrics = metric_registry.get("metrics") if isinstance(metric_registry.get("metrics"), list) else []
    if data_gate and not metrics:
        cues.append(cue("metric_registry", "missing_metric_registry", "Data Gate exists but metric registry has no report-ready metrics.", "high"))
    for issue in review.get("overclaims") or []:
        cues.append(cue("review", "critic_overclaim", str(issue), "medium"))
    summary = evidence_graph.get("summary") if isinstance(evidence_graph.get("summary"), dict) else {}
    if summary.get("proposal_count", 0) and not summary.get("fact_count", 0):
        cues.append(cue("evidence_graph", "proposal_without_fact", "Evidence Graph has proposals but no verified facts.", "medium"))
    return {"status": "cues_detected" if cues else "clear", "cues": cues, "cue_count": len(cues)}


def artifact_cue_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    run_id = str(state.get("run_id") or "unknown")
    tenant_id = str((state.get("metadata") or {}).get("tenant_id") or "default")
    signals = []
    for item in report.get("cues") or []:
        signals.append(
            PheromoneSignal(
                run_id=run_id,
                tenant_id=tenant_id,
                type=SignalType.ARTIFACT_CUE,
                target=f"artifact:{item.get('artifact')}",
                content=str(item.get("message") or "Artifact cue detected."),
                strength=0.85 if item.get("severity") == "high" else 0.6,
                confidence=0.78,
                verification_state=VerificationState.VERIFIED,
                source_module="artifact_cues",
                evidence_ref=str(item.get("artifact") or "artifact"),
                metadata=item,
            )
        )
    return signals


def cue(artifact: str, code: str, message: str, severity: str, **extra: Any) -> dict[str, Any]:
    item = {"artifact": artifact, "code": code, "message": message, "severity": severity}
    item.update(extra)
    return item


def contains_any(text: str, values: Any) -> bool:
    if not text:
        return False
    for value in values if isinstance(values, list) else [values]:
        if value and str(value)[:80] in text:
            return True
    return False
