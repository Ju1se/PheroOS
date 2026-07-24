from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    governance_issuer_grant_stream_ref_v2,
    governance_verified_signal_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    open_governance_authority_session_v2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance._baseline_output_v2.contracts import (
    ActionPermissionDispositionV2,
    ActionPermissionV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    BaselineOutputTerminalStatusV2,
    baseline_verified_signal_proposal_root_v2,
)
from pheroos.governance._baseline_output_v2.operations import (
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
)
from tests.governance.test_baseline_output_v2_contracts import _manifest, _root


@dataclass(frozen=True)
class _Context:
    domain: AuthorityDomainV2
    store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


def _context(
    *,
    scope_ref: str = "scope:baseline-output-operations",
    operations: tuple[GovernanceIssuerOperationV2, ...] | None = None,
) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:trusted-host",
        grant_ref="grant:baseline-output",
        grant_binding_ref=_root("1"),
        operations=operations
        or (
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=("target:answer",),
        action_refs=("action:publish",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    store = InMemoryGovernanceStateStoreV2((domain,))
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant:activate",
        1,
    )
    assert activation.disposition is GovernanceCommitDispositionV2.COMMITTED
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        2,
    )
    return _Context(domain=domain, store=store, grant=grant, capability=capability)


def _verified_signal(
    context: _Context,
    *,
    label: str,
    candidate_ref: str = "candidate:accept",
    source_ref: str | None = None,
) -> dict[str, str]:
    signal_ref = f"signal:{label}"
    transition_id = f"transition:signal:{label}"
    evidence_root = _root(label[-1])
    provenance_ref = _root("9")
    resolved_source_ref = source_ref or f"source:{label}"
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        target_ref="target:answer",
        candidate_ref=candidate_ref,
        signal_ref=signal_ref,
        evidence_root=evidence_root,
        provenance_ref=provenance_ref,
        source_ref=resolved_source_ref,
    )
    request = GovernanceVerifiedSignalRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        request_ref=f"request:signal:{label}",
        transition_id=transition_id,
        signal_ref=signal_ref,
        target_ref="target:answer",
        signal_root=signal_root,
        evidence_root=evidence_root,
        status="verified",
        observed_epoch=2,
    )
    session = open_governance_authority_session_v2(context.capability, request)
    attempt = commit_verified_signal_v2(request, authority_session=session)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return {
        "candidate_ref": candidate_ref,
        "evidence_root": evidence_root,
        "provenance_ref": provenance_ref,
        "signal_ref": signal_ref,
        "signal_root": signal_root,
        "signal_transition_id": transition_id,
        "source_ref": resolved_source_ref,
    }


def _request(
    context: _Context,
    *,
    request_label: str = "one",
    decision_mode: str = "quorum",
    threshold: int = 2,
    verified_signals: tuple[dict[str, str], ...] | None = None,
    blocked: bool = False,
    allowed_outcomes: tuple[str, ...] = ("evidence_commit", "safe_fallback"),
    payload: str = "answer-one",
    authority_profile: str = "pheroos-scoped-authority-local-v2",
) -> BaselineOutputRequestV2:
    if verified_signals is None:
        verified_signals = (
            (
                _verified_signal(
                    context,
                    label=sha256(request_label.encode("utf-8")).hexdigest()[:8],
                    candidate_ref="candidate:accept",
                    source_ref=f"source:direct:{request_label}",
                ),
            )
            if decision_mode == "direct_governance"
            else ()
        )
    sorted_signals = tuple(
        sorted(
            verified_signals,
            key=lambda item: (
                item["source_ref"].encode("utf-8"),
                item["signal_ref"].encode("utf-8"),
            ),
        )
    )
    return BaselineOutputRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:one",
        request_ref=f"request:output:{request_label}",
        output_transition_id=f"transition:output:{request_label}",
        manifest=_manifest(
            decision_mode=decision_mode,
            threshold=threshold,
            allowed_outcomes=allowed_outcomes,
            authority_profile=authority_profile,
        ),
        target_ref="target:answer",
        action_ref="action:publish",
        proposed_candidate_ref=(
            "candidate:accept" if decision_mode == "direct_governance" else None
        ),
        verified_signals=sorted_signals,
        stop_resolutions=(
            {
                "action_ref": "action:publish",
                "blocked": blocked,
                "provenance_ref": _root("8"),
                "reason_ref": "reason:blocked" if blocked else "reason:clear",
            },
        ),
        output_payload={"answer": payload},
        observed_epoch=2,
    )


