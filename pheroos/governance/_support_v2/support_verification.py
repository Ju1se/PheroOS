"""Pure upstream verification and deterministic projections for Support v2."""

from __future__ import annotations

from dataclasses import dataclass
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.validation import validate_support_lease_policy

from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_count_v2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MembershipPrincipalV2,
    MembershipSnapshotV2,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_OBSERVATIONS_V2,
    SupportLeaseProposalV2,
    SupportLeaseV2,
    SupportObservationV2,
    SupportRevocationV2,
    canonical_support_observations_v2,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportSnapshotV2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    support_lease_ref_v2,
    support_revocation_ref_v2,
)
from pheroos.governance.commit_numeric import checked_add


@dataclass(frozen=True, slots=True)
class _SupportManifestContextV2:
    manifest: ScopedProtocolManifestV2
    manifest_root: str
    commit_policy: CollectiveCommitPolicy
    commit_policy_root: str
    authority_policy_root: str
    assurance: CommitAssurance
    protocol_ref: str


def _validated_support_manifest_context_v2(
    manifest: object,
    *,
    profile: str,
    target_ref: str,
) -> _SupportManifestContextV2:
    """Detach and derive every policy-owned Support selector."""

    _require_bounded_text_v2(profile, "support manifest profile")
    _require_bounded_text_v2(target_ref, "support manifest target_ref")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("support source requires exact ScopedProtocolManifestV2")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    if target_ref not in {item.id for item in detached.targets}:
        raise ValueError("support target is not declared by its manifest")
    policy = detached.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise ValueError("support manifest has no collective commit policy")
    if policy.target != target_ref:
        raise ValueError("support manifest commit policy target is mismatched")
    try:
        assurance = CommitAssurance(policy.assurance)
    except (TypeError, ValueError) as exc:
        raise ValueError("support manifest assurance is unsupported") from exc
    if profile not in COMMIT_PROFILES_BY_ASSURANCE.get(
        assurance.value,
        frozenset(),
    ):
        raise ValueError("support manifest profile and assurance are mismatched")
    support_diagnostics = validate_support_lease_policy(
        policy.support_lease,
        path="collective_commit_policy.support_lease",
    )
    if support_diagnostics:
        codes = ", ".join(
            sorted({diagnostic.code for diagnostic in support_diagnostics})
        )
        raise ValueError(f"support manifest lease policy is invalid: {codes}")
    manifest_root = detached.manifest_root
    policy_root = commit_policy_fingerprint(policy, profile=profile)
    authority_root = detached.authority_policy.root()
    for value, label in (
        (manifest_root, "manifest_root"),
        (policy_root, "commit_policy_root"),
        (authority_root, "authority_policy_root"),
    ):
        _require_root(value, f"support manifest {label}")
    return _SupportManifestContextV2(
        manifest=detached,
        manifest_root=manifest_root,
        commit_policy=policy,
        commit_policy_root=policy_root,
        authority_policy_root=authority_root,
        assurance=assurance,
        protocol_ref=detached.id,
    )


def _validated_support_prepare_context_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    issuer_ref: str,
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    provenance_root: str,
) -> _SupportManifestContextV2:
    _require_root(domain_root, "support source domain_root")
    _require_root(provenance_root, "support source provenance_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("profile", profile),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("issuer_ref", issuer_ref),
        ("mutation_ref", mutation_ref),
    ):
        _require_bounded_text_v2(value, f"support source {label}")
    _require_count_v2(observed_epoch, "support source observed_epoch")
    _require_count_v2(current_step, "support source current_step")
    return _validated_support_manifest_context_v2(
        manifest,
        profile=profile,
        target_ref=target_ref,
    )


def _validated_child_manifest_v2(
    manifest: object,
    parent: SupportSnapshotV2,
) -> _SupportManifestContextV2:
    context = _validated_support_manifest_context_v2(
        manifest,
        profile=parent.profile,
        target_ref=parent.target_ref,
    )
    expected = (
        context.assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.authority_policy_root,
        context.protocol_ref,
    )
    observed = (
        parent.assurance,
        parent.manifest_root,
        parent.commit_policy_root,
        parent.authority_policy_root,
        parent.protocol_ref,
    )
    if observed != expected:
        raise ValueError("support manifest is cross-bound to the parent ledger")
    return context


