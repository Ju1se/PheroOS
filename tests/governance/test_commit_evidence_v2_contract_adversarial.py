from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from pheroos.governance.commit_evidence_v2 import (
    ChallengeResultV2,
    CommitEvidenceAttestationV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceEvaluationV2,
    CommitEvidenceKindV2,
    CommitEvidencePolicySnapshotV2,
    CommitEvidenceProjectionV2,
    CommitEvidenceRevocationV2,
    CommitEvidenceStatusV2,
    CounterevidenceDispositionProposalV2,
    QualifiedCommitEvidenceV2,
    commit_evidence_replay_receipts_for_proposals_v2,
    evaluate_commit_evidence_projection_v2,
)
from pheroos.governance.commit_numeric import WEIGHT_SCALE
from tests.governance.test_commit_evidence_v2_operations import _attestations, _root
from tests.governance.test_commit_evidence_v2_evaluation import (
    _evaluate,
    _policy,
    _projection,
    _record,
)


TARGET = "target:commit-evidence:contract"


def _counter_attestation() -> CommitEvidenceAttestationV2:
    positive, _challenge = _attestations(claim_root=_root("claim:contract"))
    return replace(
        positive,
        evidence_ref="evidence:counter",
        kind=CommitEvidenceKindV2.COUNTER,
        nonce="nonce:counter",
        attestation_root="",
    )


def _disposition(
    counter: CommitEvidenceAttestationV2,
    disposition: CommitEvidenceDispositionV2 = CommitEvidenceDispositionV2.UNRESOLVED,
) -> CounterevidenceDispositionProposalV2:
    rebutted = disposition is CommitEvidenceDispositionV2.REBUTTED
    unresolved = disposition is CommitEvidenceDispositionV2.UNRESOLVED
    return CounterevidenceDispositionProposalV2(
        disposition_ref=f"disposition:{disposition.value}",
        counter_attestation_root=counter.attestation_root,
        disposition=disposition,
        rebuttal_observation_roots=(_root("rebuttal"),) if rebutted else (),
        resolution_root="" if unresolved else _root(f"resolution:{disposition.value}"),
        reason_codes=(f"reason:{disposition.value}",),
        nonce=f"nonce:disposition:{disposition.value}",
        issued_at_step=4,
        expires_at_step=20,
        provenance_root=_root("provenance:disposition"),
        trace_roots=(_root("trace:disposition"),),
    )


def _revocation(record_root: str | None = None) -> CommitEvidenceRevocationV2:
    return CommitEvidenceRevocationV2(
        revocation_ref="revocation:one",
        record_ref="evidence:positive",
        record_root=record_root or _root("record:positive"),
        revoked_at_step=8,
        reason_codes=("reason:withdrawn",),
        provenance_root=_root("provenance:revocation"),
        trace_roots=(_root("trace:revocation"),),
    )


def test_attestation_wire_round_trip_and_every_kind_are_canonical() -> None:
    positive, challenge = _attestations(claim_root=_root("claim:contract"))
    counter = _counter_attestation()
    found = replace(
        challenge,
        challenge_result=ChallengeResultV2.COUNTEREVIDENCE_FOUND,
        result_observation_roots=(_root("result:observation"),),
        attestation_root="",
    )

    for item in (positive, counter, challenge, found):
        assert CommitEvidenceAttestationV2.from_dict(item.to_dict()) == item

    receipts = commit_evidence_replay_receipts_for_proposals_v2(
        (challenge, positive, counter),
        (_disposition(counter),),
        target_ref=TARGET,
    )
    assert len(receipts) == 4
    assert tuple(item.receipt_root for item in receipts) == tuple(
        sorted(item.receipt_root for item in receipts)
    )


