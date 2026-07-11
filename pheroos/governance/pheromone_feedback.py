from __future__ import annotations

from dataclasses import dataclass, replace

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.pheromone import (
    SUPPORTED_PHEROMONE_SUBJECT_TYPES,
    PheromoneBudgetState,
    PheromoneLifecycleRecord,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneTrail,
    _finite_number,
    _non_negative_number,
    _non_negative_step,
    is_extension_pheromone_value,
    lifecycle_record,
    pheromone_bound_candidate_id,
    pheromone_budget_for_policy,
    pheromone_kind_priority,
    pheromone_source_id,
    pheromone_subject_id,
    pheromone_subject_type,
    scoreable_pheromone_candidate_id,
    validate_pheromone_policy,
    validate_pheromone_subject_binding,
    validate_pheromone_topology,
    validate_pheromone_trail,
)


SUPPORTED_PHEROMONE_FEEDBACK_OUTCOMES = frozenset(
    {"success", "failure", "blocked", "congested", "hazard", "novel", "stale"}
)


@dataclass(frozen=True)
class PheromoneFeedback:
    source_id: str
    subject_type: str
    subject_id: str
    candidate_id: str
    target: str
    outcome: str
    reward: float = 0.0
    strength_delta: float = 0.0
    evidence_id: str = ""
    provenance: str = ""
    trace_event_id: str = ""
    step: int = 0


@dataclass(frozen=True)
class PheromoneReinforcementResult:
    trails: tuple[PheromoneTrail, ...] = ()
    records: tuple[PheromoneLifecycleRecord, ...] = ()
    processed_feedback_ids: frozenset[str] = frozenset()
    budget_state: PheromoneBudgetState | None = None
    replayed_feedback_ids: tuple[str, ...] = ()


def _feedback_clip_causal_payload(
    feedback: PheromoneFeedback,
    *,
    source_trace_event_id: str,
    source_strength: float,
    source_kind: str,
    source_provenance: str,
) -> dict[str, object]:
    """Snapshot every feedback input plus the memory state it attempted to mutate."""

    return {
        "lifecycle": "feedback",
        "input": {
            "source_id": feedback.source_id,
            "subject_type": feedback.subject_type,
            "subject_id": feedback.subject_id,
            "candidate_id": feedback.candidate_id,
            "target": feedback.target,
            "outcome": feedback.outcome,
            "reward": float(feedback.reward),
            "strength_delta": float(feedback.strength_delta),
            "evidence_id": feedback.evidence_id,
            "provenance": feedback.provenance,
            "trace_event_id": feedback.trace_event_id,
            "step": feedback.step,
        },
        "source_state": {
            "trace_event_id": source_trace_event_id,
            "strength": float(source_strength),
            "kind": source_kind,
            "provenance": source_provenance,
        },
    }


def validate_pheromone_feedback(
    feedback: PheromoneFeedback,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    neighborhood: PheromoneNeighborhood | None = None,
) -> None:
    validate_pheromone_policy(policy)
    for field_name in (
        "source_id",
        "subject_type",
        "subject_id",
        "candidate_id",
        "target",
        "outcome",
        "evidence_id",
        "provenance",
        "trace_event_id",
    ):
        if not isinstance(getattr(feedback, field_name), str):
            raise GovernanceError(f"pheromone feedback {field_name} must be a string")
    if feedback.outcome not in SUPPORTED_PHEROMONE_FEEDBACK_OUTCOMES:
        raise GovernanceError(f"unsupported pheromone feedback outcome: {feedback.outcome}")
    if not is_nonblank_string(feedback.source_id):
        raise GovernanceError("pheromone feedback source_id is required")
    if feedback.subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES and not is_extension_pheromone_value(feedback.subject_type):
        raise GovernanceError(f"unsupported pheromone feedback subject type: {feedback.subject_type}")
    if not is_nonblank_string(feedback.subject_id):
        raise GovernanceError("pheromone feedback subject_id is required")
    if not is_nonblank_string(feedback.target):
        raise GovernanceError("pheromone feedback target is required")
    if target is not None and feedback.target != target:
        raise GovernanceError(f"pheromone feedback targets {feedback.target}, not active target {target}")
    if not is_nonblank_string(feedback.candidate_id):
        raise GovernanceError("pheromone feedback must declare candidate_id")
    for field_name in ("evidence_id", "provenance", "trace_event_id"):
        value = getattr(feedback, field_name)
        if value and not is_nonblank_string(value):
            raise GovernanceError(
                f"pheromone feedback {field_name} must be empty or a non-blank string"
            )
    if feedback.subject_type == "candidate":
        if feedback.subject_id != feedback.candidate_id:
            raise GovernanceError("candidate pheromone feedback subject_id must match candidate_id")
    if feedback.candidate_id and candidate_set is not None:
        candidate_set.require_declared_for_target(feedback.candidate_id, feedback.target)
    if neighborhood is not None:
        validate_pheromone_topology(
            neighborhood,
            candidate_set=candidate_set,
            target=target,
        )
        validate_pheromone_subject_binding(
            neighborhood,
            subject_type=feedback.subject_type,
            subject_id=feedback.subject_id,
            candidate_id=feedback.candidate_id,
            require_declared=True,
        )
    if policy.require_provenance and not is_nonblank_string(feedback.provenance):
        raise GovernanceError("pheromone feedback is missing provenance")
    if policy.require_trace and not is_nonblank_string(feedback.trace_event_id):
        raise GovernanceError("pheromone feedback is missing trace event id")
    _finite_number(feedback.reward, "pheromone feedback reward")
    _non_negative_number(feedback.strength_delta, "pheromone feedback strength_delta")
    _non_negative_step(feedback.step, "pheromone feedback step")


