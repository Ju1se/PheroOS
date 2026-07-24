from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any, cast

from pheroos.governance._swarm.replay import (
    _replay_state_from_verified_hybrid_step,
)
from pheroos.governance.collective import (
    HybridCollectiveStep,
    HybridReplayState,
    _canonical_authority_value,
    evaluate_hybrid_collective_step,
    hybrid_collective_step_is_authoritative,
    hybrid_replay_state_is_authoritative,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.pheromone import (
    pheromone_bound_candidate_id,
    pheromone_subject_id,
    pheromone_subject_type,
)
from pheroos.trace import pheromone_clip_payload_fingerprint


HYBRID_ATTENTION_PROFILE = "pheroos-hybrid-attention-v1"
ATTENTION_AUTHORITY_SCOPE = "none"
ATTENTION_CHANNEL = "attention_only"
_ATTENTION_BREAKDOWN_ISSUANCE = object()
_EXPLORATION_DIRECTIVE_ISSUANCE = object()
_NEGATIVE_ATTENTION_KINDS = frozenset({"negative", "cautionary", "alarm", "stale"})


@dataclass(frozen=True)
class AttentionCandidatePriority:
    """One non-authoritative candidate priority in the attention plane."""

    candidate_id: str
    rank: int
    attention_value: float
    contribution_breakdown: tuple[tuple[str, float], ...]
    independent_scout_count: int
    pheromone_source_diversity: int
    recruitment_pressure: float
    inhibition_pressure: float
    caution_pressure: float
    alarm_pressure: float
    novelty_pressure: float

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "attention candidate_id")
        _require_positive_integer(self.rank, "attention candidate rank")
        _require_finite(self.attention_value, "attention candidate value")
        _require_nonnegative_integer(
            self.independent_scout_count,
            "attention independent scout count",
        )
        _require_nonnegative_integer(
            self.pheromone_source_diversity,
            "attention pheromone source diversity",
        )
        for name in (
            "recruitment_pressure",
            "inhibition_pressure",
            "caution_pressure",
            "alarm_pressure",
            "novelty_pressure",
        ):
            _require_nonnegative(getattr(self, name), f"attention {name}")
        normalized = _canonical_contributions(self.contribution_breakdown)
        object.__setattr__(self, "contribution_breakdown", normalized)


@dataclass(frozen=True)
class AttentionSubjectPriority:
    """Route/tool/candidate pressure used only to direct exploration."""

    candidate_id: str
    subject_type: str
    subject_id: str
    kind: str
    pressure: float
    source_count: int
    trace_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "attention subject candidate_id")
        _require_text(self.subject_type, "attention subject_type")
        _require_text(self.subject_id, "attention subject_id")
        _require_text(self.kind, "attention subject kind")
        _require_finite(self.pressure, "attention subject pressure")
        _require_positive_integer(self.source_count, "attention subject source_count")
        object.__setattr__(
            self,
            "trace_event_ids",
            _canonical_labels(
                self.trace_event_ids,
                "attention subject trace_event_ids",
                allow_empty=False,
            ),
        )


@dataclass(frozen=True)
class AttentionReopenEligibility:
    candidate_id: str
    subject_type: str
    subject_id: str
    novelty_pressure: float
    reason: str
    trace_event_id: str

    def __post_init__(self) -> None:
        _require_text(self.candidate_id, "attention reopen candidate_id")
        _require_text(self.subject_type, "attention reopen subject_type")
        _require_text(self.subject_id, "attention reopen subject_id")
        _require_nonnegative(
            self.novelty_pressure,
            "attention reopen novelty_pressure",
        )
        _require_text(self.reason, "attention reopen reason")
        _require_text(self.trace_event_id, "attention reopen trace_event_id")


