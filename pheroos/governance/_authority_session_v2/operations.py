"""StateStore-backed scoped-authority grant and session operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any, cast

from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceDomainSealV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
    _governance_disposition_for_diagnostic_v2,
)
from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
    IssuerGrantVerifierV2,
    _governance_authority_session_state_v2,
    _governance_issuer_capability_state_v2,
    _make_governance_authority_session_v2,
    _make_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
)


GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2 = "pheroos-governance-issuer-grant-state-v2"
GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2 = (
    "pheroos-governance-verified-signal-state-v2"
)

_GRANT_STATE_FIELDS = frozenset(
    {
        "schema",
        "profile",
        "domain_root",
        "scope_ref",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "grant",
        "verification",
        "status",
        "activated_epoch",
        "revoked_epoch",
        "revocation_generation",
    }
)


def activate_governance_issuer_grant_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    transition_id: str,
    observed_epoch: int,
    verifier: IssuerGrantVerifierV2 | None = None,
) -> GovernanceCommitAttemptV2:
    """Atomically activate one exact local or authenticated issuer grant."""

    _require_domain_and_grant(domain, grant)
    _require_transition_id(transition_id)
    _require_epoch(observed_epoch)
    stream_ref = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    try:
        _require_store(store)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            exc.code,
            exc.path,
            GovernanceFailureStageV2.VALIDATION,
        )
    retry = _reconcile(
        store,
        domain,
        stream_ref,
        transition_id,
        lambda view: _activation_view_matches(
            view,
            domain,
            grant,
            observed_epoch,
        ),
    )
    if retry is not None:
        return retry
    verification, verification_failure = _verification_for_profile(
        domain,
        grant,
        observed_epoch,
        verifier,
    )
    if verification_failure is not None:
        code, path = verification_failure
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            code,
            path,
            GovernanceFailureStageV2.VALIDATION,
        )
    try:
        grant_head = store.load_head_v2(domain.scope_ref, stream_ref)
        lifecycle = store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        existing_state = store.load_state_v2(domain.scope_ref, stream_ref)
    except KeyError:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
            GovernanceFailureStageV2.VALIDATION,
        )
    if grant_head.revision != 0 or existing_state:
        code = _existing_grant_diagnostic(existing_state)
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            code,
            "/grant_ref",
            GovernanceFailureStageV2.PRECONDITION,
        )
    state = _active_grant_state(domain, grant, verification, observed_epoch)
    return _commit_transition(
        store=store,
        domain=domain,
        stream_ref=stream_ref,
        transition_id=transition_id,
        write_head=grant_head,
        observed_heads=(grant_head, lifecycle),
        state_records=state,
        event=_authority_event(
            "issuer_grant_activated",
            domain,
            stream_ref,
            transition_id,
            target=grant.grant_ref,
            lineage={
                "profile": domain.profile,
                "grant_ref": grant.grant_ref,
                "grant_root": grant.grant_root,
                "grant_binding_ref": grant.grant_binding_ref,
                "observed_epoch": observed_epoch,
                "revocation_generation": grant.revocation_generation,
                "verification_root": (
                    None if verification is None else verification.verification_root
                ),
            },
        ),
    )


def revoke_governance_issuer_grant_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant_ref: str,
    transition_id: str,
    observed_epoch: int,
) -> GovernanceCommitAttemptV2:
    """Atomically make one active issuer grant terminally revoked."""

    _require_domain(domain)
    _require_text(grant_ref, "grant_ref")
    _require_transition_id(transition_id)
    _require_epoch(observed_epoch)
    stream_ref = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant_ref,
    )
    try:
        _require_store(store)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            exc.code,
            exc.path,
            GovernanceFailureStageV2.VALIDATION,
        )
    retry = _reconcile(
        store,
        domain,
        stream_ref,
        transition_id,
        lambda view: _revocation_view_matches(view, grant_ref, observed_epoch),
    )
    if retry is not None:
        return retry
    try:
        grant_head = store.load_head_v2(domain.scope_ref, stream_ref)
        lifecycle = store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        state = _decode_grant_state(
            store.load_state_v2(domain.scope_ref, stream_ref),
            domain,
            grant_ref,
        )
    except KeyError:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
            GovernanceFailureStageV2.VALIDATION,
        )
    except (TypeError, ValueError):
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/grant_ref",
            GovernanceFailureStageV2.PRECONDITION,
        )
    if state["status"] == "revoked":
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
            "/grant_ref",
            GovernanceFailureStageV2.PRECONDITION,
        )
    grant = GovernanceIssuerGrantV2.from_dict(state["grant"])
    if observed_epoch < state["activated_epoch"]:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/observed_epoch",
            GovernanceFailureStageV2.PRECONDITION,
        )
    if state["revocation_generation"] == MAX_AUTHORITY_REVISION_V2:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/revocation_generation",
            GovernanceFailureStageV2.PRECONDITION,
        )
    revoked_state = dict(state)
    revoked_state["status"] = "revoked"
    revoked_state["revoked_epoch"] = observed_epoch
    revoked_state["revocation_generation"] = state["revocation_generation"] + 1
    return _commit_transition(
        store=store,
        domain=domain,
        stream_ref=stream_ref,
        transition_id=transition_id,
        write_head=grant_head,
        observed_heads=(grant_head, lifecycle),
        state_records=revoked_state,
        event=_authority_event(
            "issuer_grant_revoked",
            domain,
            stream_ref,
            transition_id,
            target=grant_ref,
            lineage={
                "profile": domain.profile,
                "grant_ref": grant_ref,
                "grant_root": grant.grant_root,
                "grant_binding_ref": grant.grant_binding_ref,
                "observed_epoch": observed_epoch,
                "revocation_generation": revoked_state["revocation_generation"],
            },
        ),
    )


def bind_governance_issuer_capability_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    run_ref: str,
    observed_epoch: int,
    verifier: IssuerGrantVerifierV2 | None = None,
) -> GovernanceIssuerCapabilityV2:
    """Bind a committed active grant to the exact trusted writer object."""

    _require_store(store)
    _require_bindable_domain_and_grant(domain, grant)
    _require_text(run_ref, "run_ref")
    _require_epoch(observed_epoch)
    verification, failure = _verification_for_profile(
        domain,
        grant,
        observed_epoch,
        verifier,
    )
    if failure is not None:
        raise GovernanceAuthorityBindingErrorV2(*failure)
    stream_ref = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    try:
        grant_head = store.load_head_v2(domain.scope_ref, stream_ref)
        lifecycle = store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        lifecycle_state = store.load_state_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        state = _decode_grant_state(
            store.load_state_v2(domain.scope_ref, stream_ref),
            domain,
            grant.grant_ref,
        )
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/grant_ref",
        ) from exc
    if lifecycle.revision != 0 or lifecycle_state:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
            "/domain_root",
        )
    _require_active_exact_grant(state, grant, observed_epoch)
    if grant_head.revision == 0:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/grant_ref",
        )
    return _make_governance_issuer_capability_v2(
        store=store,
        domain=domain,
        grant=grant,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        verification=verification,
    )


def open_governance_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: GovernanceVerifiedSignalRequestV2 | GovernanceDomainRetirementRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact request-bound, least-privilege authority session."""

    operation, request_ref, request_root, run_ref, observed_epoch, targets = (
        _request_session_bindings(request)
    )
    return _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request_ref,
        request_root=request_root,
        operation=operation,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        target_refs=targets,
        action_refs=(),
    )


