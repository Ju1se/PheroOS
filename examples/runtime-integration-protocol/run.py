"""Facade-only independent consumer for Runtime Integration transcript TCK v1."""

from __future__ import annotations

import base64
import binascii
from hashlib import sha256
import json

from pheroos.conformance.runtime_compatibility import (
    RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
    build_runtime_compatibility_manifest_v1,
    evaluate_runtime_compatibility_v1,
)
from pheroos.conformance.runtime_integration import (
    RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
    IndependentRuntimeIntegrationStoreFactoryV1,
    RuntimeIntegrationAdapterV1,
    RuntimeIntegrationTranscriptErrorV1,
    RuntimeTranscriptDispositionV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    RuntimeTranscriptStepV1,
    run_runtime_integration_conformance_v1,
)
from pheroos.drivers import (
    DRIVER_INVOCATION_RECEIPT_VERSION_V2,
    DriverInvocationReceiptV2,
    DriverProbeSnapshot,
)
from pheroos.governance import (
    GovernanceCommitDispositionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerOperationV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    open_governance_authority_session_v2,
    require_current_commit_certificate_state_v2,
)
from pheroos.governance import (
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
    recover_baseline_output_result_v2,
)
from pheroos.governance import (
    CommitDecisionOutcomeKindV2,
    CommitDecisionOutcomeV2,
    VerifiedCommitCertificateStateV2,
)
from pheroos.kernel import (
    KERNEL_PLAN_VERSION_V2,
    InputEnvelope,
    OSKernel,
    OSPlanDocument,
)
from pheroos.protocol import CAPABILITY_SCHEMA_V3, read_capability_manifest
from pheroos.trace import (
    SCOPED_TRACE_CHECKPOINT_VERSION_V2,
    ScopedTraceCheckpointV2,
    ScopedTraceEvent,
    TraceEvent,
)

from stores import IndependentDriverStoreV2, IndependentTraceStoreV2


