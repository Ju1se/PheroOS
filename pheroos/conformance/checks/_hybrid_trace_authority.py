from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import fsum
from typing import Any, cast

from pheroos.governance import HybridReplayState
from pheroos.governance.pheromone import BREAKDOWN_CATEGORIES
from pheroos.protocol.models import CapabilityManifest, collective_fallback_id
from pheroos.trace import TraceEvent

from ._hybrid_trace_coordination import (
    coordination_replay_problems,
    layer_pheromone_lineage_problems,
    policy_adjustment_trace_problems,
)
from ._hybrid_trace_lifecycle import pheromone_lifecycle_policy_problems
from ._hybrid_trace_receipts import replay_trace_problems as replay_trace_problems
from ._hybrid_trace_score import pheromone_score_reconstruction_problems
from ._hybrid_trace_shared import event_stage_order_problems, near


@dataclass(frozen=True)
class _AuthorityEvents:
    score_index: int
    score: TraceEvent
    consensus_index: int
    consensus: TraceEvent
    decision_index: int
    decision: TraceEvent


@dataclass
class _SignalReplay:
    active_ids: set[str]
    scout_ids: dict[str, set[str]]
    scout_support: dict[str, float]
    recruitment: dict[str, float]
    inhibition: dict[str, float]
    all_scout_ids: set[str] = field(default_factory=set)
    recruitment_sources: set[tuple[Any, Any]] = field(default_factory=set)
    inhibition_sources: set[tuple[Any, Any]] = field(default_factory=set)
    scout_trace_ids: set[str] = field(default_factory=set)
    recruitment_trace_ids: set[str] = field(default_factory=set)
    inhibition_trace_ids: set[str] = field(default_factory=set)
    lineage_ids: set[str] = field(default_factory=set)
    scout_count: int = 0


@dataclass(frozen=True)
class _CoordinationView:
    resolution: Mapping[str, Any]
    proposal_trace_ids: set[str]


