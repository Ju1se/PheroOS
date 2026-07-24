"""Exact bounded current-projection rules for Support v2."""

from __future__ import annotations

from pheroos.governance._support_v2.common import _require_count_v2
from pheroos.governance._support_v2.support_lease_contracts import (
    SupportLeaseV2,
    canonical_support_leases_v2,
)
from pheroos.governance._support_v2.support_request_contracts import (
    SupportAdvanceRequestV2,
    _validate_support_mutation_semantics_v2,
)
from pheroos.governance._support_v2.support_snapshot_contracts import (
    SupportSnapshotV2,
)


def _current_projection(
    parent: SupportSnapshotV2,
    *,
    current_step: int,
) -> tuple[tuple[SupportLeaseV2, ...], tuple[str, ...]]:
    current = _require_count_v2(current_step, "support mutation current_step")
    if current < parent.current_step:
        raise ValueError("support mutation time moves backwards")
    retained: list[SupportLeaseV2] = []
    evicted: list[str] = []
    for lease in parent.leases:
        if current < lease.issued_at_step:
            raise ValueError("support parent contains a future lease")
        if current >= lease.expires_at_step:
            evicted.append(lease.lease_root)
        else:
            retained.append(lease)
    return (
        canonical_support_leases_v2(tuple(retained)),
        tuple(sorted(evicted, key=lambda item: item.encode("ascii"))),
    )


def _validate_transition_delta(
    request: SupportAdvanceRequestV2,
    parent: SupportSnapshotV2,
) -> None:
    _validate_support_mutation_semantics_v2(request)
    snapshot = request.snapshot
    immutable = (
        "domain_root",
        "scope_ref",
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "authority_policy_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "initialized_at_step",
    )
    if any(getattr(snapshot, name) != getattr(parent, name) for name in immutable):
        raise ValueError("support child context is mismatched")
    if (
        snapshot.parent_revision != parent.revision
        or snapshot.parent_transition_id != parent.transition_id
        or snapshot.parent_snapshot_root != parent.snapshot_root
        or snapshot.revision != parent.revision + 1
        or snapshot.parent_history_root != parent.history_root
        or snapshot.parent_history_count != parent.history_count
        or snapshot.observed_epoch < parent.observed_epoch
    ):
        raise ValueError("support child parent history is mismatched")
    retained, evicted = _current_projection(
        parent,
        current_step=snapshot.current_step,
    )
    if tuple(request.evicted_lease_roots) != evicted:
        raise ValueError("support expiry eviction delta is not exact")
    projected = {item.lease_root: item for item in retained}
    revoked = request.revoked_lease
    if revoked is not None:
        prior = projected.pop(revoked.lease_root, None)
        if prior is None or prior.to_dict() != revoked.to_dict():
            raise ValueError("support revocation does not remove its exact prior lease")
    issued = request.issued_lease
    if issued is not None:
        if issued.lease_root in projected:
            raise ValueError("support issuance collides with the current projection")
        projected[issued.lease_root] = issued
    expected = {root: lease.to_dict() for root, lease in projected.items()}
    observed = {lease.lease_root: lease.to_dict() for lease in snapshot.leases}
    if observed != expected:
        raise ValueError("support current authority projection delta is not exact")


__all__: tuple[str, ...] = ()
