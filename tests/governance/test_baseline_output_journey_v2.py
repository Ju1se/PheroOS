from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from typing import Any

from pheroos.conformance import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
    build_runtime_integration_request_v1,
)
from pheroos.governance import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    GovernanceCommitBatchV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceStateStoreV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
    baseline_verified_signal_proposal_root_v2,
    evaluate_and_commit_governed_baseline_output_v2,
    recover_baseline_output_result_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.conformance.runtime_integration import RuntimeTranscriptRequestV1


ROOT = Path(__file__).resolve().parents[2]


def _fixture(
    label: str,
    *,
    terminal: str = "evidence_commit",
) -> tuple[
    ReferenceGovernanceStateStoreConformanceAdapterV2,
    object,
    object,
]:
    transcript = build_runtime_integration_request_v1(label, terminal=terminal)
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    store = adapter.create_store_v2((transcript.authority_domain,))
    return adapter, store, transcript


def _journey(store: object, transcript: object) -> object:
    baseline = transcript.baseline_request
    assert baseline is not None
    return evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        f"transition:activate:{transcript.scenario_id}",
        1,
        baseline,
        verified_signal_requests=transcript.verified_signal_requests,
    )


class _Verifier:
    def __init__(self, *, accepted: bool = True, wrong_root: bool = False) -> None:
        self._accepted = accepted
        self._wrong_root = wrong_root

    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2:
        return IssuerGrantVerificationV2(
            grant_root=("sha256:" + "f" * 64 if self._wrong_root else grant.grant_root),
            grant_binding_ref=grant.grant_binding_ref,
            verifier_ref="verifier:test",
            accepted=self._accepted,
            verified_epoch=observed_epoch,
        )


class _FailOnceOutputStore:
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        output_transition_id: str,
    ) -> None:
        self._store = store
        self._output_transition_id = output_transition_id
        self._failed = False

    @property
    def state_store_version(self) -> str:
        return self._store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self._store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self._store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        return self._store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        if batch.transition_id == self._output_transition_id and self._failed is False:
            self._failed = True
            failure = GovernanceFailureV2(
                code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                path="/read_set",
                stage=GovernanceFailureStageV2.COMMIT,
            )
            return GovernanceCommitAttemptV2(
                domain_root=batch.domain_root,
                scope_ref=batch.scope_ref,
                stream_ref=batch.stream_ref,
                transition_id=batch.transition_id,
                disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
                failure=failure,
                committed_transition=None,
                position_observation=None,
            )
        return self._store.atomic_commit_v2(batch)


def _authenticated_material(
    transcript: RuntimeTranscriptRequestV1,
) -> tuple[
    AuthorityDomainV2,
    GovernanceIssuerGrantV2,
    BaselineOutputRequestV2,
    tuple[GovernanceVerifiedSignalRequestV2, ...],
]:
    baseline = transcript.baseline_request
    assert baseline is not None
    domain = replace(
        transcript.authority_domain,
        profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
        domain_root="",
    )
    grant = replace(
        transcript.issuer_grant,
        domain_root=domain.domain_root,
        grant_root="",
    )
    policy = replace(
        baseline.manifest.authority_policy,
        profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
    )
    manifest = replace(baseline.manifest, authority_policy=policy)
    proposals: list[dict[str, object]] = []
    signal_requests: list[GovernanceVerifiedSignalRequestV2] = []
    for signal_request, proposal in zip(
        transcript.verified_signal_requests,
        baseline.verified_signals,
        strict=True,
    ):
        signal_root = baseline_verified_signal_proposal_root_v2(
            domain_root=domain.domain_root,
            scope_ref=baseline.scope_ref,
            run_ref=baseline.run_ref,
            target_ref=baseline.target_ref,
            candidate_ref=proposal["candidate_ref"],
            signal_ref=signal_request.signal_ref,
            evidence_root=signal_request.evidence_root,
            provenance_ref=proposal["provenance_ref"],
            source_ref=proposal["source_ref"],
        )
        signal_requests.append(
            replace(
                signal_request,
                domain_root=domain.domain_root,
                signal_root=signal_root,
                request_root="",
            )
        )
        proposals.append(
            {
                **dict(proposal),
                "signal_root": signal_root,
            }
        )
    request = replace(
        baseline,
        domain_root=domain.domain_root,
        manifest=manifest,
        verified_signals=tuple(proposals),
        manifest_stream_ref="",
        evidence_stream_ref="",
        stop_stream_ref="",
        decision_stream_ref="",
        permission_stream_ref="",
        output_stream_ref="",
        output_payload_root="",
        request_root="",
    )
    return domain, grant, request, tuple(signal_requests)


