"""Independent invariant checks for Runtime Integration transcript v1 results."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from pheroos.conformance._runtime_compatibility_codec import (
    RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1,
    RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
)
from pheroos.conformance._runtime_compatibility_evaluation import (
    evaluate_runtime_compatibility_v1,
)
from pheroos.conformance._runtime_compatibility_catalog import (
    build_runtime_compatibility_manifest_v1,
)
from pheroos.drivers import (
    DRIVER_INVOCATION_RECEIPT_VERSION_V2,
    DRIVER_INVOCATION_CHECKPOINT_MAX_BYTES_V2,
    DriverInvocationReceiptV2,
)
from pheroos.governance import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputTerminalStatusV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionOutcomeKindV2,
)
from pheroos.kernel import (
    KERNEL_PLAN_VERSION_V2,
    InputEnvelope,
    OSKernel,
    OSPlanDocument,
    os_plan_from_dict,
)
from pheroos.drivers import DriverProbeSnapshot
from pheroos.protocol import CAPABILITY_SCHEMA_V3, read_capability_manifest
from pheroos.trace import SCOPED_TRACE_CHECKPOINT_VERSION_V2

from pheroos.conformance._runtime_integration_codec import (
    checkpoint_from_wire,
    document_root,
)
from pheroos.conformance._runtime_integration_contracts import (
    RuntimeTranscriptDispositionV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    RuntimeTranscriptStepV1,
)


_LAYERS = (
    "compatibility",
    "scope",
    "protocol",
    "kernel",
    "drivers",
    "governance",
    "output",
    "trace",
)


def verify_runtime_transcript_v1(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
) -> tuple[str, ...]:
    """Recompute bindings and ordering without trusting adapter-side decisions."""

    problems: list[str] = []
    if result.request_root != request.request_root:
        problems.append("request_root")
    _verify_compatibility(request, result, problems)
    _verify_plan(request, result, problems)
    _verify_driver(request, result, problems)
    _verify_governance(request, result, problems)
    _verify_steps(request, result, problems)
    _verify_trace(request, result, problems)
    return tuple(problems)


def _verify_compatibility(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    manifest = build_runtime_compatibility_manifest_v1()
    report = evaluate_runtime_compatibility_v1(
        manifest,
        request.compatibility_claim,
    )
    if (
        result.compatibility_manifest_root != manifest.manifest_root
        or result.compatibility_report_version
        != RUNTIME_COMPATIBILITY_REPORT_VERSION_V1
        or result.compatibility_ok is not report.ok
        or not report.ok
    ):
        problems.append("compatibility")


def _verify_plan(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    try:
        selected = os_plan_from_dict(result.plan_document)
    except Exception:
        problems.append("kernel_plan_wire")
        return
    plan = selected.plan
    descriptor = request.capability.drivers[0]
    expected_capability = read_capability_manifest(
        request.capability.to_dict(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    expected_plan = OSKernel().plan(
        InputEnvelope(
            request=f"runtime transcript {request.scenario_id}",
            tenant_id=request.scope.tenant_id,
            metadata={
                "request_id": request.scope.request_id,
                "run_id": request.scope.run_id,
            },
        ),
        [expected_capability],
        driver_probe_snapshots=(
            DriverProbeSnapshot(
                driver_id=descriptor.id,
                available=True,
                version=descriptor.version,
                capabilities=tuple(descriptor.capabilities),
            ),
        ),
    )
    expected_document = OSPlanDocument(expected_plan).to_dict()
    if (
        selected.plan_version != KERNEL_PLAN_VERSION_V2
        or dict(result.plan_document) != expected_document
        or result.plan_root != document_root("kernel-plan", dict(result.plan_document))
        or plan.scope_ref != request.scope.scope_ref
        or plan.tenant_id != request.scope.tenant_id
        or plan.run_id != request.scope.run_id
        or plan.request_id != request.scope.request_id
        or not plan.runtime_ready
        or plan.degraded
        or len(plan.driver_exposures) != 1
        or plan.driver_exposures[0].driver_id != request.driver_request.driver_id
    ):
        problems.append("kernel_plan_binding")
    if (
        request.capability.protocol.collective_decision_policy is not None
        or request.capability.protocol.collective_commit_policy is not None
    ):
        problems.append("baseline_profile_upgrade")


def _verify_driver(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    expected = DriverInvocationReceiptV2.for_result(request.driver_result)
    count = 2 if request.control.repeat_invocation else 1
    if (
        len(result.driver_receipts) != count
        or any(item != expected for item in result.driver_receipts)
        or result.driver_restarted_receipt != expected
    ):
        problems.append("driver_receipts")
    try:
        wire = checkpoint_from_wire(result.driver_checkpoint_wire)
        checkpoint = "sha256:" + sha256(wire).hexdigest()
    except Exception:
        problems.append("driver_checkpoint_wire")
        return
    if (
        result.driver_checkpoint_root != checkpoint
        or not wire
        or len(wire) > DRIVER_INVOCATION_CHECKPOINT_MAX_BYTES_V2
    ):
        problems.append("driver_checkpoint")


def _verify_governance(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    expected_disposition = _expected_disposition(request)
    if result.disposition is not expected_disposition:
        problems.append("runtime_disposition")
    expected_diagnostics = tuple(
        label
        for enabled, label in (
            (request.control.wall_clock_timed_out, "wall_clock_timed_out"),
            (request.control.cancel_requested, "cancel_requested"),
        )
        if enabled
    )
    if result.diagnostics != expected_diagnostics:
        problems.append("runtime_diagnostics")
    if expected_disposition is not RuntimeTranscriptDispositionV1.COMPLETED:
        _verify_non_authoritative_control(result, problems)
        return
    if request.commit_observation is not None:
        _verify_commit_outcome(request, result, problems)
        if request.baseline_request is None:
            return
    _verify_baseline_result(request, result, problems)


def _expected_disposition(
    request: RuntimeTranscriptRequestV1,
) -> RuntimeTranscriptDispositionV1:
    if request.control.wall_clock_timed_out:
        return RuntimeTranscriptDispositionV1.RUNTIME_TIMED_OUT
    if request.control.cancel_requested:
        return RuntimeTranscriptDispositionV1.RUNTIME_CANCELLED
    return RuntimeTranscriptDispositionV1.COMPLETED


def _verify_non_authoritative_control(
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    if (
        result.governance_result is not None
        or result.commit_outcome is not None
        or result.delivery_eligible
        or result.publication_authorized
        or result.execution_authorized
        or result.recovered_after_commit
    ):
        problems.append("runtime_control_created_authority")


def _verify_commit_outcome(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    outcome = result.commit_outcome
    observation = request.commit_observation
    if (
        observation is None
        or outcome != observation.outcome
        or outcome is None
        or not outcome.delivery_eligible
        or outcome.publication_eligible
        or outcome.execution_eligible
        or not result.delivery_eligible
    ):
        problems.append("commit_outcome_projection")
        return
    if outcome.kind is CommitDecisionOutcomeKindV2.ADVISORY:
        if (
            result.governance_result is not None
            or result.publication_authorized
            or result.execution_authorized
            or observation.observed_finality is not None
            or observation.successor_finality is not None
        ):
            problems.append("advisory_certificate_material")
        return
    observed = observation.observed_finality
    successor = observation.successor_finality
    if (
        outcome.kind is not CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
        or result.governance_result is None
        or observed is None
        or outcome.finality_root != observed.projection_root
    ):
        problems.append("stale_certificate_currentness")
        return
    if successor is not None and (
        observed.stream_ref != successor.stream_ref
        or successor.revision != observed.revision + 1
        or observed.head_root == successor.head_root
        or observed.transition_id == successor.transition_id
    ):
        problems.append("stale_certificate_currentness")


def _verify_baseline_result(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    governance = result.governance_result
    baseline = (
        request.contender_request
        if request.control.inject_cas_conflict
        else request.baseline_request
    )
    if governance is None or baseline is None:
        problems.append("baseline_result_missing")
        return
    if (
        governance.request_root != baseline.request_root
        or governance.scope_ref != request.scope.scope_ref
        or governance.domain_root != request.authority_domain.domain_root
        or governance.output_payload_root != baseline.output_payload_root
    ):
        problems.append("baseline_result_binding")
    status = _expected_terminal_status(request)
    if (
        governance.terminal_status is not status
        or governance.delivery_disposition
        is not BaselineOutputDeliveryDispositionV2.DELIVERABLE
        or not result.delivery_eligible
    ):
        problems.append("baseline_delivery")
    _verify_commit_position(request, governance, problems)
    _verify_stale_dependencies(request, governance, problems)
    baseline_action = _baseline_action_authorized(request, governance)
    effect = baseline.effect
    if not _certificate_action_gate_is_deferred(request) and (
        result.publication_authorized is not (baseline_action and effect == "publish")
        or result.execution_authorized is not (baseline_action and effect == "execute")
    ):
        problems.append("action_projection")
    authorization = governance.authorization
    if baseline_action:
        if (
            authorization is None
            or authorization.effect != effect
            or authorization.action_ref != baseline.action_ref
            or authorization.target_ref != baseline.target_ref
            or authorization.scope_ref != baseline.scope_ref
            or authorization.domain_root != baseline.domain_root
            or authorization.request_root != baseline.request_root
        ):
            problems.append("action_authority_binding")
    elif authorization is not None:
        problems.append("denied_action_exposed_authority")
    if result.recovered_after_commit is not request.control.recover_after_commit:
        problems.append("recovery_observation")


def _expected_terminal_status(
    request: RuntimeTranscriptRequestV1,
) -> BaselineOutputTerminalStatusV2:
    if request.control.inject_cas_conflict or request.control.omit_permission:
        return BaselineOutputTerminalStatusV2.INVALID
    baseline = request.baseline_request
    assert baseline is not None
    if any(bool(item["blocked"]) for item in baseline.stop_resolutions):
        return BaselineOutputTerminalStatusV2.BLOCKED
    threshold = baseline.manifest.quorum_policy.commit_threshold
    if len(baseline.verified_signals) < threshold:
        return BaselineOutputTerminalStatusV2.SAFE_FALLBACK
    return BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT


def _verify_commit_position(
    request: RuntimeTranscriptRequestV1,
    governance: Any,
    problems: list[str],
) -> None:
    if request.control.inject_cas_conflict:
        failure = governance.commit_attempt.failure
        if (
            governance.disposition is not GovernanceCommitDispositionV2.INVALID
            or failure is None
            or failure.code.value != "governance_transition_conflict"
        ):
            problems.append("cas_conflict")
        return
    if request.control.omit_permission:
        if governance.disposition is not GovernanceCommitDispositionV2.INVALID:
            problems.append("invalid_without_permission")
        return
    expected_position = (
        GovernanceCommitPositionV2.SUPERSEDED
        if request.control.supersede_before_recovery
        else GovernanceCommitPositionV2.CURRENT
    )
    if (
        governance.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or governance.position is not expected_position
    ):
        problems.append("commit_position")


def _baseline_action_authorized(
    request: RuntimeTranscriptRequestV1,
    governance: Any,
) -> bool:
    if (
        request.control.inject_cas_conflict
        or request.control.omit_permission
        or request.control.supersede_before_recovery
        or request.control.advance_permission_before_recovery
        or request.control.advance_stop_before_recovery
    ):
        return False
    return bool(
        governance.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
        and governance.authorization is not None
    )


def _certificate_action_gate_is_deferred(
    request: RuntimeTranscriptRequestV1,
) -> bool:
    observation = request.commit_observation
    return (
        observation is not None
        and observation.outcome.kind is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    )


def _verify_stale_dependencies(
    request: RuntimeTranscriptRequestV1,
    governance: Any,
    problems: list[str],
) -> None:
    if not (
        request.control.advance_permission_before_recovery
        or request.control.advance_stop_before_recovery
    ):
        return
    transition = governance.commit_attempt.committed_transition
    baseline = request.baseline_request
    if transition is None or baseline is None:
        problems.append("stale_dependency_history")
        return
    observed_streams = {item.stream_ref for item in transition.batch.read_set.entries}
    if (
        governance.position is not GovernanceCommitPositionV2.CURRENT
        or governance.action_disposition is not BaselineOutputActionDispositionV2.DENIED
        or governance.authorization is not None
        or baseline.permission_stream_ref not in observed_streams
        or baseline.stop_stream_ref not in observed_streams
    ):
        problems.append("stale_dependency_gate")


def _verify_steps(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    if tuple(item.layer for item in result.steps) != _LAYERS:
        problems.append("step_layers")
        return
    expected = _expected_steps(request, result)
    if result.steps != expected:
        problems.append("step_chain")


def _expected_steps(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
) -> tuple[RuntimeTranscriptStepV1, ...]:
    values = (
        (
            "compatibility",
            RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1,
            result.compatibility_manifest_root,
        ),
        ("scope", request.scope.to_dict()["scope_version"], request.scope.scope_ref),
        (
            "protocol",
            request.capability.protocol.protocol_version,
            request.capability.manifest_root,
        ),
        ("kernel", KERNEL_PLAN_VERSION_V2, result.plan_root),
        (
            "drivers",
            DRIVER_INVOCATION_RECEIPT_VERSION_V2,
            _driver_stage_root(request, result),
        ),
        ("governance", *_governance_stage(request, result)),
        (
            "output",
            "pheroos-runtime-output-projection-v1",
            _output_stage_root(request, result),
        ),
        (
            "trace",
            SCOPED_TRACE_CHECKPOINT_VERSION_V2,
            result.trace_checkpoint.checkpoint_root,
        ),
    )
    steps: tuple[RuntimeTranscriptStepV1, ...] = ()
    for layer, version, root in values:
        steps = (
            *steps,
            RuntimeTranscriptStepV1(
                sequence=len(steps),
                layer=layer,
                artifact_version=version,
                artifact_root=root,
                predecessor_root="" if not steps else steps[-1].step_root,
            ),
        )
    return steps


def _driver_stage_root(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
) -> str:
    return document_root(
        "driver-stage",
        {
            "request_digest": request.driver_request.request_digest,
            "result_digest": request.driver_result.result_digest,
            "receipt_roots": [item.receipt_digest for item in result.driver_receipts],
            "restarted_receipt_root": (result.driver_restarted_receipt.receipt_digest),
            "checkpoint_root": result.driver_checkpoint_root,
        },
    )


def _governance_stage(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
) -> tuple[str, str]:
    if result.governance_result is not None and result.commit_outcome is not None:
        return (
            "pheroos-runtime-governance-composite-v1",
            document_root(
                "governance-composite",
                {
                    "baseline_result_root": result.governance_result.result_root,
                    "commit_outcome_root": result.commit_outcome.outcome_root,
                },
            ),
        )
    if result.governance_result is not None:
        return result.governance_result.schema, result.governance_result.result_root
    if result.commit_outcome is not None:
        return result.commit_outcome.schema, result.commit_outcome.outcome_root
    return (
        request.control.version + ":" + result.disposition.value,
        document_root("runtime-control", request.control.to_dict()),
    )


def _output_stage_root(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
) -> str:
    governance_root = result.steps[5].artifact_root
    baseline = (
        request.contender_request
        if request.control.inject_cas_conflict
        else request.baseline_request
    )
    return document_root(
        "delivery-projection",
        {
            "delivery_eligible": result.delivery_eligible,
            "publication_authorized": result.publication_authorized,
            "execution_authorized": result.execution_authorized,
            "governance_root": governance_root,
            "request_action_ref": "" if baseline is None else baseline.action_ref,
            "request_effect": "" if baseline is None else baseline.effect,
            "action_authority_root": _action_authority_root(result),
        },
    )


def _action_authority_root(result: RuntimeTranscriptResultV1) -> str:
    governance = result.governance_result
    if (
        governance is None
        or governance.authorization is None
        or not (result.publication_authorized or result.execution_authorized)
    ):
        return ""
    return governance.authorization.permission_root


def _verify_trace(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    problems: list[str],
) -> None:
    records = result.trace_checkpoint.records
    projected_steps = result.steps[:-1]
    if result.trace_checkpoint.retirements or len(records) != len(projected_steps):
        problems.append("trace_count")
        return
    for record, step in zip(records, projected_steps, strict=True):
        event = record.event
        lineage = event.event.lineage
        expected_lineage = {
            "request_root": request.request_root,
            "sequence": step.sequence,
            "artifact_version": step.artifact_version,
            "artifact_root": step.artifact_root,
            "predecessor_root": step.predecessor_root,
            "step_root": step.step_root,
        }
        if (
            record.scope_ref != request.scope.scope_ref
            or record.stream != "runtime-integration-v1"
            or record.sequence != step.sequence
            or event.event.event_type
            != f"ext.pheroos.runtime_integration_v1.{step.layer}"
            or dict(lineage) != expected_lineage
            or event.event.protocol_id != request.capability.protocol.id
            or event.event.target != request.scenario_id
            or event.event.reason
            != "project provider-free runtime integration transcript"
            or event.transition_id
            != f"transition:runtime:{request.scenario_id}:{step.sequence}"
            or event.trace_id != f"trace:runtime:{request.scenario_id}:{step.sequence}"
        ):
            problems.append(f"trace_projection:{step.sequence}")


__all__ = ["verify_runtime_transcript_v1"]
