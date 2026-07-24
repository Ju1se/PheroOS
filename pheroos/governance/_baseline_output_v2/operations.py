"""StateStore-backed scoped baseline-output v2 operations."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    _compute_root,
    _governance_authority_session_state_v2,
    _governance_issuer_capability_state_v2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2,
    _bound_failure_attempt,
    _canonical_commit_view_v2,
    _commit_transition,
    _current_session_grant_failure,
    _decode_grant_state,
    _open_governance_authority_session_binding_v2,
    _portable_projection,
    _read_set,
    _reconcile,
    _require_store,
    _scoped_manifest_authority_matches_domain_v2,
    _session_binding,
    _session_domain,
    _session_grant_precondition,
    _session_lifecycle_precondition,
    _view_state_records,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    GovernanceFailureStageV2,
)
from pheroos.governance.authority_session_v2 import (
    governance_verified_signal_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)

from pheroos.governance._baseline_output_v2.contracts import (
    BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2,
    BASELINE_DECISION_STATE_SCHEMA_V2,
    BASELINE_EVIDENCE_STATE_SCHEMA_V2,
    BASELINE_MANIFEST_STATE_SCHEMA_V2,
    BASELINE_OUTPUT_STATE_SCHEMA_V2,
    BASELINE_STOP_STATE_SCHEMA_V2,
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
    baseline_output_result_root_v2,
)


_ACTIONABLE_STATUSES = frozenset(
    {
        BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
        BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
    }
)
_STAGE_STREAM_FIELDS = {
    "manifest": "manifest_stream_ref",
    "evidence": "evidence_stream_ref",
    "stop": "stop_stream_ref",
    "decision": "decision_stream_ref",
}
_SESSION_BINDING_FIELDS = {
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


def open_baseline_output_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: BaselineOutputRequestV2,
    operation: GovernanceIssuerOperationV2,
) -> GovernanceAuthoritySessionV2:
    """Open one request-, target-, action-, operation-, and payload-bound session."""

    if type(request) is not BaselineOutputRequestV2:
        raise TypeError("baseline output session requires its exact request type")
    if operation not in {
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    }:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/operation",
        )
    session = _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.request_ref,
        request_root=request.request_root,
        operation=operation,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=(request.target_ref,),
        action_refs=(request.action_ref,),
    )
    state = _governance_authority_session_state_v2(session)
    if not _scoped_manifest_authority_matches_domain_v2(
        request.manifest,
        _session_domain(state),
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
            "/manifest/authority_policy",
        )
    return session


def issue_action_permission_v2(
    request: BaselineOutputRequestV2,
    *,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Materialize prerequisites and commit one independently current permission."""

    _require_request(request)
    session, failure = _validated_session_or_failure(
        authority_session,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        request.permission_stream_ref,
        request.permission_transition_id,
    )
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    retry = _reconcile_permission(store, request, session)
    if retry is not None:
        return retry
    grant_failure = _session_grant_attempt(
        session, request.permission_stream_ref, request.permission_transition_id
    )
    if grant_failure is not None:
        return grant_failure
    operation_failure = _permission_stage_operations_failure(session, request)
    if operation_failure is not None:
        return _failure_from_session(
            session,
            request.permission_stream_ref,
            request.permission_transition_id,
            *operation_failure,
        )
    prepared = _prepare_permission_inputs(store, request, session)
    if isinstance(prepared, GovernanceCommitAttemptV2):
        return prepared
    (
        manifest_head,
        evidence_head,
        stop_head,
        decision_head,
        decision,
        evidence,
    ) = prepared
    permission = _permission_from_decision(request, session, decision, evidence)
    write_head = store.load_head_v2(request.scope_ref, request.permission_stream_ref)
    observed = (
        write_head,
        manifest_head,
        evidence_head,
        stop_head,
        decision_head,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    state = _permission_state(request, session, permission)
    event = _permission_event(request, session, permission)
    return _commit_transition(
        store=store,
        domain=_session_domain(session),
        stream_ref=request.permission_stream_ref,
        transition_id=request.permission_transition_id,
        write_head=write_head,
        observed_heads=observed,
        state_records=state,
        event=event,
    )


def evaluate_and_commit_baseline_output_v2(
    request: BaselineOutputRequestV2,
    *,
    authority_session: object = None,
) -> BaselineOutputResultV2:
    """Recompute every gate and atomically commit one baseline terminal output."""

    _require_request(request)
    session, failure = _validated_session_or_failure(
        authority_session,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        request.output_stream_ref,
        request.output_transition_id,
    )
    if failure is not None:
        return _failure_result(request, failure)
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    existing = _reconcile_output(store, request, session)
    if existing is not None:
        return _result_from_attempt(store, request, existing)
    grant_failure = _session_grant_attempt(
        session,
        request.output_stream_ref,
        request.output_transition_id,
    )
    if grant_failure is not None:
        return _failure_result(request, grant_failure)
    loaded = _load_output_inputs(store, request)
    if isinstance(loaded, GovernanceCommitAttemptV2):
        return _failure_result(request, loaded)
    heads, permission, decision = loaded
    permission_failure = _permission_binding_failure(request, permission, decision)
    if permission_failure is not None:
        return _failure_result(
            request,
            _failure_from_session(
                session,
                request.output_stream_ref,
                request.output_transition_id,
                *permission_failure,
            ),
            decision=decision,
            permission=permission,
        )
    permission_grant = _permission_issuer_grant_head(
        store,
        request,
        session,
        permission,
    )
    if isinstance(permission_grant, GovernanceCommitAttemptV2):
        return _failure_result(
            request,
            permission_grant,
            decision=decision,
            permission=permission,
        )
    write_head = store.load_head_v2(request.scope_ref, request.output_stream_ref)
    output_grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        session.grant_ref,
    )
    permission_grant_dependency = (
        ()
        if permission_grant.stream_ref == output_grant_stream
        else (permission_grant,)
    )
    observed = (
        write_head,
        *heads,
        *permission_grant_dependency,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    result_root = baseline_output_result_root_v2(
        request,
        terminal_status=decision["terminal_status"],
        candidate_ref=decision["candidate_ref"],
        permission_root=permission.permission_root,
    )
    read_set_root = _read_set(observed).root()
    state = _output_state(request, session, permission, decision, result_root)
    event = _output_event(
        request,
        session,
        permission,
        decision,
        result_root,
        read_set_root,
    )
    attempt = _commit_transition(
        store=store,
        domain=_session_domain(session),
        stream_ref=request.output_stream_ref,
        transition_id=request.output_transition_id,
        write_head=write_head,
        observed_heads=observed,
        state_records=state,
        event=event,
    )
    return _result_from_attempt(store, request, attempt)


def recover_baseline_output_result_v2(
    request: BaselineOutputRequestV2,
    *,
    state_reader: GovernanceStateReaderV2,
) -> BaselineOutputResultV2:
    """Recover one committed output fact without restoring portable authority.

    The reader is the only source of commit inclusion and currentness.  A
    historical output remains deliverable, while authorization is reconstructed
    only when the output and every original authority dependency are current.
    """

    _require_request(request)
    attempt = _load_recovery_attempt(request, state_reader)
    return _result_from_attempt(state_reader, request, attempt)


def _prepare_permission_inputs(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
) -> (
    tuple[
        GovernanceHeadV2,
        GovernanceHeadV2,
        GovernanceHeadV2,
        GovernanceHeadV2,
        dict[str, Any],
        dict[str, Any],
    ]
    | GovernanceCommitAttemptV2
):
    manifest = _ensure_manifest_state(store, request, session)
    if isinstance(manifest, GovernanceCommitAttemptV2):
        return manifest
    evidence = _ensure_evidence_state(store, request, session, manifest)
    if isinstance(evidence, GovernanceCommitAttemptV2):
        return evidence
    stop = _ensure_stop_state(store, request, session, manifest)
    if isinstance(stop, GovernanceCommitAttemptV2):
        return stop
    decision = _ensure_decision_state(store, request, session, manifest, evidence, stop)
    if isinstance(decision, GovernanceCommitAttemptV2):
        return decision
    decision_head, decision_record = decision
    evidence_record = _decode_evidence_state(
        store.load_state_v2(request.scope_ref, request.evidence_stream_ref),
        request,
    )
    return manifest, evidence, stop, decision_head, decision_record, evidence_record


def _ensure_manifest_state(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    current_head = store.load_head_v2(request.scope_ref, request.manifest_stream_ref)
    current = _project_state(
        store.load_state_v2(request.scope_ref, request.manifest_stream_ref)
    )
    if _manifest_state_matches(current, request):
        return current_head
    state = {
        "schema": BASELINE_MANIFEST_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.manifest_stream_ref,
        "protocol_ref": request.manifest.id,
        "manifest": request.manifest.to_dict(),
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "request_root": request.request_root,
        "session_binding": _session_binding(session),
    }
    attempted = _commit_stage(
        store,
        request,
        session,
        role="manifest",
        write_head=current_head,
        dependencies=(),
        state=state,
        event=_manifest_event(request, session),
    )
    return _head_after_stage(store, request, "manifest", attempted)


def _ensure_evidence_state(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
    manifest_head: GovernanceHeadV2,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    signals = _verified_signal_bindings(store, request, session)
    if isinstance(signals, GovernanceCommitAttemptV2):
        return signals
    signal_records, signal_heads = signals
    evidence_root = _evidence_root(request, signal_records)
    state = {
        "schema": BASELINE_EVIDENCE_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.evidence_stream_ref,
        "request_root": request.request_root,
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "target_ref": request.target_ref,
        "signals": deepcopy(signal_records),
        "qualified_signal_count": len(signal_records),
        "evidence_root": evidence_root,
        "session_binding": _session_binding(session),
    }
    current_head = store.load_head_v2(request.scope_ref, request.evidence_stream_ref)
    attempted = _commit_stage(
        store,
        request,
        session,
        role="evidence",
        write_head=current_head,
        dependencies=(manifest_head, *signal_heads),
        state=state,
        event=_evidence_event(request, session, evidence_root, len(signal_records)),
    )
    return _head_after_stage(store, request, "evidence", attempted)


def _ensure_stop_state(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
    manifest_head: GovernanceHeadV2,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    stop_records = [
        deepcopy(_portable_projection(item)) for item in request.stop_resolutions
    ]
    stop_root = _stop_root(request, stop_records)
    state = {
        "schema": BASELINE_STOP_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stop_stream_ref,
        "request_root": request.request_root,
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "target_ref": request.target_ref,
        "resolutions": stop_records,
        "stop_root": stop_root,
        "session_binding": _session_binding(session),
    }
    current_head = store.load_head_v2(request.scope_ref, request.stop_stream_ref)
    attempted = _commit_stage(
        store,
        request,
        session,
        role="stop",
        write_head=current_head,
        dependencies=(manifest_head,),
        state=state,
        event=_stop_event(request, session, stop_root),
    )
    return _head_after_stage(store, request, "stop", attempted)


def _ensure_decision_state(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
    manifest_head: GovernanceHeadV2,
    evidence_head: GovernanceHeadV2,
    stop_head: GovernanceHeadV2,
) -> tuple[GovernanceHeadV2, dict[str, Any]] | GovernanceCommitAttemptV2:
    evidence = _decode_evidence_state(
        store.load_state_v2(request.scope_ref, request.evidence_stream_ref),
        request,
    )
    stop = _decode_stop_state(
        store.load_state_v2(request.scope_ref, request.stop_stream_ref),
        request,
    )
    decision = _evaluate_decision(request, evidence, stop)
    state = {
        "schema": BASELINE_DECISION_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.decision_stream_ref,
        "request_root": request.request_root,
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "target_ref": request.target_ref,
        **_decision_wire(decision),
        "session_binding": _session_binding(session),
    }
    current_head = store.load_head_v2(request.scope_ref, request.decision_stream_ref)
    attempted = _commit_stage(
        store,
        request,
        session,
        role="decision",
        write_head=current_head,
        dependencies=(manifest_head, evidence_head, stop_head),
        state=state,
        event=_decision_event(request, session, decision),
    )
    head = _head_after_stage(store, request, "decision", attempted)
    if isinstance(head, GovernanceCommitAttemptV2):
        return head
    return head, decision


def _commit_stage(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
    *,
    role: str,
    write_head: GovernanceHeadV2,
    dependencies: tuple[GovernanceHeadV2, ...],
    state: Mapping[str, Any],
    event: TraceEvent,
) -> GovernanceCommitAttemptV2:
    stream_ref = cast(str, getattr(request, _STAGE_STREAM_FIELDS[role]))
    transition_id = request.stage_transition_id(role)
    existing = _reconcile(
        store,
        _session_domain(session),
        stream_ref,
        transition_id,
        lambda view: _stage_view_matches(view, state),
    )
    if existing is not None:
        return existing
    return _commit_transition(
        store=store,
        domain=_session_domain(session),
        stream_ref=stream_ref,
        transition_id=transition_id,
        write_head=write_head,
        observed_heads=(
            write_head,
            *dependencies,
            _session_grant_precondition(session),
            _session_lifecycle_precondition(session),
        ),
        state_records=state,
        event=event,
    )


def _head_after_stage(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    role: str,
    attempt: GovernanceCommitAttemptV2,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        return attempt
    stream_ref = cast(str, getattr(request, _STAGE_STREAM_FIELDS[role]))
    return store.load_head_v2(request.scope_ref, stream_ref)


def _verified_signal_bindings(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
) -> (
    tuple[list[dict[str, Any]], tuple[GovernanceHeadV2, ...]]
    | GovernanceCommitAttemptV2
):
    records: list[dict[str, Any]] = []
    heads: list[GovernanceHeadV2] = []
    declared = {
        item.id
        for item in request.manifest.candidates
        if item.target == request.target_ref
    }
    for index, proposal in enumerate(request.verified_signals):
        candidate_ref = cast(str, proposal["candidate_ref"])
        if candidate_ref not in declared:
            return _failure_from_session(
                session,
                request.evidence_stream_ref,
                request.stage_transition_id("evidence"),
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                f"/verified_signals/{index}/candidate_ref",
            )
        stream_ref = governance_verified_signal_stream_ref_v2(
            request.scope_ref,
            cast(str, proposal["signal_ref"]),
            request.target_ref,
        )
        view = store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            cast(str, proposal["signal_transition_id"]),
        )
        if not _verified_signal_matches(view, request, proposal):
            return _failure_from_session(
                session,
                request.evidence_stream_ref,
                request.stage_transition_id("evidence"),
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                f"/verified_signals/{index}",
            )
        heads.append(store.load_head_v2(request.scope_ref, stream_ref))
        records.append(
            {
                **cast(dict[str, Any], _portable_projection(proposal)),
                "verified_signal_stream_ref": stream_ref,
                "verified_signal_receipt_root": (
                    view.committed_transition.receipt.receipt_root
                    if view.committed_transition is not None
                    else ""
                ),
            }
        )
    return records, tuple(heads)


def _verified_signal_matches(
    view: Any,
    request: BaselineOutputRequestV2,
    proposal: Mapping[str, Any],
) -> bool:
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.position_observation is None
        or view.position_observation.position is not GovernanceCommitPositionV2.CURRENT
    ):
        return False
    state = _view_state_records(view)
    if state is None:
        return False
    projected = _project_state(state)
    return bool(
        projected.get("schema") == GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2
        and projected.get("status") == "verified"
        and projected.get("scope_ref") == request.scope_ref
        and projected.get("run_ref") == request.run_ref
        and projected.get("target_ref") == request.target_ref
        and projected.get("signal_ref") == proposal["signal_ref"]
        and projected.get("signal_root") == proposal["signal_root"]
        and projected.get("evidence_root") == proposal["evidence_root"]
    )


def _evaluate_decision(
    request: BaselineOutputRequestV2,
    evidence: Mapping[str, Any],
    stop: Mapping[str, Any],
) -> dict[str, Any]:
    fallback = _safe_fallback(request)
    requested_stop = next(
        item
        for item in cast(list[dict[str, Any]], stop["resolutions"])
        if item["action_ref"] == request.action_ref
    )
    if requested_stop["blocked"] is True:
        candidate_ref = fallback
        status = BaselineOutputTerminalStatusV2.BLOCKED
    elif request.manifest.output_policy.decision_mode == "direct_governance":
        candidate_ref = cast(str, request.proposed_candidate_ref)
        status = BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
    else:
        candidate_ref, threshold_met = _evaluate_quorum(request, evidence)
        status = (
            BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
            if threshold_met
            else BaselineOutputTerminalStatusV2.SAFE_FALLBACK
        )
    decision_root = _compute_root(
        "baseline-decision",
        {
            "request_root": request.request_root,
            "manifest_root": request.manifest.manifest_root,
            "output_policy_root": request.output_policy_root,
            "evidence_root": evidence["evidence_root"],
            "stop_root": stop["stop_root"],
            "target_ref": request.target_ref,
            "candidate_ref": candidate_ref,
            "terminal_status": status.value,
        },
    )
    return {
        "candidate_ref": candidate_ref,
        "terminal_status": status,
        "evidence_root": evidence["evidence_root"],
        "stop_root": stop["stop_root"],
        "decision_root": decision_root,
    }


def _evaluate_quorum(
    request: BaselineOutputRequestV2,
    evidence: Mapping[str, Any],
) -> tuple[str, bool]:
    policy = request.manifest.quorum_policy
    if policy.target != request.target_ref:
        raise ValueError("baseline quorum policy target is mismatched")
    supporters: dict[str, set[str]] = {
        candidate.id: set()
        for candidate in request.manifest.candidates
        if candidate.target == request.target_ref
    }
    for signal in cast(list[dict[str, Any]], evidence["signals"]):
        supporters[signal["candidate_ref"]].add(signal["source_ref"])
    ranked = sorted(supporters.items(), key=lambda item: (-len(item[1]), item[0]))
    winner = next(
        (
            candidate_ref
            for candidate_ref, sources in ranked
            if len(sources) >= policy.commit_threshold
        ),
        None,
    )
    return (winner, True) if winner is not None else (_safe_fallback(request), False)


def _safe_fallback(request: BaselineOutputRequestV2) -> str:
    fallback_ref = request.manifest.quorum_policy.fallback_candidate
    matches = [
        item
        for item in request.manifest.candidates
        if item.id == fallback_ref
        and item.target == request.target_ref
        and item.safe_fallback is True
    ]
    if len(matches) != 1:
        raise ValueError("baseline quorum fallback is not one declared safe candidate")
    return fallback_ref


def _permission_from_decision(
    request: BaselineOutputRequestV2,
    session: Any,
    decision: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> ActionPermissionV2:
    status = cast(BaselineOutputTerminalStatusV2, decision["terminal_status"])
    action_policy = next(
        item
        for item in request.manifest.output_policy.actions
        if item.action_ref == request.action_ref
    )
    allowed = (
        status in _ACTIONABLE_STATUSES
        and status.value in set(action_policy.allowed_outcomes)
        and _evidence_allows_external_action(request, decision, evidence)
    )
    disposition = (
        ActionPermissionDispositionV2.AUTHORIZED
        if allowed
        else ActionPermissionDispositionV2.DENIED
    )
    return ActionPermissionV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        request_ref=request.request_ref,
        request_root=request.request_root,
        permission_transition_id=request.permission_transition_id,
        permission_stream_ref=request.permission_stream_ref,
        manifest_root=request.manifest.manifest_root,
        output_policy_root=request.output_policy_root,
        evidence_root=cast(str, decision["evidence_root"]),
        stop_root=cast(str, decision["stop_root"]),
        decision_root=cast(str, decision["decision_root"]),
        target_ref=request.target_ref,
        candidate_ref=cast(str, decision["candidate_ref"]),
        action_ref=request.action_ref,
        effect=request.effect,
        terminal_status=status,
        output_payload_root=request.output_payload_root,
        disposition=disposition,
        issued_epoch=request.observed_epoch,
        expires_at_epoch=request.observed_epoch + 1,
        grant_ref=session.grant_ref,
        grant_root=session.grant_root,
        grant_binding_ref=session.grant_binding_ref,
    )


def _evidence_allows_external_action(
    request: BaselineOutputRequestV2,
    decision: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> bool:
    signals = cast(list[dict[str, Any]], evidence["signals"])
    if not signals:
        return False
    status = cast(BaselineOutputTerminalStatusV2, decision["terminal_status"])
    if status is BaselineOutputTerminalStatusV2.SAFE_FALLBACK:
        return True
    candidate_ref = cast(str, decision["candidate_ref"])
    return any(item["candidate_ref"] == candidate_ref for item in signals)


def _load_output_inputs(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
) -> (
    tuple[tuple[GovernanceHeadV2, ...], ActionPermissionV2, dict[str, Any]]
    | GovernanceCommitAttemptV2
):
    try:
        heads = tuple(
            store.load_head_v2(request.scope_ref, stream_ref)
            for stream_ref in (
                request.manifest_stream_ref,
                request.evidence_stream_ref,
                request.stop_stream_ref,
                request.decision_stream_ref,
                request.permission_stream_ref,
            )
        )
        manifest = _decode_manifest_state(
            store.load_state_v2(request.scope_ref, request.manifest_stream_ref),
            request,
        )
        evidence = _decode_evidence_state(
            store.load_state_v2(request.scope_ref, request.evidence_stream_ref),
            request,
        )
        stop = _decode_stop_state(
            store.load_state_v2(request.scope_ref, request.stop_stream_ref),
            request,
        )
        decision = _decode_decision_state(
            store.load_state_v2(request.scope_ref, request.decision_stream_ref),
            request,
        )
        permission = _decode_permission_state(
            store.load_state_v2(request.scope_ref, request.permission_stream_ref),
            request,
        )
        recomputed = _evaluate_decision(request, evidence, stop)
        if decision != recomputed or manifest["manifest"] != request.manifest.to_dict():
            raise ValueError("baseline output durable inputs do not recompute exactly")
        return heads, permission, decision
    except KeyError:
        code = AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED
        path = "/permission_stream_ref"
    except (TypeError, ValueError):
        code = AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
        path = "/authority_inputs"
    return _bound_failure_attempt(
        request.domain_root,
        request.scope_ref,
        request.output_stream_ref,
        request.output_transition_id,
        code,
        path,
        GovernanceFailureStageV2.PRECONDITION,
    )


def _permission_binding_failure(
    request: BaselineOutputRequestV2,
    permission: ActionPermissionV2,
    decision: Mapping[str, Any],
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    expected = {
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "run_ref": request.run_ref,
        "request_ref": request.request_ref,
        "request_root": request.request_root,
        "permission_transition_id": request.permission_transition_id,
        "permission_stream_ref": request.permission_stream_ref,
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "evidence_root": decision["evidence_root"],
        "stop_root": decision["stop_root"],
        "decision_root": decision["decision_root"],
        "target_ref": request.target_ref,
        "candidate_ref": decision["candidate_ref"],
        "action_ref": request.action_ref,
        "effect": request.effect,
        "terminal_status": decision["terminal_status"],
        "output_payload_root": request.output_payload_root,
    }
    for field_name, value in expected.items():
        if getattr(permission, field_name) != value:
            return (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                f"/{field_name}",
            )
    if (
        not permission.issued_epoch
        <= request.observed_epoch
        < permission.expires_at_epoch
    ):
        return (
            AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
            "/expires_at_epoch",
        )
    return None


def _load_recovery_attempt(
    request: BaselineOutputRequestV2,
    state_reader: object,
) -> GovernanceCommitAttemptV2:
    """Load and detach the exact output transition through one reader call."""

    try:
        conforms = isinstance(state_reader, GovernanceStateReaderV2)
    except Exception:
        conforms = False
    if not conforms:
        return _recovery_failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/state_reader",
        )
    reader = cast(GovernanceStateReaderV2, state_reader)
    try:
        raw_view = reader.load_commit_view_v2(
            request.scope_ref,
            request.output_stream_ref,
            request.output_transition_id,
        )
    except KeyError:
        return _recovery_failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/output_transition_id",
        )
    except Exception:
        return _recovery_failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "/output_transition_id",
        )
    try:
        view = _canonical_commit_view_v2(
            raw_view,
            invalid_path="/output_transition_id",
        )
        if (
            view.domain_root != request.domain_root
            or view.scope_ref != request.scope_ref
            or view.stream_ref != request.output_stream_ref
            or view.transition_id != request.output_transition_id
            or view.expected_receipt_root is not None
        ):
            raise ValueError("baseline recovery commit view binding is mismatched")
        return GovernanceCommitAttemptV2(
            domain_root=request.domain_root,
            scope_ref=request.scope_ref,
            stream_ref=request.output_stream_ref,
            transition_id=request.output_transition_id,
            disposition=view.disposition,
            failure=view.failure,
            committed_transition=view.committed_transition,
            position_observation=view.position_observation,
        )
    except Exception:
        return _recovery_failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/output_transition_id",
        )


def _recovery_failure_attempt(
    request: BaselineOutputRequestV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        request.domain_root,
        request.scope_ref,
        request.output_stream_ref,
        request.output_transition_id,
        code,
        path,
        GovernanceFailureStageV2.LOAD,
    )


def _result_from_attempt(
    store: GovernanceStateReaderV2,
    request: BaselineOutputRequestV2,
    attempt: GovernanceCommitAttemptV2,
) -> BaselineOutputResultV2:
    if attempt.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED:
        return _retry_result(request, attempt)
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        return _failure_result(request, attempt)
    state = _project_state(_view_or_attempt_state(attempt))
    try:
        _require_output_state(state, request)
        permission = ActionPermissionV2.from_dict(state["permission"])
        status = BaselineOutputTerminalStatusV2(state["terminal_status"])
        candidate_ref = cast(str, state["candidate_ref"])
        result_root = cast(str, state["result_root"])
        permission_current_at_epoch = _require_recovered_output_bindings(
            state,
            request,
            permission,
            status,
            candidate_ref,
            result_root,
            attempt,
        )
    except (KeyError, TypeError, ValueError):
        invalid = _bound_failure_attempt(
            request.domain_root,
            request.scope_ref,
            request.output_stream_ref,
            request.output_transition_id,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/committed_transition",
            GovernanceFailureStageV2.RECONCILIATION,
        )
        return _failure_result(request, invalid)
    current = permission_current_at_epoch and _permission_current_for_result(
        store,
        request,
        permission,
        attempt,
    )
    action = (
        BaselineOutputActionDispositionV2.AUTHORIZED
        if current
        else BaselineOutputActionDispositionV2.DENIED
    )
    return BaselineOutputResultV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        request_ref=request.request_ref,
        request_root=request.request_root,
        output_transition_id=request.output_transition_id,
        output_payload_root=request.output_payload_root,
        terminal_status=status,
        candidate_ref=candidate_ref,
        delivery_disposition=BaselineOutputDeliveryDispositionV2.DELIVERABLE,
        action_disposition=action,
        permission_root=permission.permission_root,
        authorization=permission if current else None,
        commit_attempt=attempt,
        result_root=result_root,
    )


