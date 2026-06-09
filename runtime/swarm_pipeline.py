from __future__ import annotations

from typing import Any, Iterable

from runtime.swarm.artifact_cues import build_artifact_cue_report, artifact_cue_signals
from runtime.swarm.evidence_graph import build_evidence_graph
from runtime.swarm.execution_loop import public_execution_loop_report, run_swarm_execution_loop
from runtime.swarm.signal_extractor import review_signals, update_state_with_signals
from runtime.swarm.types import PheromoneSignal


def apply_signals_to_state(
    state: dict[str, Any],
    signals: Iterable[PheromoneSignal | dict[str, Any]],
) -> dict[str, Any]:
    return update_state_with_signals(state, signals)


def attach_review_governance(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    next_result = dict(result)
    next_result.update(update_state_with_signals({**state, **next_result}, review_signals({**state, **next_result})))
    next_result["evidence_graph"] = build_evidence_graph({**state, **next_result})
    return attach_artifact_cue_governance(state, next_result)


def attach_swarm_execution_loop(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    next_result = dict(result)
    loop = run_swarm_execution_loop({**state, **next_result})
    report = public_execution_loop_report(loop)
    next_result["swarm_execution_loop"] = report
    signals = loop.get("signals") or []
    if signals:
        next_result.update(update_state_with_signals({**state, **next_result}, signals))
    protocol_trace = list(next_result.get("swarm_protocol_trace") or [])
    protocol_trace.extend(loop.get("events") or [])
    next_result["swarm_protocol_trace"] = protocol_trace
    return next_result


def attach_artifact_cue_governance(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    next_result = dict(result)
    artifact_report = build_artifact_cue_report({**state, **next_result})
    next_result["artifact_cue_report"] = artifact_report
    cue_signals = artifact_cue_signals({**state, **next_result}, artifact_report)
    if cue_signals:
        next_result.update(update_state_with_signals({**state, **next_result}, cue_signals))
    return next_result