def _validate_request_manifest_context_v2(
    request: object,
    context: _SupportManifestContextV2,
) -> None:
    if type(request) is not SupportAdvanceRequestV2:
        raise TypeError("support manifest validation requires exact request v2")
    snapshot = request.snapshot
    observed = (
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.authority_policy_root,
        snapshot.protocol_ref,
    )
    expected = (
        context.assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.authority_policy_root,
        context.protocol_ref,
    )
    if observed != expected:
        raise ValueError("support source manifest is cross-bound")


def project_support_lease_v2(
    *,
    parent: SupportSnapshotV2,
    membership: MembershipSnapshotV2,
    proposal: SupportLeaseProposalV2,
    positive_observations: tuple[SupportObservationV2, ...],
    manifest: ScopedProtocolManifestV2,
    mutation_transition_id: str,
    issuance_issuer_ref: str,
    current_step: int,
    prior_lease: SupportLeaseV2 | None,
    issuance_provenance_root: str,
    issuance_trace_roots: tuple[str, ...],
) -> SupportLeaseV2:
    if type(proposal) is not SupportLeaseProposalV2:
        raise TypeError("support issuance requires exact proposal v2")
    _require_bounded_text_v2(
        mutation_transition_id,
        "support lease mutation_transition_id",
    )
    _require_bounded_text_v2(
        issuance_issuer_ref,
        "support lease issuance_issuer_ref",
    )
    _require_root(issuance_provenance_root, "support issuance provenance_root")
    current = _require_count_v2(current_step, "support issuance current_step")
    if proposal.proposed_at_step > current:
        raise ValueError("support proposal is from a future step")
    context = _validated_support_manifest_context_v2(
        manifest,
        profile=proposal.profile,
        target_ref=proposal.target_ref,
    )
    _validate_policy(proposal, context)
    _validate_parent_proposal(parent, proposal)
    _validate_membership(proposal, membership, current_step=current)
    cluster_ref, membership_principal = _membership_principal(proposal, membership)
    observations, observation_roots, observation_expiry = _validate_observations(
        proposal, positive_observations, current_step=current
    )
    expires = checked_add(
        current,
        context.commit_policy.support_lease.lease_ttl_steps,
    )
    if membership.expires_at_step < expires:
        raise ValueError("support TTL exceeds membership freshness")
    if observation_expiry < expires:
        raise ValueError("support TTL exceeds observation freshness")
    prior_root = "" if prior_lease is None else prior_lease.lease_root
    if prior_lease is not None:
        _validate_switch_prior(
            prior_lease,
            proposal,
            cluster_ref,
            membership_principal,
            membership,
        )
    return SupportLeaseV2(
        lease_ref=support_lease_ref_v2(
            mutation_transition_id,
            proposal.proposal_root,
        ),
        mutation_transition_id=mutation_transition_id,
        proposal_root=proposal.proposal_root,
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_ref=proposal.protocol_ref,
        run_ref=proposal.run_ref,
        target_ref=proposal.target_ref,
        candidate_ref=proposal.candidate_ref,
        claim_root=proposal.claim_root,
        epoch=proposal.epoch,
        principal_ref=proposal.principal_ref,
        principal_cluster_ref=cluster_ref,
        membership_principal_root=membership_principal.principal_root,
        principal_verification_root=membership_principal.verification_root,
        membership_stream_ref=membership.stream_ref,
        membership_transition_id=membership.transition_id,
        membership_snapshot_root=membership.snapshot_root,
        membership_root=membership.membership_root,
        positive_observations=observations,
        positive_observation_roots=observation_roots,
        positive_observation_set_root="",
        prior_lease_root=prior_root,
        nonce=proposal.nonce,
        issuance_issuer_ref=issuance_issuer_ref,
        issued_at_step=current,
        expires_at_step=expires,
        proposal_provenance_root=proposal.provenance_root,
        proposal_trace_roots=proposal.source_trace_roots,
        issuance_provenance_root=issuance_provenance_root,
        issuance_trace_roots=issuance_trace_roots,
    )


