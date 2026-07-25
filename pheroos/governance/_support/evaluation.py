from __future__ import annotations
from collections import defaultdict
from collections.abc import Sequence
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    ceil_scaled_count,
    commit_payload_fingerprint,
    scaled_ratio,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CollectiveCommitPolicy, SupportLeasePolicy
from pheroos.governance._support.invariants import (
    _canonical_fingerprints,
    _equivocation_finding_id,
    _same_commit_scope,
    _validate_commit_policy_binding,
    _validate_support_policy,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportEquivocationFinding,
    SupportLease,
    SupportLeaseEvaluation,
    SupportLeaseReplayReceipt,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    SupportLeaseStatus,
    support_lease_fingerprint,
)
from pheroos.governance._support.lease import (
    support_lease_is_authoritative,
    support_lease_revocation_is_authoritative,
    support_lease_revocation_matches,
    support_lease_status,
)
from pheroos.governance._support.membership import (
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_matches,
    _membership_contains_principal,
)
from pheroos.governance._support.replay import (
    _support_replay_receipt_matches_scope,
    _support_replay_scope_root,
    support_lease_replay_state_is_current,
)


def evaluate_support_leases(
    leases: Sequence[SupportLease],
    *,
    revocations: Sequence[SupportLeaseRevocation],
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    commit_policy: CollectiveCommitPolicy,
    candidate_id: str,
    claim_fingerprint: str,
    current_step: int,
) -> SupportLeaseEvaluation:
    current, candidate, claim, policy, eligible_count = (
        _validate_support_evaluation_context(
            membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            replay_state=replay_state,
            commit_policy=commit_policy,
            candidate_id=candidate_id,
            claim_fingerprint=claim_fingerprint,
            current_step=current_step,
        )
    )
    normalized_leases = tuple(leases)
    membership_state_fingerprint, expected_receipts, expected_lease_fingerprints = (
        _expected_support_replay_receipts(
            membership_snapshot,
            membership_epoch_state=membership_epoch_state,
            replay_state=replay_state,
            current_step=current,
        )
    )
    fingerprints = _validated_support_lease_map(
        normalized_leases,
        membership_snapshot=membership_snapshot,
        membership_state_fingerprint=membership_state_fingerprint,
        replay_state=replay_state,
    )
    if set(fingerprints) != expected_lease_fingerprints:
        raise GovernanceError(
            "support evaluation lease set is incomplete or absent from the "
            "authoritative replay state"
        )

    revocations_by_lease = _validated_revocation_map(
        tuple(revocations),
        leases_by_fingerprint=fingerprints,
        current_step=current,
    )
    findings = _find_equivocations(
        normalized_leases,
        revocations_by_lease=revocations_by_lease,
    )
    equivocated = {
        fingerprint
        for finding in findings
        for fingerprint in finding.conflicting_lease_fingerprints
    }
    active_clusters, included, excluded = _active_support_lease_fingerprints(
        fingerprints,
        candidate=candidate,
        claim=claim,
        current_step=current,
        revocations=revocations,
        equivocated=equivocated,
    )
    active_count = len(active_clusters)
    ratio_ppm = scaled_ratio(active_count, eligible_count, scale=WEIGHT_SCALE)
    threshold = max(
        policy.minimum_support_clusters,
        ceil_scaled_count(
            eligible_count,
            policy.support_ratio_ppm,
            scale=WEIGHT_SCALE,
        ),
    )
    lease_root = commit_payload_fingerprint(
        {
            "candidate_id": candidate,
            "claim_fingerprint": claim,
            "commit_policy_root": membership_snapshot.commit_policy_root,
            "current_step": current,
            "epoch": membership_snapshot.epoch,
            "equivocation_finding_ids": tuple(
                finding.finding_id for finding in findings
            ),
            "excluded_lease_fingerprints": tuple(sorted(excluded | equivocated)),
            "included_lease_fingerprints": included,
            "membership_root": membership_snapshot.membership_root,
            "membership_epoch_state_fingerprint": membership_state_fingerprint,
            "run_id": membership_snapshot.run_id,
            "support_replay_scope_root": _support_replay_scope_root(
                expected_receipts,
                profile=membership_snapshot.profile,
            ),
            "target": membership_snapshot.target,
        },
        schema="pheroos-support-lease-evaluation-root-v1",
        profile=membership_snapshot.profile,
    )
    return SupportLeaseEvaluation(
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        manifest_root=membership_snapshot.manifest_root,
        commit_policy_root=membership_snapshot.commit_policy_root,
        protocol_id=membership_snapshot.protocol_id,
        run_id=membership_snapshot.run_id,
        target=membership_snapshot.target,
        candidate_id=candidate,
        claim_fingerprint=claim,
        epoch=membership_snapshot.epoch,
        current_step=current,
        membership_root=membership_snapshot.membership_root,
        membership_epoch_state_fingerprint=membership_state_fingerprint,
        support_replay_scope_root=_support_replay_scope_root(
            expected_receipts,
            profile=membership_snapshot.profile,
        ),
        eligible_cluster_count=eligible_count,
        active_support_cluster_count=active_count,
        support_ratio_ppm=ratio_ppm,
        policy_support_threshold_clusters=threshold,
        policy_support_met=active_count >= threshold,
        active_support_clusters=active_clusters,
        included_lease_fingerprints=included,
        excluded_lease_fingerprints=tuple(sorted(excluded | equivocated)),
        equivocation_findings=findings,
        lease_root=lease_root,
    )