@dataclass(frozen=True)
class AttentionBreakdown:
    """Tamper-evident view of the one authoritative Hybrid memory pipeline.

    ``attention_value`` is deliberately not a commit score.  This record has
    ``authority_scope='none'`` and can only influence exploration ordering.
    The three lineage roots are domain separated and are never part of an
    Optimal Commit assessment or certificate truth root.
    """

    profile: str
    channel: str
    authority_scope: str
    commit_authority: bool
    protocol_id: str
    target: str
    current_step: int
    candidate_priorities: tuple[AttentionCandidatePriority, ...]
    subject_priorities: tuple[AttentionSubjectPriority, ...]
    reopen_eligibility: tuple[AttentionReopenEligibility, ...]
    memory_root: str
    replay_root: str
    trace_root: str
    source_step_root: str
    attention_root: str
    source_step: HybridCollectiveStep = field(repr=False, compare=False)
    replay_state: HybridReplayState = field(repr=False, compare=False)
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_priorities",
            tuple(self.candidate_priorities),
        )
        object.__setattr__(self, "subject_priorities", tuple(self.subject_priorities))
        object.__setattr__(self, "reopen_eligibility", tuple(self.reopen_eligibility))
        _validate_attention_breakdown_shape(self)


@dataclass(frozen=True)
class ExplorationDirective:
    """Runtime-facing exploration advice with explicitly zero commit authority."""

    profile: str
    channel: str
    authority_scope: str
    commit_authority: bool
    protocol_id: str
    target: str
    current_step: int
    source_attention_fingerprint: str
    candidate_order: tuple[str, ...]
    route_priorities: tuple[AttentionSubjectPriority, ...]
    tool_priorities: tuple[AttentionSubjectPriority, ...]
    exploration_budget: float
    requested_verification_roles: tuple[str, ...]
    requested_challenge_roles: tuple[str, ...]
    reopen_eligibility: tuple[AttentionReopenEligibility, ...]
    caution_candidate_ids: tuple[str, ...]
    alarm_candidate_ids: tuple[str, ...]
    directive_root: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for name in (
            "candidate_order",
            "requested_verification_roles",
            "requested_challenge_roles",
            "caution_candidate_ids",
            "alarm_candidate_ids",
        ):
            object.__setattr__(
                self,
                name,
                _canonical_labels(
                    getattr(self, name),
                    f"exploration directive {name}",
                    allow_empty=True,
                    preserve_order=name == "candidate_order",
                ),
            )
        object.__setattr__(self, "route_priorities", tuple(self.route_priorities))
        object.__setattr__(self, "tool_priorities", tuple(self.tool_priorities))
        object.__setattr__(self, "reopen_eligibility", tuple(self.reopen_eligibility))
        _validate_exploration_directive_shape(self)


def evaluate_hybrid_attention_step(
    **hybrid_inputs: Any,
) -> tuple[AttentionBreakdown, ExplorationDirective]:
    """Run the full shared Hybrid pipeline in attention-only mode.

    The legacy evaluator remains unchanged by default.  This adapter forces
    ``attention_only=True`` so an active Commit profile cannot accidentally
    traverse the legacy blended-score-to-commit branch.
    """

    if "attention_only" in hybrid_inputs:
        raise GovernanceError(
            "hybrid attention adapter owns attention_only and cannot be overridden"
        )
    step = evaluate_hybrid_collective_step(
        **hybrid_inputs,
        attention_only=True,
    )
    breakdown = derive_attention_breakdown(step)
    return breakdown, derive_exploration_directive(breakdown)