def test_complete_write_journey_exact_retry_restart_and_recovery() -> None:
    adapter, store, transcript = _fixture("stable-write-success")
    baseline = transcript.baseline_request
    assert baseline is not None

    first = _journey(store, transcript)
    assert isinstance(first, BaselineOutputResultV2)
    assert first.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert first.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    assert first.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    assert first.authorization is not None
    before_retry = adapter.observe_store_v2(store, baseline.scope_ref)

    exact_retry = _journey(store, transcript)
    assert isinstance(exact_retry, BaselineOutputResultV2)
    assert exact_retry.result_root == first.result_root
    assert exact_retry.to_dict() == first.to_dict()
    after_retry = adapter.observe_store_v2(store, baseline.scope_ref)
    assert after_retry["commit_order"] == before_retry["commit_order"]
    assert after_retry["trace_batches"] == before_retry["trace_batches"]
    assert after_retry["receipts"] == before_retry["receipts"]

    restarted = adapter.restart_store_v2(store)
    restart_retry = _journey(restarted, transcript)
    assert isinstance(restart_retry, BaselineOutputResultV2)
    assert restart_retry.result_root == first.result_root

    recovered = recover_baseline_output_result_v2(
        baseline,
        state_reader=restarted,
    )
    assert recovered.result_root == first.result_root
    assert recovered.authorization is not None


def test_authenticated_profile_requires_and_rechecks_host_verifier() -> None:
    transcript = build_runtime_integration_request_v1("stable-write-authenticated")
    domain, grant, request, signals = _authenticated_material(transcript)
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()

    missing_store = adapter.create_store_v2((domain,))
    missing = evaluate_and_commit_governed_baseline_output_v2(
        missing_store,
        domain,
        grant,
        "transition:activate:stable-write-authenticated",
        1,
        request,
        verified_signal_requests=signals,
    )
    assert isinstance(missing, GovernanceCommitAttemptV2)
    assert missing.failure is not None
    assert missing.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED

    bad_store = adapter.create_store_v2((domain,))
    bad = evaluate_and_commit_governed_baseline_output_v2(
        bad_store,
        domain,
        grant,
        "transition:activate:stable-write-authenticated",
        1,
        request,
        verified_signal_requests=signals,
        verifier=_Verifier(wrong_root=True),
    )
    assert isinstance(bad, GovernanceCommitAttemptV2)
    assert bad.failure is not None
    assert bad.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED

    store = adapter.create_store_v2((domain,))
    committed = evaluate_and_commit_governed_baseline_output_v2(
        store,
        domain,
        grant,
        "transition:activate:stable-write-authenticated",
        1,
        request,
        verified_signal_requests=signals,
        verifier=_Verifier(),
    )
    assert isinstance(committed, BaselineOutputResultV2)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED

    local_transcript = build_runtime_integration_request_v1("stable-write-local")
    local_adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    local_store = local_adapter.create_store_v2((local_transcript.authority_domain,))
    local = evaluate_and_commit_governed_baseline_output_v2(
        local_store,
        local_transcript.authority_domain,
        local_transcript.issuer_grant,
        "transition:activate:stable-write-local",
        1,
        local_transcript.baseline_request,
        verified_signal_requests=local_transcript.verified_signal_requests,
        verifier=_Verifier(),
    )
    assert isinstance(local, GovernanceCommitAttemptV2)
    assert local.failure is not None
    assert local.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED


def test_revoked_and_expired_grants_return_portable_denials() -> None:
    _, store, transcript = _fixture("stable-write-revoked")
    committed = _journey(store, transcript)
    assert isinstance(committed, BaselineOutputResultV2)

    revoked = revoke_governance_issuer_grant_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant.grant_ref,
        "transition:revoke:stable-write",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    denied = _journey(store, transcript)
    assert isinstance(denied, GovernanceCommitAttemptV2)
    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    assert denied.committed_transition is None

    _, expired_store, expired_transcript = _fixture("stable-write-expired")
    baseline = expired_transcript.baseline_request
    signal = expired_transcript.verified_signal_requests[0]
    assert baseline is not None
    expired_baseline = replace(baseline, observed_epoch=101, request_root="")
    expired_signal = replace(signal, observed_epoch=101, request_root="")
    expired = evaluate_and_commit_governed_baseline_output_v2(
        expired_store,
        expired_transcript.authority_domain,
        expired_transcript.issuer_grant,
        "transition:activate:stable-write-expired",
        1,
        expired_baseline,
        verified_signal_requests=(expired_signal,),
    )
    assert isinstance(expired, GovernanceCommitAttemptV2)
    assert expired.disposition is GovernanceCommitDispositionV2.DENIED
    assert expired.failure is not None
    assert expired.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED


def test_successor_revokes_current_actionability_without_erasing_history() -> None:
    adapter, store, transcript = _fixture("stable-write-currentness")
    baseline = transcript.baseline_request
    assert baseline is not None
    original = _journey(store, transcript)
    assert isinstance(original, BaselineOutputResultV2)
    assert original.authorization is not None

    successor = replace(
        baseline,
        request_ref="request:output:stable-write-currentness:successor",
        output_transition_id="transition:output:stable-write-currentness:successor",
        output_payload={"answer": "successor"},
        manifest_stream_ref="",
        evidence_stream_ref="",
        stop_stream_ref="",
        decision_stream_ref="",
        permission_stream_ref="",
        output_stream_ref="",
        output_payload_root="",
        request_root="",
    )
    successor_result = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-currentness",
        1,
        successor,
        verified_signal_requests=transcript.verified_signal_requests,
    )
    assert isinstance(successor_result, BaselineOutputResultV2)
    assert successor_result.disposition is GovernanceCommitDispositionV2.COMMITTED

    restarted = adapter.restart_store_v2(store)
    historical = recover_baseline_output_result_v2(
        baseline,
        state_reader=restarted,
    )
    assert (
        historical.delivery_disposition
        is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert historical.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert historical.authorization is None


def test_publish_denied_and_signal_mismatch_are_total_portable_results() -> None:
    _, blocked_store, blocked_transcript = _fixture(
        "stable-write-blocked",
        terminal="blocked",
    )
    blocked = _journey(blocked_store, blocked_transcript)
    assert isinstance(blocked, BaselineOutputResultV2)
    assert (
        blocked.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert blocked.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert blocked.authorization is None

    _, mismatch_store, mismatch_transcript = _fixture("stable-write-mismatch")
    baseline = mismatch_transcript.baseline_request
    signal = mismatch_transcript.verified_signal_requests[0]
    assert baseline is not None
    mismatched_signal = replace(
        signal,
        run_ref="run:mismatched",
        request_root="",
    )
    mismatched = evaluate_and_commit_governed_baseline_output_v2(
        mismatch_store,
        mismatch_transcript.authority_domain,
        mismatch_transcript.issuer_grant,
        "transition:activate:stable-write-mismatch",
        1,
        baseline,
        verified_signal_requests=(mismatched_signal,),
    )
    assert isinstance(mismatched, GovernanceCommitAttemptV2)
    assert mismatched.disposition is GovernanceCommitDispositionV2.INVALID
    assert mismatched.failure is not None
    assert (
        mismatched.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert mismatched.committed_transition is None


def test_signal_set_missing_extra_and_order_mismatches_fail_before_activation() -> None:
    adapter, store, transcript = _fixture("stable-write-signal-set")
    baseline = transcript.baseline_request
    signal = transcript.verified_signal_requests[0]
    assert baseline is not None

    missing = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-signal-set",
        1,
        baseline,
        verified_signal_requests=(),
    )
    assert isinstance(missing, GovernanceCommitAttemptV2)
    assert missing.disposition is GovernanceCommitDispositionV2.INVALID
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0

    extra = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-signal-set",
        1,
        baseline,
        verified_signal_requests=(signal, signal),
    )
    assert isinstance(extra, GovernanceCommitAttemptV2)
    assert extra.disposition is GovernanceCommitDispositionV2.INVALID
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0

    first_proposal = dict(baseline.verified_signals[0])
    second_signal_ref = "signal:stable-write-signal-set:second"
    second_source = "source:stable-write-signal-set:second"
    second_provenance = first_proposal["provenance_ref"]
    second_root = baseline_verified_signal_proposal_root_v2(
        domain_root=baseline.domain_root,
        scope_ref=baseline.scope_ref,
        run_ref=baseline.run_ref,
        target_ref=baseline.target_ref,
        candidate_ref=first_proposal["candidate_ref"],
        signal_ref=second_signal_ref,
        evidence_root=first_proposal["evidence_root"],
        provenance_ref=second_provenance,
        source_ref=second_source,
    )
    second_request = replace(
        signal,
        request_ref="request:signal:stable-write-signal-set:second",
        transition_id="transition:signal:stable-write-signal-set:second",
        signal_ref=second_signal_ref,
        signal_root=second_root,
        stream_ref="",
        request_root="",
    )
    second_proposal = {
        **first_proposal,
        "signal_ref": second_signal_ref,
        "signal_root": second_root,
        "signal_transition_id": second_request.transition_id,
        "source_ref": second_source,
    }
    proposals = tuple(
        sorted(
            (first_proposal, second_proposal),
            key=lambda item: (
                str(item["source_ref"]).encode("utf-8"),
                str(item["signal_ref"]).encode("utf-8"),
            ),
        )
    )
    requests_by_signal = {
        signal.signal_ref: signal,
        second_request.signal_ref: second_request,
    }
    ordered_requests = tuple(
        requests_by_signal[str(proposal["signal_ref"])] for proposal in proposals
    )
    two_signal_baseline = replace(
        baseline,
        verified_signals=proposals,
        request_root="",
    )
    reversed_order = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-signal-set",
        1,
        two_signal_baseline,
        verified_signal_requests=tuple(reversed(ordered_requests)),
    )
    assert isinstance(reversed_order, GovernanceCommitAttemptV2)
    assert reversed_order.disposition is GovernanceCommitDispositionV2.INVALID
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0


def test_output_retry_after_permission_preserves_prerequisites_and_recovers() -> None:
    adapter, inner, transcript = _fixture("stable-write-output-retry")
    baseline = transcript.baseline_request
    assert baseline is not None
    store = _FailOnceOutputStore(inner, baseline.output_transition_id)

    retry = _journey(store, transcript)
    assert isinstance(retry, BaselineOutputResultV2)
    assert retry.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert retry.authorization is None
    after_retry = adapter.observe_store_v2(inner, baseline.scope_ref)
    assert baseline.permission_transition_id in after_retry["commit_order"]
    assert baseline.output_transition_id not in after_retry["commit_order"]

    restarted = adapter.restart_store_v2(inner)
    committed = _journey(restarted, transcript)
    assert isinstance(committed, BaselineOutputResultV2)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert committed.authorization is not None
    after_commit = adapter.observe_store_v2(restarted, baseline.scope_ref)
    assert after_commit["commit_order"].count(baseline.permission_transition_id) == 1
    assert after_commit["commit_order"].count(baseline.output_transition_id) == 1


