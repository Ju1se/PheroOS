from __future__ import annotations

from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
import base64
import importlib.util
import inspect
import sys
from types import SimpleNamespace
from typing import Any, cast, get_args, get_type_hints

import pytest

from pheroos.conformance.runtime_integration import (
    RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1,
    RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
    RUNTIME_INTEGRATION_CONTROL_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1,
    ReferenceRuntimeIntegrationAdapterV1,
    RuntimeCommitObservationV1,
    RuntimeControlInputV1,
    RuntimeIntegrationAdapterV1,
    RuntimeIntegrationTranscriptErrorV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    RuntimeTranscriptStepV1,
    build_runtime_integration_request_v1,
    run_runtime_integration_conformance_v1,
)
from pheroos.conformance._runtime_integration_reference import (
    _append_step,
    _base_steps,
    _trace_projection,
)
from pheroos.conformance._runtime_integration_certificate import (
    build_recovered_certificate_states_v1,
    certificate_state_matches_projection_v1,
)
from pheroos.conformance._runtime_integration_dependency import (
    runtime_recovery_witness_stream_ref_v1,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.runtime_integration_v1_contract import (
    _exercise,
    _malformed_request,
)
from pheroos.governance import (
    BaselineOutputActionDispositionV2,
    BaselineOutputTerminalStatusV2,
    CommitDecisionOutcomeKindV2,
    GovernanceCommitPositionV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
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


def _clone_result(
    result: RuntimeTranscriptResultV1,
    implementation_id: str,
    **changes: object,
) -> RuntimeTranscriptResultV1:
    payload = result.to_dict()
    payload.update(changes)
    payload["implementation_id"] = implementation_id
    payload["result_root"] = ""
    return RuntimeTranscriptResultV1.from_dict(payload)


class _MutationAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-mutation-v1"

    def _reference(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = super().execute_transcript_v1(request)
        return _clone_result(result, self.implementation_id)


class EchoAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-echo-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        return cast(RuntimeTranscriptResultV1, request)


class ConstantAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-constant-v1"

    def __init__(self) -> None:
        self._result = self._reference(
            build_runtime_integration_request_v1("constant-source")
        )

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        del request
        return self._result


class MalformedAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-malformed-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        del request
        return cast(RuntimeTranscriptResultV1, object())


class OutOfOrderAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-out-of-order-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        selected = (result.steps[1], result.steps[0], *result.steps[2:])
        steps: tuple[RuntimeTranscriptStepV1, ...] = ()
        for item in selected:
            steps = (
                *steps,
                RuntimeTranscriptStepV1(
                    sequence=len(steps),
                    layer=item.layer,
                    artifact_version=item.artifact_version,
                    artifact_root=item.artifact_root,
                    predecessor_root="" if not steps else steps[-1].step_root,
                ),
            )
        return _clone_result(
            result,
            self.implementation_id,
            steps=[item.to_dict() for item in steps],
        )


class TimeoutIgnoringAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-timeout-ignoring-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        if not (
            request.control.wall_clock_timed_out or request.control.cancel_requested
        ):
            return self._reference(request)
        payload = request.to_dict()
        payload["control"] = RuntimeControlInputV1().to_dict()
        payload["request_root"] = ""
        uninterrupted = RuntimeTranscriptRequestV1.from_dict(payload)
        return self._reference(uninterrupted)


class CrossRequestStateAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-cross-request-state-v1"

    def __init__(self) -> None:
        self._cached: RuntimeTranscriptResultV1 | None = None

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        if self._cached is None:
            self._cached = self._reference(request)
        return self._cached


class CrossScopeAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-cross-scope-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        del request
        return self._reference(
            build_runtime_integration_request_v1("cross-scope-source")
        )


class SelfRootKernelAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-self-root-kernel-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        plan = dict(result.plan_document)
        plan["request_id"] = request.scope.request_id + ":forged"
        plan_root = _document_root("kernel-plan", plan)
        return _clone_result(
            result,
            self.implementation_id,
            plan_document=plan,
            plan_root=plan_root,
        )


class CheckpointLiarAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-checkpoint-liar-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        checkpoint = b"not-a-store-checkpoint"
        return _clone_result(
            result,
            self.implementation_id,
            driver_checkpoint_wire=base64.urlsafe_b64encode(checkpoint).decode("ascii"),
            driver_checkpoint_root="sha256:" + sha256(checkpoint).hexdigest(),
        )


class StaleCertificateAuthorizerAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-stale-certificate-authorizer-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        observation = request.commit_observation
        if (
            observation is not None
            and observation.outcome.kind is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
        ):
            return _clone_result(
                result,
                self.implementation_id,
                publication_authorized=True,
            )
        return result


class NoRestartRecoveryAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-no-restart-recovery-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        if not (
            request.control.recover_after_commit and request.successor_request is None
        ):
            return self._reference(request)
        payload = request.to_dict()
        payload["control"] = RuntimeControlInputV1().to_dict()
        payload["request_root"] = ""
        uninterrupted = RuntimeTranscriptRequestV1.from_dict(payload)
        result = self._reference(uninterrupted)
        steps = _base_steps(
            request,
            result.compatibility_manifest_root,
            result.plan_root,
            result.driver_receipts,
            result.driver_restarted_receipt,
            result.driver_checkpoint_root,
            result.governance_result,
            result.commit_outcome,
            result.disposition,
            result.delivery_eligible,
            result.publication_authorized,
            result.execution_authorized,
        )
        trace = _trace_projection(request, steps)
        steps = _append_step(
            steps,
            "trace",
            trace.version,
            trace.checkpoint_root,
        )
        return _clone_result(
            result,
            self.implementation_id,
            request_root=request.request_root,
            recovered_after_commit=True,
            trace_checkpoint=trace.to_dict(),
            steps=[item.to_dict() for item in steps],
        )


class LiveGovernanceReaderAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-live-governance-reader-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        return self._reference(request)

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        self._ensure_observation_maps()
        return self._recovery_source_readers.get((request_root, scope_ref))


class UnrelatedCurrentCertificateAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-unrelated-current-certificate-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        observation = request.commit_observation
        if observation is not None and observation.successor_finality is None:
            self._certificate_states[
                (request.request_root, request.scope.scope_ref)
            ] = build_recovered_certificate_states_v1(
                ReferenceGovernanceStateStoreConformanceAdapterV2(),
                label=request.scenario_id + ":unrelated-current",
                scope_ref=request.scope.scope_ref,
                with_successor=False,
            )
        return result


class UnrelatedStaleCertificatePairAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-unrelated-stale-certificate-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        observation = request.commit_observation
        if observation is not None and observation.successor_finality is not None:
            self._certificate_states[
                (request.request_root, request.scope.scope_ref)
            ] = build_recovered_certificate_states_v1(
                ReferenceGovernanceStateStoreConformanceAdapterV2(),
                label=request.scenario_id + ":unrelated-stale",
                scope_ref=request.scope.scope_ref,
                with_successor=True,
            )
        return result


class StalePermissionIgnoringAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-stale-permission-ignoring-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        if request.control.advance_permission_before_recovery:
            return _clone_result(
                result,
                self.implementation_id,
                publication_authorized=True,
            )
        return result


class StaleStopIgnoringAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-stale-stop-ignoring-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        if request.control.advance_stop_before_recovery:
            return _clone_result(
                result,
                self.implementation_id,
                publication_authorized=True,
            )
        return result


class EffectCouplingAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-effect-coupling-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        if result.publication_authorized:
            return _clone_result(
                result,
                self.implementation_id,
                publication_authorized=False,
                execution_authorized=True,
            )
        if result.execution_authorized:
            return _clone_result(
                result,
                self.implementation_id,
                execution_authorized=False,
                publication_authorized=True,
            )
        if result.delivery_eligible:
            return _clone_result(
                result,
                self.implementation_id,
                delivery_eligible=False,
            )
        return result


class NonCanonicalTupleAdapterV1(_MutationAdapter):
    implementation_id = "tests-runtime-integration-noncanonical-tuple-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = self._reference(request)
        object.__setattr__(result, "diagnostics", list(result.diagnostics))
        return result


class WrongVersionAdapterV1(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-wrong-version-v1"
    conformance_version = "pheroos-runtime-integration-conformance-v999"


class BlankImplementationAdapterV1(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = ""


class NonCanonicalImplementationAdapterV1(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = " tests-runtime-integration-noncanonical-id "


@pytest.mark.parametrize(
    ("adapter", "expected_detail"),
    [
        (EchoAdapterV1(), "result_type"),
        (ConstantAdapterV1(), "request_root"),
        (MalformedAdapterV1(), "result_type"),
        (OutOfOrderAdapterV1(), "step_layers"),
        (TimeoutIgnoringAdapterV1(), "runtime_control_created_authority"),
        (CrossRequestStateAdapterV1(), "request_root"),
        (CrossScopeAdapterV1(), "request_root"),
        (SelfRootKernelAdapterV1(), "kernel_plan_binding"),
        (CheckpointLiarAdapterV1(), "checkpoint_reader"),
        (
            StaleCertificateAuthorizerAdapterV1(),
            "certificate_currentness_action_gate",
        ),
        (NoRestartRecoveryAdapterV1(), "governance_recovery_reader"),
        (LiveGovernanceReaderAdapterV1(), "governance_checkpoint_reopen"),
        (
            UnrelatedCurrentCertificateAdapterV1(),
            "certificate_recovery_binding",
        ),
        (
            UnrelatedStaleCertificatePairAdapterV1(),
            "certificate_recovery_binding",
        ),
        (
            StalePermissionIgnoringAdapterV1(),
            "stale_permission_action_gate",
        ),
        (StaleStopIgnoringAdapterV1(), "stale_stop_action_gate"),
        (EffectCouplingAdapterV1(), "action_projection"),
        (NonCanonicalTupleAdapterV1(), "result_noncanonical_object"),
    ],
    ids=lambda value: getattr(value, "implementation_id", None),
)
def test_named_adversarial_adapters_fail_closed(
    adapter: RuntimeIntegrationAdapterV1,
    expected_detail: str,
) -> None:
    result = run_runtime_integration_conformance_v1(adapter)
    assert not result.ok
    assert expected_detail in result.detail


def test_reference_adapter_passes_exact_eight_layer_matrix() -> None:
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    assert isinstance(adapter, RuntimeIntegrationAdapterV1)
    report = run_runtime_integration_conformance_v1(adapter)
    assert report.ok, report.detail
    request = build_runtime_integration_request_v1("exact-eight-layers")
    result = adapter.execute_transcript_v1(request)
    assert len(result.steps) == 8
    assert tuple(item.layer for item in result.steps) == _LAYERS


@pytest.mark.parametrize(
    ("adapter", "detail"),
    [
        (WrongVersionAdapterV1(), "adapter_version"),
        (BlankImplementationAdapterV1(), "adapter_implementation_id"),
        (NonCanonicalImplementationAdapterV1(), "adapter_implementation_id"),
    ],
)
def test_adapter_exact_version_and_identity_dispatch_fail_closed(
    adapter: RuntimeIntegrationAdapterV1,
    detail: str,
) -> None:
    assert isinstance(adapter, RuntimeIntegrationAdapterV1)
    assert run_runtime_integration_conformance_v1(adapter).detail == detail


def test_independent_public_only_fixture_passes_same_matrix() -> None:
    module = _load_external_fixture()
    adapter = module.IndependentFixtureRuntimeIntegrationAdapterV1()
    assert isinstance(adapter, RuntimeIntegrationAdapterV1)
    report = run_runtime_integration_conformance_v1(adapter)
    assert report.ok, report.detail


def test_conformance_reports_a_noncanonical_fixture_request_wire() -> None:
    request = build_runtime_integration_request_v1("request-wire-rejection")
    object.__setattr__(
        request,
        "version",
        "pheroos-runtime-integration-transcript-request-v999",
    )
    problems: list[str] = []

    _exercise(
        ReferenceRuntimeIntegrationAdapterV1(),
        request,
        "request-wire-rejection",
        problems,
    )

    assert problems == [
        "request-wire-rejection:request_wire:RuntimeIntegrationTranscriptErrorV1"
    ]


def test_malformed_request_factory_rejects_an_unknown_case_label() -> None:
    with pytest.raises(AssertionError, match="unknown-malformation"):
        _malformed_request("unknown-malformation")


def test_exact_versions_and_expected_free_request_shape() -> None:
    assert RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1.endswith("-v1")
    assert RUNTIME_INTEGRATION_CONTROL_VERSION_V1.endswith("-v1")
    assert RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1.endswith("-v1")
    assert RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1.endswith("-v1")
    assert RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1.endswith("-v1")
    assert RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1.endswith("-v1")
    names = {item.name for item in fields(RuntimeTranscriptRequestV1)}
    assert all("expected" not in name and "oracle" not in name for name in names)
    assert "commit_observation" in names
    assert "certificate_current" not in names
    assert "certificate_current_root" not in names
    annotation = get_type_hints(RuntimeTranscriptRequestV1)["commit_observation"]
    assert RuntimeCommitObservationV1 in get_args(annotation)


@pytest.mark.parametrize(
    ("label", "terminal", "effect", "control", "status", "publish", "execute"),
    [
        (
            "matrix-publish",
            "evidence_commit",
            "publish",
            RuntimeControlInputV1(),
            BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
            True,
            False,
        ),
        (
            "matrix-execute",
            "evidence_commit",
            "execute",
            RuntimeControlInputV1(),
            BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT,
            False,
            True,
        ),
        (
            "matrix-fallback",
            "safe_fallback",
            "publish",
            RuntimeControlInputV1(),
            BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
            True,
            False,
        ),
        (
            "matrix-blocked",
            "blocked",
            "publish",
            RuntimeControlInputV1(),
            BaselineOutputTerminalStatusV2.BLOCKED,
            False,
            False,
        ),
        (
            "matrix-invalid",
            "invalid",
            "publish",
            RuntimeControlInputV1(omit_permission=True),
            BaselineOutputTerminalStatusV2.INVALID,
            False,
            False,
        ),
    ],
)
def test_delivery_publish_and_execute_are_independent(
    label: str,
    terminal: str,
    effect: str,
    control: RuntimeControlInputV1,
    status: BaselineOutputTerminalStatusV2,
    publish: bool,
    execute: bool,
) -> None:
    request = build_runtime_integration_request_v1(
        label,
        terminal=terminal,
        effect=effect,
        control=control,
    )
    result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(request)
    governance = result.governance_result
    assert governance is not None
    assert governance.terminal_status is status
    assert result.delivery_eligible
    assert result.publication_authorized is publish
    assert result.execution_authorized is execute


@pytest.mark.parametrize(
    ("label", "control"),
    [
        (
            "stale-permission-direct",
            RuntimeControlInputV1(
                recover_after_commit=True,
                advance_permission_before_recovery=True,
            ),
        ),
        (
            "stale-stop-direct",
            RuntimeControlInputV1(
                recover_after_commit=True,
                advance_stop_before_recovery=True,
            ),
        ),
    ],
)
def test_real_store_successor_makes_recovered_action_dependency_stale(
    label: str,
    control: RuntimeControlInputV1,
) -> None:
    request = build_runtime_integration_request_v1(label, control=control)
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    result = adapter.execute_transcript_v1(request)
    governance = result.governance_result
    assert governance is not None
    assert result.recovered_after_commit
    assert governance.position is GovernanceCommitPositionV2.CURRENT
    assert governance.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert governance.authorization is None
    assert not result.publication_authorized
    assert not result.execution_authorized
    transition = governance.commit_attempt.committed_transition
    assert transition is not None
    streams = {item.stream_ref for item in transition.batch.read_set.entries}
    baseline = request.baseline_request
    assert baseline is not None
    assert baseline.permission_stream_ref in streams
    assert baseline.stop_stream_ref in streams
    reader = adapter.open_recovered_governance_reader_v1(
        request.request_root,
        request.scope.scope_ref,
    )
    assert reader is not None
    target = (
        baseline.permission_stream_ref
        if control.advance_permission_before_recovery
        else baseline.stop_stream_ref
    )
    changed = set()
    for entry in transition.batch.read_set.entries:
        head = reader.load_head_v2(request.scope.scope_ref, entry.stream_ref)
        if head.revision == entry.expected_revision + 1:
            changed.add(entry.stream_ref)
        else:
            assert head.revision == entry.expected_revision
            assert head.head_root == entry.expected_root
    assert changed == {baseline.output_stream_ref, target}


def test_recovery_reader_is_the_pre_source_witness_checkpoint_view() -> None:
    request = build_runtime_integration_request_v1(
        "checkpoint-reopen-witness-direct",
        control=RuntimeControlInputV1(recover_after_commit=True),
    )
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    result = adapter.execute_transcript_v1(request)
    key = (request.request_root, request.scope.scope_ref)
    reader = adapter.open_recovered_governance_reader_v1(*key)
    source = adapter._recovery_source_readers[key]
    witness = runtime_recovery_witness_stream_ref_v1(request.request_root)
    expected = GovernanceHeadV2.genesis(request.authority_domain, witness)
    assert result.recovered_after_commit
    assert reader is not None
    assert reader.load_head_v2(request.scope.scope_ref, witness) == expected
    assert source.load_head_v2(request.scope.scope_ref, witness).revision == 1
    transition = result.governance_result
    assert transition is not None
    committed = transition.commit_attempt.committed_transition
    assert committed is not None
    assert witness not in {item.stream_ref for item in committed.batch.read_set.entries}


def test_stale_certificate_is_typed_commit_v2_successor_data_not_authority() -> None:
    request = build_runtime_integration_request_v1(
        "stale-certificate-direct",
        terminal="certificate_stale",
    )
    observation = request.commit_observation
    assert type(observation) is RuntimeCommitObservationV1
    observed = observation.observed_finality
    successor = observation.successor_finality
    assert observed is not None and successor is not None
    assert observed.stream_ref == successor.stream_ref
    assert successor.revision == observed.revision + 1
    assert observed.head_root != successor.head_root
    assert observation.outcome.finality_root == observed.projection_root


@pytest.mark.parametrize(
    ("effect", "publish", "execute"),
    [("publish", True, False), ("execute", False, True)],
)
def test_current_certificate_exact_state_binding_opens_only_selected_action(
    effect: str,
    publish: bool,
    execute: bool,
) -> None:
    request = build_runtime_integration_request_v1(
        f"current-certificate-{effect}-direct",
        terminal="certificate_current",
        effect=effect,
    )
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    result = adapter.execute_transcript_v1(request)
    states = adapter.open_recovered_certificate_states_v1(
        request.request_root,
        request.scope.scope_ref,
    )
    observation = request.commit_observation
    assert states is not None and observation is not None
    assert observation.observed_finality is not None
    assert certificate_state_matches_projection_v1(
        states[0],
        observation.observed_finality,
    )
    assert result.publication_authorized is publish
    assert result.execution_authorized is execute


def test_timeout_and_cancel_coexist_without_creating_governance_authority() -> None:
    request = build_runtime_integration_request_v1(
        "timeout-and-cancel-direct",
        control=RuntimeControlInputV1(
            wall_clock_timed_out=True,
            cancel_requested=True,
        ),
    )
    result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(request)
    assert result.diagnostics == ("wall_clock_timed_out", "cancel_requested")
    assert result.governance_result is None
    assert result.commit_outcome is None
    assert not result.delivery_eligible
    assert not result.publication_authorized
    assert not result.execution_authorized


def test_duplicate_and_restart_bind_the_same_driver_receipt() -> None:
    request = build_runtime_integration_request_v1(
        "driver-restart-direct",
        control=RuntimeControlInputV1(repeat_invocation=True),
    )
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    result = adapter.execute_transcript_v1(request)
    assert len(result.driver_receipts) == 2
    assert result.driver_receipts[0] == result.driver_receipts[1]
    assert result.driver_restarted_receipt == result.driver_receipts[0]
    assert (
        adapter.read_driver_checkpoint_v1(
            result.driver_checkpoint_wire,
            request.scope.scope_ref,
            request.driver_request.driver_id,
            request.driver_request.idempotency_key,
        )
        == result.driver_receipts[0]
    )


def test_baseline_transcript_does_not_activate_swarm_or_commit_profile() -> None:
    request = build_runtime_integration_request_v1("baseline-stays-baseline")
    protocol = request.capability.protocol
    assert protocol.collective_decision_policy is None
    assert protocol.collective_commit_policy is None


def test_unknown_exact_versions_and_noncanonical_nested_types_fail() -> None:
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="unsupported"):
        RuntimeControlInputV1(version="pheroos-runtime-integration-control-v999")
    request = build_runtime_integration_request_v1("version-rejection")
    payload = request.to_dict()
    payload["version"] = "pheroos-runtime-integration-transcript-request-v999"
    payload["request_root"] = ""
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="unsupported"):
        RuntimeTranscriptRequestV1.from_dict(payload)
    observation = build_runtime_integration_request_v1(
        "observation-version-rejection",
        terminal="advisory",
    ).commit_observation
    assert type(observation) is RuntimeCommitObservationV1
    observed_payload = observation.to_dict()
    observed_payload["version"] = "pheroos-runtime-integration-commit-observation-v999"
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="unsupported"):
        RuntimeCommitObservationV1.from_dict(observed_payload)
    result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(request)
    object.__setattr__(result, "steps", list(result.steps))
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="steps"):
        result.__post_init__()


def test_request_envelope_rejects_noncanonical_abi_record_types() -> None:
    request = build_runtime_integration_request_v1("request-envelope-types")
    cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"scope": object()}, "noncanonical ABI record"),
        ({"verified_signal_requests": (object(),)}, "signal requests"),
        ({"control": object()}, "noncanonical ABI record"),
        ({"baseline_request": object()}, "baseline request"),
    )

    for changes, detail in cases:
        with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match=detail):
            replace(request, request_root="", **changes)  # type: ignore[arg-type]

    control = RuntimeControlInputV1()
    object.__setattr__(control, "repeat_invocation", 1)
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="noncanonical"):
        replace(request, control=control, request_root="")