def reinforce_pheromone_trails(
    trails: list[PheromoneTrail],
    feedback: list[PheromoneFeedback],
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    processed_feedback_ids: frozenset[str] = frozenset(),
    budget_state: PheromoneBudgetState | None = None,
    neighborhood: PheromoneNeighborhood | None = None,
) -> list[PheromoneTrail]:
    return list(
        reinforce_pheromone_trails_with_records(
            trails,
            feedback,
            policy,
            candidate_set=candidate_set,
            target=target,
            processed_feedback_ids=processed_feedback_ids,
            budget_state=budget_state,
            neighborhood=neighborhood,
        ).trails
    )


def reinforce_pheromone_trails_with_records(
    trails: list[PheromoneTrail],
    feedback: list[PheromoneFeedback],
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    processed_feedback_ids: frozenset[str] = frozenset(),
    budget_state: PheromoneBudgetState | None = None,
    neighborhood: PheromoneNeighborhood | None = None,
) -> PheromoneReinforcementResult:
    """Validate and reinforce an entire feedback batch atomically.

    Round and source budgets are shared by the whole batch.  Canonical kind
    priority prevents lower-priority feedback from consuming an emergency
    budget first. Only explicitly processed feedback ids are idempotent no-ops;
    caller-provided trail ancestry is lineage, not replay authority.
    """

    validate_pheromone_policy(policy)
    existing = list(trails)
    if neighborhood is not None:
        validate_pheromone_topology(
            neighborhood,
            candidate_set=candidate_set,
            target=target,
        )
    for trail in existing:
        validate_pheromone_trail(trail, policy, candidate_set=candidate_set, target=target)
        if neighborhood is not None:
            validate_pheromone_subject_binding(
                neighborhood,
                subject_type=pheromone_subject_type(trail),
                subject_id=pheromone_subject_id(trail),
                candidate_id=pheromone_bound_candidate_id(trail),
                require_declared=bool(scoreable_pheromone_candidate_id(trail, policy)),
            )
    items = list(feedback)
    for item in items:
        validate_pheromone_feedback(
            item,
            policy,
            candidate_set=candidate_set,
            target=target,
            neighborhood=neighborhood,
        )
    _reject_duplicate_feedback(items)
    if any(not is_nonblank_string(item) for item in processed_feedback_ids):
        raise GovernanceError("processed pheromone feedback ids must be non-blank strings")
    budget = pheromone_budget_for_policy(policy, budget_state)
    if not policy.feedback_enabled:
        return PheromoneReinforcementResult(trails=tuple(existing), budget_state=budget)

    known_lineage_ids = set(processed_feedback_ids)
    replayed_feedback_ids = tuple(
        sorted(item.trace_event_id for item in items if item.trace_event_id in known_lineage_ids)
    )
    pending = [item for item in items if item.trace_event_id not in known_lineage_ids]
    processed = set(processed_feedback_ids)
    processed.update(replayed_feedback_ids)
    ordered = sorted(pending, key=lambda item: feedback_processing_key(item, policy))
    reinforced = list(existing)
    records: list[PheromoneLifecycleRecord] = []

    for item in ordered:
        kind = pheromone_kind_for_feedback(item)
        if kind == "stale":
            changed, stale_records = stale_matching_trails_with_records(reinforced, item, policy)
            reinforced = changed
            records.extend(
                replace(
                    record,
                    round_budget_remaining=budget.round_remaining,
                    source_budget_remaining=budget.source_remaining(item.source_id),
                )
                for record in stale_records
            )
            processed.add(item.trace_event_id)
            continue

        requested = abs(float(item.strength_delta or item.reward))
        index = find_matching_trail_index(reinforced, item, kind)
        current_strength = float(reinforced[index].strength) if index is not None else 0.0
        if index is not None and item.step < reinforced[index].updated_at_step:
            raise GovernanceError("pheromone feedback step must not precede matching trail update")
        source_trace_event_id = (
            reinforced[index].trace_event_id if index is not None else item.trace_event_id
        )
        headroom = max(0.0, float(policy.max_strength) - current_strength)
        applied, updated_budget = budget.consume(item.source_id, min(requested, headroom))
        if index is None and applied < policy.min_strength:
            applied = 0.0
            updated_budget = budget
        budget = updated_budget
        processed.add(item.trace_event_id)
        if applied <= 0:
            if index is None:
                rejected = PheromoneTrail(
                    candidate_id=item.candidate_id,
                    strength=0.0,
                    subject_type=item.subject_type,
                    subject_id=item.subject_id,
                    target=item.target,
                    kind=kind,
                    source_id=item.source_id,
                    evidence_id=item.evidence_id,
                    provenance=item.provenance,
                    trace_event_id=item.trace_event_id,
                    deposited_at_step=item.step,
                    updated_at_step=item.step,
                )
            else:
                rejected = replace(reinforced[index], trace_event_id=item.trace_event_id)
            record = lifecycle_record(
                "reinforce_rejected",
                rejected,
                old_strength=current_strength,
                requested_strength=requested,
                applied_strength=0.0,
                source_trace_event_id=source_trace_event_id,
                round_budget_remaining=budget.round_remaining,
                source_budget_remaining=budget.source_remaining(item.source_id),
                cause_trace_event_id=item.trace_event_id,
                causal_payload=_feedback_clip_causal_payload(
                    item,
                    source_trace_event_id=source_trace_event_id,
                    source_strength=current_strength,
                    source_kind=rejected.kind,
                    source_provenance=rejected.provenance,
                ),
            )
            records.append(replace(record, outcome=item.outcome, reward=float(item.reward)))
            continue

        if index is None:
            profile = policy.kind_profiles.get(kind)
            updated = PheromoneTrail(
                candidate_id=item.candidate_id,
                strength=applied,
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                target=item.target,
                kind=kind,
                source_id=item.source_id,
                evidence_id=item.evidence_id,
                provenance=item.provenance,
                trace_event_id=item.trace_event_id,
                deposited_at_step=item.step,
                updated_at_step=item.step,
                ttl_steps=profile.ttl_steps if profile is not None else None,
                lineage_event_ids=(item.trace_event_id,),
            )
            validate_pheromone_trail(updated, policy, candidate_set=candidate_set, target=target)
            reinforced.append(updated)
        else:
            current = reinforced[index]
            updated = replace(
                current,
                strength=current_strength + applied,
                updated_at_step=item.step,
                evidence_id=item.evidence_id or current.evidence_id,
                trace_event_id=item.trace_event_id,
                provenance=item.provenance or current.provenance,
                lineage_event_ids=tuple(
                    dict.fromkeys((*current.lineage_event_ids, item.trace_event_id))
                ),
            )
            validate_pheromone_trail(updated, policy, candidate_set=candidate_set, target=target)
            reinforced[index] = updated
        record = lifecycle_record(
            "reinforce",
            updated,
            old_strength=current_strength,
            requested_strength=requested,
            applied_strength=applied,
            source_trace_event_id=source_trace_event_id,
            round_budget_remaining=budget.round_remaining,
            source_budget_remaining=budget.source_remaining(item.source_id),
            cause_trace_event_id=item.trace_event_id,
        )
        records.append(replace(record, outcome=item.outcome, reward=float(item.reward)))

    return PheromoneReinforcementResult(
        trails=tuple(reinforced),
        records=tuple(records),
        processed_feedback_ids=frozenset(processed),
        budget_state=budget,
        replayed_feedback_ids=replayed_feedback_ids,
    )


