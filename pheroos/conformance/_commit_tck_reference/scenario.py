"""Private Commit TCK reference scenario handlers."""

from __future__ import annotations

from collections.abc import Sequence

import json

from typing import Any

from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_reference import (
    ReferenceScenario,
    build_reference_scenario,
    issue_reference_binding,
    issue_reference_observation,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.evidence_binding import (
    evaluate_evidence_binding,
)

from pheroos.governance.observation import (
    ObservationPolarity,
)

from pheroos.governance.risk import (
    commit_threshold_snapshot_fingerprint,
)

from pheroos.trace import (
    TraceEvent,
    make_commit_trace_event,
    replay_commit_trace,
)

from pheroos.conformance._commit_tck_reference.state import (
    _REFERENCE_FIXTURE_CACHE,
    _REFERENCE_FIXTURE_CACHE_LOCK,
)


def _require_vector_manifest(vector: _CommitTckRequest) -> dict[str, Any]:
    if vector.manifest is None:
        raise ValueError(f"TCK vector {vector.id} requires a manifest")
    return vector.manifest


def _reference_scenario(
    vector: _CommitTckRequest,
    *,
    variant: str = "base",
    tie: bool = False,
    blocked: bool = False,
    shared_cluster: bool = False,
    leader_observation_count: int = 2,
    other_observation_count: int | None = None,
    minimum_membership_size: int = 3,
) -> ReferenceScenario:
    manifest = _require_vector_manifest(vector)
    key = (
        vector.id,
        vector.profile,
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        variant,
        tie,
        blocked,
        shared_cluster,
        leader_observation_count,
        other_observation_count,
        minimum_membership_size,
    )
    with _REFERENCE_FIXTURE_CACHE_LOCK:
        cached = _REFERENCE_FIXTURE_CACHE.get(key)
        if cached is not None:
            return cached
        scenario = build_reference_scenario(
            vector.id,
            manifest,
            profile=vector.profile,
            variant=variant,
            tie=tie,
            blocked=blocked,
            shared_cluster=shared_cluster,
            leader_observation_count=leader_observation_count,
            other_observation_count=other_observation_count,
            minimum_membership_size=minimum_membership_size,
        )
        _REFERENCE_FIXTURE_CACHE[key] = scenario
        return scenario


def _observation(
    scenario: ReferenceScenario,
    *,
    index: int,
    principal_index: int = 0,
    candidate_id: str | None = None,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    independence_group: str | None = None,
    source_domain: str | None = None,
    nonce: str | None = None,
    quality_ppm: int = 1_000_000,
    relevance_ppm: int = 1_000_000,
    materiality_ppm: int = 1_000_000,
    criticality_ppm: int = 0,
) -> Any:
    candidate = candidate_id or scenario.leader_id
    return issue_reference_observation(
        scenario.namespace,
        index=index,
        principal=scenario.principals[principal_index],
        candidate_id=candidate,
        claim_fingerprint=scenario.claims[candidate],
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        evidence_policy=collective_commit_policy(
            scenario.policy
        ).evidence_qualification,
        polarity=polarity,
        independence_group=independence_group,
        source_domain=source_domain,
        nonce=nonce,
        quality_ppm=quality_ppm,
        relevance_ppm=relevance_ppm,
        materiality_ppm=materiality_ppm,
        criticality_ppm=criticality_ppm,
    )


def _binding(
    scenario: ReferenceScenario,
    *,
    candidate_id: str,
    positives: Sequence[Any],
    counters: Sequence[Any] = (),
    dispositions: Sequence[Any] = (),
    challenges: Sequence[Any] | None = None,
    variant: str,
) -> Any:
    return issue_reference_binding(
        scenario.namespace,
        candidate_id=candidate_id,
        claim_fingerprint=scenario.claims[candidate_id],
        observations=tuple(positives),
        counter_observations=tuple(counters),
        dispositions=tuple(dispositions),
        challenges=(
            (scenario.challenges[candidate_id],)
            if challenges is None
            else tuple(challenges)
        ),
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        current_step=4,
        binding_variant=variant,
    )


def _evaluate_binding(
    scenario: ReferenceScenario,
    binding: Any,
    *,
    positives: Sequence[Any],
    counters: Sequence[Any] = (),
    dispositions: Sequence[Any] = (),
    challenges: Sequence[Any] | None = None,
    current_step: int = 5,
) -> Any:
    return evaluate_evidence_binding(
        binding,
        positive_observations=tuple(positives),
        counter_observations=tuple(counters),
        dispositions=tuple(dispositions),
        challenges=(
            (scenario.challenges[binding.candidate_id],)
            if challenges is None
            else tuple(challenges)
        ),
        evidence_policy=collective_commit_policy(
            scenario.policy
        ).evidence_qualification,
        current_step=current_step,
    )


def _risk_trace_event(scenario: ReferenceScenario) -> TraceEvent:
    threshold_ref = commit_threshold_snapshot_fingerprint(scenario.threshold)
    return make_commit_trace_event(
        event_type="risk_assessed",
        protocol_id=scenario.protocol_id,
        target=scenario.target,
        reason="tck_risk_assessed",
        profile=scenario.profile,
        assurance=scenario.assurance.value,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        run_id=scenario.run_id,
        epoch=scenario.epoch,
        step=scenario.risk_assessment.issued_at_step,
        record_schema="pheroos-tck-risk-observation-v1",
        record_payload={
            "risk_band": scenario.risk_assessment.risk_band.value,
            "threshold_ref": threshold_ref,
            "risk_chain_revision": scenario.risk_assessment.risk_chain_revision,
        },
        details={
            "risk_band": scenario.risk_assessment.risk_band.value,
            "risk_ref": "",
            "threshold_ref": threshold_ref,
            "risk_chain_revision": scenario.risk_assessment.risk_chain_revision,
        },
    )


def _risk_trace_sequence(scenario: ReferenceScenario) -> list[str]:
    event = _risk_trace_event(scenario)
    replay = replay_commit_trace((event,), require_complete=False)
    return list(replay.event_types)