def test_commit_observation_tampering_is_rejected_with_typed_causes() -> None:
    advisory_request = build_runtime_integration_request_v1(
        "tampered-advisory-finality",
        terminal="advisory",
    )
    certificate_request = build_runtime_integration_request_v1(
        "tampered-advisory-finality-source",
        terminal="certificate_current",
    )
    advisory = advisory_request.commit_observation
    certificate = certificate_request.commit_observation
    assert advisory is not None and certificate is not None
    assert certificate.observed_finality is not None
    object.__setattr__(
        advisory,
        "observed_finality",
        certificate.observed_finality,
    )
    with pytest.raises(
        RuntimeIntegrationTranscriptErrorV1,
        match="Commit observation is noncanonical",
    ) as advisory_error:
        replace(advisory_request, request_root="")
    assert advisory_error.value.__cause__ is not None
    assert "cannot carry finality" in str(advisory_error.value.__cause__)

    noncanonical_request = build_runtime_integration_request_v1(
        "tampered-observation-type",
        terminal="advisory",
    )
    noncanonical = noncanonical_request.commit_observation
    assert noncanonical is not None
    object.__setattr__(noncanonical, "outcome", object())
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1) as type_error:
        replace(noncanonical_request, request_root="")
    assert type_error.value.__cause__ is not None
    assert "noncanonical" in str(type_error.value.__cause__)

    undeliverable_request = build_runtime_integration_request_v1(
        "tampered-advisory-delivery",
        terminal="advisory",
    )
    undeliverable = undeliverable_request.commit_observation
    assert undeliverable is not None
    object.__setattr__(undeliverable.outcome, "delivery_eligible", False)
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1) as delivery_error:
        replace(undeliverable_request, request_root="")
    assert delivery_error.value.__cause__ is not None
    assert "deliverable advisory" in str(delivery_error.value.__cause__)

    missing_finality_request = build_runtime_integration_request_v1(
        "tampered-certificate-missing-finality",
        terminal="certificate_current",
    )
    missing_finality = missing_finality_request.commit_observation
    assert missing_finality is not None
    object.__setattr__(missing_finality, "observed_finality", None)
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1) as lane_error:
        replace(missing_finality_request, request_root="")
    assert lane_error.value.__cause__ is not None
    assert "lane is unsupported" in str(lane_error.value.__cause__)

    mismatched_root_request = build_runtime_integration_request_v1(
        "tampered-certificate-root",
        terminal="certificate_current",
    )
    mismatched_root = mismatched_root_request.commit_observation
    assert mismatched_root is not None
    object.__setattr__(mismatched_root.outcome, "finality_root", "sha256:" + "0" * 64)
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1) as root_error:
        replace(mismatched_root_request, request_root="")
    assert root_error.value.__cause__ is not None
    assert "canonical verified lane" in str(root_error.value.__cause__)

    stale_request = build_runtime_integration_request_v1(
        "tampered-certificate-successor",
        terminal="certificate_stale",
    )
    stale = stale_request.commit_observation
    assert stale is not None
    assert stale.observed_finality is not None and stale.successor_finality is not None
    object.__setattr__(
        stale.successor_finality,
        "revision",
        stale.observed_finality.revision,
    )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1) as successor_error:
        replace(stale_request, request_root="")
    assert successor_error.value.__cause__ is not None
    assert "canonical successor lane" in str(successor_error.value.__cause__)


