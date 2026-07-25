"""Committed state, read-set, and Trace verification for Decision v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
    _portable_projection,
)
from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_STATE_SCHEMA_V2,
    _exact_mapping,
    _require_root,
)
from pheroos.governance._commit_decision_v2.events import _commit_decision_events_v2
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


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
        "session_binding",
    }
)
_SESSION_FIELDS = frozenset(
    {
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "operation",
        "observed_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "grant_expected_revision",
        "grant_expected_root",
        "lifecycle_expected_revision",
        "lifecycle_expected_root",
        "target_refs",
        "action_refs",
    }
)


def _decision_state_records_v2(
    request: CommitDecisionRequestV2,
    snapshot: CommitDecisionSnapshotV2,
    session_binding: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": COMMIT_DECISION_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": snapshot.snapshot_root,
        "snapshot": snapshot.to_dict(),
        "source_context_root": snapshot.source_context_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_committed_decision_view_v2(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    *,
    reader: GovernanceStateReaderV2 | None,
) -> tuple[CommitDecisionRequestV2, CommitDecisionSnapshotV2, dict[str, object]]:
    view = _canonical_commit_view_v2(view)
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
        or view.position_observation is None
        or view.committed_transition.batch.transition is None
    ):
        raise ValueError("commit decision view is not committed")
    records = _portable_projection(
        view.committed_transition.batch.transition.state_records
    )
    state = _exact_mapping(records, _STATE_FIELDS, "commit decision committed state")
    if (
        state["schema"] != COMMIT_DECISION_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("commit decision committed state domain is mismatched")
    request = CommitDecisionRequestV2.from_dict(state["request"])
    snapshot = CommitDecisionSnapshotV2.from_dict(state["snapshot"])
    source_root = _require_root(
        state["source_context_root"], "commit decision source_context_root"
    )
    observed = (
        state["stream_ref"],
        state["transition_id"],
        state["request_root"],
        state["snapshot_root"],
        source_root,
    )
    expected: tuple[object, ...] = (
        request.stream_ref,
        request.transition_id,
        request.request_root,
        snapshot.snapshot_root,
        snapshot.source_context_root,
    )
    if observed != expected:
        raise ValueError("commit decision committed state payload is mismatched")
    binding = _validate_session_binding(state["session_binding"], request)
    receipt = view.committed_transition.receipt
    if (
        receipt.stream_ref != snapshot.stream_ref
        or receipt.transition_id != snapshot.transition_id
        or receipt.revision != snapshot.revision
    ):
        raise ValueError("commit decision committed receipt is mismatched")
    _validate_read_set(view, snapshot, binding)
    events = _commit_decision_events_v2(
        request,
        snapshot,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    if view.committed_transition.batch.trace_batch.events != events:
        raise ValueError("commit decision committed Trace lineage is mismatched")
    if reader is not None:
        _validate_history(reader, domain, snapshot)
    return request, snapshot, binding


def _validate_session_binding(
    value: object, request: CommitDecisionRequestV2
) -> dict[str, object]:
    projected = _portable_projection(value)
    binding = _exact_mapping(
        projected, _SESSION_FIELDS, "commit decision stored session binding"
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
    expected: tuple[object, ...] = (
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.mutation_ref,
        request.request_root,
        GovernanceIssuerOperationV2.EVALUATE_QUORUM.value,
        request.observed_epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("commit decision stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("commit decision stored grant binding is invalid")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref, cast(str, binding["grant_ref"])
        ),
        expected_revision=cast(int, binding["grant_expected_revision"]),
        expected_root=cast(str, binding["grant_expected_root"]),
    )
    GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=cast(int, binding["lifecycle_expected_revision"]),
        expected_root=cast(str, binding["lifecycle_expected_root"]),
    )
    return binding


def _validate_read_set(
    view: GovernanceCommitViewV2,
    snapshot: CommitDecisionSnapshotV2,
    binding: Mapping[str, object],
) -> None:
    assert view.committed_transition is not None
    entries = view.committed_transition.batch.read_set.entries
    observed = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in entries
    }
    if len(observed) != len(entries):
        raise ValueError("commit decision read set contains duplicate streams")
    expected = {
        item.stream_ref: (item.revision, item.head_root)
        for item in snapshot.dependencies
    }
    expected[
        governance_issuer_grant_stream_ref_v2(
            snapshot.scope_ref, cast(str, binding["grant_ref"])
        )
    ] = (
        cast(int, binding["grant_expected_revision"]),
        cast(str, binding["grant_expected_root"]),
    )
    expected[GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2] = (
        cast(int, binding["lifecycle_expected_revision"]),
        cast(str, binding["lifecycle_expected_root"]),
    )
    if observed != expected:
        raise ValueError("commit decision authority read set is mismatched")


def _validate_history(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    child: CommitDecisionSnapshotV2,
) -> None:
    seen = {child.transition_id}
    remaining = child.parent_revision
    while remaining:
        try:
            view = reader.load_commit_view_v2(
                child.scope_ref, child.stream_ref, child.parent_transition_id
            )
        except KeyError as exc:
            raise ValueError(
                "commit decision historical parent is unavailable"
            ) from exc
        _, parent, _ = _decode_committed_decision_view_v2(view, domain, reader=None)
        _validate_successor(child, parent)
        if parent.transition_id in seen or parent.revision != remaining:
            raise ValueError("commit decision historical lineage is cyclic or gapped")
        seen.add(parent.transition_id)
        child = parent
        remaining -= 1


def _validate_successor(
    child: CommitDecisionSnapshotV2, parent: CommitDecisionSnapshotV2
) -> None:
    if (
        child.parent_revision != parent.revision
        or child.parent_transition_id != parent.transition_id
        or child.parent_snapshot_root != parent.snapshot_root
        or child.parent_history_root != parent.history_root
        or child.parent_history_count != parent.history_count
        or child.history_count != parent.history_count + 1
    ):
        raise ValueError("commit decision successor parent lineage is mismatched")
    fixed_child = (
        child.domain_root,
        child.scope_ref,
        child.protocol_ref,
        child.run_ref,
        child.target_ref,
        child.profile,
        child.assurance,
        child.manifest_root,
        child.commit_policy_root,
        child.stream_ref,
        child.initialized_at_step,
        child.evidence_deadline_step,
        child.finality_deadline_step,
    )
    fixed_parent = (
        parent.domain_root,
        parent.scope_ref,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
        parent.profile,
        parent.assurance,
        parent.manifest_root,
        parent.commit_policy_root,
        parent.stream_ref,
        parent.initialized_at_step,
        parent.evidence_deadline_step,
        parent.finality_deadline_step,
    )
    if fixed_child != fixed_parent or child.current_step < parent.current_step:
        raise ValueError("commit decision successor fixed context is mismatched")
    if parent.outcome is not None:
        raise ValueError("commit decision terminal state has a successor")


def _head_from_view_v2(
    view: GovernanceCommitViewV2, domain: AuthorityDomainV2
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("commit decision view has no committed transition")
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
