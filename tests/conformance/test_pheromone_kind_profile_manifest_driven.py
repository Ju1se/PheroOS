from dataclasses import replace

import pytest

from pheroos.conformance.checks import (
    hybrid_trace_contract,
    pheromone_diffusion,
    pheromone_kind_profile,
    pheromone_policy,
    pheromone_subject_scoring,
)
from pheroos.conformance.profile import profile_for_manifest
from pheroos.conformance.runner import MANIFEST_CHECKS, safe_check
from pheroos.protocol import (
    PheromoneKindProfile,
    effective_pheromone_scored_subject_types,
    load_capability_manifest,
    validate_capability_manifest,
)


def test_kind_profile_check_exercises_every_declared_kind_subject_and_ttl(monkeypatch) -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(
                policy,
                pheromone_max_strength=0.5,
                pheromone_min_source_diversity=2,
            ),
        ),
    )
    observed_scores: set[tuple[str, str]] = set()
    observed_ttls: set[str] = set()
    score = pheromone_kind_profile.score_pheromone_trails_result
    evaporate = pheromone_kind_profile.evaporate_trails

    def tracking_score(*, trails, **kwargs):
        observed_scores.update((trail.kind, trail.subject_type) for trail in trails)
        return score(trails=trails, **kwargs)

    def tracking_evaporation(trails, *args, **kwargs):
        observed_ttls.update(trail.kind for trail in trails)
        return evaporate(trails, *args, **kwargs)

    monkeypatch.setattr(
        pheromone_kind_profile,
        "score_pheromone_trails_result",
        tracking_score,
    )
    monkeypatch.setattr(pheromone_kind_profile, "evaporate_trails", tracking_evaporation)

    result = pheromone_kind_profile.check(manifest)

    expected_scores: set[tuple[str, str]] = set()
    for kind, profile in policy.pheromone_kind_profiles.items():
        subjects = effective_pheromone_scored_subject_types(
            kind,
            profile,
            policy.pheromone_scored_subject_types,
        )
        if not subjects and kind == "stale":
            subjects = ("candidate",)
        expected_scores.update((kind, subject_type) for subject_type in subjects)
    expected_ttls = {
        kind
        for kind, profile in policy.pheromone_kind_profiles.items()
        if profile.ttl_steps is not None
    }
    assert result.ok is True, result.detail
    assert expected_scores <= observed_scores
    assert expected_ttls <= observed_ttls


def test_kind_profile_check_proves_global_cap_precedes_source_diversity_gate() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    profiles = dict(policy.pheromone_kind_profiles)
    profiles["alarm"] = replace(
        profiles["alarm"],
        weight=1.0,
        response_model="linear",
        priority=2,
        scored_subject_types=["candidate"],
    )
    profiles["positive"] = replace(
        profiles["positive"],
        weight=1.0,
        response_model="linear",
        priority=1,
        scored_subject_types=["candidate"],
    )
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(
                policy,
                pheromone_per_source_cap=1.0,
                pheromone_min_source_diversity=2,
                pheromone_kind_profiles=profiles,
            ),
        ),
    )

    result = pheromone_kind_profile.check(manifest)

    assert result.ok is True, result.detail


@pytest.mark.parametrize(
    ("scored_subject_types", "expects_kind_score"),
    [
        ([], False),
        (["candidate"], True),
    ],
)
def test_namespaced_kind_conformance_requires_explicit_per_kind_scoring_subjects(
    scored_subject_types: list[str],
    expects_kind_score: bool,
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = manifest.protocol.collective_decision_policy
    assert collective is not None
    custom_kind = "x-acme.preference"
    collective = replace(
        collective,
        pheromone_kind_profiles={
            **collective.pheromone_kind_profiles,
            custom_kind: PheromoneKindProfile(
                weight=1.0,
                scored_subject_types=scored_subject_types,
            ),
        },
    )
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=collective,
        ),
    )
    candidates = pheromone_kind_profile.candidate_set(manifest)
    candidate_id = pheromone_kind_profile.exercise_candidate_id(manifest)
    assert candidate_id is not None
    runtime_policy = pheromone_kind_profile.pheromone_policy_from_collective(
        collective
    )
    trails = pheromone_kind_profile.profile_trails(
        candidate_id,
        target=pheromone_kind_profile.active_target(manifest),
        kind=custom_kind,
        subject_type="candidate",
        strength=1.0,
        source_count=runtime_policy.min_source_diversity,
    )

    result = pheromone_kind_profile.check(manifest)
    score_result = pheromone_kind_profile.score_pheromone_trails_result(
        candidate_set=candidates,
        policy=runtime_policy,
        trails=trails,
    )
    kind_score = score_result.kind_breakdown[candidate_id].get(custom_kind, 0.0)

    assert validate_capability_manifest(manifest) == []
    assert result.ok is True, result.detail
    assert (kind_score > 0) is expects_kind_score


