from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from pheroos.governance._commit_evidence_projection_v2.evaluation import (
    _saturating_scaled_product,
    _saturating_signed,
    _saturating_sum,
)
from pheroos.governance.commit_evidence_v2 import (
    ChallengeResultV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceEvaluationV2,
    CommitEvidenceKindV2,
    CommitEvidencePolicySnapshotV2,
    CommitEvidenceProjectionV2,
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
    evaluate_commit_evidence_projection_v2,
)
from pheroos.governance.commit_numeric import MAX_AUTHORITY_INTEGER, WEIGHT_SCALE
from pheroos.protocol.commit_models import CommitAssurance


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode()).hexdigest()


def _policy(**changes: object) -> CommitEvidencePolicySnapshotV2:
    values: dict[str, object] = {
        "numeric_scale": WEIGHT_SCALE,
        "minimum_quality_ppm": 1,
        "minimum_relevance_ppm": 1,
        "positive_group_cap": 1_500_000,
        "counter_group_cap": 1_500_000,
        "counter_weight_ppm": WEIGHT_SCALE,
        "minimum_positive_evidence": 1,
        "maximum_counterevidence": MAX_AUTHORITY_INTEGER,
        "maximum_counterevidence_ratio_ppm": WEIGHT_SCALE,
        "domain_contribution_floor": 1,
        "minimum_source_diversity": 1,
        "required_challenge_categories": ("category:required",),
        "observation_ttl_steps": 100,
        "require_provenance": True,
        "require_trace": True,
        "extensions_root": _root("extensions"),
    }
    values.update(changes)
    return CommitEvidencePolicySnapshotV2(**values)  # type: ignore[arg-type]


def _record(
    index: int,
    *,
    kind: CommitEvidenceKindV2 = CommitEvidenceKindV2.POSITIVE,
    candidate: str = "candidate:a",
    claim: str | None = None,
    cluster: str | None = None,
    domain: str | None = None,
    independence: str | None = None,
) -> QualifiedCommitEvidenceV2:
    counter = kind is CommitEvidenceKindV2.COUNTER
    challenge = kind is CommitEvidenceKindV2.CHALLENGE
    return QualifiedCommitEvidenceV2(
        record_ref=f"evidence:{index}",
        kind=kind,
        status=CommitEvidenceStatusV2.ACTIVE,
        candidate_ref=candidate,
        claim_root=claim or _root("claim:a"),
        epoch=1,
        principal_ref=f"principal:{index}",
        cluster_ref=cluster or f"cluster:{index}",
        failure_domain_ref=domain or f"domain:{index}",
        membership_principal_root=_root(f"membership-principal:{index}"),
        principal_verification_root=_root(f"principal-verification:{index}"),
        attestation_root=_root(f"attestation:{index}"),
        payload_root=_root(f"payload:{index}"),
        source_ref="" if challenge else f"source:{index}",
        independence_ref="" if challenge else (independence or f"group:{index}"),
        quality_ppm=0 if challenge else WEIGHT_SCALE,
        relevance_ppm=0 if challenge else WEIGHT_SCALE,
        materiality_ppm=0,
        criticality_ppm=0,
        weight_ppm=0 if challenge else WEIGHT_SCALE,
        category_ref="category:required" if challenge else "",
        execution_method="deterministic" if challenge else "",
        execution_attestation_root=_root(f"execution-attestation:{index}")
        if challenge
        else "",
        execution_root=_root(f"execution:{index}") if challenge else "",
        challenge_result=ChallengeResultV2.NO_COUNTEREVIDENCE
        if challenge
        else ChallengeResultV2.NONE,
        result_root=_root(f"result:{index}") if challenge else "",
        result_observation_roots=(),
        disposition=CommitEvidenceDispositionV2.UNRESOLVED
        if counter
        else CommitEvidenceDispositionV2.NONE,
        disposition_ref=f"disposition:{index}" if counter else "",
        disposition_nonce=f"disposition-nonce:{index}" if counter else "",
        disposition_root=_root(f"disposition:{index}") if counter else "",
        rebuttal_observation_roots=(),
        resolution_root="",
        reason_codes=("reason:counter",) if counter else (),
        nonce=f"nonce:{index}",
        observed_at_step=1,
        qualified_at_step=1,
        expires_at_step=100,
        qualification_issuer_ref="issuer:evidence",
        qualification_root=_root(f"qualification:{index}"),
        qualification_policy_root=_root("placeholder-policy"),
        membership_root=_root("membership"),
        verification_set_root=_root("verification"),
        attestation_provenance_root=_root(f"attestation-provenance:{index}"),
        attestation_trace_roots=(_root(f"attestation-trace:{index}"),),
        qualification_provenance_root=_root(f"qualification-provenance:{index}"),
        qualification_trace_roots=(_root(f"qualification-trace:{index}"),),
        revoked_at_step=None,
        revocation_root="",
        revocation_provenance_root="",
        revocation_trace_roots=(),
        replay_receipt_roots=(
            (_root(f"replay:{index}:observation"), _root(f"replay:{index}:disposition"))
            if counter
            else (_root(f"replay:{index}"),)
        ),
    )


