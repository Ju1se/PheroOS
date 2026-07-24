"""Deterministic Store-current Support v2 evaluation."""

from __future__ import annotations

from collections import defaultdict

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CollectiveCommitPolicy

from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_count_v2,
)
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.membership_operations import (
    require_current_membership_state_v2,
)
from pheroos.governance._support_v2.support_equivocation_contracts import (
    SupportEquivocationV2,
)
from pheroos.governance._support_v2.support_evaluation_contracts import (
    SupportEvaluationV2,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    SupportLeaseStatusV2,
    SupportLeaseV2,
)
from pheroos.governance._support_v2.support_state_contracts import SupportSnapshotV2
from pheroos.governance._support_v2.support_state_handle import (
    require_current_support_state_v2,
)
from pheroos.governance._support_v2.support_verification import (
    _validated_support_manifest_context_v2,
)
from pheroos.governance.commit_numeric import ceil_scaled_count, scaled_ratio


def evaluate_support_v2(
    *,
    support_state: object,
    membership_state: object,
    manifest: ScopedProtocolManifestV2,
    candidate_ref: str,
    claim_root: str,
    epoch: int,
    current_step: int,
) -> SupportEvaluationV2:
    """Evaluate only Store-current Support and Membership heads."""

    support = require_current_support_state_v2(support_state)
    membership = require_current_membership_state_v2(membership_state)
    current = _require_count_v2(current_step, "support evaluation current_step")
    _require_bounded_text_v2(candidate_ref, "support evaluation candidate_ref")
    _require_root(claim_root, "support evaluation claim_root")
    _require_count_v2(epoch, "support evaluation epoch")
    commit_policy = _validate_evaluation_context(
        support,
        membership,
        manifest,
        epoch=epoch,
        current_step=current,
    )
    relevant = tuple(
        lease
        for lease in support.leases
        if _lease_matches_evaluation(
            lease,
            membership,
            claim_root=claim_root,
            epoch=epoch,
        )
    )
    findings = _equivocations(support, relevant, current_step=current)
    equivocated_roots = frozenset(
        root for finding in findings for root in finding.conflicting_lease_roots
    )
    included: list[str] = []
    excluded: list[str] = []
    active_clusters: set[str] = set()
    for lease in relevant:
        status = _lease_status(
            lease,
            equivocated_roots=equivocated_roots,
            current_step=current,
        )
        if (
            status is SupportLeaseStatusV2.ACTIVE
            and lease.candidate_ref == candidate_ref
        ):
            included.append(lease.lease_root)
            active_clusters.add(lease.principal_cluster_ref)
        else:
            excluded.append(lease.lease_root)
    eligible = len(membership.clusters)
    threshold = max(
        commit_policy.support_lease.minimum_support_clusters,
        ceil_scaled_count(eligible, commit_policy.support_lease.support_ratio_ppm),
    )
    active = len(active_clusters)
    return SupportEvaluationV2(
        profile=membership.profile,
        assurance=membership.assurance,
        manifest_root=membership.manifest_root,
        commit_policy_root=membership.commit_policy_root,
        protocol_ref=membership.protocol_ref,
        run_ref=membership.run_ref,
        target_ref=membership.target_ref,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=epoch,
        current_step=current,
        membership_snapshot_root=membership.snapshot_root,
        membership_root=membership.membership_root,
        support_snapshot_root=support.snapshot_root,
        eligible_cluster_count=eligible,
        active_support_cluster_count=active,
        support_ratio_ppm=scaled_ratio(active, eligible),
        policy_threshold_clusters=threshold,
        policy_support_met=active >= threshold,
        active_cluster_refs=tuple(active_clusters),
        included_lease_roots=tuple(included),
        excluded_lease_roots=tuple(excluded),
        equivocations=findings,
    )


def support_lease_status_v2(
    support_state: object,
    lease_root: str,
    *,
    current_step: int,
) -> SupportLeaseStatusV2:
    """Return derived status without mutating the current projection."""

    support = require_current_support_state_v2(support_state)
    _require_root(lease_root, "support status lease_root")
    current = _require_count_v2(current_step, "support status current_step")
    matches = tuple(item for item in support.leases if item.lease_root == lease_root)
    if len(matches) != 1:
        raise ValueError("support status lease is absent")
    lease = matches[0]
    peers = tuple(
        item
        for item in support.leases
        if item.target_ref == lease.target_ref
        and item.claim_root == lease.claim_root
        and item.epoch == lease.epoch
        and item.principal_cluster_ref == lease.principal_cluster_ref
    )
    findings = _equivocations(support, peers, current_step=current)
    equivocated = frozenset(
        root for finding in findings for root in finding.conflicting_lease_roots
    )
    return _lease_status(
        lease,
        equivocated_roots=equivocated,
        current_step=current,
    )


def _validate_evaluation_context(
    support: SupportSnapshotV2,
    membership: MembershipSnapshotV2,
    manifest: ScopedProtocolManifestV2,
    *,
    epoch: int,
    current_step: int,
) -> CollectiveCommitPolicy:
    context = _validated_support_manifest_context_v2(
        manifest,
        profile=membership.profile,
        target_ref=membership.target_ref,
    )
    policy = context.commit_policy
    if not membership.clusters:
        raise ValueError("support evaluation fails closed on empty membership")
    if current_step < support.current_step:
        raise ValueError("support evaluation step predates current ledger state")
    if not membership.issued_at_step <= current_step < membership.expires_at_step:
        raise ValueError("support evaluation membership is expired or not yet valid")
    if (
        policy.target != membership.target_ref
        or policy.assurance != membership.assurance.value
        or context.manifest_root != membership.manifest_root
        or context.commit_policy_root != membership.commit_policy_root
        or context.protocol_ref != membership.protocol_ref
        or membership.epoch != epoch
    ):
        raise ValueError("support evaluation policy or membership is cross-bound")
    if (
        support.domain_root != membership.domain_root
        or support.scope_ref != membership.scope_ref
        or support.profile != membership.profile
        or support.assurance is not membership.assurance
        or support.manifest_root != membership.manifest_root
        or support.commit_policy_root != membership.commit_policy_root
        or support.protocol_ref != membership.protocol_ref
        or support.run_ref != membership.run_ref
        or support.target_ref != membership.target_ref
    ):
        raise ValueError("support evaluation states are cross-bound")
    return policy