def derive_attention_breakdown(step: HybridCollectiveStep) -> AttentionBreakdown:
    """Derive a governance-issued attention view from one Hybrid memory step."""

    verified_step = _require_attention_only_step(step)
    replay_state = _replay_state_from_verified_hybrid_step(verified_step)
    current_step = _hybrid_step_current_step(step)
    roots = _hybrid_attention_roots(step, replay_state)
    candidate_pressures = _candidate_trail_pressures(step)
    priorities: list[AttentionCandidatePriority] = []
    ranked = sorted(
        step.state.scores.items(),
        key=lambda item: (-float(item[1]), item[0]),
    )
    for rank, (candidate_id, value) in enumerate(ranked, start=1):
        breakdown = tuple(
            sorted(
                (
                    (name, float(contribution))
                    for name, contribution in step.state.score_breakdown[
                        candidate_id
                    ].items()
                ),
                key=lambda item: item[0],
            )
        )
        pressure = candidate_pressures.get(candidate_id, {})
        priorities.append(
            AttentionCandidatePriority(
                candidate_id=candidate_id,
                rank=rank,
                attention_value=float(value),
                contribution_breakdown=breakdown,
                independent_scout_count=len(
                    step.state.independent_scouts[candidate_id]
                ),
                pheromone_source_diversity=int(
                    step.state.pheromone_source_diversity[candidate_id]
                ),
                recruitment_pressure=max(
                    0.0,
                    _breakdown_value(breakdown, "recruitment"),
                ),
                inhibition_pressure=abs(
                    min(0.0, _breakdown_value(breakdown, "inhibition"))
                ),
                caution_pressure=pressure.get("cautionary", 0.0),
                alarm_pressure=pressure.get("alarm", 0.0),
                novelty_pressure=pressure.get("novelty", 0.0),
            )
        )
    subject_priorities = _subject_priorities(step)
    reopen = tuple(
        sorted(
            (
                AttentionReopenEligibility(
                    candidate_id=item.candidate_id,
                    subject_type=item.subject_type,
                    subject_id=item.subject_id,
                    novelty_pressure=float(item.novelty_pressure),
                    reason=item.reason,
                    trace_event_id=item.trace_event_id,
                )
                for item in step.exploration_observations
                if item.reopen_eligible or item.novelty_pressure > 0
            ),
            key=lambda item: (
                item.candidate_id,
                item.subject_type,
                item.subject_id,
                item.trace_event_id,
            ),
        )
    )
    # Authority verification above and replay materialization both validate the
    # exact four-part issuance shape before this projection reads its bindings.
    issuance = cast(tuple[object, str, str, object], step._issuance)
    draft = AttentionBreakdown(
        profile=HYBRID_ATTENTION_PROFILE,
        channel=ATTENTION_CHANNEL,
        authority_scope=ATTENTION_AUTHORITY_SCOPE,
        commit_authority=False,
        protocol_id=issuance[1],
        target=issuance[2],
        current_step=current_step,
        candidate_priorities=tuple(priorities),
        subject_priorities=subject_priorities,
        reopen_eligibility=reopen,
        memory_root=roots["memory_root"],
        replay_root=roots["replay_root"],
        trace_root=roots["trace_root"],
        source_step_root=roots["source_step_root"],
        attention_root="sha256:" + "0" * 64,
        source_step=step,
        replay_state=replay_state,
    )
    root = pheromone_clip_payload_fingerprint(
        _attention_breakdown_payload(draft, include_root=False)
    )
    result = _replace_attention_root(draft, root)
    object.__setattr__(
        result,
        "_issuance",
        (_ATTENTION_BREAKDOWN_ISSUANCE, attention_breakdown_fingerprint(result)),
    )
    return result


