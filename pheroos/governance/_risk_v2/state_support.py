"""Committed-state, read-set, and trace verification support for Risk v2."""

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
    _session_binding,
    _session_domain,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
)
from pheroos.governance._risk_policy import _RISK_ORDER
from pheroos.governance._risk_v2.contracts import (
    RISK_STATE_SCHEMA_V2,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
)
from pheroos.governance._risk_v2.source import _expected_source_context_root


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
        "assessment_root",
        "threshold_root",
        "session_binding",
    }
)
_SESSION_BINDING_FIELDS = frozenset(
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
    request: RiskStateAdvanceRequestV2,
    parent: RiskStateSnapshotV2 | None,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    snapshot = request.snapshot
    if parent is None:
        if (
            snapshot.revision != 1
            or snapshot.parent_epoch is not None
            or snapshot.assessment.previous_assessment_root
            or snapshot.assessment.window_reset_required
        ):
            return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
        return None
    immutable = (
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "risk_policy_root",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
    )
    if any(getattr(snapshot, field) != getattr(parent, field) for field in immutable):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
    assessment = snapshot.assessment
    previous = parent.assessment
    if snapshot.epoch < parent.epoch:
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot/epoch"
    epoch_changed = snapshot.epoch != parent.epoch
    if (
        snapshot.revision != parent.revision + 1
        or snapshot.parent_epoch != parent.epoch
        or snapshot.current_step < parent.current_step
        or assessment.issued_at_step <= previous.issued_at_step
        or assessment.previous_assessment_root != previous.assessment_root
        or (
            not epoch_changed and assessment.expires_at_step != previous.expires_at_step
        )
        or (
            not epoch_changed
            and _RISK_ORDER[assessment.risk_band] < _RISK_ORDER[previous.risk_band]
        )
        or assessment.window_reset_required
        is not (epoch_changed or assessment.risk_band is not previous.risk_band)
    ):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/assessment",
        )
    return None