def test_request_governance_lane_and_control_shapes_fail_closed() -> None:
    baseline = build_runtime_integration_request_v1("lane-baseline")
    advisory = build_runtime_integration_request_v1(
        "lane-advisory",
        terminal="advisory",
    )
    assert baseline.baseline_request is not None
    assert advisory.commit_observation is not None

    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="outcome path"):
        replace(
            baseline,
            baseline_request=None,
            commit_observation=None,
            request_root="",
        )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="Certificate Commit"):
        replace(
            baseline,
            commit_observation=advisory.commit_observation,
            request_root="",
        )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="control material"):
        replace(
            advisory,
            control=RuntimeControlInputV1(recover_after_commit=True),
            request_root="",
        )

    superseded = build_runtime_integration_request_v1(
        "lane-unrequested-successor",
        control=RuntimeControlInputV1(
            recover_after_commit=True,
            supersede_before_recovery=True,
        ),
    )
    assert superseded.successor_request is not None
    with pytest.raises(
        RuntimeIntegrationTranscriptErrorV1, match="unrequested successor"
    ):
        replace(superseded, control=RuntimeControlInputV1(), request_root="")
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="lacks a successor"):
        replace(
            baseline,
            control=RuntimeControlInputV1(
                recover_after_commit=True,
                supersede_before_recovery=True,
            ),
            request_root="",
        )

    conflicted = build_runtime_integration_request_v1(
        "lane-unrequested-contender",
        control=RuntimeControlInputV1(inject_cas_conflict=True),
    )
    assert conflicted.contender_request is not None
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="unrequested CAS"):
        replace(conflicted, control=RuntimeControlInputV1(), request_root="")
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="lacks a contender"):
        replace(
            baseline,
            control=RuntimeControlInputV1(inject_cas_conflict=True),
            request_root="",
        )
    object.__setattr__(
        conflicted.contender_request,
        "output_transition_id",
        "transition:forged-contender",
    )
    with pytest.raises(
        RuntimeIntegrationTranscriptErrorV1, match="transition identity"
    ):
        replace(conflicted, request_root="")