def derive_exploration_directive(
    attention: AttentionBreakdown,
) -> ExplorationDirective:
    if not attention_breakdown_is_authoritative(attention):
        raise GovernanceError(
            "exploration directive requires a governance-issued attention breakdown"
        )
    candidate_order = tuple(
        item.candidate_id for item in attention.candidate_priorities
    )
    routes = tuple(
        item for item in attention.subject_priorities if item.subject_type == "route"
    )
    tools = tuple(
        item for item in attention.subject_priorities if item.subject_type == "tool"
    )
    missing_scouts = any(
        item.independent_scout_count == 0 for item in attention.candidate_priorities
    )
    verification_roles = {"evidence_verifier", "trace_verifier"}
    if missing_scouts:
        verification_roles.add("independent_scout")
    caution_ids = tuple(
        item.candidate_id
        for item in attention.candidate_priorities
        if item.caution_pressure > 0 or item.inhibition_pressure > 0
    )
    alarm_ids = tuple(
        item.candidate_id
        for item in attention.candidate_priorities
        if item.alarm_pressure > 0
    )
    challenge_roles = {"independent_replication"}
    if caution_ids or alarm_ids:
        challenge_roles.add("counterevidence_search")
    budget_state = attention.source_step.budget_state
    remaining = float(budget_state.round_remaining) if budget_state is not None else 0.0
    exploration_budget = max(
        0.0,
        remaining,
        float(attention.source_step.effective_policy.exploration_floor),
    )
    provisional = ExplorationDirective(
        profile=attention.profile,
        channel=attention.channel,
        authority_scope=ATTENTION_AUTHORITY_SCOPE,
        commit_authority=False,
        protocol_id=attention.protocol_id,
        target=attention.target,
        current_step=attention.current_step,
        source_attention_fingerprint=attention_breakdown_fingerprint(attention),
        candidate_order=candidate_order,
        route_priorities=routes,
        tool_priorities=tools,
        exploration_budget=exploration_budget,
        requested_verification_roles=tuple(sorted(verification_roles)),
        requested_challenge_roles=tuple(sorted(challenge_roles)),
        reopen_eligibility=attention.reopen_eligibility,
        caution_candidate_ids=caution_ids,
        alarm_candidate_ids=alarm_ids,
        directive_root="sha256:" + "0" * 64,
    )
    root = pheromone_clip_payload_fingerprint(
        _exploration_directive_payload(provisional, include_root=False)
    )
    result = _replace_directive_root(provisional, root)
    object.__setattr__(
        result,
        "_issuance",
        (_EXPLORATION_DIRECTIVE_ISSUANCE, exploration_directive_fingerprint(result)),
    )
    return result


def attention_breakdown_payload(
    attention: AttentionBreakdown,
) -> dict[str, Any]:
    if type(attention) is not AttentionBreakdown:
        raise GovernanceError("attention breakdown must be canonical")
    _validate_attention_breakdown_shape(attention)
    return _attention_breakdown_payload(attention, include_root=True)


def attention_breakdown_fingerprint(attention: AttentionBreakdown) -> str:
    return pheromone_clip_payload_fingerprint(attention_breakdown_payload(attention))


def attention_breakdown_is_authoritative(attention: object) -> bool:
    if type(attention) is not AttentionBreakdown:
        return False
    try:
        _validate_attention_breakdown_shape(attention)
        issuance = attention._issuance
        if not (
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _ATTENTION_BREAKDOWN_ISSUANCE
            and issuance[1] == attention_breakdown_fingerprint(attention)
        ):
            return False
        verified_step = _require_attention_only_step(attention.source_step)
        if not hybrid_replay_state_is_authoritative(attention.replay_state):
            return False
        expected_replay = _replay_state_from_verified_hybrid_step(verified_step)
        expected_replay_root = _hybrid_replay_root(expected_replay)
        replay_root = _hybrid_replay_root(attention.replay_state)
        if expected_replay_root != replay_root:
            return False
        roots = _hybrid_attention_roots(
            attention.source_step,
            attention.replay_state,
            verified_replay_root=replay_root,
        )
        if any(getattr(attention, name) != value for name, value in roots.items()):
            return False
        if attention.current_step != _hybrid_step_current_step(attention.source_step):
            return False
        if attention.attention_root != pheromone_clip_payload_fingerprint(
            _attention_breakdown_payload(attention, include_root=False)
        ):
            return False
        return True
    except Exception:
        return False


def exploration_directive_payload(
    directive: ExplorationDirective,
) -> dict[str, Any]:
    if type(directive) is not ExplorationDirective:
        raise GovernanceError("exploration directive must be canonical")
    _validate_exploration_directive_shape(directive)
    return _exploration_directive_payload(directive, include_root=True)


def exploration_directive_fingerprint(directive: ExplorationDirective) -> str:
    return pheromone_clip_payload_fingerprint(exploration_directive_payload(directive))