def _validate_support_evaluation_context(
    membership_snapshot: EligiblePrincipalSnapshot,
    *,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    commit_policy: CollectiveCommitPolicy,
    candidate_id: str,
    claim_fingerprint: str,
    current_step: int,
) -> tuple[int, str, str, SupportLeasePolicy, int]:
    if type(membership_snapshot) is not EligiblePrincipalSnapshot:
        raise GovernanceError("support evaluation requires a membership snapshot")
    current = require_commit_step(current_step, "support evaluation current_step")
    candidate = require_commit_text(candidate_id, "support evaluation candidate_id")
    claim = require_commit_fingerprint(
        claim_fingerprint,
        "support evaluation claim_fingerprint",
    )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        manifest_root=membership_snapshot.manifest_root,
        commit_policy_root=membership_snapshot.commit_policy_root,
        protocol_id=membership_snapshot.protocol_id,
        run_id=membership_snapshot.run_id,
        target=membership_snapshot.target,
        epoch=membership_snapshot.epoch,
        current_step=current,
    ):
        raise GovernanceError(
            "support evaluation membership is forged, stale, or mismatched"
        )
    if not support_lease_replay_state_is_current(replay_state):
        raise GovernanceError(
            "support evaluation requires the authoritative current replay state"
        )
    if (
        replay_state.profile != membership_snapshot.profile
        or replay_state.protocol_id != membership_snapshot.protocol_id
    ):
        raise GovernanceError("support evaluation replay authority binding mismatch")
    _validate_commit_policy_binding(commit_policy, membership_snapshot)
    policy = commit_policy.support_lease
    _validate_support_policy(policy)
    eligible_count = len(membership_snapshot.eligible_clusters)
    if eligible_count == 0:
        raise GovernanceError(
            "eligible membership is empty; support policy is incomplete"
        )
    return current, candidate, claim, policy, eligible_count


def _expected_support_replay_receipts(
    membership_snapshot: EligiblePrincipalSnapshot,
    *,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    current_step: int,
) -> tuple[str, tuple[SupportLeaseReplayReceipt, ...], set[str]]:
    membership_state_fingerprint = eligible_membership_epoch_state_fingerprint(
        membership_epoch_state
    )
    expected_receipts = tuple(
        receipt
        for receipt in replay_state.receipts
        if _support_replay_receipt_matches_scope(
            receipt,
            membership_snapshot=membership_snapshot,
            membership_epoch_state_fingerprint=membership_state_fingerprint,
        )
        and receipt.issued_at_step <= current_step
    )
    expected_lease_fingerprints = {
        receipt.lease_fingerprint for receipt in expected_receipts
    }
    return (
        membership_state_fingerprint,
        expected_receipts,
        expected_lease_fingerprints,
    )


