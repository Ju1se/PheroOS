"""Semantic validation for Runtime Integration transcript v1 records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pheroos.conformance._runtime_compatibility_contracts import (
    RuntimeCompatibilityClaimV1,
)
from pheroos.drivers import (
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    validate_driver_invocation_binding_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceVerifiedSignalRequestV2,
)
from pheroos.governance.authority_store_v2 import AuthorityDomainV2
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionOutcomeKindV2,
    CommitDecisionOutcomeV2,
)
from pheroos.governance.commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    commit_finality_owner_stream_ref_v2,
)
from pheroos.kernel import RuntimeScope
from pheroos.protocol import ScopedCapabilityManifestV2
from pheroos.trace import ScopedTraceCheckpointV2

from pheroos.conformance._runtime_integration_codec import (
    RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1,
    RUNTIME_INTEGRATION_CONTROL_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1,
    RuntimeIntegrationTranscriptErrorV1,
    checkpoint_from_wire,
    document_root,
    root_value,
    text_value,
)


if TYPE_CHECKING:

    @runtime_checkable
    class _RuntimeCommitObservationView(Protocol):
        @property
        def version(self) -> str: ...

        @property
        def outcome(self) -> CommitDecisionOutcomeV2: ...

        @property
        def observed_finality(self) -> CommitFinalityProjectionV2 | None: ...

        @property
        def successor_finality(self) -> CommitFinalityProjectionV2 | None: ...

    @runtime_checkable
    class _RuntimeControlView(Protocol):
        @property
        def version(self) -> str: ...

        @property
        def wall_clock_timed_out(self) -> bool: ...

        @property
        def cancel_requested(self) -> bool: ...

        @property
        def repeat_invocation(self) -> bool: ...

        @property
        def recover_after_commit(self) -> bool: ...

        @property
        def supersede_before_recovery(self) -> bool: ...

        @property
        def advance_permission_before_recovery(self) -> bool: ...

        @property
        def advance_stop_before_recovery(self) -> bool: ...

        @property
        def omit_permission(self) -> bool: ...

        @property
        def inject_cas_conflict(self) -> bool: ...

    @runtime_checkable
    class _RuntimeTranscriptRequestView(Protocol):
        @property
        def version(self) -> str: ...

        @property
        def scenario_id(self) -> str: ...

        @property
        def scope(self) -> RuntimeScope: ...

        @property
        def compatibility_claim(self) -> RuntimeCompatibilityClaimV1: ...

        @property
        def capability(self) -> ScopedCapabilityManifestV2: ...

        @property
        def authority_domain(self) -> AuthorityDomainV2: ...

        @property
        def issuer_grant(self) -> GovernanceIssuerGrantV2: ...

        @property
        def driver_request(self) -> DriverInvocationRequestV2: ...

        @property
        def driver_result(self) -> DriverInvocationResultV2: ...

        @property
        def verified_signal_requests(
            self,
        ) -> tuple[GovernanceVerifiedSignalRequestV2, ...]: ...

        @property
        def baseline_request(self) -> BaselineOutputRequestV2 | None: ...

        @property
        def commit_observation(self) -> _RuntimeCommitObservationView | None: ...

        @property
        def control(self) -> _RuntimeControlView: ...

        @property
        def successor_request(self) -> BaselineOutputRequestV2 | None: ...

        @property
        def contender_request(self) -> BaselineOutputRequestV2 | None: ...

    @runtime_checkable
    class _RuntimeDispositionView(Protocol):
        @property
        def value(self) -> str: ...

    @runtime_checkable
    class _RuntimeTranscriptStepView(Protocol):
        @property
        def version(self) -> str: ...

        @property
        def sequence(self) -> int: ...

        @property
        def layer(self) -> str: ...

        @property
        def artifact_version(self) -> str: ...

        @property
        def artifact_root(self) -> str: ...

        @property
        def predecessor_root(self) -> str: ...

        @property
        def step_root(self) -> str: ...

    @runtime_checkable
    class _RuntimeTranscriptResultView(Protocol):
        @property
        def version(self) -> str: ...

        @property
        def implementation_id(self) -> str: ...

        @property
        def request_root(self) -> str: ...

        @property
        def disposition(self) -> _RuntimeDispositionView: ...

        @property
        def compatibility_manifest_root(self) -> str: ...

        @property
        def compatibility_report_version(self) -> str: ...

        @property
        def compatibility_ok(self) -> bool: ...

        @property
        def plan_document(self) -> Mapping[str, object]: ...

        @property
        def plan_root(self) -> str: ...

        @property
        def driver_receipts(self) -> tuple[DriverInvocationReceiptV2, ...]: ...

        @property
        def driver_restarted_receipt(self) -> DriverInvocationReceiptV2: ...

        @property
        def driver_checkpoint_wire(self) -> str: ...

        @property
        def driver_checkpoint_root(self) -> str: ...

        @property
        def governance_result(self) -> BaselineOutputResultV2 | None: ...

        @property
        def commit_outcome(self) -> CommitDecisionOutcomeV2 | None: ...

        @property
        def trace_checkpoint(self) -> ScopedTraceCheckpointV2: ...

        @property
        def delivery_eligible(self) -> bool: ...

        @property
        def publication_authorized(self) -> bool: ...

        @property
        def execution_authorized(self) -> bool: ...

        @property
        def recovered_after_commit(self) -> bool: ...

        @property
        def diagnostics(self) -> tuple[str, ...]: ...

        @property
        def steps(self) -> tuple[_RuntimeTranscriptStepView, ...]: ...
else:

    @runtime_checkable
    class _RuntimeCommitObservationView(Protocol):
        version: str
        outcome: CommitDecisionOutcomeV2
        observed_finality: CommitFinalityProjectionV2 | None
        successor_finality: CommitFinalityProjectionV2 | None

    @runtime_checkable
    class _RuntimeControlView(Protocol):
        version: str
        wall_clock_timed_out: bool
        cancel_requested: bool
        repeat_invocation: bool
        recover_after_commit: bool
        supersede_before_recovery: bool
        advance_permission_before_recovery: bool
        advance_stop_before_recovery: bool
        omit_permission: bool
        inject_cas_conflict: bool

    @runtime_checkable
    class _RuntimeTranscriptRequestView(Protocol):
        version: str
        scenario_id: str
        scope: RuntimeScope
        compatibility_claim: RuntimeCompatibilityClaimV1
        capability: ScopedCapabilityManifestV2
        authority_domain: AuthorityDomainV2
        issuer_grant: GovernanceIssuerGrantV2
        driver_request: DriverInvocationRequestV2
        driver_result: DriverInvocationResultV2
        verified_signal_requests: tuple[GovernanceVerifiedSignalRequestV2, ...]
        baseline_request: BaselineOutputRequestV2 | None
        commit_observation: _RuntimeCommitObservationView | None
        control: _RuntimeControlView
        successor_request: BaselineOutputRequestV2 | None
        contender_request: BaselineOutputRequestV2 | None

    @runtime_checkable
    class _RuntimeDispositionView(Protocol):
        value: str

    @runtime_checkable
    class _RuntimeTranscriptStepView(Protocol):
        version: str
        sequence: int
        layer: str
        artifact_version: str
        artifact_root: str
        predecessor_root: str
        step_root: str

    @runtime_checkable
    class _RuntimeTranscriptResultView(Protocol):
        version: str
        implementation_id: str
        request_root: str
        disposition: _RuntimeDispositionView
        compatibility_manifest_root: str
        compatibility_report_version: str
        compatibility_ok: bool
        plan_document: Mapping[str, object]
        plan_root: str
        driver_receipts: tuple[DriverInvocationReceiptV2, ...]
        driver_restarted_receipt: DriverInvocationReceiptV2
        driver_checkpoint_wire: str
        driver_checkpoint_root: str
        governance_result: BaselineOutputResultV2 | None
        commit_outcome: CommitDecisionOutcomeV2 | None
        trace_checkpoint: ScopedTraceCheckpointV2
        delivery_eligible: bool
        publication_authorized: bool
        execution_authorized: bool
        recovered_after_commit: bool
        diagnostics: tuple[str, ...]
        steps: tuple[_RuntimeTranscriptStepView, ...]


def validate_commit_observation_v1(value: object) -> None:
    if not isinstance(value, _RuntimeCommitObservationView):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime Commit observation is noncanonical"
        )
    if (
        value.version != RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1
        or type(value.outcome) is not CommitDecisionOutcomeV2
        or any(
            projection is not None
            and type(projection) is not CommitFinalityProjectionV2
            for projection in (value.observed_finality, value.successor_finality)
        )
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime Commit observation is noncanonical"
        )
    outcome = value.outcome
    observed = value.observed_finality
    successor = value.successor_finality
    if outcome.kind is CommitDecisionOutcomeKindV2.ADVISORY:
        if observed is not None or successor is not None:
            raise RuntimeIntegrationTranscriptErrorV1(
                "advisory Commit observation cannot carry finality material"
            )
        if (
            not outcome.delivery_eligible
            or outcome.epistemically_committed
            or outcome.finality_root
        ):
            raise RuntimeIntegrationTranscriptErrorV1(
                "advisory Commit observation is not a deliverable advisory"
            )
        return
    if (
        outcome.kind is not CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
        or observed is None
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime Commit observation lane is unsupported"
        )
    if (
        observed.owner is not CommitFinalityOwnerV2.CERTIFICATE
        or observed.status is not CommitFinalityStatusV2.VERIFIED
        or outcome.finality_root != observed.projection_root
        or outcome.seal_root != observed.seal_root
        or outcome.frozen_dependency_root != observed.frozen_dependency_root
        or not outcome.epistemically_committed
        or not outcome.delivery_eligible
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "certificate observation is not one canonical verified lane"
        )
    if successor is not None and (
        successor.owner is not CommitFinalityOwnerV2.CERTIFICATE
        or successor.status is not CommitFinalityStatusV2.VERIFIED
        or observed.stream_ref != successor.stream_ref
        or successor.revision != observed.revision + 1
        or observed.transition_id == successor.transition_id
        or observed.head_root == successor.head_root
        or observed.seal_transition_id != successor.seal_transition_id
        or observed.seal_root != successor.seal_root
        or observed.frozen_dependency_root != successor.frozen_dependency_root
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "stale certificate observation is not one canonical successor lane"
        )


def validate_transcript_request_v1(value: object) -> None:
    if not isinstance(value, _RuntimeTranscriptRequestView):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript request contains a noncanonical ABI record"
        )
    _validate_request_types(value)
    _validate_request_bindings(value)


def _validate_request_types(value: _RuntimeTranscriptRequestView) -> None:
    if value.version != RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript request version is unsupported"
        )
    text_value(value.scenario_id, "runtime transcript scenario")
    _validate_request_envelope_types(value)
    _validate_optional_request_types(value)
    _validate_request_lane_shape(value)


def _validate_request_envelope_types(
    value: _RuntimeTranscriptRequestView,
) -> None:
    exact_types = (
        (value.scope, RuntimeScope),
        (value.compatibility_claim, RuntimeCompatibilityClaimV1),
        (value.capability, ScopedCapabilityManifestV2),
        (value.authority_domain, AuthorityDomainV2),
        (value.issuer_grant, GovernanceIssuerGrantV2),
        (value.driver_request, DriverInvocationRequestV2),
        (value.driver_result, DriverInvocationResultV2),
    )
    if any(type(item) is not expected for item, expected in exact_types):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript request contains a noncanonical ABI record"
        )
    if type(value.verified_signal_requests) is not tuple or any(
        type(item) is not GovernanceVerifiedSignalRequestV2
        for item in value.verified_signal_requests
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript signal requests are noncanonical"
        )
    _validate_control_input(value.control)


def _validate_control_input(value: object) -> None:
    if not isinstance(value, _RuntimeControlView):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript request contains a noncanonical ABI record"
        )
    flags = (
        value.wall_clock_timed_out,
        value.cancel_requested,
        value.repeat_invocation,
        value.recover_after_commit,
        value.supersede_before_recovery,
        value.advance_permission_before_recovery,
        value.advance_stop_before_recovery,
        value.omit_permission,
        value.inject_cas_conflict,
    )
    if (
        value.version != RUNTIME_INTEGRATION_CONTROL_VERSION_V1
        or any(type(flag) is not bool for flag in flags)
        or (value.supersede_before_recovery and not value.recover_after_commit)
        or (
            (
                value.advance_permission_before_recovery
                or value.advance_stop_before_recovery
            )
            and not value.recover_after_commit
        )
        or (
            value.advance_permission_before_recovery
            and value.advance_stop_before_recovery
        )
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript request contains a noncanonical ABI record"
        )


def _validate_optional_request_types(
    value: _RuntimeTranscriptRequestView,
) -> None:
    for item, expected, label in (
        (value.baseline_request, BaselineOutputRequestV2, "baseline request"),
        (value.successor_request, BaselineOutputRequestV2, "successor request"),
        (value.contender_request, BaselineOutputRequestV2, "contender request"),
    ):
        if item is not None and type(item) is not expected:
            raise RuntimeIntegrationTranscriptErrorV1(
                f"runtime transcript {label} is noncanonical"
            )
    observation = value.commit_observation
    if observation is not None:
        try:
            validate_commit_observation_v1(observation)
        except RuntimeIntegrationTranscriptErrorV1 as exc:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript Commit observation is noncanonical"
            ) from exc


def _validate_request_lane_shape(value: _RuntimeTranscriptRequestView) -> None:
    if value.baseline_request is None and value.commit_observation is None:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript requires a Governance outcome path"
        )
    if (
        value.baseline_request is not None
        and value.commit_observation is not None
        and value.commit_observation.outcome.kind
        is not CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "only a Certificate Commit observation may gate baseline output"
        )
    if value.baseline_request is None and _has_baseline_control_material(value):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime Commit observation cannot carry baseline control material"
        )
    if value.successor_request is not None and not (
        value.control.supersede_before_recovery
        or value.control.advance_permission_before_recovery
        or value.control.advance_stop_before_recovery
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript has an unrequested successor"
        )
    if value.contender_request is not None and not value.control.inject_cas_conflict:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript has an unrequested CAS contender"
        )


def _has_baseline_control_material(value: _RuntimeTranscriptRequestView) -> bool:
    return (
        value.successor_request is not None
        or value.contender_request is not None
        or value.control.recover_after_commit
        or value.control.omit_permission
        or value.control.inject_cas_conflict
    )


def _validate_request_bindings(value: _RuntimeTranscriptRequestView) -> None:
    _validate_scope_and_domain_binding(value)
    _validate_driver_binding(value)
    _validate_signal_bindings(value)
    _validate_baseline_bindings(value)
    _validate_control_bindings(value)
    _validate_commit_observation_binding(value)


def _validate_scope_and_domain_binding(
    value: _RuntimeTranscriptRequestView,
) -> None:
    scope_ref = value.scope.scope_ref
    if any(
        item != scope_ref
        for item in (
            value.authority_domain.scope_ref,
            value.issuer_grant.scope_ref,
            value.driver_request.scope_ref,
            value.driver_result.scope_ref,
        )
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript contains a cross-scope record"
        )
    if value.issuer_grant.domain_root != value.authority_domain.domain_root:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript issuer grant domain is mismatched"
        )


def _validate_driver_binding(value: _RuntimeTranscriptRequestView) -> None:
    try:
        validate_driver_invocation_binding_v2(
            value.driver_request,
            value.driver_result,
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript Driver request/result binding is mismatched"
        ) from exc
    if not value.driver_result.provenance:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript driver result lacks provenance"
        )
    if len(value.capability.drivers) != 1:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript requires one exact Driver declaration"
        )
    descriptor = value.capability.drivers[0]
    if (
        descriptor.id != value.driver_request.driver_id
        or value.driver_request.capability not in descriptor.capabilities
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript Driver invocation is not declared"
        )


def _validate_signal_bindings(value: _RuntimeTranscriptRequestView) -> None:
    scope_ref = value.scope.scope_ref
    for signal in value.verified_signal_requests:
        if (
            signal.scope_ref != scope_ref
            or signal.domain_root != value.authority_domain.domain_root
            or signal.run_ref != value.scope.run_id
            or signal.evidence_root != value.driver_result.result_digest
        ):
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript verified signal binding is invalid"
            )


def _validate_baseline_bindings(value: _RuntimeTranscriptRequestView) -> None:
    scope_ref = value.scope.scope_ref
    for request in (
        value.baseline_request,
        value.successor_request,
        value.contender_request,
    ):
        if request is None:
            continue
        if (
            request.scope_ref != scope_ref
            or request.domain_root != value.authority_domain.domain_root
            or request.run_ref != value.scope.run_id
            or request.manifest != value.capability.protocol
        ):
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript baseline request binding is invalid"
            )
        if not _baseline_signals_bind_runtime(value, request):
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript baseline evidence is not Driver-bound"
            )


def _validate_control_bindings(value: _RuntimeTranscriptRequestView) -> None:
    if value.control.supersede_before_recovery and value.successor_request is None:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript supersession lacks a successor request"
        )
    if value.control.inject_cas_conflict and value.contender_request is None:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript CAS conflict lacks a contender request"
        )
    if value.contender_request is not None and value.baseline_request is not None:
        if (
            value.contender_request.output_transition_id
            != value.baseline_request.output_transition_id
        ):
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript contender must share the transition identity"
            )


def _validate_commit_observation_binding(
    value: _RuntimeTranscriptRequestView,
) -> None:
    observation = value.commit_observation
    if observation is not None and observation.observed_finality is not None:
        scope_ref = value.scope.scope_ref
        target = value.capability.protocol.quorum_policy.target
        expected_stream = commit_finality_owner_stream_ref_v2(
            CommitFinalityOwnerV2.CERTIFICATE,
            scope_ref,
            value.capability.protocol.id,
            value.scope.run_id,
            target,
        )
        if observation.observed_finality.stream_ref != expected_stream:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime Commit observation is not bound to this request scope"
            )


def _baseline_signals_bind_runtime(
    transcript: _RuntimeTranscriptRequestView,
    request: BaselineOutputRequestV2,
) -> bool:
    if len(request.verified_signals) != len(transcript.verified_signal_requests):
        return False
    requests = {
        item.transition_id: item for item in transcript.verified_signal_requests
    }
    for proposal in request.verified_signals:
        transition_id = proposal.get("signal_transition_id")
        if not isinstance(transition_id, str):
            return False
        signal = requests.get(transition_id)
        if signal is None:
            return False
        if (
            proposal.get("signal_ref") != signal.signal_ref
            or proposal.get("signal_root") != signal.signal_root
            or proposal.get("evidence_root") != transcript.driver_result.result_digest
            or proposal.get("provenance_ref") != transcript.driver_result.result_digest
            or proposal.get("source_ref") != transcript.driver_result.provenance
        ):
            return False
    return True


def validate_transcript_result_v1(value: object) -> None:
    if not isinstance(value, _RuntimeTranscriptResultView):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript result contains a noncanonical ABI record"
        )
    _validate_result_identity(value)
    _validate_driver_result_material(value)
    _validate_result_governance_lane(value)
    _validate_result_trace_and_flags(value)
    _validate_result_diagnostics(value)
    _validate_steps(value.steps)


def _validate_result_identity(value: _RuntimeTranscriptResultView) -> None:
    if value.version != RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript result version is unsupported"
        )
    text_value(value.implementation_id, "runtime adapter implementation id")
    if not isinstance(
        value.disposition, _RuntimeDispositionView
    ) or value.disposition.value not in {
        "completed",
        "runtime_timed_out",
        "runtime_cancelled",
    }:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript disposition is noncanonical"
        )
    root_value(value.request_root, "runtime transcript request root")
    root_value(value.compatibility_manifest_root, "compatibility manifest root")
    text_value(value.compatibility_report_version, "compatibility report version")
    root_value(value.plan_root, "runtime Kernel plan root")
    root_value(value.driver_checkpoint_root, "driver checkpoint root")
    if (
        type(value.compatibility_ok) is not bool
        or type(value.plan_document) is not dict
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript compatibility or plan projection is invalid"
        )


def _validate_driver_result_material(
    value: _RuntimeTranscriptResultView,
) -> None:
    if type(value.driver_receipts) is not tuple or any(
        type(item) is not DriverInvocationReceiptV2 for item in value.driver_receipts
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript driver receipts are invalid"
        )
    if type(value.driver_restarted_receipt) is not DriverInvocationReceiptV2:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript restarted Driver receipt is invalid"
        )
    try:
        checkpoint_from_wire(value.driver_checkpoint_wire)
    except RuntimeIntegrationTranscriptErrorV1 as exc:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript driver checkpoint wire is invalid"
        ) from exc


def _validate_result_governance_lane(
    value: _RuntimeTranscriptResultView,
) -> None:
    if (
        value.governance_result is not None
        and type(value.governance_result) is not BaselineOutputResultV2
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript Governance result is noncanonical"
        )
    if (
        value.commit_outcome is not None
        and type(value.commit_outcome) is not CommitDecisionOutcomeV2
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript advisory outcome is noncanonical"
        )
    has_governance_lane = value.governance_result is not None
    has_commit_lane = value.commit_outcome is not None
    if value.disposition.value == "completed":
        if not has_governance_lane and not has_commit_lane:
            raise RuntimeIntegrationTranscriptErrorV1(
                "completed runtime transcript requires a Governance lane"
            )
    elif has_governance_lane or has_commit_lane:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime availability result cannot contain a Governance outcome"
        )


def _validate_result_trace_and_flags(
    value: _RuntimeTranscriptResultView,
) -> None:
    if type(value.trace_checkpoint) is not ScopedTraceCheckpointV2:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript trace checkpoint is invalid"
        )
    for name in (
        "delivery_eligible",
        "publication_authorized",
        "execution_authorized",
        "recovered_after_commit",
    ):
        if type(getattr(value, name)) is not bool:
            raise RuntimeIntegrationTranscriptErrorV1(
                f"runtime transcript {name} must be boolean"
            )
    if value.publication_authorized and value.execution_authorized:
        raise RuntimeIntegrationTranscriptErrorV1(
            "publication and execution cannot share one action authorization"
        )


def _validate_result_diagnostics(value: _RuntimeTranscriptResultView) -> None:
    if type(value.diagnostics) is not tuple:
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript diagnostics must be a tuple"
        )
    for item in value.diagnostics:
        text_value(item, "runtime transcript diagnostic")


def _validate_steps(steps: tuple[_RuntimeTranscriptStepView, ...]) -> None:
    if (
        type(steps) is not tuple
        or not steps
        or any(not isinstance(item, _RuntimeTranscriptStepView) for item in steps)
    ):
        raise RuntimeIntegrationTranscriptErrorV1(
            "runtime transcript requires canonical ordered steps"
        )
    previous = ""
    for index, step in enumerate(steps):
        if not _step_is_canonical(step):
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript requires canonical ordered steps"
            )
        if step.sequence != index or step.predecessor_root != previous:
            raise RuntimeIntegrationTranscriptErrorV1(
                "runtime transcript step order or predecessor is invalid"
            )
        previous = step.step_root


def _step_is_canonical(step: _RuntimeTranscriptStepView) -> bool:
    try:
        if (
            step.version != RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1
            or type(step.sequence) is not int
            or step.sequence < 0
        ):
            return False
        text_value(step.layer, "runtime transcript step layer")
        text_value(step.artifact_version, "runtime transcript artifact version")
        root_value(step.artifact_root, "runtime transcript artifact root")
        root_value(
            step.predecessor_root,
            "runtime transcript predecessor root",
            allow_empty=True,
        )
        root_value(step.step_root, "runtime transcript step root")
    except RuntimeIntegrationTranscriptErrorV1:
        return False
    return step.step_root == document_root(
        "step",
        {
            "version": step.version,
            "sequence": step.sequence,
            "layer": step.layer,
            "artifact_version": step.artifact_version,
            "artifact_root": step.artifact_root,
            "predecessor_root": step.predecessor_root,
        },
    )


__all__: tuple[str, ...] = ()