def test_exact_type_and_request_grant_preflight_boundaries() -> None:
    adapter, store, transcript = _fixture("stable-write-preflight")
    baseline = transcript.baseline_request
    assert baseline is not None

    try:
        evaluate_and_commit_governed_baseline_output_v2(
            store,
            transcript.authority_domain,
            transcript.issuer_grant,
            "transition:activate:stable-write-preflight",
            1,
            object(),  # type: ignore[arg-type]
        )
    except TypeError:
        pass
    else:
        raise AssertionError("non-request input did not fail its type boundary")

    try:
        evaluate_and_commit_governed_baseline_output_v2(
            store,
            transcript.authority_domain,
            transcript.issuer_grant,
            "transition:activate:stable-write-preflight",
            1,
            baseline,
            verified_signal_requests=[],  # type: ignore[arg-type]
        )
    except TypeError:
        pass
    else:
        raise AssertionError("non-tuple signal input did not fail its type boundary")

    other = build_runtime_integration_request_v1("stable-write-preflight-other")
    request_mismatch = evaluate_and_commit_governed_baseline_output_v2(
        store,
        other.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-preflight",
        1,
        baseline,
        verified_signal_requests=transcript.verified_signal_requests,
    )
    assert isinstance(request_mismatch, GovernanceCommitAttemptV2)
    assert request_mismatch.disposition is GovernanceCommitDispositionV2.INVALID

    grant_mismatch = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        other.issuer_grant,
        "transition:activate:stable-write-preflight",
        1,
        baseline,
        verified_signal_requests=transcript.verified_signal_requests,
    )
    assert isinstance(grant_mismatch, GovernanceCommitAttemptV2)
    assert grant_mismatch.disposition is GovernanceCommitDispositionV2.INVALID

    non_request_signal = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-preflight",
        1,
        baseline,
        verified_signal_requests=(object(),),  # type: ignore[arg-type]
    )
    assert isinstance(non_request_signal, GovernanceCommitAttemptV2)
    assert non_request_signal.disposition is GovernanceCommitDispositionV2.INVALID
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0

    future_activation = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-preflight",
        3,
        baseline,
        verified_signal_requests=transcript.verified_signal_requests,
    )
    assert isinstance(future_activation, GovernanceCommitAttemptV2)
    assert future_activation.disposition is GovernanceCommitDispositionV2.INVALID
    assert future_activation.failure is not None
    assert (
        future_activation.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert future_activation.failure.path == "/activation_observed_epoch"
    assert future_activation.committed_transition is None
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0


def test_each_internal_session_and_commit_stage_fails_closed() -> None:
    stages = (
        (
            "signal-open",
            (
                GovernanceIssuerOperationV2.EVALUATE_QUORUM,
                GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
                GovernanceIssuerOperationV2.RESOLVE_STOP,
                GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
                GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
            ),
            "verified",
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        ),
        (
            "permission-open",
            (
                GovernanceIssuerOperationV2.VERIFY_SIGNAL,
                GovernanceIssuerOperationV2.EVALUATE_QUORUM,
                GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
                GovernanceIssuerOperationV2.RESOLVE_STOP,
                GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
            ),
            "verified",
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        ),
        (
            "permission-commit",
            (
                GovernanceIssuerOperationV2.VERIFY_SIGNAL,
                GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
                GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
            ),
            "verified",
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        ),
        (
            "output-open",
            (
                GovernanceIssuerOperationV2.VERIFY_SIGNAL,
                GovernanceIssuerOperationV2.EVALUATE_QUORUM,
                GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
                GovernanceIssuerOperationV2.RESOLVE_STOP,
                GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            ),
            "verified",
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        ),
    )
    for label, operations, signal_status, expected_code in stages:
        adapter, store, transcript = _fixture(f"stable-write-{label}")
        baseline = transcript.baseline_request
        assert baseline is not None
        grant = replace(
            transcript.issuer_grant,
            operations=operations,
            grant_root="",
        )
        signal = replace(
            transcript.verified_signal_requests[0],
            status=signal_status,
            request_root="",
        )
        attempted = evaluate_and_commit_governed_baseline_output_v2(
            store,
            transcript.authority_domain,
            grant,
            f"transition:activate:stable-write-{label}",
            1,
            baseline,
            verified_signal_requests=(signal,),
        )
        assert isinstance(attempted, GovernanceCommitAttemptV2)
        assert attempted.failure is not None
        assert attempted.failure.code is expected_code
        assert attempted.committed_transition is None
        observation = adapter.observe_store_v2(store, baseline.scope_ref)
        assert baseline.output_transition_id not in observation["commit_order"]


def test_signal_target_must_be_in_the_exact_grant_bounds() -> None:
    adapter, store, transcript = _fixture("stable-write-signal-grant")
    baseline = transcript.baseline_request
    assert baseline is not None
    grant = replace(
        transcript.issuer_grant,
        target_refs=("decision:other",),
        grant_root="",
    )
    attempted = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        grant,
        "transition:activate:stable-write-signal-grant",
        1,
        baseline,
        verified_signal_requests=transcript.verified_signal_requests,
    )
    assert isinstance(attempted, GovernanceCommitAttemptV2)
    assert attempted.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempted.failure is not None
    assert (
        attempted.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0


def test_rejected_verified_set_input_fails_before_any_store_mutation() -> None:
    adapter, store, transcript = _fixture("stable-write-rejected-signal")
    baseline = transcript.baseline_request
    assert baseline is not None
    rejected = replace(
        transcript.verified_signal_requests[0],
        status="rejected",
        request_root="",
    )
    attempted = evaluate_and_commit_governed_baseline_output_v2(
        store,
        transcript.authority_domain,
        transcript.issuer_grant,
        "transition:activate:stable-write-rejected-signal",
        1,
        baseline,
        verified_signal_requests=(rejected,),
    )
    assert isinstance(attempted, GovernanceCommitAttemptV2)
    assert attempted.disposition is GovernanceCommitDispositionV2.INVALID
    assert attempted.failure is not None
    assert attempted.failure.path == "/verified_signal_requests/0/status"
    assert attempted.committed_transition is None
    assert adapter.observe_store_v2(store, baseline.scope_ref)["receipts"] == 0


def test_signal_commit_retry_stops_before_permission_and_output() -> None:
    adapter, inner, transcript = _fixture("stable-write-signal-retry")
    baseline = transcript.baseline_request
    signal = transcript.verified_signal_requests[0]
    assert baseline is not None
    store = _FailOnceOutputStore(inner, signal.transition_id)
    attempted = _journey(store, transcript)
    assert isinstance(attempted, GovernanceCommitAttemptV2)
    assert attempted.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    observation = adapter.observe_store_v2(inner, baseline.scope_ref)
    assert signal.transition_id not in observation["commit_order"]
    assert baseline.permission_transition_id not in observation["commit_order"]
    assert baseline.output_transition_id not in observation["commit_order"]


def test_private_journey_owner_is_import_order_independent_and_acyclic() -> None:
    script = """
import importlib
private = importlib.import_module("pheroos.governance._baseline_output_v2.journey")
facade = importlib.import_module("pheroos.governance.baseline_output_v2")
root = importlib.import_module("pheroos.governance")
assert private.evaluate_and_commit_governed_baseline_output_v2 is facade.evaluate_and_commit_governed_baseline_output_v2
assert root.evaluate_and_commit_governed_baseline_output_v2 is facade.evaluate_and_commit_governed_baseline_output_v2
assert facade.evaluate_and_commit_governed_baseline_output_v2.__module__ == "pheroos.governance.baseline_output_v2"
try:
    importlib.import_module("pheroos.governance.baseline_output_journey_v2")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("removed public implementation module still imports")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    path = ROOT / "pheroos" / "governance" / "_baseline_output_v2" / "journey.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "pheroos.governance" not in imported_modules
    assert "pheroos.governance.baseline_output_v2" not in imported_modules
