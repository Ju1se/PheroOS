from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance._authority_v2 import (
    FAILURE_STAGE_BEFORE_VALIDATION_V2,
)
from pheroos.governance._baseline_output_v2.contracts import (
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
)
from pheroos.governance._baseline_output_v2.operations import (
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.evidence import EvidenceGraph, EvidenceNode
from pheroos.governance.output import OutputContract, output_gate_lineage
from pheroos.governance.quorum import commit_candidate
from pheroos.governance.stop_signal import StopResolution
from tests.governance.test_baseline_output_v2_operations import (
    _all_non_lifecycle_streams,
    _commit_output,
    _context,
    _issue,
    _permission,
    _request,
    _root,
    _verified_signal,
)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("candidate_ref", "candidate:fallback"),
        ("source_ref", "source:substituted"),
        ("provenance_ref", "sha256:" + "7" * 64),
    ],
)
def test_verified_signal_cannot_be_reinterpreted_for_quorum(
    field_name: str,
    replacement: str,
) -> None:
    context = _context(scope_ref=f"scope:baseline-signal-binding:{field_name}")
    signal = _verified_signal(context, label="2a", source_ref="source:alpha")
    substituted = deepcopy(signal)
    substituted[field_name] = replacement

    with pytest.raises(ValueError, match="signal_root does not bind its proposal"):
        _request(context, threshold=1, verified_signals=(substituted,))


def test_manifest_authority_selector_must_match_session_domain_exactly() -> None:
    context = _context(scope_ref="scope:baseline-profile-downgrade")
    request = _request(
        context,
        decision_mode="direct_governance",
        authority_profile="pheroos-scoped-authority-authenticated-v2",
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as denied:
        open_baseline_output_authority_session_v2(
            context.capability,
            request,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        )

    assert denied.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.permission_stream_ref,
        ).revision
        == 0
    )


