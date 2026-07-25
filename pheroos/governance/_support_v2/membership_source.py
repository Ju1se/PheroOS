"""Store-bound preparation for fixed-lineage durable Membership v2."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import NoReturn, SupportsIndex, final

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
from pheroos.governance._support_v2.membership_contracts import (
    MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
    MEMBERSHIP_GENESIS_TRANSITION_ID_V2,
    MembershipClusterV2,
    MembershipCommitRequestV2,
    MembershipPrincipalV2,
    MembershipSnapshotV2,
    membership_stream_ref_v2,
    membership_transition_id_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PrincipalVerificationSetSnapshotV2,
)


@dataclass(frozen=True, slots=True)
class _MembershipSourceBindingV2:
    request_root: str
    manifest_root: str
    authority_policy_root: str
    commit_policy_root: str
    membership_policy_root: str
    verification_set_root: str
    membership_root: str
    source_context_root: str

    def body(self) -> dict[str, object]:
        return {
            "version": "pheroos-membership-source-v2",
            "request_root": self.request_root,
            "manifest_root": self.manifest_root,
            "authority_policy_root": self.authority_policy_root,
            "commit_policy_root": self.commit_policy_root,
            "membership_policy_root": self.membership_policy_root,
            "verification_set_root": self.verification_set_root,
            "membership_root": self.membership_root,
        }


@final
class VerifiedMembershipSourceV2:
    """Non-portable deterministic source binding, not an authority token."""

    __slots__ = ("_binding", "_manifest", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedMembershipSourceV2:
        raise TypeError("VerifiedMembershipSourceV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedMembershipSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedMembershipSourceV2 is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedMembershipSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedMembershipSourceV2 is not portable")

    @property
    def context_root(self) -> str:
        return _verified_source(self)[1].source_context_root


def prepare_membership_commit_v2(
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
    request_ref: str,
    snapshot_ref: str,
    current_step: int,
    expires_at_step: int,
    mutation_issuer_ref: str,
    membership_method: str,
    provenance_ref: str,
    source_trace_roots: tuple[str, ...],
    verification_state: object,
    parent_snapshot: MembershipSnapshotV2 | None = None,
) -> tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2]:
    """Prepare Membership exclusively from one Store-current verification set."""

    _require_root(domain_root, "membership source domain_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("request_ref", request_ref),
        ("snapshot_ref", snapshot_ref),
        ("mutation_issuer_ref", mutation_issuer_ref),
        ("membership_method", membership_method),
        ("provenance_ref", provenance_ref),
    ):
        _require_bounded_text_v2(value, f"membership source {label}")
    subject_epoch = _require_count_v2(epoch, "membership source epoch")
    _require_count_v2(observed_epoch, "membership source observed_epoch")
    issued = _require_count_v2(current_step, "membership source current_step")
    expires = _require_count_v2(expires_at_step, "membership source expires_at_step")
    if expires <= issued:
        raise ValueError("membership expiry must follow current_step")
    context = durable_support_context_v2(
        manifest, profile=profile, assurance=assurance, target_ref=target_ref
    )
    verification, verification_head = _verification_material(verification_state)
    _validate_verification_context(
        verification,
        context=context,
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        epoch=subject_epoch,
        current_step=issued,
        expires_at_step=expires,
    )
    parent = _membership_parent(parent_snapshot)
    _validate_parent_context(
        parent,
        context=context,
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        epoch=subject_epoch,
        current_step=issued,
    )
    clusters = _project_verifications(verification)
    if parent is None:
        revision = 1
        parent_revision = 0
        parent_epoch = None
        parent_transition_id = MEMBERSHIP_GENESIS_TRANSITION_ID_V2
        parent_snapshot_root = MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2
    else:
        revision = parent.revision + 1
        parent_revision = parent.revision
        parent_epoch = parent.epoch
        parent_transition_id = parent.transition_id
        parent_snapshot_root = parent.snapshot_root
    stream_ref = membership_stream_ref_v2(
        scope_ref,
        profile,
        assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.membership_policy_root,
        context.protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = membership_transition_id_v2(stream_ref, request_ref)
    snapshot = MembershipSnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=assurance,
        authority_policy_root=context.authority_policy_root,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        membership_policy_root=context.membership_policy_root,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=subject_epoch,
        observed_epoch=observed_epoch,
        request_ref=request_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        snapshot_ref=snapshot_ref,
        revision=revision,
        parent_revision=parent_revision,
        parent_epoch=parent_epoch,
        parent_transition_id=parent_transition_id,
        parent_snapshot_root=parent_snapshot_root,
        issued_at_step=issued,
        expires_at_step=expires,
        mutation_issuer_ref=mutation_issuer_ref,
        membership_method=membership_method,
        provenance_ref=provenance_ref,
        source_trace_roots=source_trace_roots,
        verification_stream_ref=verification.stream_ref,
        verification_transition_id=verification.transition_id,
        verification_policy_root=verification.verification_policy_root,
        verification_request_ref=verification.advance_ref,
        verification_revision=verification.revision,
        verification_head_root=verification_head,
        verification_snapshot_root=verification.snapshot_root,
        verification_set_root=verification.verification_set_root,
        verification_current_step=verification.current_step,
        verification_expires_at_step=verification.expires_at_step,
        verification_record_count=verification.record_count,
        clusters=clusters,
        cluster_count=len(clusters),
        principal_count=verification.record_count,
    )
    request = MembershipCommitRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=subject_epoch,
        observed_epoch=observed_epoch,
        request_ref=request_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        snapshot=snapshot,
    )
    return request, _issue_source(request, context.manifest)


def _verification_material(
    state: object,
) -> tuple[PrincipalVerificationSetSnapshotV2, str]:
    from pheroos.governance._support_v2.principal_verification_operations import (
        VerifiedPrincipalVerificationSetStateV2,
        _verified_state_view,
        require_current_principal_verification_set_v2,
    )

    if type(state) is not VerifiedPrincipalVerificationSetStateV2:
        raise TypeError("membership requires verified principal verification state")
    snapshot = require_current_principal_verification_set_v2(state)
    _, view = _verified_state_view(state)
    assert view.committed_transition is not None
    return snapshot, view.committed_transition.receipt.head_root


def _membership_parent(
    snapshot: MembershipSnapshotV2 | None,
) -> MembershipSnapshotV2 | None:
    if snapshot is None:
        return None
    if type(snapshot) is not MembershipSnapshotV2:
        raise TypeError("membership parent must be an exact Membership v2 snapshot")
    return MembershipSnapshotV2.from_dict(snapshot.to_dict())


def _validate_verification_context(
    verification: PrincipalVerificationSetSnapshotV2,
    *,
    context: DurableSupportContextV2,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    epoch: int,
    current_step: int,
    expires_at_step: int,
) -> None:
    observed = (
        verification.domain_root,
        verification.scope_ref,
        verification.profile,
        verification.assurance,
        verification.authority_policy_root,
        verification.manifest_root,
        verification.commit_policy_root,
        verification.verification_policy_root,
        verification.protocol_ref,
        verification.run_ref,
        verification.target_ref,
        verification.epoch,
    )
    expected = (
        domain_root,
        scope_ref,
        context.profile,
        context.assurance,
        context.authority_policy_root,
        context.manifest_root,
        context.commit_policy_root,
        context.principal_verification_policy_root,
        context.protocol_ref,
        run_ref,
        context.target_ref,
        epoch,
    )
    if (
        observed != expected
        or verification.current_step > current_step
        or verification.expires_at_step < expires_at_step
    ):
        raise ValueError("membership verification set is stale or cross-bound")


def _validate_parent_context(
    parent: MembershipSnapshotV2 | None,
    *,
    context: DurableSupportContextV2,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    epoch: int,
    current_step: int,
) -> None:
    if parent is None:
        return
    immutable = (
        parent.domain_root,
        parent.scope_ref,
        parent.profile,
        parent.assurance,
        parent.authority_policy_root,
        parent.manifest_root,
        parent.commit_policy_root,
        parent.membership_policy_root,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
    )
    expected = (
        domain_root,
        scope_ref,
        context.profile,
        context.assurance,
        context.authority_policy_root,
        context.manifest_root,
        context.commit_policy_root,
        context.membership_policy_root,
        context.protocol_ref,
        run_ref,
        context.target_ref,
    )
    if immutable != expected:
        raise ValueError("membership parent is cross-bound")
    if epoch <= parent.epoch or current_step <= parent.issued_at_step:
        raise ValueError("membership epoch and current_step must advance")


def _project_verifications(
    snapshot: PrincipalVerificationSetSnapshotV2,
) -> tuple[MembershipClusterV2, ...]:
    grouped: dict[str, list[MembershipPrincipalV2]] = defaultdict(list)
    for record in snapshot.records:
        grouped[record.cluster_ref].append(
            MembershipPrincipalV2(
                principal_ref=record.principal_ref,
                verification_root=record.verification_root,
                verified_issuer_ref=record.verification_issuer_ref,
                verification_method=record.verification_method,
                failure_domain_ref=record.failure_domain_ref,
            )
        )
    return tuple(
        MembershipClusterV2(cluster_ref=cluster_ref, principals=tuple(principals))
        for cluster_ref, principals in sorted(
            grouped.items(), key=lambda item: item[0].encode("utf-8")
        )
    )


def _issue_source(
    request: MembershipCommitRequestV2,
    manifest: ScopedProtocolManifestV2,
) -> VerifiedMembershipSourceV2:
    snapshot = request.snapshot
    provisional = _MembershipSourceBindingV2(
        request_root=request.request_root,
        manifest_root=snapshot.manifest_root,
        authority_policy_root=snapshot.authority_policy_root,
        commit_policy_root=snapshot.commit_policy_root,
        membership_policy_root=snapshot.membership_policy_root,
        verification_set_root=snapshot.verification_set_root,
        membership_root=snapshot.membership_root,
        source_context_root="",
    )
    context_root = _compute_root("membership-v2:source-context", provisional.body())
    source = object.__new__(VerifiedMembershipSourceV2)
    object.__setattr__(
        source, "_binding", replace(provisional, source_context_root=context_root)
    )
    object.__setattr__(source, "_manifest", manifest)
    object.__setattr__(
        source, "_request", MembershipCommitRequestV2.from_dict(request.to_dict())
    )
    return source


def _verified_source(
    source: object,
) -> tuple[MembershipCommitRequestV2, _MembershipSourceBindingV2]:
    if type(source) is not VerifiedMembershipSourceV2:
        raise TypeError("membership source proof is invalid")
    try:
        binding = object.__getattribute__(source, "_binding")
        manifest = object.__getattribute__(source, "_manifest")
        request = object.__getattribute__(source, "_request")
    except AttributeError as exc:
        raise TypeError("membership source proof is incomplete") from exc
    if (
        type(binding) is not _MembershipSourceBindingV2
        or type(manifest) is not ScopedProtocolManifestV2
        or type(request) is not MembershipCommitRequestV2
    ):
        raise TypeError("membership source proof shape is invalid")
    detached = MembershipCommitRequestV2.from_dict(request.to_dict())
    snapshot = detached.snapshot
    context = durable_support_context_v2(
        manifest,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        target_ref=snapshot.target_ref,
    )
    expected = (
        detached.request_root,
        context.manifest_root,
        context.authority_policy_root,
        context.commit_policy_root,
        context.membership_policy_root,
        snapshot.verification_set_root,
        snapshot.membership_root,
    )
    observed = (
        binding.request_root,
        binding.manifest_root,
        binding.authority_policy_root,
        binding.commit_policy_root,
        binding.membership_policy_root,
        binding.verification_set_root,
        binding.membership_root,
    )
    context_root = _compute_root(
        "membership-v2:source-context", _MembershipSourceBindingV2(*observed, "").body()
    )
    if observed != expected or binding.source_context_root != context_root:
        raise ValueError("membership source proof is cross-bound")
    return detached, binding


def verify_membership_request_source_v2(
    request: MembershipCommitRequestV2, *, source: object
) -> None:
    if type(request) is not MembershipCommitRequestV2:
        raise TypeError("membership source requires exact request")
    source_request, _ = _verified_source(source)
    if source_request.to_dict() != request.to_dict():
        raise ValueError("membership source belongs to another request")


def _verified_source_manifest_v2(source: object) -> ScopedProtocolManifestV2:
    _verified_source(source)
    manifest = object.__getattribute__(source, "_manifest")
    return ScopedProtocolManifestV2.from_dict(manifest.to_dict())


def _expected_source_context_root_v2(request: MembershipCommitRequestV2) -> str:
    snapshot = request.snapshot
    binding = _MembershipSourceBindingV2(
        request_root=request.request_root,
        manifest_root=snapshot.manifest_root,
        authority_policy_root=snapshot.authority_policy_root,
        commit_policy_root=snapshot.commit_policy_root,
        membership_policy_root=snapshot.membership_policy_root,
        verification_set_root=snapshot.verification_set_root,
        membership_root=snapshot.membership_root,
        source_context_root="",
    )
    return _compute_root("membership-v2:source-context", binding.body())


__all__ = [
    "VerifiedMembershipSourceV2",
    "prepare_membership_commit_v2",
    "verify_membership_request_source_v2",
]