@pytest.mark.parametrize(
    "updates",
    [
        {"pheromone_scored_subject_types": ["candidate", "evidence"]},
        {
            "pheromone_kind_profiles": {
                "positive": PheromoneKindProfile(
                    scored_subject_types=["evidence"],
                )
            }
        },
    ],
)
def test_manifest_conformance_rejects_evidence_scoring_declarations(
    updates: dict[str, object],
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    collective = replace(manifest.protocol.collective_decision_policy, **updates)
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=collective,
        ),
    )

    assert validate_capability_manifest(manifest)
    assert pheromone_policy.check(manifest).ok is False
    assert pheromone_subject_scoring.check(manifest).ok is False


def test_low_max_strength_replay_emits_truthful_clip_lineage() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, pheromone_max_strength=0.5),
        ),
    )

    step, _ = hybrid_trace_contract.manifest_replay(manifest)
    clips = [event for event in step.trace_events if event.event_type == "pheromone_clip"]

    assert clips
    assert any(event.lineage["requested_strength"] > 0.5 for event in clips)
    assert all(event.lineage["applied_strength"] <= 0.5 for event in clips)


@pytest.mark.parametrize(
    "updates",
    [
        {"pheromone_max_strength": 0.5},
        {"pheromone_min_source_diversity": 2},
        {"pheromone_max_strength": 0.5, "pheromone_min_source_diversity": 2},
    ],
)
@pytest.mark.parametrize(
    "check",
    [pheromone_kind_profile.check, pheromone_diffusion.check, hybrid_trace_contract.check],
)
def test_hybrid_behavior_checks_accept_valid_manifest_edge_policies(check, updates) -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )

    result = check(manifest)

    assert result.ok is True, result.detail


@pytest.mark.parametrize(
    ("check", "updates"),
    [
        (pheromone_kind_profile.check, {"pheromone_min_source_diversity": "invalid"}),
        (pheromone_diffusion.check, {"pheromone_max_strength": "invalid"}),
    ],
)
def test_manifest_driven_behavior_checks_are_total_for_malformed_direct_policy(
    check,
    updates,
) -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )

    result = check(manifest)

    assert result.ok is False
    assert result.detail.startswith("exercise:")


@pytest.mark.parametrize(
    "updates",
    [
        {
            "pheromone_min_strength": 0.4,
            "pheromone_max_strength": 0.5,
            "pheromone_per_source_cap": 0.5,
            "pheromone_per_round_deposit_cap": 0.8,
        },
        {
            "pheromone_min_strength": 9.0,
            "pheromone_max_strength": 10.0,
            "pheromone_per_source_cap": 10.0,
            "pheromone_per_round_deposit_cap": 10.0,
        },
        {"pheromone_activation_threshold": 20.0},
    ],
)
def test_full_hybrid_profile_accepts_valid_manifest_derived_strength_edges(updates) -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=replace(policy, **updates),
        ),
    )

    assert validate_capability_manifest(manifest) == []
    failures = [
        result
        for check_name in profile_for_manifest(manifest).required_checks
        if check_name != "manifest_schema"
        for result in [safe_check(check_name, MANIFEST_CHECKS[check_name], manifest)]
        if not result.ok
    ]

    assert failures == []
