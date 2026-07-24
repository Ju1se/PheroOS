"""Committed record, read-set, history, and dependency verification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, cast

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
    _portable_projection,
)
from pheroos.governance._commit_certificate_v2.state_records import (
    _decode_committed_certificate_view_v2,
)
from pheroos.governance._commit_decision_v2.state_records import (
    _decode_committed_decision_view_v2,
)
from pheroos.governance._distributed_v2.dependency_contracts import (
    DistributedDependencyV2,
)
from pheroos.governance._distributed_v2.enums import (
    DistributedDependencyRoleV2,
    DistributedLaneV2,
)
from pheroos.governance._distributed_v2.events import _distributed_event_v2
from pheroos.governance._distributed_v2.lane_states import DistributedEpochStateV2
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2
from pheroos.governance._distributed_v2.state_contracts import (
    DISTRIBUTED_LANE_STATE_SCHEMA_V2,
    DistributedLaneSnapshotV2,
)
from pheroos.governance._support_v2.membership_state import (
    _decode_committed_view_shallow as _decode_membership_view,
)
from pheroos.governance._support_v2.principal_verification_state import (
    _decode_committed_view_shallow as _decode_verification_view,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


class _SessionBindingV2(TypedDict):
    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    request_root: str
    operation: str
    observed_epoch: int
    grant_ref: str
    grant_root: str
    grant_binding_ref: str
    grant_expected_revision: int
    grant_expected_root: str
    lifecycle_expected_revision: int
    lifecycle_expected_root: str
    target_refs: list[str]
    action_refs: list[str]


_STATE_FIELDS = frozenset(
    {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "transition_id",
        "request_root",
        "request",
        "snapshot_root",
        "snapshot",
        "source_context_root",
        "lane_state_root",
        "dependency_set_root",
        "session_binding",
    }
)
_SESSION_FIELDS = frozenset(_SessionBindingV2.__annotations__)


def _distributed_state_records_v2(
    request: DistributedAdvanceRequestV2,
    session_binding: Mapping[str, object],
) -> dict[str, object]:
    snapshot = request.snapshot
    return {
        "schema": DISTRIBUTED_LANE_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": snapshot.snapshot_root,
        "snapshot": snapshot.to_dict(),
        "source_context_root": snapshot.source_context_root,
        "lane_state_root": snapshot.state.state_root,
        "dependency_set_root": snapshot.dependency_set_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_committed_distributed_view_v2(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    *,
    reader: GovernanceStateReaderV2 | None,
) -> tuple[DistributedAdvanceRequestV2, DistributedLaneSnapshotV2, _SessionBindingV2]:
    canonical = _canonical_commit_view_v2(view)
    if (
        canonical.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or canonical.committed_transition is None
    ):
        raise ValueError("distributed committed transition is unavailable")
    transition = canonical.committed_transition.batch.transition
    if transition is None:
        raise ValueError("distributed committed state transition is unavailable")
    request, snapshot, binding = _decode_state_records_v2(
        transition.state_records,
        domain,
    )
    receipt = canonical.committed_transition.receipt
    inclusion = canonical.committed_transition.inclusion_proof
    if (
        receipt.domain_root != domain.domain_root
        or receipt.scope_ref != domain.scope_ref
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
        or receipt.revision != snapshot.revision
        or inclusion.receipt_root != receipt.receipt_root
    ):
        raise ValueError("distributed committed receipt is cross-bound")
    _validate_read_set_v2(canonical, snapshot, binding)
    expected_event = _distributed_event_v2(
        request,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=canonical.committed_transition.batch.read_set.root(),
    )
    if canonical.committed_transition.batch.trace_batch.events != (expected_event,):
        raise ValueError("distributed Trace lineage is mismatched")
    if reader is not None:
        _verify_dependencies(snapshot, domain, reader)
        _verify_parent(snapshot, domain, reader)
    return request, snapshot, binding


def _decode_state_records_v2(
    value: object,
    domain: AuthorityDomainV2,
) -> tuple[DistributedAdvanceRequestV2, DistributedLaneSnapshotV2, _SessionBindingV2]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _STATE_FIELDS:
        raise ValueError("distributed committed state fields are invalid")
    state = cast(dict[str, object], projected)
    if (
        state["schema"] != DISTRIBUTED_LANE_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("distributed committed state domain is mismatched")
    request = DistributedAdvanceRequestV2.from_dict(state["request"])
    snapshot = DistributedLaneSnapshotV2.from_dict(state["snapshot"])
    if (
        request.snapshot.to_dict() != snapshot.to_dict()
        or state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != snapshot.snapshot_root
        or state["source_context_root"] != snapshot.source_context_root
        or state["lane_state_root"] != snapshot.state.state_root
        or state["dependency_set_root"] != snapshot.dependency_set_root
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("distributed committed state is cross-bound")
    binding = _validate_session_binding(state["session_binding"], request)
    return request, snapshot, binding


def _validate_session_binding(
    value: object,
    request: DistributedAdvanceRequestV2,
) -> _SessionBindingV2:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_FIELDS:
        raise ValueError("distributed session binding fields are invalid")
    binding = cast(_SessionBindingV2, projected)
    actions = _required_actions(request.snapshot)
    expected: tuple[object, ...] = (
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.mutation_ref,
        request.request_root,
        GovernanceIssuerOperationV2.EVALUATE_QUORUM.value,
        request.observed_epoch,
        [request.target_ref],
        list(actions),
    )
    observed = (
        binding["domain_root"],
        binding["scope_ref"],
        binding["run_ref"],
        binding["request_ref"],
        binding["request_root"],
        binding["operation"],
        binding["observed_epoch"],
        binding["target_refs"],
        binding["action_refs"],
    )
    if observed != expected:
        raise ValueError("distributed stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("distributed stored grant binding is invalid")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref, binding["grant_ref"]
        ),
        expected_revision=binding["grant_expected_revision"],
        expected_root=binding["grant_expected_root"],
    )
    GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=binding["lifecycle_expected_revision"],
        expected_root=binding["lifecycle_expected_root"],
    )
    return binding


def _validate_read_set_v2(
    view: GovernanceCommitViewV2,
    snapshot: DistributedLaneSnapshotV2,
    binding: _SessionBindingV2,
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    entries = view.committed_transition.batch.read_set.entries
    observed = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in entries
    }
    if len(observed) != len(entries):
        raise ValueError("distributed read set repeats a stream")
    expected = {
        snapshot.stream_ref: (snapshot.parent_revision, receipt.parent_root),
        **{
            item.stream_ref: (item.revision, item.head_root)
            for item in snapshot.dependencies
        },
        governance_issuer_grant_stream_ref_v2(
            snapshot.scope_ref, binding["grant_ref"]
        ): (binding["grant_expected_revision"], binding["grant_expected_root"]),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    }
    if observed != expected:
        raise ValueError("distributed committed read set is not closed")


def _verify_dependencies(
    snapshot: DistributedLaneSnapshotV2,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> None:
    for dependency in snapshot.dependencies:
        if dependency.revision == 0:
            continue
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                snapshot.scope_ref,
                dependency.stream_ref,
                dependency.transition_id,
                expected_receipt_root=dependency.receipt_root,
            )
        )
        if view.committed_transition is None:
            raise ValueError("distributed historical dependency is unavailable")
        receipt = view.committed_transition.receipt
        inclusion = view.committed_transition.inclusion_proof
        if (
            receipt.revision != dependency.revision
            or receipt.head_root != dependency.head_root
            or receipt.receipt_root != dependency.receipt_root
            or inclusion.inclusion_root != dependency.inclusion_root
            or _dependency_snapshot_root(dependency, view, domain, reader)
            != dependency.snapshot_root
        ):
            raise ValueError("distributed historical dependency is mismatched")


def _dependency_snapshot_root(
    dependency: DistributedDependencyV2,
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> str:
    role = dependency.role
    if role in {
        DistributedDependencyRoleV2.EPOCH,
        DistributedDependencyRoleV2.PROPOSAL,
        DistributedDependencyRoleV2.WITNESS,
        DistributedDependencyRoleV2.CERTIFICATE,
    }:
        _, distributed_snapshot, _ = _decode_committed_distributed_view_v2(
            view, domain, reader=reader
        )
        expected_lane = DistributedLaneV2(role.value)
        if distributed_snapshot.lane is not expected_lane:
            raise ValueError("distributed dependency lane is mismatched")
        return distributed_snapshot.snapshot_root
    if role is DistributedDependencyRoleV2.DECISION:
        _, decision_snapshot, _ = _decode_committed_decision_view_v2(
            view, domain, reader=reader
        )
        return decision_snapshot.snapshot_root
    if role is DistributedDependencyRoleV2.CENTRAL_CERTIFICATE:
        _, certificate_snapshot, _ = _decode_committed_certificate_view_v2(
            view, domain, reader=reader
        )
        return certificate_snapshot.snapshot_root
    if role is DistributedDependencyRoleV2.MEMBERSHIP:
        membership_request, _ = _decode_membership_view(view, domain)
        return membership_request.snapshot.snapshot_root
    verification_request, _ = _decode_verification_view(view, domain)
    return verification_request.snapshot.snapshot_root


def _verify_parent(
    snapshot: DistributedLaneSnapshotV2,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> None:
    if snapshot.parent_revision == 0:
        return
    parent_view = _canonical_commit_view_v2(
        reader.load_commit_view_v2(
            snapshot.scope_ref, snapshot.stream_ref, snapshot.parent_transition_id
        )
    )
    _, parent, _ = _decode_committed_distributed_view_v2(
        parent_view, domain, reader=None
    )
    if (
        parent.revision != snapshot.parent_revision
        or parent.snapshot_root != snapshot.parent_snapshot_root
        or parent.history_root != snapshot.parent_history_root
        or parent.history_count != snapshot.parent_history_count
        or parent.lane is not snapshot.lane
    ):
        raise ValueError("distributed parent history is mismatched")
    _verify_parent(parent, domain, reader)


def _required_actions(snapshot: DistributedLaneSnapshotV2) -> tuple[str, ...]:
    if snapshot.lane is not DistributedLaneV2.EPOCH:
        return ()
    state = snapshot.state
    if type(state) is not DistributedEpochStateV2:
        raise TypeError("distributed epoch action state is invalid")
    return tuple(state.transition_certificate.required_action_refs)


def _head_from_view_v2(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("distributed committed head is unavailable")
    receipt = view.committed_transition.receipt
    return GovernanceHeadV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=receipt.stream_ref,
        revision=receipt.revision,
        parent_root=receipt.parent_root,
        state_root=receipt.state_root,
        transition_id=receipt.transition_id,
        batch_root=receipt.batch_root,
        head_root=receipt.head_root,
    )


__all__: tuple[str, ...] = ()