def _lease_matches_evaluation(
    lease: SupportLeaseV2,
    membership: MembershipSnapshotV2,
    *,
    claim_root: str,
    epoch: int,
) -> bool:
    return bool(
        lease.profile == membership.profile
        and lease.assurance is membership.assurance
        and lease.manifest_root == membership.manifest_root
        and lease.commit_policy_root == membership.commit_policy_root
        and lease.protocol_ref == membership.protocol_ref
        and lease.run_ref == membership.run_ref
        and lease.target_ref == membership.target_ref
        and lease.claim_root == claim_root
        and lease.epoch == epoch
        and lease.membership_stream_ref == membership.stream_ref
        and lease.membership_transition_id == membership.transition_id
        and lease.membership_snapshot_root == membership.snapshot_root
        and lease.membership_root == membership.membership_root
    )


def _lease_status(
    lease: SupportLeaseV2,
    *,
    equivocated_roots: frozenset[str],
    current_step: int,
) -> SupportLeaseStatusV2:
    if current_step < lease.issued_at_step or current_step >= lease.expires_at_step:
        return SupportLeaseStatusV2.EXPIRED
    if lease.lease_root in equivocated_roots:
        return SupportLeaseStatusV2.EQUIVOCATED
    return SupportLeaseStatusV2.ACTIVE


def _equivocations(
    support: SupportSnapshotV2,
    leases: tuple[SupportLeaseV2, ...],
    *,
    current_step: int,
) -> tuple[SupportEquivocationV2, ...]:
    groups: dict[tuple[str, str, int, str], list[SupportLeaseV2]] = defaultdict(list)
    for lease in leases:
        if not lease.issued_at_step <= current_step < lease.expires_at_step:
            continue
        groups[
            (
                lease.target_ref,
                lease.claim_root,
                lease.epoch,
                lease.principal_cluster_ref,
            )
        ].append(lease)
    findings: list[SupportEquivocationV2] = []
    for key in sorted(groups, key=_group_sort_key):
        finding = _group_equivocation(
            support,
            tuple(groups[key]),
            current_step=current_step,
        )
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


def _group_sort_key(
    value: tuple[str, str, int, str],
) -> tuple[bytes, bytes, int, bytes]:
    return (
        value[0].encode("utf-8"),
        value[1].encode("utf-8"),
        value[2],
        value[3].encode("utf-8"),
    )


def _group_equivocation(
    support: SupportSnapshotV2,
    leases: tuple[SupportLeaseV2, ...],
    *,
    current_step: int,
) -> SupportEquivocationV2 | None:
    intervals = tuple(
        interval
        for lease in leases
        if (interval := _active_interval(lease, current_step=current_step)) is not None
    )
    segments = _conflict_segments(intervals)
    if not segments:
        return None
    involved = tuple(
        lease
        for lease, start, end in intervals
        if _intersects_segments(start, end, segments)
    )
    candidates = frozenset(item.candidate_ref for item in involved)
    if len(candidates) < 2:
        return None
    first = min(start for start, _ in segments)
    anchor = involved[0]
    return SupportEquivocationV2(
        target_ref=anchor.target_ref,
        claim_root=anchor.claim_root,
        epoch=anchor.epoch,
        principal_cluster_ref=anchor.principal_cluster_ref,
        support_snapshot_root=support.snapshot_root,
        lease_set_root=support.lease_set_root,
        conflicting_candidate_refs=tuple(candidates),
        conflicting_lease_roots=tuple(item.lease_root for item in involved),
        first_overlap_step=first,
    )


def _active_interval(
    lease: SupportLeaseV2,
    *,
    current_step: int,
) -> tuple[SupportLeaseV2, int, int] | None:
    end = min(lease.expires_at_step, current_step + 1)
    if end <= lease.issued_at_step:
        return None
    return lease, lease.issued_at_step, end


def _conflict_segments(
    intervals: tuple[tuple[SupportLeaseV2, int, int], ...],
) -> tuple[tuple[int, int], ...]:
    events: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for lease, start, end in intervals:
        events[start].append((1, lease.candidate_ref))
        events[end].append((-1, lease.candidate_ref))
    steps = sorted(events)
    active: dict[str, int] = {}
    segments: list[tuple[int, int]] = []
    for index, step in enumerate(steps[:-1]):
        changes = events[step]
        for delta, candidate in changes:
            if delta < 0:
                count = active.get(candidate, 0) - 1
                if count <= 0:
                    active.pop(candidate, None)
                else:
                    active[candidate] = count
        for delta, candidate in changes:
            if delta > 0:
                active[candidate] = active.get(candidate, 0) + 1
        next_step = steps[index + 1]
        if len(active) > 1 and next_step > step:
            if segments and segments[-1][1] == step:
                segments[-1] = (segments[-1][0], next_step)
            else:
                segments.append((step, next_step))
    return tuple(segments)


def _intersects_segments(
    start: int,
    end: int,
    segments: tuple[tuple[int, int], ...],
) -> bool:
    return any(
        start < segment_end and segment_start < end
        for segment_start, segment_end in segments
    )


__all__: tuple[str, ...] = ()
