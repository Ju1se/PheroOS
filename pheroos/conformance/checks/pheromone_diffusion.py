from __future__ import annotations

from math import isclose

from pheroos.conformance.checks._manifest import (
    active_target,
    candidate_set,
    exercise_candidate_id,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    PheromoneBatchResult,
    PheromoneDiffusionPolicy,
    PheromoneEdge,
    PheromoneLifecycleRecord,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneSubject,
    PheromoneTrail,
    diffusion_policy_from_collective,
    diffuse_pheromone_trails_with_records,
    pheromone_policy_from_collective,
    validate_pheromone_topology,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CapabilityManifest, has_hybrid_pheromone_features


def check(manifest: CapabilityManifest) -> CheckResult:
    collective_policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(collective_policy):
        return CheckResult("pheromone_diffusion", True)
    if collective_policy is None:
        return CheckResult("pheromone_diffusion", False, "collective_policy")
    try:
        problems = diffusion_problems(manifest)
    except Exception as exc:  # total-function boundary for direct check consumers
        detail = str(exc).strip()
        return CheckResult(
            "pheromone_diffusion",
            False,
            f"exercise:{type(exc).__name__}" + (f":{detail}" if detail else ""),
        )
    return CheckResult("pheromone_diffusion", not problems, ", ".join(problems))


def diffusion_problems(manifest: CapabilityManifest) -> list[str]:
    candidates = candidate_set(manifest)
    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        return ["active_target_candidates"]
    target = active_target(manifest)
    collective_policy = manifest.protocol.collective_decision_policy
    if collective_policy is None:
        return ["collective_policy"]
    policy = pheromone_policy_from_collective(collective_policy)
    diffusion_policy = diffusion_policy_from_collective(collective_policy)
    neighborhood = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "route", "route:alpha", candidate_id=candidate_id, target=target
            ),
            PheromoneSubject(
                "candidate", candidate_id, candidate_id=candidate_id, target=target
            ),
            PheromoneSubject(
                "tool", "tool:terminal", candidate_id=candidate_id, target=target
            ),
        ],
        edges=[
            PheromoneEdge(
                "route", "route:alpha", "candidate", candidate_id, attenuation=1.0
            ),
            PheromoneEdge(
                "candidate", candidate_id, "tool", "tool:terminal", attenuation=1.0
            ),
        ],
    )
    source_strength = float(policy.max_strength)
    result = diffuse_pheromone_trails_with_records(
        [trail(candidate_id, target=target, strength=source_strength)],
        neighborhood,
        policy,
        diffusion_policy,
        candidate_set=candidates,
        target=target,
    )

    problems = expected_diffusion_problems(
        result,
        candidate_id=candidate_id,
        source_strength=source_strength,
        policy=policy,
        diffusion_policy=diffusion_policy,
    )
    unbound_topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:unbound", target=target),
            PheromoneSubject(
                "candidate", candidate_id, candidate_id=candidate_id, target=target
            ),
        ],
        edges=[PheromoneEdge("route", "route:unbound", "candidate", candidate_id)],
    )
    try:
        validate_pheromone_topology(
            unbound_topology, candidate_set=candidates, target=target
        )
    except GovernanceError:
        pass
    else:
        problems.append("unbound_topology_subject")

    bad_topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "route", "route:alpha", candidate_id=candidate_id, target=target
            )
        ],
        edges=[PheromoneEdge("route", "route:alpha", "candidate", "candidate:missing")],
    )
    try:
        validate_pheromone_topology(
            bad_topology, candidate_set=candidates, target=target
        )
    except GovernanceError:
        pass
    else:
        problems.append("undeclared_topology")

    alternate_candidate_id = next(
        (
            candidate.id
            for candidate in candidates.candidates
            if candidate.target == target and candidate.id != candidate_id
        ),
        None,
    )
    if alternate_candidate_id is not None:
        try:
            diffuse_pheromone_trails_with_records(
                [
                    trail(
                        alternate_candidate_id, target=target, strength=source_strength
                    )
                ],
                neighborhood,
                policy,
                diffusion_policy,
                candidate_set=candidates,
                target=target,
            )
        except GovernanceError:
            pass
        else:
            problems.append("topology_candidate_binding")
    return problems


def expected_diffusion_problems(
    result: PheromoneBatchResult,
    *,
    candidate_id: str,
    source_strength: float,
    policy: PheromonePolicy,
    diffusion_policy: PheromoneDiffusionPolicy,
) -> list[str]:
    problems: list[str] = []
    derived = {
        (item.subject_type, item.subject_id): item
        for item in result.trails
        if item.diffusion_hop > 0
    }
    records_by_hop = {record.hop: record for record in result.records}
    remaining_source = float(policy.per_source_cap)
    remaining_round = float(policy.per_round_deposit_cap)
    frontier_strength = source_strength
    destinations = (("candidate", candidate_id), ("tool", "tool:terminal"))

    for hop, destination in enumerate(destinations, start=1):
        if hop > diffusion_policy.max_hops or diffusion_policy.attenuation <= 0:
            if destination in derived:
                problems.append(f"exceeded_declared_hops:{hop}")
            continue
        requested = frontier_strength * float(diffusion_policy.attenuation)
        budget_request = min(requested, float(policy.max_strength))
        applied = min(budget_request, remaining_source, remaining_round)
        if applied < policy.min_strength:
            applied = 0.0
        record = records_by_hop.get(hop)
        hop_problems, should_continue = _diffusion_hop_problems(
            record=record,
            observed=derived.get(destination),
            requested=requested,
            applied=applied,
            attenuation=float(diffusion_policy.attenuation),
            hop=hop,
        )
        problems.extend(hop_problems)
        if not should_continue:
            break
        remaining_source -= applied
        remaining_round -= applied
        frontier_strength = applied

    if any(record.hop > diffusion_policy.max_hops for record in result.records):
        problems.append("record_exceeded_max_hops")
    return problems


def _diffusion_hop_problems(
    *,
    record: PheromoneLifecycleRecord | None,
    observed: PheromoneTrail | None,
    requested: float,
    applied: float,
    attenuation: float,
    hop: int,
) -> tuple[list[str], bool]:
    if record is None:
        return [f"diffusion_record_missing:{hop}"], False
    problems = _diffusion_record_problems(
        record=record,
        requested=requested,
        applied=applied,
        attenuation=attenuation,
        hop=hop,
    )
    if applied <= 0:
        if observed is not None or record.action != "diffuse_rejected":
            problems.append(f"rejected_diffusion_materialized:{hop}")
        return problems, False
    if observed is None:
        problems.append(f"declared_hop_not_applied:{hop}")
        return problems, False
    if not isclose(observed.strength, applied, abs_tol=1e-9):
        problems.append(f"diffused_strength:{hop}")
    return problems, True


def _diffusion_record_problems(
    *,
    record: PheromoneLifecycleRecord,
    requested: float,
    applied: float,
    attenuation: float,
    hop: int,
) -> list[str]:
    problems: list[str] = []
    if not isclose(record.requested_strength, requested, abs_tol=1e-9):
        problems.append(f"attenuation:{hop}")
    if not isclose(record.applied_strength, applied, abs_tol=1e-9):
        problems.append(f"budget_application:{hop}")
    if not isclose(record.attenuation, attenuation, abs_tol=1e-9):
        problems.append(f"recorded_attenuation:{hop}")
    return problems


def trail(candidate_id: str, *, target: str, strength: float) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type="route",
        subject_id="route:alpha",
        target=target,
        source_id="agent:conformance",
        evidence_id="evidence:conformance",
        provenance="driver:conformance",
        trace_event_id="trace:conformance:route",
    )
