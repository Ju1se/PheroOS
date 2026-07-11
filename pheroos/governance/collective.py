from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, fields as dataclass_fields, is_dataclass, replace
from enum import Enum
import json
import math
from types import MappingProxyType
from typing import Any

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import (
    SUPPORTED_LAYER_IDS,
    LayerCoordinationState,
    LayerPerformanceSnapshot,
    LayerProposal,
    StrategyBias,
    evaluate_layer_coordination,
    layer_coordination_policy_from_collective,
    materialize_layer_pheromone_proposals,
)
from pheroos.governance.pheromone import (
    PheromoneBudgetState,
    PheromoneBatchResult,
    PheromoneExplorationObservation,
    PheromoneLifecycleRecord,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneTrail,
    add_breakdown,
    collect_pheromone_source_diversity,
    deposit_pheromone_trails,
    diffuse_pheromone_trails_with_records,
    diffusion_policy_from_collective,
    empty_score_breakdown,
    evaporate_trails,
    evaporate_trails_with_records,
    observe_pheromone_exploration,
    pheromone_bound_candidate_id,
    pheromone_policy_from_collective,
    pheromone_source_id,
    pheromone_subject_id,
    pheromone_subject_type,
    scoreable_pheromone_candidate_id,
    score_pheromone_trails_result,
    score_pheromone_trails_with_breakdown,
    validate_pheromone_trail,
    validate_pheromone_subject_binding,
)
from pheroos.governance.pheromone_feedback import (
    PheromoneFeedback,
    PheromoneReinforcementResult,
    reinforce_pheromone_trails_with_records,
)
from pheroos.governance.policy_adjustment import (
    PolicyAdjustmentBatchResult,
    PolicyAdjustmentProposal,
    RunScopedPolicyOverlay,
    apply_policy_adjustment_overlay,
    run_scoped_policy_overlay_is_authoritative,
    validate_policy_adjustment_proposals,
)
from pheroos.governance.quorum import (
    QuorumDecision,
    _issue_quorum_decision,
    quorum_decision_is_authoritative,
)
from pheroos.governance.runtime_policy import (
    resolve_collective_fallback_id,
    validate_collective_runtime_policy,
)
from pheroos.governance.signal import SignalVerification, signal_verification_matches
from pheroos.protocol.models import (
    SWARM_COLLECTIVE_MODES,
    CollectiveDecisionPolicy,
    thaw_protocol_value,
)
from pheroos.trace import (
    PHEROMONE_CLIP_PAYLOAD_VERSION,
    TraceEvent,
    pheromone_clip_payload_fingerprint,
)


@dataclass(frozen=True)
class ScoutReport:
    scout_id: str
    candidate_id: str
    evidence_id: str
    provenance: str
    support: float = 1.0
    target: str = ""
    trace_event_id: str = ""
    verification: SignalVerification | None = None


@dataclass(frozen=True)
class RecruitmentSignal:
    source_id: str
    candidate_id: str
    strength: float = 1.0
    target: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    verification: SignalVerification | None = None


@dataclass(frozen=True)
class InhibitionSignal:
    source_id: str
    candidate_id: str
    strength: float = 1.0
    target: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    verification: SignalVerification | None = None


@dataclass(frozen=True)
class CollectiveDecisionState:
    scores: dict[str, float] = field(default_factory=dict)
    independent_scouts: dict[str, set[str]] = field(default_factory=dict)
    pheromone_source_diversity: dict[str, int] = field(default_factory=dict)
    score_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    layer_coordination: LayerCoordinationState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))
        object.__setattr__(
            self,
            "independent_scouts",
            MappingProxyType(
                {
                    candidate_id: frozenset(source_ids)
                    for candidate_id, source_ids in self.independent_scouts.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "pheromone_source_diversity",
            MappingProxyType(dict(self.pheromone_source_diversity)),
        )
        object.__setattr__(
            self,
            "score_breakdown",
            MappingProxyType(
                {
                    candidate_id: MappingProxyType(dict(categories))
                    for candidate_id, categories in self.score_breakdown.items()
                }
            ),
        )
        object.__setattr__(self, "layer_coordination", deepcopy(self.layer_coordination))

    def __deepcopy__(self, memo: dict[int, object]) -> CollectiveDecisionState:
        del memo
        return self


@dataclass(frozen=True)
class CollectiveDecisionStep:
    decision: QuorumDecision
    state: CollectiveDecisionState
    pheromone_trails: list[PheromoneTrail] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pheromone_trails", tuple(deepcopy(self.pheromone_trails)))


@dataclass(frozen=True)
class HybridCollectiveStep:
    decision: QuorumDecision
    state: CollectiveDecisionState
    active_trails: tuple[PheromoneTrail, ...]
    layer_coordination: LayerCoordinationState
    adjustment_overlay: RunScopedPolicyOverlay
    effective_policy: CollectiveDecisionPolicy
    deposit_records: tuple[PheromoneLifecycleRecord, ...] = ()
    evaporation_records: tuple[PheromoneLifecycleRecord, ...] = ()
    diffusion_records: tuple[PheromoneLifecycleRecord, ...] = ()
    reinforcement_records: tuple[PheromoneLifecycleRecord, ...] = ()
    exploration_observations: tuple[PheromoneExplorationObservation, ...] = ()
    processed_pheromone_event_ids: frozenset[str] = frozenset()
    processed_feedback_ids: frozenset[str] = frozenset()
    processed_adjustment_ids: frozenset[str] = frozenset()
    deposit_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    diffusion_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    feedback_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    adjustment_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    budget_state: PheromoneBudgetState | None = None
    trace_events: tuple[TraceEvent, ...] = ()
    _issuance: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in (
            "active_trails",
            "deposit_records",
            "evaporation_records",
            "diffusion_records",
            "reinforcement_records",
            "exploration_observations",
            "trace_events",
        ):
            object.__setattr__(self, field_name, tuple(deepcopy(getattr(self, field_name))))
        object.__setattr__(
            self,
            "processed_pheromone_event_ids",
            frozenset(self.processed_pheromone_event_ids),
        )
        object.__setattr__(self, "processed_feedback_ids", frozenset(self.processed_feedback_ids))
        object.__setattr__(self, "processed_adjustment_ids", frozenset(self.processed_adjustment_ids))
        for field_name in (
            "deposit_replay_receipts",
            "diffusion_replay_receipts",
            "feedback_replay_receipts",
            "adjustment_replay_receipts",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_replay_receipts(getattr(self, field_name)),
            )


_HYBRID_STEP_ISSUANCE = object()
_HYBRID_REPLAY_STATE_ISSUANCE = object()


@dataclass(frozen=True)
class HybridReplayState:
    protocol_id: str
    target: str
    active_trails: tuple[PheromoneTrail, ...] = ()
    processed_pheromone_event_ids: frozenset[str] = frozenset()
    processed_feedback_ids: frozenset[str] = frozenset()
    processed_adjustment_ids: frozenset[str] = frozenset()
    deposit_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    diffusion_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    feedback_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    adjustment_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    _issuance: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_trails", tuple(deepcopy(self.active_trails)))
        object.__setattr__(
            self,
            "processed_pheromone_event_ids",
            frozenset(self.processed_pheromone_event_ids),
        )
        object.__setattr__(self, "processed_feedback_ids", frozenset(self.processed_feedback_ids))
        object.__setattr__(self, "processed_adjustment_ids", frozenset(self.processed_adjustment_ids))
        for field_name in (
            "deposit_replay_receipts",
            "diffusion_replay_receipts",
            "feedback_replay_receipts",
            "adjustment_replay_receipts",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_replay_receipts(getattr(self, field_name)),
            )


def _canonical_authority_value(value: Any) -> Any:
    """Return an immutable, type-aware value snapshot for issued authority.

    Hybrid results deliberately contain several deeply nested frozen records,
    mapping proxies, and trace-lineage dictionaries.  A regular equality copy
    is insufficient because ``object.__setattr__`` can replace a field and
    because nested trace dictionaries remain mutable.  The canonical form owns
    no references to those containers and preserves concrete container types.
    """

    value_type = type(value)
    type_id = (value_type.__module__, value_type.__qualname__)
    if isinstance(value, Enum):
        return ("enum", type_id, _canonical_authority_value(value.value))
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, RunScopedPolicyOverlay):
        return (
            "run_scoped_policy_overlay",
            type_id,
            _canonical_authority_value(dict(value)),
            _canonical_authority_value(value.source_ids),
            _canonical_authority_value(value.trace_event_ids),
        )
    if is_dataclass(value) and not isinstance(value, type):
        return (
            "dataclass",
            type_id,
            tuple(
                (item.name, _canonical_authority_value(getattr(value, item.name)))
                for item in dataclass_fields(value)
                if item.name != "_issuance"
            ),
        )
    if isinstance(value, Mapping):
        entries = [
            (
                _canonical_authority_value(key),
                _canonical_authority_value(item),
            )
            for key, item in value.items()
        ]
        return ("mapping", type_id, tuple(sorted(entries, key=repr)))
    if isinstance(value, tuple):
        return (
            "tuple",
            type_id,
            tuple(_canonical_authority_value(item) for item in value),
        )
    if isinstance(value, list):
        return (
            "list",
            type_id,
            tuple(_canonical_authority_value(item) for item in value),
        )
    if isinstance(value, (set, frozenset)):
        items = [_canonical_authority_value(item) for item in value]
        return ("set", type_id, tuple(sorted(items, key=repr)))
    raise TypeError(f"unsupported authority snapshot value: {type_id[0]}.{type_id[1]}")


def _hybrid_authority_snapshot(record: object) -> tuple[tuple[str, Any], ...]:
    return tuple(
        (item.name, _canonical_authority_value(getattr(record, item.name)))
        for item in dataclass_fields(record)
        if item.name != "_issuance"
    )


def _hybrid_step_bindings_match(
    step: HybridCollectiveStep,
    *,
    protocol_id: str,
    target: str,
) -> bool:
    lifecycle_records = (
        *step.deposit_records,
        *step.evaporation_records,
        *step.diffusion_records,
        *step.reinforcement_records,
    )
    return bool(
        is_nonblank_string(protocol_id)
        and is_nonblank_string(target)
        and quorum_decision_is_authoritative(step.decision)
        and step.decision.target == target
        and type(step.state) is CollectiveDecisionState
        and type(step.layer_coordination) is LayerCoordinationState
        and step.state.layer_coordination == step.layer_coordination
        and run_scoped_policy_overlay_is_authoritative(step.adjustment_overlay)
        and type(step.effective_policy) is CollectiveDecisionPolicy
        and bool(step.trace_events)
        and all(
            type(event) is TraceEvent
            and event.protocol_id == protocol_id
            and event.target == target
            for event in step.trace_events
        )
        and all(type(trail) is PheromoneTrail and trail.target == target for trail in step.active_trails)
        and all(
            type(record) is PheromoneLifecycleRecord and record.target == target
            for record in lifecycle_records
        )
        and all(
            type(observation) is PheromoneExplorationObservation
            and observation.target == target
            for observation in step.exploration_observations
        )
        and (step.budget_state is None or type(step.budget_state) is PheromoneBudgetState)
    )


def _issue_hybrid_collective_step(
    step: HybridCollectiveStep,
    *,
    protocol_id: str,
    target: str,
) -> HybridCollectiveStep:
    if not _hybrid_step_bindings_match(
        step,
        protocol_id=protocol_id,
        target=target,
    ) or not _replay_receipts_match_processed_ids(step):
        raise GovernanceError("hybrid collective step authority bindings are invalid")
    object.__setattr__(
        step,
        "_issuance",
        (
            _HYBRID_STEP_ISSUANCE,
            protocol_id,
            target,
            _hybrid_authority_snapshot(step),
        ),
    )
    return step


def hybrid_collective_step_is_authoritative(step: object) -> bool:
    if type(step) is not HybridCollectiveStep:
        return False
    try:
        issuance = step._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 4
            and issuance[0] is _HYBRID_STEP_ISSUANCE
            and issuance[3] == _hybrid_authority_snapshot(step)
            and _hybrid_step_bindings_match(
                step,
                protocol_id=issuance[1],
                target=issuance[2],
            )
            and _replay_receipts_match_processed_ids(step)
        )
    except Exception:
        # Malformed or object.__setattr__-tampered issued records fail closed.
        return False