def collective_authority_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    *,
    replay_state: HybridReplayState | None = None,
) -> list[str]:
    """Reconstruct the authority gates that justify commit or safe fallback."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return ["authority_collective_policy_missing"]
    selected, selection_problems = _select_authority_events(events)
    if selected is None:
        return selection_problems
    problems = _ordering_and_threshold_problems(policy, events, selected)
    active_ids = _active_candidate_ids(manifest)
    signal_state, signal_problems = _replay_signals(
        policy,
        events[: selected.score_index],
        active_ids,
    )
    problems.extend(signal_problems)
    problems.extend(_exploration_problems(events[: selected.score_index], signal_state))
    problems.extend(
        pheromone_lifecycle_policy_problems(manifest, events[: selected.score_index])
    )
    problems.extend(
        policy_adjustment_trace_problems(policy, events[: selected.score_index])
    )
    pheromone_events = tuple(
        event for event in events if event.event_type == "pheromone_score"
    )
    problems.extend(
        _replay_receipt_problems(
            manifest,
            events,
            pheromone_events,
            replay_state,
        )
    )
    problems.extend(_candidate_score_problems(selected.score, signal_state))
    problems.extend(
        _pheromone_score_problems(
            manifest,
            policy,
            events,
            selected,
            active_ids,
            pheromone_events,
        )
    )
    coordination, coordination_problems = _coordination_view(
        manifest,
        events,
        selected,
        active_ids,
    )
    problems.extend(coordination_problems)
    qualified = _qualified_candidates(policy, selected.score, active_ids)
    problems.extend(
        _decision_semantic_problems(manifest, selected, coordination, qualified)
    )
    problems.extend(
        _decision_upstream_problems(
            policy,
            events,
            selected,
            signal_state,
            coordination,
            pheromone_events,
        )
    )
    return problems


def _select_authority_events(
    events: tuple[TraceEvent, ...],
) -> tuple[_AuthorityEvents | None, list[str]]:
    candidates = tuple(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "candidate_score"
    )
    consensuses = tuple(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "consensus_check"
    )
    decisions = tuple(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type in {"commit", "fallback"}
    )
    issue = _authority_event_count_issue(candidates, consensuses, decisions)
    if issue is not None:
        return None, [issue]
    return _AuthorityEvents(*candidates[0], *consensuses[0], *decisions[0]), []


def _authority_event_count_issue(
    candidates: tuple[Any, ...],
    consensuses: tuple[Any, ...],
    decisions: tuple[Any, ...],
) -> str | None:
    if len(candidates) != 1:
        return "authority_candidate_score_count"
    if len(consensuses) != 1:
        return "authority_consensus_check_count"
    if len(decisions) != 1:
        return "authority_decision_event_count"
    return None


def _ordering_and_threshold_problems(
    policy: Any,
    events: tuple[TraceEvent, ...],
    selected: _AuthorityEvents,
) -> list[str]:
    problems: list[str] = []
    if not selected.score_index < selected.consensus_index < selected.decision_index:
        problems.append("authority_score_consensus_decision_order")
    problems.extend(event_stage_order_problems(events))
    lineage = selected.consensus.lineage
    if lineage.get("quorum_threshold") != policy.quorum_threshold:
        problems.append("authority_quorum_threshold_mismatch")
    if lineage.get("min_independent_scouts") != policy.min_independent_scouts:
        problems.append("authority_scout_threshold_mismatch")
    return problems


def _active_candidate_ids(manifest: CapabilityManifest) -> set[str]:
    target = manifest.protocol.quorum_policy.target
    return {
        candidate.id
        for candidate in manifest.protocol.candidates
        if candidate.target == target
    }


def _new_signal_replay(active_ids: set[str]) -> _SignalReplay:
    return _SignalReplay(
        active_ids=active_ids,
        scout_ids={candidate_id: set() for candidate_id in active_ids},
        scout_support={candidate_id: 0.0 for candidate_id in active_ids},
        recruitment={candidate_id: 0.0 for candidate_id in active_ids},
        inhibition={candidate_id: 0.0 for candidate_id in active_ids},
    )


def _replay_signals(
    policy: Any,
    events: tuple[TraceEvent, ...],
    active_ids: set[str],
) -> tuple[_SignalReplay, list[str]]:
    state = _new_signal_replay(active_ids)
    problems: list[str] = []
    for index, event in enumerate(events):
        if event.event_type == "scout_report":
            problems.extend(_scout_problems(policy, index, event, state))
        elif event.event_type in {"recruit", "inhibit"}:
            problems.extend(_direct_signal_problems(policy, index, event, state))
    return state, problems


def _scout_problems(
    policy: Any,
    index: int,
    event: TraceEvent,
    state: _SignalReplay,
) -> list[str]:
    state.scout_count += 1
    lineage = event.lineage
    candidate_id = cast(str, lineage.get("candidate_id"))
    if candidate_id not in state.active_ids:
        return [f"authority_scout_target:{index}"]
    problems: list[str] = []
    scout_id = cast(str, lineage.get("scout_id"))
    if scout_id in state.all_scout_ids:
        problems.append(f"authority_duplicate_scout:{scout_id}")
    state.all_scout_ids.add(scout_id)
    state.scout_ids[candidate_id].add(scout_id)
    support = float(lineage.get("support", 0.0))
    if support > float(policy.quorum_threshold):
        problems.append(f"authority_scout_strength_bound:{index}")
    state.scout_support[candidate_id] += support
    problems.extend(_scout_lineage_problems(index, lineage, state))
    return problems


def _scout_lineage_problems(
    index: int,
    lineage: Any,
    state: _SignalReplay,
) -> list[str]:
    source = lineage.get("source_trace_event_id")
    verification = lineage.get("verification_trace_event_id")
    if not source or not verification:
        return [f"authority_scout_verification_lineage:{index}"]
    problems = _record_collective_lineage(index, source, verification, state)
    state.scout_trace_ids.add(source)
    return problems


def _direct_signal_problems(
    policy: Any,
    index: int,
    event: TraceEvent,
    state: _SignalReplay,
) -> list[str]:
    kind = "recruitment" if event.event_type == "recruit" else "inhibition"
    enabled = (
        policy.recruitment_enabled
        if kind == "recruitment"
        else policy.inhibition_enabled
    )
    sources = (
        state.recruitment_sources if kind == "recruitment" else state.inhibition_sources
    )
    values = state.recruitment if kind == "recruitment" else state.inhibition
    trace_ids = (
        state.recruitment_trace_ids
        if kind == "recruitment"
        else state.inhibition_trace_ids
    )
    lineage = event.lineage
    candidate_id = lineage.get("candidate_id")
    identity = (lineage.get("source_id"), candidate_id)
    problems: list[str] = []
    if not enabled:
        problems.append(f"authority_{kind}_disabled:{index}")
    if identity in sources:
        problems.append(f"authority_duplicate_{kind}:{identity[0]}")
    sources.add(identity)
    if candidate_id not in state.active_ids or not lineage.get(
        "verification_trace_event_id"
    ):
        problems.append(f"authority_{kind}_lineage:{index}")
        return problems
    problems.extend(_record_direct_signal(index, lineage, state, trace_ids))
    strength = float(lineage.get("strength", 0.0))
    if strength > float(policy.quorum_threshold):
        problems.append(f"authority_{kind}_strength_bound:{index}")
    values[candidate_id] += strength
    return problems


def _record_direct_signal(
    index: int,
    lineage: Any,
    state: _SignalReplay,
    trace_ids: set[str],
) -> list[str]:
    source = lineage.get("source_trace_event_id")
    verification = lineage.get("verification_trace_event_id")
    problems = _record_collective_lineage(index, source, verification, state)
    trace_ids.add(str(source))
    return problems


def _record_collective_lineage(
    index: int,
    source: Any,
    verification: Any,
    state: _SignalReplay,
) -> list[str]:
    problems: list[str] = []
    for trace_event_id in (source, verification):
        if not isinstance(trace_event_id, str) or not trace_event_id:
            continue
        if trace_event_id in state.lineage_ids:
            problems.append(
                f"authority_duplicate_collective_trace:{index}:{trace_event_id}"
            )
        state.lineage_ids.add(trace_event_id)
    return problems


def _exploration_problems(
    events: tuple[TraceEvent, ...],
    state: _SignalReplay,
) -> list[str]:
    explore = [event for event in events if event.event_type == "explore"]
    if state.scout_count:
        valid = (
            len(explore) == 1
            and explore[0].lineage.get("scout_count") == state.scout_count
        )
        return [] if valid else ["authority_explore_scout_count"]
    return ["authority_explore_without_scouts"] if explore else []


def _replay_receipt_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    pheromone_events: tuple[TraceEvent, ...],
    replay_state: HybridReplayState | None,
) -> list[str]:
    if len(pheromone_events) != 1:
        return ["authority_pheromone_score_count"]
    return replay_trace_problems(
        events,
        pheromone_events[0],
        replay_state=replay_state,
        protocol_id=manifest.protocol.id,
        target=manifest.protocol.quorum_policy.target,
    )


def _candidate_score_problems(
    score_event: TraceEvent,
    state: _SignalReplay,
) -> list[str]:
    breakdown = score_event.lineage.get("score_breakdown", {})
    diversity = score_event.lineage.get("scout_diversity", {})
    problems: list[str] = []
    for candidate_id in state.active_ids:
        categories = breakdown.get(candidate_id, {})
        if set(categories) != set(BREAKDOWN_CATEGORIES):
            problems.append(f"authority_score_categories:{candidate_id}")
        if diversity.get(candidate_id) != len(state.scout_ids[candidate_id]):
            problems.append(f"authority_scout_diversity:{candidate_id}")
        if not near(categories.get("scout", 0.0), state.scout_support[candidate_id]):
            problems.append(f"authority_scout_score:{candidate_id}")
        if not near(
            categories.get("recruitment", 0.0), state.recruitment[candidate_id]
        ):
            problems.append(f"authority_recruitment_score:{candidate_id}")
        if not near(categories.get("inhibition", 0.0), -state.inhibition[candidate_id]):
            problems.append(f"authority_inhibition_score:{candidate_id}")
    return problems


def _pheromone_score_problems(
    manifest: CapabilityManifest,
    policy: Any,
    events: tuple[TraceEvent, ...],
    selected: _AuthorityEvents,
    active_ids: set[str],
    pheromone_events: tuple[TraceEvent, ...],
) -> list[str]:
    if not policy.pheromone_enabled:
        return []
    if len(pheromone_events) != 1:
        return ["authority_pheromone_score_count"]
    pheromone_event = pheromone_events[0]
    problems = pheromone_score_reconstruction_problems(
        manifest,
        events[: selected.score_index],
        pheromone_event,
        selected.score,
    )
    problems.extend(
        _pheromone_breakdown_problems(selected.score, pheromone_event, active_ids)
    )
    return problems


def _pheromone_breakdown_problems(
    score_event: TraceEvent,
    pheromone_event: TraceEvent,
    active_ids: set[str],
) -> list[str]:
    breakdown = score_event.lineage.get("score_breakdown", {})
    scores = pheromone_event.lineage.get("scores", {})
    pheromone_breakdown = pheromone_event.lineage.get("score_breakdown", {})
    problems: list[str] = []
    for candidate_id in active_ids:
        categories = breakdown.get(candidate_id, {})
        total = fsum(
            float(value)
            for category, value in categories.items()
            if category.startswith("pheromone_")
        )
        if not near(total, scores.get(candidate_id, 0.0)):
            problems.append(f"authority_pheromone_score:{candidate_id}")
        problems.extend(
            _pheromone_category_problems(candidate_id, categories, pheromone_breakdown)
        )
    return problems


def _pheromone_category_problems(
    candidate_id: str,
    categories: Any,
    pheromone_breakdown: Any,
) -> list[str]:
    return [
        f"authority_pheromone_category:{candidate_id}:{category}"
        for category in BREAKDOWN_CATEGORIES
        if category.startswith("pheromone_")
        and not near(
            categories.get(category, 0.0),
            pheromone_breakdown.get(candidate_id, {}).get(category, 0.0),
        )
    ]


def _coordination_view(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    selected: _AuthorityEvents,
    active_ids: set[str],
) -> tuple[_CoordinationView, list[str]]:
    prefix = events[: selected.score_index]
    assessments = [
        event for event in prefix if event.event_type == "coordination_assess"
    ]
    resolutions = [
        event for event in prefix if event.event_type == "coordination_resolve"
    ]
    proposals = [event for event in prefix if event.event_type == "layer_proposal"]
    resolution = resolutions[-1].lineage if resolutions else {}
    trace_ids = cast(
        set[str],
        {event.lineage.get("source_trace_event_id") for event in proposals},
    )
    trace_ids.discard(cast(str, None))
    problems: list[str] = []
    if len(trace_ids) != len(proposals):
        problems.append("authority_duplicate_layer_proposal_lineage")
    problems.extend(layer_pheromone_lineage_problems(prefix, proposals))
    problems.extend(
        _coordination_event_problems(
            manifest,
            prefix,
            proposals,
            assessments,
            resolutions,
            selected.score.lineage.get("score_breakdown", {}),
            active_ids,
            trace_ids,
            resolution,
        )
    )
    return _CoordinationView(resolution, trace_ids), problems


def _coordination_event_problems(
    manifest: CapabilityManifest,
    events: tuple[TraceEvent, ...],
    proposals: list[TraceEvent],
    assessments: list[TraceEvent],
    resolutions: list[TraceEvent],
    breakdown: dict[str, Any],
    active_ids: set[str],
    trace_ids: set[str],
    resolution: Mapping[str, Any],
) -> list[str]:
    if len(assessments) != 1 or len(resolutions) != 1:
        return ["authority_coordination_event_count"]
    problems: list[str] = []
    if set(assessments[0].lineage.get("proposal_lineage", ())) != trace_ids:
        problems.append("authority_coordination_proposal_lineage")
    if set(resolution.get("proposal_lineage", ())) != trace_ids:
        problems.append("authority_resolution_proposal_lineage")
    problems.extend(
        coordination_replay_problems(
            manifest,
            events,
            proposals,
            assessments[0],
            resolutions[0],
            breakdown,
            active_ids,
        )
    )
    return problems


def _qualified_candidates(
    policy: Any,
    score_event: TraceEvent,
    active_ids: set[str],
) -> list[str]:
    scores = score_event.lineage.get("scores", {})
    diversity = score_event.lineage.get("scout_diversity", {})
    return sorted(
        (
            candidate_id
            for candidate_id in active_ids
            if float(scores.get(candidate_id, 0.0)) >= float(policy.quorum_threshold)
            and int(diversity.get(candidate_id, 0)) >= policy.min_independent_scouts
        ),
        key=lambda candidate_id: (-float(scores[candidate_id]), candidate_id),
    )


def _decision_semantic_problems(
    manifest: CapabilityManifest,
    selected: _AuthorityEvents,
    coordination: _CoordinationView,
    qualified: list[str],
) -> list[str]:
    decision_candidate = selected.decision.lineage.get("candidate_id")
    coordination_fallback = bool(coordination.resolution.get("fallback_used", False))
    problems = _decision_consensus_problems(
        selected.decision,
        decision_candidate,
        coordination,
        coordination_fallback,
        qualified,
    )
    event_type, candidate, reason = _expected_decision(
        manifest,
        coordination,
        coordination_fallback,
        qualified,
    )
    checks = (
        (
            selected.decision.event_type != event_type,
            "authority_decision_semantic_event_type",
        ),
        (decision_candidate != candidate, "authority_decision_semantic_candidate"),
        (
            selected.decision.lineage.get("decision_reason") != reason,
            "authority_decision_semantic_reason",
        ),
        (selected.decision.reason != reason, "authority_decision_event_reason"),
    )
    problems.extend(message for failed, message in checks if failed)
    return problems


def _decision_consensus_problems(
    decision: TraceEvent,
    decision_candidate: Any,
    coordination: _CoordinationView,
    coordination_fallback: bool,
    qualified: list[str],
) -> list[str]:
    problems: list[str] = []
    if decision.event_type == "commit":
        if coordination_fallback:
            problems.append("authority_commit_during_coordination_fallback")
        if not qualified:
            problems.append("authority_commit_without_consensus")
        elif decision_candidate != qualified[0]:
            problems.append("authority_commit_not_top_qualified_candidate")
    else:
        if qualified and not coordination_fallback:
            problems.append("authority_fallback_despite_consensus")
        if (
            coordination_fallback
            and coordination.resolution.get("selected_candidate") != decision_candidate
        ):
            problems.append("authority_coordination_fallback_candidate")
    return problems


def _expected_decision(
    manifest: CapabilityManifest,
    coordination: _CoordinationView,
    coordination_fallback: bool,
    qualified: list[str],
) -> tuple[str, Any, str]:
    if coordination_fallback:
        return (
            "fallback",
            coordination.resolution.get("selected_candidate"),
            "safe_layer_coordination_fallback",
        )
    if qualified:
        return "commit", qualified[0], "collective_consensus"
    return (
        "fallback",
        collective_fallback_id(manifest.protocol),
        "safe_collective_fallback",
    )


def _decision_upstream_problems(
    policy: Any,
    events: tuple[TraceEvent, ...],
    selected: _AuthorityEvents,
    signals: _SignalReplay,
    coordination: _CoordinationView,
    pheromone_events: tuple[TraceEvent, ...],
) -> list[str]:
    upstream = set(selected.decision.lineage.get("upstream_score_lineage", ()))
    accepted = {
        str(event.lineage.get("source_trace_event_id"))
        for event in events[: selected.score_index]
        if event.event_type == "policy_adjustment"
        and event.lineage.get("result") == "accepted"
    }
    trails = {
        str(item.get("trace_event_id"))
        for event in pheromone_events
        for item in event.lineage.get("active_trails", ())
    }
    checks = (
        ("candidate_score" not in upstream, "authority_candidate_score_lineage"),
        (
            not signals.scout_trace_ids.issubset(upstream),
            "authority_scout_upstream_lineage",
        ),
        (
            not signals.recruitment_trace_ids.issubset(upstream),
            "authority_recruitment_upstream_lineage",
        ),
        (
            not signals.inhibition_trace_ids.issubset(upstream),
            "authority_inhibition_upstream_lineage",
        ),
        (not accepted.issubset(upstream), "authority_adjustment_upstream_lineage"),
        (
            policy.pheromone_enabled and "pheromone_score" not in upstream,
            "authority_pheromone_score_upstream_lineage",
        ),
        (not trails.issubset(upstream), "authority_pheromone_trail_upstream_lineage"),
        (
            not coordination.proposal_trace_ids.issubset(upstream),
            "authority_layer_upstream_lineage",
        ),
    )
    return [message for failed, message in checks if failed]