def test_attestation_constructor_rejects_malformed_authority_meaning() -> None:
    positive, challenge = _attestations(claim_root=_root("claim:contract"))
    malformed = (
        lambda: replace(positive, schema="unsupported"),
        lambda: replace(positive, kind=cast(CommitEvidenceKindV2, "positive")),
        lambda: replace(positive, challenge_result=cast(ChallengeResultV2, "none")),
        lambda: replace(positive, evidence_ref=""),
        lambda: replace(positive, claim_root="not-a-root"),
        lambda: replace(positive, epoch=True),
        lambda: replace(positive, reported_quality_ppm=WEIGHT_SCALE + 1),
        lambda: replace(positive, expires_at_step=positive.observed_at_step),
        lambda: replace(positive, trace_roots=()),
        lambda: replace(positive, category_ref="category:forged"),
        lambda: replace(challenge, category_ref=""),
        lambda: replace(challenge, source_ref="source:forged"),
        lambda: replace(challenge, challenge_result=ChallengeResultV2.NONE),
        lambda: replace(
            challenge,
            result_observation_roots=(_root("unexpected-result"),),
        ),
        lambda: replace(positive, attestation_root=_root("forged-attestation-root")),
    )
    for build in malformed:
        with pytest.raises((TypeError, ValueError)):
            build()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("kind", "unsupported"),
        ("challenge_result", "unsupported"),
        ("result_observation_roots", "not-an-array"),
        ("trace_roots", "not-an-array"),
    ],
)
def test_attestation_wire_decoder_rejects_invalid_enum_and_array_shape(
    field_name: str,
    value: object,
) -> None:
    positive, _challenge = _attestations(claim_root=_root("claim:wire"))
    payload = positive.to_dict()
    payload[field_name] = value
    with pytest.raises((TypeError, ValueError)):
        CommitEvidenceAttestationV2.from_dict(payload)


def test_attestation_wire_decoder_rejects_noncanonical_and_inexact_objects() -> None:
    positive, _challenge = _attestations(claim_root=_root("claim:wire"))
    reordered = positive.to_dict()
    reordered["trace_roots"] = [
        _root("trace:z"),
        _root("trace:a"),
    ]
    with pytest.raises(ValueError):
        CommitEvidenceAttestationV2.from_dict(reordered)

    for payload in (None, {**positive.to_dict(), "extra": True}):
        with pytest.raises((TypeError, ValueError)):
            CommitEvidenceAttestationV2.from_dict(payload)


def test_disposition_variants_round_trip_and_bind_counter_replay() -> None:
    counter = _counter_attestation()
    for disposition in (
        CommitEvidenceDispositionV2.UNRESOLVED,
        CommitEvidenceDispositionV2.REBUTTED,
        CommitEvidenceDispositionV2.ACCEPTED,
        CommitEvidenceDispositionV2.IMMATERIAL,
    ):
        proposal = _disposition(counter, disposition)
        assert CounterevidenceDispositionProposalV2.from_dict(proposal.to_dict()) == (
            proposal
        )
        receipts = commit_evidence_replay_receipts_for_proposals_v2(
            (counter,),
            (proposal,),
            target_ref=TARGET,
        )
        assert len(receipts) == 2