def _validated_support_lease_map(
    leases: Sequence[SupportLease],
    *,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_state_fingerprint: str,
    replay_state: SupportLeaseReplayState,
) -> dict[str, SupportLease]:
    claims_by_candidate: dict[str, str] = {}
    fingerprints: dict[str, SupportLease] = {}
    lease_ids: set[str] = set()
    nonces: set[str] = set()
    for lease in leases:
        _validate_support_lease_scope(
            lease,
            membership_snapshot=membership_snapshot,
            membership_state_fingerprint=membership_state_fingerprint,
            replay_state=replay_state,
        )
        existing_claim = claims_by_candidate.setdefault(
            lease.candidate_id,
            lease.claim_fingerprint,
        )
        if existing_claim != lease.claim_fingerprint:
            raise GovernanceError(
                "support evaluation detected one candidate bound to conflicting claims"
            )
        if not _membership_contains_principal(
            membership_snapshot,
            principal_id=lease.principal_id,
            cluster_id=lease.principal_cluster_id,
            verification_fingerprint=lease.principal_verification_fingerprint,
        ):
            raise GovernanceError("support evaluation lease principal is not eligible")
        fingerprint = support_lease_fingerprint(lease)
        if fingerprint in fingerprints or lease.lease_id in lease_ids:
            raise GovernanceError("support evaluation contains a duplicate lease")
        replay_key = f"{lease.principal_cluster_id}\x00{lease.nonce}"
        if replay_key in nonces:
            raise GovernanceError("support evaluation contains a replayed lease nonce")
        fingerprints[fingerprint] = lease
        lease_ids.add(lease.lease_id)
        nonces.add(replay_key)
    return fingerprints


def _validate_support_lease_scope(
    lease: SupportLease,
    *,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_state_fingerprint: str,
    replay_state: SupportLeaseReplayState,
) -> None:
    if not support_lease_is_authoritative(lease):
        raise GovernanceError("support evaluation contains a forged lease")
    if not _same_commit_scope(lease, membership_snapshot):
        raise GovernanceError("support evaluation lease binding mismatch")
    if lease.membership_root != membership_snapshot.membership_root:
        raise GovernanceError("support evaluation lease membership root mismatch")
    if lease.membership_epoch_state_fingerprint != membership_state_fingerprint:
        raise GovernanceError(
            "support evaluation lease membership epoch state mismatch"
        )
    if lease.replay_authority_key != replay_state.authority_key:
        raise GovernanceError("support evaluation lease replay authority mismatch")


def _active_support_lease_fingerprints(
    fingerprints: dict[str, SupportLease],
    *,
    candidate: str,
    claim: str,
    current_step: int,
    revocations: Sequence[SupportLeaseRevocation],
    equivocated: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...], set[str]]:
    active_by_cluster: dict[str, list[str]] = defaultdict(list)
    excluded: set[str] = set()
    for fingerprint, lease in fingerprints.items():
        if lease.candidate_id != candidate or lease.claim_fingerprint != claim:
            continue
        status = support_lease_status(
            lease,
            current_step=current_step,
            revocations=tuple(revocations),
            equivocated_lease_fingerprints=tuple(equivocated),
        )
        if status is SupportLeaseStatus.ACTIVE:
            active_by_cluster[lease.principal_cluster_id].append(fingerprint)
        else:
            excluded.add(fingerprint)

    active_clusters = tuple(sorted(active_by_cluster))
    included = tuple(
        fingerprint
        for cluster_id in active_clusters
        for fingerprint in sorted(active_by_cluster[cluster_id])
    )
    return active_clusters, included, excluded


