"""Pure source-context roots for the durable Support v2 ledger."""

from __future__ import annotations

from dataclasses import dataclass, replace

from pheroos.governance._authority_store_v2_contracts.foundation import _compute_root
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.support_lease_contracts import (
    SupportLeaseV2,
    SupportRevocationV2,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
    support_mutation_delta_root_v2,
)


_SOURCE_VERSION_V2 = "pheroos-support-source-proof-v2"


@dataclass(frozen=True, slots=True)
class _SupportSourceBindingV2:
    domain_root: str
    scope_ref: str
    profile: str
    assurance: str
    manifest_root: str
    commit_policy_root: str
    authority_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    current_step: int
    mutation_ref: str
    transition_id: str
    mutation_issuer_ref: str
    mutation_kind: str
    mutation_provenance_root: str
    mutation_trace_roots: tuple[str, ...]
    request_root: str
    parent_snapshot_root: str
    parent_transition_id: str
    parent_revision: int
    parent_history_root: str
    parent_history_count: int
    membership_stream_ref: str
    membership_snapshot_root: str
    membership_transition_id: str
    proposal_root: str
    membership_principal_root: str
    principal_verification_root: str
    observation_roots: tuple[str, ...]
    observation_set_root: str
    policy_root: str
    issued_lease_root: str
    revoked_lease_root: str
    revocation_root: str
    evicted_lease_roots: tuple[str, ...]
    mutation_delta_root: str
    source_verification_root: str
    context_root: str

    def body(self) -> dict[str, object]:
        return {
            "version": _SOURCE_VERSION_V2,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "profile": self.profile,
            "assurance": self.assurance,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "authority_policy_root": self.authority_policy_root,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "current_step": self.current_step,
            "mutation_ref": self.mutation_ref,
            "transition_id": self.transition_id,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "mutation_kind": self.mutation_kind,
            "mutation_provenance_root": self.mutation_provenance_root,
            "mutation_trace_roots": list(self.mutation_trace_roots),
            "parent_snapshot_root": self.parent_snapshot_root,
            "parent_transition_id": self.parent_transition_id,
            "parent_revision": self.parent_revision,
            "parent_history_root": self.parent_history_root,
            "parent_history_count": self.parent_history_count,
            "membership_stream_ref": self.membership_stream_ref,
            "membership_snapshot_root": self.membership_snapshot_root,
            "membership_transition_id": self.membership_transition_id,
            "proposal_root": self.proposal_root,
            "membership_principal_root": self.membership_principal_root,
            "principal_verification_root": self.principal_verification_root,
            "observation_roots": list(self.observation_roots),
            "observation_set_root": self.observation_set_root,
            "policy_root": self.policy_root,
            "issued_lease_root": self.issued_lease_root,
            "revoked_lease_root": self.revoked_lease_root,
            "revocation_root": self.revocation_root,
            "evicted_lease_roots": list(self.evicted_lease_roots),
            "mutation_delta_root": self.mutation_delta_root,
            "source_verification_root": self.source_verification_root,
        }


def _mutation_lineage_roots(
    *,
    domain_root: str,
    scope_ref: str,
    profile: str,
    assurance: str,
    manifest_root: str,
    commit_policy_root: str,
    authority_policy_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    current_step: int,
    mutation_ref: str,
    transition_id: str,
    mutation_issuer_ref: str,
    mutation_kind: SupportMutationKindV2,
    mutation_provenance_root: str,
    mutation_trace_roots: tuple[str, ...],
    parent_snapshot_root: str,
    parent_transition_id: str,
    parent_revision: int,
    parent_history_root: str,
    parent_history_count: int,
    issued_lease: SupportLeaseV2 | None,
    revoked_lease: SupportLeaseV2 | None,
    revocation: SupportRevocationV2 | None,
    evicted_lease_roots: tuple[str, ...],
    membership: MembershipSnapshotV2 | None,
) -> tuple[str, str]:
    issued_root = "" if issued_lease is None else issued_lease.lease_root
    revoked_root = "" if revoked_lease is None else revoked_lease.lease_root
    revocation_root = "" if revocation is None else revocation.revocation_root
    membership_stream = "" if membership is None else membership.stream_ref
    membership_transition = "" if membership is None else membership.transition_id
    membership_snapshot = "" if membership is None else membership.snapshot_root
    delta_root = support_mutation_delta_root_v2(
        mutation_kind,
        transition_id=transition_id,
        mutation_issuer_ref=mutation_issuer_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        mutation_provenance_root=mutation_provenance_root,
        mutation_trace_roots=mutation_trace_roots,
        issued_lease_root=issued_root,
        revoked_lease_root=revoked_root,
        revocation_root=revocation_root,
        evicted_lease_roots=evicted_lease_roots,
        membership_stream_ref=membership_stream,
        membership_transition_id=membership_transition,
        membership_snapshot_root=membership_snapshot,
    )
    binding = _build_source_binding(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        authority_policy_root=authority_policy_root,
        protocol_ref=protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        mutation_ref=mutation_ref,
        transition_id=transition_id,
        mutation_issuer_ref=mutation_issuer_ref,
        mutation_kind=mutation_kind,
        mutation_provenance_root=mutation_provenance_root,
        mutation_trace_roots=mutation_trace_roots,
        request_root="",
        parent_snapshot_root=parent_snapshot_root,
        parent_transition_id=parent_transition_id,
        parent_revision=parent_revision,
        parent_history_root=parent_history_root,
        parent_history_count=parent_history_count,
        membership_stream_ref=membership_stream,
        membership_transition_id=membership_transition,
        membership_snapshot_root=membership_snapshot,
        issued_lease=issued_lease,
        issued_lease_root=issued_root,
        revoked_lease_root=revoked_root,
        revocation_root=revocation_root,
        evicted_lease_roots=evicted_lease_roots,
        mutation_delta_root=delta_root,
    )
    return binding.context_root, delta_root