def test_disposition_constructor_rejects_invalid_resolution_semantics() -> None:
    counter = _counter_attestation()
    unresolved = _disposition(counter)
    rebutted = _disposition(counter, CommitEvidenceDispositionV2.REBUTTED)
    accepted = _disposition(counter, CommitEvidenceDispositionV2.ACCEPTED)
    malformed = (
        lambda: replace(unresolved, schema="unsupported"),
        lambda: replace(unresolved, disposition=CommitEvidenceDispositionV2.NONE),
        lambda: replace(
            unresolved,
            disposition=cast(CommitEvidenceDispositionV2, "unresolved"),
        ),
        lambda: replace(unresolved, disposition_ref=""),
        lambda: replace(unresolved, counter_attestation_root="not-a-root"),
        lambda: replace(unresolved, reason_codes=()),
        lambda: replace(unresolved, trace_roots=()),
        lambda: replace(unresolved, expires_at_step=unresolved.issued_at_step),
        lambda: replace(unresolved, resolution_root=_root("forged-resolution")),
        lambda: replace(rebutted, rebuttal_observation_roots=()),
        lambda: replace(
            accepted, rebuttal_observation_roots=(_root("unexpected-rebuttal"),)
        ),
        lambda: replace(accepted, resolution_root=""),
        lambda: replace(unresolved, disposition_root=_root("forged-disposition-root")),
    )
    for build in malformed:
        with pytest.raises((TypeError, ValueError)):
            build()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("disposition", "unsupported"),
        ("rebuttal_observation_roots", "not-an-array"),
        ("reason_codes", "not-an-array"),
        ("trace_roots", "not-an-array"),
    ],
)
def test_disposition_wire_decoder_rejects_invalid_enum_and_array_shape(
    field_name: str,
    value: object,
) -> None:
    proposal = _disposition(_counter_attestation())
    payload = proposal.to_dict()
    payload[field_name] = value
    with pytest.raises((TypeError, ValueError)):
        CounterevidenceDispositionProposalV2.from_dict(payload)


def test_revocation_round_trip_and_invalid_meaning() -> None:
    revocation = _revocation()
    assert CommitEvidenceRevocationV2.from_dict(revocation.to_dict()) == revocation

    malformed = (
        lambda: replace(revocation, schema="unsupported"),
        lambda: replace(revocation, revocation_ref=""),
        lambda: replace(revocation, record_root="not-a-root"),
        lambda: replace(revocation, revoked_at_step=True),
        lambda: replace(revocation, reason_codes=()),
        lambda: replace(revocation, trace_roots=()),
        lambda: replace(revocation, revocation_root=_root("forged-revocation-root")),
    )
    for build in malformed:
        with pytest.raises((TypeError, ValueError)):
            build()

    for field_name in ("reason_codes", "trace_roots"):
        payload = revocation.to_dict()
        payload[field_name] = "not-an-array"
        with pytest.raises((TypeError, ValueError)):
            CommitEvidenceRevocationV2.from_dict(payload)


def test_public_replay_projection_rejects_nonexact_duplicate_and_unbound_inputs() -> (
    None
):
    positive, _challenge = _attestations(claim_root=_root("claim:replay"))
    duplicate = replace(
        positive,
        payload_root=_root("payload:duplicate"),
        attestation_root="",
    )
    counter = _counter_attestation()
    disposition = _disposition(counter)

    invalid_calls = (
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            cast(tuple[CommitEvidenceAttestationV2, ...], set()),
            (),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            cast(list[CommitEvidenceAttestationV2], [object()]),
            (),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            cast(tuple[CommitEvidenceAttestationV2, ...], (positive, duplicate)),
            (),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            (counter,),
            (),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            (positive,),
            (disposition,),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            (positive,),
            cast(tuple[CounterevidenceDispositionProposalV2, ...], set()),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            (positive,),
            cast(tuple[CounterevidenceDispositionProposalV2, ...], (object(),)),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            (counter,),
            (disposition, disposition),
            target_ref=TARGET,
        ),
        lambda: commit_evidence_replay_receipts_for_proposals_v2(
            (positive,),
            (),
            target_ref="",
        ),
    )
    for call in invalid_calls:
        with pytest.raises((TypeError, ValueError)):
            call()


