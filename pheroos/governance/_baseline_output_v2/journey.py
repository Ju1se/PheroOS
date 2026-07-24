"""High-level portable-input Baseline Output v2 write journey.

This composition keeps the store-bound capability and request-bound sessions
inside Governance.  Callers provide only versioned contracts and receive only
portable commit attempts or the portable terminal output result.
"""

from __future__ import annotations

from collections.abc import Mapping

from pheroos.protocol import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.operations import (
    _bound_failure_attempt,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    GovernanceFailureStageV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerifierV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    open_governance_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance._baseline_output_v2.contracts import (
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
)
from pheroos.governance._baseline_output_v2.operations import (
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
)


def evaluate_and_commit_governed_baseline_output_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    activation_transition_id: str,
    activation_observed_epoch: int,
    request: BaselineOutputRequestV2,
    *,
    verified_signal_requests: tuple[GovernanceVerifiedSignalRequestV2, ...] = (),
    verifier: IssuerGrantVerifierV2 | None = None,
) -> GovernanceCommitAttemptV2 | BaselineOutputResultV2:
    """Run the complete Governance-owned baseline write path.

    ``activation_transition_id`` and ``activation_observed_epoch`` describe the
    grant-lifecycle request and must remain unchanged on exact retry.  The
    output request's own epoch may be later.  Opaque capability/session objects
    never cross this boundary.
    """

    _require_exact_request(request)
    if type(verified_signal_requests) is not tuple:
        raise TypeError("verified_signal_requests must be an exact tuple")
    request_mismatch = _request_binding_mismatch(request, domain, grant)
    if request_mismatch is not None:
        return _journey_failure_code(
            request,
            request.permission_stream_ref,
            request.permission_transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            f"/request/{request_mismatch}",
        )
    if (
        type(activation_observed_epoch) is int
        and activation_observed_epoch > request.observed_epoch
    ):
        return _journey_failure_code(
            request,
            request.permission_stream_ref,
            request.permission_transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/activation_observed_epoch",
        )
    if len(verified_signal_requests) != len(request.verified_signals):
        return _journey_failure_code(
            request,
            request.permission_stream_ref,
            request.permission_transition_id,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/verified_signal_requests",
        )
    for index, (signal_request, proposal) in enumerate(
        zip(verified_signal_requests, request.verified_signals, strict=True)
    ):
        if type(signal_request) is not GovernanceVerifiedSignalRequestV2:
            return _journey_failure_code(
                request,
                request.permission_stream_ref,
                request.permission_transition_id,
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                f"/verified_signal_requests/{index}",
            )
        mismatch = _signal_binding_mismatch(
            signal_request,
            proposal,
            request,
            grant,
        )
        if mismatch is not None:
            return _journey_failure_code(
                request,
                signal_request.stream_ref,
                signal_request.transition_id,
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                f"/verified_signal_requests/{index}/{mismatch}",
            )

    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        activation_transition_id,
        activation_observed_epoch,
        verifier,
    )
    if activation.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        return activation

    try:
        capability = bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            request.run_ref,
            request.observed_epoch,
            verifier,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _journey_failure(
            request,
            request.permission_stream_ref,
            request.permission_transition_id,
            exc,
        )

    for signal_request in verified_signal_requests:
        try:
            signal_session = open_governance_authority_session_v2(
                capability,
                signal_request,
            )
        except GovernanceAuthorityBindingErrorV2 as exc:
            return _journey_failure(
                request,
                signal_request.stream_ref,
                signal_request.transition_id,
                exc,
            )
        signal_attempt = commit_verified_signal_v2(
            signal_request,
            authority_session=signal_session,
        )
        if signal_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
            return signal_attempt

    try:
        permission_session = open_baseline_output_authority_session_v2(
            capability,
            request,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _journey_failure(
            request,
            request.permission_stream_ref,
            request.permission_transition_id,
            exc,
        )
    permission_attempt = issue_action_permission_v2(
        request,
        authority_session=permission_session,
    )
    if permission_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        return permission_attempt

    try:
        output_session = open_baseline_output_authority_session_v2(
            capability,
            request,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _journey_failure(
            request,
            request.output_stream_ref,
            request.output_transition_id,
            exc,
        )
    return evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )


def _require_exact_request(request: object) -> None:
    if type(request) is not BaselineOutputRequestV2:
        raise TypeError("governed baseline output requires its exact request type")


def _request_binding_mismatch(
    request: BaselineOutputRequestV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
) -> str | None:
    expected = (
        ("domain_root", domain.domain_root),
        ("scope_ref", domain.scope_ref),
    )
    for field, value in expected:
        if getattr(request, field) != value:
            return field
    if grant.domain_root != request.domain_root or grant.scope_ref != request.scope_ref:
        return "grant"
    return None


def _signal_binding_mismatch(
    signal_request: GovernanceVerifiedSignalRequestV2,
    proposal: Mapping[str, object],
    request: BaselineOutputRequestV2,
    grant: GovernanceIssuerGrantV2,
) -> str | None:
    if signal_request.status != "verified":
        return "status"
    expected = (
        ("domain_root", request.domain_root),
        ("scope_ref", request.scope_ref),
        ("run_ref", request.run_ref),
        ("observed_epoch", request.observed_epoch),
        ("target_ref", request.target_ref),
    )
    for field, value in expected:
        if getattr(signal_request, field) != value:
            return field
    if (
        signal_request.domain_root != grant.domain_root
        or signal_request.scope_ref != grant.scope_ref
        or signal_request.target_ref not in grant.target_refs
    ):
        return "grant"
    if (
        proposal["signal_ref"] != signal_request.signal_ref
        or proposal["signal_transition_id"] != signal_request.transition_id
        or proposal["signal_root"] != signal_request.signal_root
        or proposal["evidence_root"] != signal_request.evidence_root
    ):
        return "baseline_request"
    return None


def _journey_failure(
    request: BaselineOutputRequestV2,
    stream_ref: str,
    transition_id: str,
    error: GovernanceAuthorityBindingErrorV2,
) -> GovernanceCommitAttemptV2:
    return _journey_failure_code(
        request,
        stream_ref,
        transition_id,
        error.code,
        error.path,
    )


def _journey_failure_code(
    request: BaselineOutputRequestV2,
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
        GovernanceFailureStageV2.PRECONDITION,
    )


__all__ = ["evaluate_and_commit_governed_baseline_output_v2"]