def replay_state_from_hybrid_step(step: HybridCollectiveStep) -> HybridReplayState:
    if not hybrid_collective_step_is_authoritative(step):
        raise GovernanceError("hybrid replay state requires a governance-issued step")
    protocol_id = step._issuance[1]
    target = step._issuance[2]
    state = HybridReplayState(
        protocol_id=protocol_id,
        target=target,
        active_trails=step.active_trails,
        processed_pheromone_event_ids=step.processed_pheromone_event_ids,
        processed_feedback_ids=step.processed_feedback_ids,
        processed_adjustment_ids=step.processed_adjustment_ids,
        deposit_replay_receipts=step.deposit_replay_receipts,
        diffusion_replay_receipts=step.diffusion_replay_receipts,
        feedback_replay_receipts=step.feedback_replay_receipts,
        adjustment_replay_receipts=step.adjustment_replay_receipts,
    )
    object.__setattr__(
        state,
        "_issuance",
        (
            _HYBRID_REPLAY_STATE_ISSUANCE,
            protocol_id,
            target,
            _hybrid_authority_snapshot(state),
        ),
    )
    return state


def hybrid_replay_state_is_authoritative(state: object) -> bool:
    if type(state) is not HybridReplayState:
        return False
    try:
        issuance = state._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 4
            and issuance[0] is _HYBRID_REPLAY_STATE_ISSUANCE
            and issuance[1] == state.protocol_id
            and issuance[2] == state.target
            and is_nonblank_string(state.protocol_id)
            and is_nonblank_string(state.target)
            and issuance[3] == _hybrid_authority_snapshot(state)
            and all(
                type(trail) is PheromoneTrail and trail.target == state.target
                for trail in state.active_trails
            )
            and _replay_receipts_match_processed_ids(state)
        )
    except Exception:
        # Replay memory is an authority input, so corruption is a denial rather
        # than a best-effort attempt to continue with caller-controlled state.
        return False


def _freeze_replay_receipts(
    receipts: Mapping[str, tuple[Any, ...]],
) -> MappingProxyType:
    return MappingProxyType(
        {
            trace_event_id: tuple(deepcopy(fingerprint))
            for trace_event_id, fingerprint in receipts.items()
        }
    )


def _replay_receipts_match_processed_ids(state: object) -> bool:
    receipt_id_sets = tuple(
        set(receipts)
        for receipts in (
            state.deposit_replay_receipts,
            state.diffusion_replay_receipts,
            state.feedback_replay_receipts,
            state.adjustment_replay_receipts,
        )
    )
    all_receipt_ids = set().union(*receipt_id_sets)
    return bool(
        sum(len(trace_ids) for trace_ids in receipt_id_sets)
        == len(all_receipt_ids)
        and
        (
            set(state.deposit_replay_receipts)
            | set(state.diffusion_replay_receipts)
        )
        == set(state.processed_pheromone_event_ids)
        and set(state.feedback_replay_receipts) == set(state.processed_feedback_ids)
        and set(state.adjustment_replay_receipts) == set(state.processed_adjustment_ids)
        and all(
            is_nonblank_string(trace_event_id) and isinstance(fingerprint, tuple)
            for receipts in (
                state.deposit_replay_receipts,
                state.diffusion_replay_receipts,
                state.feedback_replay_receipts,
                state.adjustment_replay_receipts,
            )
            for trace_event_id, fingerprint in receipts.items()
        )
    )


def _canonical_replay_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _canonical_replay_value(item))
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_replay_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_canonical_replay_value(item) for item in value), key=repr))
    return value


def _trail_replay_fingerprint(trail: PheromoneTrail) -> tuple[Any, ...]:
    return (
        "deposit-v1",
        trail.candidate_id,
        trail.strength,
        trail.subject_type,
        trail.subject_id,
        trail.target,
        trail.route_id,
        trail.tool_id,
        trail.kind,
        trail.source_id,
        trail.source_role,
        trail.evidence_id,
        trail.provenance,
        trail.trace_event_id,
        trail.deposited_at_step,
        trail.updated_at_step,
        trail.ttl_steps,
        tuple(trail.lineage_event_ids),
        trail.diffusion_root_trace_event_id,
        trail.diffusion_parent_trace_event_id,
        trail.diffusion_hop,
    )


def _feedback_replay_fingerprint(item: PheromoneFeedback) -> tuple[Any, ...]:
    return (
        "feedback-v1",
        item.source_id,
        item.subject_type,
        item.subject_id,
        item.candidate_id,
        item.target,
        item.outcome,
        item.reward,
        item.strength_delta,
        item.evidence_id,
        item.provenance,
        item.trace_event_id,
        item.step,
    )


def _adjustment_replay_fingerprint(
    item: PolicyAdjustmentProposal,
) -> tuple[Any, ...]:
    return (
        "adjustment-v1",
        item.layer_id,
        item.source_id,
        _canonical_replay_value(item.adjustments),
        item.provenance,
        item.trace_event_id,
    )


def _validate_replay_receipts(
    *,
    items: list[Any] | tuple[Any, ...],
    processed_ids: frozenset[str],
    receipts: Mapping[str, tuple[Any, ...]],
    fingerprint: Any,
    label: str,
) -> None:
    for item in items:
        trace_event_id = item.trace_event_id
        if trace_event_id not in processed_ids:
            continue
        expected = receipts.get(trace_event_id)
        if expected is None:
            raise GovernanceError(
                f"processed {label} id has no matching replay receipt: {trace_event_id}"
            )
        if expected != fingerprint(item):
            raise GovernanceError(
                f"{label} replay payload does not match its processed id: {trace_event_id}"
            )


def _extend_replay_receipts(
    receipts: Mapping[str, tuple[Any, ...]],
    items: list[Any] | tuple[Any, ...],
    fingerprint: Any,
) -> dict[str, tuple[Any, ...]]:
    updated = dict(receipts)
    for item in items:
        updated.setdefault(item.trace_event_id, fingerprint(item))
    return updated


def _validate_complete_hybrid_trace_identity(
    *,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal],
    inhibition_signals: list[InhibitionSignal],
    deposits: list[PheromoneTrail],
    layer_proposals: list[LayerProposal],
    materialized_layer_deposits: tuple[PheromoneTrail, ...],
    feedback: list[PheromoneFeedback],
    strategy_biases: list[StrategyBias],
    adjustment_proposals: list[PolicyAdjustmentProposal],
    existing_trails: list[PheromoneTrail],
    deposit_replay_receipts: Mapping[str, tuple[Any, ...]],
    diffusion_replay_receipts: Mapping[str, tuple[Any, ...]],
    feedback_replay_receipts: Mapping[str, tuple[Any, ...]],
    adjustment_replay_receipts: Mapping[str, tuple[Any, ...]],
) -> None:
    """Reject ambiguous trace identities before pheromone budget transitions.

    The sole intentional cross-surface identity is a ``propose_pheromone``
    LayerProposal and the deposit materialized from that same proposal.  The
    materialized record is therefore represented by its proposal owner here,
    rather than registered a second time.
    """

    materialized_ids = {trail.trace_event_id for trail in materialized_layer_deposits}
    current_owners: dict[str, list[str]] = {}

    def register(trace_event_id: Any, owner: str) -> None:
        if is_nonblank_string(trace_event_id):
            current_owners.setdefault(trace_event_id, []).append(owner)

    for report in scout_reports:
        register(report.trace_event_id, "scout")
        register(
            getattr(report.verification, "trace_event_id", ""),
            "scout_verification",
        )
    for signal, owner in (
        *((signal, "recruitment") for signal in recruitment_signals),
        *((signal, "inhibition") for signal in inhibition_signals),
    ):
        register(signal.trace_event_id, owner)
        register(
            getattr(signal.verification, "trace_event_id", ""),
            f"{owner}_verification",
        )
    for trail in deposits:
        register(trail.trace_event_id, "deposit")
    for proposal in layer_proposals:
        register(
            proposal.trace_event_id,
            (
                "layer_deposit"
                if proposal.trace_event_id in materialized_ids
                else "layer_proposal"
            ),
        )
    for item in feedback:
        register(item.trace_event_id, "feedback")
    for bias in strategy_biases:
        register(bias.trace_event_id, "strategy_bias")
    for proposal in adjustment_proposals:
        register(proposal.trace_event_id, "adjustment")

    duplicate_inputs = next(
        (
            trace_event_id
            for trace_event_id, owners in sorted(current_owners.items())
            if len(owners) != 1
        ),
        None,
    )
    if duplicate_inputs is not None:
        raise GovernanceError(
            "duplicate hybrid trace_event_id across input surfaces: "
            f"{duplicate_inputs}"
        )

    receipt_maps = {
        "deposit": deposit_replay_receipts,
        "diffusion": diffusion_replay_receipts,
        "feedback": feedback_replay_receipts,
        "adjustment": adjustment_replay_receipts,
    }
    receipt_owner: dict[str, str] = {}
    for lifecycle, receipts in receipt_maps.items():
        for trace_event_id in receipts:
            previous = receipt_owner.setdefault(trace_event_id, lifecycle)
            if previous != lifecycle:
                raise GovernanceError(
                    "duplicate hybrid trace_event_id across replay receipt lifecycles: "
                    f"{trace_event_id}"
                )

    allowed_replay_owner = {
        "deposit": "deposit",
        "layer_deposit": "deposit",
        "feedback": "feedback",
        "adjustment": "adjustment",
    }
    for trace_event_id, owners in current_owners.items():
        prior_lifecycle = receipt_owner.get(trace_event_id)
        if prior_lifecycle is not None and (
            allowed_replay_owner.get(owners[0]) != prior_lifecycle
        ):
            raise GovernanceError(
                "duplicate hybrid trace_event_id across current input and replay memory: "
                f"{trace_event_id}"
            )

    active_ids = {
        trail.trace_event_id
        for trail in existing_trails
        if is_nonblank_string(trail.trace_event_id)
    }
    for trace_event_id, owners in current_owners.items():
        if trace_event_id not in active_ids:
            continue
        prior_lifecycle = receipt_owner.get(trace_event_id)
        if allowed_replay_owner.get(owners[0]) != prior_lifecycle:
            raise GovernanceError(
                "duplicate hybrid trace_event_id across current input and active memory: "
                f"{trace_event_id}"
            )