def _projection(
    records: tuple[QualifiedCommitEvidenceV2, ...],
    *,
    policy: CommitEvidencePolicySnapshotV2 | None = None,
) -> CommitEvidenceProjectionV2:
    policy = policy or _policy()
    bound = tuple(
        replace(item, qualification_policy_root=policy.policy_root, record_root="")
        for item in records
    )
    return CommitEvidenceProjectionV2(
        domain_root=_root("domain"),
        scope_ref="scope:test",
        manifest_root=_root("manifest"),
        commit_policy_root=_root("commit-policy"),
        evidence_policy=policy,
        profile="pheroos-hybrid-commit-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref="protocol:test",
        run_ref="run:test",
        target_ref="target:test",
        epoch=1,
        current_step=2,
        stream_ref="authority:commit-evidence-v2:" + "a" * 64,
        revision=1,
        transition_id="transition:commit-evidence-v2:" + "b" * 64,
        snapshot_root=_root("snapshot"),
        head_root=_root("head"),
        receipt_root=_root("receipt"),
        membership_stream_ref="authority:membership-v2:" + "c" * 64,
        membership_transition_id="transition:membership-v2:" + "d" * 64,
        membership_head_root=_root("membership-head"),
        membership_snapshot_root=_root("membership-snapshot"),
        membership_root=_root("membership"),
        verification_stream_ref="authority:principal-verification-v2:" + "e" * 64,
        verification_transition_id="transition:principal-verification-v2:" + "f" * 64,
        verification_head_root=_root("verification-head"),
        verification_snapshot_root=_root("verification-snapshot"),
        verification_set_root=_root("verification"),
        records=bound,
    )


def _evaluate(projection: CommitEvidenceProjectionV2) -> CommitEvidenceEvaluationV2:
    replay = tuple(
        root for record in projection.records for root in record.replay_receipt_roots
    )
    return evaluate_commit_evidence_projection_v2(
        projection,
        candidate_ref="candidate:a",
        claim_root=_root("claim:a"),
        replay_receipt_roots=replay,
    )


def test_caps_are_by_independence_group_not_cluster() -> None:
    challenge = _record(90, kind=CommitEvidenceKindV2.CHALLENGE)
    same_group = _projection(
        (
            _record(1, cluster="cluster:a", independence="group:same"),
            _record(2, cluster="cluster:b", independence="group:same"),
            challenge,
        )
    )
    same_cluster = _projection(
        (
            _record(3, cluster="cluster:same", independence="group:a"),
            _record(4, cluster="cluster:same", independence="group:b"),
            _record(91, kind=CommitEvidenceKindV2.CHALLENGE),
        )
    )
    assert _evaluate(same_group).positive_evidence == 1_500_000
    assert _evaluate(same_cluster).positive_evidence == 2_000_000


def test_counter_caps_are_by_independence_group_and_order_is_canonical() -> None:
    records = (
        _record(1, kind=CommitEvidenceKindV2.POSITIVE),
        _record(2, kind=CommitEvidenceKindV2.COUNTER, independence="counter:same"),
        _record(3, kind=CommitEvidenceKindV2.COUNTER, independence="counter:same"),
        _record(90, kind=CommitEvidenceKindV2.CHALLENGE),
    )
    forward = _projection(records)
    reverse = _projection(tuple(reversed(records)))
    assert _evaluate(forward).counterevidence == 1_500_000
    assert _evaluate(forward).evaluation_root == _evaluate(reverse).evaluation_root


def test_candidate_and_claim_are_exact_evaluation_subjects() -> None:
    projection = _projection(
        (
            _record(1),
            _record(2, candidate="candidate:b", claim=_root("claim:b")),
            _record(90, kind=CommitEvidenceKindV2.CHALLENGE),
        )
    )
    evaluation = _evaluate(projection)
    assert evaluation.candidate_ref == "candidate:a"
    assert evaluation.claim_root == _root("claim:a")
    assert evaluation.positive_evidence == WEIGHT_SCALE


def test_authority_arithmetic_saturates_before_canonical_output() -> None:
    assert _saturating_sum((MAX_AUTHORITY_INTEGER, 1)) == MAX_AUTHORITY_INTEGER
    assert (
        _saturating_scaled_product(MAX_AUTHORITY_INTEGER, MAX_AUTHORITY_INTEGER)
        == MAX_AUTHORITY_INTEGER
    )
    assert _saturating_signed(-MAX_AUTHORITY_INTEGER - 1) == -MAX_AUTHORITY_INTEGER


def test_evaluation_wire_rejects_bool_as_int_and_overflow() -> None:
    evaluation = _evaluate(
        _projection(
            (
                _record(1),
                _record(90, kind=CommitEvidenceKindV2.CHALLENGE),
            )
        )
    )
    assert CommitEvidenceEvaluationV2.from_dict(evaluation.to_dict()) == evaluation
    bool_payload = evaluation.to_dict()
    bool_payload["positive_evidence"] = True
    with pytest.raises(ValueError, match="positive_evidence"):
        CommitEvidenceEvaluationV2.from_dict(bool_payload)
    overflow = evaluation.to_dict()
    overflow["weighted_counterevidence"] = MAX_AUTHORITY_INTEGER + 1
    with pytest.raises(ValueError, match="weighted_counterevidence"):
        CommitEvidenceEvaluationV2.from_dict(overflow)


def test_counter_weight_saturates_and_net_has_negative_bound() -> None:
    policy = _policy(counter_weight_ppm=MAX_AUTHORITY_INTEGER)
    evaluation = _evaluate(
        _projection(
            (
                _record(1),
                _record(2, kind=CommitEvidenceKindV2.COUNTER),
                _record(90, kind=CommitEvidenceKindV2.CHALLENGE),
            ),
            policy=policy,
        )
    )
    assert evaluation.weighted_counterevidence == MAX_AUTHORITY_INTEGER
    assert evaluation.net_evidence == 1_000_000 - MAX_AUTHORITY_INTEGER
