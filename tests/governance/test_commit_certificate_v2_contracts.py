from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import pickle

import pytest

from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateAuthorityLeafV2,
    CommitCertificateAuthorityRoleV2,
    CommitCertificateBodyV2,
    CommitCertificateIssuerAttestationVerifierV2,
    CommitCertificateMutationKindV2,
    CommitCertificateRequestV2,
    CommitCertificateSnapshotV2,
    CommitCertificateStatusV2,
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    PortableCommitCertificateV2,
    VerifiedCommitCertificateSourceV2,
    VerifiedCommitCertificateStateV2,
    commit_certificate_stream_ref_v2,
    verify_portable_commit_certificate_v2,
)
from pheroos.governance._commit_certificate_v2.reducer import _reduce_snapshot
from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


class _TrustedVerifier:
    def __init__(self, bindings: dict[tuple[str, str], str]) -> None:
        self.bindings = bindings

    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return self.bindings.get((issuer_ref, attestation_ref)) == body_root


def _leaves() -> tuple[CommitCertificateAuthorityLeafV2, ...]:
    return tuple(
        CommitCertificateAuthorityLeafV2(
            role=role,
            stream_ref=f"authority:{role.value}",
            revision=2,
            transition_id=f"transition:{role.value}:2",
            snapshot_root=_root(f"snapshot:{role.value}"),
            head_root=_root(f"head:{role.value}"),
            receipt_root=_root(f"receipt:{role.value}"),
        )
        for role in CommitCertificateAuthorityRoleV2
    )


def _body(**changes: object) -> CommitCertificateBodyV2:
    values: dict[str, object] = {
        "wire_version": "pheroos-commit-wire-v1",
        "canonicalization": "rfc8785",
        "hash_algorithm": "sha256",
        "domain_root": _root("domain"),
        "scope_ref": "scope:certificate",
        "profile": "pheroos-certified-commit-v1",
        "assurance": CommitAssurance.CERTIFIED,
        "protocol_ref": "protocol:optimal",
        "run_ref": "run:one",
        "target_ref": "target:answer",
        "epoch": 7,
        "manifest_root": _root("manifest"),
        "commit_policy_root": _root("commit-policy"),
        "decision_stream_ref": "authority:decision",
        "decision_revision": 5,
        "decision_transition_id": "transition:decision:heartbeat:5",
        "decision_snapshot_root": _root("decision-snapshot"),
        "decision_head_root": _root("decision-head"),
        "decision_receipt_root": _root("decision-receipt"),
        "decision_inclusion_root": _root("decision-inclusion"),
        "seal_transition_id": "transition:decision:seal:4",
        "seal_revision": 4,
        "seal_snapshot_root": _root("seal-snapshot"),
        "seal_receipt_root": _root("seal-receipt"),
        "seal_head_root": _root("seal-head"),
        "seal_inclusion_root": _root("seal-inclusion"),
        "seal_root": _root("seal"),
        "window_root": _root("window"),
        "frozen_dependency_root": _root("frozen-dependencies"),
        "assessment_root": _root("assessment"),
        "candidate_ref": "candidate:answer",
        "claim_root": _root("claim"),
        "evidence_root": _root("evidence"),
        "challenge_root": _root("challenge"),
        "lease_root": _root("lease"),
        "output_contract_root": _root("output-contract"),
        "output_payload_root": _root("output-payload"),
        "authority_leaves": _leaves(),
    }
    values.update(changes)
    return CommitCertificateBodyV2(**values)  # type: ignore[arg-type]


def _certificate(
    *,
    body: CommitCertificateBodyV2 | None = None,
    certificate_id: str = "certificate:one",
    nonce: str = "nonce:one",
) -> PortableCommitCertificateV2:
    return PortableCommitCertificateV2(
        certificate_id=certificate_id,
        issuer_ref="issuer:certificate",
        issued_at_step=5,
        provenance_ref="urn:test:certificate",
        envelope_nonce=nonce,
        body=_body() if body is None else body,
        issuer_attestation_refs=("attestation:one",),
    )


def _verifier(certificate: PortableCommitCertificateV2) -> _TrustedVerifier:
    return _TrustedVerifier(
        {
            (
                certificate.issuer_ref,
                certificate.issuer_attestation_refs[0],
            ): certificate.body.body_root
        }
    )


def _request(
    certificate: PortableCommitCertificateV2,
    *,
    mutation: str,
    parent: CommitCertificateSnapshotV2 | None = None,
) -> CommitCertificateRequestV2:
    return CommitCertificateRequestV2(
        domain_root=certificate.body.domain_root,
        scope_ref=certificate.body.scope_ref,
        protocol_ref=certificate.body.protocol_ref,
        run_ref=certificate.body.run_ref,
        target_ref=certificate.body.target_ref,
        observed_epoch=certificate.body.epoch,
        mutation_ref=mutation,
        mutation_issuer_ref=certificate.issuer_ref,
        current_step=certificate.issued_at_step,
        parent_revision=0 if parent is None else parent.revision,
        parent_transition_id="genesis" if parent is None else parent.transition_id,
        parent_snapshot_root=(
            COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
            if parent is None
            else parent.snapshot_root
        ),
        certificate=certificate,
    )


