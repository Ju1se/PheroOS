from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import replace
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.trace import canonical_pheromone_clip_payload
from typing import Any
import math
from pheroos.governance._pheromone.invariants import (
    _trail_clip_payload,
    pheromone_bound_candidate_id,
    pheromone_processing_key,
    pheromone_source_id,
    pheromone_subject_id,
    pheromone_subject_type,
    scoreable_pheromone_candidate_id,
    subject_key,
    topology_subject_candidate_id,
    topology_subject_target,
    validate_pheromone_diffusion_policy,
    validate_pheromone_policy,
    validate_pheromone_subject_binding,
    validate_pheromone_topology,
    validate_pheromone_trail,
)
from pheroos.governance._pheromone.lifecycle import (
    PheromoneBatchResult,
    PheromoneBudgetState,
    _reject_duplicate_trail_events,
    lifecycle_record,
    pheromone_budget_for_policy,
)
from pheroos.governance._pheromone.records import (
    PheromoneDiffusionPolicy,
    PheromoneEdge,
    PheromoneLifecycleRecord,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneSubject,
    PheromoneTrail,
)


def _diffusion_clip_causal_payload(
    *,
    source_trail: PheromoneTrail,
    target_subject: PheromoneSubject,
    edge: PheromoneEdge,
    policy_attenuation: float,
    hop: int,
    parent_trace_event_id: str,
    derived_trace_event_id: str,
    effective_target: str,
    effective_candidate_id: str,
    source_strength: float,
) -> dict[str, Any]:
    return {
        "lifecycle": "diffusion",
        "input": {
            "source_trail": _trail_clip_payload(source_trail),
            "target_subject": {
                "subject_type": target_subject.subject_type,
                "subject_id": target_subject.subject_id,
                "candidate_id": target_subject.candidate_id,
                "target": target_subject.target,
            },
            "edge": {
                "source_subject_type": edge.source_subject_type,
                "source_subject_id": edge.source_subject_id,
                "target_subject_type": edge.target_subject_type,
                "target_subject_id": edge.target_subject_id,
                "attenuation": float(edge.attenuation),
            },
            "policy_attenuation": float(policy_attenuation),
            "hop": hop,
            "parent_trace_event_id": parent_trace_event_id,
            "derived_trace_event_id": derived_trace_event_id,
        },
        "effective": {
            "target": effective_target,
            "candidate_id": effective_candidate_id,
            "subject_type": target_subject.subject_type,
            "subject_id": target_subject.subject_id,
            "source_id": pheromone_source_id(source_trail),
            "source_kind": source_trail.kind,
            "source_strength": float(source_strength),
            "root_trace_event_id": (
                source_trail.diffusion_root_trace_event_id
                or source_trail.trace_event_id
            ),
        },
    }


def _diffusion_replay_fingerprint(
    causal_payload: Mapping[str, Any],
) -> tuple[Any, ...]:
    return (
        "diffusion-v1",
        canonical_pheromone_clip_payload(causal_payload),
    )


def diffuse_pheromone_trails(
    trails: list[PheromoneTrail],
    neighborhood: PheromoneNeighborhood,
    policy: PheromonePolicy,
    diffusion_policy: PheromoneDiffusionPolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
    processed_event_ids: frozenset[str] = frozenset(),
    processed_event_receipts: Mapping[str, tuple[Any, ...]] | None = None,
) -> list[PheromoneTrail]:
    return list(
        diffuse_pheromone_trails_with_records(
            trails,
            neighborhood,
            policy,
            diffusion_policy,
            candidate_set=candidate_set,
            target=target,
            budget_state=budget_state,
            processed_event_ids=processed_event_ids,
            processed_event_receipts=processed_event_receipts,
        ).trails
    )