def test_request_scope_driver_signal_and_baseline_bindings_reject_tampering() -> None:
    cross_scope_request = build_runtime_integration_request_v1("binding-cross-scope")
    foreign_scope_request = build_runtime_integration_request_v1(
        "binding-cross-scope-foreign"
    )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="cross-scope"):
        replace(
            cross_scope_request,
            issuer_grant=foreign_scope_request.issuer_grant,
            request_root="",
        )

    domain_request = build_runtime_integration_request_v1("binding-domain")
    mismatched_grant = replace(
        domain_request.issuer_grant,
        domain_root="sha256:" + "0" * 64,
        grant_root="",
    )
    with pytest.raises(
        RuntimeIntegrationTranscriptErrorV1, match="domain is mismatched"
    ):
        replace(
            domain_request,
            issuer_grant=mismatched_grant,
            request_root="",
        )

    provenance_request = build_runtime_integration_request_v1("binding-provenance")
    object.__setattr__(provenance_request.driver_result, "provenance", "")
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="lacks provenance"):
        replace(provenance_request, request_root="")

    invocation_request = build_runtime_integration_request_v1("binding-driver-result")
    object.__setattr__(
        invocation_request.driver_result,
        "invocation_id",
        "invocation:forged",
    )
    with pytest.raises(
        RuntimeIntegrationTranscriptErrorV1,
        match="request/result binding",
    ):
        replace(invocation_request, request_root="")

    declaration_count_request = build_runtime_integration_request_v1(
        "binding-driver-count"
    )
    object.__setattr__(declaration_count_request.capability, "drivers", ())
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="one exact Driver"):
        replace(declaration_count_request, request_root="")

    declaration_request = build_runtime_integration_request_v1(
        "binding-driver-declaration"
    )
    descriptor = declaration_request.capability.drivers[0]
    forged_descriptor = replace(descriptor, id="forged-driver")
    object.__setattr__(
        declaration_request.capability,
        "drivers",
        (forged_descriptor,),
    )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="not declared"):
        replace(declaration_request, request_root="")

    signal_request = build_runtime_integration_request_v1("binding-signal")
    signal = signal_request.verified_signal_requests[0]
    forged_signal = replace(
        signal,
        evidence_root="sha256:" + "0" * 64,
        request_root="",
    )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="signal binding"):
        replace(
            signal_request,
            verified_signal_requests=(forged_signal,),
            request_root="",
        )

    baseline_request = build_runtime_integration_request_v1("binding-baseline")
    baseline = baseline_request.baseline_request
    assert baseline is not None
    object.__setattr__(baseline, "run_ref", "run:other")
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="request binding"):
        replace(baseline_request, request_root="")


