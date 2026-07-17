from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.trace import canonical_pheromone_clip_payload
from types import MappingProxyType
from typing import Any
import math
from pheroos.governance._pheromone.invariants import _non_negative_number, _non_negative_step, _trail_clip_payload, clip_pheromone_strength, pheromone_bound_candidate_id, pheromone_processing_key, pheromone_source_id, pheromone_subject_id, pheromone_subject_type, validate_pheromone_policy, validate_pheromone_trail
from pheroos.governance._pheromone.records import PheromoneLifecycleRecord, PheromonePolicy, PheromoneTrail

@dataclass(frozen=True)
class PheromoneBudgetState:
    round_cap: float
    per_source_cap: float
    round_used: float = 0.0
    source_used: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_used", MappingProxyType(dict(self.source_used)))

    def __deepcopy__(self, memo: dict[int, object]) -> PheromoneBudgetState:
        del memo
        return self

    @classmethod
    def for_policy(cls, policy: PheromonePolicy) -> PheromoneBudgetState:
        validate_pheromone_policy(policy)
        return cls(
            round_cap=float(policy.per_round_deposit_cap),
            per_source_cap=float(policy.per_source_cap),
        )

    @property
    def round_remaining(self) -> float:
        return max(0.0, self.round_cap - self.round_used)

    def source_remaining(self, source_id: str) -> float:
        return max(0.0, self.per_source_cap - self.source_used.get(source_id, 0.0))

    def consume(self, source_id: str, requested: float) -> tuple[float, PheromoneBudgetState]:
        amount = _non_negative_number(requested, "pheromone budget request")
        applied = min(amount, self.round_remaining, self.source_remaining(source_id))
        updated_sources = dict(self.source_used)
        updated_sources[source_id] = updated_sources.get(source_id, 0.0) + applied
        return applied, PheromoneBudgetState(
            round_cap=self.round_cap,
            per_source_cap=self.per_source_cap,
            round_used=self.round_used + applied,
            source_used=updated_sources,
        )


@dataclass(frozen=True)
class PheromoneBatchResult:
    trails: tuple[PheromoneTrail, ...] = ()
    records: tuple[PheromoneLifecycleRecord, ...] = ()
    processed_event_ids: frozenset[str] = frozenset()
    budget_state: PheromoneBudgetState | None = None
    replayed_event_ids: tuple[str, ...] = ()
    _processed_event_receipts: tuple[tuple[str, tuple[Any, ...]], ...] = field(
        default=(),
        repr=False,
    )


def validate_pheromone_budget_state(
    budget_state: PheromoneBudgetState,
    policy: PheromonePolicy,
) -> None:
    round_cap = _non_negative_number(budget_state.round_cap, "pheromone budget round_cap")
    source_cap = _non_negative_number(budget_state.per_source_cap, "pheromone budget per_source_cap")
    round_used = _non_negative_number(budget_state.round_used, "pheromone budget round_used")
    if round_cap != float(policy.per_round_deposit_cap) or source_cap != float(policy.per_source_cap):
        raise GovernanceError("pheromone budget state caps do not match active policy")
    if round_used > round_cap:
        raise GovernanceError("pheromone round budget usage exceeds declared cap")
    total_source_usage = 0.0
    for source_id, used in budget_state.source_used.items():
        if not isinstance(source_id, str):
            raise GovernanceError("pheromone budget source identity must be a string")
        amount = _non_negative_number(used, f"pheromone budget source usage {source_id}")
        if amount > source_cap:
            raise GovernanceError("pheromone source budget usage exceeds declared cap")
        total_source_usage += amount
    if not math.isfinite(total_source_usage):
        raise GovernanceError("pheromone source budget usage must remain finite")
    if abs(total_source_usage - round_used) > 1e-9:
        raise GovernanceError("pheromone budget round and source usage do not reconstruct")


def pheromone_budget_for_policy(
    policy: PheromonePolicy,
    budget_state: PheromoneBudgetState | None,
) -> PheromoneBudgetState:
    state = budget_state or PheromoneBudgetState.for_policy(policy)
    validate_pheromone_budget_state(state, policy)
    return state


def deposit_pheromone(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
) -> PheromoneTrail:
    result = deposit_pheromone_trails(
        [trail],
        policy,
        candidate_set=candidate_set,
        target=target,
        budget_state=budget_state,
    )
    if not result.trails:
        raise GovernanceError("pheromone deposit was rejected by the active budget")
    return result.trails[0]