class IndependentFixtureRuntimeIntegrationAdapterV1:
    """Independent orchestration using the public ABI and independent Store."""

    implementation_id = "external-independent-runtime-integration-v1"
    conformance_version = RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1

    def __init__(self) -> None:
        self._recovered_readers: dict[tuple[str, str], GovernanceStateReaderV2] = {}
        self._certificate_states: dict[
            tuple[str, str],
            tuple[
                VerifiedCommitCertificateStateV2,
                VerifiedCommitCertificateStateV2 | None,
            ],
        ] = {}

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        if type(request) is not RuntimeTranscriptRequestV1:
            raise RuntimeIntegrationTranscriptErrorV1(
                "independent adapter requires an exact request"
            )
        original = request
        request = RuntimeTranscriptRequestV1.from_dict(request.to_dict())
        if original != request:
            raise RuntimeIntegrationTranscriptErrorV1(
                "independent adapter rejected a mutated request"
            )
        lookup = (request.request_root, request.scope.scope_ref)
        self._recovered_readers.pop(lookup, None)
        self._certificate_states.pop(lookup, None)
        compatibility = build_runtime_compatibility_manifest_v1()
        compatibility_report = evaluate_runtime_compatibility_v1(
            compatibility,
            request.compatibility_claim,
        )
        plan_document, plan_root = _kernel_projection(request)
        (
            receipts,
            restarted_receipt,
            checkpoint_wire,
            checkpoint_root,
        ) = _driver_projection(request)
        disposition = _runtime_disposition(request)
        governance_result: BaselineOutputResultV2 | None = None
        outcome = (
            None
            if request.commit_observation is None
            else request.commit_observation.outcome
        )
        recovered = False
        certificate_state: VerifiedCommitCertificateStateV2 | None = None
        diagnostics: tuple[str, ...] = ()
        if disposition is RuntimeTranscriptDispositionV1.COMPLETED:
            governance_result, recovered, recovered_reader = _governance_projection(
                request
            )
            if recovered_reader is not None:
                self._recovered_readers[lookup] = recovered_reader
            if (
                request.commit_observation is not None
                and request.commit_observation.outcome.kind
                is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
            ):
                states = IndependentRuntimeIntegrationStoreFactoryV1().build_recovered_certificate_states_v1(
                    label=request.scenario_id,
                    scope_ref=request.scope.scope_ref,
                    with_successor=(
                        request.commit_observation.successor_finality is not None
                    ),
                )
                self._certificate_states[lookup] = states
                certificate_state = states[0]
        else:
            outcome = None
            diagnostics = tuple(
                label
                for enabled, label in (
                    (request.control.wall_clock_timed_out, "wall_clock_timed_out"),
                    (request.control.cancel_requested, "cancel_requested"),
                )
                if enabled
            )
        delivery, publish, execute = _output_projection(
            request,
            disposition,
            governance_result,
            outcome,
            certificate_state,
        )
        steps = _compose_steps(
            request,
            compatibility.manifest_root,
            plan_root,
            receipts,
            restarted_receipt,
            checkpoint_root,
            governance_result,
            outcome,
            disposition,
            delivery,
            publish,
            execute,
        )
        trace = _project_trace(request, steps)
        steps = _new_step(
            steps,
            "trace",
            SCOPED_TRACE_CHECKPOINT_VERSION_V2,
            trace.checkpoint_root,
        )
        return RuntimeTranscriptResultV1(
            implementation_id=self.implementation_id,
            request_root=request.request_root,
            disposition=disposition,
            compatibility_manifest_root=compatibility.manifest_root,
            compatibility_report_version=RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
            compatibility_ok=compatibility_report.ok,
            plan_document=plan_document,
            plan_root=plan_root,
            driver_receipts=receipts,
            driver_restarted_receipt=restarted_receipt,
            driver_checkpoint_wire=checkpoint_wire,
            driver_checkpoint_root=checkpoint_root,
            governance_result=governance_result,
            commit_outcome=outcome,
            trace_checkpoint=trace,
            delivery_eligible=delivery,
            publication_authorized=publish,
            execution_authorized=execute,
            recovered_after_commit=recovered,
            diagnostics=diagnostics,
            steps=steps,
        )

    def read_driver_checkpoint_v1(
        self,
        checkpoint_wire: str,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        try:
            checkpoint = base64.b64decode(
                checkpoint_wire,
                altchars=b"-_",
                validate=True,
            )
        except (ValueError, binascii.Error) as exc:
            raise ValueError("independent checkpoint wire is invalid") from exc
        if base64.urlsafe_b64encode(checkpoint).decode("ascii") != checkpoint_wire:
            raise ValueError("independent checkpoint wire is noncanonical")
        return IndependentDriverStoreV2.restart(checkpoint).get(
            scope_ref,
            driver_id,
            idempotency_key,
        )

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        return self._recovered_readers.get((request_root, scope_ref))

    def open_recovered_certificate_states_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> (
        tuple[
            VerifiedCommitCertificateStateV2,
            VerifiedCommitCertificateStateV2 | None,
        ]
        | None
    ):
        return self._certificate_states.get((request_root, scope_ref))


def _kernel_projection(
    request: RuntimeTranscriptRequestV1,
) -> tuple[dict[str, object], str]:
    capability = read_capability_manifest(
        request.capability.to_dict(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    driver = request.capability.drivers[0]
    plan = OSKernel().plan(
        InputEnvelope(
            request=f"runtime transcript {request.scenario_id}",
            tenant_id=request.scope.tenant_id,
            metadata={
                "request_id": request.scope.request_id,
                "run_id": request.scope.run_id,
            },
        ),
        [capability],
        driver_probe_snapshots=(
            DriverProbeSnapshot(
                driver_id=driver.id,
                available=True,
                version=driver.version,
                capabilities=tuple(driver.capabilities),
            ),
        ),
    )
    document = OSPlanDocument(plan).to_dict()
    return document, _root("kernel-plan", document)


def _driver_projection(
    request: RuntimeTranscriptRequestV1,
) -> tuple[tuple[DriverInvocationReceiptV2, ...], DriverInvocationReceiptV2, str, str]:
    store = IndependentDriverStoreV2()
    receipts = [store.record(request.driver_request, request.driver_result)]
    if request.control.repeat_invocation:
        receipts.append(store.record(request.driver_request, request.driver_result))
    checkpoint = store.checkpoint()
    restarted = IndependentDriverStoreV2.restart(checkpoint)
    replay = restarted.record(request.driver_request, request.driver_result)
    if replay != receipts[0]:
        raise ValueError("independent driver restart changed receipt")
    return (
        tuple(receipts),
        replay,
        base64.urlsafe_b64encode(checkpoint).decode("ascii"),
        "sha256:" + sha256(checkpoint).hexdigest(),
    )


def _runtime_disposition(
    request: RuntimeTranscriptRequestV1,
) -> RuntimeTranscriptDispositionV1:
    if request.control.wall_clock_timed_out:
        return RuntimeTranscriptDispositionV1.RUNTIME_TIMED_OUT
    if request.control.cancel_requested:
        return RuntimeTranscriptDispositionV1.RUNTIME_CANCELLED
    return RuntimeTranscriptDispositionV1.COMPLETED


def _governance_projection(
    request: RuntimeTranscriptRequestV1,
) -> tuple[BaselineOutputResultV2 | None, bool, GovernanceStateReaderV2 | None]:
    factory = IndependentRuntimeIntegrationStoreFactoryV1()
    store = factory.create_governance_store_v2((request.authority_domain,))
    capability = _initialize_governance(store, request)
    baseline = request.baseline_request
    if baseline is None:
        return None, False, None
    result = _baseline_commit(capability, baseline, request)
    if request.control.inject_cas_conflict:
        contender = request.contender_request
        if contender is None:
            raise ValueError("independent CAS contender is absent")
        return _baseline_commit(capability, contender, request), False, None
    if not request.control.recover_after_commit:
        return result, False, None
    _advance_before_recovery(factory, store, capability, request)
    restarted = factory.restart_governance_store_v2(store)
    witness_digest = sha256(request.request_root.encode("ascii")).hexdigest()
    factory.advance_dependency_head_v1(
        store,
        request.authority_domain,
        stream_ref=(
            "authority:runtime-integration-restart-witness-v1:" + witness_digest
        ),
        transition_id=("transition:runtime:post-checkpoint-witness:" + witness_digest),
    )
    return (
        recover_baseline_output_result_v2(
            baseline,
            state_reader=restarted,
        ),
        True,
        restarted,
    )


def _initialize_governance(
    store: GovernanceStateStoreV2,
    request: RuntimeTranscriptRequestV1,
) -> GovernanceIssuerCapabilityV2:
    activated = activate_governance_issuer_grant_v2(
        store,
        request.authority_domain,
        request.issuer_grant,
        f"transition:activate:{request.scenario_id}",
        1,
    )
    if activated.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise ValueError("independent issuer grant activation failed")
    capability = bind_governance_issuer_capability_v2(
        store,
        request.authority_domain,
        request.issuer_grant,
        request.scope.run_id,
        2,
    )
    for signal in request.verified_signal_requests:
        session = open_governance_authority_session_v2(capability, signal)
        committed = commit_verified_signal_v2(signal, authority_session=session)
        if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
            raise ValueError("independent verified signal commit failed")
    return capability


def _advance_before_recovery(
    factory: IndependentRuntimeIntegrationStoreFactoryV1,
    store: GovernanceStateStoreV2,
    capability: GovernanceIssuerCapabilityV2,
    request: RuntimeTranscriptRequestV1,
) -> None:
    baseline = request.baseline_request
    assert baseline is not None
    successor = request.successor_request
    if request.control.advance_permission_before_recovery:
        factory.advance_dependency_head_v1(
            store,
            request.authority_domain,
            stream_ref=baseline.permission_stream_ref,
            transition_id=(
                f"transition:runtime:permission-successor:{request.scenario_id}"
            ),
        )
    elif request.control.advance_stop_before_recovery:
        factory.advance_dependency_head_v1(
            store,
            request.authority_domain,
            stream_ref=baseline.stop_stream_ref,
            transition_id=f"transition:runtime:stop-successor:{request.scenario_id}",
        )
    elif successor is not None:
        _baseline_commit(capability, successor, request)


def _baseline_commit(
    capability: GovernanceIssuerCapabilityV2,
    baseline: BaselineOutputRequestV2,
    transcript: RuntimeTranscriptRequestV1,
) -> BaselineOutputResultV2:
    if (
        not transcript.control.omit_permission
        or baseline is transcript.successor_request
    ):
        _permission(
            capability,
            baseline,
            required=baseline is not transcript.contender_request,
        )
    session = open_baseline_output_authority_session_v2(
        capability,
        baseline,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    return evaluate_and_commit_baseline_output_v2(
        baseline,
        authority_session=session,
    )


def _permission(
    capability: GovernanceIssuerCapabilityV2,
    baseline: BaselineOutputRequestV2,
    *,
    required: bool = True,
) -> None:
    session = open_baseline_output_authority_session_v2(
        capability,
        baseline,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    attempt = issue_action_permission_v2(baseline, authority_session=session)
    if required and attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise ValueError("independent action permission failed")


def _output_projection(
    request: RuntimeTranscriptRequestV1,
    disposition: RuntimeTranscriptDispositionV1,
    result: BaselineOutputResultV2 | None,
    outcome: CommitDecisionOutcomeV2 | None,
    certificate_state: VerifiedCommitCertificateStateV2 | None,
) -> tuple[bool, bool, bool]:
    if disposition is not RuntimeTranscriptDispositionV1.COMPLETED:
        return False, False, False
    if result is None:
        return bool(outcome is not None and outcome.delivery_eligible), False, False
    delivery = (
        result.delivery_disposition is BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    authorized = (
        result.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
        and result.authorization is not None
        and _certificate_gate_open(request, certificate_state)
    )
    selected = _selected_baseline_request(request)
    effect = "" if selected is None else selected.effect
    return (
        delivery,
        authorized and effect == "publish",
        authorized and effect == "execute",
    )


def _certificate_gate_open(
    request: RuntimeTranscriptRequestV1,
    certificate_state: VerifiedCommitCertificateStateV2 | None,
) -> bool:
    observation = request.commit_observation
    if observation is None:
        return True
    if certificate_state is None or observation.observed_finality is None:
        return False
    projection = observation.observed_finality
    try:
        snapshot = require_current_commit_certificate_state_v2(certificate_state)
    except Exception:
        return False
    body = snapshot.certificate.body
    committed = observation.outcome
    return (
        snapshot.stream_ref == projection.stream_ref
        and snapshot.revision == projection.revision
        and snapshot.transition_id == projection.transition_id
        and snapshot.snapshot_root == projection.snapshot_root
        and certificate_state.receipt_root == projection.receipt_root
        and body.seal_transition_id == projection.seal_transition_id
        and body.seal_root == projection.seal_root
        and body.frozen_dependency_root == projection.frozen_dependency_root
        and snapshot.current_step + 1 == projection.verified_at_step
        and tuple(snapshot.reason_codes) == tuple(projection.reason_codes)
        and body.candidate_ref == committed.candidate_ref
        and body.claim_root == committed.claim_root
        and body.output_contract_root == committed.output_contract_root
        and body.output_payload_root == committed.output_payload_root
    )


def _compose_steps(
    request: RuntimeTranscriptRequestV1,
    compatibility_root: str,
    plan_root: str,
    receipts: tuple[DriverInvocationReceiptV2, ...],
    restarted_receipt: DriverInvocationReceiptV2,
    checkpoint_root: str,
    result: BaselineOutputResultV2 | None,
    outcome: CommitDecisionOutcomeV2 | None,
    disposition: RuntimeTranscriptDispositionV1,
    delivery: bool,
    publish: bool,
    execute: bool,
) -> tuple[RuntimeTranscriptStepV1, ...]:
    steps: tuple[RuntimeTranscriptStepV1, ...] = ()
    steps = _new_step(
        steps,
        "compatibility",
        "pheroos-runtime-compatibility-manifest-v1",
        compatibility_root,
    )
    steps = _new_step(
        steps,
        "scope",
        request.scope.to_dict()["scope_version"],
        request.scope.scope_ref,
    )
    steps = _new_step(
        steps,
        "protocol",
        request.capability.protocol.protocol_version,
        request.capability.manifest_root,
    )
    steps = _new_step(steps, "kernel", KERNEL_PLAN_VERSION_V2, plan_root)
    driver_root = _root(
        "driver-stage",
        {
            "request_digest": request.driver_request.request_digest,
            "result_digest": request.driver_result.result_digest,
            "receipt_roots": [item.receipt_digest for item in receipts],
            "restarted_receipt_root": restarted_receipt.receipt_digest,
            "checkpoint_root": checkpoint_root,
        },
    )
    steps = _new_step(
        steps, "drivers", DRIVER_INVOCATION_RECEIPT_VERSION_V2, driver_root
    )
    governance_version, governance_root = _governance_root(
        request,
        result,
        outcome,
        disposition,
    )
    steps = _new_step(steps, "governance", governance_version, governance_root)
    delivery_root = _root(
        "delivery-projection",
        {
            "delivery_eligible": delivery,
            "publication_authorized": publish,
            "execution_authorized": execute,
            "governance_root": governance_root,
            "request_action_ref": _request_action_ref(request),
            "request_effect": _request_effect(request),
            "action_authority_root": _action_authority_root(
                result,
                publish=publish,
                execute=execute,
            ),
        },
    )
    return _new_step(
        steps,
        "output",
        "pheroos-runtime-output-projection-v1",
        delivery_root,
    )


def _selected_baseline_request(
    request: RuntimeTranscriptRequestV1,
) -> BaselineOutputRequestV2 | None:
    if request.control.inject_cas_conflict:
        return request.contender_request
    return request.baseline_request


def _request_action_ref(request: RuntimeTranscriptRequestV1) -> str:
    selected = _selected_baseline_request(request)
    return "" if selected is None else selected.action_ref


def _request_effect(request: RuntimeTranscriptRequestV1) -> str:
    selected = _selected_baseline_request(request)
    return "" if selected is None else selected.effect


def _action_authority_root(
    result: BaselineOutputResultV2 | None,
    *,
    publish: bool,
    execute: bool,
) -> str:
    if result is None or result.authorization is None or not (publish or execute):
        return ""
    return result.authorization.permission_root


def _governance_root(
    request: RuntimeTranscriptRequestV1,
    result: BaselineOutputResultV2 | None,
    outcome: CommitDecisionOutcomeV2 | None,
    disposition: RuntimeTranscriptDispositionV1,
) -> tuple[str, str]:
    if result is not None and outcome is not None:
        return (
            "pheroos-runtime-governance-composite-v1",
            _root(
                "governance-composite",
                {
                    "baseline_result_root": result.result_root,
                    "commit_outcome_root": outcome.outcome_root,
                },
            ),
        )
    if result is not None:
        return result.schema, result.result_root
    if outcome is not None:
        return outcome.schema, outcome.outcome_root
    return (
        request.control.version + ":" + disposition.value,
        _root("runtime-control", request.control.to_dict()),
    )


def _new_step(
    steps: tuple[RuntimeTranscriptStepV1, ...],
    layer: str,
    version: str,
    artifact_root: str,
) -> tuple[RuntimeTranscriptStepV1, ...]:
    return (
        *steps,
        RuntimeTranscriptStepV1(
            sequence=len(steps),
            layer=layer,
            artifact_version=version,
            artifact_root=artifact_root,
            predecessor_root="" if not steps else steps[-1].step_root,
        ),
    )


def _project_trace(
    request: RuntimeTranscriptRequestV1,
    steps: tuple[RuntimeTranscriptStepV1, ...],
) -> ScopedTraceCheckpointV2:
    store = IndependentTraceStoreV2()
    for step in steps:
        envelope = ScopedTraceEvent(
            scope_ref=request.scope.scope_ref,
            stream="runtime-integration-v1",
            transition_id=f"transition:runtime:{request.scenario_id}:{step.sequence}",
            trace_id=f"trace:runtime:{request.scenario_id}:{step.sequence}",
            event=TraceEvent(
                event_type=f"ext.pheroos.runtime_integration_v1.{step.layer}",
                protocol_id=request.capability.protocol.id,
                target=request.scenario_id,
                reason="project provider-free runtime integration transcript",
                lineage={
                    "request_root": request.request_root,
                    "sequence": step.sequence,
                    "artifact_version": step.artifact_version,
                    "artifact_root": step.artifact_root,
                    "predecessor_root": step.predecessor_root,
                    "step_root": step.step_root,
                },
            ),
        )
        store.append_scoped_v2(envelope)
    checkpoint = store.checkpoint_v2()
    return store.restart_v2(checkpoint).checkpoint_v2()


def _root(kind: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    prefix = b"pheroos-runtime-integration-v1\x00" + kind.encode("ascii") + b"\x00"
    return "sha256:" + sha256(prefix + encoded).hexdigest()


def main() -> int:
    adapter = IndependentFixtureRuntimeIntegrationAdapterV1()
    if not isinstance(adapter, RuntimeIntegrationAdapterV1):
        print(json.dumps({"ok": False, "detail": "adapter_protocol"}))
        return 1
    report = run_runtime_integration_conformance_v1(adapter)
    print(json.dumps({"name": report.name, "ok": report.ok, "detail": report.detail}))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