def test_policy_wire_round_trip_and_constructor_bounds() -> None:
    policy = _policy()
    assert CommitEvidencePolicySnapshotV2.from_dict(policy.to_dict()) == policy

    invalid = (
        lambda: replace(policy, schema="unsupported"),
        lambda: replace(policy, numeric_scale=1),
        lambda: replace(policy, minimum_quality_ppm=WEIGHT_SCALE + 1),
        lambda: replace(policy, positive_group_cap=0),
        lambda: replace(policy, maximum_counterevidence=-1),
        lambda: replace(policy, required_challenge_categories=()),
        lambda: replace(policy, require_provenance=False),
        lambda: replace(policy, require_trace=False),
        lambda: replace(policy, extensions_root="not-a-root"),
        lambda: replace(policy, policy_root=_root("forged-policy-root")),
    )
    for build in invalid:
        with pytest.raises((TypeError, ValueError)):
            build()

    payload = policy.to_dict()
    payload["required_challenge_categories"] = "not-an-array"
    with pytest.raises((TypeError, ValueError)):
        CommitEvidencePolicySnapshotV2.from_dict(payload)


def test_qualified_record_variants_round_trip() -> None:
    positive = _record(1)
    counter = _record(2, kind=CommitEvidenceKindV2.COUNTER)
    challenge = _record(3, kind=CommitEvidenceKindV2.CHALLENGE)
    found = replace(
        challenge,
        challenge_result=ChallengeResultV2.COUNTEREVIDENCE_FOUND,
        result_observation_roots=(_root("challenge:found"),),
        record_root="",
    )
    rebutted = replace(
        counter,
        disposition=CommitEvidenceDispositionV2.REBUTTED,
        rebuttal_observation_roots=(_root("counter:rebuttal"),),
        resolution_root=_root("counter:rebutted"),
        record_root="",
    )
    accepted = replace(
        counter,
        disposition=CommitEvidenceDispositionV2.ACCEPTED,
        resolution_root=_root("counter:accepted"),
        record_root="",
    )
    revoked = replace(
        positive,
        status=CommitEvidenceStatusV2.REVOKED,
        revoked_at_step=2,
        revocation_root=_root("revocation:positive"),
        revocation_provenance_root=_root("revocation:provenance"),
        revocation_trace_roots=(_root("revocation:trace"),),
        record_root="",
    )
    for record in (
        positive,
        counter,
        challenge,
        found,
        rebutted,
        accepted,
        revoked,
    ):
        assert QualifiedCommitEvidenceV2.from_dict(record.to_dict()) == record


def test_qualified_record_rejects_invalid_base_and_kind_semantics() -> None:
    positive = _record(1)
    counter = _record(2, kind=CommitEvidenceKindV2.COUNTER)
    challenge = _record(3, kind=CommitEvidenceKindV2.CHALLENGE)
    invalid = (
        lambda: replace(positive, schema="unsupported"),
        lambda: replace(positive, kind=cast(CommitEvidenceKindV2, "positive")),
        lambda: replace(positive, status=cast(CommitEvidenceStatusV2, "active")),
        lambda: replace(positive, record_ref=""),
        lambda: replace(positive, claim_root="not-a-root"),
        lambda: replace(positive, epoch=True),
        lambda: replace(positive, quality_ppm=WEIGHT_SCALE + 1),
        lambda: replace(positive, weight_ppm=1),
        lambda: replace(positive, source_ref=""),
        lambda: replace(positive, category_ref="category:forged"),
        lambda: replace(
            positive,
            disposition=CommitEvidenceDispositionV2.ACCEPTED,
            disposition_ref="disposition:forged",
            disposition_nonce="nonce:disposition:forged",
            disposition_root=_root("disposition:forged"),
            resolution_root=_root("resolution:forged"),
            reason_codes=("reason:forged",),
        ),
        lambda: replace(positive, replay_receipt_roots=()),
        lambda: replace(
            positive,
            replay_receipt_roots=(
                _root("replay:unexpected:one"),
                _root("replay:unexpected:two"),
            ),
        ),
        lambda: replace(challenge, category_ref=""),
        lambda: replace(challenge, challenge_result=ChallengeResultV2.NONE),
        lambda: replace(challenge, source_ref="source:forged"),
        lambda: replace(challenge, quality_ppm=1, weight_ppm=0),
        lambda: replace(
            challenge,
            result_observation_roots=(_root("unexpected-result"),),
        ),
        lambda: replace(counter, disposition=CommitEvidenceDispositionV2.NONE),
        lambda: replace(counter, disposition_ref=""),
        lambda: replace(counter, disposition_root=""),
        lambda: replace(counter, reason_codes=()),
        lambda: replace(
            counter,
            disposition=CommitEvidenceDispositionV2.REBUTTED,
            resolution_root=_root("counter:rebutted"),
        ),
        lambda: replace(
            counter,
            disposition=CommitEvidenceDispositionV2.ACCEPTED,
            rebuttal_observation_roots=(_root("unexpected-rebuttal"),),
            resolution_root=_root("counter:accepted"),
        ),
        lambda: replace(counter, resolution_root=_root("unresolved-cannot-resolve")),
    )
    for build in invalid:
        with pytest.raises((TypeError, ValueError)):
            build()