def deposit_pheromone_trails(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
    processed_event_ids: frozenset[str] = frozenset(),
) -> PheromoneBatchResult:
    """Validate and apply a deposit batch atomically.

    Budgets are allocated in canonical priority order, while the returned trails
    retain caller order.  Validation completes for the entire batch before any
    transition record is produced.
    """

    validate_pheromone_policy(policy)
    items = list(trails)
    for trail in items:
        validate_pheromone_trail(
            trail,
            policy,
            candidate_set=candidate_set,
            target=target,
            allow_strength_above_max=True,
            allow_strength_below_min=True,
        )
    _reject_duplicate_trail_events(items, lifecycle="deposit")

    budget = pheromone_budget_for_policy(policy, budget_state)
    already_processed = set(processed_event_ids)
    replayed = tuple(sorted(trail.trace_event_id for trail in items if trail.trace_event_id in already_processed))
    pending = [trail for trail in items if trail.trace_event_id not in already_processed]
    deposited_by_identity: dict[int, PheromoneTrail] = {}
    records: list[PheromoneLifecycleRecord] = []
    indexed = sorted(enumerate(pending), key=lambda item: pheromone_processing_key(item[1], item[0], policy))
    for index, trail in indexed:
        # Preserve the caller's requested strength in lifecycle lineage.  The
        # bounded value is what consumes budget, but pre-clamping the recorded
        # request would hide a real max-strength clip from trace/conformance.
        requested = float(trail.strength)
        budget_request = min(requested, float(policy.max_strength))
        source_id = pheromone_source_id(trail)
        applied, updated_budget = budget.consume(source_id, budget_request)
        if applied < policy.min_strength:
            applied = 0.0
            updated_budget = budget
        budget = updated_budget
        deposited_trail = replace(trail, strength=applied)
        if applied > 0:
            deposited_by_identity[id(trail)] = deposited_trail
        records.append(
            lifecycle_record(
                "deposit" if applied > 0 else "deposit_rejected",
                deposited_trail,
                old_strength=0.0,
                requested_strength=requested,
                applied_strength=applied,
                round_budget_remaining=budget.round_remaining,
                source_budget_remaining=budget.source_remaining(source_id),
                causal_payload=_deposit_clip_causal_payload(trail),
            )
        )
        if trail.trace_event_id:
            already_processed.add(trail.trace_event_id)
    return PheromoneBatchResult(
        trails=tuple(
            deposited_by_identity[id(trail)]
            for trail in pending
            if id(trail) in deposited_by_identity
        ),
        records=tuple(records),
        processed_event_ids=frozenset(already_processed),
        budget_state=budget,
        replayed_event_ids=replayed,
    )


def clip_pheromone_deposit_strength(strength: float, policy: PheromonePolicy) -> float:
    validate_pheromone_policy(policy)
    value = _non_negative_number(strength, "pheromone deposit strength")
    clipped = min(policy.per_round_deposit_cap, policy.per_source_cap, policy.max_strength, value)
    if clipped < policy.min_strength:
        return 0.0
    return clipped


