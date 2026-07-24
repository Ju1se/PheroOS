"""Reference composition for the provider-free Runtime Integration TCK.

This module is Conformance plumbing.  It composes existing public contracts but
does not implement a runtime, provider, scheduler, clock, queue, or database.
"""

from __future__ import annotations

from hashlib import sha256

from pheroos.conformance._runtime_compatibility_codec import (
    RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
)
from pheroos.conformance._runtime_compatibility_evaluation import (
    evaluate_runtime_compatibility_v1,
)
from pheroos.conformance._runtime_compatibility_catalog import (
    build_runtime_compatibility_manifest_v1,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.drivers import (
    DRIVER_INVOCATION_RECEIPT_VERSION_V2,
    DriverInvocationReceiptV2,
    DriverInvocationStoreV2,
    InMemoryDriverInvocationStoreV2,
    DriverProbeSnapshot,
    validate_driver_invocation_binding_v2,
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
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    evaluate_and_commit_baseline_output_v2,
    issue_action_permission_v2,
    open_baseline_output_authority_session_v2,
    recover_baseline_output_result_v2,
)
from pheroos.governance.commit_certificate_v2 import (
    VerifiedCommitCertificateStateV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionOutcomeKindV2,
    CommitDecisionOutcomeV2,
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
    InMemoryScopedTraceStoreV2,
    ScopedTraceCheckpointV2,
    ScopedTraceEvent,
    ScopedTraceStoreV2,
    TraceEvent,
)

from pheroos.conformance._runtime_integration_codec import (
    RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
    RuntimeIntegrationTranscriptErrorV1,
    checkpoint_from_wire,
    checkpoint_to_wire,
    document_root,
)
from pheroos.conformance._runtime_integration_contracts import (
    RuntimeTranscriptDispositionV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    RuntimeTranscriptStepV1,
)
from pheroos.conformance._runtime_integration_certificate import (
    _observe_certificate_state_v1,
    build_recovered_certificate_states_v1,
)
from pheroos.conformance._runtime_integration_dependency import (
    advance_runtime_dependency_head_v1,
    advance_runtime_recovery_witness_v1,
)


_TRACE_STREAM = "runtime-integration-v1"


class ReferenceRuntimeIntegrationAdapterV1:
    """Deterministic composition over reference stores and prebuilt inputs."""

    __slots__ = (
        "_certificate_states",
        "_recovered_readers",
        "_recovery_source_readers",
    )

    implementation_id = "pheroos-reference-runtime-integration-v1"
    conformance_version = RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1

    def __init__(self) -> None:
        self._recovered_readers: dict[tuple[str, str], GovernanceStateReaderV2] = {}
        self._recovery_source_readers: dict[
            tuple[str, str], GovernanceStateReaderV2
        ] = {}
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
        self._ensure_observation_maps()
        canonical = _canonical_request(request)
        lookup = (canonical.request_root, canonical.scope.scope_ref)
        self._recovered_readers.pop(lookup, None)
        self._recovery_source_readers.pop(lookup, None)
        self._certificate_states.pop(lookup, None)
        compatibility = build_runtime_compatibility_manifest_v1()
        report = evaluate_runtime_compatibility_v1(
            compatibility,
            canonical.compatibility_claim,
        )
        plan_document, plan_root = _plan(canonical)
        (
            receipts,
            restarted_receipt,
            driver_checkpoint_wire,
            driver_checkpoint_root,
        ) = _record_driver(canonical)
        disposition = _control_disposition(canonical)
        governance_result: BaselineOutputResultV2 | None = None
        commit_outcome = (
            None
            if canonical.commit_observation is None
            else canonical.commit_observation.outcome
        )
        recovered = False
        certificate_state: VerifiedCommitCertificateStateV2 | None = None
        diagnostics: tuple[str, ...] = ()
        if disposition is RuntimeTranscriptDispositionV1.COMPLETED:
            (
                governance_result,
                recovered,
                recovered_reader,
                recovery_source_reader,
            ) = _govern(canonical)
            if recovered_reader is not None:
                self._recovered_readers[lookup] = recovered_reader
            if recovery_source_reader is not None:
                self._recovery_source_readers[lookup] = recovery_source_reader
            if (
                canonical.commit_observation is not None
                and canonical.commit_observation.outcome.kind
                is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
            ):
                certificate_states = build_recovered_certificate_states_v1(
                    ReferenceGovernanceStateStoreConformanceAdapterV2(),
                    label=canonical.scenario_id,
                    scope_ref=canonical.scope.scope_ref,
                    with_successor=(
                        canonical.commit_observation.successor_finality is not None
                    ),
                )
                self._certificate_states[lookup] = certificate_states
                certificate_state = certificate_states[0]
        else:
            commit_outcome = None
            diagnostics = tuple(
                label
                for enabled, label in (
                    (
                        canonical.control.wall_clock_timed_out,
                        "wall_clock_timed_out",
                    ),
                    (canonical.control.cancel_requested, "cancel_requested"),
                )
                if enabled
            )
        delivery, publish, execute = _action_projection(
            canonical,
            disposition,
            governance_result,
            commit_outcome,
            certificate_state,
        )
        steps = _base_steps(
            canonical,
            compatibility.manifest_root,
            plan_root,
            receipts,
            restarted_receipt,
            driver_checkpoint_root,
            governance_result,
            commit_outcome,
            disposition,
            delivery,
            publish,
            execute,
        )
        trace_checkpoint = _trace_projection(canonical, steps)
        steps = _append_step(
            steps,
            "trace",
            SCOPED_TRACE_CHECKPOINT_VERSION_V2,
            trace_checkpoint.checkpoint_root,
        )
        return RuntimeTranscriptResultV1(
            implementation_id=self.implementation_id,
            request_root=canonical.request_root,
            disposition=disposition,
            compatibility_manifest_root=compatibility.manifest_root,
            compatibility_report_version=RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
            compatibility_ok=report.ok,
            plan_document=plan_document,
            plan_root=plan_root,
            driver_receipts=receipts,
            driver_restarted_receipt=restarted_receipt,
            driver_checkpoint_wire=driver_checkpoint_wire,
            driver_checkpoint_root=driver_checkpoint_root,
            governance_result=governance_result,
            commit_outcome=commit_outcome,
            trace_checkpoint=trace_checkpoint,
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
        store = InMemoryDriverInvocationStoreV2.from_checkpoint(
            checkpoint_from_wire(checkpoint_wire)
        )
        return store.get(scope_ref, driver_id, idempotency_key)

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        self._ensure_observation_maps()
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
        self._ensure_observation_maps()
        return self._certificate_states.get((request_root, scope_ref))

    def _ensure_observation_maps(self) -> None:
        if not hasattr(self, "_recovered_readers"):
            self._recovered_readers = {}
        if not hasattr(self, "_certificate_states"):
            self._certificate_states = {}
        if not hasattr(self, "_recovery_source_readers"):
            self._recovery_source_readers = {}


def _canonical_request(value: RuntimeTranscriptRequestV1) -> RuntimeTranscriptRequestV1:
    if type(value) is not RuntimeTranscriptRequestV1:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime adapter requires the exact transcript request"
        )
    canonical = RuntimeTranscriptRequestV1.from_dict(value.to_dict())
    if value != canonical:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime adapter rejected a mutated transcript request"
        )
    return canonical