def test_qualified_record_rejects_invalid_interval_revocation_and_wire() -> None:
    positive = _record(1)
    invalid = (
        lambda: replace(positive, qualified_at_step=0),
        lambda: replace(positive, expires_at_step=positive.qualified_at_step),
        lambda: replace(positive, revoked_at_step=2),
        lambda: replace(
            positive,
            status=CommitEvidenceStatusV2.REVOKED,
            revoked_at_step=0,
            revocation_root=_root("revocation"),
            revocation_provenance_root=_root("revocation:provenance"),
            revocation_trace_roots=(_root("revocation:trace"),),
        ),
        lambda: replace(
            positive,
            status=CommitEvidenceStatusV2.REVOKED,
            revoked_at_step=2,
            revocation_root="",
            revocation_provenance_root=_root("revocation:provenance"),
            revocation_trace_roots=(_root("revocation:trace"),),
        ),
        lambda: replace(
            positive,
            status=CommitEvidenceStatusV2.REVOKED,
            revoked_at_step=2,
            revocation_root=_root("revocation"),
            revocation_provenance_root=_root("revocation:provenance"),
            revocation_trace_roots=(),
        ),
        lambda: replace(positive, record_root=_root("forged-record-root")),
    )
    for build in invalid:
        with pytest.raises((TypeError, ValueError)):
            build()

    for field_name in (
        "kind",
        "status",
        "challenge_result",
        "disposition",
    ):
        payload = positive.to_dict()
        payload[field_name] = "unsupported"
        with pytest.raises(ValueError):
            QualifiedCommitEvidenceV2.from_dict(payload)
    payload = positive.to_dict()
    payload["trace_roots"] = "not-an-array"
    with pytest.raises((TypeError, ValueError)):
        QualifiedCommitEvidenceV2.from_dict(payload)


def test_projection_rejects_duplicate_qualified_record_identities() -> None:
    positive = _record(1)
    duplicate_ref = replace(
        positive,
        payload_root=_root("payload:duplicate-ref"),
        record_root="",
    )
    duplicate_nonce = replace(
        positive,
        record_ref="evidence:duplicate-nonce",
        payload_root=_root("payload:duplicate-nonce"),
        record_root="",
    )
    for records in (
        (positive, duplicate_ref),
        (positive, duplicate_nonce),
        cast(tuple[QualifiedCommitEvidenceV2, ...], (object(),)),
    ):
        with pytest.raises((TypeError, ValueError)):
            _projection(records)