def test_public_portable_certificate_round_trip_and_external_trust_boundary() -> None:
    certificate = _certificate()
    decoded = PortableCommitCertificateV2.from_dict(certificate.to_dict())
    verifier = _verifier(certificate)
    assert isinstance(verifier, CommitCertificateIssuerAttestationVerifierV2)
    assert decoded == certificate
    assert verify_portable_commit_certificate_v2(
        decoded,
        trusted_verifier=verifier,
        expected_body_root=certificate.body.body_root,
        expected_target_ref="target:answer",
        expected_candidate_ref="candidate:answer",
        expected_claim_root=_root("claim"),
        expected_epoch=7,
    )
    assert not verify_portable_commit_certificate_v2(
        decoded,
        trusted_verifier={"attestation:one": certificate.body.body_root},  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("target_ref", "target:other"),
        ("epoch", 8),
        ("candidate_ref", "candidate:other"),
        ("claim_root", _root("claim:other")),
        ("manifest_root", _root("manifest:other")),
        ("commit_policy_root", _root("policy:other")),
        ("decision_receipt_root", _root("decision-receipt:other")),
        ("seal_inclusion_root", _root("seal-inclusion:other")),
        ("risk", _root("risk-head:other")),
        ("output_payload_root", _root("payload:other")),
    ),
)
def test_every_authority_leaf_or_subject_substitution_fails_trusted_verification(
    field: str,
    replacement: object,
) -> None:
    original = _certificate()
    if field == "risk":
        leaves = tuple(
            replace(item, head_root=str(replacement), leaf_root="")
            if item.role is CommitCertificateAuthorityRoleV2.RISK
            else item
            for item in original.body.authority_leaves
        )
        mutated_body = _body(authority_leaves=leaves)
    else:
        mutated_body = _body(**{field: replacement})
    mutated = _certificate(body=mutated_body)
    assert mutated.body.body_root != original.body.body_root
    assert not verify_portable_commit_certificate_v2(
        mutated,
        trusted_verifier=_verifier(original),
    )


def test_stale_roots_unknown_fields_bool_substitution_and_envelope_tamper_fail() -> (
    None
):
    certificate = _certificate()
    verifier = _verifier(certificate)
    stale = certificate.to_dict()
    body = dict(stale["body"])  # type: ignore[arg-type]
    body["candidate_ref"] = "candidate:forged"
    stale["body"] = body
    assert not verify_portable_commit_certificate_v2(stale, trusted_verifier=verifier)

    unknown = certificate.to_dict()
    unknown["authority"] = True
    assert not verify_portable_commit_certificate_v2(unknown, trusted_verifier=verifier)

    bool_revision = certificate.to_dict()
    bool_body = dict(bool_revision["body"])  # type: ignore[arg-type]
    leaves = list(bool_body["authority_leaves"])  # type: ignore[arg-type]
    first = dict(leaves[0])  # type: ignore[arg-type]
    first["revision"] = True
    leaves[0] = first
    bool_body["authority_leaves"] = leaves
    bool_revision["body"] = bool_body
    assert not verify_portable_commit_certificate_v2(
        bool_revision, trusted_verifier=verifier
    )

    envelope = certificate.to_dict()
    envelope["envelope_nonce"] = "nonce:forged"
    assert not verify_portable_commit_certificate_v2(
        envelope, trusted_verifier=verifier
    )


def test_attestation_and_resource_bounds_are_fail_closed() -> None:
    certificate = _certificate()
    with pytest.raises(ValueError, match="item count"):
        PortableCommitCertificateV2(
            certificate_id=certificate.certificate_id,
            issuer_ref=certificate.issuer_ref,
            issued_at_step=certificate.issued_at_step,
            provenance_ref=certificate.provenance_ref,
            envelope_nonce=certificate.envelope_nonce,
            body=certificate.body,
            issuer_attestation_refs=tuple(
                f"attestation:{index}" for index in range(33)
            ),
        )
    with pytest.raises(ValueError, match="incomplete"):
        _body(authority_leaves=certificate.body.authority_leaves[:-1])
    with pytest.raises(ValueError, match="text bound"):
        PortableCommitCertificateV2(
            certificate_id="界" * 4_097,
            issuer_ref=certificate.issuer_ref,
            issued_at_step=certificate.issued_at_step,
            provenance_ref=certificate.provenance_ref,
            envelope_nonce=certificate.envelope_nonce,
            body=certificate.body,
            issuer_attestation_refs=certificate.issuer_attestation_refs,
        )
    with pytest.raises(ValueError, match="integer bound"):
        PortableCommitCertificateV2(
            certificate_id=certificate.certificate_id,
            issuer_ref=certificate.issuer_ref,
            issued_at_step=True,
            provenance_ref=certificate.provenance_ref,
            envelope_nonce=certificate.envelope_nonce,
            body=certificate.body,
            issuer_attestation_refs=certificate.issuer_attestation_refs,
        )