def _open_governance_authority_session_binding_v2(
    capability: GovernanceIssuerCapabilityV2,
    *,
    domain_root: str,
    scope_ref: str,
    request_ref: str,
    request_root: str,
    operation: GovernanceIssuerOperationV2,
    run_ref: str,
    observed_epoch: int,
    target_refs: tuple[str, ...],
    action_refs: tuple[str, ...],
) -> GovernanceAuthoritySessionV2:
    """Open one exact binding for a Governance-owned v2 request family."""

    capability_state = _governance_issuer_capability_state_v2(capability)
    grant = capability_state.grant
    if domain_root != grant.domain_root:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    if scope_ref != grant.scope_ref:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        )
    if operation not in grant.operations:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/operation",
        )
    if target_refs and not set(target_refs) <= set(grant.target_refs):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/target_refs",
        )
    if action_refs and not set(action_refs) <= set(grant.action_refs):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/action_refs",
        )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        grant.scope_ref,
        grant.grant_ref,
    )
    store = cast(GovernanceStateStoreV2, capability_state.store)
    _require_store(store)
    try:
        grant_head = store.load_head_v2(grant.scope_ref, grant_stream)
        lifecycle = store.load_head_v2(
            grant.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        lifecycle_state = store.load_state_v2(
            grant.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        raw_state = store.load_state_v2(grant.scope_ref, grant_stream)
        current = _decode_grant_state(
            raw_state,
            capability_state.domain,
            grant.grant_ref,
        )
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/grant_ref",
        ) from exc
    if lifecycle.revision != 0 or lifecycle_state:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
            "/domain_root",
        )
    _require_active_exact_grant(current, grant, observed_epoch)
    return _make_governance_authority_session_v2(
        capability=capability,
        request_ref=request_ref,
        request_root=request_root,
        operation=operation,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        grant_expected_revision=grant_head.revision,
        grant_expected_root=grant_head.head_root,
        lifecycle_expected_revision=lifecycle.revision,
        lifecycle_expected_root=lifecycle.head_root,
        target_refs=target_refs,
        action_refs=action_refs,
    )


