"""Trusted preparation and non-portable source proof for Certificate v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAssurance, CollectiveCommitPolicy
from pheroos.protocol.commit_wire import commit_policy_fingerprint

from pheroos.governance._commit_certificate_v2.common import _root
from pheroos.governance._commit_certificate_v2.decision_leaves import (
    _authority_leaves,
)
from pheroos.governance._commit_certificate_v2.portable_body import (
    CommitCertificateBodyV2,
)
from pheroos.governance._commit_certificate_v2.portable_envelope import (
    CommitCertificateIssuerAttestationVerifierV2,
    PortableCommitCertificateV2,
    verify_portable_commit_certificate_v2,
)
from pheroos.governance._commit_certificate_v2.request import (
    CommitCertificateRequestV2,
)
from pheroos.governance._commit_certificate_v2.reducer import _reduce_snapshot
from pheroos.governance._commit_certificate_v2.state_contracts import (
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2,
    CommitCertificateSnapshotV2,
)
from pheroos.governance._commit_decision_v2.seal_context import (
    _CommitDecisionSealContextMaterialV2,
    _verified_commit_decision_seal_context_material_v2,
    _verified_commit_decision_seal_context_v2,
)
from pheroos.governance._commit_decision_v2.state_handle import (
    VerifiedCommitDecisionStateV2,
)


@dataclass(frozen=True, slots=True)
class _CertificateSourceMaterialV2:
    request: CommitCertificateRequestV2
    snapshot: CommitCertificateSnapshotV2
    manifest: ScopedProtocolManifestV2
    decision_state: VerifiedCommitDecisionStateV2
    parent_state: object | None
    trusted_verifier: CommitCertificateIssuerAttestationVerifierV2
    source_context_root: str


@final
class VerifiedCommitCertificateSourceV2:
    """Opaque source whose trust and Decision observations are rechecked."""

    __slots__ = (
        "_decision_state",
        "_manifest",
        "_parent_state",
        "_request",
        "_snapshot",
        "_source_context_root",
        "_trusted_verifier",
    )

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedCommitCertificateSourceV2:
        raise TypeError("VerifiedCommitCertificateSourceV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitCertificateSourceV2 is immutable")

    def __copy__(self) -> VerifiedCommitCertificateSourceV2:
        _verified_commit_certificate_source_material_v2(self)
        return self

    def __deepcopy__(
        self, _memo: dict[int, object]
    ) -> VerifiedCommitCertificateSourceV2:
        _verified_commit_certificate_source_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateSourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitCertificateSourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitCertificateSourceV2 redacted>"


def prepare_commit_certificate_v2(
    *,
    decision_state: VerifiedCommitDecisionStateV2,
    manifest: ScopedProtocolManifestV2,
    trusted_verifier: CommitCertificateIssuerAttestationVerifierV2,
    certificate_id: str,
    issuer_ref: str,
    issuer_attestation_refs: Sequence[str],
    issued_at_step: int,
    provenance_ref: str,
    envelope_nonce: str,
    mutation_ref: str,
    parent_state: object | None = None,
) -> tuple[CommitCertificateRequestV2, VerifiedCommitCertificateSourceV2]:
    """Verify external attestations and derive one complete replacement."""

    decision_context = _verified_commit_decision_seal_context_v2(decision_state)
    decision = _verified_commit_decision_seal_context_material_v2(decision_context)
    detached_manifest = _validated_manifest(manifest, decision)
    parent = _parent_snapshot(parent_state)
    envelope = _build_envelope(
        decision,
        detached_manifest,
        certificate_id=certificate_id,
        issuer_ref=issuer_ref,
        issuer_attestation_refs=issuer_attestation_refs,
        issued_at_step=issued_at_step,
        provenance_ref=provenance_ref,
        envelope_nonce=envelope_nonce,
    )
    if not verify_portable_commit_certificate_v2(
        envelope,
        trusted_verifier=trusted_verifier,
        expected_body_root=envelope.body.body_root,
        expected_target_ref=decision.snapshot.target_ref,
        expected_candidate_ref=envelope.body.candidate_ref,
        expected_claim_root=envelope.body.claim_root,
        expected_epoch=decision.snapshot.epoch,
    ):
        raise ValueError("commit certificate issuer attestation is not trusted")
    request = _build_request(
        decision,
        envelope,
        mutation_ref=mutation_ref,
        issuer_ref=issuer_ref,
        issued_at_step=issued_at_step,
        parent=parent,
    )
    source_root = _source_context_root(request, decision, detached_manifest, parent)
    snapshot = _reduce_snapshot(request, parent=parent, source_context_root=source_root)
    source = object.__new__(VerifiedCommitCertificateSourceV2)
    object.__setattr__(
        source, "_request", CommitCertificateRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(
        source, "_snapshot", CommitCertificateSnapshotV2.from_dict(snapshot.to_dict())
    )
    object.__setattr__(source, "_manifest", detached_manifest)
    object.__setattr__(source, "_decision_state", decision_state)
    object.__setattr__(source, "_parent_state", parent_state)
    object.__setattr__(source, "_trusted_verifier", trusted_verifier)
    object.__setattr__(source, "_source_context_root", source_root)
    return request, source


def verify_commit_certificate_request_source_v2(
    request: CommitCertificateRequestV2,
    *,
    source: object,
    committed_parent_snapshot: CommitCertificateSnapshotV2 | None,
) -> tuple[
    CommitCertificateSnapshotV2,
    _CommitDecisionSealContextMaterialV2,
]:
    material = _verified_commit_certificate_source_material_v2(source)
    if material.request.to_dict() != request.to_dict():
        raise ValueError("commit certificate source request is mismatched")
    if (committed_parent_snapshot is None) != (material.parent_state is None):
        raise ValueError("commit certificate source parent presence is mismatched")
    parent = _parent_snapshot(material.parent_state)
    if parent is not None and committed_parent_snapshot is not None:
        if parent.to_dict() != committed_parent_snapshot.to_dict():
            raise ValueError("commit certificate source parent is mismatched")
    decision = _verified_commit_decision_seal_context_material_v2(
        _verified_commit_decision_seal_context_v2(material.decision_state)
    )
    _validated_manifest(material.manifest, decision)
    if not verify_portable_commit_certificate_v2(
        request.certificate,
        trusted_verifier=material.trusted_verifier,
        expected_body_root=request.certificate.body.body_root,
        expected_target_ref=request.target_ref,
        expected_candidate_ref=request.certificate.body.candidate_ref,
        expected_claim_root=request.certificate.body.claim_root,
        expected_epoch=request.observed_epoch,
    ):
        raise ValueError("commit certificate source trust has changed")
    expected = _build_envelope_from_existing(
        request.certificate, decision, material.manifest
    )
    if expected.body.to_dict() != request.certificate.body.to_dict():
        raise ValueError("commit certificate body no longer matches Decision authority")
    source_root = _source_context_root(request, decision, material.manifest, parent)
    if source_root != material.source_context_root:
        raise ValueError("commit certificate source context is mismatched")
    rebuilt = _reduce_snapshot(request, parent=parent, source_context_root=source_root)
    if rebuilt.to_dict() != material.snapshot.to_dict():
        raise ValueError("commit certificate source replacement is mismatched")
    return rebuilt, decision


def _verified_commit_certificate_source_material_v2(
    source: object,
) -> _CertificateSourceMaterialV2:
    if type(source) is not VerifiedCommitCertificateSourceV2:
        raise TypeError("commit certificate source has the wrong exact type")
    names = (
        "_request",
        "_snapshot",
        "_manifest",
        "_decision_state",
        "_parent_state",
        "_trusted_verifier",
        "_source_context_root",
    )
    try:
        values = tuple(object.__getattribute__(source, name) for name in names)
    except AttributeError as exc:
        raise TypeError("commit certificate source is incomplete") from exc
    request, snapshot, manifest, decision, parent, verifier, source_root = values
    if type(request) is not CommitCertificateRequestV2:
        raise TypeError("commit certificate source request is invalid")
    if type(snapshot) is not CommitCertificateSnapshotV2:
        raise TypeError("commit certificate source snapshot is invalid")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("commit certificate source manifest is invalid")
    if type(decision) is not VerifiedCommitDecisionStateV2:
        raise TypeError("commit certificate source Decision state is invalid")
    if not isinstance(verifier, CommitCertificateIssuerAttestationVerifierV2):
        raise TypeError("commit certificate source verifier is invalid")
    if type(source_root) is not str:
        raise TypeError("commit certificate source root is invalid")
    return _CertificateSourceMaterialV2(
        request=request,
        snapshot=snapshot,
        manifest=(manifest),
        decision_state=(decision),
        parent_state=parent,
        trusted_verifier=verifier,
        source_context_root=source_root,
    )


def _validated_manifest(
    manifest: ScopedProtocolManifestV2,
    decision: _CommitDecisionSealContextMaterialV2,
) -> ScopedProtocolManifestV2:
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("Commit Certificate v2 requires an exact scoped manifest")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    snapshot = decision.snapshot
    policy = detached.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("Commit Certificate v2 manifest has no commit policy")
    expected_mode = (
        "portable" if snapshot.assurance is CommitAssurance.CERTIFIED else "distributed"
    )
    if snapshot.assurance not in {
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        raise ValueError("Commit Certificate v2 requires certified assurance")
    if (
        detached.manifest_root != snapshot.manifest_root
        or detached.id != snapshot.protocol_ref
        or policy.assurance != snapshot.assurance.value
        or policy.target != snapshot.target_ref
        or commit_policy_fingerprint(policy, profile=snapshot.profile)
        != snapshot.commit_policy_root
        or policy.certificate.mode != expected_mode
        or policy.certificate.issuer_attestation_required is not True
        or policy.certificate.independent_verification_required is not True
    ):
        raise ValueError("Commit Certificate v2 manifest policy is mismatched")
    return detached


def _build_envelope(
    decision: _CommitDecisionSealContextMaterialV2,
    manifest: ScopedProtocolManifestV2,
    *,
    certificate_id: str,
    issuer_ref: str,
    issuer_attestation_refs: Sequence[str],
    issued_at_step: int,
    provenance_ref: str,
    envelope_nonce: str,
) -> PortableCommitCertificateV2:
    snapshot = decision.snapshot
    if (
        issued_at_step != snapshot.current_step
        or issued_at_step >= snapshot.finality_deadline_step
    ):
        raise ValueError("commit certificate issuance step is not current")
    body = _body_from_decision(decision, manifest)
    return PortableCommitCertificateV2(
        certificate_id=certificate_id,
        issuer_ref=issuer_ref,
        issued_at_step=issued_at_step,
        provenance_ref=provenance_ref,
        envelope_nonce=envelope_nonce,
        body=body,
        issuer_attestation_refs=issuer_attestation_refs,
    )


def _build_envelope_from_existing(
    envelope: PortableCommitCertificateV2,
    decision: _CommitDecisionSealContextMaterialV2,
    manifest: ScopedProtocolManifestV2,
) -> PortableCommitCertificateV2:
    return PortableCommitCertificateV2(
        certificate_id=envelope.certificate_id,
        issuer_ref=envelope.issuer_ref,
        issued_at_step=envelope.issued_at_step,
        provenance_ref=envelope.provenance_ref,
        envelope_nonce=envelope.envelope_nonce,
        body=_body_from_decision(decision, manifest),
        issuer_attestation_refs=envelope.issuer_attestation_refs,
    )


def _body_from_decision(
    decision: _CommitDecisionSealContextMaterialV2,
    manifest: ScopedProtocolManifestV2,
) -> CommitCertificateBodyV2:
    snapshot = decision.snapshot
    seal = snapshot.seal
    assessment = snapshot.assessment
    assert seal is not None and assessment is not None
    metrics = tuple(
        item
        for item in assessment.candidate_metrics
        if item.candidate_ref == seal.candidate_ref
        and item.claim_root == seal.claim_root
    )
    if len(metrics) != 1 or not metrics[0].ready_for_stability:
        raise ValueError("commit certificate sealed candidate is not evidence-ready")
    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return CommitCertificateBodyV2(
        wire_version=policy.certificate.wire_version,
        canonicalization=policy.certificate.canonicalization,
        hash_algorithm=policy.certificate.hash_algorithm,
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        epoch=snapshot.epoch,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        decision_stream_ref=snapshot.stream_ref,
        decision_revision=snapshot.revision,
        decision_transition_id=snapshot.transition_id,
        decision_snapshot_root=snapshot.snapshot_root,
        decision_head_root=decision.decision_head.head_root,
        decision_receipt_root=decision.current_inclusion.receipt_root,
        decision_inclusion_root=decision.current_inclusion.inclusion_root,
        seal_transition_id=decision.seal_inclusion.transition_id,
        seal_revision=decision.seal_inclusion.revision,
        seal_snapshot_root=decision.seal_inclusion.snapshot_root,
        seal_receipt_root=decision.seal_inclusion.receipt_root,
        seal_head_root=decision.seal_inclusion.head_root,
        seal_inclusion_root=decision.seal_inclusion.inclusion_root,
        seal_root=seal.seal_root,
        window_root=seal.window_root,
        frozen_dependency_root=seal.frozen_dependency_root,
        assessment_root=assessment.assessment_root,
        candidate_ref=seal.candidate_ref,
        claim_root=seal.claim_root,
        evidence_root=metrics[0].evidence_root,
        challenge_root=metrics[0].challenge_root,
        lease_root=metrics[0].lease_root,
        output_contract_root=seal.output_contract_root,
        output_payload_root=seal.output_payload_root,
        authority_leaves=_authority_leaves(snapshot.dependencies),
    )


def _build_request(
    decision: _CommitDecisionSealContextMaterialV2,
    envelope: PortableCommitCertificateV2,
    *,
    mutation_ref: str,
    issuer_ref: str,
    issued_at_step: int,
    parent: CommitCertificateSnapshotV2 | None,
) -> CommitCertificateRequestV2:
    snapshot = decision.snapshot
    return CommitCertificateRequestV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        observed_epoch=snapshot.epoch,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=issuer_ref,
        current_step=issued_at_step,
        parent_revision=0 if parent is None else parent.revision,
        parent_transition_id=(
            COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
            if parent is None
            else parent.transition_id
        ),
        parent_snapshot_root=(
            COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
            if parent is None
            else parent.snapshot_root
        ),
        certificate=envelope,
    )


def _source_context_root(
    request: CommitCertificateRequestV2,
    decision: _CommitDecisionSealContextMaterialV2,
    manifest: ScopedProtocolManifestV2,
    parent: CommitCertificateSnapshotV2 | None,
) -> str:
    return _root(
        "source-context",
        {
            "request_root": request.request_root,
            "manifest_root": manifest.manifest_root,
            "decision_snapshot_root": decision.snapshot.snapshot_root,
            "decision_head_root": decision.decision_head.head_root,
            "seal_inclusion_root": decision.seal_inclusion.inclusion_root,
            "parent_snapshot_root": "" if parent is None else parent.snapshot_root,
        },
    )


def _parent_snapshot(value: object | None) -> CommitCertificateSnapshotV2 | None:
    if value is None:
        return None
    from pheroos.governance._commit_certificate_v2.state_handle import (
        _verified_commit_certificate_state_material_v2,
    )

    return _verified_commit_certificate_state_material_v2(value).snapshot


__all__: tuple[str, ...] = ()