def active_support_lease_from_parent_v2(
    parent: SupportSnapshotV2,
    lease_root: str,
    *,
    current_step: int,
) -> SupportLeaseV2:
    _require_root(lease_root, "support selected lease_root")
    current = _require_count_v2(current_step, "support revocation current_step")
    matches = [item for item in parent.leases if item.lease_root == lease_root]
    if len(matches) != 1:
        raise ValueError("support selected lease is absent from verified parent")
    lease = matches[0]
    if not lease.issued_at_step <= current < lease.expires_at_step:
        raise ValueError("only an active support lease may be revoked")
    return lease


def project_support_revocation_v2(
    lease: SupportLeaseV2,
    *,
    mutation_transition_id: str,
    reason_codes: tuple[str, ...],
    revocation_issuer_ref: str,
    current_step: int,
    provenance_root: str,
    source_trace_roots: tuple[str, ...],
) -> SupportRevocationV2:
    _require_bounded_text_v2(
        revocation_issuer_ref,
        "support revocation issuer_ref",
    )
    return SupportRevocationV2(
        revocation_ref=support_revocation_ref_v2(
            mutation_transition_id,
            lease.lease_root,
        ),
        mutation_transition_id=mutation_transition_id,
        lease_root=lease.lease_root,
        profile=lease.profile,
        assurance=lease.assurance,
        manifest_root=lease.manifest_root,
        commit_policy_root=lease.commit_policy_root,
        protocol_ref=lease.protocol_ref,
        run_ref=lease.run_ref,
        target_ref=lease.target_ref,
        candidate_ref=lease.candidate_ref,
        claim_root=lease.claim_root,
        epoch=lease.epoch,
        principal_ref=lease.principal_ref,
        principal_cluster_ref=lease.principal_cluster_ref,
        reason_codes=reason_codes,
        lease_issuance_issuer_ref=lease.issuance_issuer_ref,
        revocation_issuer_ref=revocation_issuer_ref,
        revoked_at_step=current_step,
        provenance_root=provenance_root,
        source_trace_roots=source_trace_roots,
    )


def _validate_policy(
    proposal: SupportLeaseProposalV2,
    context: _SupportManifestContextV2,
) -> None:
    policy = context.commit_policy
    if (
        policy.target != proposal.target_ref
        or policy.assurance != proposal.assurance.value
    ):
        raise ValueError("support proposal policy context is mismatched")
    if (
        context.manifest_root != proposal.manifest_root
        or context.commit_policy_root != proposal.commit_policy_root
        or context.protocol_ref != proposal.protocol_ref
    ):
        raise ValueError("support proposal policy root is mismatched")


def _validate_parent_proposal(
    parent: SupportSnapshotV2,
    proposal: SupportLeaseProposalV2,
) -> None:
    if (
        proposal.profile != parent.profile
        or proposal.assurance is not parent.assurance
        or proposal.manifest_root != parent.manifest_root
        or proposal.commit_policy_root != parent.commit_policy_root
        or proposal.protocol_ref != parent.protocol_ref
        or proposal.run_ref != parent.run_ref
        or proposal.target_ref != parent.target_ref
    ):
        raise ValueError("support proposal is cross-ledger")


def _validate_membership(
    proposal: SupportLeaseProposalV2,
    membership: MembershipSnapshotV2,
    *,
    current_step: int,
) -> None:
    expected = (
        proposal.profile,
        proposal.assurance,
        proposal.manifest_root,
        proposal.commit_policy_root,
        proposal.protocol_ref,
        proposal.run_ref,
        proposal.target_ref,
        proposal.epoch,
    )
    observed = (
        membership.profile,
        membership.assurance,
        membership.manifest_root,
        membership.commit_policy_root,
        membership.protocol_ref,
        membership.run_ref,
        membership.target_ref,
        membership.epoch,
    )
    if observed != expected:
        raise ValueError("support membership is cross-bound")
    if not membership.issued_at_step <= current_step < membership.expires_at_step:
        raise ValueError("support membership is not fresh")