def exploration_directive_is_authoritative(
    directive: object,
    *,
    attention: AttentionBreakdown | None = None,
) -> bool:
    if type(directive) is not ExplorationDirective:
        return False
    try:
        _validate_exploration_directive_shape(directive)
        issuance = directive._issuance
        if not (
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _EXPLORATION_DIRECTIVE_ISSUANCE
            and issuance[1] == exploration_directive_fingerprint(directive)
            and directive.directive_root
            == pheromone_clip_payload_fingerprint(
                _exploration_directive_payload(directive, include_root=False)
            )
        ):
            return False
        if attention is None:
            return True
        return bool(
            attention_breakdown_is_authoritative(attention)
            and directive.source_attention_fingerprint
            == attention_breakdown_fingerprint(attention)
            and directive.protocol_id == attention.protocol_id
            and directive.target == attention.target
            and directive.current_step == attention.current_step
        )
    except Exception:
        return False


def _replace_attention_root(
    value: AttentionBreakdown,
    root: str,
) -> AttentionBreakdown:
    return replace(value, attention_root=root)


def _replace_directive_root(
    value: ExplorationDirective,
    root: str,
) -> ExplorationDirective:
    return replace(value, directive_root=root)


def _attention_breakdown_payload(
    attention: AttentionBreakdown,
    *,
    include_root: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile": attention.profile,
        "channel": attention.channel,
        "authority_scope": attention.authority_scope,
        "commit_authority": attention.commit_authority,
        "protocol_id": attention.protocol_id,
        "target": attention.target,
        "current_step": attention.current_step,
        "candidate_priorities": [
            _candidate_priority_payload(item) for item in attention.candidate_priorities
        ],
        "subject_priorities": [
            _subject_priority_payload(item) for item in attention.subject_priorities
        ],
        "reopen_eligibility": [
            _reopen_payload(item) for item in attention.reopen_eligibility
        ],
        "memory_root": attention.memory_root,
        "replay_root": attention.replay_root,
        "trace_root": attention.trace_root,
        "source_step_root": attention.source_step_root,
    }
    if include_root:
        payload["attention_root"] = attention.attention_root
    return payload


def _exploration_directive_payload(
    directive: ExplorationDirective,
    *,
    include_root: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile": directive.profile,
        "channel": directive.channel,
        "authority_scope": directive.authority_scope,
        "commit_authority": directive.commit_authority,
        "protocol_id": directive.protocol_id,
        "target": directive.target,
        "current_step": directive.current_step,
        "source_attention_fingerprint": directive.source_attention_fingerprint,
        "candidate_order": list(directive.candidate_order),
        "route_priorities": [
            _subject_priority_payload(item) for item in directive.route_priorities
        ],
        "tool_priorities": [
            _subject_priority_payload(item) for item in directive.tool_priorities
        ],
        "exploration_budget": directive.exploration_budget,
        "requested_verification_roles": list(directive.requested_verification_roles),
        "requested_challenge_roles": list(directive.requested_challenge_roles),
        "reopen_eligibility": [
            _reopen_payload(item) for item in directive.reopen_eligibility
        ],
        "caution_candidate_ids": list(directive.caution_candidate_ids),
        "alarm_candidate_ids": list(directive.alarm_candidate_ids),
    }
    if include_root:
        payload["directive_root"] = directive.directive_root
    return payload


def _candidate_priority_payload(item: AttentionCandidatePriority) -> dict[str, Any]:
    return {
        "candidate_id": item.candidate_id,
        "rank": item.rank,
        "attention_value": item.attention_value,
        "contribution_breakdown": [
            list(value) for value in item.contribution_breakdown
        ],
        "independent_scout_count": item.independent_scout_count,
        "pheromone_source_diversity": item.pheromone_source_diversity,
        "recruitment_pressure": item.recruitment_pressure,
        "inhibition_pressure": item.inhibition_pressure,
        "caution_pressure": item.caution_pressure,
        "alarm_pressure": item.alarm_pressure,
        "novelty_pressure": item.novelty_pressure,
    }


def _subject_priority_payload(item: AttentionSubjectPriority) -> dict[str, Any]:
    return {
        "candidate_id": item.candidate_id,
        "subject_type": item.subject_type,
        "subject_id": item.subject_id,
        "kind": item.kind,
        "pressure": item.pressure,
        "source_count": item.source_count,
        "trace_event_ids": list(item.trace_event_ids),
    }