def pheromone_kind_for_feedback(feedback: PheromoneFeedback) -> str:
    if feedback.outcome == "success":
        return "positive"
    if feedback.outcome == "failure":
        return "negative"
    if feedback.outcome in {"blocked", "congested"}:
        return "cautionary"
    if feedback.outcome == "hazard":
        return "alarm"
    if feedback.outcome == "novel":
        return "novelty"
    return "stale"


def find_matching_trail_index(trails: list[PheromoneTrail], feedback: PheromoneFeedback, kind: str) -> int | None:
    for index, trail in enumerate(trails):
        if (
            trail.kind == kind
            and pheromone_subject_type(trail) == feedback.subject_type
            and pheromone_subject_id(trail) == feedback.subject_id
            and pheromone_bound_candidate_id(trail) == feedback.candidate_id
            and trail.target == feedback.target
            and pheromone_source_id(trail) == feedback.source_id
        ):
            return index
    return None


def stale_matching_trails(
    trails: list[PheromoneTrail],
    feedback: PheromoneFeedback,
    policy: PheromonePolicy,
) -> list[PheromoneTrail]:
    return stale_matching_trails_with_records(trails, feedback, policy)[0]


def stale_matching_trails_with_records(
    trails: list[PheromoneTrail],
    feedback: PheromoneFeedback,
    policy: PheromonePolicy,
) -> tuple[list[PheromoneTrail], list[PheromoneLifecycleRecord]]:
    changed: list[PheromoneTrail] = []
    records: list[PheromoneLifecycleRecord] = []
    matching = [
        trail
        for trail in trails
        if (
            pheromone_subject_type(trail) == feedback.subject_type
            and pheromone_subject_id(trail) == feedback.subject_id
            and pheromone_bound_candidate_id(trail) == feedback.candidate_id
            and trail.target == feedback.target
            and pheromone_source_id(trail) == feedback.source_id
        )
    ]
    for trail in trails:
        matches = (
            pheromone_subject_type(trail) == feedback.subject_type
            and pheromone_subject_id(trail) == feedback.subject_id
            and pheromone_bound_candidate_id(trail) == feedback.candidate_id
            and trail.target == feedback.target
            and pheromone_source_id(trail) == feedback.source_id
        )
        if not matches:
            changed.append(trail)
            continue
        if feedback.step < trail.updated_at_step:
            raise GovernanceError("pheromone feedback step must not precede matching trail update")
        mutation_trace_event_id = feedback.trace_event_id
        if len(matching) > 1:
            # One stale outcome can invalidate several kind-specific memories.
            # Keep the feedback id in every trail's lineage as the replay key,
            # while issuing one deterministic state-transition id per mutated
            # trail so active-memory identities remain unique.
            mutation_trace_event_id = (
                f"{feedback.trace_event_id}:stale:{trail.kind}:{trail.trace_event_id}"
            )
        updated = replace(
            trail,
            kind="stale",
            strength=policy.min_strength,
            updated_at_step=feedback.step,
            evidence_id=feedback.evidence_id or trail.evidence_id,
            provenance=feedback.provenance or trail.provenance,
            trace_event_id=mutation_trace_event_id,
            lineage_event_ids=tuple(
                dict.fromkeys((*trail.lineage_event_ids, feedback.trace_event_id))
            ),
        )
        changed.append(updated)
        record = lifecycle_record(
            "reinforce_stale",
            updated,
            old_strength=float(trail.strength),
            requested_strength=0.0,
            applied_strength=float(updated.strength) - float(trail.strength),
            source_trace_event_id=trail.trace_event_id,
            source_kind=trail.kind,
            cause_trace_event_id=feedback.trace_event_id,
        )
        records.append(replace(record, outcome=feedback.outcome, reward=float(feedback.reward)))
    return changed, records


