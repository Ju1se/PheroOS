"""Committed-state, transitive history, and Trace checks for Membership v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
    _portable_projection,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MEMBERSHIP_STATE_SCHEMA_V2,
    MembershipCommitRequestV2,
    MembershipSnapshotV2,
)
from pheroos.governance._support_v2.membership_source import (
    _expected_source_context_root_v2,
    _project_verifications,
)
from pheroos.governance._support_v2.principal_verification_state import (
    _decode_committed_view_shallow as _decode_verification_view,
    _validate_history as _validate_verification_history,
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
        "membership_root",
        "verification_read_precondition",
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


def _continuity_failure(
    request: MembershipCommitRequestV2,
    parent: MembershipSnapshotV2 | None,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    snapshot = request.snapshot
    if parent is None:
        if snapshot.parent_revision != 0 or snapshot.parent_epoch is not None:
            return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
        return None
    immutable = (
        "domain_root",
        "scope_ref",
        "profile",
        "assurance",
        "authority_policy_root",
        "manifest_root",
        "commit_policy_root",
        "membership_policy_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
    )
    if any(getattr(snapshot, field) != getattr(parent, field) for field in immutable):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
    if (
        snapshot.revision != parent.revision + 1
        or snapshot.parent_revision != parent.revision
        or snapshot.parent_epoch != parent.epoch
        or snapshot.parent_transition_id != parent.transition_id
        or snapshot.parent_snapshot_root != parent.snapshot_root
        or snapshot.epoch <= parent.epoch
        or snapshot.issued_at_step <= parent.issued_at_step
    ):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
    return None


def _state_records(
    request: MembershipCommitRequestV2,
    binding: Mapping[str, Any],
) -> dict[str, object]:
    snapshot = request.snapshot
    verification = GovernanceReadPreconditionV2(
        stream_ref=snapshot.verification_stream_ref,
        expected_revision=snapshot.verification_revision,
        expected_root=snapshot.verification_head_root,
    )
    return {
        "schema": MEMBERSHIP_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": snapshot.snapshot_root,
        "snapshot": snapshot.to_dict(),
        "source_context_root": _expected_source_context_root_v2(request),
        "membership_root": snapshot.membership_root,
        "verification_read_precondition": verification.to_dict(),
        "session_binding": _portable_projection(binding),
    }


def _decode_state_records(
    value: object, domain: AuthorityDomainV2
) -> tuple[MembershipCommitRequestV2, dict[str, Any]]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _STATE_FIELDS:
        raise ValueError("membership committed state fields are invalid")
    state = cast(dict[str, Any], projected)
    if (
        state["schema"] != MEMBERSHIP_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("membership committed state domain is mismatched")
    request = MembershipCommitRequestV2.from_dict(state["request"])
    snapshot = MembershipSnapshotV2.from_dict(state["snapshot"])
    verification = GovernanceReadPreconditionV2.from_dict(
        state["verification_read_precondition"]
    )
    expected_verification = (
        snapshot.verification_stream_ref,
        snapshot.verification_revision,
        snapshot.verification_head_root,
    )
    if (
        snapshot.to_dict() != request.snapshot.to_dict()
        or state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != snapshot.snapshot_root
        or state["membership_root"] != snapshot.membership_root
        or state["source_context_root"] != _expected_source_context_root_v2(request)
        or (
            verification.stream_ref,
            verification.expected_revision,
            verification.expected_root,
        )
        != expected_verification
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("membership committed state is cross-bound")
    return request, _validate_session_binding(state["session_binding"], request)


def _validate_session_binding(
    value: object, request: MembershipCommitRequestV2
) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_FIELDS:
        raise ValueError("membership session binding fields are invalid")
    binding = cast(dict[str, Any], projected)
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
        request.request_ref,
        request.request_root,
        GovernanceIssuerOperationV2.EVALUATE_QUORUM.value,
        request.observed_epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("membership session binding is mismatched")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref, cast(str, binding["grant_ref"])
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


def _decode_committed_view_shallow(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> tuple[MembershipCommitRequestV2, dict[str, Any]]:
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
    request, binding = _decode_state_records(
        view.committed_transition.batch.transition.state_records, domain
    )
    receipt = view.committed_transition.receipt
    if (
        receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
        or receipt.revision != request.snapshot.revision
    ):
        raise ValueError("membership receipt is mismatched")
    _validate_read_set(view, request, binding)
    event = _membership_event(
        request,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    if view.committed_transition.batch.trace_batch.events != (event,):
        raise ValueError("membership trace lineage is mismatched")
    return request, binding


def _validate_read_set(
    view: GovernanceCommitViewV2,
    request: MembershipCommitRequestV2,
    binding: Mapping[str, Any],
) -> None:
    assert view.committed_transition is not None
    entries = view.committed_transition.batch.read_set.entries
    projected = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in entries
    }
    if len(projected) != len(entries):
        raise ValueError("membership read set contains duplicate streams")
    snapshot = request.snapshot
    expected = {
        request.stream_ref: (
            snapshot.parent_revision,
            view.committed_transition.receipt.parent_root,
        ),
        snapshot.verification_stream_ref: (
            snapshot.verification_revision,
            snapshot.verification_head_root,
        ),
        governance_issuer_grant_stream_ref_v2(
            request.scope_ref, cast(str, binding["grant_ref"])
        ): (binding["grant_expected_revision"], binding["grant_expected_root"]),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    }
    if projected != expected:
        raise ValueError("membership authority read set is mismatched")


def _validate_verification_inclusion(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    snapshot: MembershipSnapshotV2,
    *,
    require_current: bool,
) -> None:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                snapshot.scope_ref,
                snapshot.verification_stream_ref,
                snapshot.verification_transition_id,
            ),
            invalid_path="/snapshot/verification_transition_id",
        )
        verification, _ = _decode_verification_view(view, domain)
        _validate_verification_history(reader, domain, verification)
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise ValueError("membership verification inclusion is unavailable") from exc
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    projected = verification.snapshot
    expected_context = (
        snapshot.domain_root,
        snapshot.scope_ref,
        snapshot.profile,
        snapshot.assurance,
        snapshot.authority_policy_root,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.verification_policy_root,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
        snapshot.epoch,
        snapshot.verification_request_ref,
        snapshot.verification_revision,
        snapshot.verification_snapshot_root,
        snapshot.verification_set_root,
        snapshot.verification_head_root,
        snapshot.verification_current_step,
        snapshot.verification_expires_at_step,
        snapshot.verification_record_count,
    )
    observed_context = (
        projected.domain_root,
        projected.scope_ref,
        projected.profile,
        projected.assurance,
        projected.authority_policy_root,
        projected.manifest_root,
        projected.commit_policy_root,
        projected.verification_policy_root,
        projected.protocol_ref,
        projected.run_ref,
        projected.target_ref,
        projected.epoch,
        projected.advance_ref,
        receipt.revision,
        projected.snapshot_root,
        projected.verification_set_root,
        receipt.head_root,
        projected.current_step,
        projected.expires_at_step,
        projected.record_count,
    )
    expected_clusters = _project_verifications(projected)
    if (
        observed_context != expected_context
        or tuple(snapshot.clusters) != expected_clusters
        or snapshot.cluster_count != len(expected_clusters)
        or snapshot.principal_count != projected.record_count
        or snapshot.issued_at_step < projected.current_step
        or snapshot.expires_at_step > projected.expires_at_step
    ):
        raise ValueError("membership verification inclusion is cross-bound")
    if require_current and (
        view.position_observation is None
        or view.position_observation.position is not GovernanceCommitPositionV2.CURRENT
    ):
        raise ValueError("membership verification set is not current")


def _validate_history(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: MembershipCommitRequestV2,
) -> None:
    child = request
    visited: set[str] = set()
    while True:
        _validate_verification_inclusion(
            reader, domain, child.snapshot, require_current=False
        )
        if child.snapshot.parent_revision == 0:
            if _continuity_failure(child, None) is not None:
                raise ValueError("membership genesis continuity is invalid")
            return
        transition_id = child.snapshot.parent_transition_id
        if transition_id in visited:
            raise ValueError("membership history contains a cycle")
        visited.add(transition_id)
        try:
            view = _canonical_commit_view_v2(
                reader.load_commit_view_v2(
                    child.scope_ref, child.stream_ref, transition_id
                ),
                invalid_path="/snapshot/parent_transition_id",
            )
            parent, _ = _decode_committed_view_shallow(view, domain)
        except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
            raise ValueError("membership historical parent unavailable") from exc
        if _continuity_failure(child, parent.snapshot) is not None:
            raise ValueError("membership historical continuity is invalid")
        child = parent


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected: MembershipCommitRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[MembershipCommitRequestV2, GovernanceCommitViewV2]:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                expected.scope_ref,
                expected.stream_ref,
                expected.transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "/transition_id",
        )
    try:
        request, _ = _decode_committed_view_shallow(view, domain)
        _validate_history(reader, domain, request)
    except GovernanceAuthorityBindingErrorV2:
        raise
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if request.to_dict() != expected.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/request_root"
        )
    return request, view


def _membership_event(
    request: MembershipCommitRequestV2,
    binding: Mapping[str, Any],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> TraceEvent:
    snapshot = request.snapshot
    lineage = {
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "run_ref": request.run_ref,
        "request_ref": request.request_ref,
        "request_root": request.request_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": GovernanceIssuerOperationV2.EVALUATE_QUORUM.value,
        "observed_epoch": request.observed_epoch,
        "session_binding": _portable_projection(binding),
        "target_ref": request.target_ref,
        "protocol_ref": snapshot.protocol_ref,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "authority_policy_root": snapshot.authority_policy_root,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "membership_policy_root": snapshot.membership_policy_root,
        "epoch": snapshot.epoch,
        "revision": snapshot.revision,
        "parent_revision": snapshot.parent_revision,
        "parent_epoch": snapshot.parent_epoch,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "membership_root": snapshot.membership_root,
        "cluster_count": snapshot.cluster_count,
        "principal_count": snapshot.principal_count,
        "issued_at_step": snapshot.issued_at_step,
        "expires_at_step": snapshot.expires_at_step,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "grant_issuer_ref": snapshot.mutation_issuer_ref,
        "verification_stream_ref": snapshot.verification_stream_ref,
        "verification_transition_id": snapshot.verification_transition_id,
        "verification_policy_root": snapshot.verification_policy_root,
        "verification_request_ref": snapshot.verification_request_ref,
        "verification_revision": snapshot.verification_revision,
        "verification_head_root": snapshot.verification_head_root,
        "verification_snapshot_root": snapshot.verification_snapshot_root,
        "verification_set_root": snapshot.verification_set_root,
        "verification_current_step": snapshot.verification_current_step,
        "verification_expires_at_step": snapshot.verification_expires_at_step,
        "verification_record_count": snapshot.verification_record_count,
        "source_trace_roots": list(snapshot.source_trace_roots),
        "source_context_root": _expected_source_context_root_v2(request),
        "read_set_root": read_set_root,
    }
    return TraceEvent(
        event_type="membership_epoch_committed",
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="commit one Sybil-collapsed membership epoch",
        lineage=lineage,
    )


__all__: tuple[str, ...] = ()