def _require_recovered_output_bindings(
    state: Mapping[str, Any],
    request: BaselineOutputRequestV2,
    permission: ActionPermissionV2,
    status: BaselineOutputTerminalStatusV2,
    candidate_ref: str,
    result_root: str,
    attempt: GovernanceCommitAttemptV2,
) -> bool:
    """Validate durable output semantics and return epoch-current permission."""

    declared = {
        candidate.id
        for candidate in request.manifest.candidates
        if candidate.target == request.target_ref
    }
    if candidate_ref not in declared:
        raise ValueError("recovered output candidate is not declared")
    fallback_ref = _safe_fallback(request)
    if (
        status
        in {
            BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
            BaselineOutputTerminalStatusV2.BLOCKED,
        }
        and candidate_ref != fallback_ref
    ):
        raise ValueError("recovered output fallback candidate is invalid")
    if status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT and (
        request.manifest.output_policy.decision_mode == "direct_governance"
        and candidate_ref != request.proposed_candidate_ref
    ):
        raise ValueError("recovered direct output candidate is invalid")
    if status not in {
        BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
        BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
        BaselineOutputTerminalStatusV2.BLOCKED,
    }:
        raise ValueError("recovered committed output terminal status is invalid")
    decision = {
        "candidate_ref": candidate_ref,
        "terminal_status": status,
        "evidence_root": state["evidence_root"],
        "stop_root": state["stop_root"],
        "decision_root": state["decision_root"],
    }
    permission_failure = _permission_binding_failure(request, permission, decision)
    if permission_failure is not None and permission_failure[0] is not (
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED
    ):
        raise ValueError("recovered output permission binding is invalid")
    expected_action = (
        BaselineOutputActionDispositionV2.AUTHORIZED.value
        if permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
        else BaselineOutputActionDispositionV2.DENIED.value
    )
    expected_result_root = baseline_output_result_root_v2(
        request,
        terminal_status=status,
        candidate_ref=candidate_ref,
        permission_root=permission.permission_root,
    )
    if (
        state["permission_root"] != permission.permission_root
        or state["action_disposition"] != expected_action
        or result_root != expected_result_root
    ):
        raise ValueError("recovered output result binding is invalid")
    _require_recovery_commit_material(state, request, permission, attempt)
    return permission_failure is None