def _issue(context: _Context, request: BaselineOutputRequestV2):  # type: ignore[no-untyped-def]
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    return issue_action_permission_v2(request, authority_session=session)


def _commit_output(context: _Context, request: BaselineOutputRequestV2):  # type: ignore[no-untyped-def]
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    return evaluate_and_commit_baseline_output_v2(
        request,
        authority_session=session,
    )


def _permission(
    context: _Context, request: BaselineOutputRequestV2
) -> ActionPermissionV2:
    state = context.store.load_state_v2(
        request.scope_ref,
        request.permission_stream_ref,
    )
    return ActionPermissionV2.from_dict(state["permission"])


def test_quorum_vertical_slice_computes_permission_and_commits_full_read_set() -> None:
    context = _context()
    signals = (
        _verified_signal(context, label="2a", source_ref="source:alpha"),
        _verified_signal(context, label="3b", source_ref="source:beta"),
    )
    request = _request(context, verified_signals=signals)

    permission_attempt = _issue(context, request)
    assert permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert permission_attempt.position_observation is not None
    assert (
        permission_attempt.position_observation.position
        is GovernanceCommitPositionV2.CURRENT
    )
    permission = _permission(context, request)
    assert permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
    assert permission.terminal_status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
    assert permission.candidate_ref == "candidate:accept"
    assert permission.output_payload_root == request.output_payload_root

    assert permission_attempt.committed_transition is not None
    permission_entries = {
        item.stream_ref
        for item in permission_attempt.committed_transition.batch.read_set.entries
    }
    assert permission_entries == {
        request.permission_stream_ref,
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref,
            context.grant.grant_ref,
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert (
        permission_attempt.committed_transition.batch.trace_batch.events[0].event_type
        == "baseline_action_permission_issued"
    )

    result = _commit_output(context, request)
    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert result.position is GovernanceCommitPositionV2.CURRENT
    assert result.terminal_status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
    assert result.candidate_ref == "candidate:accept"
    assert (
        result.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    assert result.authorization == permission
    assert result.commit_attempt.committed_transition is not None
    output_batch = result.commit_attempt.committed_transition.batch
    assert {item.stream_ref for item in output_batch.read_set.entries} == {
        request.output_stream_ref,
        request.manifest_stream_ref,
        request.evidence_stream_ref,
        request.stop_stream_ref,
        request.decision_stream_ref,
        request.permission_stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref,
            context.grant.grant_ref,
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert output_batch.trace_batch.events[0].event_type == "baseline_output_committed"
    assert output_batch.trace_batch.events[0].lineage["read_set_root"] == (
        output_batch.read_set.root()
    )
    reread = BaselineOutputResultV2.from_dict(result.to_dict())
    assert reread == result
    assert reread.canonical_bytes() == result.canonical_bytes()
    assert reread.root() == result.result_root
    tampered = result.to_dict()
    tampered["result_root"] = _root("7")
    with pytest.raises(ValueError, match="binding is mismatched"):
        BaselineOutputResultV2.from_dict(tampered)


def test_direct_governance_without_evidence_denies_external_action() -> None:
    context = _context(scope_ref="scope:baseline-output-direct")
    request = _request(
        context,
        decision_mode="direct_governance",
        threshold=1,
        verified_signals=(),
    )

    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    permission = _permission(context, request)
    assert permission.candidate_ref == "candidate:accept"
    assert permission.disposition is ActionPermissionDispositionV2.DENIED
    result = _commit_output(context, request)
    assert result.terminal_status is BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED


def test_quorum_miss_selects_declared_safe_fallback() -> None:
    context = _context(scope_ref="scope:baseline-output-fallback")
    request = _request(context, threshold=2)

    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    permission = _permission(context, request)
    assert permission.terminal_status is BaselineOutputTerminalStatusV2.SAFE_FALLBACK
    assert permission.candidate_ref == "candidate:fallback"
    assert permission.disposition is ActionPermissionDispositionV2.DENIED
    result = _commit_output(context, request)
    assert result.terminal_status is BaselineOutputTerminalStatusV2.SAFE_FALLBACK
    assert result.candidate_ref == "candidate:fallback"
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED


def test_quorum_miss_with_provenance_can_authorize_safe_fallback() -> None:
    context = _context(scope_ref="scope:baseline-output-evidenced-fallback")
    signal = _verified_signal(context, label="4c", source_ref="source:alpha")
    request = _request(context, threshold=2, verified_signals=(signal,))

    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    permission = _permission(context, request)
    assert permission.terminal_status is BaselineOutputTerminalStatusV2.SAFE_FALLBACK
    assert permission.disposition is ActionPermissionDispositionV2.AUTHORIZED
    result = _commit_output(context, request)
    assert result.candidate_ref == "candidate:fallback"
    assert result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED


def test_stop_block_forces_fallback_and_denies_external_action() -> None:
    context = _context(scope_ref="scope:baseline-output-stop")
    request = _request(
        context,
        decision_mode="direct_governance",
        threshold=1,
        blocked=True,
    )

    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    permission = _permission(context, request)
    assert permission.terminal_status is BaselineOutputTerminalStatusV2.BLOCKED
    assert permission.candidate_ref == "candidate:fallback"
    assert permission.disposition is ActionPermissionDispositionV2.DENIED
    result = _commit_output(context, request)
    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert (
        result.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert result.terminal_status is BaselineOutputTerminalStatusV2.BLOCKED
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert result.authorization is None


def test_exact_replay_is_idempotent_and_old_output_becomes_superseded() -> None:
    context = _context(scope_ref="scope:baseline-output-replay")
    first = _request(context, decision_mode="direct_governance", request_label="first")
    assert _issue(context, first).disposition is GovernanceCommitDispositionV2.COMMITTED
    committed = _commit_output(context, first)
    assert committed.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    assert committed.commit_attempt.committed_transition is not None
    first_receipt = committed.commit_attempt.committed_transition.receipt.receipt_root

    permission_retry = _issue(context, first)
    replay = _commit_output(context, first)
    assert permission_retry.position_observation is not None
    assert (
        permission_retry.position_observation.position
        is GovernanceCommitPositionV2.CURRENT
    )
    assert replay.commit_attempt.committed_transition is not None
    assert (
        replay.commit_attempt.committed_transition.receipt.receipt_root == first_receipt
    )
    assert replay.position is GovernanceCommitPositionV2.CURRENT
    assert replay.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED

    successor = _request(
        context,
        decision_mode="direct_governance",
        request_label="successor",
        payload="answer-two",
    )
    assert (
        _issue(context, successor).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert _commit_output(context, successor).action_disposition is (
        BaselineOutputActionDispositionV2.AUTHORIZED
    )

    historical = _commit_output(context, first)
    assert historical.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert historical.position is GovernanceCommitPositionV2.SUPERSEDED
    assert (
        historical.delivery_disposition
        is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert historical.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert historical.authorization is None


def _all_non_lifecycle_streams(
    context: _Context,
    request: BaselineOutputRequestV2,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            (
                governance_issuer_grant_stream_ref_v2(
                    context.domain.scope_ref,
                    context.grant.grant_ref,
                ),
                request.manifest_stream_ref,
                request.evidence_stream_ref,
                request.stop_stream_ref,
                request.decision_stream_ref,
                request.permission_stream_ref,
                request.output_stream_ref,
                *(
                    governance_verified_signal_stream_ref_v2(
                        request.scope_ref,
                        str(signal["signal_ref"]),
                        request.target_ref,
                    )
                    for signal in request.verified_signals
                ),
            ),
            key=lambda value: value.encode("utf-8"),
        )
    )


__all__ = [
    "_Context",
    "_all_non_lifecycle_streams",
    "_commit_output",
    "_context",
    "_issue",
    "_permission",
    "_request",
    "_verified_signal",
]