def commit_verified_signal_v2(
    request: GovernanceVerifiedSignalRequestV2,
    *,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Commit one verified signal through a genuine request-bound session."""

    if type(request) is not GovernanceVerifiedSignalRequestV2:
        raise TypeError("verified signal commit requires its exact request type")
    transition_id = request.transition_id
    _require_transition_id(transition_id)
    session, failure = _validated_session_or_failure(
        authority_session,
        request,
        GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        request.stream_ref,
        transition_id,
        target_refs=(request.target_ref,),
    )
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    retry = _reconcile(
        store,
        _session_domain(session),
        request.stream_ref,
        transition_id,
        lambda view: _signal_view_matches(view, request, session),
    )
    if retry is not None:
        return retry
    if request.status != "verified":
        return _failure_attempt_from_session(
            session,
            request.stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
            "/status",
        )
    grant_check = _current_session_grant_failure(session)
    if grant_check is not None:
        code, path = grant_check
        return _failure_attempt_from_session(
            session,
            request.stream_ref,
            transition_id,
            code,
            path,
        )
    write_head = store.load_head_v2(request.scope_ref, request.stream_ref)
    grant_precondition = _session_grant_precondition(session)
    lifecycle_precondition = _session_lifecycle_precondition(session)
    state = {
        "schema": GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "request": request.to_dict(),
        "request_root": request.request_root,
        "operation": GovernanceIssuerOperationV2.VERIFY_SIGNAL.value,
        "grant_ref": session.grant_ref,
        "grant_root": session.grant_root,
        "grant_binding_ref": session.grant_binding_ref,
        "run_ref": request.run_ref,
        "signal_ref": request.signal_ref,
        "target_ref": request.target_ref,
        "signal_root": request.signal_root,
        "evidence_root": request.evidence_root,
        "status": request.status,
        "observed_epoch": request.observed_epoch,
        "session_binding": _session_binding(session),
    }
    return _commit_transition(
        store=store,
        domain=_session_domain(session),
        stream_ref=request.stream_ref,
        transition_id=transition_id,
        write_head=write_head,
        observed_heads=(write_head, grant_precondition, lifecycle_precondition),
        state_records=state,
        event=_authority_event(
            "signal_verified",
            _session_domain(session),
            request.stream_ref,
            transition_id,
            target=request.target_ref,
            lineage={
                "run_ref": request.run_ref,
                "request_ref": request.request_ref,
                "request_root": request.request_root,
                "target_ref": request.target_ref,
                "signal_ref": request.signal_ref,
                "signal_root": request.signal_root,
                "evidence_root": request.evidence_root,
                "grant_ref": session.grant_ref,
                "grant_root": session.grant_root,
                "grant_binding_ref": session.grant_binding_ref,
                "operation": session.operation.value,
                "observed_epoch": session.observed_epoch,
                "session_binding": _session_binding(session),
            },
        ),
    )


def retire_governance_domain_v2(
    request: GovernanceDomainRetirementRequestV2,
    *,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Seal one domain through the existing StateStore lifecycle primitive."""

    if type(request) is not GovernanceDomainRetirementRequestV2:
        raise TypeError("domain retirement requires its exact request type")
    transition_id = request.transition_id
    _require_transition_id(transition_id)
    lifecycle_stream = GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    session, failure = _validated_session_or_failure(
        authority_session,
        request,
        GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        lifecycle_stream,
        transition_id,
        target_refs=(),
    )
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)
    retry = _reconcile(
        store,
        domain,
        lifecycle_stream,
        transition_id,
        lambda view: _retirement_view_matches(view, request, session),
    )
    if retry is not None:
        return retry
    grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        session.grant_ref,
    )
    if (
        grant_stream not in request.stream_refs
        or lifecycle_stream in request.stream_refs
    ):
        return _failure_attempt_from_session(
            session,
            lifecycle_stream,
            transition_id,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
            "/stream_refs",
        )
    grant_check = _current_session_grant_failure(session)
    if grant_check is not None:
        code, path = grant_check
        return _failure_attempt_from_session(
            session,
            lifecycle_stream,
            transition_id,
            code,
            path,
        )
    preconditions = {
        stream_ref: _precondition_from_head(
            store.load_head_v2(request.scope_ref, stream_ref)
        )
        for stream_ref in request.stream_refs
        if stream_ref != grant_stream
    }
    preconditions[grant_stream] = _session_grant_precondition(session)
    lifecycle = _session_lifecycle_precondition(session)
    preconditions[lifecycle_stream] = lifecycle
    read_set = _read_set(tuple(preconditions.values()))
    final_heads = tuple(
        {
            "stream_ref": stream_ref,
            "revision": preconditions[stream_ref].expected_revision,
            "head_root": preconditions[stream_ref].expected_root,
        }
        for stream_ref in sorted(
            request.stream_refs,
            key=lambda item: item.encode("utf-8"),
        )
    )
    seal = GovernanceDomainSealV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        transition_id=transition_id,
        expected_revision=lifecycle.expected_revision,
        expected_root=lifecycle.expected_root,
        final_heads=final_heads,
    )
    event = _authority_event(
        "domain_retired",
        domain,
        lifecycle_stream,
        transition_id,
        target=domain.scope_ref,
        lineage={
            "run_ref": request.run_ref,
            "request_ref": request.request_ref,
            "request_root": request.request_root,
            "reason_ref": request.reason_ref,
            "grant_ref": session.grant_ref,
            "grant_root": session.grant_root,
            "grant_binding_ref": session.grant_binding_ref,
            "operation": session.operation.value,
            "observed_epoch": session.observed_epoch,
            "final_heads_root": seal.final_heads_root,
            "seal_root": seal.seal_root,
            "session_binding": _session_binding(session),
        },
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=lifecycle_stream,
        transition_id=transition_id,
        events=(event,),
    )
    batch = GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=domain.scope_ref,
        stream_ref=lifecycle_stream,
        transition_id=transition_id,
        kind="seal",
        read_set=read_set,
        trace_batch=trace_batch,
        seal=seal,
    )
    return _atomic_commit_v2_or_failure(store, batch)


