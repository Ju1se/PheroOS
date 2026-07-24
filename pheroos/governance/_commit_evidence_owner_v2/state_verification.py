"""Committed-view, read-set, trace, and history verification for Evidence v2."""

from __future__ import annotations

from collections.abc import Mapping

from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
)
from pheroos.governance._commit_evidence_owner_v2.state_records import (
    _decode_state_records,
    _integer_field,
    _text_field,
)
from pheroos.governance._commit_evidence_owner_v2.trace_events import (
    _commit_evidence_events,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


def _decode_committed_view(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> tuple[CommitEvidenceAdvanceRequestV2, dict[str, object], str]:
    view = _canonical_commit_view_v2(view)
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
        or view.position_observation is None
        or view.committed_transition.batch.transition is None
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        )
    request, binding, source_root = _decode_state_records(
        view.committed_transition.batch.transition.state_records,
        domain,
    )
    receipt = view.committed_transition.receipt
    if (
        receipt.revision != request.snapshot.revision
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
    ):
        raise ValueError("commit evidence committed receipt is mismatched")
    _validate_committed_read_set(view, request, binding)
    events = _commit_evidence_events(
        request,
        binding,
        source_context_root=source_root,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    if view.committed_transition.batch.trace_batch.events != events:
        raise ValueError("commit evidence committed trace lineage is mismatched")
    return request, binding, source_root


def _validate_committed_read_set(
    view: GovernanceCommitViewV2,
    request: CommitEvidenceAdvanceRequestV2,
    binding: Mapping[str, object],
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    read_entries = view.committed_transition.batch.read_set.entries
    entries = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in read_entries
    }
    if len(entries) != len(read_entries):
        raise ValueError("commit evidence read set contains duplicate streams")
    snapshot = request.snapshot
    grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        _text_field(binding, "grant_ref"),
    )
    expected = {
        request.stream_ref: (snapshot.parent_revision, receipt.parent_root),
        grant_stream: (
            _integer_field(binding, "grant_expected_revision"),
            _text_field(binding, "grant_expected_root"),
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            _integer_field(binding, "lifecycle_expected_revision"),
            _text_field(binding, "lifecycle_expected_root"),
        ),
        snapshot.membership_stream_ref: (
            snapshot.membership_revision,
            snapshot.membership_head_root,
        ),
        snapshot.verification_stream_ref: (
            snapshot.verification_revision,
            snapshot.verification_head_root,
        ),
        snapshot.replay_stream_ref: (
            snapshot.replay_revision,
            snapshot.replay_head_root,
        ),
    }
    if len(expected) != 6 or entries != expected:
        raise ValueError("commit evidence authority read set is mismatched")


def _validate_transition_delta(
    child: CommitEvidenceSnapshotV2,
    parent: CommitEvidenceSnapshotV2,
) -> None:
    for field in (
        "domain_root",
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
    ):
        if getattr(child, field) != getattr(parent, field):
            raise ValueError("commit evidence historical lineage is cross-bound")
    if (
        child.revision != parent.revision + 1
        or child.parent_revision != parent.revision
        or child.parent_epoch != parent.epoch
        or child.parent_transition_id != parent.transition_id
        or child.parent_snapshot_root != parent.snapshot_root
        or child.parent_history_root != parent.history_root
        or child.parent_history_count != parent.history_count
        or child.initialized_at_step != parent.initialized_at_step
        or child.current_step <= parent.current_step
        or child.epoch < parent.epoch
    ):
        raise ValueError("commit evidence historical continuity is invalid")
    if child.epoch == parent.epoch:
        stable = (
            "profile",
            "assurance",
            "authority_policy_root",
            "manifest_root",
            "commit_policy_root",
        )
        if any(getattr(child, field) != getattr(parent, field) for field in stable):
            raise ValueError("commit evidence policy rotated without a new epoch")
        if child.evidence_policy.to_dict() != parent.evidence_policy.to_dict():
            raise ValueError("commit evidence policy snapshot changed in one epoch")
    _validate_record_delta(child, parent)


def _validate_record_delta(
    child: CommitEvidenceSnapshotV2,
    parent: CommitEvidenceSnapshotV2,
) -> None:
    parent_by_ref = {item.record_ref: item for item in parent.records}
    child_by_ref = {item.record_ref: item for item in child.records}
    if not set(parent_by_ref).issubset(child_by_ref):
        raise ValueError("commit evidence complete replacement dropped history")
    added = tuple(
        item for ref, item in child_by_ref.items() if ref not in parent_by_ref
    )
    changed: list[tuple[QualifiedCommitEvidenceV2, QualifiedCommitEvidenceV2]] = []
    for ref, before in parent_by_ref.items():
        after = child_by_ref[ref]
        if before.record_root != after.record_root:
            changed.append((before, after))
    for before, after in changed:
        _validate_revocation_replacement(before, after, child.current_step)
    expected_mutations = {item.record_root for item in added}
    expected_mutations.update(after.record_root for _, after in changed)
    expected_removed = {before.record_root for before, _ in changed}
    expected_revocations = {after.revocation_root for _, after in changed}
    if (
        set(child.mutation_record_roots) != expected_mutations
        or set(child.removed_record_roots) != expected_removed
        or set(child.revocation_roots) != expected_revocations
    ):
        raise ValueError("commit evidence mutation delta is not exact")


def _validate_revocation_replacement(
    before: QualifiedCommitEvidenceV2,
    after: QualifiedCommitEvidenceV2,
    current_step: int,
) -> None:
    before_body = before.to_dict()
    after_body = after.to_dict()
    mutable = {
        "status",
        "revoked_at_step",
        "revocation_root",
        "revocation_provenance_root",
        "revocation_trace_roots",
        "record_root",
    }
    for field in mutable:
        before_body.pop(field)
        after_body.pop(field)
    if (
        before.status is not CommitEvidenceStatusV2.ACTIVE
        or after.status is not CommitEvidenceStatusV2.REVOKED
        or after.revoked_at_step != current_step
        or before_body != after_body
    ):
        raise ValueError("commit evidence record mutation is not a revocation")


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected_request: CommitEvidenceAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[CommitEvidenceAdvanceRequestV2, GovernanceCommitViewV2]:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                expected_request.scope_ref,
                expected_request.stream_ref,
                expected_request.transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        code = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
            if view.failure is None
            else view.failure.code
        )
        path = "/transition_id" if view.failure is None else view.failure.path
        raise GovernanceAuthorityBindingErrorV2(code, path)
    try:
        request, _, _ = _decode_committed_view(view, domain)
        _validate_history(reader, domain, request, view)
    except GovernanceAuthorityBindingErrorV2:
        raise
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if request.to_dict() != expected_request.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return request, view