def _require_recovery_commit_material(
    state: Mapping[str, Any],
    request: BaselineOutputRequestV2,
    permission: ActionPermissionV2,
    attempt: GovernanceCommitAttemptV2,
) -> None:
    committed = attempt.committed_transition
    if committed is None or committed.batch.transition is None:
        raise ValueError("recovered output transition is absent")
    batch = committed.batch
    receipt = committed.receipt
    binding = _project_state(state["session_binding"])
    if set(binding) != _SESSION_BINDING_FIELDS:
        raise ValueError("recovered output session binding fields are invalid")
    expected_binding = (
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.request_ref,
        request.request_root,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT.value,
        request.observed_epoch,
        [request.target_ref],
        [request.action_ref],
    )
    observed_binding = (
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
    if observed_binding != expected_binding:
        raise ValueError("recovered output session binding is invalid")
    entries = {
        entry.stream_ref: (entry.expected_revision, entry.expected_root)
        for entry in batch.read_set.entries
    }
    output_grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        cast(str, binding["grant_ref"]),
    )
    permission_grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        permission.grant_ref,
    )
    if output_grant_stream == permission_grant_stream and (
        binding["grant_root"] != permission.grant_root
        or binding["grant_binding_ref"] != permission.grant_binding_ref
    ):
        raise ValueError("recovered output shared grant binding is invalid")
    expected_streams = {
        request.output_stream_ref,
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
        output_grant_stream,
        permission_grant_stream,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    if set(entries) != expected_streams:
        raise ValueError("recovered output read set is invalid")
    expected_preconditions = {
        request.output_stream_ref: (receipt.revision - 1, receipt.parent_root),
        output_grant_stream: (
            binding["grant_expected_revision"],
            binding["grant_expected_root"],
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    }
    if any(
        entries[stream_ref] != expected
        for stream_ref, expected in expected_preconditions.items()
    ):
        raise ValueError("recovered output authority precondition is invalid")
    events = batch.trace_batch.events
    if len(events) != 1 or events[0].event_type != "baseline_output_committed":
        raise ValueError("recovered output Trace event is invalid")
    lineage = events[0].lineage
    expected_lineage = {
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.output_stream_ref,
        "transition_id": request.output_transition_id,
        "run_ref": request.run_ref,
        "request_ref": request.request_ref,
        "request_root": request.request_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT.value,
        "observed_epoch": request.observed_epoch,
        "target_ref": request.target_ref,
        "action_ref": request.action_ref,
        "effect": request.effect,
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "evidence_root": state["evidence_root"],
        "stop_root": state["stop_root"],
        "decision_root": state["decision_root"],
        "candidate_ref": state["candidate_ref"],
        "terminal_status": state["terminal_status"],
        "output_payload_root": request.output_payload_root,
        "permission_root": permission.permission_root,
        "result_root": state["result_root"],
        "delivery_disposition": (BaselineOutputDeliveryDispositionV2.DELIVERABLE.value),
        "action_disposition": state["action_disposition"],
        "read_set_root": batch.read_set.root(),
        "session_binding": binding,
    }
    if any(
        _portable_projection(lineage.get(key)) != value
        for key, value in expected_lineage.items()
    ):
        raise ValueError("recovered output Trace binding is invalid")


def _permission_current_for_result(
    store: GovernanceStateReaderV2,
    request: BaselineOutputRequestV2,
    permission: ActionPermissionV2,
    attempt: GovernanceCommitAttemptV2,
) -> bool:
    if (
        permission.disposition is not ActionPermissionDispositionV2.AUTHORIZED
        or attempt.position_observation is None
        or attempt.position_observation.position
        is not GovernanceCommitPositionV2.CURRENT
    ):
        return False
    try:
        permission_state = _decode_permission_state(
            store.load_state_v2(request.scope_ref, request.permission_stream_ref),
            request,
        )
        output_state = _project_state(_view_or_attempt_state(attempt))
    except Exception:
        return False
    transition = attempt.committed_transition
    if transition is None:
        return False
    dependencies_are_current = all(
        _read_precondition_is_current(store, request, entry)
        for entry in transition.batch.read_set.entries
        if entry.stream_ref != request.output_stream_ref
    )
    return bool(
        permission_state.permission_root == permission.permission_root
        and dependencies_are_current
        and output_state.get("permission_root") == permission.permission_root
    )


def _read_precondition_is_current(
    store: GovernanceStateReaderV2,
    request: BaselineOutputRequestV2,
    precondition: GovernanceReadPreconditionV2,
) -> bool:
    try:
        loaded = store.load_head_v2(request.scope_ref, precondition.stream_ref)
        if type(loaded) is not GovernanceHeadV2:
            return False
        current = GovernanceHeadV2.from_dict(loaded.to_dict())
    except Exception:
        return False
    return bool(
        current.domain_root == request.domain_root
        and current.scope_ref == request.scope_ref
        and current.stream_ref == precondition.stream_ref
        and current.revision == precondition.expected_revision
        and current.head_root == precondition.expected_root
    )


def _failure_result(
    request: BaselineOutputRequestV2,
    attempt: GovernanceCommitAttemptV2,
    *,
    decision: Mapping[str, Any] | None = None,
    permission: ActionPermissionV2 | None = None,
) -> BaselineOutputResultV2:
    if attempt.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED:
        return _retry_result(request, attempt)
    status = (
        BaselineOutputTerminalStatusV2.FINALITY_UNAVAILABLE
        if attempt.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
        else BaselineOutputTerminalStatusV2.INVALID
    )
    candidate_ref = (
        cast(str, decision["candidate_ref"])
        if decision is not None
        else _safe_fallback(request)
    )
    permission_root = (
        permission.permission_root
        if permission is not None
        else _compute_root("baseline-missing-permission", request.request_root)
    )
    return BaselineOutputResultV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        request_ref=request.request_ref,
        request_root=request.request_root,
        output_transition_id=request.output_transition_id,
        output_payload_root=request.output_payload_root,
        terminal_status=status,
        candidate_ref=candidate_ref,
        delivery_disposition=BaselineOutputDeliveryDispositionV2.DELIVERABLE,
        action_disposition=BaselineOutputActionDispositionV2.DENIED,
        permission_root=permission_root,
        authorization=None,
        commit_attempt=attempt,
        result_root=baseline_output_result_root_v2(
            request,
            terminal_status=status,
            candidate_ref=candidate_ref,
            permission_root=permission_root,
        ),
    )


def _retry_result(
    request: BaselineOutputRequestV2,
    attempt: GovernanceCommitAttemptV2,
) -> BaselineOutputResultV2:
    return BaselineOutputResultV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        request_ref=request.request_ref,
        request_root=request.request_root,
        output_transition_id=request.output_transition_id,
        output_payload_root=request.output_payload_root,
        terminal_status=None,
        candidate_ref=None,
        delivery_disposition=BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED,
        action_disposition=BaselineOutputActionDispositionV2.DENIED,
        permission_root=_compute_root(
            "baseline-missing-permission",
            request.request_root,
        ),
        authorization=None,
        commit_attempt=attempt,
        result_root=_compute_root(
            "baseline-output-retry",
            {
                "request_root": request.request_root,
                "attempt_root": attempt.attempt_root,
            },
        ),
    )