def _validated_revocation_map(
    revocations: Sequence[SupportLeaseRevocation],
    *,
    leases_by_fingerprint: dict[str, SupportLease],
    current_step: int,
) -> dict[str, SupportLeaseRevocation]:
    result: dict[str, SupportLeaseRevocation] = {}
    revocation_ids: set[str] = set()
    for revocation in revocations:
        if not support_lease_revocation_is_authoritative(revocation):
            raise GovernanceError("support evaluation contains a forged revocation")
        if revocation.revocation_id in revocation_ids:
            raise GovernanceError("support evaluation repeats a revocation id")
        lease = leases_by_fingerprint.get(revocation.lease_fingerprint)
        if lease is None:
            raise GovernanceError("support evaluation contains an orphan revocation")
        if not support_lease_revocation_matches(
            revocation,
            lease=lease,
            current_step=max(current_step, revocation.revoked_at_step),
        ):
            raise GovernanceError("support evaluation revocation binding mismatch")
        if revocation.lease_fingerprint in result:
            raise GovernanceError("support lease has multiple revocations")
        revocation_ids.add(revocation.revocation_id)
        result[revocation.lease_fingerprint] = revocation
    return result


def _find_equivocations(
    leases: Sequence[SupportLease],
    *,
    revocations_by_lease: dict[str, SupportLeaseRevocation],
) -> tuple[SupportEquivocationFinding, ...]:
    by_cluster: dict[str, list[tuple[SupportLease, str, int]]] = defaultdict(list)
    for lease in leases:
        fingerprint = support_lease_fingerprint(lease)
        revocation = revocations_by_lease.get(fingerprint)
        end = (
            revocation.revoked_at_step
            if revocation is not None
            else lease.expires_at_step
        )
        by_cluster[lease.principal_cluster_id].append((lease, fingerprint, end))

    findings: list[SupportEquivocationFinding] = []
    for cluster_id, records in sorted(by_cluster.items()):
        conflicts: set[str] = set()
        candidates: set[str] = set()
        overlap_steps: list[int] = []
        for index, (left, left_fingerprint, left_end) in enumerate(records):
            for right, right_fingerprint, right_end in records[index + 1 :]:
                if left.candidate_id == right.candidate_id:
                    continue
                overlap_start = max(left.issued_at_step, right.issued_at_step)
                overlap_end = min(left_end, right_end)
                if overlap_start < overlap_end:
                    conflicts.update((left_fingerprint, right_fingerprint))
                    candidates.update((left.candidate_id, right.candidate_id))
                    overlap_steps.append(overlap_start)
        if not conflicts:
            continue
        prototype = records[0][0]
        normalized_candidates = require_commit_labels(
            tuple(candidates),
            "support equivocation candidates",
        )
        normalized_conflicts = _canonical_fingerprints(
            tuple(conflicts),
            "support equivocation lease fingerprints",
        )
        first_overlap = min(overlap_steps)
        finding_id = _equivocation_finding_id(
            profile=prototype.profile,
            assurance=prototype.assurance,
            manifest_root=prototype.manifest_root,
            commit_policy_root=prototype.commit_policy_root,
            protocol_id=prototype.protocol_id,
            run_id=prototype.run_id,
            target=prototype.target,
            epoch=prototype.epoch,
            cluster_id=cluster_id,
            candidates=normalized_candidates,
            lease_fingerprints=normalized_conflicts,
            first_overlap_step=first_overlap,
        )
        findings.append(
            SupportEquivocationFinding(
                finding_id=finding_id,
                profile=prototype.profile,
                assurance=prototype.assurance,
                manifest_root=prototype.manifest_root,
                commit_policy_root=prototype.commit_policy_root,
                protocol_id=prototype.protocol_id,
                run_id=prototype.run_id,
                target=prototype.target,
                epoch=prototype.epoch,
                principal_cluster_id=cluster_id,
                conflicting_candidates=normalized_candidates,
                conflicting_lease_fingerprints=normalized_conflicts,
                first_overlap_step=first_overlap,
            )
        )
    return tuple(findings)


evaluate_support_leases.__module__ = "pheroos.governance.support_lease"