def _validate_history(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: CommitEvidenceAdvanceRequestV2,
    view: GovernanceCommitViewV2,
) -> None:
    child, child_view = request, view
    visited = {child.transition_id}
    while child.snapshot.parent_revision:
        parent_id = child.snapshot.parent_transition_id
        if parent_id in visited:
            raise ValueError("commit evidence history contains a cycle")
        visited.add(parent_id)
        try:
            parent_view = _canonical_commit_view_v2(
                reader.load_commit_view_v2(
                    child.scope_ref,
                    child.stream_ref,
                    parent_id,
                ),
                invalid_path="/snapshot/parent_transition_id",
            )
            parent, _, _ = _decode_committed_view(parent_view, domain)
        except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
            raise ValueError("commit evidence historical parent unavailable") from exc
        assert child_view.committed_transition is not None
        assert parent_view.committed_transition is not None
        child_receipt = child_view.committed_transition.receipt
        parent_receipt = parent_view.committed_transition.receipt
        if child_receipt.parent_root != parent_receipt.head_root:
            raise ValueError("commit evidence Store history is reordered")
        _validate_transition_delta(child.snapshot, parent.snapshot)
        child, child_view = parent, parent_view
    assert child_view.committed_transition is not None
    genesis = GovernanceHeadV2.genesis(domain, child.stream_ref)
    if (
        child.snapshot.revision != 1
        or child.snapshot.parent_transition_id
        != COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2
        or child.snapshot.parent_snapshot_root
        != COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2
        or child_view.committed_transition.receipt.parent_root != genesis.head_root
    ):
        raise ValueError("commit evidence genesis Store lineage is invalid")


__all__: tuple[str, ...] = ()