def score_candidates(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    scout_reports: list[ScoutReport],
    target: str | None = None,
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    layer_coordination_state: LayerCoordinationState | None = None,
) -> CollectiveDecisionState:
    if layer_coordination_state is not None:
        raise GovernanceError(
            "externally constructed layer coordination state is not authoritative; "
            "submit layer proposals through evaluate_hybrid_collective_step"
        )
    validate_collective_runtime_policy(policy)
    strict_authority = policy.mode in SWARM_COLLECTIVE_MODES
    if strict_authority and not target:
        raise GovernanceError("swarm candidate scoring requires an active target")
    candidates = [
        candidate for candidate in candidate_set.candidates
        if target is None or candidate.target == target
    ]
    active_candidate_set = CandidateSet(candidates)
    scores = {candidate.id: 0.0 for candidate in candidates}
    independent_scouts = {candidate.id: set() for candidate in candidates}
    pheromone_source_diversity = {candidate.id: 0 for candidate in candidates}
    score_breakdown = empty_score_breakdown(active_candidate_set)
    collective_lineage_ids: set[str] = set()

    def record_lineage_ids(
        source_trace_event_id: str,
        verification: SignalVerification | None,
    ) -> None:
        identifiers = [source_trace_event_id]
        if verification is not None:
            identifiers.append(verification.trace_event_id)
        for trace_event_id in identifiers:
            if not trace_event_id:
                continue
            if trace_event_id in collective_lineage_ids:
                raise GovernanceError(
                    f"duplicate collective trace_event_id: {trace_event_id}"
                )
            collective_lineage_ids.add(trace_event_id)

    verified_scout_ids: set[str] = set()
    for report in sorted(
        scout_reports,
        key=lambda item: (item.candidate_id, item.scout_id, item.evidence_id, item.trace_event_id),
    ):
        validate_scout_report(
            report,
            target=target,
            require_verification=strict_authority,
            maximum_strength=float(policy.quorum_threshold),
        )
        if target is None:
            candidate_set.require_declared(report.candidate_id)
        else:
            candidate_set.require_declared_for_target(report.candidate_id, target)
        if report.scout_id in verified_scout_ids:
            raise GovernanceError(f"duplicate scout identity in collective batch: {report.scout_id}")
        verified_scout_ids.add(report.scout_id)
        record_lineage_ids(report.trace_event_id, report.verification)
        support = float(report.support)
        scores[report.candidate_id] += support
        add_breakdown(score_breakdown, report.candidate_id, "scout", support)
        independent_scouts[report.candidate_id].add(report.scout_id)

    if policy.recruitment_enabled:
        recruitment_sources: set[tuple[str, str]] = set()
        for signal in sorted(
            recruitment_signals or [],
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        ):
            validate_collective_signal(
                signal,
                target=target,
                require_verification=strict_authority,
                signal_name="recruitment",
                maximum_strength=float(policy.quorum_threshold),
            )
            if target is None:
                candidate_set.require_declared(signal.candidate_id)
            else:
                candidate_set.require_declared_for_target(signal.candidate_id, target)
            identity = (signal.source_id, signal.candidate_id)
            if identity in recruitment_sources:
                raise GovernanceError(f"duplicate recruitment source in collective batch: {signal.source_id}")
            recruitment_sources.add(identity)
            record_lineage_ids(signal.trace_event_id, signal.verification)
            support = float(signal.strength)
            scores[signal.candidate_id] += support
            add_breakdown(score_breakdown, signal.candidate_id, "recruitment", support)

    if policy.inhibition_enabled:
        inhibition_sources: set[tuple[str, str]] = set()
        for signal in sorted(
            inhibition_signals or [],
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        ):
            validate_collective_signal(
                signal,
                target=target,
                require_verification=strict_authority,
                signal_name="inhibition",
                maximum_strength=float(policy.quorum_threshold),
            )
            if target is None:
                candidate_set.require_declared(signal.candidate_id)
            else:
                candidate_set.require_declared_for_target(signal.candidate_id, target)
            identity = (signal.source_id, signal.candidate_id)
            if identity in inhibition_sources:
                raise GovernanceError(f"duplicate inhibition source in collective batch: {signal.source_id}")
            inhibition_sources.add(identity)
            record_lineage_ids(signal.trace_event_id, signal.verification)
            support = float(signal.strength)
            scores[signal.candidate_id] -= support
            add_breakdown(score_breakdown, signal.candidate_id, "inhibition", -support)

    if policy.pheromone_enabled:
        pheromone_policy = pheromone_policy_from_collective(policy)
        pheromone_source_diversity = collect_pheromone_source_diversity(
            candidate_set=active_candidate_set,
            trails=pheromone_trails or [],
            policy=pheromone_policy,
        )
        pheromone_scores, pheromone_breakdown = score_pheromone_trails_with_breakdown(
            candidate_set=active_candidate_set,
            trails=pheromone_trails or [],
            policy=pheromone_policy,
        )
        for candidate_id, score in pheromone_scores.items():
            scores[candidate_id] += score
            merge_candidate_breakdown(score_breakdown, candidate_id, pheromone_breakdown.get(candidate_id, {}))

    # Canonicalize totals from the breakdown.  This makes the breakdown the
    # reconstructable ABI source of truth instead of maintaining a second,
    # independently rounded score accumulator.
    scores = {
        candidate_id: sum(candidate_breakdown.values())
        for candidate_id, candidate_breakdown in score_breakdown.items()
    }
    state = CollectiveDecisionState(
        scores=scores,
        independent_scouts=independent_scouts,
        pheromone_source_diversity=pheromone_source_diversity,
        score_breakdown=score_breakdown,
        layer_coordination=layer_coordination_state,
    )
    validate_score_breakdown(state)
    return state


def validate_scout_report(
    report: ScoutReport,
    *,
    target: str | None,
    require_verification: bool,
    maximum_strength: float,
) -> None:
    if not is_nonblank_string(report.scout_id):
        raise GovernanceError("scout report scout_id is required")
    if not is_nonblank_string(report.evidence_id):
        raise GovernanceError("scout report evidence_id is required")
    if not is_nonblank_string(report.provenance):
        raise GovernanceError(f"scout report evidence is missing provenance: {report.evidence_id}")
    require_finite_bounded_strength(
        report.support,
        "scout report support",
        maximum_strength,
    )
    if target is not None and report.target and report.target != target:
        raise GovernanceError(f"scout report targets {report.target}, not active target {target}")
    if require_verification:
        if report.target != target:
            raise GovernanceError("verified swarm scout report must declare the active target")
        if not is_nonblank_string(report.trace_event_id):
            raise GovernanceError("verified swarm scout report trace_event_id is required")
        if not signal_verification_matches(
            report.verification,
            target=target or "",
            source_id=report.scout_id,
            subject_id=report.candidate_id,
        ):
            raise GovernanceError("swarm scout report is not governance-verified")


def validate_collective_signal(
    signal: RecruitmentSignal | InhibitionSignal,
    *,
    target: str | None,
    require_verification: bool,
    signal_name: str,
    maximum_strength: float,
) -> None:
    if not is_nonblank_string(signal.source_id):
        raise GovernanceError(f"{signal_name} signal source_id is required")
    require_finite_bounded_strength(
        signal.strength,
        f"{signal_name} signal strength",
        maximum_strength,
    )
    if target is not None and signal.target and signal.target != target:
        raise GovernanceError(f"{signal_name} signal targets {signal.target}, not active target {target}")
    if require_verification:
        if signal.target != target:
            raise GovernanceError(f"verified swarm {signal_name} signal must declare the active target")
        if not is_nonblank_string(signal.provenance):
            raise GovernanceError(f"swarm {signal_name} signal provenance is required")
        if not is_nonblank_string(signal.trace_event_id):
            raise GovernanceError(f"swarm {signal_name} signal trace_event_id is required")
        if not signal_verification_matches(
            signal.verification,
            target=target or "",
            source_id=signal.source_id,
            subject_id=signal.candidate_id,
        ):
            raise GovernanceError(f"swarm {signal_name} signal is not governance-verified")


