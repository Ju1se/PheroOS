"""Non-portable source proof for Commit Evidence v2 requests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import NoReturn, SupportsIndex, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._commit_evidence_owner_v2.context import (
    CommitEvidenceContextV2,
    commit_evidence_context_v2,
)
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    CommitEvidenceAdvanceRequestV2,
)
from pheroos.governance._commit_evidence_owner_v2.dependencies import (
    _DependencyMaterialV2,
    _dependency_material,
    _validate_dependency_context,
    _validate_replay_coverage,
)
from pheroos.governance._commit_evidence_owner_v2.proposals import (
    CommitEvidenceAttestationV2,
    CommitEvidenceRevocationV2,
    CounterevidenceDispositionProposalV2,
)
from pheroos.governance._commit_evidence_projection_v2.common import evidence_root_v2
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceStatusV2,
)


@dataclass(frozen=True, slots=True)
class _EvidenceSourceBindingV2:
    request_root: str
    manifest_root: str
    authority_policy_root: str
    commit_policy_root: str
    evidence_policy_root: str
    membership_head_root: str
    membership_snapshot_root: str
    membership_root: str
    verification_head_root: str
    verification_snapshot_root: str
    verification_set_root: str
    replay_head_root: str
    replay_snapshot_root: str
    replay_receipt_root: str
    attestation_roots: tuple[str, ...]
    disposition_roots: tuple[str, ...]
    revocation_roots: tuple[str, ...]
    source_context_root: str

    def body(self) -> dict[str, object]:
        return {
            "version": "pheroos-commit-evidence-source-v2",
            "request_root": self.request_root,
            "manifest_root": self.manifest_root,
            "authority_policy_root": self.authority_policy_root,
            "commit_policy_root": self.commit_policy_root,
            "evidence_policy_root": self.evidence_policy_root,
            "membership_head_root": self.membership_head_root,
            "membership_snapshot_root": self.membership_snapshot_root,
            "membership_root": self.membership_root,
            "verification_head_root": self.verification_head_root,
            "verification_snapshot_root": self.verification_snapshot_root,
            "verification_set_root": self.verification_set_root,
            "replay_head_root": self.replay_head_root,
            "replay_snapshot_root": self.replay_snapshot_root,
            "replay_receipt_root": self.replay_receipt_root,
            "attestation_roots": list(self.attestation_roots),
            "disposition_roots": list(self.disposition_roots),
            "revocation_roots": list(self.revocation_roots),
        }


@final
class VerifiedCommitEvidenceSourceV2:
    """Non-portable proof that current dependencies produced one request."""

    __slots__ = (
        "_binding",
        "_manifest",
        "_membership_state",
        "_replay_state",
        "_request",
        "_verification_state",
    )

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedCommitEvidenceSourceV2:
        raise TypeError("VerifiedCommitEvidenceSourceV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitEvidenceSourceV2 is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceSourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceSourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitEvidenceSourceV2 redacted>"

    @property
    def context_root(self) -> str:
        return _verified_source(self)[1].source_context_root


def _issue_source(
    request: CommitEvidenceAdvanceRequestV2,
    context: CommitEvidenceContextV2,
    dependency: _DependencyMaterialV2,
    verification_state: object,
    membership_state: object,
    replay_state: object,
    *,
    attestations: Sequence[CommitEvidenceAttestationV2],
    dispositions: Sequence[CounterevidenceDispositionProposalV2],
    revocations: Sequence[CommitEvidenceRevocationV2],
) -> VerifiedCommitEvidenceSourceV2:
    provisional = _EvidenceSourceBindingV2(
        request_root=request.request_root,
        manifest_root=context.manifest_root,
        authority_policy_root=context.authority_policy_root,
        commit_policy_root=context.commit_policy_root,
        evidence_policy_root=context.evidence_policy.policy_root,
        membership_head_root=dependency.membership_head_root,
        membership_snapshot_root=dependency.membership.snapshot_root,
        membership_root=dependency.membership.membership_root,
        verification_head_root=dependency.verification_head_root,
        verification_snapshot_root=dependency.verification.snapshot_root,
        verification_set_root=dependency.verification.verification_set_root,
        replay_head_root=dependency.replay_head_root,
        replay_snapshot_root=dependency.replay.snapshot_root,
        replay_receipt_root=dependency.replay.receipt_root,
        attestation_roots=tuple(sorted(item.attestation_root for item in attestations)),
        disposition_roots=tuple(sorted(item.disposition_root for item in dispositions)),
        revocation_roots=tuple(sorted(item.revocation_root for item in revocations)),
        source_context_root="",
    )
    binding = replace(
        provisional,
        source_context_root=evidence_root_v2("source-context", provisional.body()),
    )
    source = object.__new__(VerifiedCommitEvidenceSourceV2)
    object.__setattr__(source, "_binding", binding)
    object.__setattr__(source, "_manifest", context.manifest)
    object.__setattr__(source, "_verification_state", verification_state)
    object.__setattr__(source, "_membership_state", membership_state)
    object.__setattr__(source, "_replay_state", replay_state)
    object.__setattr__(
        source,
        "_request",
        CommitEvidenceAdvanceRequestV2.from_dict(request.to_dict()),
    )
    return source


def _verified_source(
    source: object,
) -> tuple[CommitEvidenceAdvanceRequestV2, _EvidenceSourceBindingV2]:
    if type(source) is not VerifiedCommitEvidenceSourceV2:
        raise TypeError("commit evidence source proof is invalid")
    try:
        binding = object.__getattribute__(source, "_binding")
        manifest = object.__getattribute__(source, "_manifest")
        request = object.__getattribute__(source, "_request")
        verification_state = object.__getattribute__(source, "_verification_state")
        membership_state = object.__getattribute__(source, "_membership_state")
        replay_state = object.__getattribute__(source, "_replay_state")
    except AttributeError as exc:
        raise TypeError("commit evidence source proof is incomplete") from exc
    if (
        type(binding) is not _EvidenceSourceBindingV2
        or type(manifest) is not ScopedProtocolManifestV2
        or type(request) is not CommitEvidenceAdvanceRequestV2
    ):
        raise TypeError("commit evidence source proof shape is invalid")
    detached = CommitEvidenceAdvanceRequestV2.from_dict(request.to_dict())
    snapshot = detached.snapshot
    context = commit_evidence_context_v2(
        manifest,
        profile=snapshot.profile,
        target_ref=snapshot.target_ref,
    )
    dependency = _dependency_material(
        verification_state,
        membership_state,
        replay_state,
    )
    _validate_dependency_context(
        dependency,
        context=context,
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        run_ref=snapshot.run_ref,
        epoch=snapshot.epoch,
        current_step=snapshot.current_step,
    )
    _validate_replay_coverage(
        snapshot.records,
        dependency,
        context=context,
        epoch=snapshot.epoch,
        current_step=snapshot.current_step,
    )
    expected = _expected_binding(detached, context, dependency, binding)
    context_root = evidence_root_v2(
        "source-context",
        replace(binding, source_context_root="").body(),
    )
    if _binding_material(binding) != _binding_material(expected):
        mismatched = next(
            field
            for field in _SOURCE_BINDING_MATERIAL_FIELDS_V2
            if getattr(binding, field) != getattr(expected, field)
        )
        raise ValueError(f"commit evidence source proof is cross-bound at {mismatched}")
    if binding.source_context_root != context_root:
        raise ValueError("commit evidence source context root is mismatched")
    return detached, binding


def _expected_binding(
    request: CommitEvidenceAdvanceRequestV2,
    context: CommitEvidenceContextV2,
    dependency: _DependencyMaterialV2,
    binding: _EvidenceSourceBindingV2,
) -> _EvidenceSourceBindingV2:
    additions = tuple(
        item
        for item in request.snapshot.records
        if item.record_root in request.snapshot.mutation_record_roots
        and item.status is CommitEvidenceStatusV2.ACTIVE
    )
    return replace(
        binding,
        request_root=request.request_root,
        manifest_root=context.manifest_root,
        authority_policy_root=context.authority_policy_root,
        commit_policy_root=context.commit_policy_root,
        evidence_policy_root=context.evidence_policy.policy_root,
        membership_head_root=dependency.membership_head_root,
        membership_snapshot_root=dependency.membership.snapshot_root,
        membership_root=dependency.membership.membership_root,
        verification_head_root=dependency.verification_head_root,
        verification_snapshot_root=dependency.verification.snapshot_root,
        verification_set_root=dependency.verification.verification_set_root,
        replay_head_root=dependency.replay_head_root,
        replay_snapshot_root=dependency.replay.snapshot_root,
        replay_receipt_root=dependency.replay.receipt_root,
        attestation_roots=tuple(sorted(item.attestation_root for item in additions)),
        disposition_roots=tuple(
            sorted(item.disposition_root for item in additions if item.disposition_root)
        ),
        revocation_roots=tuple(request.snapshot.revocation_roots),
    )


def _binding_material(binding: _EvidenceSourceBindingV2) -> tuple[object, ...]:
    return tuple(
        getattr(binding, field) for field in _SOURCE_BINDING_MATERIAL_FIELDS_V2
    )


_SOURCE_BINDING_MATERIAL_FIELDS_V2 = (
    "request_root",
    "manifest_root",
    "authority_policy_root",
    "commit_policy_root",
    "evidence_policy_root",
    "membership_head_root",
    "membership_snapshot_root",
    "membership_root",
    "verification_head_root",
    "verification_snapshot_root",
    "verification_set_root",
    "replay_head_root",
    "replay_snapshot_root",
    "replay_receipt_root",
    "attestation_roots",
    "disposition_roots",
    "revocation_roots",
)


def _verified_source_manifest_v2(source: object) -> ScopedProtocolManifestV2:
    _verified_source(source)
    manifest = object.__getattribute__(source, "_manifest")
    return ScopedProtocolManifestV2.from_dict(manifest.to_dict())


def _expected_source_context_root_v2(source: object) -> str:
    return _verified_source(source)[1].source_context_root


def _source_context_root_from_request_v2(
    request: CommitEvidenceAdvanceRequestV2,
) -> str:
    if type(request) is not CommitEvidenceAdvanceRequestV2:
        raise TypeError("commit evidence source root requires exact request v2")
    snapshot = request.snapshot
    additions = tuple(
        item
        for item in snapshot.records
        if item.status is CommitEvidenceStatusV2.ACTIVE
        and item.record_root in snapshot.mutation_record_roots
    )
    binding = _EvidenceSourceBindingV2(
        request_root=request.request_root,
        manifest_root=snapshot.manifest_root,
        authority_policy_root=snapshot.authority_policy_root,
        commit_policy_root=snapshot.commit_policy_root,
        evidence_policy_root=snapshot.evidence_policy.policy_root,
        membership_head_root=snapshot.membership_head_root,
        membership_snapshot_root=snapshot.membership_snapshot_root,
        membership_root=snapshot.membership_root,
        verification_head_root=snapshot.verification_head_root,
        verification_snapshot_root=snapshot.verification_snapshot_root,
        verification_set_root=snapshot.verification_set_root,
        replay_head_root=snapshot.replay_head_root,
        replay_snapshot_root=snapshot.replay_snapshot_root,
        replay_receipt_root=snapshot.replay_receipt_root,
        attestation_roots=tuple(sorted(item.attestation_root for item in additions)),
        disposition_roots=tuple(
            sorted(item.disposition_root for item in additions if item.disposition_root)
        ),
        revocation_roots=tuple(snapshot.revocation_roots),
        source_context_root="",
    )
    return evidence_root_v2("source-context", binding.body())


def _source_read_preconditions_v2(
    source: object,
) -> tuple[
    GovernanceReadPreconditionV2,
    GovernanceReadPreconditionV2,
    GovernanceReadPreconditionV2,
]:
    request, _ = _verified_source(source)
    snapshot = request.snapshot
    return (
        GovernanceReadPreconditionV2(
            stream_ref=snapshot.membership_stream_ref,
            expected_revision=snapshot.membership_revision,
            expected_root=snapshot.membership_head_root,
        ),
        GovernanceReadPreconditionV2(
            stream_ref=snapshot.verification_stream_ref,
            expected_revision=snapshot.verification_revision,
            expected_root=snapshot.verification_head_root,
        ),
        GovernanceReadPreconditionV2(
            stream_ref=snapshot.replay_stream_ref,
            expected_revision=snapshot.replay_revision,
            expected_root=snapshot.replay_head_root,
        ),
    )


__all__: tuple[str, ...] = ()
