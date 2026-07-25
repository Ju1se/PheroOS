"""Canonical committed-view and transitive history verification for Support v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._support_v2.support_committed_state import (
    _decode_state_records,
)
from pheroos.governance._support_v2.support_projection import (
    _validate_transition_delta,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
)
from pheroos.governance._support_v2.support_trace_events import _support_events
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
) -> tuple[
    SupportAdvanceRequestV2,
    dict[str, Any],
    str,
    str,
    GovernanceReadPreconditionV2 | None,
]:
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
    (
        request,
        binding,
        source_context_root,
        source_verification_root,
        membership_precondition,
    ) = _decode_state_records(
        view.committed_transition.batch.transition.state_records,
        domain,
    )
    receipt = view.committed_transition.receipt
    if (
        receipt.revision != request.snapshot.revision
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
    ):
        raise ValueError("support committed receipt is mismatched")
    _validate_committed_read_set(
        view,
        request,
        binding,
        membership_precondition=membership_precondition,
    )
    expected_events = _support_events(
        request,
        binding,
        source_context_root=source_context_root,
        source_verification_root=source_verification_root,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    if view.committed_transition.batch.trace_batch.events != expected_events:
        raise ValueError("support committed trace lineage is mismatched")
    return (
        request,
        binding,
        source_context_root,
        source_verification_root,
        membership_precondition,
    )


def _validate_committed_read_set(
    view: GovernanceCommitViewV2,
    request: SupportAdvanceRequestV2,
    binding: Mapping[str, Any],
    *,
    membership_precondition: GovernanceReadPreconditionV2 | None,
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    read_entries = view.committed_transition.batch.read_set.entries
    entries = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in read_entries
    }
    if len(entries) != len(read_entries):
        raise ValueError("support read set contains duplicate streams")
    grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        cast(str, binding["grant_ref"]),
    )
    expected = {
        request.stream_ref: (request.snapshot.parent_revision, receipt.parent_root),
        grant_stream: (
            binding["grant_expected_revision"],
            binding["grant_expected_root"],
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    }
    if membership_precondition is not None:
        expected[membership_precondition.stream_ref] = (
            membership_precondition.expected_revision,
            membership_precondition.expected_root,
        )
    expected_count = 3 + int(membership_precondition is not None)
    if len(expected) != expected_count or entries != expected:
        raise ValueError("support authority read set is mismatched")


def _validate_history(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: SupportAdvanceRequestV2,
    view: GovernanceCommitViewV2,
) -> None:
    child = request
    child_view = view
    visited = {child.transition_id}
    while True:
        assert child_view.committed_transition is not None
        child_receipt = child_view.committed_transition.receipt
        if child.mutation_kind is SupportMutationKindV2.INITIALIZE:
            genesis = GovernanceHeadV2.genesis(domain, child.stream_ref)
            if (
                child.snapshot.revision != 1
                or child_receipt.parent_root != genesis.head_root
            ):
                raise ValueError("support genesis Store lineage is invalid")
            return
        parent_transition_id = child.snapshot.parent_transition_id
        if parent_transition_id in visited:
            raise ValueError("support history contains a cycle")
        visited.add(parent_transition_id)
        try:
            parent_view = _canonical_commit_view_v2(
                reader.load_commit_view_v2(
                    child.scope_ref,
                    child.stream_ref,
                    parent_transition_id,
                ),
                invalid_path="/snapshot/parent_transition_id",
            )
            parent, _, _, _, _ = _decode_committed_view(parent_view, domain)
        except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
            raise ValueError("support historical parent is unavailable") from exc
        assert parent_view.committed_transition is not None
        parent_receipt = parent_view.committed_transition.receipt
        if child_receipt.parent_root != parent_receipt.head_root:
            raise ValueError("support historical Store heads are reordered")
        _validate_transition_delta(child, parent.snapshot)
        child = parent
        child_view = parent_view


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected_request: SupportAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[SupportAdvanceRequestV2, GovernanceCommitViewV2]:
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
        request, _, _, _, _ = _decode_committed_view(view, domain)
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


__all__: tuple[str, ...] = ()