def _validated_session_or_failure(
    candidate: object,
    request: GovernanceVerifiedSignalRequestV2 | GovernanceDomainRetirementRequestV2,
    operation: GovernanceIssuerOperationV2,
    stream_ref: str,
    transition_id: str,
    *,
    target_refs: tuple[str, ...],
) -> tuple[Any | None, GovernanceCommitAttemptV2 | None]:
    try:
        session = _governance_authority_session_state_v2(candidate)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _failure_attempt_for_request(
            request,
            stream_ref,
            transition_id,
            exc.code,
            exc.path,
        )
    bindings_match = (
        session.operation is operation
        and session.domain_root == request.domain_root
        and session.scope_ref == request.scope_ref
        and session.run_ref == request.run_ref
        and session.request_ref == request.request_ref
        and session.request_root == request.request_root
        and session.observed_epoch == request.observed_epoch
        and session.target_refs == target_refs
        and session.action_refs == ()
    )
    if not bindings_match:
        return None, _failure_attempt_for_request(
            request,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    try:
        _require_store(cast(GovernanceStateStoreV2, session.store))
    except (GovernanceAuthorityBindingErrorV2, TypeError):
        return None, _failure_attempt_for_request(
            request,
            stream_ref,
            transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
        )
    return session, None


def _current_session_grant_failure(
    session: Any,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    try:
        _require_store(cast(GovernanceStateStoreV2, session.store))
    except (GovernanceAuthorityBindingErrorV2, TypeError):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/state_store_version",
        )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        session.scope_ref,
        session.grant_ref,
    )
    try:
        capability = _governance_issuer_capability_state_v2(session.capability)
        state = _decode_grant_state(
            session.store.load_state_v2(session.scope_ref, grant_stream),
            capability.domain,
            session.grant_ref,
        )
    except KeyError:
        return AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH, "/scope_ref"
    except (GovernanceAuthorityBindingErrorV2, TypeError, ValueError):
        return AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED, "/grant_ref"
    status = state.get("status")
    if status == "revoked":
        return AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED, "/grant_ref"
    if (
        state.get("grant_root") != session.grant_root
        or state.get("grant_binding_ref") != session.grant_binding_ref
    ):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/grant_ref"
    grant = capability.grant
    if state["grant"] != grant.to_dict():
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/grant_ref"
    if not grant.not_before_epoch <= session.observed_epoch <= grant.expires_at_epoch:
        return AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED, "/observed_epoch"
    return None


def _current_session_lifecycle_failure(
    session: Any,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    """Report a sealed or substituted lifecycle before dependent-head reads.

    Exact transition reconciliation must run before this check so a response
    lost after an atomic commit remains recoverable.  New transitions use this
    check before reading their parent/dependency heads; otherwise a domain seal
    can be misreported as an ordinary stale parent.
    """

    try:
        store = cast(GovernanceStateStoreV2, session.store)
        _require_store(store)
        head = store.load_head_v2(
            session.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        if type(head) is not GovernanceHeadV2:
            raise TypeError("StateStore returned an invalid lifecycle view")
        detached = GovernanceHeadV2.from_dict(head.to_dict())
    except KeyError:
        return AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH, "/scope_ref"
    except (GovernanceAuthorityBindingErrorV2, TypeError, ValueError):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/state_store_version",
        )
    if (
        detached.domain_root != session.domain_root
        or detached.scope_ref != session.scope_ref
        or detached.stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    ):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/domain_root"
    if detached.revision != 0:
        return AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED, "/domain_root"
    expected = (
        session.lifecycle_expected_revision,
        session.lifecycle_expected_root,
    )
    if (detached.revision, detached.head_root) != expected:
        return (
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/lifecycle_expected_root",
        )
    return None


def _request_session_bindings(
    request: GovernanceVerifiedSignalRequestV2 | GovernanceDomainRetirementRequestV2,
) -> tuple[
    GovernanceIssuerOperationV2,
    str,
    str,
    str,
    int,
    tuple[str, ...],
]:
    if type(request) is GovernanceVerifiedSignalRequestV2:
        return (
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            request.request_ref,
            request.request_root,
            request.run_ref,
            request.observed_epoch,
            (request.target_ref,),
        )
    if type(request) is GovernanceDomainRetirementRequestV2:
        return (
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
            request.request_ref,
            request.request_root,
            request.run_ref,
            request.observed_epoch,
            (),
        )
    raise TypeError("authority session request type is unsupported")


def _commit_transition(
    *,
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    stream_ref: str,
    transition_id: str,
    write_head: GovernanceHeadV2,
    observed_heads: tuple[
        GovernanceHeadV2 | GovernanceReadPreconditionV2,
        ...,
    ],
    state_records: Mapping[str, Any],
    event: TraceEvent,
) -> GovernanceCommitAttemptV2:
    return _commit_transition_events(
        store=store,
        domain=domain,
        stream_ref=stream_ref,
        transition_id=transition_id,
        write_head=write_head,
        observed_heads=observed_heads,
        state_records=state_records,
        events=(event,),
    )


def _commit_transition_events(
    *,
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    stream_ref: str,
    transition_id: str,
    write_head: GovernanceHeadV2,
    observed_heads: tuple[
        GovernanceHeadV2 | GovernanceReadPreconditionV2,
        ...,
    ],
    state_records: Mapping[str, Any],
    events: tuple[TraceEvent, ...],
) -> GovernanceCommitAttemptV2:
    """Atomically commit one state transition and its complete Trace lineage."""

    read_set = _read_set(observed_heads)
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        expected_revision=write_head.revision,
        expected_root=write_head.head_root,
        read_set_root=read_set.root(),
        state_records=state_records,
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        events=events,
    )
    batch = GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        kind="transition",
        read_set=read_set,
        trace_batch=trace_batch,
        transition=transition,
    )
    return _atomic_commit_v2_or_failure(store, batch)


