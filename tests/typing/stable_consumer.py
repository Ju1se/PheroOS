"""External-style consumer of only the Draft Stable promotion candidate.

The file is both a strict Mypy fixture and an executable, provider-free smoke
journey.  Every PheroOS import comes from one of the six public package
facades; candidate membership is checked independently by the companion test.
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import assert_type

from pheroos.conformance import (
    CheckResult,
    ConformanceReport,
    GovernanceStateStoreConformanceAdapterV2,
    run_conformance,
    run_governance_baseline_output_conformance_v2,
    run_governance_state_store_conformance_v2,
    run_source_conformance,
)
from pheroos.drivers import (
    DriverDescriptor,
    DriverHandle,
    DriverInvocationReceiptV2,
    DriverInvocationReplyV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationStoreV2,
    DriverProbeResult,
    bind,
    expose,
    probe,
    register,
)
from pheroos.governance import (
    AuthorityDomainV2,
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerifierV2,
    activate_governance_issuer_grant_v2,
    baseline_verified_signal_proposal_root_v2,
    evaluate_and_commit_governed_baseline_output_v2,
    recover_baseline_output_result_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.kernel import (
    InputEnvelope,
    OSKernel,
    OSPlanDocument,
    RuntimeContext,
    RuntimeMaterializer,
    RuntimeScope,
    os_plan_from_dict,
)
from pheroos.protocol import (
    AuthorityDiagnosticCodeV2,
    ProtocolSchemaVersionError,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    capability_schema_v3,
    protocol_schema_v3,
    read_capability_manifest,
    validate_capability_manifest,
)
from pheroos.trace import (
    ScopedTraceAppendReceiptV2,
    ScopedTraceEvent,
    ScopedTraceStoreV2,
    TraceEvent,
    validate_event_lineage,
)


_ZERO_ROOT = "sha256:" + "0" * 64


def _capability_payload() -> dict[str, object]:
    return {
        "id": "stable-consumer",
        "name": "Stable Consumer",
        "version": "1",
        "permissions": [],
        "required_connections": [],
        "drivers": [
            {
                "id": "driver.echo",
                "kind": "tool",
                "version": "1",
                "capabilities": ["capability:echo"],
                "permissions": ["driver:invoke"],
            }
        ],
        "protocol": {
            "protocol_version": "pheroos.protocol.v2",
            "id": "stable.consumer.protocol",
            "targets": [{"id": "decision:answer"}],
            "signals": [],
            "candidates": [
                {"id": "candidate:answer", "target": "decision:answer"},
                {
                    "id": "candidate:fallback",
                    "target": "decision:answer",
                    "safe_fallback": True,
                },
            ],
            "quorum_policy": {
                "target": "decision:answer",
                "fallback_candidate": "candidate:fallback",
                "commit_threshold": 1,
            },
            "authority_policy": {
                "policy_version": "pheroos-scoped-authority-policy-v2",
                "profile": "pheroos-scoped-authority-local-v2",
                "wire_version": "pheroos-authority-wire-v2",
                "canonical_version": "pheroos-authority-canonical-v2",
                "ledger_version": "pheroos-governance-authority-ledger-v2",
                "state_store_version": "pheroos-governance-state-store-v2",
                "trace_batch_version": "pheroos-governance-trace-batch-v2",
                "read_set_version": "pheroos-governance-authority-read-set-v2",
            },
            "recovery_protocols": [],
            "evidence_policy": {
                "require_provenance": True,
                "allow_agent_fact_creation": False,
            },
            "output_policy": {
                "policy_version": "pheroos-baseline-output-policy-v2",
                "decision_mode": "quorum",
                "actions": [
                    {
                        "action_ref": "action:publish",
                        "effect": "publish",
                        "target": "decision:answer",
                        "allowed_outcomes": [
                            "evidence_commit",
                            "safe_fallback",
                        ],
                    }
                ],
            },
            "trace_policy": {
                "required_events": [
                    "baseline_action_permission_issued",
                    "baseline_decision_evaluated",
                    "baseline_evidence_qualified",
                    "baseline_manifest_activated",
                    "baseline_output_committed",
                    "baseline_stop_resolved",
                    "block",
                    "commit",
                    "output",
                    "recovery",
                ]
            },
        },
    }


def _read_manifest() -> ScopedCapabilityManifestV2:
    try:
        manifest = read_capability_manifest(
            _capability_payload(),
            schema_version="pheroos-capability-schema-v3",
        )
    except ProtocolSchemaVersionError as exc:
        raise AssertionError("candidate manifest must be readable") from exc
    if not isinstance(manifest, ScopedCapabilityManifestV2):
        raise AssertionError("v3 must select the scoped capability contract")
    diagnostics = validate_capability_manifest(manifest)
    if any(item.level == "error" for item in diagnostics):
        raise AssertionError(diagnostics)
    return manifest


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _write_material(
    scope: RuntimeScope,
    manifest: ScopedProtocolManifestV2,
    label: str,
    *,
    blocked: bool = False,
    expires_at_epoch: int = 10,
    observed_epoch: int = 2,
) -> tuple[
    AuthorityDomainV2,
    GovernanceIssuerGrantV2,
    GovernanceVerifiedSignalRequestV2,
    BaselineOutputRequestV2,
]:
    domain = AuthorityDomainV2(
        policy_version="pheroos-scoped-authority-policy-v2",
        profile="pheroos-scoped-authority-local-v2",
        wire_version="pheroos-authority-wire-v2",
        canonical_version="pheroos-authority-canonical-v2",
        ledger_version="pheroos-governance-authority-ledger-v2",
        state_store_version="pheroos-governance-state-store-v2",
        trace_batch_version="pheroos-governance-trace-batch-v2",
        read_set_version="pheroos-governance-authority-read-set-v2",
        scope_ref=scope.scope_ref,
    )
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        issuer_ref="issuer:stable-consumer",
        grant_ref=f"grant:{label}",
        grant_binding_ref=_root(f"grant-binding:{label}"),
        operations=(
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        ),
        target_refs=("decision:answer",),
        action_refs=("action:publish",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=expires_at_epoch,
        revocation_generation=0,
    )
    signal_ref = f"signal:{label}"
    evidence_root = _root(f"evidence:{label}")
    provenance_ref = _root(f"provenance:{label}")
    source_ref = f"source:{label}"
    signal_root = baseline_verified_signal_proposal_root_v2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        run_ref=scope.run_id,
        target_ref="decision:answer",
        candidate_ref="candidate:answer",
        signal_ref=signal_ref,
        evidence_root=evidence_root,
        provenance_ref=provenance_ref,
        source_ref=source_ref,
    )
    signal = GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        run_ref=scope.run_id,
        request_ref=f"request:signal:{label}",
        transition_id=f"transition:signal:{label}",
        signal_ref=signal_ref,
        target_ref="decision:answer",
        signal_root=signal_root,
        evidence_root=evidence_root,
        status="verified",
        observed_epoch=observed_epoch,
    )
    request = BaselineOutputRequestV2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        run_ref=scope.run_id,
        request_ref=f"request:output:{label}",
        output_transition_id=f"transition:output:{label}",
        manifest=manifest,
        target_ref="decision:answer",
        action_ref="action:publish",
        proposed_candidate_ref=None,
        verified_signals=(
            {
                "candidate_ref": "candidate:answer",
                "evidence_root": evidence_root,
                "provenance_ref": provenance_ref,
                "signal_ref": signal_ref,
                "signal_root": signal_root,
                "signal_transition_id": signal.transition_id,
                "source_ref": source_ref,
            },
        ),
        stop_resolutions=(
            {
                "action_ref": "action:publish",
                "blocked": blocked,
                "provenance_ref": _root(f"stop:{label}"),
                "reason_ref": "reason:blocked" if blocked else "reason:clear",
            },
        ),
        output_payload={"answer": label},
        observed_epoch=observed_epoch,
    )
    return domain, grant, signal, request


def exercise_governance_write_journey(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> None:
    """Run candidate writes through an externally supplied Stable Store Protocol."""

    manifest = _read_manifest().protocol
    scope = RuntimeScope("tenant:write", "run:write", "request:write")
    domain, grant, signal, request = _write_material(
        scope,
        manifest,
        "stable-write",
    )
    store = adapter.create_store_v2((domain,))
    first = evaluate_and_commit_governed_baseline_output_v2(
        store,
        domain,
        grant,
        "transition:activate:stable-write",
        1,
        request,
        verified_signal_requests=(signal,),
    )
    assert_type(first, GovernanceCommitAttemptV2 | BaselineOutputResultV2)
    if not isinstance(first, BaselineOutputResultV2):
        raise AssertionError(first)
    if (
        first.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or first.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or first.action_disposition is not BaselineOutputActionDispositionV2.AUTHORIZED
        or first.authorization is None
    ):
        raise AssertionError(first)

    before_retry = adapter.observe_store_v2(store, scope.scope_ref)
    retry = evaluate_and_commit_governed_baseline_output_v2(
        store,
        domain,
        grant,
        "transition:activate:stable-write",
        1,
        request,
        verified_signal_requests=(signal,),
    )
    if not isinstance(retry, BaselineOutputResultV2):
        raise AssertionError(retry)
    after_retry = adapter.observe_store_v2(store, scope.scope_ref)
    if retry.result_root != first.result_root or (
        after_retry["commit_order"] != before_retry["commit_order"]
        or after_retry["receipts"] != before_retry["receipts"]
        or after_retry["trace_batches"] != before_retry["trace_batches"]
    ):
        raise AssertionError("exact retry changed the durable result")

    restarted = adapter.restart_store_v2(store)
    restart_retry = evaluate_and_commit_governed_baseline_output_v2(
        restarted,
        domain,
        grant,
        "transition:activate:stable-write",
        1,
        request,
        verified_signal_requests=(signal,),
    )
    recovered = recover_baseline_output_result_v2(
        request,
        state_reader=restarted,
    )
    if (
        not isinstance(restart_retry, BaselineOutputResultV2)
        or restart_retry.result_root != first.result_root
        or recovered.result_root != first.result_root
        or recovered.authorization is None
    ):
        raise AssertionError("restart recovery changed the committed result")

    successor = replace(
        request,
        request_ref="request:output:stable-write:successor",
        output_transition_id="transition:output:stable-write:successor",
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
        restarted,
        domain,
        grant,
        "transition:activate:stable-write",
        1,
        successor,
        verified_signal_requests=(signal,),
    )
    stale = recover_baseline_output_result_v2(
        request,
        state_reader=restarted,
    )
    if (
        not isinstance(successor_result, BaselineOutputResultV2)
        or successor_result.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or stale.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or stale.action_disposition is not BaselineOutputActionDispositionV2.DENIED
        or stale.authorization is not None
    ):
        raise AssertionError("superseded output retained action authority")

    revoked = revoke_governance_issuer_grant_v2(
        restarted,
        domain,
        grant.grant_ref,
        "transition:revoke:stable-write",
        3,
    )
    revoked_retry = evaluate_and_commit_governed_baseline_output_v2(
        restarted,
        domain,
        grant,
        "transition:activate:stable-write",
        1,
        successor,
        verified_signal_requests=(signal,),
    )
    if (
        revoked.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or not isinstance(revoked_retry, GovernanceCommitAttemptV2)
        or revoked_retry.failure is None
        or revoked_retry.failure.code
        is not AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
        or revoked_retry.committed_transition is not None
    ):
        raise AssertionError("revoked grant retained write authority")

    expired_scope = RuntimeScope(
        "tenant:expired",
        "run:expired",
        "request:expired",
    )
    expired_domain, expired_grant, expired_signal, expired_request = _write_material(
        expired_scope,
        manifest,
        "stable-expired",
        expires_at_epoch=1,
    )
    expired = evaluate_and_commit_governed_baseline_output_v2(
        adapter.create_store_v2((expired_domain,)),
        expired_domain,
        expired_grant,
        "transition:activate:stable-expired",
        1,
        expired_request,
        verified_signal_requests=(expired_signal,),
    )
    if (
        not isinstance(expired, GovernanceCommitAttemptV2)
        or expired.failure is None
        or expired.failure.code is not AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED
    ):
        raise AssertionError("expired grant retained write authority")

    blocked_scope = RuntimeScope(
        "tenant:blocked",
        "run:blocked",
        "request:blocked",
    )
    blocked_domain, blocked_grant, blocked_signal, blocked_request = _write_material(
        blocked_scope,
        manifest,
        "stable-blocked",
        blocked=True,
    )
    blocked = evaluate_and_commit_governed_baseline_output_v2(
        adapter.create_store_v2((blocked_domain,)),
        blocked_domain,
        blocked_grant,
        "transition:activate:stable-blocked",
        1,
        blocked_request,
        verified_signal_requests=(blocked_signal,),
    )
    if (
        not isinstance(blocked, BaselineOutputResultV2)
        or blocked.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or blocked.action_disposition is not BaselineOutputActionDispositionV2.DENIED
        or blocked.authorization is not None
    ):
        raise AssertionError("blocked publish became externally actionable")


def _driver_journey(
    scope: RuntimeScope,
) -> tuple[DriverProbeResult, DriverHandle, DriverInvocationReplyV2]:
    descriptor = DriverDescriptor(
        id="driver.echo",
        kind="tool",
        version="1",
        capabilities=["capability:echo"],
        permissions=["driver:invoke"],
    )
    registration = register(descriptor)
    snapshot = probe(registration)
    binding = bind(
        registration,
        tenant_id=scope.tenant_id,
        run_id=scope.run_id,
        permissions=("driver:invoke",),
    )
    handle = expose(binding)
    request = DriverInvocationRequestV2(
        scope_ref=scope.scope_ref,
        driver_id=descriptor.id,
        invocation_id="invocation:1",
        operation="driver:invoke",
        capability="capability:echo",
        idempotency_key="idempotency:1",
        payload={"message": "hello"},
    )
    result = DriverInvocationResultV2(
        scope_ref=request.scope_ref,
        driver_id=request.driver_id,
        invocation_id=request.invocation_id,
        operation=request.operation,
        capability=request.capability,
        idempotency_key=request.idempotency_key,
        request_digest=request.request_digest,
        ok=True,
        payload={"message": "hello"},
        provenance="provider-free:stable-consumer",
    )
    receipt = DriverInvocationReceiptV2(
        scope_ref=request.scope_ref,
        driver_id=request.driver_id,
        invocation_id=request.invocation_id,
        operation=request.operation,
        capability=request.capability,
        idempotency_key=request.idempotency_key,
        provenance=result.provenance,
        request_digest=request.request_digest,
        result_digest=result.result_digest,
    )
    reply = DriverInvocationReplyV2(request, result, receipt)
    return snapshot, handle, reply


def persist_driver_result(
    store: DriverInvocationStoreV2,
    reply: DriverInvocationReplyV2,
) -> DriverInvocationReceiptV2:
    """Exercise the candidate Driver Store contract without selecting a store."""

    return store.record(reply.request, reply.result)


def append_trace(
    store: ScopedTraceStoreV2,
    event: ScopedTraceEvent,
) -> ScopedTraceAppendReceiptV2:
    """Exercise the candidate Trace Store contract without selecting storage."""

    return store.append_scoped_v2(event)


def activate_grant(
    store: GovernanceStateStoreV2,
    verifier: IssuerGrantVerifierV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
) -> GovernanceCommitAttemptV2:
    """Show the portable grant plus external-verifier activation boundary."""

    return activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant",
        1,
        verifier,
    )


def recover_output(
    reader: GovernanceStateReaderV2,
    request: BaselineOutputRequestV2,
) -> BaselineOutputResultV2:
    """Recover output from durable state, never from a local authority handle."""

    return recover_baseline_output_result_v2(request, state_reader=reader)


def run_store_conformance(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> tuple[CheckResult, CheckResult]:
    return (
        run_governance_state_store_conformance_v2(adapter),
        run_governance_baseline_output_conformance_v2(adapter),
    )


def run_manifest_conformance(path: str | Path) -> ConformanceReport:
    return run_conformance(path)


def main() -> None:
    capability_schema = capability_schema_v3()
    protocol_schema = protocol_schema_v3()
    if not str(capability_schema["$id"]).endswith(
        "capability-v3.schema.json"
    ) or not str(protocol_schema["$id"]).endswith("protocol-v3.schema.json"):
        raise AssertionError("candidate schema selectors returned wrong versions")

    scope = RuntimeScope("tenant:stable", "run:stable", "request:stable")
    manifest = _read_manifest()
    snapshot, handle, reply = _driver_journey(scope)
    plan = OSKernel().plan(
        InputEnvelope(
            request="stable consumer",
            tenant_id=scope.tenant_id,
            metadata={"request_id": scope.request_id, "run_id": scope.run_id},
        ),
        [manifest],
        driver_probe_snapshots=(snapshot,),
    )
    document = OSPlanDocument(plan)
    restored = os_plan_from_dict(document.to_dict())
    context = RuntimeMaterializer().materialize(restored.plan)
    assert_type(context, RuntimeContext)
    if not context.ready or handle.binding.scope_ref != context.scope_ref:
        raise AssertionError("candidate Kernel/Driver scope journey is not ready")

    event = TraceEvent(
        event_type="ext.stable-consumer",
        protocol_id=manifest.protocol.id,
        target="decision:answer",
        reason="provider-free candidate smoke journey",
        lineage={},
    )
    validate_event_lineage(event)
    scoped_event = ScopedTraceEvent(
        scope_ref=scope.scope_ref,
        stream="stable-consumer",
        transition_id="transition:trace",
        trace_id="trace:stable-consumer",
        event=event,
    )

    domain = AuthorityDomainV2(
        policy_version="pheroos-scoped-authority-policy-v2",
        profile="pheroos-scoped-authority-local-v2",
        wire_version="pheroos-authority-wire-v2",
        canonical_version="pheroos-authority-canonical-v2",
        ledger_version="pheroos-governance-authority-ledger-v2",
        state_store_version="pheroos-governance-state-store-v2",
        trace_batch_version="pheroos-governance-trace-batch-v2",
        read_set_version="pheroos-governance-authority-read-set-v2",
        scope_ref=scope.scope_ref,
    )
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=scope.scope_ref,
        issuer_ref="issuer:external-runtime",
        grant_ref="grant:stable-consumer",
        grant_binding_ref=_ZERO_ROOT,
        operations=(GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,),
        target_refs=("decision:answer",),
        action_refs=("action:publish",),
        issued_epoch=0,
        not_before_epoch=0,
        expires_at_epoch=10,
        revocation_generation=0,
    )
    assert_type(reply, DriverInvocationReplyV2)
    assert_type(scoped_event, ScopedTraceEvent)
    assert_type(grant, GovernanceIssuerGrantV2)

    source_report = run_source_conformance()
    assert_type(source_report, ConformanceReport)
    if not source_report.target:
        raise AssertionError("source Conformance report must identify its target")


if __name__ == "__main__":
    main()