def _validated_session_or_failure(
    candidate: object,
    request: BaselineOutputRequestV2,
    operation: GovernanceIssuerOperationV2,
    stream_ref: str,
    transition_id: str,
) -> tuple[Any | None, GovernanceCommitAttemptV2 | None]:
    try:
        session = _governance_authority_session_state_v2(candidate)
        _require_store(cast(GovernanceStateStoreV2, session.store))
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _bound_failure_attempt(
            request.domain_root,
            request.scope_ref,
            stream_ref,
            transition_id,
            exc.code,
            exc.path,
            GovernanceFailureStageV2.VALIDATION,
        )
    except TypeError:
        return None, _bound_failure_attempt(
            request.domain_root,
            request.scope_ref,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
            GovernanceFailureStageV2.VALIDATION,
        )
    expected = (
        operation,
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.request_ref,
        request.request_root,
        request.observed_epoch,
        (request.target_ref,),
        (request.action_ref,),
    )
    observed = (
        session.operation,
        session.domain_root,
        session.scope_ref,
        session.run_ref,
        session.request_ref,
        session.request_root,
        session.observed_epoch,
        session.target_refs,
        session.action_refs,
    )
    try:
        domain = _session_domain(session)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _bound_failure_attempt(
            request.domain_root,
            request.scope_ref,
            stream_ref,
            transition_id,
            exc.code,
            exc.path,
            GovernanceFailureStageV2.VALIDATION,
        )
    if not _scoped_manifest_authority_matches_domain_v2(request.manifest, domain):
        return None, _bound_failure_attempt(
            request.domain_root,
            request.scope_ref,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
            "/manifest/authority_policy",
            GovernanceFailureStageV2.VALIDATION,
        )
    if observed != expected:
        return None, _bound_failure_attempt(
            request.domain_root,
            request.scope_ref,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
            GovernanceFailureStageV2.VALIDATION,
        )
    return session, None