def test_projection_rejects_duplicate_disposition_identities() -> None:
    first = _record(1, kind=CommitEvidenceKindV2.COUNTER)
    second = _record(2, kind=CommitEvidenceKindV2.COUNTER)
    base = _projection((first,))
    duplicate_nonce = replace(
        second,
        disposition_nonce=first.disposition_nonce,
        record_root="",
    )
    duplicate_root = replace(
        second,
        disposition_root=first.disposition_root,
        record_root="",
    )
    intersects_record_nonce = replace(
        second,
        disposition_nonce=first.nonce,
        record_root="",
    )
    for records in (
        (first, duplicate_nonce),
        (first, duplicate_root),
        (first, intersects_record_nonce),
    ):
        with pytest.raises(ValueError, match="disposition identity"):
            replace(base, records=records, projection_root="")

    with pytest.raises(TypeError, match="bounded array"):
        replace(
            base,
            records=cast(tuple[QualifiedCommitEvidenceV2, ...], set()),
            projection_root="",
        )
    with pytest.raises(TypeError, match="non-exact"):
        replace(
            base,
            records=cast(tuple[QualifiedCommitEvidenceV2, ...], (object(),)),
            projection_root="",
        )


def test_public_contracts_reject_noncanonical_text_collections_and_oversized_wire() -> (
    None
):
    positive, _challenge = _attestations(claim_root=_root("claim:canonical"))
    policy = _policy()

    invalid = (
        lambda: replace(positive, evidence_ref=" evidence:spaced"),
        lambda: replace(positive, evidence_ref="x" * 4_097),
        lambda: replace(
            positive,
            trace_roots=(positive.trace_roots[0], positive.trace_roots[0]),
        ),
        lambda: replace(
            positive,
            result_observation_roots=cast(tuple[str, ...], set()),
        ),
        lambda: replace(
            policy,
            required_challenge_categories=("category:a", "category:a"),
        ),
        lambda: replace(
            policy,
            required_challenge_categories=cast(tuple[str, ...], set()),
        ),
    )
    for build in invalid:
        with pytest.raises((TypeError, ValueError)):
            build()

    payload = positive.to_dict()
    payload["trace_roots"] = [_root(f"trace:{index}") for index in range(16_385)]
    with pytest.raises(ValueError, match="item bound"):
        CommitEvidenceAttestationV2.from_dict(payload)

    with_two_traces = replace(
        positive,
        trace_roots=(_root("trace:a"), _root("trace:z")),
        attestation_root="",
    )
    noncanonical = with_two_traces.to_dict()
    noncanonical["trace_roots"] = list(
        reversed(cast(list[str], noncanonical["trace_roots"]))
    )
    with pytest.raises(ValueError, match="canonical wire"):
        CommitEvidenceAttestationV2.from_dict(noncanonical)


def test_projection_round_trip_context_and_root_invariants() -> None:
    base = _projection((_record(1), _record(2)))
    assert CommitEvidenceProjectionV2.from_dict(base.to_dict()) == base

    invalid = (
        lambda: replace(base, schema="unsupported"),
        lambda: replace(base, canonical_version="unsupported"),
        lambda: replace(
            base,
            evidence_policy=cast(CommitEvidencePolicySnapshotV2, object()),
        ),
        lambda: replace(base, assurance=cast(object, "evidence_bound")),
        lambda: replace(base, profile="pheroos-quorum-v1"),
        lambda: replace(base, domain_root="not-a-root"),
        lambda: replace(base, scope_ref=""),
        lambda: replace(base, epoch=True),
        lambda: replace(base, revision=0),
        lambda: replace(base, record_set_root=_root("forged-record-set")),
        lambda: replace(base, conflict_roots=(_root("forged-conflict"),)),
        lambda: replace(base, projection_root=_root("forged-projection")),
    )
    for build in invalid:
        with pytest.raises((TypeError, ValueError)):
            build()

    for field_name, value in (
        ("assurance", "unsupported"),
        ("evidence_policy", "not-an-object"),
        ("records", "not-an-array"),
        ("conflict_roots", "not-an-array"),
    ):
        payload = base.to_dict()
        payload[field_name] = value
        with pytest.raises((TypeError, ValueError)):
            CommitEvidenceProjectionV2.from_dict(payload)

    noncanonical = base.to_dict()
    noncanonical["records"] = list(
        reversed(cast(list[object], noncanonical["records"]))
    )
    with pytest.raises(ValueError, match="canonical wire"):
        CommitEvidenceProjectionV2.from_dict(noncanonical)


