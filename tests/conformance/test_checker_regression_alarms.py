from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pheroos.conformance.checks import (
    commit_authority_boundary,
    commit_policy_contract,
    layer_coordination_policy,
    pheromone_kind_profile,
    pheromone_subject_scoring,
    policy_adjustment_bounds,
    principal_attestation_contract,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import pheromone_policy_from_collective
from pheroos.protocol import load_capability_manifest
from pheroos.protocol.manifest import capability_manifest_from_dict


ROOT = Path(__file__).resolve().parents[2]


def _hybrid_manifest():
    return load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )


def _commit_manifest():
    payload = json.loads(
        (ROOT / "tests/fixtures/commit-integrity/v1/case-01.json").read_text(
            encoding="utf-8"
        )
    )
    return capability_manifest_from_dict(payload["manifest"])


def test_commit_authority_checker_surfaces_an_injected_tck_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    injected = "injected authority TCK regression"
    monkeypatch.setattr(
        commit_authority_boundary,
        "check_commit_tck_cases",
        lambda *args, **kwargs: CheckResult(
            "commit_authority_boundary", False, injected
        ),
    )

    result = commit_authority_boundary.check(_commit_manifest())

    assert result.ok is False
    assert injected in result.detail


def test_commit_policy_checker_surfaces_an_injected_profile_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _commit_manifest()
    policy = manifest.protocol.collective_commit_policy
    assert policy is not None
    monkeypatch.setattr(
        commit_policy_contract,
        "profile_for_manifest",
        lambda _manifest: SimpleNamespace(
            version="pheroos-injected-profile-v0",
            required_checks=commit_policy_contract.COMMIT_AUTHORITY_CHECKS,
        ),
    )

    problems, selected = commit_policy_contract._profile_contract_problems(
        manifest,
        policy,
    )

    assert selected == "pheroos-injected-profile-v0"
    assert problems == [
        "profile_selection:pheroos-injected-profile-v0!=pheroos-hybrid-commit-v1"
    ]


def test_layer_checker_surfaces_an_injected_materialization_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _hybrid_manifest()
    collective = manifest.protocol.collective_decision_policy
    assert collective is not None
    policy = layer_coordination_policy.layer_coordination_policy_from_collective(
        collective
    )
    candidates = layer_coordination_policy.candidate_set(manifest)
    target = layer_coordination_policy.active_target(manifest)
    primary = layer_coordination_policy.exercise_candidate_id(manifest)
    assert primary is not None
    item = layer_coordination_policy.action_proposal(
        "propose_pheromone",
        layer_id="evolutionary",
        candidate_id=primary,
        target=target,
        policy=policy,
        collective_policy=collective,
    )
    monkeypatch.setattr(
        layer_coordination_policy,
        "materialize_layer_pheromone_proposals",
        lambda **_kwargs: [],
    )

    assert layer_coordination_policy._pheromone_materialization_problems(
        primary=primary,
        item=item,
        candidates=candidates,
        target=target,
        policy=policy,
    ) == ["action_materialization:propose_pheromone"]


@pytest.mark.parametrize(
    ("kind", "injected_score"),
    (("negative", 1.0), ("positive", -1.0)),
)
def test_kind_checker_surfaces_injected_pressure_sign_regressions(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    injected_score: float,
) -> None:
    manifest = _hybrid_manifest()
    collective = manifest.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    candidates = pheromone_kind_profile.candidate_set(manifest)
    target = pheromone_kind_profile.active_target(manifest)
    candidate_id = pheromone_kind_profile.exercise_candidate_id(manifest)
    assert candidate_id is not None
    monkeypatch.setattr(
        pheromone_kind_profile,
        "score_pheromone_trails_result",
        lambda **_kwargs: SimpleNamespace(
            kind_breakdown={candidate_id: {kind: injected_score}}
        ),
    )

    assert pheromone_kind_profile._kind_subject_score_problems(
        kind=kind,
        profile=policy.kind_profiles[kind],
        subject_type="candidate",
        subject_types=("candidate",),
        competitive_singleton=False,
        candidates=candidates,
        candidate_id=candidate_id,
        target=target,
        policy=policy,
        strength=1.0,
    ) == [f"{kind}_candidate_pressure"]