def _session_grant_attempt(
    session: Any,
    stream_ref: str,
    transition_id: str,
) -> GovernanceCommitAttemptV2 | None:
    failure = _current_session_grant_failure(session)
    if failure is None:
        return None
    return _failure_from_session(session, stream_ref, transition_id, *failure)


def _permission_stage_operations_failure(
    session: Any,
    request: BaselineOutputRequestV2,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    capability = _governance_issuer_capability_state_v2(session.capability)
    required = _required_permission_stage_operations(request)
    if not required.issubset(set(capability.grant.operations)):
        return AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED, "/operation"
    return None


def _required_permission_stage_operations(
    request: BaselineOutputRequestV2,
) -> frozenset[GovernanceIssuerOperationV2]:
    required = {
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        GovernanceIssuerOperationV2.RESOLVE_STOP,
    }
    if request.manifest.output_policy.decision_mode == "quorum":
        required.add(GovernanceIssuerOperationV2.EVALUATE_QUORUM)
    return frozenset(required)


def _permission_issuer_grant_head(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
    permission: ActionPermissionV2,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    stream_ref = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        permission.grant_ref,
    )
    failure: tuple[AuthorityDiagnosticCodeV2, str] | None
    try:
        state = _decode_grant_state(
            store.load_state_v2(request.scope_ref, stream_ref),
            _session_domain(session),
            permission.grant_ref,
        )
        grant = GovernanceIssuerGrantV2.from_dict(state["grant"])
        head = store.load_head_v2(request.scope_ref, stream_ref)
    except KeyError:
        failure = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
            "/permission/grant_ref",
        )
    except (GovernanceAuthorityBindingErrorV2, TypeError, ValueError):
        failure = (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/permission/grant_ref",
        )
    else:
        failure = _permission_issuer_grant_failure(
            request,
            permission,
            state,
            grant,
        )
        if failure is None:
            return head
    return _failure_from_session(
        session,
        request.output_stream_ref,
        request.output_transition_id,
        *failure,
    )


