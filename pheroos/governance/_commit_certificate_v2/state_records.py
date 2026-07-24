"""Committed record, receipt, read-set, and Trace verification."""

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
from pheroos.governance._commit_certificate_v2.events import (
    _commit_certificate_event_v2,
)
from pheroos.governance._commit_certificate_v2.request import (
    CommitCertificateRequestV2,
)
from pheroos.governance._commit_certificate_v2.decision_leaves import (
    _authority_leaves,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2,
    COMMIT_CERTIFICATE_STATE_SCHEMA_V2,
    CommitCertificateSnapshotV2,
)
from pheroos.governance._commit_decision_v2.state_records import (
    _decode_committed_decision_view_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionMutationKindV2,
)
from pheroos.governance._commit_decision_v2.snapshot import (
    CommitDecisionSnapshotV2,
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
        "certificate_body_root",
        "certificate_envelope_root",
        "session_binding",
    }
)
_SESSION_FIELDS = frozenset(_SessionBindingV2.__annotations__)


def _certificate_state_records_v2(
    request: CommitCertificateRequestV2,
    snapshot: CommitCertificateSnapshotV2,
    session_binding: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": COMMIT_CERTIFICATE_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": snapshot.snapshot_root,
        "snapshot": snapshot.to_dict(),
        "source_context_root": snapshot.source_context_root,
        "certificate_body_root": snapshot.certificate.body.body_root,
        "certificate_envelope_root": snapshot.certificate.envelope_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_committed_certificate_view_v2(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    *,
    reader: GovernanceStateReaderV2 | None,
) -> tuple[CommitCertificateRequestV2, CommitCertificateSnapshotV2, _SessionBindingV2]:
    canonical = _canonical_commit_view_v2(view)
    if (
        canonical.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or canonical.committed_transition is None
        or canonical.position_observation is None
    ):
        raise ValueError("commit certificate view is not committed")
    transition = canonical.committed_transition.batch.transition
    if transition is None:
        raise ValueError("commit certificate committed batch has no transition")
    request, snapshot, binding = _decode_state_records_v2(
        transition.state_records, domain
    )
    receipt = canonical.committed_transition.receipt
    if (
        receipt.stream_ref != snapshot.stream_ref
        or receipt.transition_id != snapshot.transition_id
        or receipt.revision != snapshot.revision
    ):
        raise ValueError("commit certificate receipt is mismatched")
    _validate_read_set_v2(canonical, snapshot, binding)
    expected_event = _commit_certificate_event_v2(
        request,
        snapshot,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=canonical.committed_transition.batch.read_set.root(),
    )
    if canonical.committed_transition.batch.trace_batch.events != (expected_event,):
        raise ValueError("commit certificate Trace lineage is mismatched")
    if reader is not None:
        _verify_historical_dependencies(snapshot, domain, reader)
        _verify_parent_history(snapshot, domain, reader)
    return request, snapshot, binding


def _decode_state_records_v2(
    value: object,
    domain: AuthorityDomainV2,
) -> tuple[CommitCertificateRequestV2, CommitCertificateSnapshotV2, _SessionBindingV2]:
    projected = _portable_projection(value)
    if type(projected) is not dict:
        raise TypeError("commit certificate committed state must be an exact object")
    state = cast(dict[str, object], projected)
    if set(state) != _STATE_FIELDS:
        raise ValueError("commit certificate committed state fields are invalid")
    if (
        state["schema"] != COMMIT_CERTIFICATE_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("commit certificate committed state domain is mismatched")
    request = CommitCertificateRequestV2.from_dict(state["request"])
    snapshot = CommitCertificateSnapshotV2.from_dict(state["snapshot"])
    if (
        state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != snapshot.snapshot_root
        or state["source_context_root"] != snapshot.source_context_root
        or state["certificate_body_root"] != snapshot.certificate.body.body_root
        or state["certificate_envelope_root"] != snapshot.certificate.envelope_root
        or snapshot.stream_ref != request.stream_ref
        or snapshot.transition_id != request.transition_id
        or snapshot.domain_root != domain.domain_root
        or snapshot.scope_ref != domain.scope_ref
    ):
        raise ValueError("commit certificate committed state payload is mismatched")
    binding = _validate_session_binding_v2(state["session_binding"], request)
    return request, snapshot, binding


def _validate_session_binding_v2(
    value: object,
    request: CommitCertificateRequestV2,
) -> _SessionBindingV2:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_FIELDS:
        raise ValueError("commit certificate session binding fields are invalid")
    binding = cast(_SessionBindingV2, projected)
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
        raise ValueError("commit certificate stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("commit certificate stored grant binding is invalid")
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
    snapshot: CommitCertificateSnapshotV2,
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
        raise ValueError("commit certificate read set contains duplicate streams")
    body = snapshot.certificate.body
    expected = {
        snapshot.stream_ref: (snapshot.parent_revision, receipt.parent_root),
        body.decision_stream_ref: (body.decision_revision, body.decision_head_root),
        **{
            item.stream_ref: (item.revision, item.head_root)
            for item in body.authority_leaves
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
        raise ValueError("commit certificate committed read set is not closed")


def _verify_historical_dependencies(
    snapshot: CommitCertificateSnapshotV2,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> None:
    body = snapshot.certificate.body
    decision_view = _load_bound_view(
        reader,
        snapshot,
        stream_ref=body.decision_stream_ref,
        transition_id=body.decision_transition_id,
        receipt_root=body.decision_receipt_root,
    )
    _, decision_snapshot, _ = _decode_committed_decision_view_v2(
        decision_view,
        domain,
        reader=reader,
    )
    assert decision_view.committed_transition is not None
    decision_receipt = decision_view.committed_transition.receipt
    decision_inclusion = decision_view.committed_transition.inclusion_proof
    if (
        decision_snapshot.revision != body.decision_revision
        or decision_snapshot.snapshot_root != body.decision_snapshot_root
        or decision_receipt.head_root != body.decision_head_root
        or decision_inclusion.inclusion_root != body.decision_inclusion_root
    ):
        raise ValueError("commit certificate Decision dependency is mismatched")
    sealed_snapshot, sealed_view = _verify_seal_inclusion(snapshot, domain, reader)
    _verify_decision_body_binding(
        snapshot,
        decision_snapshot=decision_snapshot,
        decision_view=decision_view,
        sealed_snapshot=sealed_snapshot,
        sealed_view=sealed_view,
    )
    for item in body.authority_leaves:
        view = _load_bound_view(
            reader,
            snapshot,
            stream_ref=item.stream_ref,
            transition_id=item.transition_id,
            receipt_root=item.receipt_root,
        )
        assert view.committed_transition is not None
        receipt = view.committed_transition.receipt
        if receipt.revision != item.revision or receipt.head_root != item.head_root:
            raise ValueError("commit certificate historical dependency is mismatched")


def _verify_seal_inclusion(
    snapshot: CommitCertificateSnapshotV2,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> tuple[CommitDecisionSnapshotV2, GovernanceCommitViewV2]:
    body = snapshot.certificate.body
    view = _load_bound_view(
        reader,
        snapshot,
        stream_ref=body.decision_stream_ref,
        transition_id=body.seal_transition_id,
        receipt_root=body.seal_receipt_root,
    )
    _, sealed, _ = _decode_committed_decision_view_v2(view, domain, reader=reader)
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    inclusion = view.committed_transition.inclusion_proof
    if (
        sealed.mutation_kind is not CommitDecisionMutationKindV2.SEALED
        or sealed.stream_ref != body.decision_stream_ref
        or sealed.revision != body.seal_revision
        or sealed.snapshot_root != body.seal_snapshot_root
        or sealed.seal is None
        or sealed.seal.seal_root != body.seal_root
        or sealed.seal.frozen_dependency_root != body.frozen_dependency_root
        or receipt.head_root != body.seal_head_root
        or inclusion.inclusion_root != body.seal_inclusion_root
    ):
        raise ValueError("commit certificate seal inclusion is mismatched")
    return sealed, view


def _verify_decision_body_binding(
    certificate: CommitCertificateSnapshotV2,
    *,
    decision_snapshot: CommitDecisionSnapshotV2,
    decision_view: GovernanceCommitViewV2,
    sealed_snapshot: CommitDecisionSnapshotV2,
    sealed_view: GovernanceCommitViewV2,
) -> None:
    body = certificate.certificate.body
    seal = decision_snapshot.seal
    assessment = decision_snapshot.assessment
    if seal is None or assessment is None or sealed_snapshot.seal is None:
        raise ValueError("commit certificate Decision authority is incomplete")
    metrics = tuple(
        item
        for item in assessment.candidate_metrics
        if item.candidate_ref == seal.candidate_ref
        and item.claim_root == seal.claim_root
    )
    if len(metrics) != 1 or not metrics[0].ready_for_stability:
        raise ValueError("commit certificate Decision candidate is not evidence-ready")
    assert decision_view.committed_transition is not None
    assert sealed_view.committed_transition is not None
    decision_receipt = decision_view.committed_transition.receipt
    decision_inclusion = decision_view.committed_transition.inclusion_proof
    sealed_receipt = sealed_view.committed_transition.receipt
    sealed_inclusion = sealed_view.committed_transition.inclusion_proof
    observed = (
        body.domain_root,
        body.scope_ref,
        body.protocol_ref,
        body.run_ref,
        body.target_ref,
        body.profile,
        body.assurance,
        body.epoch,
        body.manifest_root,
        body.commit_policy_root,
        body.decision_stream_ref,
        body.decision_revision,
        body.decision_transition_id,
        body.decision_snapshot_root,
        body.decision_head_root,
        body.decision_receipt_root,
        body.decision_inclusion_root,
        body.seal_transition_id,
        body.seal_revision,
        body.seal_snapshot_root,
        body.seal_receipt_root,
        body.seal_head_root,
        body.seal_inclusion_root,
        body.seal_root,
        body.window_root,
        body.frozen_dependency_root,
        body.assessment_root,
        body.candidate_ref,
        body.claim_root,
        body.evidence_root,
        body.challenge_root,
        body.lease_root,
        body.output_contract_root,
        body.output_payload_root,
        tuple(item.to_dict() for item in body.authority_leaves),
    )
    expected = (
        decision_snapshot.domain_root,
        decision_snapshot.scope_ref,
        decision_snapshot.protocol_ref,
        decision_snapshot.run_ref,
        decision_snapshot.target_ref,
        decision_snapshot.profile,
        decision_snapshot.assurance,
        decision_snapshot.epoch,
        decision_snapshot.manifest_root,
        decision_snapshot.commit_policy_root,
        decision_snapshot.stream_ref,
        decision_snapshot.revision,
        decision_snapshot.transition_id,
        decision_snapshot.snapshot_root,
        decision_receipt.head_root,
        decision_receipt.receipt_root,
        decision_inclusion.inclusion_root,
        sealed_snapshot.transition_id,
        sealed_snapshot.revision,
        sealed_snapshot.snapshot_root,
        sealed_receipt.receipt_root,
        sealed_receipt.head_root,
        sealed_inclusion.inclusion_root,
        seal.seal_root,
        seal.window_root,
        seal.frozen_dependency_root,
        assessment.assessment_root,
        seal.candidate_ref,
        seal.claim_root,
        metrics[0].evidence_root,
        metrics[0].challenge_root,
        metrics[0].lease_root,
        seal.output_contract_root,
        seal.output_payload_root,
        tuple(
            item.to_dict() for item in _authority_leaves(decision_snapshot.dependencies)
        ),
    )
    if observed != expected or sealed_snapshot.seal.seal_root != seal.seal_root:
        raise ValueError("commit certificate body is not bound to Decision authority")


def _load_bound_view(
    reader: GovernanceStateReaderV2,
    snapshot: CommitCertificateSnapshotV2,
    *,
    stream_ref: str,
    transition_id: str,
    receipt_root: str,
) -> GovernanceCommitViewV2:
    view = _canonical_commit_view_v2(
        reader.load_commit_view_v2(
            snapshot.scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=receipt_root,
        )
    )
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
    ):
        raise ValueError("commit certificate historical dependency is unavailable")
    return view


def _verify_parent_history(
    snapshot: CommitCertificateSnapshotV2,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> None:
    if snapshot.parent_revision == 0:
        if (
            snapshot.parent_transition_id != COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
            or snapshot.parent_snapshot_root
            != COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
        ):
            raise ValueError("commit certificate genesis parent is invalid")
        return
    parent_view = _canonical_commit_view_v2(
        reader.load_commit_view_v2(
            snapshot.scope_ref,
            snapshot.stream_ref,
            snapshot.parent_transition_id,
        )
    )
    _, parent, _ = _decode_committed_certificate_view_v2(
        parent_view, domain, reader=None
    )
    if (
        parent.revision != snapshot.parent_revision
        or parent.snapshot_root != snapshot.parent_snapshot_root
        or parent.history_root != snapshot.parent_history_root
        or parent.history_count != snapshot.parent_history_count
    ):
        raise ValueError("commit certificate historical parent is mismatched")


def _head_from_view_v2(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("commit certificate view has no transition")
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