def require_finite_non_negative(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise GovernanceError(f"{name} must be a finite number")
    if value < 0:
        raise GovernanceError(f"{name} must be non-negative")


def require_finite_bounded_strength(value: Any, name: str, maximum: float) -> None:
    require_finite_non_negative(value, name)
    require_finite_non_negative(maximum, f"{name} maximum")
    if float(value) > float(maximum):
        raise GovernanceError(f"{name} exceeds the declared collective threshold bound")


def _trace_event(
    event_type: str,
    *,
    protocol_id: str,
    target: str,
    reason: str,
    lineage: dict[str, Any] | None = None,
) -> TraceEvent:
    event = TraceEvent(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage or {},
    )
    try:
        event.validate()
    except ValueError as exc:
        raise GovernanceError(f"invalid governance trace action: {exc}") from exc
    return event


def _input_trace_events(
    *,
    protocol_id: str,
    target: str,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal],
    inhibition_signals: list[InhibitionSignal],
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    if scout_reports:
        events.append(
            _trace_event(
                "explore",
                protocol_id=protocol_id,
                target=target,
                reason="independent exploration produced scout reports",
                lineage={"scout_count": len(scout_reports)},
            )
        )
    for report in sorted(
        scout_reports,
        key=lambda item: (item.candidate_id, item.scout_id, item.evidence_id, item.trace_event_id),
    ):
        events.append(
            _trace_event(
                "scout_report",
                protocol_id=protocol_id,
                target=target,
                reason="governance-verified scout report accepted",
                lineage={
                    "scout_id": report.scout_id,
                    "candidate_id": report.candidate_id,
                    "evidence_id": report.evidence_id,
                    "provenance": report.provenance,
                    "support": report.support,
                    "source_trace_event_id": report.trace_event_id,
                    "verification_trace_event_id": (
                        report.verification.trace_event_id if report.verification is not None else ""
                    ),
                },
            )
        )
    for event_type, signals in (
        ("recruit", recruitment_signals),
        ("inhibit", inhibition_signals),
    ):
        for signal in sorted(
            signals,
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        ):
            events.append(
                _trace_event(
                    event_type,
                    protocol_id=protocol_id,
                    target=target,
                    reason=f"governance-verified {event_type} signal accepted",
                    lineage={
                        "source_id": signal.source_id,
                        "candidate_id": signal.candidate_id,
                        "strength": signal.strength,
                        "provenance": signal.provenance,
                        "source_trace_event_id": signal.trace_event_id,
                        "verification_trace_event_id": (
                            signal.verification.trace_event_id if signal.verification is not None else ""
                        ),
                    },
                )
            )
    return events


def _clip_causal_lineage(record: PheromoneLifecycleRecord) -> dict[str, Any]:
    if not record._causal_payload_json:
        raise GovernanceError(
            f"rejected pheromone lifecycle has no causal payload: {record.trace_event_id}"
        )
    try:
        envelope = json.loads(record._causal_payload_json)
    except (TypeError, ValueError) as exc:  # pragma: no cover - governance creates it
        raise GovernanceError("pheromone clip causal payload is not canonical JSON") from exc
    if (
        not isinstance(envelope, dict)
        or envelope.get("version") != PHEROMONE_CLIP_PAYLOAD_VERSION
        or not isinstance(envelope.get("payload"), dict)
    ):
        raise GovernanceError("pheromone clip causal payload envelope is invalid")
    payload = envelope["payload"]
    return {
        "causal_payload": payload,
        "causal_fingerprint": pheromone_clip_payload_fingerprint(payload),
    }


def _pheromone_lifecycle_trace_events(
    *,
    protocol_id: str,
    target: str,
    pheromone_policy: PheromonePolicy,
    deposit_records: tuple[PheromoneLifecycleRecord, ...],
    evaporation_records: tuple[PheromoneLifecycleRecord, ...],
    diffusion_records: tuple[PheromoneLifecycleRecord, ...],
    reinforcement_records: tuple[PheromoneLifecycleRecord, ...],
    pre_diffusion_trails: tuple[PheromoneTrail, ...],
    phase: str = "primary",
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for record in deposit_records:
        if record.requested_strength != record.applied_strength:
            events.append(
                _trace_event(
                    "pheromone_clip",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone deposit was bounded by declared budgets",
                    lineage={
                        "lifecycle": "deposit",
                        "result": (
                            "applied" if record.applied_strength > 0 else "rejected"
                        ),
                        "source_id": record.source_id,
                        "provenance": record.provenance,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": record.source_kind,
                        "source_strength": record.old_strength,
                        "new_strength": record.new_strength,
                        "step": record.step,
                        "source_trace_event_id": record.source_trace_event_id,
                        "trace_event_id": record.trace_event_id,
                        "requested_strength": record.requested_strength,
                        "applied_strength": record.applied_strength,
                        "round_budget_remaining": record.round_budget_remaining,
                        "source_budget_remaining": record.source_budget_remaining,
                        **_clip_causal_lineage(record),
                    },
                )
            )
        if record.new_strength == record.old_strength:
            continue
        events.append(
            _trace_event(
                "pheromone_deposit",
                protocol_id=protocol_id,
                target=target,
                reason="bounded pheromone deposit applied",
                lineage={
                    "source_id": record.source_id,
                    "provenance": record.provenance,
                    "subject_type": record.subject_type,
                    "subject_id": record.subject_id,
                    "candidate_id": record.candidate_id,
                    "kind": record.kind,
                    "source_kind": record.source_kind,
                    "source_strength": record.old_strength,
                    "old_strength": record.old_strength,
                    "requested_strength": record.requested_strength,
                    "applied_strength": record.applied_strength,
                    "new_strength": record.new_strength,
                    "round_budget_remaining": record.round_budget_remaining,
                    "source_budget_remaining": record.source_budget_remaining,
                    "step": record.step,
                    "deposited_at_step": record.deposited_at_step,
                    "updated_at_step": record.step,
                    "source_trace_event_id": record.source_trace_event_id,
                    "trace_event_id": record.trace_event_id,
                },
            )
        )

    for record in sorted(
        evaporation_records,
        key=lambda item: (item.trace_event_id, item.subject_type, item.subject_id, item.kind),
    ):
        if record.action == "expire":
            events.append(
                _trace_event(
                    "pheromone_expire",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone trail reached its declared TTL",
                    lineage={
                        "action": "expire",
                        "target": record.target,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": record.source_kind,
                        "source_id": record.source_id,
                        "provenance": record.provenance,
                        "source_trace_event_id": record.source_trace_event_id,
                        "trace_event_id": record.trace_event_id,
                        "source_strength": record.old_strength,
                        "old_strength": record.old_strength,
                        "requested_strength": record.old_strength,
                        "applied_strength": record.new_strength,
                        "new_strength": record.new_strength,
                        "strength_delta": record.new_strength - record.old_strength,
                        "step": record.step,
                        "source_updated_at_step": record.step - record.elapsed_steps,
                        "deposited_at_step": record.deposited_at_step,
                        "ttl_steps": record.ttl_steps,
                        "elapsed_steps": record.elapsed_steps,
                        "phase": phase,
                    },
                )
            )
            continue
        profile = (
            f"kind:{record.kind}"
            if record.kind in pheromone_policy.kind_profiles
            else f"global:{pheromone_policy.decay_model}"
        )
        events.append(
            _trace_event(
                "pheromone_evaporate",
                protocol_id=protocol_id,
                target=target,
                reason="pheromone lifecycle advanced deterministically",
                lineage={
                    "source_id": record.source_id,
                    "provenance": record.provenance,
                    "subject_type": record.subject_type,
                    "subject_id": record.subject_id,
                    "kind": record.kind,
                    "source_kind": record.source_kind,
                    "source_strength": record.old_strength,
                    "old_strength": record.old_strength,
                    "requested_strength": record.old_strength,
                    "applied_strength": record.new_strength,
                    "new_strength": record.new_strength,
                    "strength_delta": record.new_strength - record.old_strength,
                    "elapsed_steps": record.elapsed_steps,
                    "step": record.step,
                    "source_updated_at_step": record.step - record.elapsed_steps,
                    "deposited_at_step": record.deposited_at_step,
                    "profile": profile,
                    "candidate_id": record.candidate_id,
                    "source_trace_event_id": record.source_trace_event_id,
                    "trace_event_id": record.trace_event_id,
                    "phase": phase,
                },
            )
        )

    source_trails = {trail.trace_event_id: trail for trail in pre_diffusion_trails}
    for record in diffusion_records:
        source = source_trails.get(record.source_trace_event_id)
        if source is None:
            raise GovernanceError(
                f"diffusion record has no source trail lineage: {record.source_trace_event_id}"
            )
        if record.action == "diffuse_rejected":
            events.append(
                _trace_event(
                    "pheromone_clip",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone diffusion was rejected by the shared budget",
                    lineage={
                        "lifecycle": "diffusion",
                        "result": "rejected",
                        "source_id": record.source_id,
                        "provenance": source.provenance,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": source.kind,
                        "source_strength": source.strength,
                        "new_strength": 0.0,
                        "step": record.step,
                        "source_trace_event_id": record.source_trace_event_id,
                        "trace_event_id": record.trace_event_id,
                        "requested_strength": record.requested_strength,
                        "applied_strength": 0.0,
                        "round_budget_remaining": record.round_budget_remaining,
                        "source_budget_remaining": record.source_budget_remaining,
                        "source_subject": {
                            "type": pheromone_subject_type(source),
                            "id": pheromone_subject_id(source),
                        },
                        "target_subject": {
                            "type": record.subject_type,
                            "id": record.subject_id,
                        },
                        "root_trace_event_id": (
                            source.diffusion_root_trace_event_id
                            or source.trace_event_id
                        ),
                        "hop": record.hop,
                        "attenuation": record.attenuation,
                        "policy_attenuation": record.policy_attenuation,
                        "edge_attenuation": record.edge_attenuation,
                        **_clip_causal_lineage(record),
                    },
                )
            )
            continue
        events.append(
            _trace_event(
                "pheromone_diffuse",
                protocol_id=protocol_id,
                target=target,
                reason="pheromone diffused over a declared target-scoped edge",
                lineage={
                    "source_subject": {
                        "type": pheromone_subject_type(source),
                        "id": pheromone_subject_id(source),
                    },
                    "target_subject": {"type": record.subject_type, "id": record.subject_id},
                    "hop": record.hop,
                    "attenuation": record.attenuation,
                    "policy_attenuation": record.policy_attenuation,
                    "edge_attenuation": record.edge_attenuation,
                    "root_trace_event_id": (
                        source.diffusion_root_trace_event_id or source.trace_event_id
                    ),
                    "source_strength": source.strength,
                    "requested_strength": record.requested_strength,
                    "applied_strength": record.applied_strength,
                    "new_strength": record.new_strength,
                    "round_budget_remaining": record.round_budget_remaining,
                    "source_budget_remaining": record.source_budget_remaining,
                    "source_id": record.source_id,
                    "candidate_id": record.candidate_id,
                    "source_kind": source.kind,
                    "kind": record.kind,
                    "provenance": source.provenance,
                    "source_trace_event_id": record.source_trace_event_id,
                    "trace_event_id": record.trace_event_id,
                },
            )
        )
        source_trails[record.trace_event_id] = replace(
            source,
            candidate_id=record.candidate_id,
            strength=record.new_strength,
            subject_type=record.subject_type,
            subject_id=record.subject_id,
            trace_event_id=record.trace_event_id,
        )

    for record in reinforcement_records:
        if record.action == "reinforce_rejected":
            causal_lineage = _clip_causal_lineage(record)
            feedback_input = causal_lineage["causal_payload"]["input"]
            events.append(
                _trace_event(
                    "pheromone_clip",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone feedback was rejected by declared strength or budget bounds",
                    lineage={
                        "lifecycle": "feedback",
                        "result": "rejected",
                        "source_id": record.source_id,
                        "provenance": record.provenance,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": record.source_kind,
                        "source_strength": record.old_strength,
                        "new_strength": record.new_strength,
                        "outcome": record.outcome,
                        "reward": record.reward,
                        "strength_delta": feedback_input["strength_delta"],
                        "step": record.step,
                        "source_trace_event_id": record.source_trace_event_id,
                        "feedback_trace_event_id": (
                            record.cause_trace_event_id or record.trace_event_id
                        ),
                        "trace_event_id": record.trace_event_id,
                        "requested_strength": record.requested_strength,
                        "applied_strength": 0.0,
                        "round_budget_remaining": record.round_budget_remaining,
                        "source_budget_remaining": record.source_budget_remaining,
                        **causal_lineage,
                    },
                )
            )
            continue
        status = "applied"
        events.append(
            _trace_event(
                "pheromone_reinforce",
                protocol_id=protocol_id,
                target=target,
                reason="outcome feedback updated bounded collective memory",
                lineage={
                    "feedback_source": record.source_id,
                    "source_id": record.source_id,
                    "outcome": record.outcome,
                    "reward": record.reward,
                    "delta": record.applied_strength,
                    "source_strength": record.old_strength,
                    "old_strength": record.old_strength,
                    "requested_strength": (
                        record.requested_strength
                        if record.applied_strength >= 0
                        else abs(record.applied_strength)
                    ),
                    "applied_strength": abs(record.applied_strength),
                    "new_strength": record.new_strength,
                    "candidate_id": record.candidate_id,
                    "subject_type": record.subject_type,
                    "subject_id": record.subject_id,
                    "source_kind": record.source_kind,
                    "kind": record.kind,
                    "provenance": record.provenance,
                    "budget_result": {
                        "round_remaining": record.round_budget_remaining,
                        "source_remaining": record.source_budget_remaining,
                        "status": status,
                    },
                    "step": record.step,
                    "source_trace_event_id": record.source_trace_event_id,
                    "feedback_trace_event_id": (
                        record.cause_trace_event_id or record.trace_event_id
                    ),
                    "trace_event_id": record.trace_event_id,
                },
            )
        )
    return events


def _replay_receipt_digest(receipt: tuple[Any, ...]) -> str:
    return pheromone_clip_payload_fingerprint(
        {
            "lifecycle": "replay_receipt",
            "receipt": _canonical_replay_value(receipt),
        }
    )


def _replay_receipt_trace_payload(receipt: tuple[Any, ...]) -> list[Any]:
    """Expose the complete provider-neutral replay receipt for trace replay.

    Trace validation and conformance must be able to recompute the current
    payload digest instead of trusting two caller-controlled digest strings.
    The canonical replay value owns no governance objects, and TraceEvent takes
    a defensive lineage snapshot before the event leaves governance.
    """

    return list(_canonical_replay_value(receipt))


def _hybrid_step_trace_events(
    *,
    protocol_id: str,
    target: str,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    pheromone_policy: PheromonePolicy,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal],
    inhibition_signals: list[InhibitionSignal],
    deposit_inputs: list[PheromoneTrail],
    deposit_result: PheromoneBatchResult,
    deposit_replay_receipts: Mapping[str, tuple[Any, ...]],
    diffusion_replay_receipts: Mapping[str, tuple[Any, ...]],
    feedback_replay_receipts: Mapping[str, tuple[Any, ...]],
    adjustment_replay_receipts: Mapping[str, tuple[Any, ...]],
    evaporation_records: tuple[PheromoneLifecycleRecord, ...],
    pre_diffusion_trails: tuple[PheromoneTrail, ...],
    diffusion_result: PheromoneBatchResult,
    feedback: list[PheromoneFeedback],
    reinforcement_result: PheromoneReinforcementResult,
    post_reinforcement_expiration_records: tuple[PheromoneLifecycleRecord, ...],
    active_trails: tuple[PheromoneTrail, ...],
    observations: tuple[PheromoneExplorationObservation, ...],
    layer_proposals: list[LayerProposal],
    performance_snapshots: list[LayerPerformanceSnapshot],
    strategy_biases: list[StrategyBias],
    layer_state: LayerCoordinationState,
    adjustment_proposals: list[PolicyAdjustmentProposal],
    adjustment_batch: PolicyAdjustmentBatchResult,
    state: CollectiveDecisionState,
    decision: QuorumDecision,
    current_step: int,
) -> list[TraceEvent]:
    events = _input_trace_events(
        protocol_id=protocol_id,
        target=target,
        scout_reports=scout_reports,
        recruitment_signals=(recruitment_signals if policy.recruitment_enabled else []),
        inhibition_signals=(inhibition_signals if policy.inhibition_enabled else []),
    )
    replay_receipt_snapshot: dict[str, dict[str, str]] = {
        lifecycle: {}
        for lifecycle in ("deposit", "diffusion", "feedback", "adjustment")
    }

    def replay_binding(
        lifecycle: str,
        trace_event_id: str,
        current_receipt: tuple[Any, ...],
        processed_receipts: Mapping[str, tuple[Any, ...]],
    ) -> dict[str, str]:
        processed_receipt = processed_receipts.get(trace_event_id)
        if processed_receipt is None or processed_receipt != current_receipt:
            raise GovernanceError(
                f"{lifecycle} replay observation has no matching processed receipt: "
                f"{trace_event_id}"
            )
        current_digest = _replay_receipt_digest(current_receipt)
        processed_digest = _replay_receipt_digest(processed_receipt)
        replay_receipt_snapshot[lifecycle][trace_event_id] = processed_digest
        return {
            "replay_payload": _replay_receipt_trace_payload(current_receipt),
            "replay_payload_fingerprint": current_digest,
            "processed_payload_fingerprint": processed_digest,
        }

    accepted_adjustments = set(adjustment_batch.accepted_trace_event_ids)
    for proposal in sorted(
        adjustment_proposals,
        key=lambda item: (item.layer_id, item.source_id, item.trace_event_id),
    ):
        if proposal.trace_event_id not in adjustment_batch.processed_trace_event_ids:
            continue
        replayed = proposal.trace_event_id not in accepted_adjustments
        replay_lineage = (
            replay_binding(
                "adjustment",
                proposal.trace_event_id,
                _adjustment_replay_fingerprint(proposal),
                adjustment_replay_receipts,
            )
            if replayed
            else {}
        )
        events.append(
            _trace_event(
                "policy_adjustment",
                protocol_id=protocol_id,
                target=target,
                reason=(
                    "previously accepted run-scoped adjustment replay was ignored"
                    if replayed
                    else "run-scoped policy adjustment accepted within declared bounds"
                ),
                lineage={
                    "proposed_values": dict(proposal.adjustments),
                    "declared_bounds": {
                        key: thaw_protocol_value(policy.policy_adjustment_bounds[key])
                        for key in proposal.adjustments
                    },
                    "result": "replay_ignored" if replayed else "accepted",
                    "source_id": proposal.source_id,
                    "layer_id": proposal.layer_id,
                    "provenance": proposal.provenance,
                    "source_trace_event_id": proposal.trace_event_id,
                    "replayed": replayed,
                    **replay_lineage,
                },
            )
        )

    # Layer proposals are inputs to governed coordination.  Record them before
    # any proposal-derived pheromone deposit so trace order mirrors causality.
    for proposal in sorted(
        layer_proposals,
        key=lambda item: (
            item.layer_id,
            item.source_id,
            item.candidate_id,
            item.action,
            item.trace_event_id,
        ),
    ):
        events.append(
            _trace_event(
                "layer_proposal",
                protocol_id=protocol_id,
                target=target,
                reason="bounded layer proposal accepted for governance coordination",
                lineage={
                    "layer_id": proposal.layer_id,
                    "source_id": proposal.source_id,
                    "action": proposal.action,
                    "effect": layer_state.action_effects.get(proposal.trace_event_id, "metadata_only"),
                    "candidate_id": proposal.candidate_id,
                    "confidence": proposal.confidence,
                    "support": proposal.support,
                    "risk": proposal.risk,
                    "evidence_id": proposal.evidence_id,
                    "provenance": proposal.provenance,
                    "proposed_pheromone_kind": proposal.proposed_pheromone_kind,
                    "proposed_strength": proposal.proposed_strength,
                    "subject_type": proposal.metadata.get("subject_type", "candidate"),
                    "subject_id": proposal.metadata.get("subject_id", proposal.candidate_id),
                    "source_trace_event_id": proposal.trace_event_id,
                },
            )
        )
    for bias in sorted(
        strategy_biases,
        key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
    ):
        events.append(
            _trace_event(
                "layer_proposal",
                protocol_id=protocol_id,
                target=target,
                reason="bounded evolutionary StrategyBias accepted",
                lineage={
                    "layer_id": bias.layer_id,
                    "source_id": bias.source_id,
                    "action": "strategy_bias",
                    "effect": "bounded_candidate_preference",
                    "candidate_id": bias.candidate_id,
                    "confidence": bias.confidence,
                    "support": bias.support,
                    "risk": 0.0,
                    "proposed_strength": 0.0,
                    "proposed_pheromone_kind": "",
                    "subject_type": "candidate",
                    "subject_id": bias.candidate_id,
                    "evidence_id": bias.evidence_id,
                    "provenance": bias.provenance,
                    "source_trace_event_id": bias.trace_event_id,
                },
            )
        )

    events.extend(
        _pheromone_lifecycle_trace_events(
            protocol_id=protocol_id,
            target=target,
            pheromone_policy=pheromone_policy,
            deposit_records=deposit_result.records,
            evaporation_records=evaporation_records,
            diffusion_records=diffusion_result.records,
            reinforcement_records=reinforcement_result.records,
            pre_diffusion_trails=pre_diffusion_trails,
        )
    )
    events.extend(
        _pheromone_lifecycle_trace_events(
            protocol_id=protocol_id,
            target=target,
            pheromone_policy=pheromone_policy,
            deposit_records=(),
            evaporation_records=post_reinforcement_expiration_records,
            diffusion_records=(),
            reinforcement_records=(),
            pre_diffusion_trails=(),
            phase="post_reinforcement",
        )
    )
    deposit_by_id = {item.trace_event_id: item for item in deposit_inputs}
    for trace_event_id in deposit_result.replayed_event_ids:
        item = deposit_by_id[trace_event_id]
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="previously processed pheromone deposit replay was ignored",
                lineage={
                    "lifecycle": "deposit",
                    "source_trace_event_id": trace_event_id,
                    "result": "replay_ignored",
                    **replay_binding(
                        "deposit",
                        trace_event_id,
                        _trail_replay_fingerprint(item),
                        deposit_replay_receipts,
                    ),
                },
            )
        )
    for trace_event_id in diffusion_result.replayed_event_ids:
        processed_receipt = diffusion_replay_receipts.get(trace_event_id)
        if processed_receipt is None:
            raise GovernanceError(
                "diffusion replay observation has no processed receipt: "
                f"{trace_event_id}"
            )
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="previously processed pheromone diffusion replay was ignored",
                lineage={
                    "lifecycle": "diffusion",
                    "source_trace_event_id": trace_event_id,
                    "result": "replay_ignored",
                    **replay_binding(
                        "diffusion",
                        trace_event_id,
                        processed_receipt,
                        diffusion_replay_receipts,
                    ),
                },
            )
        )
    feedback_by_id = {item.trace_event_id: item for item in feedback}
    for trace_event_id in reinforcement_result.replayed_feedback_ids:
        item = feedback_by_id[trace_event_id]
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="previously processed feedback replay was ignored",
                lineage={
                    "lifecycle": "feedback",
                    "source_trace_event_id": item.trace_event_id,
                    "result": "replay_ignored",
                    **replay_binding(
                        "feedback",
                        trace_event_id,
                        _feedback_replay_fingerprint(item),
                        feedback_replay_receipts,
                    ),
                },
            )
        )

    active_source_kinds = {
        record.trace_event_id: record.source_kind
        for record in (
            *deposit_result.records,
            *evaporation_records,
            *diffusion_result.records,
            *reinforcement_result.records,
            *post_reinforcement_expiration_records,
        )
        if record.new_strength != record.old_strength or record.action == "expire"
    }
    active_candidate_set = CandidateSet(
        [candidate for candidate in candidate_set.candidates if candidate.target == target]
    )
    pheromone_score = score_pheromone_trails_result(
        candidate_set=active_candidate_set,
        trails=list(active_trails),
        policy=pheromone_policy,
    )
    events.append(
        _trace_event(
            "pheromone_score",
            protocol_id=protocol_id,
            target=target,
            reason="target-scoped pheromone contributions were scored",
            lineage={
                "scores": dict(pheromone_score.scores),
                "score_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_score.score_breakdown.items()
                },
                "kind_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_score.kind_breakdown.items()
                },
                "subject_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_score.subject_breakdown.items()
                },
                "active_trails": [
                    {
                        "trace_event_id": trail.trace_event_id,
                        "source_id": pheromone_source_id(trail),
                        "candidate_id": pheromone_bound_candidate_id(trail),
                        "subject_type": pheromone_subject_type(trail),
                        "subject_id": pheromone_subject_id(trail),
                        "kind": trail.kind,
                        "source_kind": active_source_kinds.get(
                            trail.trace_event_id,
                            trail.kind,
                        ),
                        "strength": trail.strength,
                        "provenance": trail.provenance,
                        "deposited_at_step": trail.deposited_at_step,
                        "updated_at_step": trail.updated_at_step,
                        "ttl_steps": trail.ttl_steps,
                    }
                    for trail in active_trails
                ],
                "current_step": current_step,
                "processed_replay_receipts": {
                    lifecycle: dict(receipts)
                    for lifecycle, receipts in replay_receipt_snapshot.items()
                },
            },
        )
    )
    if pheromone_score.normalization is not None:
        normalization = pheromone_score.normalization
        events.append(
            _trace_event(
                "pheromone_normalize",
                protocol_id=protocol_id,
                target=target,
                reason="competitive pheromone response normalized candidate pressure",
                lineage={
                    "candidates": list(normalization.candidate_ids),
                    "pre_scores": dict(normalization.pre_scores),
                    "post_scores": dict(normalization.post_scores),
                    "response_model": normalization.response_model,
                    "competition_mode": normalization.competition_mode,
                },
            )
        )
    for observation in observations:
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason=observation.reason,
                lineage={
                    "candidate_id": observation.candidate_id,
                    "subject_type": observation.subject_type,
                    "subject_id": observation.subject_id,
                    "novelty_pressure": observation.novelty_pressure,
                    "reopen_eligible": observation.reopen_eligible,
                    "source_trace_event_id": observation.trace_event_id,
                },
            )
        )
    exploration_candidate_ids = [
        candidate.id for candidate in active_candidate_set.candidates if not candidate.safe_fallback
    ]
    if (
        pheromone_policy.exploration_enabled
        and pheromone_policy.exploration_floor > 0
        and exploration_candidate_ids
    ):
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="declared deterministic exploration floor applied",
                lineage={
                    "exploration_floor": pheromone_policy.exploration_floor,
                    "candidate_ids": exploration_candidate_ids,
                },
            )
        )

    proposal_lineage = [*layer_state.trace_lineage]
    snapshot_by_layer = {
        snapshot.layer_id: snapshot for snapshot in performance_snapshots
    }
    snapshot_lineage: dict[str, dict[str, float | bool]] = {}
    for layer_id in sorted(SUPPORTED_LAYER_IDS):
        snapshot = snapshot_by_layer.get(layer_id)
        snapshot_lineage[layer_id] = {
            "present": snapshot is not None,
            "recent_success_rate": (
                snapshot.recent_success_rate if snapshot is not None else 0.0
            ),
            "recent_conflict_rate": (
                snapshot.recent_conflict_rate if snapshot is not None else 0.0
            ),
            "recent_fallback_rate": (
                snapshot.recent_fallback_rate if snapshot is not None else 0.0
            ),
            "mean_confidence": snapshot.mean_confidence if snapshot is not None else 0.0,
            "evidence_coverage": snapshot.evidence_coverage if snapshot is not None else 0.0,
            "trace_coverage": snapshot.trace_coverage if snapshot is not None else 0.0,
        }
    # Keep the draft coverage view for readers while recording the complete
    # performance inputs used by governance in ``snapshots``.  Explicit
    # presence prevents an omitted snapshot from being confused with an
    # all-zero snapshot during conformance replay.
    snapshot_coverage = {
        layer_id: {
            "mean_confidence": values["mean_confidence"],
            "evidence_coverage": values["evidence_coverage"],
            "trace_coverage": values["trace_coverage"],
        }
        for layer_id, values in snapshot_lineage.items()
    }
    snapshot_coverage["governance_trace_confirmations"] = dict(
        layer_state.trace_coverage_confirmations
    )
    events.append(
        _trace_event(
            "coordination_assess",
            protocol_id=protocol_id,
            target=target,
            reason="layer confidence, performance coverage, and weights assessed",
            lineage={
                "confidences": dict(layer_state.confidences),
                "weights": dict(layer_state.allocated_weights),
                "snapshots": snapshot_lineage,
                "coverage": snapshot_coverage,
                "action_effects": dict(layer_state.action_effects),
                "trace_coverage_confirmations": dict(
                    layer_state.trace_coverage_confirmations
                ),
                "proposal_lineage": list(proposal_lineage),
            },
        )
    )
    events.append(
        _trace_event(
            "coordination_resolve",
            protocol_id=protocol_id,
            target=target,
            reason="layer conflicts resolved under declared fallback policy",
            lineage={
                "conflicts": list(layer_state.conflicts),
                "resolution": layer_state.resolution,
                "selected_candidate": layer_state.selected_candidate,
                "fallback_used": layer_state.fallback_used,
                "reason": layer_state.resolution,
                "proposal_lineage": list(proposal_lineage),
            },
        )
    )

    score_lineage = {
        "scores": dict(state.scores),
        "score_breakdown": {
            candidate_id: dict(categories)
            for candidate_id, categories in state.score_breakdown.items()
        },
        "scout_diversity": {
            candidate_id: len(scout_ids)
            for candidate_id, scout_ids in state.independent_scouts.items()
        },
        "pheromone_source_diversity": dict(state.pheromone_source_diversity),
    }
    events.append(
        _trace_event(
            "candidate_score",
            protocol_id=protocol_id,
            target=target,
            reason="complete Hybrid candidate score reconstructed from declared categories",
            lineage=score_lineage,
        )
    )
    events.append(
        _trace_event(
            "consensus_check",
            protocol_id=protocol_id,
            target=target,
            reason="independent-scout and collective score gates evaluated",
            lineage={
                "quorum_threshold": policy.quorum_threshold,
                "min_independent_scouts": policy.min_independent_scouts,
            },
        )
    )
    decision_event_type = "fallback" if "fallback" in decision.reason else "commit"
    upstream_score_lineage = {
        "candidate_score",
        "pheromone_score",
        *(report.trace_event_id for report in scout_reports),
        *(
            signal.trace_event_id
            for signal in recruitment_signals
            if policy.recruitment_enabled
        ),
        *(
            signal.trace_event_id
            for signal in inhibition_signals
            if policy.inhibition_enabled
        ),
        *adjustment_batch.accepted_trace_event_ids,
        *(trail.trace_event_id for trail in active_trails),
        *proposal_lineage,
    }
    events.append(
        _trace_event(
            decision_event_type,
            protocol_id=protocol_id,
            target=target,
            reason=decision.reason,
            lineage={
                "target": target,
                "candidate_id": decision.candidate_id,
                "decision_reason": decision.reason,
                "upstream_score_lineage": sorted(upstream_score_lineage),
            },
        )
    )
    return events