def _read_set(
    observed: tuple[GovernanceHeadV2 | GovernanceReadPreconditionV2, ...],
) -> GovernanceAuthorityReadSetV2:
    preconditions = tuple(
        (item)
        if type(item) is GovernanceReadPreconditionV2
        else _precondition_from_head(cast(GovernanceHeadV2, item))
        for item in observed
    )
    by_stream = {item.stream_ref: item for item in preconditions}
    if len(by_stream) != len(preconditions):
        raise ValueError("authority operation read-set contains duplicate streams")
    return GovernanceAuthorityReadSetV2(
        entries=tuple(
            by_stream[stream_ref]
            for stream_ref in sorted(by_stream, key=lambda item: item.encode("utf-8"))
        )
    )


def _precondition_from_head(head: GovernanceHeadV2) -> GovernanceReadPreconditionV2:
    if type(head) is not GovernanceHeadV2:
        raise TypeError("authority operation requires an exact GovernanceHeadV2")
    return GovernanceReadPreconditionV2(
        stream_ref=head.stream_ref,
        expected_revision=head.revision,
        expected_root=head.head_root,
    )


def _authority_event(
    event_type: str,
    domain: AuthorityDomainV2,
    stream_ref: str,
    transition_id: str,
    *,
    target: str,
    lineage: Mapping[str, Any],
) -> TraceEvent:
    return TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target=target,
        reason="commit one scoped-authority v2 governance transition",
        lineage={
            "scope_ref": domain.scope_ref,
            "stream_ref": stream_ref,
            "transition_id": transition_id,
            "domain_root": domain.domain_root,
            **deepcopy(dict(lineage)),
        },
    )


def _active_grant_state(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    verification: IssuerGrantVerificationV2 | None,
    observed_epoch: int,
) -> dict[str, Any]:
    return {
        "schema": GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2,
        "profile": domain.profile,
        "domain_root": domain.domain_root,
        "scope_ref": domain.scope_ref,
        "grant_ref": grant.grant_ref,
        "grant_root": grant.grant_root,
        "grant_binding_ref": grant.grant_binding_ref,
        "grant": grant.to_dict(),
        "verification": None if verification is None else verification.to_dict(),
        "status": "active",
        "activated_epoch": observed_epoch,
        "revoked_epoch": None,
        "revocation_generation": grant.revocation_generation,
    }