def _reopen_payload(item: AttentionReopenEligibility) -> dict[str, Any]:
    return {
        "candidate_id": item.candidate_id,
        "subject_type": item.subject_type,
        "subject_id": item.subject_id,
        "novelty_pressure": item.novelty_pressure,
        "reason": item.reason,
        "trace_event_id": item.trace_event_id,
    }


def _hybrid_attention_roots(
    step: HybridCollectiveStep,
    replay_state: HybridReplayState,
    *,
    verified_replay_root: str | None = None,
) -> dict[str, str]:
    memory_root = pheromone_clip_payload_fingerprint(
        {
            "domain": "pheroos-hybrid-attention-memory-v1",
            "state": _canonical_authority_value(step.state),
            "active_trails": _canonical_authority_value(step.active_trails),
            "layer_coordination": _canonical_authority_value(step.layer_coordination),
            "adjustment_overlay": _canonical_authority_value(step.adjustment_overlay),
            "effective_policy": _canonical_authority_value(step.effective_policy),
            "deposit_records": _canonical_authority_value(step.deposit_records),
            "evaporation_records": _canonical_authority_value(step.evaporation_records),
            "diffusion_records": _canonical_authority_value(step.diffusion_records),
            "reinforcement_records": _canonical_authority_value(
                step.reinforcement_records
            ),
            "exploration_observations": _canonical_authority_value(
                step.exploration_observations
            ),
            "budget_state": _canonical_authority_value(step.budget_state),
        }
    )
    replay_root = (
        _hybrid_replay_root(replay_state)
        if verified_replay_root is None
        else verified_replay_root
    )
    trace_root = pheromone_clip_payload_fingerprint(
        {
            "domain": "pheroos-hybrid-attention-trace-v1",
            "events": [
                {
                    "event_type": item.event_type,
                    "protocol_id": item.protocol_id,
                    "target": item.target,
                    "reason": item.reason,
                    "lineage": dict(item.lineage),
                }
                for item in step.trace_events
            ],
        }
    )
    source_step_root = pheromone_clip_payload_fingerprint(
        {
            "domain": "pheroos-hybrid-attention-source-step-v1",
            "memory_root": memory_root,
            "replay_root": replay_root,
            "trace_root": trace_root,
        }
    )
    return {
        "memory_root": memory_root,
        "replay_root": replay_root,
        "trace_root": trace_root,
        "source_step_root": source_step_root,
    }


def _hybrid_replay_root(replay_state: HybridReplayState) -> str:
    return pheromone_clip_payload_fingerprint(
        {
            "domain": "pheroos-hybrid-attention-replay-v1",
            "state": _canonical_authority_value(replay_state),
        }
    )


def _hybrid_step_current_step(step: HybridCollectiveStep) -> int:
    score_events = tuple(
        item for item in step.trace_events if item.event_type == "pheromone_score"
    )
    if len(score_events) != 1:
        raise GovernanceError(
            "attention-only Hybrid step requires one pheromone_score trace event"
        )
    value = score_events[0].lineage.get("current_step")
    return _require_nonnegative_integer(value, "attention Hybrid current_step")


def _require_attention_only_step(step: object) -> HybridCollectiveStep:
    if not hybrid_collective_step_is_authoritative(step):
        raise GovernanceError("attention requires a governance-issued Hybrid step")
    assert type(step) is HybridCollectiveStep
    if not (
        step.decision.committed is False
        and step.decision.reason == "attention_only_no_commit_authority"
        and all(
            event.event_type not in {"consensus_check", "commit", "fallback"}
            for event in step.trace_events
        )
    ):
        raise GovernanceError(
            "active Commit attention cannot consume a legacy Hybrid decision path"
        )
    return step


