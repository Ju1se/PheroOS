from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from enum import Enum
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import LayerCoordinationState
from pheroos.governance.layer_coordination import LayerProposal
from pheroos.governance.layer_coordination import StrategyBias
from pheroos.governance._pheromone.lifecycle import PheromoneBudgetState
from pheroos.governance._pheromone.records import (
    PheromoneExplorationObservation,
    PheromoneLifecycleRecord,
    PheromoneTrail,
)
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal
from pheroos.governance.policy_adjustment import RunScopedPolicyOverlay
from pheroos.governance.policy_adjustment import (
    run_scoped_policy_overlay_is_authoritative,
)
from pheroos.governance.quorum import quorum_decision_is_authoritative
from pheroos.protocol.models import CollectiveDecisionPolicy
from pheroos.trace import TraceEvent
from typing import Any
from pheroos.governance._swarm.records import (
    CollectiveDecisionState,
    HybridCollectiveStep,
    HybridReplayState,
    _HYBRID_REPLAY_STATE_ISSUANCE,
    _HYBRID_STEP_ISSUANCE,
)
from pheroos.governance._swarm.signals import (
    InhibitionSignal,
    RecruitmentSignal,
    ScoutReport,
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


def _hybrid_authority_snapshot(
    record: HybridCollectiveStep | HybridReplayState,
) -> tuple[tuple[str, Any], ...]:
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
        and all(
            type(trail) is PheromoneTrail and trail.target == target
            for trail in step.active_trails
        )
        and all(
            type(record) is PheromoneLifecycleRecord and record.target == target
            for record in lifecycle_records
        )
        and all(
            type(observation) is PheromoneExplorationObservation
            and observation.target == target
            for observation in step.exploration_observations
        )
        and (
            step.budget_state is None or type(step.budget_state) is PheromoneBudgetState
        )
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
    return _replay_state_from_verified_hybrid_step(step)


def _replay_state_from_verified_hybrid_step(
    step: HybridCollectiveStep,
) -> HybridReplayState:
    """Materialize replay state after the caller verified the source step.

    This private path only removes a second, immediately repeated authority
    traversal.  The public ABI above remains fail-closed for every caller.
    """

    issuance = step._issuance
    if not (
        isinstance(issuance, tuple)
        and len(issuance) == 4
        and isinstance(issuance[1], str)
        and isinstance(issuance[2], str)
    ):
        raise GovernanceError("hybrid collective step issuance is malformed")
    protocol_id = issuance[1]
    target = issuance[2]
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
    return _issue_hybrid_replay_state(
        state,
        protocol_id=protocol_id,
        target=target,
    )


def _issue_hybrid_replay_state(
    state: HybridReplayState,
    *,
    protocol_id: str,
    target: str,
) -> HybridReplayState:
    """Issue validated ephemeral replay memory with the existing v1 token.

    Hybrid Replay v2 calls this only after StateStore currentness has been
    verified and its portable snapshot has been reconstructed exactly.  The
    helper deliberately reuses ``_HYBRID_REPLAY_STATE_ISSUANCE``: restart
    compatibility must not create a second registry, cursor, or sentinel.
    """

    if type(state) is not HybridReplayState or not _hybrid_replay_state_bindings_match(
        state,
        protocol_id=protocol_id,
        target=target,
    ):
        raise GovernanceError("hybrid replay state authority bindings are invalid")
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


def _hybrid_replay_state_bindings_match(
    state: object,
    *,
    protocol_id: str,
    target: str,
) -> bool:
    return bool(
        type(state) is HybridReplayState
        and is_nonblank_string(protocol_id)
        and is_nonblank_string(target)
        and state.protocol_id == protocol_id
        and state.target == target
        and all(
            type(trail) is PheromoneTrail and trail.target == target
            for trail in state.active_trails
        )
        and _replay_receipts_match_processed_ids(state)
    )


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
            and issuance[3] == _hybrid_authority_snapshot(state)
            and _hybrid_replay_state_bindings_match(
                state,
                protocol_id=issuance[1],
                target=issuance[2],
            )
        )
    except Exception:
        # Replay memory is an authority input, so corruption is a denial rather
        # than a best-effort attempt to continue with caller-controlled state.
        return False


def _replay_receipts_match_processed_ids(
    state: HybridCollectiveStep | HybridReplayState,
) -> bool:
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
        sum(len(trace_ids) for trace_ids in receipt_id_sets) == len(all_receipt_ids)
        and (set(state.deposit_replay_receipts) | set(state.diffusion_replay_receipts))
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
        return tuple(
            sorted((_canonical_replay_value(item) for item in value), key=repr)
        )
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
    for recruitment in recruitment_signals:
        register(recruitment.trace_event_id, "recruitment")
        register(
            getattr(recruitment.verification, "trace_event_id", ""),
            "recruitment_verification",
        )
    for inhibition in inhibition_signals:
        register(inhibition.trace_event_id, "inhibition")
        register(
            getattr(inhibition.verification, "trace_event_id", ""),
            "inhibition_verification",
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
    for adjustment in adjustment_proposals:
        register(adjustment.trace_event_id, "adjustment")

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
            f"duplicate hybrid trace_event_id across input surfaces: {duplicate_inputs}"
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


for _compat_function in (
    _canonical_authority_value,
    _hybrid_authority_snapshot,
    _hybrid_step_bindings_match,
    _issue_hybrid_collective_step,
    hybrid_collective_step_is_authoritative,
    replay_state_from_hybrid_step,
    hybrid_replay_state_is_authoritative,
    _replay_receipts_match_processed_ids,
    _canonical_replay_value,
    _trail_replay_fingerprint,
    _feedback_replay_fingerprint,
    _adjustment_replay_fingerprint,
    _validate_replay_receipts,
    _extend_replay_receipts,
    _validate_complete_hybrid_trace_identity,
):
    _compat_function.__module__ = "pheroos.governance.collective"
del _compat_function

__all__ = (
    "_adjustment_replay_fingerprint",
    "_canonical_authority_value",
    "_canonical_replay_value",
    "_extend_replay_receipts",
    "_feedback_replay_fingerprint",
    "_hybrid_authority_snapshot",
    "_hybrid_step_bindings_match",
    "_issue_hybrid_collective_step",
    "_replay_receipts_match_processed_ids",
    "_trail_replay_fingerprint",
    "_validate_complete_hybrid_trace_identity",
    "_validate_replay_receipts",
    "hybrid_collective_step_is_authoritative",
    "hybrid_replay_state_is_authoritative",
    "replay_state_from_hybrid_step",
)