@pytest.mark.parametrize(
    ("proposal_change", "detail"),
    [
        (None, "Driver-bound"),
        ({"signal_transition_id": 7}, "Driver-bound"),
        ({"signal_transition_id": "transition:unknown"}, "Driver-bound"),
        ({"source_ref": "fixture:forged"}, "Driver-bound"),
    ],
)
def test_baseline_evidence_projection_must_bind_exact_driver_signal(
    proposal_change: dict[str, object] | None,
    detail: str,
) -> None:
    request = build_runtime_integration_request_v1(
        f"binding-evidence-{proposal_change!r}"
    )
    baseline = request.baseline_request
    assert baseline is not None
    if proposal_change is None:
        object.__setattr__(baseline, "verified_signals", ())
    else:
        proposal = dict(baseline.verified_signals[0])
        proposal.update(proposal_change)
        object.__setattr__(baseline, "verified_signals", (proposal,))

    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match=detail):
        replace(request, request_root="")


def test_certificate_observation_stream_must_bind_request_scope() -> None:
    request = build_runtime_integration_request_v1(
        "binding-certificate-stream",
        terminal="certificate_current",
    )
    observation = request.commit_observation
    assert observation is not None and observation.observed_finality is not None
    object.__setattr__(
        observation.observed_finality,
        "stream_ref",
        "certificate-owner:forged-scope",
    )

    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="request scope"):
        replace(request, request_root="")