def _decode_grant_state(
    value: object,
    domain: AuthorityDomainV2,
    grant_ref: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("issuer grant state must be a mapping")
    projected = _portable_projection(value)
    state = cast(dict[str, Any], projected)
    if set(state) != _GRANT_STATE_FIELDS:
        raise ValueError("issuer grant state fields are invalid")
    if (
        state["schema"] != GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2
        or state["profile"] != domain.profile
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
        or state["grant_ref"] != grant_ref
        or state["status"] not in {"active", "revoked"}
    ):
        raise ValueError("issuer grant state binding is invalid")
    grant = GovernanceIssuerGrantV2.from_dict(state["grant"])
    if (
        grant.domain_root != domain.domain_root
        or grant.scope_ref != domain.scope_ref
        or grant.grant_ref != grant_ref
        or state["grant_root"] != grant.grant_root
        or state["grant_binding_ref"] != grant.grant_binding_ref
    ):
        raise ValueError("issuer grant state payload is mismatched")
    _validate_grant_state_status(state, grant)
    _validate_grant_state_verification(state, domain.profile, grant)
    return state


def _validate_grant_state_status(
    state: Mapping[str, Any],
    grant: GovernanceIssuerGrantV2,
) -> None:
    _require_epoch(state["activated_epoch"])
    _require_epoch(state["revocation_generation"])
    if not (
        grant.not_before_epoch <= state["activated_epoch"] <= grant.expires_at_epoch
    ):
        raise ValueError("issuer grant activation epoch is outside grant bounds")
    if state["status"] == "active":
        if (
            state["revoked_epoch"] is not None
            or state["revocation_generation"] != grant.revocation_generation
        ):
            raise ValueError("active issuer grant state is invalid")
    else:
        _require_epoch(state["revoked_epoch"])
        if state["revoked_epoch"] < state["activated_epoch"]:
            raise ValueError("issuer grant revocation predates activation")
        if state["revocation_generation"] != grant.revocation_generation + 1:
            raise ValueError("revoked issuer grant generation is invalid")


def _validate_grant_state_verification(
    state: Mapping[str, Any],
    profile: str,
    grant: GovernanceIssuerGrantV2,
) -> None:
    verification = state["verification"]
    if profile == AUTHORITY_LOCAL_PROFILE_V2:
        if verification is not None:
            raise ValueError("local issuer grant cannot contain verification")
    elif profile == AUTHORITY_AUTHENTICATED_PROFILE_V2:
        parsed = IssuerGrantVerificationV2.from_dict(verification)
        if (
            parsed.accepted is not True
            or parsed.grant_root != grant.grant_root
            or parsed.grant_binding_ref != grant.grant_binding_ref
            or parsed.verified_epoch != state["activated_epoch"]
        ):
            raise ValueError("authenticated issuer grant verification is invalid")
    else:
        raise ValueError("issuer grant state profile is unsupported")


def _require_active_exact_grant(
    state: Mapping[str, Any],
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int,
) -> None:
    if state["status"] == "revoked":
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
            "/grant_ref",
        )
    if state["grant"] != grant.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/grant_ref",
        )
    if observed_epoch < state["activated_epoch"]:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/observed_epoch",
        )
    if not grant.not_before_epoch <= observed_epoch <= grant.expires_at_epoch:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/observed_epoch",
        )


def _verification_for_profile(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int,
    verifier: IssuerGrantVerifierV2 | None,
) -> tuple[
    IssuerGrantVerificationV2 | None,
    tuple[AuthorityDiagnosticCodeV2, str] | None,
]:
    if not grant.not_before_epoch <= observed_epoch <= grant.expires_at_epoch:
        return None, (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/observed_epoch",
        )
    if domain.profile == AUTHORITY_LOCAL_PROFILE_V2:
        if verifier is not None:
            return None, (
                AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
                "/verifier",
            )
        return None, None
    if domain.profile != AUTHORITY_AUTHENTICATED_PROFILE_V2:
        return None, (
            AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
            "/profile",
        )
    if verifier is None or not isinstance(verifier, IssuerGrantVerifierV2):
        return None, (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/verification",
        )
    try:
        verification = verifier.verify_issuer_grant_v2(
            grant,
            observed_epoch=observed_epoch,
        )
        if type(verification) is not IssuerGrantVerificationV2:
            raise TypeError("verifier result type is invalid")
        detached = IssuerGrantVerificationV2.from_dict(verification.to_dict())
    except Exception:
        return None, (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/verification",
        )
    if (
        detached.accepted is not True
        or detached.grant_root != grant.grant_root
        or detached.grant_binding_ref != grant.grant_binding_ref
        or detached.verified_epoch != observed_epoch
    ):
        return None, (
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/verification",
        )
    return detached, None


def _reconcile(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    stream_ref: str,
    transition_id: str,
    matches: Callable[[GovernanceCommitViewV2], bool],
) -> GovernanceCommitAttemptV2 | None:
    try:
        view = store.load_commit_view_v2(
            domain.scope_ref,
            stream_ref,
            transition_id,
        )
    except KeyError:
        return None
    try:
        view = _canonical_commit_view_v2(view)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _failure_attempt(
            domain,
            stream_ref,
            transition_id,
            exc.code,
            exc.path,
            GovernanceFailureStageV2.RECONCILIATION,
        )
    if view.disposition is GovernanceCommitDispositionV2.COMMITTED:
        if not matches(view):
            return _failure_attempt(
                domain,
                stream_ref,
                transition_id,
                AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
                "/transition_id",
                GovernanceFailureStageV2.RECONCILIATION,
            )
        assert view.committed_transition is not None
        assert view.position_observation is not None
        return GovernanceCommitAttemptV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            disposition=GovernanceCommitDispositionV2.COMMITTED,
            failure=None,
            committed_transition=view.committed_transition,
            position_observation=view.position_observation,
        )
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        assert view.failure is not None
        return GovernanceCommitAttemptV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            failure=view.failure,
            committed_transition=None,
            position_observation=None,
        )
    return None