def _source_binding_from_request(
    request: SupportAdvanceRequestV2,
) -> _SupportSourceBindingV2:
    snapshot = request.snapshot
    lease = request.issued_lease
    binding = _build_source_binding(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        profile=snapshot.profile,
        assurance=snapshot.assurance.value,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        authority_policy_root=snapshot.authority_policy_root,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        observed_epoch=snapshot.observed_epoch,
        current_step=snapshot.current_step,
        mutation_ref=snapshot.mutation_ref,
        transition_id=snapshot.transition_id,
        mutation_issuer_ref=snapshot.mutation_issuer_ref,
        mutation_kind=request.mutation_kind,
        mutation_provenance_root=snapshot.mutation_provenance_root,
        mutation_trace_roots=tuple(snapshot.mutation_trace_roots),
        request_root=request.request_root,
        parent_snapshot_root=snapshot.parent_snapshot_root,
        parent_transition_id=snapshot.parent_transition_id,
        parent_revision=snapshot.parent_revision,
        parent_history_root=snapshot.parent_history_root,
        parent_history_count=snapshot.parent_history_count,
        membership_stream_ref=request.membership_stream_ref,
        membership_transition_id=request.membership_transition_id,
        membership_snapshot_root=request.membership_snapshot_root,
        issued_lease=lease,
        issued_lease_root=request.issued_lease_root,
        revoked_lease_root=request.revoked_lease_root,
        revocation_root=request.revocation_root,
        evicted_lease_roots=tuple(request.evicted_lease_roots),
        mutation_delta_root=snapshot.mutation_delta_root,
    )
    if snapshot.source_context_root != binding.context_root:
        raise ValueError("support snapshot source context root is mismatched")
    return binding


def _build_source_binding(
    *,
    domain_root: str,
    scope_ref: str,
    profile: str,
    assurance: str,
    manifest_root: str,
    commit_policy_root: str,
    authority_policy_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    current_step: int,
    mutation_ref: str,
    transition_id: str,
    mutation_issuer_ref: str,
    mutation_kind: SupportMutationKindV2,
    mutation_provenance_root: str,
    mutation_trace_roots: tuple[str, ...],
    request_root: str,
    parent_snapshot_root: str,
    parent_transition_id: str,
    parent_revision: int,
    parent_history_root: str,
    parent_history_count: int,
    membership_stream_ref: str,
    membership_transition_id: str,
    membership_snapshot_root: str,
    issued_lease: SupportLeaseV2 | None,
    issued_lease_root: str,
    revoked_lease_root: str,
    revocation_root: str,
    evicted_lease_roots: tuple[str, ...],
    mutation_delta_root: str,
) -> _SupportSourceBindingV2:
    if (issued_lease is None) != (issued_lease_root == ""):
        raise ValueError("support source issued lease material is incomplete")
    lease = issued_lease
    observation_roots = () if lease is None else tuple(lease.positive_observation_roots)
    membership_principal_root = "" if lease is None else lease.membership_principal_root
    principal_root = "" if lease is None else lease.principal_verification_root
    observation_set_root = "" if lease is None else lease.positive_observation_set_root
    proposal_root = "" if lease is None else lease.proposal_root
    policy_root = "" if lease is None else lease.commit_policy_root
    verification_root = _compute_root(
        "support-v2:source-verification",
        {
            "parent_snapshot_root": parent_snapshot_root,
            "parent_history_root": parent_history_root,
            "parent_history_count": parent_history_count,
            "membership_stream_ref": membership_stream_ref,
            "membership_transition_id": membership_transition_id,
            "membership_snapshot_root": membership_snapshot_root,
            "membership_principal_root": membership_principal_root,
            "principal_verification_root": principal_root,
            "observation_roots": list(observation_roots),
            "observation_set_root": observation_set_root,
        },
    )
    provisional = _SupportSourceBindingV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        authority_policy_root=authority_policy_root,
        protocol_ref=protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        mutation_ref=mutation_ref,
        transition_id=transition_id,
        mutation_issuer_ref=mutation_issuer_ref,
        mutation_kind=mutation_kind.value,
        mutation_provenance_root=mutation_provenance_root,
        mutation_trace_roots=mutation_trace_roots,
        request_root=request_root,
        parent_snapshot_root=parent_snapshot_root,
        parent_transition_id=parent_transition_id,
        parent_revision=parent_revision,
        parent_history_root=parent_history_root,
        parent_history_count=parent_history_count,
        membership_stream_ref=membership_stream_ref,
        membership_snapshot_root=membership_snapshot_root,
        membership_transition_id=membership_transition_id,
        proposal_root=proposal_root,
        membership_principal_root=membership_principal_root,
        principal_verification_root=principal_root,
        observation_roots=observation_roots,
        observation_set_root=observation_set_root,
        policy_root=policy_root,
        issued_lease_root=issued_lease_root,
        revoked_lease_root=revoked_lease_root,
        revocation_root=revocation_root,
        evicted_lease_roots=evicted_lease_roots,
        mutation_delta_root=mutation_delta_root,
        source_verification_root=verification_root,
        context_root="",
    )
    return replace(
        provisional,
        context_root=_compute_root("support-v2:source-context", provisional.body()),
    )


def _source_roots_from_request(
    request: SupportAdvanceRequestV2,
) -> tuple[str, str]:
    binding = _source_binding_from_request(request)
    return binding.context_root, binding.source_verification_root


__all__: tuple[str, ...] = ()