def merge_candidate_breakdown(
    target: dict[str, dict[str, float]],
    candidate_id: str,
    source: dict[str, float],
) -> None:
    for category, value in source.items():
        add_breakdown(target, candidate_id, category, value)


def merge_governed_layer_coordination(
    state: CollectiveDecisionState,
    layer_state: LayerCoordinationState,
) -> CollectiveDecisionState:
    """Merge a state produced by the governance layer evaluator.

    This helper is intentionally not an external-state trust path: the Hybrid
    entry calls it immediately after `evaluate_layer_coordination`.  Public
    scoring rejects caller-constructed layer state in Hybrid mode.
    """

    score_breakdown = {
        candidate_id: dict(categories)
        for candidate_id, categories in state.score_breakdown.items()
    }
    if not layer_state.fallback_used:
        for candidate_id, candidate_breakdown in layer_state.score_breakdown.items():
            if candidate_id not in score_breakdown:
                raise GovernanceError(
                    f"layer coordination scored an undeclared active candidate: {candidate_id}"
                )
            merge_candidate_breakdown(score_breakdown, candidate_id, candidate_breakdown)
    scores = {
        candidate_id: sum(candidate_breakdown.values())
        for candidate_id, candidate_breakdown in score_breakdown.items()
    }
    merged = CollectiveDecisionState(
        scores=scores,
        independent_scouts=state.independent_scouts,
        pheromone_source_diversity=state.pheromone_source_diversity,
        score_breakdown=score_breakdown,
        layer_coordination=layer_state,
    )
    validate_score_breakdown(merged)
    return merged