def _permission_issuer_grant_failure(
    request: BaselineOutputRequestV2,
    permission: ActionPermissionV2,
    state: Mapping[str, Any],
    grant: GovernanceIssuerGrantV2,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    if state["status"] == "revoked":
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
            "/permission/grant_ref",
        )
    if state["status"] != "active":
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/permission/grant_ref",
        )
    expected = (
        request.domain_root,
        request.scope_ref,
        permission.grant_root,
        permission.grant_binding_ref,
    )
    observed = (
        grant.domain_root,
        grant.scope_ref,
        grant.grant_root,
        grant.grant_binding_ref,
    )
    if observed != expected:
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/permission/grant_ref",
        )
    if (
        not _required_permission_stage_operations(request).issubset(
            set(grant.operations)
        )
        or request.target_ref not in grant.target_refs
        or request.action_ref not in grant.action_refs
    ):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/permission/grant_ref",
        )
    if not grant.not_before_epoch <= permission.issued_epoch <= grant.expires_at_epoch:
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/permission/issued_epoch",
        )
    return None


def _failure_from_session(
    session: Any,
    stream_ref: str,
    transition_id: str,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        session.domain_root,
        session.scope_ref,
        stream_ref,
        transition_id,
        code,
        path,
        GovernanceFailureStageV2.PRECONDITION,
    )


def _reconcile_permission(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
) -> GovernanceCommitAttemptV2 | None:
    return _reconcile(
        store,
        _session_domain(session),
        request.permission_stream_ref,
        request.permission_transition_id,
        lambda view: _permission_view_matches(view, request, session),
    )


def _reconcile_output(
    store: GovernanceStateStoreV2,
    request: BaselineOutputRequestV2,
    session: Any,
) -> GovernanceCommitAttemptV2 | None:
    return _reconcile(
        store,
        _session_domain(session),
        request.output_stream_ref,
        request.output_transition_id,
        lambda view: _output_view_matches(view, request, session),
    )


def _permission_view_matches(
    view: Any, request: BaselineOutputRequestV2, session: Any
) -> bool:
    state = _view_state_records(view)
    if state is None:
        return False
    projected = _project_state(state)
    return bool(
        projected.get("schema") == BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2
        and projected.get("request_root") == request.request_root
        and projected.get("output_payload_root") == request.output_payload_root
        and projected.get("session_binding") == _session_binding(session)
    )


def _output_view_matches(
    view: Any, request: BaselineOutputRequestV2, session: Any
) -> bool:
    state = _view_state_records(view)
    if state is None:
        return False
    projected = _project_state(state)
    return bool(
        projected.get("schema") == BASELINE_OUTPUT_STATE_SCHEMA_V2
        and projected.get("request_root") == request.request_root
        and projected.get("output_payload_root") == request.output_payload_root
        and projected.get("session_binding") == _session_binding(session)
    )


def _stage_view_matches(view: Any, expected: Mapping[str, Any]) -> bool:
    state = _view_state_records(view)
    return state is not None and _project_state(state) == _project_state(expected)