def _state_records(
    request: RiskStateAdvanceRequestV2,
    session_binding: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = request.snapshot
    return {
        "schema": RISK_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": snapshot.snapshot_root,
        "snapshot": snapshot.to_dict(),
        "source_context_root": snapshot.source_context_root,
        "assessment_root": snapshot.assessment.assessment_root,
        "threshold_root": snapshot.threshold.threshold_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_state_records(
    value: object,
    domain: AuthorityDomainV2,
) -> tuple[RiskStateAdvanceRequestV2, dict[str, Any]]:
    projected = _portable_projection(value)
    if type(projected) is not dict:
        raise TypeError("risk committed state must be an exact object")
    state = cast(dict[str, Any], projected)
    if set(state) != _STATE_FIELDS:
        raise ValueError("risk committed state fields are invalid")
    if (
        state["schema"] != RISK_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("risk committed state domain is mismatched")
    request = RiskStateAdvanceRequestV2.from_dict(state["request"])
    snapshot = RiskStateSnapshotV2.from_dict(state["snapshot"])
    expected = _expected_source_context_root(request)
    if (
        state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != request.snapshot.snapshot_root
        or snapshot.to_dict() != request.snapshot.to_dict()
        or state["source_context_root"] != expected
        or state["assessment_root"] != snapshot.assessment.assessment_root
        or state["threshold_root"] != snapshot.threshold.threshold_root
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("risk committed state payload is mismatched")
    binding = _validate_stored_session_binding(state["session_binding"], request)
    return request, binding


def _validate_stored_session_binding(
    value: object,
    request: RiskStateAdvanceRequestV2,
) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_BINDING_FIELDS:
        raise ValueError("risk session binding fields are invalid")
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
        request.epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("risk stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("risk stored grant binding is invalid")
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


def _committed_view_matches_request(
    view: GovernanceCommitViewV2,
    request: RiskStateAdvanceRequestV2,
    session: Any,
) -> bool:
    try:
        committed, binding = _decode_committed_view(
            view,
            _session_domain(session),
            reader=cast(GovernanceStateReaderV2, session.store),
        )
    except (TypeError, ValueError, GovernanceAuthorityBindingErrorV2):
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _decode_committed_view(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    *,
    reader: GovernanceStateReaderV2 | None,
) -> tuple[RiskStateAdvanceRequestV2, dict[str, Any]]:
    view = _canonical_commit_view_v2(view)
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
        or view.position_observation is None
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        )
    transition = view.committed_transition.batch.transition
    if transition is None:
        raise ValueError("risk committed batch has no transition")
    request, binding = _decode_state_records(transition.state_records, domain)
    receipt = view.committed_transition.receipt
    if (
        receipt.revision != request.snapshot.revision
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
    ):
        raise ValueError("risk committed receipt is mismatched")
    _validate_committed_read_set(view, request, binding)
    expected_events = _risk_events(
        request,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    if view.committed_transition.batch.trace_batch.events != expected_events:
        raise ValueError("risk committed trace lineage is mismatched")
    if reader is not None:
        parent = _load_parent_from_reader(reader, domain, request)
        continuity = _continuity_failure(request, parent)
        if continuity is not None:
            raise ValueError("risk committed historical continuity is invalid")
    return request, binding


def _validate_committed_read_set(
    view: GovernanceCommitViewV2,
    request: RiskStateAdvanceRequestV2,
    binding: Mapping[str, Any],
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    read_entries = view.committed_transition.batch.read_set.entries
    entries = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in read_entries
    }
    if len(entries) != len(read_entries):
        raise ValueError("risk read set contains duplicate streams")
    grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref, cast(str, binding["grant_ref"])
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
    if entries != expected:
        raise ValueError("risk authority read set is mismatched")


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected_request: RiskStateAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[RiskStateAdvanceRequestV2, GovernanceCommitViewV2]:
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
        request, _ = _decode_committed_view(view, domain, reader=reader)
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


def _load_parent_from_reader(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: RiskStateAdvanceRequestV2,
) -> RiskStateSnapshotV2 | None:
    if request.snapshot.parent_revision == 0:
        return None
    try:
        parent_view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.snapshot.parent_transition_id,
            ),
            invalid_path="/snapshot/parent_transition_id",
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise ValueError("risk historical parent is unavailable") from exc
    if parent_view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        code = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
            if parent_view.failure is None
            else parent_view.failure.code
        )
        path = (
            "/snapshot/parent_transition_id"
            if parent_view.failure is None
            else parent_view.failure.path
        )
        raise GovernanceAuthorityBindingErrorV2(code, path)
    parent_request, _ = _decode_committed_view(parent_view, domain, reader=None)
    parent = parent_request.snapshot
    if (
        parent.revision != request.snapshot.parent_revision
        or parent.transition_id != request.snapshot.parent_transition_id
        or parent.snapshot_root != request.snapshot.parent_snapshot_root
    ):
        raise ValueError("risk historical parent binding is mismatched")
    return parent


def _risk_events(
    request: RiskStateAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> tuple[TraceEvent, TraceEvent]:
    snapshot = request.snapshot
    assessment = snapshot.assessment
    threshold = snapshot.threshold
    binding = cast(dict[str, Any], _portable_projection(session_binding))
    common: dict[str, Any] = {
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
        "observed_epoch": request.epoch,
        "session_binding": binding,
        "target_ref": request.target_ref,
        "advance_ref": request.advance_ref,
        "protocol_ref": snapshot.protocol_ref,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "risk_policy_root": snapshot.risk_policy_root,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "revision": snapshot.revision,
        "epoch": snapshot.epoch,
        "parent_epoch": snapshot.parent_epoch,
        "current_step": snapshot.current_step,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "assessment_root": assessment.assessment_root,
        "threshold_root": threshold.threshold_root,
        "source_context_root": snapshot.source_context_root,
        "read_set_root": read_set_root,
    }
    state_event = TraceEvent(
        event_type="risk_state_advanced",
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="atomically advance one durable risk lineage",
        lineage=common,
    )
    semantic_event = TraceEvent(
        event_type="risk_assessed_v2",
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="classify risk and freeze the declared threshold projection",
        lineage={
            **common,
            "assessment_ref": assessment.assessment_ref,
            "issuer_ref": assessment.issuer_ref,
            "risk_band": assessment.risk_band.value,
            "risk_input_roots": list(assessment.risk_input_roots),
            "rationale_codes": list(assessment.rationale_codes),
            "assessment_method": assessment.assessment_method,
            "issued_at_step": assessment.issued_at_step,
            "expires_at_step": assessment.expires_at_step,
            "previous_assessment_root": assessment.previous_assessment_root,
            "window_reset_required": assessment.window_reset_required,
            "provenance_ref": assessment.provenance_ref,
            "source_trace_roots": list(assessment.source_trace_roots),
        },
    )
    return state_event, semantic_event