def test_projection_rejects_inactive_cross_bound_ttl_and_low_quality_records() -> None:
    base = _projection((_record(1),))
    record = base.records[0]

    def project(item: QualifiedCommitEvidenceV2, **changes: object) -> None:
        replace(
            base,
            records=(item,),
            record_set_root="",
            conflict_roots=(),
            projection_root="",
            **changes,
        )

    revoked = replace(
        record,
        status=CommitEvidenceStatusV2.REVOKED,
        revoked_at_step=2,
        revocation_root=_root("projection:revocation"),
        revocation_provenance_root=_root("projection:revocation:provenance"),
        revocation_trace_roots=(_root("projection:revocation:trace"),),
        record_root="",
    )
    invalid = (
        lambda: project(revoked),
        lambda: project(replace(record, epoch=2, record_root="")),
        lambda: project(
            replace(
                record,
                qualification_policy_root=_root("policy:other"),
                record_root="",
            )
        ),
        lambda: project(
            replace(record, membership_root=_root("membership:other"), record_root="")
        ),
        lambda: project(
            replace(
                record,
                verification_set_root=_root("verification:other"),
                record_root="",
            )
        ),
        lambda: project(record, current_step=record.expires_at_step),
        lambda: project(
            replace(record, expires_at_step=102, record_root=""),
        ),
        lambda: project(
            replace(record, quality_ppm=0, weight_ppm=0, record_root=""),
        ),
    )
    for build in invalid:
        with pytest.raises(ValueError):
            build()


def test_projection_validates_challenge_and_rebuttal_relations() -> None:
    positive = _record(1)
    counter = _record(2, kind=CommitEvidenceKindV2.COUNTER)
    challenge = _record(3, kind=CommitEvidenceKindV2.CHALLENGE)
    found = replace(
        challenge,
        challenge_result=ChallengeResultV2.COUNTEREVIDENCE_FOUND,
        result_observation_roots=(counter.attestation_root,),
        record_root="",
    )
    assert len(_projection((positive, counter, found)).records) == 3

    unresolved = replace(
        found,
        result_observation_roots=(_root("attestation:missing"),),
        record_root="",
    )
    wrong_kind = replace(
        found,
        result_observation_roots=(positive.attestation_root,),
        record_root="",
    )
    crossed = replace(
        counter,
        candidate_ref="candidate:other",
        record_ref="evidence:counter:crossed",
        nonce="nonce:counter:crossed",
        record_root="",
    )
    crossed_challenge = replace(
        found,
        result_observation_roots=(crossed.attestation_root,),
        record_root="",
    )
    for records in (
        (positive, counter, unresolved),
        (positive, counter, wrong_kind),
        (positive, crossed, crossed_challenge),
    ):
        with pytest.raises(ValueError):
            _projection(records)

    rebutted = replace(
        counter,
        disposition=CommitEvidenceDispositionV2.REBUTTED,
        rebuttal_observation_roots=(positive.attestation_root,),
        resolution_root=_root("counter:rebutted"),
        record_root="",
    )
    assert len(_projection((positive, rebutted)).records) == 2

    dependent_positive = replace(
        positive,
        principal_ref=counter.principal_ref,
        cluster_ref=counter.cluster_ref,
        failure_domain_ref=counter.failure_domain_ref,
        record_root="",
    )
    dependent_rebuttal = replace(
        rebutted,
        rebuttal_observation_roots=(dependent_positive.attestation_root,),
        record_root="",
    )
    with pytest.raises(ValueError, match="not independent"):
        _projection((dependent_positive, dependent_rebuttal))