def test_result_identity_driver_and_governance_shapes_fail_closed() -> None:
    request = build_runtime_integration_request_v1("result-shapes")
    result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(request)
    cases: tuple[tuple[dict[str, object], str], ...] = (
        (
            {"version": "pheroos-runtime-integration-transcript-result-v999"},
            "version is unsupported",
        ),
        ({"disposition": SimpleNamespace(value="forged")}, "disposition"),
        ({"compatibility_ok": 1}, "compatibility or plan"),
        ({"plan_document": []}, "compatibility or plan"),
        ({"driver_receipts": [result.driver_receipts[0]]}, "driver receipts"),
        ({"driver_restarted_receipt": object()}, "restarted Driver receipt"),
        ({"driver_checkpoint_wire": "%not-base64%"}, "checkpoint wire"),
        ({"governance_result": object()}, "Governance result"),
        ({"commit_outcome": object()}, "advisory outcome"),
        ({"trace_checkpoint": object()}, "trace checkpoint"),
        ({"delivery_eligible": 1}, "must be boolean"),
        (
            {
                "publication_authorized": True,
                "execution_authorized": True,
            },
            "cannot share",
        ),
        ({"diagnostics": ["forged"]}, "diagnostics must be a tuple"),
        ({"steps": ()}, "canonical ordered steps"),
    )

    for changes, detail in cases:
        with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match=detail):
            replace(result, result_root="", **changes)  # type: ignore[arg-type]

    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="Governance lane"):
        replace(
            result,
            governance_result=None,
            commit_outcome=None,
            result_root="",
        )

    timeout_request = build_runtime_integration_request_v1(
        "result-timeout-lane",
        control=RuntimeControlInputV1(wall_clock_timed_out=True),
    )
    timeout_result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(
        timeout_request
    )
    assert timeout_result.governance_result is None
    assert result.governance_result is not None
    with pytest.raises(
        RuntimeIntegrationTranscriptErrorV1, match="availability result"
    ):
        replace(
            timeout_result,
            governance_result=result.governance_result,
            result_root="",
        )


