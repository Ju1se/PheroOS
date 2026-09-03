from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
import pickle

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitFinalityStatus,
    DecisionOutcomeKind,
    ReplayNamespace,
    commit_finality_verification_is_authoritative,
    commit_finality_verification_payload,
    commit_replay_state_contains,
    commit_replay_state_is_authoritative,
    commit_replay_state_is_current,
    commit_replay_state_matches,
    commit_replay_state_payload,
    commit_window_seal_for_state,
    commit_window_state_is_authoritative,
    commit_window_state_is_current,
    commit_window_state_payload,
    decision_outcome_is_authoritative,
    decision_outcome_payload,
    decision_progress_is_authoritative,
    decision_progress_payload,
    record_commit_replay_receipts,
    reduce_commit_liveness,
    replay_receipt_payload,
)
from pheroos.governance.distributed_commit import (
    distributed_commit_certificate_payload,
    distributed_commit_state_payload,
    distributed_finality_decision_payload,
    evaluate_distributed_finality,
    portable_membership_snapshot_payload,
    register_distributed_commit_certificate,
    witness_verification_payload,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.schema import validate_commit_wire_record
from pheroos.protocol.commit_wire import canonical_commit_payload
from tests.governance import test_commit_liveness as liveness_fixture
from tests.governance import test_commit_output_actions as output_fixture
from tests.governance import test_commit_window as window_fixture
from tests.governance import test_commit_wp_cd_schema as support_fixture
from tests.governance import test_distributed_commit as distributed_fixture


_ROOT_A = "sha256:" + ("a" * 64)
_ROOT_B = "sha256:" + ("b" * 64)
_ROOT_C = "sha256:" + ("c" * 64)


def _wire(
    payload: dict[str, object], *, schema: str, profile: str
) -> dict[str, object]:
    import json

    return json.loads(canonical_commit_payload(payload, schema=schema, profile=profile))


def _assert_wire_error(record: dict[str, object], fragment: str) -> None:
    errors = validate_commit_wire_record(record)
    assert any(fragment in error for error in errors), errors


def _support_record(schema: str) -> dict[str, object]:
    return deepcopy(support_fixture.wp_cd_records()[schema])


def test_support_wire_temporal_disposition_and_coverage_semantics() -> None:
    record = _support_record("pheroos-verified-observation-v1")
    record["payload"]["observed_at_step"] = 3
    _assert_wire_error(record, "verification precedes observation")

    record = _support_record("pheroos-verified-challenge-v1")
    record["payload"]["executed_at_step"] = 4
    _assert_wire_error(record, "verification precedes challenge execution")

    record = _support_record("pheroos-challenge-attestation-v1")
    record["payload"]["result_observation_fingerprints"] = [_ROOT_A]
    _assert_wire_error(record, "non-counterevidence result")

    record = _support_record("pheroos-counterevidence-disposition-v1")
    record["payload"].update(
        kind="rebutted",
        rebuttal_observation_fingerprints=[],
        resolution_ref="",
    )
    _assert_wire_error(record, "rebutted disposition requires evidence")
    _assert_wire_error(record, "requires governance resolution")

    record = _support_record("pheroos-counterevidence-disposition-v1")
    record["payload"].update(
        kind="unresolved",
        rebuttal_observation_fingerprints=[_ROOT_A],
        resolution_ref=_ROOT_B,
    )
    _assert_wire_error(record, "only rebutted disposition")
    _assert_wire_error(record, "unresolved disposition cannot claim resolution")

    record = _support_record("pheroos-counterevidence-disposition-v1")
    record["payload"].update(kind="accepted", resolution_ref="")
    _assert_wire_error(record, "resolved disposition requires governance resolution")

    record = _support_record("pheroos-challenge-coverage-v1")
    record["payload"].update(
        required_categories=["category:a", "category:b"],
        covered_categories=["category:c"],
        missing_categories=[],
        challenge_fingerprints=[],
    )
    _assert_wire_error(record, "contains undeclared category")
    _assert_wire_error(record, "coverage difference mismatch")
    _assert_wire_error(record, "fewer challenges")

    record = _support_record("pheroos-challenge-coverage-v1")
    record["payload"].update(
        required_categories=["independent_replication", "second_review"],
        missing_categories=["second_review"],
        complete=True,
    )
    _assert_wire_error(record, "completion flag mismatch")


def test_support_wire_evidence_lineage_metrics_and_group_semantics() -> None:
    record = _support_record("pheroos-evidence-binding-authority-v1")
    record["payload"].update(
        positive_observation_fingerprints=[],
        counter_observation_fingerprints=[],
    )
    _assert_wire_error(record, "requires an observation")

    record = _support_record("pheroos-evidence-binding-authority-v1")
    record["payload"]["counter_observation_fingerprints"] = [
        record["payload"]["positive_observation_fingerprints"][0]
    ]
    _assert_wire_error(record, "evidence leaves overlap")

    record = _support_record("pheroos-evidence-summary-v1")
    positive_ref = record["payload"]["positive_groups"][0]["observation_fingerprints"][
        0
    ]
    record["payload"].update(
        active_counter_observation_fingerprints=[positive_ref],
        resolved_counter_observation_fingerprints=[positive_ref],
        blocking_critical_counter_observation_fingerprints=[_ROOT_C],
    )
    record["payload"]["source_domains"][0]["observation_fingerprints"] = [_ROOT_C]
    _assert_wire_error(record, "counter group lineage mismatch")
    _assert_wire_error(record, "active and resolved counterevidence overlap")
    _assert_wire_error(record, "positive and counter observation lineage overlap")
    _assert_wire_error(record, "blocking evidence is not active")
    _assert_wire_error(record, "positive evidence lineage mismatch")

    metric_cases = (
        ("positive_evidence", 699_999, "group contribution mismatch"),
        ("counterevidence", 1, "group contribution mismatch"),
        ("net_evidence", 1, "weighted subtraction mismatch"),
        ("weighted_counterevidence", 1, "exceeds declared counterevidence"),
        ("counterevidence_ratio_ppm", 1, "exact ratio mismatch"),
        ("source_diversity", 2, "qualified domain count mismatch"),
        ("evidence_gates_satisfied", False, "gate conjunction mismatch"),
    )
    for field_name, value, fragment in metric_cases:
        record = _support_record("pheroos-evidence-summary-v1")
        record["payload"][field_name] = value
        _assert_wire_error(record, fragment)

    record = _support_record("pheroos-evidence-summary-v1")
    duplicate = deepcopy(record["payload"]["positive_groups"][0])
    record["payload"]["positive_groups"].append(duplicate)
    _assert_wire_error(record, "group order is not canonical")
    _assert_wire_error(record, "observation appears in multiple groups")

    record = _support_record("pheroos-evidence-summary-v1")
    record["payload"]["positive_groups"][0]["counted_contribution"] = 600_000
    _assert_wire_error(record, "cap mismatch")

    record = _support_record("pheroos-evidence-summary-v1")
    duplicate = deepcopy(record["payload"]["source_domains"][0])
    record["payload"]["source_domains"].append(duplicate)
    _assert_wire_error(record, "domain order is not canonical")
    _assert_wire_error(record, "observation appears in multiple domains")

    record = _support_record("pheroos-evidence-summary-v1")
    record["payload"]["source_domains"][0]["qualifies"] = False
    _assert_wire_error(record, "contribution floor mismatch")


def test_support_wire_membership_replay_evaluation_and_risk_semantics() -> None:
    record = _support_record("pheroos-eligible-principal-snapshot-v1")
    record["payload"]["eligible_clusters"].append(
        deepcopy(record["payload"]["eligible_clusters"][0])
    )
    _assert_wire_error(record, "cluster order is not canonical")
    _assert_wire_error(record, "principal appears in multiple clusters")
    _assert_wire_error(record, "verification is duplicated")

    record = _support_record("pheroos-eligible-principal-snapshot-v1")
    record["payload"]["eligible_clusters"][0]["principals"].append(
        deepcopy(record["payload"]["eligible_clusters"][0]["principals"][0])
    )
    _assert_wire_error(record, "principal order is not canonical")

    replay = _support_record("pheroos-support-lease-replay-state-v1")
    replay["payload"]["authority_key"] = _ROOT_A
    replay["payload"]["last_issued_at_step"] = 2
    _assert_wire_error(replay, "support replay authority mismatch")
    _assert_wire_error(replay, "predates replay initialization")

    replay = _support_record("pheroos-support-lease-replay-state-v1")
    duplicate = deepcopy(replay["payload"]["receipts"][0])
    duplicate["replay_receipt_fingerprint"] = _ROOT_A
    replay["payload"]["receipts"].append(duplicate)
    replay["payload"]["receipts"].reverse()
    _assert_wire_error(replay, "receipt order is not canonical")
    _assert_wire_error(replay, "duplicate lease_id")
    _assert_wire_error(replay, "duplicate proposal_fingerprint")
    _assert_wire_error(replay, "duplicate nonce")

    replay = _support_record("pheroos-support-lease-replay-state-v1")
    replay["payload"]["receipts"][0]["profile"] = "pheroos-certified-commit-v1"
    replay["payload"]["receipts"][0]["protocol_id"] = "protocol:other"
    replay["payload"]["receipts"][0]["assurance"] = "advisory"
    _assert_wire_error(replay, "replay state profile mismatch")
    _assert_wire_error(replay, "replay state protocol mismatch")
    _assert_wire_error(replay, "profile/assurance mismatch")

    replay = _support_record("pheroos-support-lease-replay-state-v1")
    replay["payload"]["revision"] = 0
    _assert_wire_error(replay, "receipt count mismatch")
    _assert_wire_error(replay, "initial support replay state has predecessor")
    _assert_wire_error(replay, "initial replay step mismatch")

    replay = _support_record("pheroos-support-lease-replay-state-v1")
    replay["payload"]["previous_state_fingerprint"] = ""
    _assert_wire_error(replay, "advanced replay state requires predecessor")

    evaluation = _support_record("pheroos-support-lease-evaluation-v1")
    evaluation["payload"]["equivocation_findings"].append(
        deepcopy(evaluation["payload"]["equivocation_findings"][0])
    )
    _assert_wire_error(evaluation, "order is not canonical")

    evaluation = _support_record("pheroos-support-lease-evaluation-v1")
    evaluation["payload"]["equivocation_findings"][0]["run_id"] = "run:other"
    _assert_wire_error(evaluation, "evaluation scope mismatch")

    count_cases = (
        ("active_support_cluster_count", 2, "cluster count mismatch"),
        ("support_ratio_ppm", 0, "exact ratio mismatch"),
        ("policy_support_met", True, "threshold result mismatch"),
    )
    for field_name, value, fragment in count_cases:
        evaluation = _support_record("pheroos-support-lease-evaluation-v1")
        evaluation["payload"][field_name] = value
        _assert_wire_error(evaluation, fragment)

    evaluation = _support_record("pheroos-support-lease-evaluation-v1")
    evaluation["payload"].update(
        active_support_cluster_count=2,
        active_support_clusters=["cluster:alpha", "cluster:beta"],
        eligible_cluster_count=1,
    )
    _assert_wire_error(evaluation, "exceeds membership")

    evaluation = _support_record("pheroos-support-lease-evaluation-v1")
    evaluation["payload"]["excluded_lease_fingerprints"].append(
        evaluation["payload"]["included_lease_fingerprints"][0]
    )
    _assert_wire_error(evaluation, "included and excluded lease sets overlap")

    evaluation = _support_record("pheroos-support-lease-evaluation-v1")
    evaluation["payload"]["excluded_lease_fingerprints"] = []
    _assert_wire_error(evaluation, "conflicts not excluded")

    evaluation = _support_record("pheroos-support-lease-evaluation-v1")
    evaluation["payload"]["active_support_clusters"].append("cluster:conflict")
    _assert_wire_error(evaluation, "equivocated cluster is active")

    chain = _support_record("pheroos-risk-assessment-chain-state-v1")
    chain["payload"]["last_issued_at_step"] = 20
    _assert_wire_error(chain, "outside chain interval")

    chain = _support_record("pheroos-risk-assessment-chain-state-v1")
    chain["payload"].update(
        latest_assessment_fingerprint=_ROOT_A,
        latest_risk_band="LOW",
        previous_state_fingerprint=_ROOT_B,
        last_issued_at_step=2,
    )
    _assert_wire_error(chain, "empty risk chain has a forged head")
    _assert_wire_error(chain, "empty chain must remain at initialization")

    chain = _support_record("pheroos-risk-assessment-chain-state-v1")
    chain["payload"]["revision"] = 1
    _assert_wire_error(chain, "non-empty risk chain is missing head lineage")

    assessment = _support_record("pheroos-risk-assessment-v1")
    assessment["payload"]["previous_assessment_fingerprint"] = _ROOT_A
    _assert_wire_error(assessment, "initial assessment cannot name a predecessor")

    assessment = _support_record("pheroos-risk-assessment-v1")
    assessment["payload"]["risk_chain_revision"] = 2
    _assert_wire_error(assessment, "reassessment requires predecessor")

    assessment = _support_record("pheroos-risk-assessment-v1")
    assessment["payload"]["window_reset_required"] = True
    _assert_wire_error(assessment, "initial assessment cannot require reset")


def _distributed_records(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    bundle = distributed_fixture._distributed_scenario(monkeypatch)
    certificate = distributed_fixture._certificate(
        bundle,
        bundle.verifications[:3],
        suffix="semantic-gaps",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    finality = evaluate_distributed_finality(
        registered,
        bundle.receipt,
        certificate=certificate,
        current_step=6,
    )
    profile = bundle.proposal.profile
    return (
        _wire(
            portable_membership_snapshot_payload(registered.membership_snapshot),
            schema="pheroos-portable-membership-snapshot-v1",
            profile=profile,
        ),
        _wire(
            witness_verification_payload(bundle.verifications[0]),
            schema="pheroos-witness-verification-v1",
            profile=profile,
        ),
        _wire(
            distributed_commit_state_payload(registered),
            schema="pheroos-distributed-commit-state-v1",
            profile=profile,
        ),
        _wire(
            distributed_commit_certificate_payload(certificate),
            schema="pheroos-distributed-commit-certificate-v1",
            profile=profile,
        ),
        _wire(
            distributed_finality_decision_payload(finality),
            schema="pheroos-distributed-finality-decision-v1",
            profile=profile,
        ),
    )


def test_distributed_wire_membership_witness_and_state_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    membership, verification, state, _, _ = _distributed_records(monkeypatch)

    mutated = deepcopy(membership)
    duplicate_cluster = deepcopy(mutated["payload"]["eligible_clusters"][0])
    duplicate_cluster["principals"][0]["principal_id"] = "principal:duplicate"
    duplicate_cluster["principals"][0]["principal_verification_fingerprint"] = _ROOT_C
    mutated["payload"]["eligible_clusters"].append(duplicate_cluster)
    _assert_wire_error(mutated, "cluster order/uniqueness mismatch")

    mutated = deepcopy(membership)
    duplicate_cluster = deepcopy(mutated["payload"]["eligible_clusters"][0])
    duplicate_cluster["cluster_id"] = "cluster:zzzz"
    mutated["payload"]["eligible_clusters"].append(duplicate_cluster)
    _assert_wire_error(mutated, "principal belongs to multiple clusters")
    _assert_wire_error(mutated, "verification is reused")
    _assert_wire_error(mutated, "reconstructable root mismatch")

    mutated = deepcopy(membership)
    duplicate_principal = deepcopy(
        mutated["payload"]["eligible_clusters"][0]["principals"][0]
    )
    duplicate_principal["principal_id"] = "principal:000"
    duplicate_principal["principal_verification_fingerprint"] = _ROOT_C
    mutated["payload"]["eligible_clusters"][0]["principals"].append(duplicate_principal)
    _assert_wire_error(mutated, "principal order mismatch")

    mutated = deepcopy(verification)
    mutated["payload"]["witness_fingerprint"] = _ROOT_A
    mutated["payload"]["witness_signing_root"] = _ROOT_B
    mutated["payload"]["expires_at_step"] = mutated["payload"]["verified_at_step"]
    _assert_wire_error(mutated, "witness_fingerprint")
    _assert_wire_error(mutated, "witness_signing_root")
    _assert_wire_error(mutated, "expiry must follow verification")

    mutated = deepcopy(verification)
    mutated["payload"]["expires_at_step"] = (
        mutated["payload"]["witness"]["expires_at_step"] + 1
    )
    _assert_wire_error(mutated, "exceeds witness expiry")

    authority_cases = (
        ("chain_id", _ROOT_A, "authority scope mismatch"),
        ("current_step", 5, "predates initialization"),
        ("membership_snapshot_root", _ROOT_A, "membership lineage mismatch"),
        ("membership_root", _ROOT_A, "membership lineage mismatch"),
        ("membership_size", 3, "snapshot cardinality mismatch"),
        ("minimum_failure_domain_diversity", 4, "unreachable"),
        ("witness_receipt_root", _ROOT_A, "reconstructable root mismatch"),
        ("frozen", True, "conflict projection mismatch"),
        ("transitioned", True, "epoch proof projection mismatch"),
    )
    for field_name, value, fragment in authority_cases:
        mutated = deepcopy(state)
        mutated["payload"][field_name] = value
        _assert_wire_error(mutated, fragment)

    mutated = deepcopy(state)
    mutated["payload"].update(
        membership_size=4,
        max_byzantine_faults=1,
        witness_quorum=2,
    )
    _assert_wire_error(mutated, "Byzantine quorum intersection is unsafe")

    mutated = deepcopy(state)
    mutated["payload"]["previous_state_fingerprint"] = ""
    _assert_wire_error(mutated, "advanced state lacks predecessor")

    mutated = deepcopy(state)
    mutated["payload"]["revision"] = 0
    _assert_wire_error(mutated, "initial state has predecessor")

    mutated = deepcopy(state)
    mutated["payload"]["run_id"] = "run:state-mismatch"
    _assert_wire_error(mutated, "state binding mismatch")

    mutated = deepcopy(state)
    mutated["payload"]["witness_verifications"].reverse()
    _assert_wire_error(mutated, "order is not canonical")

    mutated = deepcopy(state)
    mutated["payload"]["witness_verifications"][0]["witness"]["run_id"] = "run:other"
    _assert_wire_error(mutated, "state binding mismatch")

    mutated = deepcopy(state)
    mutated["payload"]["witness_verifications"][0]["witness"]["membership_root"] = (
        _ROOT_A
    )
    _assert_wire_error(mutated, "state binding mismatch")

    mutated = deepcopy(state)
    mutated["payload"]["excluded_cluster_ids"] = [
        mutated["payload"]["witness_verifications"][0]["witness"][
            "principal_cluster_id"
        ]
    ]
    _assert_wire_error(mutated, "equivocation projection mismatch")


def test_distributed_wire_certificate_and_finality_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, certificate, finality = _distributed_records(monkeypatch)

    certificate_cases = (
        ("membership_size", 3, "snapshot cardinality mismatch"),
        ("membership_snapshot_root", _ROOT_A, "lineage mismatch"),
        ("membership_root", _ROOT_A, "lineage mismatch"),
        ("minimum_failure_domain_diversity", 4, "unreachable"),
        ("candidate_id", "candidate:other", "proposal binding mismatch"),
        ("witness_root", _ROOT_A, "reconstructable root mismatch"),
        ("status", "provisional", "quorum/finality mismatch"),
        ("certificate_body_root", _ROOT_A, "reconstructable root mismatch"),
        ("certificate_root", _ROOT_A, "reconstructable root mismatch"),
    )
    for field_name, value, fragment in certificate_cases:
        mutated = deepcopy(certificate)
        mutated["payload"][field_name] = value
        _assert_wire_error(mutated, fragment)

    mutated = deepcopy(certificate)
    mutated["payload"].update(
        membership_size=4,
        max_byzantine_faults=1,
        witness_quorum=2,
    )
    _assert_wire_error(mutated, "Byzantine quorum intersection is unsafe")

    mutated = deepcopy(certificate)
    mutated["payload"]["issued_at_step"] = mutated["payload"]["membership_snapshot"][
        "expires_at_step"
    ]
    _assert_wire_error(mutated, "membership is not fresh")

    mutated = deepcopy(certificate)
    mutated["payload"]["witnesses"].reverse()
    _assert_wire_error(mutated, "order is not canonical")

    mutated = deepcopy(certificate)
    duplicate_witness = deepcopy(mutated["payload"]["witnesses"][0])
    duplicate_witness["verification_id"] = "verification:duplicate-cluster"
    mutated["payload"]["witnesses"].append(duplicate_witness)
    _assert_wire_error(mutated, "cluster counted twice")

    mutated = deepcopy(certificate)
    cluster_id = mutated["payload"]["witnesses"][0]["witness"]["principal_cluster_id"]
    mutated["payload"]["excluded_cluster_ids"] = [cluster_id]
    _assert_wire_error(mutated, "excluded cluster was counted")

    mutated = deepcopy(certificate)
    mutated["payload"]["witnesses"][0]["witness"]["proposal_digest"] = _ROOT_A
    _assert_wire_error(mutated, "certificate binding mismatch")

    mutated = deepcopy(finality)
    mutated["payload"]["kind"] = "pending"
    _assert_wire_error(mutated, "pending/provisional finality cannot be terminal")
    _assert_wire_error(mutated, "pending finality has proof")
    _assert_wire_error(mutated, "non-final decision claims commit")

    mutated = deepcopy(finality)
    mutated["payload"].update(
        kind="provisional",
        authoritative_commit=False,
        distributed_certificate_ref="",
    )
    _assert_wire_error(mutated, "provisional proof is absent")

    mutated = deepcopy(finality)
    mutated["payload"].update(
        authoritative_commit=False,
        distributed_certificate_ref="",
    )
    _assert_wire_error(mutated, "final distributed decision lacks authority")

    mutated = deepcopy(finality)
    mutated["payload"]["terminal"] = True
    _assert_wire_error(mutated, "terminal/outcome binding mismatch")

    mutated = deepcopy(finality)
    mutated["payload"].update(
        kind="finality_unavailable",
        authoritative_commit=False,
        distributed_certificate_ref="",
    )
    _assert_wire_error(mutated, "non-commit finality must be terminal")


def test_commit_state_public_type_guards_and_portability_fail_closed() -> None:
    for predicate in (
        decision_progress_is_authoritative,
        decision_outcome_is_authoritative,
        commit_finality_verification_is_authoritative,
        commit_window_state_is_authoritative,
        commit_window_state_is_current,
        commit_replay_state_is_authoritative,
        commit_replay_state_is_current,
    ):
        assert predicate(object()) is False

    for serializer in (
        decision_progress_payload,
        decision_outcome_payload,
        commit_finality_verification_payload,
        commit_window_state_payload,
        replay_receipt_payload,
        commit_replay_state_payload,
    ):
        with pytest.raises(GovernanceError, match="canonical record"):
            serializer(object())

    scenario, assessment, state = liveness_fixture._one_ready_step()
    facts = liveness_fixture._liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=5,
    )
    progress = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=facts,
    )
    _, _, _, _, _, outcome = output_fixture._evidence_commit_outcome()
    stable_scenario, stable_assessment, stable_state = liveness_fixture._stable_step()
    verification = liveness_fixture._verified_local_finality(
        stable_state,
        stable_scenario,
        stable_assessment,
        current_step=6,
    )

    assert decision_progress_is_authoritative(progress)
    assert decision_outcome_is_authoritative(outcome)
    assert commit_finality_verification_is_authoritative(verification)
    assert not decision_progress_is_authoritative(pickle.loads(pickle.dumps(progress)))
    assert not decision_outcome_is_authoritative(pickle.loads(pickle.dumps(outcome)))
    assert not commit_finality_verification_is_authoritative(
        pickle.loads(pickle.dumps(verification))
    )

    forged = copy(progress)
    object.__setattr__(forged, "phase", object())
    assert not decision_progress_is_authoritative(forged)
    forged_outcome = copy(outcome)
    object.__setattr__(forged_outcome, "kind", object())
    assert not decision_outcome_is_authoritative(forged_outcome)
    forged_verification = copy(verification)
    object.__setattr__(forged_verification, "status", object())
    assert not commit_finality_verification_is_authoritative(forged_verification)


def test_commit_window_replay_progress_and_outcome_record_invariants() -> None:
    initial_scenario = window_fixture._scenario()
    initial = window_fixture._window(initial_scenario)
    _, _, ready, _, _, _ = output_fixture._evidence_commit_outcome()
    seal = commit_window_seal_for_state(ready)
    assert seal is not None

    initial_cases = (
        ({"previous_state_fingerprint": _ROOT_A}, "cannot declare a predecessor"),
        ({"minimum_stability_steps": 0}, "threshold must be positive"),
        (
            {"last_evaluated_step": initial.initialized_at_step - 1},
            "evaluated before initialization",
        ),
        (
            {"last_evaluated_step": initial.absolute_deadline_step},
            "cannot survive its deadline",
        ),
        (
            {"absolute_deadline_step": initial.absolute_run_deadline_step + 1},
            "deadline exceeds run deadline",
        ),
        ({"last_ready": 1}, "must be boolean"),
        ({"authority": AuthorityLevel.OBSERVER}, "authority is invalid"),
        ({"last_context_ref": _ROOT_A}, "empty assessment lineage"),
        ({"leader_candidate_id": "candidate:forged"}, "empty window"),
        ({"window_root": _ROOT_A}, "does not match ordered assessments"),
    )
    for changes, fragment in initial_cases:
        with pytest.raises(GovernanceError, match=fragment):
            replace(initial, **changes)

    ready_cases = (
        ({"candidate_evidence_root": ""}, "lineage roots must be complete"),
        (
            {"ordered_assessment_refs": (ready.last_assessment_ref,) * 2},
            "lineage contains replay",
        ),
        ({"window_count": 0}, "requires positive count"),
        ({"window_count": 3}, "lineage must match window_count"),
        ({"last_assessment_status": "not_ready"}, "latest ready assessment"),
        ({"reset_budget_exhausted": True}, "cannot retain a ready window"),
    )
    for changes, fragment in ready_cases:
        with pytest.raises(GovernanceError, match=fragment):
            replace(ready, **changes)

    with pytest.raises(GovernanceError, match="sealed at its deadline"):
        replace(seal, sealed_at_step=seal.absolute_deadline_step)
    with pytest.raises(GovernanceError, match="seal deadline exceeds run deadline"):
        replace(seal, absolute_deadline_step=seal.absolute_run_deadline_step + 1)

    replay = window_fixture._replay(run_id="run:semantic-gap-replay")
    receipt = window_fixture._receipt(
        ReplayNamespace.OBSERVATION,
        "observation:semantic-gap",
        "nonce:semantic-gap",
        _ROOT_A,
    )
    advanced = record_commit_replay_receipts(
        replay,
        current_step=1,
        receipts=(receipt,),
    )
    assert commit_replay_state_contains(advanced, receipt)
    assert not commit_replay_state_contains(advanced, object())
    assert not commit_replay_state_matches(
        advanced,
        profile="invalid profile",
        assurance=advanced.assurance,
        manifest_root=advanced.manifest_root,
        commit_policy_root=advanced.commit_policy_root,
        protocol_id=advanced.protocol_id,
        run_id=advanced.run_id,
        current_step=advanced.current_step,
    )
    with pytest.raises(GovernanceError, match="assurance is invalid"):
        replace(replay, assurance="evidence_bound")
    with pytest.raises(
        GovernanceError, match="initial commit replay state must be empty"
    ):
        replace(replay, previous_state_fingerprint=_ROOT_A)
    with pytest.raises(
        GovernanceError, match="advanced commit replay state requires receipts"
    ):
        replace(advanced, receipts=())
    with pytest.raises(GovernanceError, match="authority is invalid"):
        replace(replay, authority=AuthorityLevel.OBSERVER)
    with pytest.raises(GovernanceError, match="namespace is invalid"):
        replace(receipt, namespace="observation")
    with pytest.raises(GovernanceError, match="candidate_id"):
        replace(receipt, candidate_id=" ")
    with pytest.raises(GovernanceError, match="principal_id"):
        replace(receipt, principal_id=" ")

    progress_scenario, progress_assessment, progress_state = (
        liveness_fixture._one_ready_step()
    )
    progress_facts = liveness_fixture._liveness(
        state=progress_state,
        scenario=progress_scenario,
        assessment=progress_assessment,
        current_step=5,
    )
    progress = reduce_commit_liveness(
        progress_state,
        commit_policy=progress_scenario.policy,
        liveness_input=progress_facts,
    )
    progress_cases = (
        ({"phase": "search"}, "phase is invalid"),
        ({"assurance": "evidence_bound"}, "assurance is invalid"),
        (
            {"current_step": progress.absolute_deadline_step},
            "at or after the absolute deadline",
        ),
        (
            {
                "current_step": progress.absolute_run_deadline_step,
                "absolute_deadline_step": progress.absolute_run_deadline_step + 1,
            },
            "at or after the run deadline",
        ),
        ({"minimum_stability_steps": 0}, "must be positive"),
        (
            {"absolute_deadline_step": progress.absolute_run_deadline_step + 1},
            "deadline exceeds the absolute run deadline",
        ),
        ({"context_ref": ""}, "lineage must co-exist"),
        ({"heartbeat_continuous": False}, "continuous heartbeat"),
        (
            {"next_required_inputs": (), "unmet_gates": ()},
            "required input or unmet gate",
        ),
    )
    for changes, fragment in progress_cases:
        with pytest.raises(GovernanceError, match=fragment):
            replace(progress, **changes)

    forged_progress = copy(progress)
    object.__setattr__(forged_progress, "terminal", True)
    with pytest.raises(GovernanceError, match="cannot be terminal"):
        decision_progress_payload(forged_progress)

    fallback = output_fixture._nonready_outcome(DecisionOutcomeKind.SAFE_FALLBACK)[2]
    outcome_cases = (
        ({"kind": "safe_fallback"}, "kind is invalid"),
        ({"assurance": "evidence_bound"}, "assurance is invalid"),
        ({"authority_scope": "none"}, "authority scope is invalid"),
        (
            {"absolute_deadline_step": fallback.absolute_run_deadline_step + 1},
            "deadline exceeds the absolute run deadline",
        ),
        ({"authoritative_commit": 1}, "must be a boolean"),
        ({"delivery_eligible": False}, "must be deliverable"),
        ({"context_ref": _ROOT_A}, "lineage must co-exist"),
        ({"reason_codes": ()}, "at least one reason code"),
        (
            {
                "reason_codes": ("deadline_reached",),
                "current_step": fallback.absolute_deadline_step - 1,
            },
            "before the absolute deadline",
        ),
        ({"authoritative_commit": True}, "non-commit outcome cannot carry"),
        ({"execution_eligible": True}, "cannot authorize execution"),
        ({"authority_scope": AuthorityScope.DENIAL}, "none authority scope"),
        ({"candidate_id": ""}, "fallback candidate is required"),
    )
    for changes, fragment in outcome_cases:
        with pytest.raises(GovernanceError, match=fragment):
            replace(fallback, **changes)

    forged_outcome = copy(fallback)
    object.__setattr__(forged_outcome, "terminal", False)
    with pytest.raises(GovernanceError, match="must be terminal"):
        decision_outcome_payload(forged_outcome)


def test_commit_liveness_and_finality_record_invariants() -> None:
    scenario, assessment, state = liveness_fixture._one_ready_step()
    facts = liveness_fixture._liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=5,
    )
    root = facts.risk_assessment_root
    cases = (
        ({"deadline_reached": 0}, "deadline_reached must be boolean"),
        ({"assessment_ref": ""}, "empty assessment cannot carry"),
        ({"candidate_evidence_root": ""}, "lineage roots must be complete"),
        ({"leader_ready_for_stability": 1}, "readiness must be boolean"),
        (
            {"leader_ready_for_stability": True, "leader_candidate_id": ""},
            "ready leader requires a candidate",
        ),
        ({"sealed_window": 1}, "sealed_window must be boolean"),
        ({"seal_ref": root}, "unsealed liveness cannot carry seal lineage"),
        ({"heartbeat_sequence": 1}, "heartbeat sequence must be zero"),
        (
            {"heartbeat_continuous": False},
            "only a sealed late-finality path",
        ),
        ({"finality_status": "pending"}, "finality status is invalid"),
        (
            {"finality_status": CommitFinalityStatus.VERIFIED},
            "requires a typed certificate verification",
        ),
        (
            {
                "finality_status": CommitFinalityStatus.PENDING,
                "certificate_ref": root,
            },
            "non-verified finality cannot carry",
        ),
        ({"authority": AuthorityLevel.OBSERVER}, "authority is invalid"),
    )
    for changes, fragment in cases:
        with pytest.raises(GovernanceError, match=fragment):
            replace(facts, **changes)

    stable_scenario, stable_assessment, stable_state = liveness_fixture._stable_step()
    verification = liveness_fixture._verified_local_finality(
        stable_state,
        stable_scenario,
        stable_assessment,
        current_step=6,
    )
    with pytest.raises(GovernanceError, match="must be verified"):
        replace(verification, status=CommitFinalityStatus.PENDING)
    with pytest.raises(GovernanceError, match="kind does not match assurance"):
        replace(verification, certificate_kind="evidence_commit_certificate")
    with pytest.raises(GovernanceError, match="verifier authority is invalid"):
        replace(verification, authority=AuthorityLevel.OBSERVER)

    verified_facts = liveness_fixture._liveness(
        stable_state,
        stable_scenario,
        assessment=stable_assessment,
        current_step=6,
        finality_status=CommitFinalityStatus.VERIFIED,
        finality_verification=verification,
    )
    with pytest.raises(GovernanceError, match="continuous receipt-backed seal"):
        replace(verified_facts, heartbeat_continuous=False)