def test_kind_checker_surfaces_an_injected_ttl_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _hybrid_manifest()
    collective = manifest.protocol.collective_decision_policy
    assert collective is not None
    policy = pheromone_policy_from_collective(collective)
    target = pheromone_kind_profile.active_target(manifest)
    candidate_id = pheromone_kind_profile.exercise_candidate_id(manifest)
    assert candidate_id is not None
    profile = policy.kind_profiles["positive"]
    monkeypatch.setattr(
        pheromone_kind_profile,
        "evaporate_trails",
        lambda trails, *_args, **_kwargs: list(trails),
    )

    assert pheromone_kind_profile._kind_ttl_problems(
        kind="positive",
        profile=profile,
        subject_types=("candidate",),
        candidate_id=candidate_id,
        target=target,
        policy=policy,
        strength=1.0,
    ) == ["positive_profile_ttl"]


def test_subject_checker_surfaces_injected_evidence_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _hybrid_manifest()

    def injected_score(*, candidate_set, policy, trails):
        del policy
        score = 1.0 if trails else 0.0
        return {candidate.id: score for candidate in candidate_set.candidates}

    monkeypatch.setattr(
        pheromone_subject_scoring,
        "score_pheromone_trails",
        injected_score,
    )
    monkeypatch.setattr(
        pheromone_subject_scoring,
        "_collect_subject_scores",
        lambda **_kwargs: {},
    )

    result = pheromone_subject_scoring.check_hybrid(manifest)

    assert result.ok is False
    assert result.detail == "evidence_subject_scored"


def test_subject_checker_surfaces_an_injected_binding_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _hybrid_manifest()
    monkeypatch.setattr(
        pheromone_subject_scoring,
        "validate_pheromone_trail",
        lambda *_args, **_kwargs: None,
    )

    result = pheromone_subject_scoring.check_hybrid(manifest)

    assert result.ok is False
    assert result.detail == "undeclared_candidate_binding"


def test_policy_checker_totalizes_an_injected_impossible_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toy = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    assert toy.protocol.collective_decision_policy is None
    monkeypatch.setattr(
        policy_adjustment_bounds,
        "has_hybrid_pheromone_features",
        lambda _policy: True,
    )

    assert policy_adjustment_bounds.check(toy) == CheckResult(
        "policy_adjustment_bounds", True
    )


def test_policy_checker_surfaces_injected_bound_enforcement_regressions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _hybrid_manifest()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    bounds = {"pheromone_evaporation_rate": (0.0, 1.0)}
    bounded_probe = policy_adjustment_bounds._bounded_adjustment_problems

    monkeypatch.setattr(
        policy_adjustment_bounds,
        "_bounded_adjustment_problems",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        policy_adjustment_bounds,
        "_proposal_rejected",
        lambda *_args, **_kwargs: False,
    )
    assert policy_adjustment_bounds._declared_bounds_problems(policy, bounds) == [
        "unbounded_accepted"
    ]

    monkeypatch.setattr(
        policy_adjustment_bounds,
        "validate_policy_adjustment_proposal",
        lambda *_args, **_kwargs: {"wrong": 0.0},
    )
    monkeypatch.setattr(
        policy_adjustment_bounds,
        "_proposal_rejected",
        lambda *_args, **_kwargs: True,
    )
    assert bounded_probe(
        policy,
        "pheromone_evaporation_rate",
        bounds["pheromone_evaporation_rate"],
    ) == ["overlay_mismatch:pheromone_evaporation_rate"]

    monkeypatch.setattr(
        policy_adjustment_bounds,
        "validate_policy_adjustment_proposal",
        lambda *_args, **_kwargs: {"pheromone_evaporation_rate": 0.0},
    )
    monkeypatch.setattr(
        policy_adjustment_bounds,
        "apply_policy_adjustment_overlay",
        lambda current, _overlay: current,
    )
    assert bounded_probe(
        policy,
        "pheromone_evaporation_rate",
        bounds["pheromone_evaporation_rate"],
    ) == ["effective_policy_mismatch:pheromone_evaporation_rate"]

    monkeypatch.setattr(
        policy_adjustment_bounds,
        "_proposal_rejected",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        policy_adjustment_bounds,
        "effective_adjustment_applied",
        lambda *_args, **_kwargs: True,
    )
    assert bounded_probe(
        policy,
        "pheromone_evaporation_rate",
        bounds["pheromone_evaporation_rate"],
    ) == ["out_of_bounds_accepted:pheromone_evaporation_rate"]
    assert policy_adjustment_bounds._undeclared_bounds_problems(policy) == [
        "undeclared_adjustment_accepted"
    ]


def test_principal_checker_surfaces_an_injected_tamper_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = principal_attestation_contract.active_commit_context(_commit_manifest())
    assert context is not None
    monkeypatch.setattr(
        principal_attestation_contract,
        "principal_verification_is_authoritative",
        lambda _verification: True,
    )

    assert principal_attestation_contract._tamper_problems(
        context,
        principal_attestation_contract._attestation(),
    ) == ["tampered_verification_accepted"]