def validate_score_breakdown(state: CollectiveDecisionState, *, tolerance: float = 0.0) -> None:
    require_finite_non_negative(tolerance, "score breakdown tolerance")
    for candidate_id, score in state.scores.items():
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            raise GovernanceError(f"candidate score must be finite: {candidate_id}")
        for category, value in state.score_breakdown.get(candidate_id, {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise GovernanceError(
                    f"score breakdown contains a non-finite value: {candidate_id}.{category}"
                )
        total = sum(state.score_breakdown.get(candidate_id, {}).values())
        if abs(total - score) > tolerance:
            raise GovernanceError(f"score breakdown does not reconstruct candidate score: {candidate_id}")


def candidate_score_lineage(
    state: CollectiveDecisionState,
    *,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    validate_score_breakdown(state)
    candidate_ids = [candidate_id] if candidate_id is not None else sorted(state.scores)
    return {
        "scores": {item: state.scores[item] for item in candidate_ids if item in state.scores},
        "score_breakdown": {
            item: dict(state.score_breakdown.get(item, {}))
            for item in candidate_ids
            if item in state.scores
        },
        "independent_scouts": {
            item: sorted(state.independent_scouts.get(item, set()))
            for item in candidate_ids
            if item in state.scores
        },
        "scout_diversity": {
            item: len(state.independent_scouts.get(item, set()))
            for item in candidate_ids
            if item in state.scores
        },
        "pheromone_source_diversity": {
            item: state.pheromone_source_diversity.get(item, 0)
            for item in candidate_ids
            if item in state.scores
        },
    }


def evaluate_collective_decision(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    layer_coordination_state: LayerCoordinationState | None = None,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    state = score_candidates(
        candidate_set=candidate_set,
        policy=policy,
        scout_reports=scout_reports,
        target=target,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=pheromone_trails,
        layer_coordination_state=layer_coordination_state,
    )
    return _decide_collective_state(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        state=state,
        fallback_candidate_id=fallback_candidate_id,
    )


def evaluate_collective_decision_step(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    scout_reports: list[ScoutReport],
    current_step: int,
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    pheromone_trails: list[PheromoneTrail] | None = None,
    layer_coordination_state: LayerCoordinationState | None = None,
    fallback_candidate_id: str | None = None,
) -> CollectiveDecisionStep:
    validate_collective_runtime_policy(policy)
    active_trails = list(pheromone_trails or [])
    if policy.pheromone_enabled:
        active_trails = evaporate_trails(
            active_trails,
            pheromone_policy_from_collective(policy),
            current_step=current_step,
        )
    state = score_candidates(
        candidate_set=candidate_set,
        policy=policy,
        scout_reports=scout_reports,
        target=target,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        pheromone_trails=active_trails,
        layer_coordination_state=layer_coordination_state,
    )
    decision = _decide_collective_state(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        state=state,
        fallback_candidate_id=fallback_candidate_id,
    )
    return CollectiveDecisionStep(decision=decision, state=state, pheromone_trails=active_trails)


def evaluate_hybrid_collective_step(
    *,
    protocol_id: str,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    current_step: int,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    existing_trails: list[PheromoneTrail] | None = None,
    deposits: list[PheromoneTrail] | None = None,
    topology: PheromoneNeighborhood | None = None,
    feedback: list[PheromoneFeedback] | None = None,
    layer_proposals: list[LayerProposal] | None = None,
    performance_snapshots: list[LayerPerformanceSnapshot] | None = None,
    strategy_biases: list[StrategyBias] | None = None,
    adjustment_proposals: list[PolicyAdjustmentProposal] | None = None,
    processed_pheromone_event_ids: frozenset[str] = frozenset(),
    processed_feedback_ids: frozenset[str] = frozenset(),
    processed_adjustment_ids: frozenset[str] = frozenset(),
    replay_state: HybridReplayState | None = None,
    fallback_candidate_id: str | None = None,
) -> HybridCollectiveStep:
    """Evaluate one complete, deterministic Hybrid Pheromone governance step.

    All inputs are validated before a result is returned, all lifecycle
    transitions are pure, and no caller-provided decision or coordination state
    is accepted.  Proposal layers can influence bounded score categories but
    the independent-scout gate and safe fallback remain authoritative.
    """

    validate_collective_runtime_policy(policy)
    if any(
        (
            processed_pheromone_event_ids,
            processed_feedback_ids,
            processed_adjustment_ids,
        )
    ):
        raise GovernanceError(
            "raw processed replay ids are not authoritative; use a governance-issued replay state"
        )
    deposit_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    diffusion_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    feedback_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    adjustment_replay_receipts: Mapping[str, tuple[Any, ...]] = {}
    if replay_state is not None:
        if not hybrid_replay_state_is_authoritative(replay_state):
            raise GovernanceError("hybrid replay state is not governance-issued")
        if replay_state.protocol_id != protocol_id or replay_state.target != target:
            raise GovernanceError("hybrid replay state does not match the active protocol and target")
        if existing_trails:
            raise GovernanceError(
                "existing trails cannot override governance-issued replay memory"
            )
        existing_trails = list(replay_state.active_trails)
        processed_pheromone_event_ids = replay_state.processed_pheromone_event_ids
        processed_feedback_ids = replay_state.processed_feedback_ids
        processed_adjustment_ids = replay_state.processed_adjustment_ids
        deposit_replay_receipts = replay_state.deposit_replay_receipts
        diffusion_replay_receipts = replay_state.diffusion_replay_receipts
        feedback_replay_receipts = replay_state.feedback_replay_receipts
        adjustment_replay_receipts = replay_state.adjustment_replay_receipts
    if not is_nonblank_string(protocol_id):
        raise GovernanceError("hybrid collective step requires protocol_id")
    if policy.mode != "hybrid":
        raise GovernanceError("hybrid collective step requires mode='hybrid'")
    if not is_nonblank_string(target):
        raise GovernanceError("hybrid collective step requires an active target")
    if isinstance(current_step, bool) or not isinstance(current_step, int) or current_step < 0:
        raise GovernanceError("hybrid collective current_step must be a non-negative integer")
    if not (
        policy.pheromone_enabled
        and policy.pheromone_diffusion_enabled
        and policy.pheromone_feedback_enabled
        and policy.layer_coordination_enabled
        and bool(policy.pheromone_kind_profiles)
        and bool(policy.policy_adjustment_bounds)
        and policy.pheromone_require_provenance
        and policy.pheromone_require_trace
    ):
        raise GovernanceError("hybrid collective step requires the complete declared Hybrid path")
    if topology is None:
        raise GovernanceError("hybrid collective step requires declared pheromone topology")

    fallback_id = resolve_collective_fallback_id(
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        fallback_candidate_id=fallback_candidate_id,
    )
    fallback = candidate_set.require_declared_for_target(fallback_id, target)
    if not fallback.safe_fallback:
        raise GovernanceError(f"hybrid fallback candidate is not marked safe: {fallback.id}")
    active_candidates = [candidate for candidate in candidate_set.candidates if candidate.target == target]
    if not active_candidates:
        raise GovernanceError("hybrid collective step has no candidates for the active target")

    # Run-scoped adaptation is validated as one atomic batch and applied to an
    # immutable replacement policy; the manifest-owned object is never mutated.
    scout_inputs = list(scout_reports)
    recruitment_inputs = list(recruitment_signals or [])
    inhibition_inputs = list(inhibition_signals or [])
    explicit_deposits = list(deposits or [])
    feedback_inputs = list(feedback or [])
    strategy_bias_inputs = list(strategy_biases or [])
    adjustment_inputs = list(adjustment_proposals or [])
    _validate_replay_receipts(
        items=adjustment_inputs,
        processed_ids=processed_adjustment_ids,
        receipts=adjustment_replay_receipts,
        fingerprint=_adjustment_replay_fingerprint,
        label="policy adjustment",
    )
    adjustment_batch = validate_policy_adjustment_proposals(
        adjustment_inputs,
        policy,
        processed_trace_event_ids=processed_adjustment_ids,
    )
    effective_policy = apply_policy_adjustment_overlay(policy, adjustment_batch.overlay)
    validate_collective_runtime_policy(effective_policy)
    pheromone_policy = pheromone_policy_from_collective(effective_policy)
    diffusion_policy = diffusion_policy_from_collective(effective_policy)
    layer_policy = layer_coordination_policy_from_collective(effective_policy)
    layer_inputs = list(layer_proposals or [])
    # Layer processing is deliberately two-phase.  Phase 1 validates the whole
    # proposal batch and materializes only proposal-owned memory inputs; these
    # trails have no score or authority until the normal pheromone pipeline
    # accepts them below.  Phase 2 performs confidence/coverage/conflict
    # coordination after pheromone dynamics, using the same validated records.
    proposed_layer_trails = materialize_layer_pheromone_proposals(
        proposals=layer_inputs,
        candidate_set=candidate_set,
        target=target,
        current_step=current_step,
        policy=layer_policy,
        neighborhood=topology,
    )
    _validate_complete_hybrid_trace_identity(
        scout_reports=scout_inputs,
        recruitment_signals=recruitment_inputs,
        inhibition_signals=inhibition_inputs,
        deposits=explicit_deposits,
        layer_proposals=layer_inputs,
        materialized_layer_deposits=proposed_layer_trails,
        feedback=feedback_inputs,
        strategy_biases=strategy_bias_inputs,
        adjustment_proposals=adjustment_inputs,
        existing_trails=list(existing_trails or []),
        deposit_replay_receipts=deposit_replay_receipts,
        diffusion_replay_receipts=diffusion_replay_receipts,
        feedback_replay_receipts=feedback_replay_receipts,
        adjustment_replay_receipts=adjustment_replay_receipts,
    )
    deposit_inputs = [*explicit_deposits, *proposed_layer_trails]
    for trail in deposit_inputs:
        validate_pheromone_subject_binding(
            topology,
            subject_type=pheromone_subject_type(trail),
            subject_id=pheromone_subject_id(trail),
            candidate_id=pheromone_bound_candidate_id(trail),
            require_declared=bool(
                scoreable_pheromone_candidate_id(trail, pheromone_policy)
            ),
        )
    _validate_replay_receipts(
        items=deposit_inputs,
        processed_ids=processed_pheromone_event_ids,
        receipts=deposit_replay_receipts,
        fingerprint=_trail_replay_fingerprint,
        label="pheromone deposit",
    )

    # Thread one source/round budget through every state-changing pheromone
    # stage.  Splitting equivalent input across deposit, diffusion, or feedback
    # cannot multiply the declared cap.
    budget = PheromoneBudgetState.for_policy(pheromone_policy)
    deposit_result = deposit_pheromone_trails(
        deposit_inputs,
        pheromone_policy,
        candidate_set=candidate_set,
        target=target,
        budget_state=budget,
        processed_event_ids=processed_pheromone_event_ids,
    )
    budget = deposit_result.budget_state or budget
    combined_trails = [*list(existing_trails or []), *deposit_result.trails]
    seen_trail_ids: set[str] = set()
    for trail in combined_trails:
        validate_pheromone_trail(
            trail,
            pheromone_policy,
            candidate_set=candidate_set,
            target=target,
        )
        if not pheromone_bound_candidate_id(trail):
            raise GovernanceError("hybrid pheromone trail must bind a declared candidate")
        if trail.trace_event_id in seen_trail_ids:
            raise GovernanceError(f"duplicate active pheromone trace_event_id: {trail.trace_event_id}")
        seen_trail_ids.add(trail.trace_event_id)

    evaporation_result = evaporate_trails_with_records(
        combined_trails,
        pheromone_policy,
        current_step=current_step,
    )
    pre_diffusion_trails = tuple(evaporation_result.trails)
    processed_pheromone = frozenset(
        set(processed_pheromone_event_ids) | set(deposit_result.processed_event_ids)
    )
    diffusion_result = diffuse_pheromone_trails_with_records(
        list(pre_diffusion_trails),
        topology,
        pheromone_policy,
        diffusion_policy,
        candidate_set=candidate_set,
        target=target,
        budget_state=budget,
        processed_event_ids=processed_pheromone,
        processed_event_receipts=diffusion_replay_receipts,
    )
    budget = diffusion_result.budget_state or budget
    processed_pheromone = frozenset(
        set(processed_pheromone) | set(diffusion_result.processed_event_ids)
    )
    _validate_replay_receipts(
        items=feedback_inputs,
        processed_ids=processed_feedback_ids,
        receipts=feedback_replay_receipts,
        fingerprint=_feedback_replay_fingerprint,
        label="pheromone feedback",
    )
    reinforcement_result = reinforce_pheromone_trails_with_records(
        list(diffusion_result.trails),
        feedback_inputs,
        pheromone_policy,
        candidate_set=candidate_set,
        target=target,
        processed_feedback_ids=processed_feedback_ids,
        budget_state=budget,
        neighborhood=topology,
    )
    budget = reinforcement_result.budget_state or budget
    post_reinforcement_expiration = evaporate_trails_with_records(
        list(reinforcement_result.trails),
        pheromone_policy,
        current_step=current_step,
    )
    active_trails = tuple(
        sorted(
            post_reinforcement_expiration.trails,
            key=lambda trail: (
                trail.target,
                pheromone_bound_candidate_id(trail),
                pheromone_subject_type(trail),
                pheromone_subject_id(trail),
                trail.kind,
                trail.source_id,
                trail.trace_event_id,
            ),
        )
    )

    observations = observe_pheromone_exploration(
        candidate_set=CandidateSet(active_candidates),
        trails=list(active_trails),
        policy=pheromone_policy,
        current_step=current_step,
        target=target,
    )
    # Phase 2: proposals now affect only declared layer score categories,
    # coverage assessment, conflict resolution, or safe fallback.
    layer_state = evaluate_layer_coordination(
        candidate_set=candidate_set,
        target=target,
        policy=layer_policy,
        proposals=layer_inputs,
        fallback_candidate_id=fallback.id,
        snapshots=list(performance_snapshots or []),
        strategy_biases=strategy_bias_inputs,
    )

    # This is the only scoring call in the reference path.  Layer state is
    # merged only after governance computed it above, never accepted from a
    # caller as authority.
    base_state = score_candidates(
        candidate_set=candidate_set,
        policy=effective_policy,
        scout_reports=scout_inputs,
        target=target,
        recruitment_signals=recruitment_inputs,
        inhibition_signals=inhibition_inputs,
        pheromone_trails=list(active_trails),
    )
    state = merge_governed_layer_coordination(base_state, layer_state)
    decision = _decide_collective_state(
        candidate_set=candidate_set,
        policy=effective_policy,
        target=target,
        state=state,
        fallback_candidate_id=fallback.id,
    )

    events = _hybrid_step_trace_events(
        protocol_id=protocol_id,
        target=target,
        candidate_set=candidate_set,
        policy=effective_policy,
        pheromone_policy=pheromone_policy,
        scout_reports=list(scout_reports),
        recruitment_signals=list(recruitment_signals or []),
        inhibition_signals=list(inhibition_signals or []),
        deposit_inputs=deposit_inputs,
        deposit_result=deposit_result,
        deposit_replay_receipts=deposit_replay_receipts,
        diffusion_replay_receipts=diffusion_replay_receipts,
        feedback_replay_receipts=feedback_replay_receipts,
        adjustment_replay_receipts=adjustment_replay_receipts,
        evaporation_records=evaporation_result.records,
        pre_diffusion_trails=pre_diffusion_trails,
        diffusion_result=diffusion_result,
        feedback=feedback_inputs,
        reinforcement_result=reinforcement_result,
        post_reinforcement_expiration_records=post_reinforcement_expiration.records,
        active_trails=active_trails,
        observations=observations,
        layer_proposals=layer_inputs,
        performance_snapshots=list(performance_snapshots or []),
        strategy_biases=strategy_bias_inputs,
        layer_state=layer_state,
        adjustment_proposals=adjustment_inputs,
        adjustment_batch=adjustment_batch,
        state=state,
        decision=decision,
        current_step=current_step,
    )

    return _issue_hybrid_collective_step(HybridCollectiveStep(
        decision=decision,
        state=state,
        active_trails=active_trails,
        layer_coordination=layer_state,
        adjustment_overlay=adjustment_batch.overlay,
        effective_policy=effective_policy,
        deposit_records=deposit_result.records,
        evaporation_records=(
            *evaporation_result.records,
            *post_reinforcement_expiration.records,
        ),
        diffusion_records=diffusion_result.records,
        reinforcement_records=reinforcement_result.records,
        exploration_observations=observations,
        processed_pheromone_event_ids=processed_pheromone,
        processed_feedback_ids=reinforcement_result.processed_feedback_ids,
        processed_adjustment_ids=adjustment_batch.processed_trace_event_ids,
        deposit_replay_receipts=_extend_replay_receipts(
            deposit_replay_receipts,
            deposit_inputs,
            _trail_replay_fingerprint,
        ),
        diffusion_replay_receipts=dict(
            diffusion_result._processed_event_receipts
        ),
        feedback_replay_receipts=_extend_replay_receipts(
            feedback_replay_receipts,
            feedback_inputs,
            _feedback_replay_fingerprint,
        ),
        adjustment_replay_receipts=_extend_replay_receipts(
            adjustment_replay_receipts,
            adjustment_inputs,
            _adjustment_replay_fingerprint,
        ),
        budget_state=budget,
        trace_events=tuple(events),
    ), protocol_id=protocol_id, target=target)


def _decide_collective_state(
    *,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    target: str,
    state: CollectiveDecisionState,
    fallback_candidate_id: str | None = None,
) -> QuorumDecision:
    validate_score_breakdown(state)
    active_ids = {
        candidate.id
        for candidate in candidate_set.candidates
        if candidate.target == target
    }
    if set(state.scores) != active_ids or set(state.independent_scouts) != active_ids:
        raise GovernanceError("collective decision state must cover exactly the active target candidates")
    for candidate_id, scouts in state.independent_scouts.items():
        if any(not isinstance(scout_id, str) or not scout_id for scout_id in scouts):
            raise GovernanceError(f"collective state contains an invalid scout identity: {candidate_id}")
    if state.layer_coordination is not None and state.layer_coordination.fallback_used:
        fallback = candidate_set.require_declared_for_target(
            resolve_collective_fallback_id(
                candidate_set=candidate_set,
                policy=policy,
                target=target,
                fallback_candidate_id=fallback_candidate_id,
            ),
            target,
        )
        if not fallback.safe_fallback:
            raise GovernanceError(f"collective fallback candidate is not marked safe: {fallback.id}")
        return _issue_quorum_decision(
            target=target,
            candidate_id=fallback.id,
            committed=True,
            reason="safe_layer_coordination_fallback",
        )

    candidates_by_score = sorted(state.scores.items(), key=lambda item: (-item[1], item[0]))
    for candidate_id, score in candidates_by_score:
        scout_count = len(state.independent_scouts[candidate_id])
        if scout_count >= policy.min_independent_scouts and score >= policy.quorum_threshold:
            candidate = candidate_set.require_declared_for_target(candidate_id, target)
            return _issue_quorum_decision(
                target=target,
                candidate_id=candidate.id,
                committed=True,
                reason="collective_consensus",
            )

    fallback = candidate_set.require_declared_for_target(
        resolve_collective_fallback_id(
            candidate_set=candidate_set,
            policy=policy,
            target=target,
            fallback_candidate_id=fallback_candidate_id,
        ),
        target,
    )
    if not fallback.safe_fallback:
        raise GovernanceError(f"collective fallback candidate is not marked safe: {fallback.id}")
    return _issue_quorum_decision(
        target=target,
        candidate_id=fallback.id,
        committed=True,
        reason="safe_collective_fallback",
    )