def _membership_principal(
    proposal: SupportLeaseProposalV2,
    membership: MembershipSnapshotV2,
) -> tuple[str, MembershipPrincipalV2]:
    matches = tuple(
        (cluster.cluster_ref, principal)
        for cluster in membership.clusters
        for principal in cluster.principals
        if principal.principal_ref == proposal.principal_ref
    )
    if len(matches) != 1:
        raise ValueError("support principal is absent from current membership")
    return matches[0]


def _validate_observations(
    proposal: SupportLeaseProposalV2,
    observations: tuple[SupportObservationV2, ...],
    *,
    current_step: int,
) -> tuple[tuple[SupportObservationV2, ...], tuple[str, ...], int]:
    if type(observations) is not tuple or not observations:
        raise TypeError("support source observations must be a non-empty exact tuple")
    if len(observations) > MAX_SUPPORT_OBSERVATIONS_V2:
        raise ValueError("support source observation count exceeds its bound")
    if any(type(item) is not SupportObservationV2 for item in observations):
        raise TypeError("support source contains a non-canonical observation")
    detached = tuple(
        SupportObservationV2.from_dict(item.to_dict()) for item in observations
    )
    canonical = canonical_support_observations_v2(detached)
    expected_context = (
        proposal.profile,
        proposal.assurance,
        proposal.manifest_root,
        proposal.commit_policy_root,
        proposal.protocol_ref,
        proposal.run_ref,
        proposal.target_ref,
        proposal.candidate_ref,
        proposal.claim_root,
        proposal.epoch,
    )
    for observation in canonical:
        observed_context = (
            observation.profile,
            observation.assurance,
            observation.manifest_root,
            observation.commit_policy_root,
            observation.protocol_ref,
            observation.run_ref,
            observation.target_ref,
            observation.candidate_ref,
            observation.claim_root,
            observation.epoch,
        )
        if observed_context != expected_context:
            raise ValueError("support observation context is mismatched")
        if (
            not observation.observed_at_step
            <= current_step
            < observation.expires_at_step
        ):
            raise ValueError("support observation is stale or from a future step")
    roots = tuple(item.observation_root for item in canonical)
    if roots != tuple(proposal.positive_observation_roots):
        raise ValueError("support proposal observation roots are incomplete")
    return canonical, roots, min(item.expires_at_step for item in canonical)


def _validate_switch_prior(
    prior: SupportLeaseV2,
    proposal: SupportLeaseProposalV2,
    cluster_ref: str,
    membership_principal: MembershipPrincipalV2,
    membership: MembershipSnapshotV2,
) -> None:
    expected = (
        proposal.profile,
        proposal.assurance,
        proposal.manifest_root,
        proposal.commit_policy_root,
        proposal.protocol_ref,
        proposal.run_ref,
        proposal.target_ref,
        proposal.epoch,
        proposal.principal_ref,
        cluster_ref,
        membership_principal.principal_root,
        membership_principal.verification_root,
        membership.membership_root,
    )
    observed = (
        prior.profile,
        prior.assurance,
        prior.manifest_root,
        prior.commit_policy_root,
        prior.protocol_ref,
        prior.run_ref,
        prior.target_ref,
        prior.epoch,
        prior.principal_ref,
        prior.principal_cluster_ref,
        prior.membership_principal_root,
        prior.principal_verification_root,
        prior.membership_root,
    )
    if observed != expected or prior.candidate_ref == proposal.candidate_ref:
        raise ValueError("support switch prior lease is incompatible")


__all__ = [
    "_validated_support_manifest_context_v2",
    "active_support_lease_from_parent_v2",
    "project_support_lease_v2",
    "project_support_revocation_v2",
]
