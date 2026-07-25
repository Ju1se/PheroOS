"""Committed-state and lineage verification for PrincipalVerificationSet v2."""

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
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2,
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
)
from pheroos.governance._support_v2.principal_verification_source import (
    _expected_source_context_root_v2,
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
        "verification_set_root",
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
    request: PrincipalVerificationSetAdvanceRequestV2,
    parent: PrincipalVerificationSetSnapshotV2 | None,
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
        "verification_policy_root",
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
        or snapshot.current_step <= parent.current_step
    ):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
    return None


def _state_records(
    request: PrincipalVerificationSetAdvanceRequestV2,
    binding: Mapping[str, Any],
) -> dict[str, object]:
    snapshot = request.snapshot
    return {
        "schema": PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": snapshot.snapshot_root,
        "snapshot": snapshot.to_dict(),
        "source_context_root": _expected_source_context_root_v2(request),
        "verification_set_root": snapshot.verification_set_root,
        "session_binding": _portable_projection(binding),
    }


def _decode_state_records(
    value: object, domain: AuthorityDomainV2
) -> tuple[PrincipalVerificationSetAdvanceRequestV2, dict[str, Any]]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _STATE_FIELDS:
        raise ValueError("principal verification committed state fields are invalid")
    state = cast(dict[str, Any], projected)
    if (
        state["schema"] != PRINCIPAL_VERIFICATION_SET_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("principal verification committed domain is mismatched")
    request = PrincipalVerificationSetAdvanceRequestV2.from_dict(state["request"])
    snapshot = PrincipalVerificationSetSnapshotV2.from_dict(state["snapshot"])
    if (
        snapshot.to_dict() != request.snapshot.to_dict()
        or state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != snapshot.snapshot_root
        or state["verification_set_root"] != snapshot.verification_set_root
        or state["source_context_root"] != _expected_source_context_root_v2(request)
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("principal verification committed state is cross-bound")
    binding = _validate_session_binding(state["session_binding"], request)
    return request, binding


def _validate_session_binding(
    value: object, request: PrincipalVerificationSetAdvanceRequestV2
) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_FIELDS:
        raise ValueError("principal verification session binding fields are invalid")
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
        request.advance_ref,
        request.request_root,
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value,
        request.observed_epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("principal verification session binding is mismatched")
    if binding["grant_root"] == "" or binding["grant_binding_ref"] == "":
        raise ValueError("principal verification grant binding is empty")
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
) -> tuple[PrincipalVerificationSetAdvanceRequestV2, dict[str, Any]]:
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
        raise ValueError("principal verification committed receipt is mismatched")
    _validate_read_set(view, request, binding)
    expected = _verification_event(
        request,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    if view.committed_transition.batch.trace_batch.events != (expected,):
        raise ValueError("principal verification trace lineage is mismatched")
    return request, binding


def _validate_read_set(
    view: GovernanceCommitViewV2,
    request: PrincipalVerificationSetAdvanceRequestV2,
    binding: Mapping[str, Any],
) -> None:
    assert view.committed_transition is not None
    entries = view.committed_transition.batch.read_set.entries
    projected = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in entries
    }
    if len(projected) != len(entries):
        raise ValueError("principal verification read set has duplicate streams")
    expected = {
        request.stream_ref: (
            request.snapshot.parent_revision,
            view.committed_transition.receipt.parent_root,
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
        raise ValueError("principal verification authority read set is mismatched")


def _validate_history(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: PrincipalVerificationSetAdvanceRequestV2,
) -> None:
    child = request
    visited: set[str] = set()
    while child.snapshot.parent_revision:
        transition_id = child.snapshot.parent_transition_id
        if transition_id in visited:
            raise ValueError("principal verification history contains a cycle")
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
            raise ValueError(
                "principal verification historical parent unavailable"
            ) from exc
        if _continuity_failure(child, parent.snapshot) is not None:
            raise ValueError("principal verification historical continuity is invalid")
        child = parent
    if _continuity_failure(child, None) is not None:
        raise ValueError("principal verification genesis continuity is invalid")


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected: PrincipalVerificationSetAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[PrincipalVerificationSetAdvanceRequestV2, GovernanceCommitViewV2]:
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


def _verification_event(
    request: PrincipalVerificationSetAdvanceRequestV2,
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
        "request_ref": request.advance_ref,
        "request_root": request.request_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value,
        "observed_epoch": request.observed_epoch,
        "session_binding": _portable_projection(binding),
        "target_ref": request.target_ref,
        "protocol_ref": snapshot.protocol_ref,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "authority_policy_root": snapshot.authority_policy_root,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "verification_policy_root": snapshot.verification_policy_root,
        "epoch": snapshot.epoch,
        "revision": snapshot.revision,
        "parent_revision": snapshot.parent_revision,
        "parent_epoch": snapshot.parent_epoch,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "verification_set_root": snapshot.verification_set_root,
        "record_count": snapshot.record_count,
        "current_step": snapshot.current_step,
        "expires_at_step": snapshot.expires_at_step,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "grant_issuer_ref": snapshot.mutation_issuer_ref,
        "verification_roots": sorted(
            (item.verification_root for item in snapshot.records),
            key=lambda value: value.encode("utf-8"),
        ),
        "source_context_root": _expected_source_context_root_v2(request),
        "read_set_root": read_set_root,
    }
    return TraceEvent(
        event_type="principal_verification_set_advanced",
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="atomically advance one durable principal verification set",
        lineage=lineage,
    )


__all__: tuple[str, ...] = ()