def diffuse_pheromone_trails_with_records(
    trails: list[PheromoneTrail],
    neighborhood: PheromoneNeighborhood,
    policy: PheromonePolicy,
    diffusion_policy: PheromoneDiffusionPolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    budget_state: PheromoneBudgetState | None = None,
    processed_event_ids: frozenset[str] = frozenset(),
    processed_event_receipts: Mapping[str, tuple[Any, ...]] | None = None,
) -> PheromoneBatchResult:
    validate_pheromone_policy(policy)
    validate_pheromone_diffusion_policy(diffusion_policy)
    validate_pheromone_topology(
        neighborhood, candidate_set=candidate_set, target=target
    )
    items = list(trails)
    for trail in items:
        validate_pheromone_trail(
            trail, policy, candidate_set=candidate_set, target=target
        )
        validate_pheromone_subject_binding(
            neighborhood,
            subject_type=pheromone_subject_type(trail),
            subject_id=pheromone_subject_id(trail),
            candidate_id=pheromone_bound_candidate_id(trail),
            require_declared=bool(scoreable_pheromone_candidate_id(trail, policy)),
        )
    _reject_duplicate_trail_events(items, lifecycle="diffusion")
    budget = pheromone_budget_for_policy(policy, budget_state)
    processed = set(processed_event_ids)
    receipts = dict(processed_event_receipts or {})
    if not set(receipts).issubset(processed):
        raise GovernanceError(
            "pheromone diffusion replay receipt ids must be processed event ids"
        )
    if any(
        not is_nonblank_string(trace_event_id) or not isinstance(receipt, tuple)
        for trace_event_id, receipt in receipts.items()
    ):
        raise GovernanceError(
            "pheromone diffusion replay receipts require non-blank ids and tuple payloads"
        )
    replayed: set[str] = set()
    if not diffusion_policy.enabled:
        return PheromoneBatchResult(
            trails=tuple(items),
            processed_event_ids=frozenset(processed),
            budget_state=budget,
            _processed_event_receipts=tuple(sorted(receipts.items())),
        )

    subjects = {
        subject_key(subject.subject_type, subject.subject_id): subject
        for subject in neighborhood.subjects
    }
    edges = outgoing_edges(neighborhood)
    diffused = list(items)
    trail_by_trace_id = {item.trace_event_id: item for item in diffused}
    records: list[PheromoneLifecycleRecord] = []
    ordered = [
        trail
        for _, trail in sorted(
            enumerate(items),
            key=lambda item: pheromone_processing_key(item[1], item[0], policy),
        )
    ]
    for trail in ordered:
        # Derived trails are explicit ABI records produced by a complete
        # bounded BFS from their source root. Reusing them as roots on replay
        # would create propagation beyond the declared lifecycle record.
        if trail.diffusion_hop > 0:
            continue
        start = subject_key(pheromone_subject_type(trail), pheromone_subject_id(trail))
        if start not in subjects:
            continue
        start_target = topology_subject_target(subjects[start], candidate_set)
        trail_target = trail.target
        if (
            not trail_target
            and pheromone_bound_candidate_id(trail)
            and candidate_set is not None
        ):
            trail_target = candidate_set.require_declared(
                pheromone_bound_candidate_id(trail)
            ).target
        if start_target and trail_target and start_target != trail_target:
            raise GovernanceError(
                f"pheromone trail target {trail_target} does not match topology subject target {start_target}"
            )
        frontier = deque([(start, 0, trail.strength, trail.trace_event_id)])
        visited = {start}
        while frontier:
            current, hops, strength, parent_trace_event_id = frontier.popleft()
            if hops >= diffusion_policy.max_hops:
                continue
            for edge in edges.get(current, []):
                next_key = subject_key(edge.target_subject_type, edge.target_subject_id)
                if next_key in visited:
                    continue
                visited.add(next_key)
                next_hops = hops + 1
                requested_strength = (
                    strength * diffusion_policy.attenuation * edge.attenuation
                )
                if not math.isfinite(requested_strength):
                    raise GovernanceError(
                        "diffused pheromone strength must remain finite"
                    )
                if requested_strength <= 0:
                    continue
                subject = subjects[next_key]
                candidate_id = (
                    topology_subject_candidate_id(subject) or trail.candidate_id
                )
                subject_target = (
                    topology_subject_target(subject, candidate_set) or trail_target
                )
                source_id = pheromone_source_id(trail)
                derived_trace_id = pheromone_diffusion_trace_event_id(
                    trail.trace_event_id,
                    next_hops,
                    subject.subject_type,
                    subject.subject_id,
                )
                parent_trail = trail_by_trace_id.get(parent_trace_event_id, trail)
                causal_payload = _diffusion_clip_causal_payload(
                    source_trail=parent_trail,
                    target_subject=subject,
                    edge=edge,
                    policy_attenuation=diffusion_policy.attenuation,
                    hop=next_hops,
                    parent_trace_event_id=parent_trace_event_id,
                    derived_trace_event_id=derived_trace_id,
                    effective_target=subject_target,
                    effective_candidate_id=candidate_id,
                    source_strength=strength,
                )
                replay_fingerprint = _diffusion_replay_fingerprint(causal_payload)
                if derived_trace_id in processed:
                    expected = receipts.get(derived_trace_id)
                    if expected is None:
                        raise GovernanceError(
                            "processed pheromone diffusion id has no matching replay receipt: "
                            f"{derived_trace_id}"
                        )
                    if expected != replay_fingerprint:
                        raise GovernanceError(
                            "pheromone diffusion replay payload does not match its processed id: "
                            f"{derived_trace_id}"
                        )
                    replayed.add(derived_trace_id)
                    continue
                budget_request = min(requested_strength, float(policy.max_strength))
                applied_strength, updated_budget = budget.consume(
                    source_id, budget_request
                )
                if applied_strength < policy.min_strength or applied_strength <= 0:
                    rejected = replace(
                        trail,
                        candidate_id=candidate_id,
                        strength=0.0,
                        subject_type=subject.subject_type,
                        subject_id=subject.subject_id,
                        target=subject_target,
                        trace_event_id=derived_trace_id,
                    )
                    records.append(
                        lifecycle_record(
                            "diffuse_rejected",
                            rejected,
                            old_strength=0.0,
                            requested_strength=requested_strength,
                            applied_strength=0.0,
                            source_trace_event_id=parent_trace_event_id,
                            round_budget_remaining=budget.round_remaining,
                            source_budget_remaining=budget.source_remaining(source_id),
                            hop=next_hops,
                            attenuation=diffusion_policy.attenuation * edge.attenuation,
                            policy_attenuation=diffusion_policy.attenuation,
                            edge_attenuation=edge.attenuation,
                            causal_payload=causal_payload,
                        )
                    )
                    processed.add(derived_trace_id)
                    receipts[derived_trace_id] = replay_fingerprint
                    continue
                budget = updated_budget
                diffused_trail = replace(
                    trail,
                    candidate_id=candidate_id,
                    strength=applied_strength,
                    subject_type=subject.subject_type,
                    subject_id=subject.subject_id,
                    target=subject_target,
                    trace_event_id=derived_trace_id,
                    diffusion_root_trace_event_id=trail.trace_event_id,
                    diffusion_parent_trace_event_id=parent_trace_event_id,
                    diffusion_hop=next_hops,
                    lineage_event_ids=tuple(
                        dict.fromkeys((*trail.lineage_event_ids, parent_trace_event_id))
                    ),
                )
                validate_pheromone_trail(
                    diffused_trail,
                    policy,
                    candidate_set=candidate_set,
                    target=target,
                )
                diffused.append(diffused_trail)
                trail_by_trace_id[derived_trace_id] = diffused_trail
                processed.add(derived_trace_id)
                receipts[derived_trace_id] = replay_fingerprint
                attenuation = diffusion_policy.attenuation * edge.attenuation
                records.append(
                    lifecycle_record(
                        "diffuse",
                        diffused_trail,
                        old_strength=0.0,
                        requested_strength=requested_strength,
                        applied_strength=applied_strength,
                        source_trace_event_id=parent_trace_event_id,
                        round_budget_remaining=budget.round_remaining,
                        source_budget_remaining=budget.source_remaining(source_id),
                        hop=next_hops,
                        attenuation=attenuation,
                        policy_attenuation=diffusion_policy.attenuation,
                        edge_attenuation=edge.attenuation,
                        causal_payload=causal_payload,
                    )
                )
                # Propagate the actual bounded state, never the pre-budget
                # request, and bind the next hop to its immediate parent.
                frontier.append(
                    (next_key, next_hops, applied_strength, derived_trace_id)
                )
    return PheromoneBatchResult(
        trails=tuple(diffused),
        records=tuple(records),
        processed_event_ids=frozenset(processed),
        budget_state=budget,
        replayed_event_ids=tuple(sorted(replayed)),
        _processed_event_receipts=tuple(sorted(receipts.items())),
    )


