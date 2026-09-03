"""Hybrid pheromone trace conformance facade.

The named functions in this module are stable static trust-path probes.  Their
stage implementations live in focused private modules so the facade remains a
small, reviewable boundary while diagnostics and deterministic replay behavior
stay unchanged.
"""

from __future__ import annotations

from typing import Any

from pheroos.conformance.checks._manifest import candidate_set as candidate_set
from pheroos.conformance.report import CheckResult
from pheroos.governance._swarm.records import HybridReplayState
from pheroos.governance.pheromone import PheromoneTrail
from pheroos.governance.quorum import QuorumDecision
from pheroos.protocol.models import CapabilityManifest
from pheroos.trace import TraceEvent

from ._hybrid_trace_authority import (
    collective_authority_problems as _collective_authority_problems,
    replay_trace_problems as _replay_trace_problems,
)
from ._hybrid_trace_coordination import (
    coordination_replay_problems as _coordination_replay_problems,
    layer_pheromone_lineage_problems as _layer_pheromone_lineage_problems,
    policy_adjustment_trace_problems as _policy_adjustment_trace_problems,
)
from ._hybrid_trace_entry import (
    actual_trace_coverage_problems as actual_trace_coverage_problems,
    check as _check,
    check_actual_trace as _check_actual_trace,
)
from ._hybrid_trace_lifecycle import (
    pheromone_lifecycle_policy_problems as _pheromone_lifecycle_policy_problems,
)
from ._hybrid_trace_replay import (
    manifest_replay as _manifest_replay,
)
from ._hybrid_trace_score import (
    pheromone_derived_trace_problems as _pheromone_derived_trace_problems,
    pheromone_score_reconstruction_problems as _pheromone_score_reconstruction_problems,
)
from ._hybrid_trace_shared import event_stage as _event_stage


def check(manifest: CapabilityManifest) -> CheckResult:
    return _check(manifest)


def check_actual_trace(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...] | list[TraceEvent],
    *,
    decision: QuorumDecision | None = None,
    replay_state: HybridReplayState | None = None,
    enforce_declared_coverage: bool = False,
) -> CheckResult:
    return _check_actual_trace(
        manifest,
        events,
        decision=decision,
        replay_state=replay_state,
        enforce_declared_coverage=enforce_declared_coverage,
    )


def collective_authority_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    *,
    replay_state: HybridReplayState | None = None,
) -> list[str]:
    return _collective_authority_problems(
        manifest,
        events,
        replay_state=replay_state,
    )


def replay_trace_problems(
    events: tuple[TraceEvent, ...],
    score_event: TraceEvent,
    *,
    replay_state: HybridReplayState | None,
    protocol_id: str,
    target: str,
) -> list[str]:
    return _replay_trace_problems(
        events,
        score_event,
        replay_state=replay_state,
        protocol_id=protocol_id,
        target=target,
    )


def pheromone_lifecycle_policy_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
) -> list[str]:
    return _pheromone_lifecycle_policy_problems(manifest, events)


def pheromone_score_reconstruction_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    pheromone_score_event: TraceEvent,
    candidate_score_event: TraceEvent,
) -> list[str]:
    return _pheromone_score_reconstruction_problems(
        manifest,
        events,
        pheromone_score_event,
        candidate_score_event,
    )


def pheromone_derived_trace_problems(
    *,
    events: tuple[TraceEvent, ...],
    pheromone_score_event: TraceEvent,
    reconstructed: Any,
    runtime_policy: Any,
    candidates: Any,
    trails: list[PheromoneTrail],
    current_step: int,
) -> list[str]:
    return _pheromone_derived_trace_problems(
        events=events,
        pheromone_score_event=pheromone_score_event,
        reconstructed=reconstructed,
        runtime_policy=runtime_policy,
        candidates=candidates,
        trails=trails,
        current_step=current_step,
    )


def policy_adjustment_trace_problems(
    policy: Any,
    events: tuple[TraceEvent, ...],
) -> list[str]:
    return _policy_adjustment_trace_problems(policy, events)


def coordination_replay_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    proposal_events: list[TraceEvent],
    assessment_event: TraceEvent,
    resolution_event: TraceEvent,
    breakdown: dict[str, Any],
    active_ids: set[str],
) -> list[str]:
    return _coordination_replay_problems(
        manifest,
        events,
        proposal_events,
        assessment_event,
        resolution_event,
        breakdown,
        active_ids,
    )


def layer_pheromone_lineage_problems(
    events: tuple[TraceEvent, ...],
    proposal_events: list[TraceEvent],
) -> list[str]:
    return _layer_pheromone_lineage_problems(events, proposal_events)


def event_stage(event: TraceEvent) -> int | None:
    return _event_stage(event)


def manifest_replay(
    manifest: CapabilityManifest,
    *,
    force_fallback: bool = False,
    lifecycle_focus: str | None = None,
    include_layer_inputs: bool = True,
    memory_only_feedback: bool = False,
    replay_state: HybridReplayState | None = None,
) -> tuple[Any, TraceEvent]:
    return _manifest_replay(
        manifest,
        force_fallback=force_fallback,
        lifecycle_focus=lifecycle_focus,
        include_layer_inputs=include_layer_inputs,
        memory_only_feedback=memory_only_feedback,
        replay_state=replay_state,
    )


__all__ = ["check", "check_actual_trace", "manifest_replay"]