def _plan(request: RuntimeTranscriptRequestV1) -> tuple[dict[str, object], str]:
    capability = read_capability_manifest(
        request.capability.to_dict(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    descriptor = request.capability.drivers[0]
    probe = DriverProbeSnapshot(
        driver_id=descriptor.id,
        available=True,
        version=descriptor.version,
        capabilities=tuple(descriptor.capabilities),
    )
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
        driver_probe_snapshots=(probe,),
    )
    document = OSPlanDocument(plan).to_dict()
    return document, document_root("kernel-plan", document)


def _record_driver(
    request: RuntimeTranscriptRequestV1,
) -> tuple[tuple[DriverInvocationReceiptV2, ...], DriverInvocationReceiptV2, str, str]:
    validate_driver_invocation_binding_v2(request.driver_request, request.driver_result)
    store: DriverInvocationStoreV2 = InMemoryDriverInvocationStoreV2()
    receipts = [store.record(request.driver_request, request.driver_result)]
    if request.control.repeat_invocation:
        receipts.append(store.record(request.driver_request, request.driver_result))
    checkpoint = store.checkpoint()
    restarted = InMemoryDriverInvocationStoreV2.from_checkpoint(checkpoint)
    persisted = restarted.get(
        request.driver_request.scope_ref,
        request.driver_request.driver_id,
        request.driver_request.idempotency_key,
    )
    restarted_receipt = restarted.record(
        request.driver_request,
        request.driver_result,
    )
    if persisted != receipts[0] or restarted_receipt != receipts[0]:
        raise RuntimeIntegrationTranscriptErrorV1(
            "driver checkpoint did not preserve invocation idempotency"
        )
    checkpoint_root = "sha256:" + sha256(checkpoint).hexdigest()
    return (
        tuple(receipts),
        restarted_receipt,
        checkpoint_to_wire(checkpoint),
        checkpoint_root,
    )


def _control_disposition(
    request: RuntimeTranscriptRequestV1,
) -> RuntimeTranscriptDispositionV1:
    if request.control.wall_clock_timed_out:
        return RuntimeTranscriptDispositionV1.RUNTIME_TIMED_OUT
    if request.control.cancel_requested:
        return RuntimeTranscriptDispositionV1.RUNTIME_CANCELLED
    return RuntimeTranscriptDispositionV1.COMPLETED


def _govern(
    request: RuntimeTranscriptRequestV1,
) -> tuple[
    BaselineOutputResultV2 | None,
    bool,
    GovernanceStateReaderV2 | None,
    GovernanceStateReaderV2 | None,
]:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    store = adapter.create_store_v2((request.authority_domain,))
    capability = _initialize_governance(store, request)
    baseline = request.baseline_request
    if baseline is None:
        return None, False, None, None
    result = _commit_baseline(store, capability, baseline, request)
    if request.control.inject_cas_conflict:
        contender = request.contender_request
        if contender is None:
            raise RuntimeIntegrationTranscriptErrorV1(
                "CAS conflict observation lacks its contender"
            )
        return (
            _commit_baseline(store, capability, contender, request),
            False,
            None,
            None,
        )
    if not request.control.recover_after_commit:
        return result, False, None, None
    _advance_before_recovery(store, capability, request)
    restarted = adapter.restart_store_v2(store)
    advance_runtime_recovery_witness_v1(
        store,
        request.authority_domain,
        request_root=request.request_root,
    )
    recovered = recover_baseline_output_result_v2(
        baseline,
        state_reader=restarted,
    )
    return recovered, True, restarted, store


def _initialize_governance(
    store: GovernanceStateStoreV2,
    request: RuntimeTranscriptRequestV1,
) -> GovernanceIssuerCapabilityV2:
    activation = activate_governance_issuer_grant_v2(
        store,
        request.authority_domain,
        request.issuer_grant,
        f"transition:activate:{request.scenario_id}",
        1,
    )
    if activation.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeIntegrationTranscriptErrorV1("issuer grant activation failed")
    capability = bind_governance_issuer_capability_v2(
        store,
        request.authority_domain,
        request.issuer_grant,
        request.scope.run_id,
        2,
    )
    for signal in request.verified_signal_requests:
        session = open_governance_authority_session_v2(capability, signal)
        attempt = commit_verified_signal_v2(signal, authority_session=session)
        if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
            raise RuntimeIntegrationTranscriptErrorV1(
                "verified driver evidence did not commit"
            )
    return capability


def _advance_before_recovery(
    store: GovernanceStateStoreV2,
    capability: GovernanceIssuerCapabilityV2,
    request: RuntimeTranscriptRequestV1,
) -> None:
    baseline = request.baseline_request
    assert baseline is not None
    if request.control.advance_permission_before_recovery:
        advance_runtime_dependency_head_v1(
            store,
            request.authority_domain,
            stream_ref=baseline.permission_stream_ref,
            transition_id=(
                f"transition:runtime:permission-successor:{request.scenario_id}"
            ),
        )
    elif request.control.advance_stop_before_recovery:
        advance_runtime_dependency_head_v1(
            store,
            request.authority_domain,
            stream_ref=baseline.stop_stream_ref,
            transition_id=f"transition:runtime:stop-successor:{request.scenario_id}",
        )
    elif request.successor_request is not None:
        _commit_baseline(store, capability, request.successor_request, request)


def _commit_baseline(
    store: GovernanceStateStoreV2,
    capability: GovernanceIssuerCapabilityV2,
    baseline: BaselineOutputRequestV2,
    transcript: RuntimeTranscriptRequestV1,
) -> BaselineOutputResultV2:
    if (
        not transcript.control.omit_permission
        or baseline is transcript.successor_request
    ):
        _issue_baseline_permission(
            capability,
            baseline,
            require_commit=baseline is not transcript.contender_request,
        )
    output_session = open_baseline_output_authority_session_v2(
        capability,
        baseline,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    return evaluate_and_commit_baseline_output_v2(
        baseline,
        authority_session=output_session,
    )


def _issue_baseline_permission(
    capability: GovernanceIssuerCapabilityV2,
    baseline: BaselineOutputRequestV2,
    *,
    require_commit: bool = True,
) -> None:
    permission_session = open_baseline_output_authority_session_v2(
        capability,
        baseline,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    attempt = issue_action_permission_v2(
        baseline,
        authority_session=permission_session,
    )
    if (
        require_commit
        and attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "baseline action permission did not commit"
        )


def _action_projection(
    request: RuntimeTranscriptRequestV1,
    disposition: RuntimeTranscriptDispositionV1,
    result: BaselineOutputResultV2 | None,
    advisory: CommitDecisionOutcomeV2 | None,
    certificate_state: VerifiedCommitCertificateStateV2 | None,
) -> tuple[bool, bool, bool]:
    if disposition is not RuntimeTranscriptDispositionV1.COMPLETED:
        return False, False, False
    if result is None:
        delivery = bool(advisory is not None and advisory.delivery_eligible)
        return delivery, False, False
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
    observed = _observe_certificate_state_v1(
        certificate_state,
        observation.observed_finality,
    )
    if observed is None or not observed.is_current or not observed.projection_matches:
        return False
    snapshot = observed.snapshot
    body = snapshot.certificate.body
    outcome = observation.outcome
    return (
        body.candidate_ref == outcome.candidate_ref
        and body.claim_root == outcome.claim_root
        and body.output_contract_root == outcome.output_contract_root
        and body.output_payload_root == outcome.output_payload_root
    )


def _base_steps(
    request: RuntimeTranscriptRequestV1,
    compatibility_root: str,
    plan_root: str,
    receipts: tuple[DriverInvocationReceiptV2, ...],
    restarted_receipt: DriverInvocationReceiptV2,
    driver_checkpoint_root: str,
    result: BaselineOutputResultV2 | None,
    advisory: CommitDecisionOutcomeV2 | None,
    disposition: RuntimeTranscriptDispositionV1,
    delivery: bool,
    publish: bool,
    execute: bool,
) -> tuple[RuntimeTranscriptStepV1, ...]:
    steps: tuple[RuntimeTranscriptStepV1, ...] = ()
    steps = _append_step(
        steps,
        "compatibility",
        "pheroos-runtime-compatibility-manifest-v1",
        compatibility_root,
    )
    steps = _append_step(
        steps,
        "scope",
        request.scope.to_dict()["scope_version"],
        request.scope.scope_ref,
    )
    steps = _append_step(
        steps,
        "protocol",
        request.capability.protocol.protocol_version,
        request.capability.manifest_root,
    )
    steps = _append_step(steps, "kernel", KERNEL_PLAN_VERSION_V2, plan_root)
    driver_root = document_root(
        "driver-stage",
        {
            "request_digest": request.driver_request.request_digest,
            "result_digest": request.driver_result.result_digest,
            "receipt_roots": [item.receipt_digest for item in receipts],
            "restarted_receipt_root": restarted_receipt.receipt_digest,
            "checkpoint_root": driver_checkpoint_root,
        },
    )
    steps = _append_step(
        steps, "drivers", DRIVER_INVOCATION_RECEIPT_VERSION_V2, driver_root
    )
    governance_root, governance_version = _governance_artifact(
        request, result, advisory, disposition
    )
    steps = _append_step(steps, "governance", governance_version, governance_root)
    delivery_root = document_root(
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
    return _append_step(
        steps, "output", "pheroos-runtime-output-projection-v1", delivery_root
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


def _governance_artifact(
    request: RuntimeTranscriptRequestV1,
    result: BaselineOutputResultV2 | None,
    advisory: CommitDecisionOutcomeV2 | None,
    disposition: RuntimeTranscriptDispositionV1,
) -> tuple[str, str]:
    if result is not None and advisory is not None:
        return (
            document_root(
                "governance-composite",
                {
                    "baseline_result_root": result.result_root,
                    "commit_outcome_root": advisory.outcome_root,
                },
            ),
            "pheroos-runtime-governance-composite-v1",
        )
    if result is not None:
        return result.result_root, result.schema
    if advisory is not None:
        return advisory.outcome_root, advisory.schema
    return (
        document_root("runtime-control", request.control.to_dict()),
        request.control.version + ":" + disposition.value,
    )


def _append_step(
    steps: tuple[RuntimeTranscriptStepV1, ...],
    layer: str,
    version: str,
    root: str,
) -> tuple[RuntimeTranscriptStepV1, ...]:
    predecessor = "" if not steps else steps[-1].step_root
    return (
        *steps,
        RuntimeTranscriptStepV1(
            sequence=len(steps),
            layer=layer,
            artifact_version=version,
            artifact_root=root,
            predecessor_root=predecessor,
        ),
    )


def _trace_projection(
    request: RuntimeTranscriptRequestV1,
    steps: tuple[RuntimeTranscriptStepV1, ...],
) -> ScopedTraceCheckpointV2:
    store: ScopedTraceStoreV2 = InMemoryScopedTraceStoreV2()
    for step in steps:
        event = TraceEvent(
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
        )
        envelope = ScopedTraceEvent(
            scope_ref=request.scope.scope_ref,
            stream=_TRACE_STREAM,
            transition_id=f"transition:runtime:{request.scenario_id}:{step.sequence}",
            trace_id=f"trace:runtime:{request.scenario_id}:{step.sequence}",
            event=event,
        )
        store.append_scoped_v2(envelope)
    checkpoint = store.checkpoint_v2()
    restarted = store.restart_v2(checkpoint)
    return restarted.checkpoint_v2()


__all__ = [
    "ReferenceRuntimeIntegrationAdapterV1",
]