def _canonical_commit_view_v2(
    value: object,
    *,
    invalid_path: str = "/transition_id",
) -> GovernanceCommitViewV2:
    """Detach and revalidate one exact public StateReader commit view.

    A Store result is an untrusted boundary value even when it has the expected
    runtime type.  The canonical round trip rechecks the complete nested batch,
    receipt, inclusion proof, and position observation before any governance
    owner may use the view for reconciliation or currentness.
    """

    try:
        if type(value) is not GovernanceCommitViewV2:
            raise TypeError("StateReader returned a non-exact commit view")
        return GovernanceCommitViewV2.from_dict(value.to_dict())
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            invalid_path,
        ) from exc


def _scoped_manifest_authority_matches_domain_v2(
    manifest: object,
    domain: object,
) -> bool:
    """Match one exact scoped manifest selector to one exact authority domain."""

    if (
        type(manifest) is not ScopedProtocolManifestV2
        or type(domain) is not AuthorityDomainV2
    ):
        return False
    try:
        detached_manifest = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
        detached_domain = AuthorityDomainV2.from_dict(domain.to_dict())
    except Exception:
        return False
    policy = detached_manifest.authority_policy
    return bool(
        policy.policy_version == detached_domain.policy_version
        and policy.profile == detached_domain.profile
        and policy.wire_version == detached_domain.wire_version
        and policy.canonical_version == detached_domain.canonical_version
        and policy.ledger_version == detached_domain.ledger_version
        and policy.state_store_version == detached_domain.state_store_version
        and policy.trace_batch_version == detached_domain.trace_batch_version
        and policy.read_set_version == detached_domain.read_set_version
    )


def _activation_view_matches(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int,
) -> bool:
    records = _view_state_records(view)
    if records is None:
        return False
    try:
        state = _decode_grant_state(
            _portable_projection(records),
            domain,
            grant.grant_ref,
        )
    except (TypeError, ValueError):
        return False
    return bool(
        state["status"] == "active"
        and state["grant"] == grant.to_dict()
        and state["activated_epoch"] == observed_epoch
    )


def _revocation_view_matches(
    view: GovernanceCommitViewV2,
    grant_ref: str,
    observed_epoch: int,
) -> bool:
    records = _view_state_records(view)
    return bool(
        records is not None
        and records.get("schema") == GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2
        and records.get("status") == "revoked"
        and records.get("grant_ref") == grant_ref
        and records.get("revoked_epoch") == observed_epoch
    )


def _signal_view_matches(
    view: GovernanceCommitViewV2,
    request: GovernanceVerifiedSignalRequestV2,
    session: Any,
) -> bool:
    records = _view_state_records(view)
    return bool(
        records is not None
        and records.get("schema") == GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2
        and _portable_projection(records.get("request")) == request.to_dict()
        and _portable_projection(records.get("session_binding"))
        == _session_binding(session)
    )


def _retirement_view_matches(
    view: GovernanceCommitViewV2,
    request: GovernanceDomainRetirementRequestV2,
    session: Any,
) -> bool:
    # ``_reconcile`` calls matchers only for a canonical committed view, whose
    # public ABI requires a committed transition.
    committed = cast(GovernanceCommittedTransitionV2, view.committed_transition)
    batch = committed.batch
    if batch.kind != "seal" or batch.seal is None:
        return False
    return any(
        event.event_type == "domain_retired"
        and event.lineage.get("request_ref") == request.request_ref
        and event.lineage.get("request_root") == request.request_root
        and event.lineage.get("run_ref") == request.run_ref
        and event.lineage.get("reason_ref") == request.reason_ref
        and event.lineage.get("grant_root") == session.grant_root
        and _portable_projection(event.lineage.get("session_binding"))
        == _session_binding(session)
        for event in batch.trace_batch.events
    )


def _view_state_records(view: GovernanceCommitViewV2) -> Mapping[str, Any] | None:
    committed = cast(GovernanceCommittedTransitionV2, view.committed_transition)
    transition = committed.batch.transition
    return None if transition is None else transition.state_records


def _portable_projection(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _portable_projection(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable_projection(item) for item in value]
    return value


def _session_binding(session: Any) -> dict[str, Any]:
    return {
        "domain_root": session.domain_root,
        "scope_ref": session.scope_ref,
        "run_ref": session.run_ref,
        "request_ref": session.request_ref,
        "request_root": session.request_root,
        "operation": session.operation.value,
        "observed_epoch": session.observed_epoch,
        "grant_ref": session.grant_ref,
        "grant_root": session.grant_root,
        "grant_binding_ref": session.grant_binding_ref,
        "grant_expected_revision": session.grant_expected_revision,
        "grant_expected_root": session.grant_expected_root,
        "lifecycle_expected_revision": session.lifecycle_expected_revision,
        "lifecycle_expected_root": session.lifecycle_expected_root,
        "target_refs": list(session.target_refs),
        "action_refs": list(session.action_refs),
    }


def _session_domain(session: Any) -> AuthorityDomainV2:
    capability = _governance_issuer_capability_state_v2(session.capability)
    domain = capability.domain
    if (
        session.store is not capability.store
        or session.domain_root != domain.domain_root
        or session.scope_ref != domain.scope_ref
        or domain.domain_root != capability.grant.domain_root
        or domain.scope_ref != capability.grant.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/domain_root",
        )
    return domain


def _session_grant_precondition(session: Any) -> GovernanceReadPreconditionV2:
    return GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            session.scope_ref,
            session.grant_ref,
        ),
        expected_revision=session.grant_expected_revision,
        expected_root=session.grant_expected_root,
    )