def test_result_step_chain_rejects_order_and_nested_tampering() -> None:
    result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(
        build_runtime_integration_request_v1("result-step-tamper")
    )

    reordered = (result.steps[1], result.steps[0], *result.steps[2:])
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="step order"):
        replace(result, steps=reordered, result_root="")

    wrong_version = result.steps[0]
    object.__setattr__(
        wrong_version,
        "version",
        "pheroos-runtime-integration-transcript-step-v999",
    )
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="canonical ordered"):
        replace(result, result_root="")

    malformed_result = ReferenceRuntimeIntegrationAdapterV1().execute_transcript_v1(
        build_runtime_integration_request_v1("result-step-malformed")
    )
    object.__setattr__(malformed_result.steps[0], "artifact_root", "not-a-root")
    with pytest.raises(RuntimeIntegrationTranscriptErrorV1, match="canonical ordered"):
        replace(malformed_result, result_root="")


def test_runtime_public_facade_has_no_private_owner_leak() -> None:
    public = __import__(
        "pheroos.conformance.runtime_integration",
        fromlist=["runtime_integration"],
    )
    for name in public.__all__:
        value = getattr(public, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            assert value.__module__ == "pheroos.conformance.runtime_integration"
            get_type_hints(value)
    get_type_hints(RuntimeIntegrationAdapterV1.open_recovered_governance_reader_v1)
    get_type_hints(RuntimeIntegrationAdapterV1.open_recovered_certificate_states_v1)


def _load_external_fixture() -> Any:
    root = Path(__file__).resolve().parents[2]
    directory = root / "examples" / "runtime-integration-protocol"
    path = directory / "run.py"
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location(
            "external_runtime_integration_fixture",
            path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(directory))


def _document_root(kind: str, payload: dict[str, object]) -> str:
    import json

    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    prefix = b"pheroos-runtime-integration-v1\x00" + kind.encode("ascii") + b"\x00"
    return "sha256:" + sha256(prefix + encoded).hexdigest()