def evaporate_trails(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> list[PheromoneTrail]:
    return list(evaporate_trails_with_records(trails, policy, current_step=current_step).trails)


def evaporate_trails_with_records(
    trails: list[PheromoneTrail],
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> PheromoneBatchResult:
    validate_pheromone_policy(policy)
    if current_step is not None:
        _non_negative_step(current_step, "current_step")
    items = list(trails)
    # Legacy evaporation accepts trails without deposit lineage, but numeric and
    # temporal state is still validated for the entire batch up front.
    relaxed_policy = replace(policy, require_provenance=False, require_trace=False)
    for trail in items:
        validate_pheromone_trail(trail, relaxed_policy)
        if current_step is not None and current_step < trail.updated_at_step:
            raise GovernanceError("current_step must not precede pheromone updated step")
    if not policy.enabled:
        return PheromoneBatchResult(trails=tuple(items))
    active: list[PheromoneTrail] = []
    records: list[PheromoneLifecycleRecord] = []
    for trail in items:
        updated = evaporate_trail(trail, policy, current_step=current_step)
        active.append(updated)
        if updated == trail:
            continue
        action = "expire" if updated.kind == "stale" and trail.kind != "stale" else "evaporate"
        elapsed_steps = updated.updated_at_step - trail.updated_at_step
        records.append(
            lifecycle_record(
                action,
                updated,
                old_strength=float(trail.strength),
                requested_strength=float(trail.strength),
                applied_strength=float(updated.strength) - float(trail.strength),
                source_kind=trail.kind,
                elapsed_steps=elapsed_steps,
                ttl_steps=(
                    trail.ttl_steps
                    if trail.ttl_steps is not None
                    else (
                        policy.kind_profiles[trail.kind].ttl_steps
                        if trail.kind in policy.kind_profiles
                        else None
                    )
                ),
            )
        )
    return PheromoneBatchResult(
        trails=tuple(active),
        records=tuple(records),
        processed_event_ids=frozenset(trail.trace_event_id for trail in active if trail.trace_event_id),
    )


def evaporate_trail(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    current_step: int | None = None,
) -> PheromoneTrail:
    validate_pheromone_policy(policy)
    relaxed_policy = replace(policy, require_provenance=False, require_trace=False)
    validate_pheromone_trail(trail, relaxed_policy)
    step = trail.updated_at_step + 1 if current_step is None else current_step
    _non_negative_step(step, "current_step")
    if step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    active_policy = pheromone_policy_for_trail(trail, policy)
    if is_expired_with_policy(trail, active_policy, step):
        return replace(trail, kind="stale", strength=policy.min_strength, updated_at_step=step)

    elapsed_steps = step - trail.updated_at_step
    if elapsed_steps == 0:
        return trail
    retained = retained_pheromone_strength(trail.strength, active_policy, elapsed_steps)
    if trail.kind == "novelty" and policy.exploration_enabled:
        retained *= (1.0 - policy.novelty_decay_rate) ** elapsed_steps
        if not math.isfinite(retained):
            raise GovernanceError("novelty pheromone decay must remain finite")
    return replace(
        trail,
        strength=clip_pheromone_strength(retained, policy),
        updated_at_step=step,
    )


def retained_pheromone_strength(strength: float, policy: PheromonePolicy, elapsed_steps: int) -> float:
    validate_pheromone_policy(policy)
    value = _non_negative_number(strength, "pheromone strength")
    _non_negative_step(elapsed_steps, "elapsed_steps")
    retention = max(0.0, min(1.0, 1.0 - policy.evaporation_rate))
    if policy.decay_model == "exponential":
        retained = value * (retention ** elapsed_steps)
    elif policy.decay_model == "step":
        retained = value * retention if elapsed_steps > 0 else value
    else:
        retained = value * max(0.0, 1.0 - policy.evaporation_rate * elapsed_steps)
    if not math.isfinite(retained):
        raise GovernanceError("retained pheromone strength must be finite")
    return retained


def is_expired(trail: PheromoneTrail, current_step: int) -> bool:
    _non_negative_step(current_step, "current_step")
    if current_step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    return trail.ttl_steps is not None and current_step - trail.deposited_at_step >= trail.ttl_steps


def is_expired_with_policy(trail: PheromoneTrail, policy: PheromonePolicy, current_step: int) -> bool:
    _non_negative_step(current_step, "current_step")
    if current_step < trail.updated_at_step:
        raise GovernanceError("current_step must not precede pheromone updated step")
    ttl_steps = trail.ttl_steps
    profile = policy.kind_profiles.get(trail.kind)
    if ttl_steps is None and profile is not None:
        ttl_steps = profile.ttl_steps
    return ttl_steps is not None and current_step - trail.deposited_at_step >= ttl_steps


def pheromone_policy_for_trail(trail: PheromoneTrail, policy: PheromonePolicy) -> PheromonePolicy:
    profile = policy.kind_profiles.get(trail.kind)
    if profile is None or profile.evaporation_rate is None:
        return policy
    return replace(policy, evaporation_rate=profile.evaporation_rate)


def _reject_duplicate_trail_events(trails: list[PheromoneTrail], *, lifecycle: str) -> None:
    seen_trace_ids: set[str] = set()
    seen_records: set[tuple[object, ...]] = set()
    for trail in trails:
        if trail.trace_event_id:
            if trail.trace_event_id in seen_trace_ids:
                raise GovernanceError(f"duplicate pheromone {lifecycle} trace_event_id: {trail.trace_event_id}")
            seen_trace_ids.add(trail.trace_event_id)
        identity = (
            trail.target,
            pheromone_bound_candidate_id(trail),
            pheromone_subject_type(trail),
            pheromone_subject_id(trail),
            trail.kind,
            pheromone_source_id(trail),
            trail.deposited_at_step,
            trail.updated_at_step,
        )
        if identity in seen_records:
            raise GovernanceError(f"duplicate equivalent pheromone {lifecycle} record")
        seen_records.add(identity)


def _deposit_clip_causal_payload(trail: PheromoneTrail) -> dict[str, Any]:
    return {
        "lifecycle": "deposit",
        "input": _trail_clip_payload(trail),
        "effective": {
            "target": trail.target,
            "candidate_id": pheromone_bound_candidate_id(trail),
            "subject_type": pheromone_subject_type(trail),
            "subject_id": pheromone_subject_id(trail),
            "source_id": pheromone_source_id(trail),
        },
    }


def lifecycle_record(
    action: str,
    trail: PheromoneTrail,
    *,
    old_strength: float,
    requested_strength: float,
    applied_strength: float,
    source_kind: str | None = None,
    source_trace_event_id: str | None = None,
    round_budget_remaining: float | None = None,
    source_budget_remaining: float | None = None,
    hop: int = 0,
    attenuation: float = 1.0,
    policy_attenuation: float = 1.0,
    edge_attenuation: float = 1.0,
    elapsed_steps: int = 0,
    cause_trace_event_id: str = "",
    ttl_steps: int | None = None,
    causal_payload: Mapping[str, Any] | None = None,
) -> PheromoneLifecycleRecord:
    return PheromoneLifecycleRecord(
        action=action,
        target=trail.target,
        candidate_id=pheromone_bound_candidate_id(trail),
        subject_type=pheromone_subject_type(trail),
        subject_id=pheromone_subject_id(trail),
        kind=trail.kind,
        source_kind=source_kind or trail.kind,
        source_id=pheromone_source_id(trail),
        provenance=trail.provenance,
        source_trace_event_id=source_trace_event_id or trail.trace_event_id,
        trace_event_id=trail.trace_event_id,
        old_strength=old_strength,
        new_strength=float(trail.strength),
        requested_strength=requested_strength,
        applied_strength=applied_strength,
        round_budget_remaining=round_budget_remaining,
        source_budget_remaining=source_budget_remaining,
        hop=hop,
        attenuation=attenuation,
        policy_attenuation=policy_attenuation,
        edge_attenuation=edge_attenuation,
        step=trail.updated_at_step,
        elapsed_steps=elapsed_steps,
        cause_trace_event_id=cause_trace_event_id,
        deposited_at_step=trail.deposited_at_step,
        ttl_steps=trail.ttl_steps if ttl_steps is None else ttl_steps,
        _causal_payload_json=(
            canonical_pheromone_clip_payload(causal_payload)
            if causal_payload is not None
            else ""
        ),
    )


for _compat_function in (validate_pheromone_budget_state, pheromone_budget_for_policy, deposit_pheromone, deposit_pheromone_trails, clip_pheromone_deposit_strength, evaporate_trails, evaporate_trails_with_records, evaporate_trail, retained_pheromone_strength, is_expired, is_expired_with_policy, pheromone_policy_for_trail, _reject_duplicate_trail_events, _deposit_clip_causal_payload, lifecycle_record,):
    _compat_function.__module__ = 'pheroos.governance.pheromone'
del _compat_function
for _compat_type in (PheromoneBudgetState, PheromoneBatchResult,):
    _compat_type.__module__ = 'pheroos.governance.pheromone'
    for _compat_descriptor in _compat_type.__dict__.values():
        if isinstance(_compat_descriptor, (staticmethod, classmethod)):
            _compat_member = _compat_descriptor.__func__
        else:
            _compat_member = _compat_descriptor
        if callable(_compat_member) and hasattr(_compat_member, '__module__'):
            _compat_member.__module__ = 'pheroos.governance.pheromone'
del _compat_descriptor, _compat_member, _compat_type

__all__ = ('PheromoneBatchResult', 'PheromoneBudgetState', '_deposit_clip_causal_payload', '_reject_duplicate_trail_events', 'clip_pheromone_deposit_strength', 'deposit_pheromone', 'deposit_pheromone_trails', 'evaporate_trail', 'evaporate_trails', 'evaporate_trails_with_records', 'is_expired', 'is_expired_with_policy', 'lifecycle_record', 'pheromone_budget_for_policy', 'pheromone_policy_for_trail', 'retained_pheromone_strength', 'validate_pheromone_budget_state')