def _manifest_state_matches(
    state: Mapping[str, Any], request: BaselineOutputRequestV2
) -> bool:
    return bool(
        state.get("schema") == BASELINE_MANIFEST_STATE_SCHEMA_V2
        and state.get("domain_root") == request.domain_root
        and state.get("scope_ref") == request.scope_ref
        and state.get("stream_ref") == request.manifest_stream_ref
        and state.get("protocol_ref") == request.manifest.id
        and state.get("manifest") == request.manifest.to_dict()
        and state.get("manifest_root") == request.manifest.manifest_root
        and state.get("output_policy_root") == request.output_policy_root
    )


def _decode_manifest_state(
    value: object, request: BaselineOutputRequestV2
) -> dict[str, Any]:
    state = _project_state(value)
    if not _manifest_state_matches(state, request):
        raise ValueError("baseline manifest state is mismatched")
    return state


def _decode_evidence_state(
    value: object, request: BaselineOutputRequestV2
) -> dict[str, Any]:
    state = _project_state(value)
    required = {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "request_root",
        "manifest_root",
        "output_policy_root",
        "target_ref",
        "signals",
        "qualified_signal_count",
        "evidence_root",
        "session_binding",
    }
    _require_state_fields(state, required, "baseline evidence")
    if (
        state["schema"] != BASELINE_EVIDENCE_STATE_SCHEMA_V2
        or state["domain_root"] != request.domain_root
        or state["scope_ref"] != request.scope_ref
        or state["stream_ref"] != request.evidence_stream_ref
        or state["request_root"] != request.request_root
        or state["manifest_root"] != request.manifest.manifest_root
        or state["output_policy_root"] != request.output_policy_root
        or state["target_ref"] != request.target_ref
        or state["qualified_signal_count"] != len(state["signals"])
        or state["evidence_root"] != _evidence_root(request, state["signals"])
    ):
        raise ValueError("baseline evidence state binding is invalid")
    return state


def _decode_stop_state(
    value: object, request: BaselineOutputRequestV2
) -> dict[str, Any]:
    state = _project_state(value)
    required = {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "request_root",
        "manifest_root",
        "output_policy_root",
        "target_ref",
        "resolutions",
        "stop_root",
        "session_binding",
    }
    _require_state_fields(state, required, "baseline stop")
    if (
        state["schema"] != BASELINE_STOP_STATE_SCHEMA_V2
        or state["domain_root"] != request.domain_root
        or state["scope_ref"] != request.scope_ref
        or state["stream_ref"] != request.stop_stream_ref
        or state["request_root"] != request.request_root
        or state["manifest_root"] != request.manifest.manifest_root
        or state["output_policy_root"] != request.output_policy_root
        or state["target_ref"] != request.target_ref
        or state["resolutions"]
        != [_portable_projection(item) for item in request.stop_resolutions]
        or state["stop_root"] != _stop_root(request, state["resolutions"])
    ):
        raise ValueError("baseline stop state binding is invalid")
    return state


def _decode_decision_state(
    value: object, request: BaselineOutputRequestV2
) -> dict[str, Any]:
    state = _project_state(value)
    required = {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "request_root",
        "manifest_root",
        "output_policy_root",
        "target_ref",
        "candidate_ref",
        "terminal_status",
        "evidence_root",
        "stop_root",
        "decision_root",
        "session_binding",
    }
    _require_state_fields(state, required, "baseline decision")
    if (
        state["schema"] != BASELINE_DECISION_STATE_SCHEMA_V2
        or state["domain_root"] != request.domain_root
        or state["scope_ref"] != request.scope_ref
        or state["stream_ref"] != request.decision_stream_ref
        or state["request_root"] != request.request_root
        or state["manifest_root"] != request.manifest.manifest_root
        or state["output_policy_root"] != request.output_policy_root
        or state["target_ref"] != request.target_ref
    ):
        raise ValueError("baseline decision state binding is invalid")
    return {
        "candidate_ref": state["candidate_ref"],
        "terminal_status": BaselineOutputTerminalStatusV2(state["terminal_status"]),
        "evidence_root": state["evidence_root"],
        "stop_root": state["stop_root"],
        "decision_root": state["decision_root"],
    }


def _decode_permission_state(
    value: object, request: BaselineOutputRequestV2
) -> ActionPermissionV2:
    state = _project_state(value)
    required = {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "request_root",
        "output_payload_root",
        "permission",
        "permission_root",
        "session_binding",
    }
    _require_state_fields(state, required, "baseline permission")
    permission = ActionPermissionV2.from_dict(state["permission"])
    if (
        state["schema"] != BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2
        or state["domain_root"] != request.domain_root
        or state["scope_ref"] != request.scope_ref
        or state["stream_ref"] != request.permission_stream_ref
        or state["request_root"] != request.request_root
        or state["output_payload_root"] != request.output_payload_root
        or state["permission_root"] != permission.permission_root
    ):
        raise ValueError("baseline permission state binding is invalid")
    return permission


def _require_output_state(
    state: Mapping[str, Any], request: BaselineOutputRequestV2
) -> None:
    required = {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "request_root",
        "output_payload_root",
        "manifest_root",
        "output_policy_root",
        "evidence_root",
        "stop_root",
        "decision_root",
        "candidate_ref",
        "terminal_status",
        "permission",
        "permission_root",
        "result_root",
        "delivery_disposition",
        "action_disposition",
        "session_binding",
    }
    _require_state_fields(cast(dict[str, Any], state), required, "baseline output")
    if (
        state["schema"] != BASELINE_OUTPUT_STATE_SCHEMA_V2
        or state["domain_root"] != request.domain_root
        or state["scope_ref"] != request.scope_ref
        or state["stream_ref"] != request.output_stream_ref
        or state["request_root"] != request.request_root
        or state["output_payload_root"] != request.output_payload_root
        or state["manifest_root"] != request.manifest.manifest_root
        or state["output_policy_root"] != request.output_policy_root
        or state["delivery_disposition"]
        != BaselineOutputDeliveryDispositionV2.DELIVERABLE.value
    ):
        raise ValueError("baseline output state binding is invalid")


def _evidence_root(request: BaselineOutputRequestV2, signals: object) -> str:
    return _compute_root(
        "baseline-qualified-evidence",
        {
            "request_root": request.request_root,
            "manifest_root": request.manifest.manifest_root,
            "target_ref": request.target_ref,
            "signals": deepcopy(_portable_projection(signals)),
        },
    )


def _stop_root(request: BaselineOutputRequestV2, resolutions: object) -> str:
    return _compute_root(
        "baseline-stop-resolution",
        {
            "request_root": request.request_root,
            "manifest_root": request.manifest.manifest_root,
            "target_ref": request.target_ref,
            "resolutions": deepcopy(_portable_projection(resolutions)),
        },
    )


def _decision_wire(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_ref": decision["candidate_ref"],
        "terminal_status": decision["terminal_status"].value,
        "evidence_root": decision["evidence_root"],
        "stop_root": decision["stop_root"],
        "decision_root": decision["decision_root"],
    }


def _permission_state(
    request: BaselineOutputRequestV2,
    session: Any,
    permission: ActionPermissionV2,
) -> dict[str, Any]:
    return {
        "schema": BASELINE_ACTION_PERMISSION_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.permission_stream_ref,
        "request_root": request.request_root,
        "output_payload_root": request.output_payload_root,
        "permission": permission.to_dict(),
        "permission_root": permission.permission_root,
        "session_binding": _session_binding(session),
    }