def _candidate_trail_pressures(
    step: HybridCollectiveStep,
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for trail in step.active_trails:
        candidate_id = pheromone_bound_candidate_id(trail)
        pressures = result.setdefault(candidate_id, {})
        pressures[trail.kind] = pressures.get(trail.kind, 0.0) + float(trail.strength)
    return result


def _subject_priorities(
    step: HybridCollectiveStep,
) -> tuple[AttentionSubjectPriority, ...]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for trail in step.active_trails:
        key = (
            pheromone_bound_candidate_id(trail),
            pheromone_subject_type(trail),
            pheromone_subject_id(trail),
            trail.kind,
        )
        group = groups.setdefault(
            key,
            {"pressure": 0.0, "sources": set(), "traces": set()},
        )
        sign = -1.0 if trail.kind in _NEGATIVE_ATTENTION_KINDS else 1.0
        group["pressure"] += sign * float(trail.strength)
        group["sources"].add(trail.source_id)
        group["traces"].add(trail.trace_event_id)
    values = tuple(
        AttentionSubjectPriority(
            candidate_id=key[0],
            subject_type=key[1],
            subject_id=key[2],
            kind=key[3],
            pressure=float(value["pressure"]),
            source_count=len(value["sources"]),
            trace_event_ids=tuple(value["traces"]),
        )
        for key, value in groups.items()
    )
    return tuple(
        sorted(
            values,
            key=lambda item: (
                -item.pressure,
                item.subject_type,
                item.subject_id,
                item.kind,
                item.candidate_id,
            ),
        )
    )


def _validate_attention_breakdown_shape(attention: AttentionBreakdown) -> None:
    if attention.profile != HYBRID_ATTENTION_PROFILE:
        raise GovernanceError("attention profile is unsupported")
    if attention.channel != ATTENTION_CHANNEL:
        raise GovernanceError("attention channel is invalid")
    if attention.authority_scope != ATTENTION_AUTHORITY_SCOPE:
        raise GovernanceError("attention authority_scope must be none")
    if attention.commit_authority is not False:
        raise GovernanceError("attention can never carry commit authority")
    _require_text(attention.protocol_id, "attention protocol_id")
    _require_text(attention.target, "attention target")
    _require_nonnegative_integer(attention.current_step, "attention current_step")
    for name in (
        "memory_root",
        "replay_root",
        "trace_root",
        "source_step_root",
        "attention_root",
    ):
        _require_sha256(getattr(attention, name), f"attention {name}")
    if not attention.candidate_priorities:
        raise GovernanceError("attention requires candidate priorities")
    if any(
        type(item) is not AttentionCandidatePriority
        for item in attention.candidate_priorities
    ):
        raise GovernanceError("attention candidate priorities are not canonical")
    expected_ranks = tuple(range(1, len(attention.candidate_priorities) + 1))
    if tuple(item.rank for item in attention.candidate_priorities) != expected_ranks:
        raise GovernanceError("attention candidate ranks are not contiguous")
    if len({item.candidate_id for item in attention.candidate_priorities}) != len(
        attention.candidate_priorities
    ):
        raise GovernanceError("attention candidate priorities contain duplicates")
    if any(
        type(item) is not AttentionSubjectPriority
        for item in attention.subject_priorities
    ):
        raise GovernanceError("attention subject priorities are not canonical")
    if any(
        type(item) is not AttentionReopenEligibility
        for item in attention.reopen_eligibility
    ):
        raise GovernanceError("attention reopen records are not canonical")
    if type(attention.source_step) is not HybridCollectiveStep:
        raise GovernanceError("attention source step is not canonical")
    if type(attention.replay_state) is not HybridReplayState:
        raise GovernanceError("attention replay state is not canonical")


def _validate_exploration_directive_shape(
    directive: ExplorationDirective,
) -> None:
    if directive.profile != HYBRID_ATTENTION_PROFILE:
        raise GovernanceError("exploration directive profile is unsupported")
    if directive.channel != ATTENTION_CHANNEL:
        raise GovernanceError("exploration directive channel is invalid")
    if directive.authority_scope != ATTENTION_AUTHORITY_SCOPE:
        raise GovernanceError("exploration directive authority_scope must be none")
    if directive.commit_authority is not False:
        raise GovernanceError("exploration directive cannot carry commit authority")
    _require_text(directive.protocol_id, "exploration directive protocol_id")
    _require_text(directive.target, "exploration directive target")
    _require_nonnegative_integer(
        directive.current_step,
        "exploration directive current_step",
    )
    _require_sha256(
        directive.source_attention_fingerprint,
        "exploration source attention fingerprint",
    )
    _require_sha256(directive.directive_root, "exploration directive_root")
    _require_nonnegative(
        directive.exploration_budget,
        "exploration directive budget",
    )
    if not directive.candidate_order:
        raise GovernanceError("exploration directive candidate order is empty")
    if len(set(directive.candidate_order)) != len(directive.candidate_order):
        raise GovernanceError("exploration directive candidate order has duplicates")
    if any(
        type(item) is not AttentionSubjectPriority
        for item in (*directive.route_priorities, *directive.tool_priorities)
    ):
        raise GovernanceError("exploration directive priorities are not canonical")
    if any(item.subject_type != "route" for item in directive.route_priorities):
        raise GovernanceError("route priorities contain another subject type")
    if any(item.subject_type != "tool" for item in directive.tool_priorities):
        raise GovernanceError("tool priorities contain another subject type")
    if any(
        type(item) is not AttentionReopenEligibility
        for item in directive.reopen_eligibility
    ):
        raise GovernanceError("exploration directive reopen records are not canonical")


def _canonical_contributions(
    values: Sequence[tuple[str, float]],
) -> tuple[tuple[str, float], ...]:
    normalized: list[tuple[str, float]] = []
    for item in tuple(values):
        if not isinstance(item, tuple) or len(item) != 2:
            raise GovernanceError("attention contribution must be a name/value pair")
        name = _require_text(item[0], "attention contribution name")
        value = _require_finite(item[1], "attention contribution value")
        normalized.append((name, value))
    result = tuple(sorted(normalized, key=lambda item: item[0]))
    if len({item[0] for item in result}) != len(result):
        raise GovernanceError("attention contribution names must be unique")
    return result


def _canonical_labels(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool,
    preserve_order: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GovernanceError(f"{field_name} must be a sequence")
    normalized = tuple(_require_text(item, field_name) for item in tuple(values))
    if not allow_empty and not normalized:
        raise GovernanceError(f"{field_name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise GovernanceError(f"{field_name} contains duplicates")
    return normalized if preserve_order else tuple(sorted(normalized))


def _breakdown_value(
    breakdown: Sequence[tuple[str, float]],
    name: str,
) -> float:
    return next((float(value) for key, value in breakdown if key == name), 0.0)


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise GovernanceError(f"{field_name} must be a nonblank canonical string")
    return value


def _require_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GovernanceError(f"{field_name} must be a finite number")
    result = float(value)
    if not isfinite(result):
        raise GovernanceError(f"{field_name} must be a finite number")
    return result


def _require_nonnegative(value: object, field_name: str) -> float:
    result = _require_finite(value, field_name)
    if result < 0:
        raise GovernanceError(f"{field_name} must be non-negative")
    return result


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GovernanceError(f"{field_name} must be a non-negative integer")
    return value


def _require_positive_integer(value: object, field_name: str) -> int:
    result = _require_nonnegative_integer(value, field_name)
    if result == 0:
        raise GovernanceError(f"{field_name} must be positive")
    return result


def _require_sha256(value: object, field_name: str) -> str:
    if not (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    ):
        raise GovernanceError(f"{field_name} must be a canonical sha256 fingerprint")
    return value


__all__ = [
    "ATTENTION_AUTHORITY_SCOPE",
    "ATTENTION_CHANNEL",
    "HYBRID_ATTENTION_PROFILE",
    "AttentionBreakdown",
    "AttentionCandidatePriority",
    "AttentionReopenEligibility",
    "AttentionSubjectPriority",
    "ExplorationDirective",
    "attention_breakdown_fingerprint",
    "attention_breakdown_is_authoritative",
    "attention_breakdown_payload",
    "derive_attention_breakdown",
    "derive_exploration_directive",
    "evaluate_hybrid_attention_step",
    "exploration_directive_fingerprint",
    "exploration_directive_is_authoritative",
    "exploration_directive_payload",
]