def _session_lifecycle_precondition(session: Any) -> GovernanceReadPreconditionV2:
    return GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=session.lifecycle_expected_revision,
        expected_root=session.lifecycle_expected_root,
    )


def _failure_attempt_for_request(
    request: GovernanceVerifiedSignalRequestV2 | GovernanceDomainRetirementRequestV2,
    stream_ref: str,
    transition_id: str,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        request.domain_root,
        request.scope_ref,
        stream_ref,
        transition_id,
        code,
        path,
        GovernanceFailureStageV2.VALIDATION,
    )


def _failure_attempt_from_session(
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


def _failure_attempt(
    domain: AuthorityDomainV2,
    stream_ref: str,
    transition_id: str,
    code: AuthorityDiagnosticCodeV2,
    path: str,
    stage: GovernanceFailureStageV2,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        domain.domain_root,
        domain.scope_ref,
        stream_ref,
        transition_id,
        code,
        path,
        stage,
    )


def _bound_failure_attempt(
    domain_root: str,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
    code: AuthorityDiagnosticCodeV2,
    path: str,
    stage: GovernanceFailureStageV2,
) -> GovernanceCommitAttemptV2:
    failure = GovernanceFailureV2(code=code, path=path, stage=stage)
    return GovernanceCommitAttemptV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        disposition=_governance_disposition_for_diagnostic_v2(code),
        failure=failure,
        committed_transition=None,
        position_observation=None,
    )


def _existing_grant_diagnostic(
    state: Mapping[str, Any],
) -> AuthorityDiagnosticCodeV2:
    if isinstance(state, Mapping) and state.get("status") == "revoked":
        return AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def _require_domain_and_grant(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
) -> None:
    _require_domain(domain)
    if type(grant) is not GovernanceIssuerGrantV2:
        raise TypeError("issuer operation requires GovernanceIssuerGrantV2")
    if grant.domain_root != domain.domain_root or grant.scope_ref != domain.scope_ref:
        raise ValueError("issuer grant crosses the selected authority domain")


def _require_bindable_domain_and_grant(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
) -> None:
    _require_domain(domain)
    if type(grant) is not GovernanceIssuerGrantV2:
        raise TypeError("issuer capability binding requires GovernanceIssuerGrantV2")
    if grant.domain_root != domain.domain_root:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    if grant.scope_ref != domain.scope_ref:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        )


def _require_domain(domain: AuthorityDomainV2) -> None:
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("issuer operation requires AuthorityDomainV2")


def _require_store(store: GovernanceStateStoreV2) -> None:
    try:
        conforms = isinstance(store, GovernanceStateStoreV2)
    except Exception as exc:
        raise TypeError("issuer operation requires a StateStore v2 writer") from exc
    if not conforms:
        raise TypeError("issuer operation requires a StateStore v2 writer")
    try:
        version = store.state_store_version
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/state_store_version",
        ) from exc
    if type(version) is not str or version != GOVERNANCE_STATE_STORE_VERSION_V2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/state_store_version",
        )


def _require_transition_id(value: object) -> None:
    _require_text(value, "transition_id")
    if value == "genesis":
        raise ValueError("transition_id is reserved")


def _require_text(value: object, label: str) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise TypeError(f"{label} must be canonical non-empty text")


def _require_epoch(value: object) -> None:
    if type(value) is not int or not 0 <= value <= MAX_AUTHORITY_REVISION_V2:
        raise TypeError("observed_epoch must be a JSON-safe non-negative integer")


__all__ = [
    "GOVERNANCE_ISSUER_GRANT_STATE_SCHEMA_V2",
    "GOVERNANCE_VERIFIED_SIGNAL_STATE_SCHEMA_V2",
    "activate_governance_issuer_grant_v2",
    "bind_governance_issuer_capability_v2",
    "commit_verified_signal_v2",
    "open_governance_authority_session_v2",
    "retire_governance_domain_v2",
    "revoke_governance_issuer_grant_v2",
]


def _atomic_commit_v2_or_failure(
    store: GovernanceStateStoreV2,
    batch: GovernanceCommitBatchV2,
) -> GovernanceCommitAttemptV2:
    """Fail closed if a previously validated Store loses its writer capability."""

    try:
        atomic_commit = store.atomic_commit_v2
    except Exception:
        return _bound_failure_attempt(
            batch.domain_root,
            batch.scope_ref,
            batch.stream_ref,
            batch.transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return atomic_commit(batch)