def _output_state(
    request: BaselineOutputRequestV2,
    session: Any,
    permission: ActionPermissionV2,
    decision: Mapping[str, Any],
    result_root: str,
) -> dict[str, Any]:
    action = (
        BaselineOutputActionDispositionV2.AUTHORIZED
        if permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
        else BaselineOutputActionDispositionV2.DENIED
    )
    return {
        "schema": BASELINE_OUTPUT_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.output_stream_ref,
        "request_root": request.request_root,
        "output_payload_root": request.output_payload_root,
        "manifest_root": request.manifest.manifest_root,
        "output_policy_root": request.output_policy_root,
        "evidence_root": decision["evidence_root"],
        "stop_root": decision["stop_root"],
        "decision_root": decision["decision_root"],
        "candidate_ref": decision["candidate_ref"],
        "terminal_status": decision["terminal_status"].value,
        "permission": permission.to_dict(),
        "permission_root": permission.permission_root,
        "result_root": result_root,
        "delivery_disposition": BaselineOutputDeliveryDispositionV2.DELIVERABLE.value,
        "action_disposition": action.value,
        "session_binding": _session_binding(session),
    }


def _authority_event(
    event_type: str,
    request: BaselineOutputRequestV2,
    session: Any,
    stream_ref: str,
    transition_id: str,
    lineage: Mapping[str, Any],
) -> TraceEvent:
    return TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="commit one scoped baseline-output v2 authority transition",
        lineage={
            "domain_root": request.domain_root,
            "scope_ref": request.scope_ref,
            "stream_ref": stream_ref,
            "transition_id": transition_id,
            "run_ref": request.run_ref,
            "request_ref": request.request_ref,
            "request_root": request.request_root,
            "grant_ref": session.grant_ref,
            "grant_root": session.grant_root,
            "grant_binding_ref": session.grant_binding_ref,
            "operation": session.operation.value,
            "observed_epoch": session.observed_epoch,
            "session_binding": _session_binding(session),
            **deepcopy(dict(lineage)),
        },
    )


def _manifest_event(request: BaselineOutputRequestV2, session: Any) -> TraceEvent:
    return _authority_event(
        "baseline_manifest_activated",
        request,
        session,
        request.manifest_stream_ref,
        request.stage_transition_id("manifest"),
        {
            "target_ref": request.target_ref,
            "action_ref": request.action_ref,
            "protocol_ref": request.manifest.id,
            "manifest_root": request.manifest.manifest_root,
            "output_policy_root": request.output_policy_root,
        },
    )


def _evidence_event(
    request: BaselineOutputRequestV2,
    session: Any,
    evidence_root: str,
    count: int,
) -> TraceEvent:
    return _authority_event(
        "baseline_evidence_qualified",
        request,
        session,
        request.evidence_stream_ref,
        request.stage_transition_id("evidence"),
        {
            "target_ref": request.target_ref,
            "action_ref": request.action_ref,
            "manifest_root": request.manifest.manifest_root,
            "output_policy_root": request.output_policy_root,
            "evidence_root": evidence_root,
            "qualified_signal_count": count,
        },
    )


def _stop_event(
    request: BaselineOutputRequestV2,
    session: Any,
    stop_root: str,
) -> TraceEvent:
    return _authority_event(
        "baseline_stop_resolved",
        request,
        session,
        request.stop_stream_ref,
        request.stage_transition_id("stop"),
        {
            "target_ref": request.target_ref,
            "action_ref": request.action_ref,
            "manifest_root": request.manifest.manifest_root,
            "output_policy_root": request.output_policy_root,
            "stop_root": stop_root,
        },
    )


def _decision_event(
    request: BaselineOutputRequestV2,
    session: Any,
    decision: Mapping[str, Any],
) -> TraceEvent:
    return _authority_event(
        "baseline_decision_evaluated",
        request,
        session,
        request.decision_stream_ref,
        request.stage_transition_id("decision"),
        {
            "target_ref": request.target_ref,
            "action_ref": request.action_ref,
            "manifest_root": request.manifest.manifest_root,
            "output_policy_root": request.output_policy_root,
            "evidence_root": decision["evidence_root"],
            "stop_root": decision["stop_root"],
            "decision_root": decision["decision_root"],
            "candidate_ref": decision["candidate_ref"],
            "terminal_status": decision["terminal_status"].value,
        },
    )


def _permission_event(
    request: BaselineOutputRequestV2,
    session: Any,
    permission: ActionPermissionV2,
) -> TraceEvent:
    return _authority_event(
        "baseline_action_permission_issued",
        request,
        session,
        request.permission_stream_ref,
        request.permission_transition_id,
        {
            "target_ref": request.target_ref,
            "action_ref": request.action_ref,
            "effect": request.effect,
            "manifest_root": permission.manifest_root,
            "output_policy_root": permission.output_policy_root,
            "evidence_root": permission.evidence_root,
            "stop_root": permission.stop_root,
            "decision_root": permission.decision_root,
            "candidate_ref": permission.candidate_ref,
            "terminal_status": permission.terminal_status.value,
            "output_payload_root": permission.output_payload_root,
            "permission_root": permission.permission_root,
            "permission_disposition": permission.disposition.value,
            "expires_at_epoch": permission.expires_at_epoch,
        },
    )


def _output_event(
    request: BaselineOutputRequestV2,
    session: Any,
    permission: ActionPermissionV2,
    decision: Mapping[str, Any],
    result_root: str,
    read_set_root: str,
) -> TraceEvent:
    action = (
        BaselineOutputActionDispositionV2.AUTHORIZED
        if permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
        else BaselineOutputActionDispositionV2.DENIED
    )
    return _authority_event(
        "baseline_output_committed",
        request,
        session,
        request.output_stream_ref,
        request.output_transition_id,
        {
            "target_ref": request.target_ref,
            "action_ref": request.action_ref,
            "effect": request.effect,
            "manifest_root": request.manifest.manifest_root,
            "output_policy_root": request.output_policy_root,
            "evidence_root": decision["evidence_root"],
            "stop_root": decision["stop_root"],
            "decision_root": decision["decision_root"],
            "candidate_ref": decision["candidate_ref"],
            "terminal_status": decision["terminal_status"].value,
            "output_payload_root": request.output_payload_root,
            "permission_root": permission.permission_root,
            "result_root": result_root,
            "delivery_disposition": BaselineOutputDeliveryDispositionV2.DELIVERABLE.value,
            "action_disposition": action.value,
            "read_set_root": read_set_root,
        },
    )


def _project_state(value: object) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict:
        raise TypeError("baseline authority state must project to an exact object")
    return cast(dict[str, Any], projected)


def _require_state_fields(state: dict[str, Any], fields: set[str], label: str) -> None:
    if set(state) != fields:
        raise ValueError(f"{label} state fields are invalid")


def _view_or_attempt_state(attempt: GovernanceCommitAttemptV2) -> Mapping[str, Any]:
    if attempt.committed_transition is None:
        raise ValueError("committed baseline attempt is missing transition")
    transition = attempt.committed_transition.batch.transition
    if transition is None:
        raise ValueError("baseline output commit cannot be a seal")
    return transition.state_records


def _require_request(request: object) -> None:
    if type(request) is not BaselineOutputRequestV2:
        raise TypeError("baseline output operation requires its exact request type")


__all__ = [
    "evaluate_and_commit_baseline_output_v2",
    "issue_action_permission_v2",
    "open_baseline_output_authority_session_v2",
    "recover_baseline_output_result_v2",
]
