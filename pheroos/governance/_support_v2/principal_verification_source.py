"""Deterministic source preparation for durable principal verification sets."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NoReturn, Sequence, SupportsIndex, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_count_v2,
)
from pheroos.governance._support_v2.durable_context import (
    DurableSupportContextV2,
    durable_support_context_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2,
    PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2,
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
    principal_verification_stream_ref_v2,
    principal_verification_transition_id_v2,
)
from pheroos.governance._support_v2.principal_verification_records import (
    PrincipalVerificationRecordV2,
    canonical_verification_records_v2,
)


@dataclass(frozen=True, slots=True)
class _PrincipalVerificationSourceBindingV2:
    request_root: str
    manifest_root: str
    authority_policy_root: str
    commit_policy_root: str
    verification_policy_root: str
    verification_set_root: str
    source_context_root: str

    def body(self) -> dict[str, object]:
        return {
            "version": "pheroos-principal-verification-source-v2",
            "request_root": self.request_root,
            "manifest_root": self.manifest_root,
            "authority_policy_root": self.authority_policy_root,
            "commit_policy_root": self.commit_policy_root,
            "verification_policy_root": self.verification_policy_root,
            "verification_set_root": self.verification_set_root,
        }


@final
class VerifiedPrincipalVerificationSourceV2:
    """Non-portable deterministic preparation proof, never authority itself."""

    __slots__ = ("_binding", "_manifest", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedPrincipalVerificationSourceV2:
        raise TypeError("VerifiedPrincipalVerificationSourceV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedPrincipalVerificationSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedPrincipalVerificationSourceV2 is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedPrincipalVerificationSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedPrincipalVerificationSourceV2 is not portable")

    @property
    def context_root(self) -> str:
        return _verified_source(self)[1].source_context_root


def prepare_principal_verification_set_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    assurance: CommitAssurance,
    run_ref: str,
    target_ref: str,
    epoch: int,
    observed_epoch: int,
    advance_ref: str,
    snapshot_ref: str,
    current_step: int,
    expires_at_step: int,
    mutation_issuer_ref: str,
    records: Sequence[PrincipalVerificationRecordV2],
    parent_snapshot: PrincipalVerificationSetSnapshotV2 | None = None,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSourceV2,
]:
    """Prepare a complete replacement proposal for one fixed lineage."""

    _require_root(domain_root, "principal verification source domain_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("advance_ref", advance_ref),
        ("snapshot_ref", snapshot_ref),
        ("mutation_issuer_ref", mutation_issuer_ref),
    ):
        _require_bounded_text_v2(value, f"principal verification source {label}")
    subject_epoch = _require_count_v2(epoch, "principal verification source epoch")
    _require_count_v2(observed_epoch, "principal verification source observed_epoch")
    step = _require_count_v2(current_step, "principal verification source current_step")
    expiry = _require_count_v2(
        expires_at_step, "principal verification source expires_at_step"
    )
    if expiry <= step:
        raise ValueError("principal verification set expiry must follow current_step")
    context = durable_support_context_v2(
        manifest, profile=profile, assurance=assurance, target_ref=target_ref
    )
    canonical = canonical_verification_records_v2(records)
    parent = _validated_parent(
        parent_snapshot, context, domain_root, scope_ref, run_ref
    )
    if parent is None:
        revision = 1
        parent_revision = 0
        parent_epoch = None
        parent_transition_id = PRINCIPAL_VERIFICATION_GENESIS_TRANSITION_ID_V2
        parent_snapshot_root = PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2
    else:
        if subject_epoch <= parent.epoch:
            raise ValueError("principal verification epoch must advance")
        if step <= parent.current_step:
            raise ValueError("principal verification current_step must advance")
        revision = parent.revision + 1
        parent_revision = parent.revision
        parent_epoch = parent.epoch
        parent_transition_id = parent.transition_id
        parent_snapshot_root = parent.snapshot_root
    stream_ref = principal_verification_stream_ref_v2(
        scope_ref,
        profile,
        assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.principal_verification_policy_root,
        context.protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = principal_verification_transition_id_v2(stream_ref, advance_ref)
    snapshot = PrincipalVerificationSetSnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=assurance,
        authority_policy_root=context.authority_policy_root,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        verification_policy_root=context.principal_verification_policy_root,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=subject_epoch,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        snapshot_ref=snapshot_ref,
        revision=revision,
        parent_revision=parent_revision,
        parent_epoch=parent_epoch,
        parent_transition_id=parent_transition_id,
        parent_snapshot_root=parent_snapshot_root,
        current_step=step,
        expires_at_step=expiry,
        mutation_issuer_ref=mutation_issuer_ref,
        records=canonical,
        record_count=len(canonical),
    )
    request = PrincipalVerificationSetAdvanceRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=subject_epoch,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        snapshot=snapshot,
    )
    return request, _issue_source(request, context.manifest)


def _validated_parent(
    parent: PrincipalVerificationSetSnapshotV2 | None,
    context: DurableSupportContextV2,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
) -> PrincipalVerificationSetSnapshotV2 | None:
    if parent is None:
        return None
    if type(parent) is not PrincipalVerificationSetSnapshotV2:
        raise TypeError("principal verification parent must be an exact snapshot")
    detached = PrincipalVerificationSetSnapshotV2.from_dict(parent.to_dict())
    observed = (
        detached.domain_root,
        detached.scope_ref,
        detached.manifest_root,
        detached.authority_policy_root,
        detached.commit_policy_root,
        detached.verification_policy_root,
        detached.protocol_ref,
        detached.run_ref,
        detached.profile,
        detached.assurance,
    )
    expected = (
        domain_root,
        scope_ref,
        context.manifest_root,
        context.authority_policy_root,
        context.commit_policy_root,
        context.principal_verification_policy_root,
        context.protocol_ref,
        run_ref,
        context.profile,
        context.assurance,
    )
    if observed != expected:
        raise ValueError("principal verification parent is cross-bound")
    return detached


def _issue_source(
    request: PrincipalVerificationSetAdvanceRequestV2,
    manifest: ScopedProtocolManifestV2,
) -> VerifiedPrincipalVerificationSourceV2:
    snapshot = request.snapshot
    provisional = _PrincipalVerificationSourceBindingV2(
        request_root=request.request_root,
        manifest_root=snapshot.manifest_root,
        authority_policy_root=snapshot.authority_policy_root,
        commit_policy_root=snapshot.commit_policy_root,
        verification_policy_root=snapshot.verification_policy_root,
        verification_set_root=snapshot.verification_set_root,
        source_context_root="",
    )
    context_root = _compute_root(
        "principal-verification-v2:source-context", provisional.body()
    )
    binding = replace(provisional, source_context_root=context_root)
    source = object.__new__(VerifiedPrincipalVerificationSourceV2)
    object.__setattr__(source, "_binding", binding)
    object.__setattr__(source, "_manifest", manifest)
    object.__setattr__(
        source,
        "_request",
        PrincipalVerificationSetAdvanceRequestV2.from_dict(request.to_dict()),
    )
    return source


def _verified_source(
    source: object,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    _PrincipalVerificationSourceBindingV2,
]:
    if type(source) is not VerifiedPrincipalVerificationSourceV2:
        raise TypeError("principal verification source proof is invalid")
    try:
        binding = object.__getattribute__(source, "_binding")
        manifest = object.__getattribute__(source, "_manifest")
        request = object.__getattribute__(source, "_request")
    except AttributeError as exc:
        raise TypeError("principal verification source proof is incomplete") from exc
    if (
        type(binding) is not _PrincipalVerificationSourceBindingV2
        or type(manifest) is not ScopedProtocolManifestV2
        or type(request) is not PrincipalVerificationSetAdvanceRequestV2
    ):
        raise TypeError("principal verification source proof shape is invalid")
    detached_request = PrincipalVerificationSetAdvanceRequestV2.from_dict(
        request.to_dict()
    )
    snapshot = detached_request.snapshot
    context = durable_support_context_v2(
        manifest,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        target_ref=snapshot.target_ref,
    )
    expected = (
        detached_request.request_root,
        context.manifest_root,
        context.authority_policy_root,
        context.commit_policy_root,
        context.principal_verification_policy_root,
        snapshot.verification_set_root,
    )
    observed = (
        binding.request_root,
        binding.manifest_root,
        binding.authority_policy_root,
        binding.commit_policy_root,
        binding.verification_policy_root,
        binding.verification_set_root,
    )
    expected_context = _compute_root(
        "principal-verification-v2:source-context",
        _PrincipalVerificationSourceBindingV2(*observed, "").body(),
    )
    if observed != expected or binding.source_context_root != expected_context:
        raise ValueError("principal verification source proof is cross-bound")
    return detached_request, binding


def verify_principal_verification_source_v2(
    request: PrincipalVerificationSetAdvanceRequestV2, *, source: object
) -> None:
    if type(request) is not PrincipalVerificationSetAdvanceRequestV2:
        raise TypeError("principal verification source requires exact request")
    source_request, _ = _verified_source(source)
    if source_request.to_dict() != request.to_dict():
        raise ValueError("principal verification source belongs to another request")


def _verified_source_manifest_v2(
    source: object,
) -> ScopedProtocolManifestV2:
    _verified_source(source)
    manifest = object.__getattribute__(source, "_manifest")
    return ScopedProtocolManifestV2.from_dict(manifest.to_dict())


def _expected_source_context_root_v2(
    request: PrincipalVerificationSetAdvanceRequestV2,
) -> str:
    if type(request) is not PrincipalVerificationSetAdvanceRequestV2:
        raise TypeError("principal verification source context requires exact request")
    snapshot = request.snapshot
    binding = _PrincipalVerificationSourceBindingV2(
        request_root=request.request_root,
        manifest_root=snapshot.manifest_root,
        authority_policy_root=snapshot.authority_policy_root,
        commit_policy_root=snapshot.commit_policy_root,
        verification_policy_root=snapshot.verification_policy_root,
        verification_set_root=snapshot.verification_set_root,
        source_context_root="",
    )
    return _compute_root("principal-verification-v2:source-context", binding.body())


__all__ = [
    "VerifiedPrincipalVerificationSourceV2",
    "prepare_principal_verification_set_v2",
    "verify_principal_verification_source_v2",
]