def test_projection_rejects_reused_challenge_execution_and_projects_conflicts() -> None:
    first = _record(3, kind=CommitEvidenceKindV2.CHALLENGE)
    second = _record(4, kind=CommitEvidenceKindV2.CHALLENGE)
    reused = replace(
        second,
        execution_root=first.execution_root,
        execution_attestation_root=first.execution_attestation_root,
        record_root="",
    )
    with pytest.raises(ValueError, match="reuses a challenge execution"):
        _projection((first, reused))

    conflict = replace(
        _record(5, kind=CommitEvidenceKindV2.COUNTER),
        materiality_ppm=1,
        criticality_ppm=1,
        record_root="",
    )
    projection = _projection((conflict,))
    assert projection.conflict_roots == (projection.records[0].record_root,)


def test_evaluation_public_boundary_and_record_coverage() -> None:
    projection = _projection((_record(1),))
    evaluation = _evaluate(projection)
    assert CommitEvidenceEvaluationV2.from_dict(evaluation.to_dict()) == evaluation

    with pytest.raises(TypeError, match="exact projection"):
        evaluate_commit_evidence_projection_v2(
            cast(CommitEvidenceProjectionV2, object()),
            candidate_ref="candidate:a",
            claim_root=_root("claim:a"),
            replay_receipt_roots=(),
        )

    high_floor = _projection(
        (_record(2),),
        policy=_policy(domain_contribution_floor=WEIGHT_SCALE + 1),
    )
    assert _evaluate(high_floor).source_diversity == 0

    inconclusive = replace(
        _record(3, kind=CommitEvidenceKindV2.CHALLENGE),
        challenge_result=ChallengeResultV2.INCONCLUSIVE,
        record_root="",
    )
    inconclusive_evaluation = _evaluate(_projection((inconclusive,)))
    assert inconclusive_evaluation.covered_challenge_categories == ()
    assert inconclusive_evaluation.missing_challenge_categories

    conclusive = _record(4, kind=CommitEvidenceKindV2.CHALLENGE)
    assert _evaluate(_projection((conclusive,))).covered_challenge_categories == (
        "category:required",
    )

    matching = _projection(
        (
            _record(10, domain="domain:a", cluster="cluster:x"),
            _record(11, domain="domain:a", cluster="cluster:y"),
            _record(12, domain="domain:b", cluster="cluster:x"),
            _record(13, domain="domain:c", cluster="cluster:x"),
        )
    )
    assert _evaluate(matching).source_diversity == 2


def test_evaluation_rejects_forged_metrics_booleans_and_root() -> None:
    evaluation = _evaluate(_projection((_record(1),)))
    invalid = (
        lambda: replace(evaluation, positive_evidence=-1),
        lambda: replace(evaluation, net_evidence=WEIGHT_SCALE**4),
        lambda: replace(evaluation, counterevidence_ratio_ppm=WEIGHT_SCALE + 1),
        lambda: replace(evaluation, replay_complete=cast(bool, 1)),
        lambda: replace(
            evaluation,
            evidence_gates_satisfied=not evaluation.evidence_gates_satisfied,
        ),
        lambda: replace(evaluation, evaluation_root=_root("forged-evaluation")),
    )
    for build in invalid:
        with pytest.raises((TypeError, ValueError)):
            build()


def test_evaluation_rejects_projection_tampered_after_construction() -> None:
    counter = _record(2, kind=CommitEvidenceKindV2.COUNTER)
    challenge = replace(
        _record(3, kind=CommitEvidenceKindV2.CHALLENGE),
        challenge_result=ChallengeResultV2.COUNTEREVIDENCE_FOUND,
        result_observation_roots=(counter.attestation_root,),
        record_root="",
    )
    projection = _projection((counter, challenge))
    forged = replace(projection)
    challenge_record = next(
        item for item in forged.records if item.kind is CommitEvidenceKindV2.CHALLENGE
    )
    object.__setattr__(forged, "records", (challenge_record,))
    with pytest.raises(ValueError, match="unavailable counterevidence"):
        _evaluate(forged)