def test_permission_issuer_requires_explicit_stop_resolution_authority() -> None:
    context = _context(
        scope_ref="scope:baseline-stop-operation",
        operations=(
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
    )
    request = _request(context, decision_mode="direct_governance")

    denied = _issue(context, request)

    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED
    for stream_ref in (
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
    ):
        assert context.store.load_head_v2(request.scope_ref, stream_ref).revision == 0


def test_output_reads_both_grants_and_revoking_permission_issuer_denies_action() -> (
    None
):
    context = _context(scope_ref="scope:baseline-two-grants")
    request = _request(context, decision_mode="direct_governance")
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )

    output_grant = GovernanceIssuerGrantV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        issuer_ref="issuer:output-host",
        grant_ref="grant:output-only",
        grant_binding_ref=_root("6"),
        operations=(GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,),
        target_refs=(request.target_ref,),
        action_refs=(request.action_ref,),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    activation = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        output_grant,
        "transition:grant:output:activate",
        2,
    )
    assert activation.disposition is GovernanceCommitDispositionV2.COMMITTED
    output_capability = bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        output_grant,
        request.run_ref,
        request.observed_epoch,
    )
    output_session = open_baseline_output_authority_session_v2(
        output_capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )

    result = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )

    assert result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    assert result.commit_attempt.committed_transition is not None
    read_streams = {
        entry.stream_ref
        for entry in result.commit_attempt.committed_transition.batch.read_set.entries
    }
    permission_grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        context.grant.grant_ref,
    )
    output_grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref,
        output_grant.grant_ref,
    )
    assert {permission_grant_stream, output_grant_stream} <= read_streams

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:grant:permission:revoke",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    replay = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )
    assert (
        replay.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert replay.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert replay.authorization is None


def test_result_reader_rejects_cross_request_authorization_substitution() -> None:
    first_context = _context(scope_ref="scope:baseline-result-binding:first")
    first_request = _request(first_context, decision_mode="direct_governance")
    assert _issue(first_context, first_request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    result = _commit_output(first_context, first_request)
    assert result.authorization is not None

    other_context = _context(scope_ref="scope:baseline-result-binding:other")
    other_request = _request(other_context, decision_mode="direct_governance")
    assert _issue(other_context, other_request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    substituted = result.to_dict()
    substituted["authorization"] = _permission(
        other_context,
        other_request,
    ).to_dict()

    with pytest.raises(ValueError, match="authorization binding is mismatched"):
        BaselineOutputResultV2.from_dict(substituted)


def test_missing_fake_or_wrong_operation_session_cannot_write() -> None:
    context = _context(scope_ref="scope:baseline-output-fake-session")
    request = _request(context, decision_mode="direct_governance")
    before = context.store.snapshot_v2()

    for fake in (None, object()):
        attempt = issue_action_permission_v2(request, authority_session=fake)
        assert attempt.disposition is GovernanceCommitDispositionV2.DENIED
        assert attempt.failure is not None
        assert (
            attempt.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
        )
        assert context.store.snapshot_v2() == before

    output_session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    wrong_issue = issue_action_permission_v2(
        request,
        authority_session=output_session,
    )
    assert wrong_issue.disposition is GovernanceCommitDispositionV2.INVALID
    assert wrong_issue.failure is not None
    assert (
        wrong_issue.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert context.store.snapshot_v2() == before

    permission_session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    wrong_output = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=permission_session,
    )
    assert wrong_output.disposition is GovernanceCommitDispositionV2.INVALID
    assert wrong_output.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert context.store.snapshot_v2() == before

    with pytest.raises(GovernanceAuthorityBindingErrorV2) as unsupported:
        open_baseline_output_authority_session_v2(
            context.capability,
            request,
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        )
    assert (
        unsupported.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED
    )


def test_session_binds_request_target_action_operation_and_payload_root() -> None:
    context = _context(scope_ref="scope:baseline-output-session-binding")
    original = _request(
        context,
        request_label="original",
        decision_mode="direct_governance",
        payload="payload-original",
    )
    session = open_baseline_output_authority_session_v2(
        context.capability,
        original,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    assert session.target_refs == (original.target_ref,)
    assert session.action_refs == (original.action_ref,)
    assert session.request_root == original.request_root
    assert session.operation is GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION

    substituted = _request(
        context,
        request_label="substituted",
        decision_mode="direct_governance",
        payload="payload-substituted",
    )
    before = context.store.snapshot_v2()
    attempt = issue_action_permission_v2(
        substituted,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempt.failure is not None
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert context.store.snapshot_v2() == before


def test_revoked_grant_denies_uncommitted_permission_without_partial_stages() -> None:
    context = _context(scope_ref="scope:baseline-output-revoked-before")
    request = _request(context, decision_mode="direct_governance")
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:grant:revoke",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED

    denied = issue_action_permission_v2(request, authority_session=session)
    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    for stream_ref in (
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
    ):
        assert context.store.load_head_v2(request.scope_ref, stream_ref).revision == 0


def test_grant_revocation_after_output_preserves_delivery_but_denies_action() -> None:
    context = _context(scope_ref="scope:baseline-output-revoked-after")
    request = _request(context, decision_mode="direct_governance")
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    output_session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    committed = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )
    assert committed.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:grant:revoke",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    replay = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )
    assert replay.position is GovernanceCommitPositionV2.CURRENT
    assert (
        replay.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert replay.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert replay.authorization is None


def test_domain_seal_after_output_preserves_history_but_denies_action() -> None:
    context = _context(scope_ref="scope:baseline-output-sealed")
    request = _request(context, decision_mode="direct_governance")
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    output_session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    assert evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    ).action_disposition is (BaselineOutputActionDispositionV2.AUTHORIZED)
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        request_ref="request:retire",
        transition_id="transition:retire",
        stream_refs=_all_non_lifecycle_streams(context, request),
        reason_ref="reason:completed",
        observed_epoch=2,
    )
    retirement_session = open_governance_authority_session_v2(
        context.capability,
        retirement,
    )
    sealed = retire_governance_domain_v2(
        retirement,
        authority_session=retirement_session,
    )
    assert sealed.disposition is GovernanceCommitDispositionV2.COMMITTED

    replay = evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=output_session,
    )
    assert replay.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert replay.position is GovernanceCommitPositionV2.SEALED
    assert (
        replay.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert replay.action_disposition is BaselineOutputActionDispositionV2.DENIED


def test_dependency_successor_revokes_old_output_actionability() -> None:
    context = _context(scope_ref="scope:baseline-output-dependency-successor")
    first = _request(
        context,
        request_label="first",
        decision_mode="direct_governance",
    )
    assert _issue(context, first).disposition is GovernanceCommitDispositionV2.COMMITTED
    original = _commit_output(context, first)
    assert original.position is GovernanceCommitPositionV2.CURRENT
    assert original.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED

    successor = _request(
        context,
        request_label="dependency-successor",
        decision_mode="direct_governance",
        payload="new-payload",
    )
    assert (
        _issue(context, successor).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert (
        context.store.load_head_v2(
            first.scope_ref,
            first.output_stream_ref,
        ).revision
        == 1
    )

    replay = _commit_output(context, first)
    assert replay.position is GovernanceCommitPositionV2.CURRENT
    assert (
        replay.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert replay.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert replay.authorization is None


def test_output_finality_failure_is_total_and_has_no_prepublication_write() -> None:
    context = _context(scope_ref="scope:baseline-output-finality")
    request = _request(context, decision_mode="direct_governance")
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )

    def fail_output(stage: str, batch: object) -> None:
        if (
            stage == FAILURE_STAGE_BEFORE_VALIDATION_V2
            and getattr(batch, "stream_ref", None) == request.output_stream_ref
        ):
            raise OSError("injected output finality loss")

    context.store._failure_injector = fail_output
    result = _commit_output(context, request)
    assert result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert result.terminal_status is BaselineOutputTerminalStatusV2.FINALITY_UNAVAILABLE
    assert (
        result.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert (
        context.store.load_head_v2(
            request.scope_ref, request.output_stream_ref
        ).revision
        == 0
    )

    context.store._failure_injector = None
    recovered = _commit_output(context, request)
    assert recovered.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert recovered.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED


def test_stale_output_read_set_returns_nonterminal_retry_result() -> None:
    context = _context(scope_ref="scope:baseline-output-retry")
    request = _request(
        context,
        request_label="raced",
        decision_mode="direct_governance",
    )
    successor = _request(
        context,
        request_label="racer",
        decision_mode="direct_governance",
        payload="racer-payload",
    )
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    raced = False
    atomic_commit = context.store.atomic_commit_v2

    def advance_dependency(batch: object):  # type: ignore[no-untyped-def]
        nonlocal raced
        if (
            not raced
            and getattr(batch, "stream_ref", None) == request.output_stream_ref
        ):
            raced = True
            assert _issue(context, successor).disposition is (
                GovernanceCommitDispositionV2.COMMITTED
            )
        return atomic_commit(batch)  # type: ignore[arg-type]

    context.store.atomic_commit_v2 = advance_dependency  # type: ignore[method-assign]
    result = _commit_output(context, request)
    context.store.atomic_commit_v2 = atomic_commit  # type: ignore[method-assign]

    assert raced is True
    assert result.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert (
        result.delivery_disposition
        is BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED
    )
    assert result.terminal_status is None
    assert result.candidate_ref is None
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert result.authorization is None
    assert (
        context.store.load_head_v2(
            request.scope_ref, request.output_stream_ref
        ).revision
        == 0
    )


def test_legacy_v1_output_boolean_signature_and_behavior_are_unchanged() -> None:
    signature = inspect.signature(output_gate_lineage)
    assert "publication_permission" in signature.parameters
    assert signature.parameters["publication_permission"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    candidates = CandidateSet([Candidate("candidate:accept", "target:legacy")])
    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:accept",
        target="target:legacy",
    )
    evidence = EvidenceGraph(
        [EvidenceNode("evidence:legacy", "legacy claim", "urn:legacy:source")]
    )
    stops = [StopResolution("target:legacy", "publish", blocked=False)]

    allowed = output_gate_lineage(
        OutputContract(),
        decision,
        evidence,
        stops,
        publication_permission=True,
        candidate_set=candidates,
    )
    denied = output_gate_lineage(
        OutputContract(),
        decision,
        evidence,
        stops,
        publication_permission=False,
        candidate_set=candidates,
    )
    assert allowed == {
        "committed_candidate": True,
        "evidence_provenance": True,
        "stop_resolution": True,
        "publication_permission": True,
    }
    assert denied == {**allowed, "publication_permission": False}