def pheromone_diffusion_trace_event_id(
    root_trace_event_id: str,
    hop: int,
    subject_type: str,
    subject_id: str,
) -> str:
    """Build a collision-free deterministic identity from opaque ABI fields."""

    components = (root_trace_event_id, str(hop), subject_type, subject_id)
    return "diffuse:" + "".join(f"{len(item)}:{item}" for item in components)


def outgoing_edges(
    neighborhood: PheromoneNeighborhood,
) -> dict[tuple[str, str], list[PheromoneEdge]]:
    edges: dict[tuple[str, str], list[PheromoneEdge]] = {}
    for edge in neighborhood.edges:
        edges.setdefault(
            subject_key(edge.source_subject_type, edge.source_subject_id), []
        ).append(edge)
    for items in edges.values():
        items.sort(key=lambda edge: (edge.target_subject_type, edge.target_subject_id))
    return edges


for _compat_function in (
    _diffusion_clip_causal_payload,
    _diffusion_replay_fingerprint,
    diffuse_pheromone_trails,
    diffuse_pheromone_trails_with_records,
    pheromone_diffusion_trace_event_id,
    outgoing_edges,
):
    _compat_function.__module__ = "pheroos.governance.pheromone"
del _compat_function

__all__ = (
    "_diffusion_clip_causal_payload",
    "_diffusion_replay_fingerprint",
    "diffuse_pheromone_trails",
    "diffuse_pheromone_trails_with_records",
    "outgoing_edges",
    "pheromone_diffusion_trace_event_id",
)