def feedback_processing_key(feedback: PheromoneFeedback, policy: PheromonePolicy) -> tuple[object, ...]:
    kind = pheromone_kind_for_feedback(feedback)
    synthetic = PheromoneTrail(
        candidate_id=feedback.candidate_id,
        strength=0.0,
        subject_type=feedback.subject_type,
        subject_id=feedback.subject_id,
        target=feedback.target,
        kind=kind,
        source_id=feedback.source_id,
        trace_event_id=feedback.trace_event_id,
    )
    return (
        -pheromone_kind_priority(synthetic, policy),
        feedback.target,
        feedback.candidate_id,
        feedback.subject_type,
        feedback.subject_id,
        feedback.source_id,
        kind,
        feedback.step,
        feedback.trace_event_id,
    )


def _reject_duplicate_feedback(feedback: list[PheromoneFeedback]) -> None:
    trace_ids: set[str] = set()
    identities: set[tuple[object, ...]] = set()
    for item in feedback:
        if item.trace_event_id in trace_ids:
            raise GovernanceError(f"duplicate pheromone feedback trace_event_id: {item.trace_event_id}")
        trace_ids.add(item.trace_event_id)
        identity = (
            item.source_id,
            item.target,
            item.subject_type,
            item.subject_id,
            item.candidate_id,
            item.outcome,
            item.step,
        )
        if identity in identities:
            raise GovernanceError("duplicate equivalent pheromone feedback record")
        identities.add(identity)