def test_fixed_stream_excludes_epoch_issuer_manifest_policy_and_candidate() -> None:
    stream = commit_certificate_stream_ref_v2(
        "scope:certificate", "protocol:optimal", "run:one", "target:answer"
    )
    assert stream.startswith("authority:commit-certificate-v2:")
    assert all(
        item not in stream
        for item in ("epoch", "issuer", "manifest", "policy", "candidate")
    )


def test_complete_replacement_semantic_retry_identity_conflict_and_sticky_state() -> (
    None
):
    first_certificate = _certificate()
    first_request = _request(first_certificate, mutation="mutation:first")
    first = _reduce_snapshot(
        first_request,
        parent=None,
        source_context_root=_root("source:first"),
    )
    assert first.status is CommitCertificateStatusV2.VERIFIED
    assert first.mutation_kind is CommitCertificateMutationKindV2.VERIFIED

    retry_certificate = _certificate(
        body=first_certificate.body,
        certificate_id="certificate:two",
        nonce="nonce:two",
    )
    retry_request = _request(
        retry_certificate,
        mutation="mutation:retry",
        parent=first,
    )
    retry = _reduce_snapshot(
        retry_request,
        parent=first,
        source_context_root=_root("source:retry"),
    )
    assert retry.status is CommitCertificateStatusV2.VERIFIED
    assert retry.mutation_kind is CommitCertificateMutationKindV2.SEMANTIC_RETRY
    assert retry.certificate.body.body_root == first.certificate.body.body_root
    assert len(retry.envelope_roots) == 2

    conflicting_body = _body(output_payload_root=_root("output:conflict"))
    conflict_certificate = _certificate(
        body=conflicting_body,
        certificate_id=first_certificate.certificate_id,
        nonce="nonce:conflict",
    )
    conflict_request = _request(
        conflict_certificate,
        mutation="mutation:conflict",
        parent=retry,
    )
    conflict = _reduce_snapshot(
        conflict_request,
        parent=retry,
        source_context_root=_root("source:conflict"),
    )
    assert conflict.status is CommitCertificateStatusV2.CONFLICT
    assert conflict.mutation_kind is CommitCertificateMutationKindV2.CONFLICT
    assert set(conflict.conflicting_body_roots) == {
        first_certificate.body.body_root,
        conflicting_body.body_root,
    }

    sticky_certificate = _certificate(
        body=conflicting_body,
        certificate_id="certificate:three",
        nonce="nonce:sticky",
    )
    sticky = _reduce_snapshot(
        _request(sticky_certificate, mutation="mutation:sticky", parent=conflict),
        parent=conflict,
        source_context_root=_root("source:sticky"),
    )
    assert sticky.status is CommitCertificateStatusV2.CONFLICT
    assert sticky.reason_codes == ("certificate_conflict_sticky",)
    assert CommitCertificateSnapshotV2.from_dict(sticky.to_dict()) == sticky


def test_request_rejects_cross_target_body_and_portable_handles_are_not_authority() -> (
    None
):
    certificate = _certificate()
    with pytest.raises(ValueError, match="cross-bound"):
        CommitCertificateRequestV2(
            domain_root=certificate.body.domain_root,
            scope_ref=certificate.body.scope_ref,
            protocol_ref=certificate.body.protocol_ref,
            run_ref=certificate.body.run_ref,
            target_ref="target:other",
            observed_epoch=certificate.body.epoch,
            mutation_ref="mutation:one",
            mutation_issuer_ref=certificate.issuer_ref,
            current_step=certificate.issued_at_step,
            parent_revision=0,
            parent_transition_id="genesis",
            parent_snapshot_root=_root("irrelevant"),
            certificate=certificate,
        )
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitCertificateSourceV2()
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitCertificateStateV2()
    forged = object.__new__(VerifiedCommitCertificateSourceV2)
    with pytest.raises((AttributeError, TypeError, ValueError)):
        copy(forged)
    with pytest.raises((AttributeError, TypeError, ValueError)):
        deepcopy(forged)
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(forged)


def test_public_objects_are_native_and_owner_has_no_legacy_authority() -> None:
    assert CommitCertificateBodyV2.__module__ == (
        "pheroos.governance.commit_certificate_v2"
    )
    root = (
        Path(__file__).resolve().parents[2]
        / "pheroos/governance/_commit_certificate_v2"
    )
    source = "\n".join(path.read_text() for path in root.glob("*.py"))
    for forbidden in (
        "authority_registry",
        "LEGACY_AUTHORITY_REGISTRY",
        "_ISSUANCE",
        "threading",
        "RLock",
        "module-global dict",
        "pheroos.governance._certificate",
        "pheroos.governance._distributed",
    ):
        assert forbidden not in source
    assert max(len(path.read_text().splitlines()) for path in root.glob("*.py")) < 600
    assert AUTHORITY_CANONICAL_VERSION_V2 in _body().to_dict().values()
