from __future__ import annotations

from dataclasses import replace

import pytest

from pheroos.governance.errors import GovernanceError
from pheroos.governance.pheromone import (
    PHEROMONE_KIND_PROFILE_MAP_VERSION,
    PheromonePolicy,
    PheromoneTrail,
    canonical_pheromone_kind_profiles,
    normalize_legacy_pheromone_trail,
    pheromone_policy_from_collective,
    raw_pheromone_delta,
    validate_pheromone_trail,
)
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    SUPPORTED_PHEROMONE_KINDS,
)


def test_scalar_weights_normalize_to_one_complete_runtime_profile_map() -> None:
    policy = CollectiveDecisionPolicy(
        pheromone_positive_weight=1.5,
        pheromone_negative_weight=2.5,
        pheromone_cautionary_weight=3.5,
        pheromone_novelty_weight=0.75,
        pheromone_response_model="saturating",
    )

    profiles = canonical_pheromone_kind_profiles(policy)
    runtime = pheromone_policy_from_collective(policy)

    assert PHEROMONE_KIND_PROFILE_MAP_VERSION == "pheroos-pheromone-kind-profile-map-v1"
    assert set(profiles) == set(SUPPORTED_PHEROMONE_KINDS)
    assert set(runtime.kind_profiles) == set(SUPPORTED_PHEROMONE_KINDS)
    assert {kind: profile.weight for kind, profile in profiles.items()} == {
        "positive": 1.5,
        "negative": 2.5,
        "cautionary": 3.5,
        "alarm": 3.5,
        "novelty": 0.75,
        "stale": 0.0,
    }
    assert profiles["alarm"].can_suppress_positive is True
    assert profiles["cautionary"].can_suppress_positive is True
    assert profiles["positive"].response_model == "saturating"
    assert policy.pheromone_kind_profiles == {}


def test_explicit_kind_profile_wins_full_double_write_conflict() -> None:
    explicit = PheromoneKindProfile(
        weight=9.0,
        evaporation_rate=0.4,
        ttl_steps=7,
        response_model="threshold",
        priority=19,
        can_suppress_positive=True,
        scored_subject_types=["route"],
    )
    extension = PheromoneKindProfile(weight=0.25, scored_subject_types=["candidate"])
    policy = CollectiveDecisionPolicy(
        pheromone_positive_weight=1.0,
        pheromone_kind_profiles={
            "positive": explicit,
            "x-acme.preference": extension,
        },
    )

    profiles = canonical_pheromone_kind_profiles(policy)

    assert profiles["positive"] is explicit
    assert profiles["positive"].weight == 9.0
    assert profiles["positive"].response_model == "threshold"
    assert profiles["x-acme.preference"] is extension
    assert profiles["negative"].weight == policy.pheromone_negative_weight


@pytest.mark.parametrize("kind", ["positive", "negative", "cautionary", "alarm", "novelty"])
def test_scalar_only_runtime_keeps_legacy_score_semantics(kind: str) -> None:
    collective = CollectiveDecisionPolicy(
        pheromone_positive_weight=1.25,
        pheromone_negative_weight=1.5,
        pheromone_cautionary_weight=1.75,
        pheromone_novelty_weight=0.8,
    )
    normalized = pheromone_policy_from_collective(collective)
    legacy = replace(normalized, kind_profiles={})
    trail = PheromoneTrail(candidate_id="candidate:a", strength=2.0, kind=kind)

    assert raw_pheromone_delta(trail, normalized) == raw_pheromone_delta(trail, legacy)


def test_two_field_legacy_trail_requires_and_receives_explicit_lineage() -> None:
    trail = PheromoneTrail("candidate:a", 2.0)

    normalized = normalize_legacy_pheromone_trail(
        trail,
        target="target:decision",
        source_id="agent:scout-a",
        source_role="scout",
        evidence_id="evidence:a",
        provenance="provider-free:test",
        trace_event_id="trace:deposit:a",
    )

    assert normalized.subject_type == "candidate"
    assert normalized.subject_id == "candidate:a"
    assert normalized.target == "target:decision"
    assert normalized.source_id == "agent:scout-a"
    assert normalized.source_role == "scout"
    assert normalized.evidence_id == "evidence:a"
    assert normalized.provenance == "provider-free:test"
    assert normalized.lineage_event_ids == ("trace:deposit:a",)
    validate_pheromone_trail(
        normalized,
        PheromonePolicy(enabled=True, require_provenance=True, require_trace=True),
        target="target:decision",
    )


def test_legacy_route_binding_is_canonical_and_retains_candidate_association() -> None:
    normalized = normalize_legacy_pheromone_trail(
        PheromoneTrail("candidate:a", 1.0, route_id="route:a"),
        target="target:decision",
        source_id="agent:a",
        provenance="test",
        trace_event_id="trace:a",
    )

    assert normalized.subject_type == "route"
    assert normalized.subject_id == "route:a"
    assert normalized.candidate_id == "candidate:a"


@pytest.mark.parametrize(
    ("trail", "updates", "match"),
    [
        (
            PheromoneTrail("candidate:a", 1.0),
            {"target": ""},
            "requires non-blank target",
        ),
        (
            PheromoneTrail("candidate:a", 1.0, target="target:a"),
            {"target": "target:b"},
            "target conflicts",
        ),
        (
            PheromoneTrail("candidate:a", 1.0, route_id="route:a", tool_id="tool:a"),
            {},
            "ambiguous route/tool",
        ),
        (
            PheromoneTrail("", 1.0),
            {},
            "does not identify a subject",
        ),
    ],
)
def test_legacy_normalization_fails_closed_on_missing_or_conflicting_bindings(
    trail: PheromoneTrail,
    updates: dict[str, str],
    match: str,
) -> None:
    bindings = {
        "target": "target:a",
        "source_id": "agent:a",
        "provenance": "test",
        "trace_event_id": "trace:a",
        **updates,
    }

    with pytest.raises(GovernanceError, match=match):
        normalize_legacy_pheromone_trail(trail, **bindings)
