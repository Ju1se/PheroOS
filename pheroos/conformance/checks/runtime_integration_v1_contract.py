"""Black-box Runtime Integration transcript TCK v1.

The matrix composes Protocol, Kernel, Drivers, Governance, Trace, and
Conformance over preconstructed provider-free inputs.  It never supplies an
expected result to the adapter and never creates runtime infrastructure.
"""

from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.conformance._runtime_integration_codec import (
    RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
    checkpoint_from_wire,
    checkpoint_to_wire,
    document_root,
)
from pheroos.conformance._runtime_integration_contracts import (
    RuntimeControlInputV1,
    RuntimeIntegrationAdapterV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
)
from pheroos.conformance._runtime_integration_fixture import (
    build_runtime_integration_request_v1,
)
from pheroos.conformance._runtime_integration_reference import (
    ReferenceRuntimeIntegrationAdapterV1,
)
from pheroos.kernel import runtime_scope_ref
from pheroos.drivers import DriverInvocationRequestV2, DriverInvocationResultV2
from pheroos.governance import (
    BaselineOutputActionDispositionV2,
    BaselineOutputRequestV2,
    CommitDecisionOutcomeKindV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    VerifiedCommitCertificateStateV2,
    recover_baseline_output_result_v2,
)
from pheroos.protocol import GovernanceReadPreconditionV2

from pheroos.conformance._runtime_integration_verification import (
    verify_runtime_transcript_v1,
)
from pheroos.conformance._runtime_integration_certificate import (
    _CertificateStateObservationV1,
    _observe_certificate_state_v1,
)
from pheroos.conformance._runtime_integration_dependency import (
    runtime_recovery_witness_stream_ref_v1,
)


_CHECK = "runtime_integration_v1_contract"
_CASES = (
    ("evidence-publish", "evidence_commit", "publish", RuntimeControlInputV1()),
    ("evidence-execute", "evidence_commit", "execute", RuntimeControlInputV1()),
    ("safe-fallback", "safe_fallback", "publish", RuntimeControlInputV1()),
    ("blocked", "blocked", "publish", RuntimeControlInputV1()),
    (
        "invalid-without-permission",
        "invalid",
        "publish",
        RuntimeControlInputV1(omit_permission=True),
    ),
    (
        "wall-clock-timeout",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(wall_clock_timed_out=True),
    ),
    (
        "client-cancel",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(cancel_requested=True),
    ),
    (
        "timeout-and-cancel",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(
            wall_clock_timed_out=True,
            cancel_requested=True,
        ),
    ),
    ("advisory", "advisory", "publish", RuntimeControlInputV1()),
    (
        "duplicate-invocation",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(repeat_invocation=True),
    ),
    (
        "crash-after-commit",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(recover_after_commit=True),
    ),
    (
        "superseded-output-recovery",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(
            recover_after_commit=True,
            supersede_before_recovery=True,
        ),
    ),
    (
        "stale-permission-dependency",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(
            recover_after_commit=True,
            advance_permission_before_recovery=True,
        ),
    ),
    (
        "stale-stop-dependency",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(
            recover_after_commit=True,
            advance_stop_before_recovery=True,
        ),
    ),
    (
        "stale-certificate",
        "certificate_stale",
        "publish",
        RuntimeControlInputV1(),
    ),
    (
        "current-certificate-publish",
        "certificate_current",
        "publish",
        RuntimeControlInputV1(),
    ),
    (
        "current-certificate-execute",
        "certificate_current",
        "execute",
        RuntimeControlInputV1(),
    ),
    (
        "cas-conflict",
        "evidence_commit",
        "publish",
        RuntimeControlInputV1(inject_cas_conflict=True),
    ),
)


def run_runtime_integration_conformance_v1(
    adapter: RuntimeIntegrationAdapterV1,
) -> CheckResult:
    """Execute all mandatory cases against one exact-version black box."""

    boundary = _adapter_problem(adapter)
    if boundary is not None:
        return CheckResult(_CHECK, False, boundary)
    problems: list[str] = []
    for label, terminal, effect, control in _CASES:
        request = build_runtime_integration_request_v1(
            label,
            terminal=terminal,
            effect=effect,
            control=control,
        )
        _exercise(adapter, request, label, problems)
        if problems:
            break
    if not problems:
        _exercise_rejected_inputs(adapter, problems)
    return CheckResult(_CHECK, not problems, ", ".join(problems))


def check() -> CheckResult:
    return run_runtime_integration_conformance_v1(
        ReferenceRuntimeIntegrationAdapterV1()
    )


def _adapter_problem(adapter: object) -> str | None:
    if not isinstance(adapter, RuntimeIntegrationAdapterV1):
        return "adapter_protocol"
    try:
        implementation_id = adapter.implementation_id
        version = adapter.conformance_version
    except Exception as exc:
        return f"adapter_exception:{type(exc).__name__}:{exc}"
    if (
        type(implementation_id) is not str
        or not implementation_id
        or implementation_id != implementation_id.strip()
    ):
        return "adapter_implementation_id"
    if version != RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1:
        return "adapter_version"
    return None


def _exercise(
    adapter: RuntimeIntegrationAdapterV1,
    request: RuntimeTranscriptRequestV1,
    label: str,
    problems: list[str],
) -> None:
    try:
        request = RuntimeTranscriptRequestV1.from_dict(request.to_dict())
    except Exception as exc:
        problems.append(f"{label}:request_wire:{type(exc).__name__}")
        return
    try:
        raw = adapter.execute_transcript_v1(request)
    except Exception as exc:
        problems.append(f"{label}:adapter_exception:{type(exc).__name__}:{exc}")
        return
    if type(raw) is not RuntimeTranscriptResultV1:
        problems.append(f"{label}:result_type")
        return
    if raw.implementation_id != adapter.implementation_id:
        problems.append(f"{label}:implementation_binding")
    try:
        result = RuntimeTranscriptResultV1.from_dict(raw.to_dict())
    except Exception as exc:
        problems.append(f"{label}:result_wire:{type(exc).__name__}")
        return
    if raw != result:
        problems.append(f"{label}:result_noncanonical_object")
        return
    for problem in verify_runtime_transcript_v1(request, result):
        problems.append(f"{label}:{problem}")
    _exercise_driver_checkpoint(adapter, request, result, label, problems)
    _exercise_governance_recovery(adapter, request, result, label, problems)
    _exercise_certificate_currentness(adapter, request, result, label, problems)


def _exercise_driver_checkpoint(
    adapter: RuntimeIntegrationAdapterV1,
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    label: str,
    problems: list[str],
) -> None:
    expected = result.driver_restarted_receipt
    try:
        restored = adapter.read_driver_checkpoint_v1(
            result.driver_checkpoint_wire,
            request.scope.scope_ref,
            request.driver_request.driver_id,
            request.driver_request.idempotency_key,
        )
        cross_scope = adapter.read_driver_checkpoint_v1(
            result.driver_checkpoint_wire,
            runtime_scope_ref("tenant-cross-checkpoint", "run:cross-checkpoint"),
            request.driver_request.driver_id,
            request.driver_request.idempotency_key,
        )
        cross_key = adapter.read_driver_checkpoint_v1(
            result.driver_checkpoint_wire,
            request.scope.scope_ref,
            request.driver_request.driver_id,
            request.driver_request.idempotency_key + ":other",
        )
    except Exception as exc:
        problems.append(f"{label}:checkpoint_reader:{type(exc).__name__}")
        return
    if restored != expected or cross_scope is not None or cross_key is not None:
        problems.append(f"{label}:checkpoint_reader_binding")
    raw = checkpoint_from_wire(result.driver_checkpoint_wire)
    tampered = bytearray(raw)
    tampered[len(tampered) // 2] ^= 1
    try:
        adapter.read_driver_checkpoint_v1(
            checkpoint_to_wire(bytes(tampered)),
            request.scope.scope_ref,
            request.driver_request.driver_id,
            request.driver_request.idempotency_key,
        )
    except Exception:
        return
    problems.append(f"{label}:checkpoint_tamper_accepted")


def _exercise_governance_recovery(
    adapter: RuntimeIntegrationAdapterV1,
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    label: str,
    problems: list[str],
) -> None:
    expected_recovery = (
        request.control.recover_after_commit
        and result.disposition.value == "completed"
        and request.baseline_request is not None
    )
    try:
        reader = adapter.open_recovered_governance_reader_v1(
            request.request_root,
            request.scope.scope_ref,
        )
    except Exception as exc:
        problems.append(f"{label}:governance_recovery_reader:{type(exc).__name__}")
        return
    if not expected_recovery:
        if reader is not None:
            problems.append(f"{label}:unexpected_governance_recovery_reader")
        return
    if not isinstance(reader, GovernanceStateReaderV2):
        problems.append(f"{label}:governance_recovery_reader")
        return
    baseline = request.baseline_request
    expected = result.governance_result
    assert baseline is not None
    try:
        recovered = recover_baseline_output_result_v2(
            baseline,
            state_reader=reader,
        )
    except Exception as exc:
        problems.append(f"{label}:governance_recovery:{type(exc).__name__}")
        return
    if recovered != expected:
        problems.append(f"{label}:governance_recovery_result")
    _verify_checkpoint_reopen(request, reader, label, problems)
    _verify_targeted_dependency_delta(
        request,
        result,
        reader,
        label,
        problems,
    )
    _reject_unbound_governance_readers(adapter, request, label, problems)


def _verify_checkpoint_reopen(
    request: RuntimeTranscriptRequestV1,
    reader: GovernanceStateReaderV2,
    label: str,
    problems: list[str],
) -> None:
    """Require a detached pre-witness recovery image, not the live source."""

    stream_ref = runtime_recovery_witness_stream_ref_v1(request.request_root)
    try:
        observed = reader.load_head_v2(request.scope.scope_ref, stream_ref)
        expected = GovernanceHeadV2.genesis(request.authority_domain, stream_ref)
    except Exception:
        problems.append(f"{label}:governance_checkpoint_reopen")
        return
    if observed != expected:
        problems.append(f"{label}:governance_checkpoint_reopen")


def _verify_targeted_dependency_delta(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    reader: GovernanceStateReaderV2,
    label: str,
    problems: list[str],
) -> None:
    baseline = request.baseline_request
    governance = result.governance_result
    if baseline is None or governance is None:
        return
    lane = _targeted_dependency_lane(request, baseline)
    if lane is None:
        return
    target, gate_detail, delta_detail = lane
    transition = governance.commit_attempt.committed_transition
    if transition is None:
        problems.append(f"{label}:{delta_detail}")
        return
    expected_changed = {baseline.output_stream_ref, target}
    observed_changed = _changed_read_set_streams(
        request,
        reader,
        transition.batch.read_set.entries,
    )
    if observed_changed != expected_changed:
        problems.append(f"{label}:{delta_detail}")
    if result.publication_authorized or result.execution_authorized:
        problems.append(f"{label}:{gate_detail}")


def _targeted_dependency_lane(
    request: RuntimeTranscriptRequestV1,
    baseline: BaselineOutputRequestV2,
) -> tuple[str, str, str] | None:
    if request.control.advance_permission_before_recovery:
        return (
            baseline.permission_stream_ref,
            "stale_permission_action_gate",
            "stale_permission_head_delta",
        )
    if request.control.advance_stop_before_recovery:
        return (
            baseline.stop_stream_ref,
            "stale_stop_action_gate",
            "stale_stop_head_delta",
        )
    return None


def _changed_read_set_streams(
    request: RuntimeTranscriptRequestV1,
    reader: GovernanceStateReaderV2,
    entries: tuple[GovernanceReadPreconditionV2, ...],
) -> set[str] | None:
    observed_changed: set[str] = set()
    for entry in entries:
        try:
            current = reader.load_head_v2(request.scope.scope_ref, entry.stream_ref)
        except Exception:
            return None
        if current.revision == entry.expected_revision:
            if current.head_root != entry.expected_root:
                return None
            continue
        if current.revision == entry.expected_revision + 1:
            if current.head_root == entry.expected_root:
                return None
            observed_changed.add(entry.stream_ref)
            continue
        return None
    return observed_changed


def _reject_unbound_governance_readers(
    adapter: RuntimeIntegrationAdapterV1,
    request: RuntimeTranscriptRequestV1,
    label: str,
    problems: list[str],
) -> None:
    cross_request = build_runtime_integration_request_v1(
        f"reader-cross-request:{label}",
        control=RuntimeControlInputV1(recover_after_commit=True),
    )
    unknown_root = document_root(
        "unknown-request",
        {"request_root": request.request_root},
    )
    try:
        adapter.execute_transcript_v1(cross_request)
        observations = (
            adapter.open_recovered_governance_reader_v1(
                cross_request.request_root,
                request.scope.scope_ref,
            ),
            adapter.open_recovered_governance_reader_v1(
                unknown_root,
                request.scope.scope_ref,
            ),
            adapter.open_recovered_governance_reader_v1(
                request.request_root,
                runtime_scope_ref(
                    "tenant-cross-governance-reader",
                    "run:cross-governance-reader",
                ),
            ),
        )
    except Exception as exc:
        problems.append(f"{label}:governance_recovery_binding:{type(exc).__name__}")
        return
    if any(item is not None for item in observations):
        problems.append(f"{label}:governance_recovery_binding")


def _exercise_certificate_currentness(
    adapter: RuntimeIntegrationAdapterV1,
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
    label: str,
    problems: list[str],
) -> None:
    observation = request.commit_observation
    if (
        result.disposition.value != "completed"
        or observation is None
        or observation.outcome.kind is not CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
    ):
        return
    try:
        states = adapter.open_recovered_certificate_states_v1(
            request.request_root,
            request.scope.scope_ref,
        )
    except Exception as exc:
        problems.append(f"{label}:certificate_recovery_reader:{type(exc).__name__}")
        return
    pair = _canonical_certificate_state_pair(states)
    if pair is None:
        problems.append(f"{label}:certificate_recovery_reader")
        return
    observed, successor = pair
    observations = _certificate_pair_observations(request, observed, successor)
    if observations is None:
        problems.append(f"{label}:certificate_recovery_binding")
        return
    observed_view, successor_view = observations
    _verify_certificate_currentness(
        request,
        observation.successor_finality is not None,
        observed_view,
        successor_view,
        result,
        label,
        problems,
    )
    _reject_unbound_certificate_states(adapter, request, label, problems)


def _canonical_certificate_state_pair(
    states: object,
) -> (
    tuple[
        VerifiedCommitCertificateStateV2,
        VerifiedCommitCertificateStateV2 | None,
    ]
    | None
):
    if type(states) is not tuple or len(states) != 2:
        return None
    observed, successor = states
    if type(observed) is not VerifiedCommitCertificateStateV2:
        return None
    if (
        successor is not None
        and type(successor) is not VerifiedCommitCertificateStateV2
    ):
        return None
    return observed, successor


def _certificate_pair_observations(
    request: RuntimeTranscriptRequestV1,
    observed: VerifiedCommitCertificateStateV2,
    successor: VerifiedCommitCertificateStateV2 | None,
) -> (
    tuple[
        _CertificateStateObservationV1,
        _CertificateStateObservationV1 | None,
    ]
    | None
):
    observation = request.commit_observation
    if observation is None or observation.observed_finality is None:
        return None
    observed_view = _observe_certificate_state_v1(
        observed,
        observation.observed_finality,
    )
    if observed_view is None:
        return None
    observed_snapshot = observed_view.snapshot
    observed_body = observed_snapshot.certificate.body
    if (
        observed_snapshot.domain_root != request.authority_domain.domain_root
        or observed_snapshot.scope_ref != request.scope.scope_ref
        or observed_body.domain_root != request.authority_domain.domain_root
        or observed_body.scope_ref != request.scope.scope_ref
        or observed_body.protocol_ref != request.capability.protocol.id
        or observed_body.run_ref != request.scope.run_id
        or observed_body.target_ref != request.capability.protocol.quorum_policy.target
        or observed_body.candidate_ref != observation.outcome.candidate_ref
        or observed_body.claim_root != observation.outcome.claim_root
        or observed_body.output_contract_root
        != observation.outcome.output_contract_root
        or observed_body.output_payload_root != observation.outcome.output_payload_root
        or not observed_view.projection_matches
    ):
        return None
    if successor is None:
        if observation.successor_finality is not None:
            return None
        return observed_view, None
    if observation.successor_finality is None:
        return None
    successor_view = _observe_certificate_state_v1(
        successor,
        observation.successor_finality,
    )
    if successor_view is None:
        return None
    successor_snapshot = successor_view.snapshot
    successor_body = successor_snapshot.certificate.body
    if not (
        successor_snapshot.domain_root == observed_snapshot.domain_root
        and successor_snapshot.scope_ref == observed_snapshot.scope_ref
        and successor_snapshot.protocol_ref == observed_snapshot.protocol_ref
        and successor_snapshot.run_ref == observed_snapshot.run_ref
        and successor_snapshot.target_ref == observed_snapshot.target_ref
        and successor_snapshot.stream_ref == observed_snapshot.stream_ref
        and successor_snapshot.revision == observed_snapshot.revision + 1
        and successor_snapshot.parent_revision == observed_snapshot.revision
        and successor_snapshot.parent_transition_id == observed_snapshot.transition_id
        and successor_snapshot.parent_snapshot_root == observed_snapshot.snapshot_root
        and successor_body.to_dict() == observed_body.to_dict()
        and successor_view.projection_matches
    ):
        return None
    return observed_view, successor_view


def _verify_certificate_currentness(
    request: RuntimeTranscriptRequestV1,
    expects_stale: bool,
    observed: _CertificateStateObservationV1,
    successor: _CertificateStateObservationV1 | None,
    result: RuntimeTranscriptResultV1,
    label: str,
    problems: list[str],
) -> None:
    observed_current = observed.is_current
    successor_current = False if successor is None else successor.is_current
    if expects_stale:
        if observed_current or successor is None or not successor_current:
            problems.append(f"{label}:certificate_currentness")
        if result.publication_authorized or result.execution_authorized:
            problems.append(f"{label}:certificate_currentness_action_gate")
    else:
        if not observed_current or successor is not None:
            problems.append(f"{label}:certificate_currentness")
        if not _current_certificate_action_matches(request, result):
            problems.append(f"{label}:certificate_currentness_action_gate")


def _current_certificate_action_matches(
    request: RuntimeTranscriptRequestV1,
    result: RuntimeTranscriptResultV1,
) -> bool:
    baseline = request.baseline_request
    governance = result.governance_result
    if baseline is None or governance is None:
        return False
    authorized = (
        governance.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
        and governance.authorization is not None
    )
    return result.publication_authorized is (
        authorized and baseline.effect == "publish"
    ) and result.execution_authorized is (authorized and baseline.effect == "execute")


def _reject_unbound_certificate_states(
    adapter: RuntimeIntegrationAdapterV1,
    request: RuntimeTranscriptRequestV1,
    label: str,
    problems: list[str],
) -> None:
    cross_request = build_runtime_integration_request_v1(
        f"certificate-cross-request:{label}",
    )
    unknown_root = document_root(
        "unknown-certificate-request",
        {"request_root": request.request_root},
    )
    try:
        observations = (
            adapter.open_recovered_certificate_states_v1(
                cross_request.request_root,
                request.scope.scope_ref,
            ),
            adapter.open_recovered_certificate_states_v1(
                unknown_root,
                request.scope.scope_ref,
            ),
            adapter.open_recovered_certificate_states_v1(
                request.request_root,
                runtime_scope_ref(
                    "tenant-cross-certificate-reader",
                    "run:cross-certificate-reader",
                ),
            ),
        )
    except Exception as exc:
        problems.append(f"{label}:certificate_recovery_binding:{type(exc).__name__}")
        return
    if any(item is not None for item in observations):
        problems.append(f"{label}:certificate_recovery_binding")


def _exercise_rejected_inputs(
    adapter: RuntimeIntegrationAdapterV1,
    problems: list[str],
) -> None:
    for label in (
        "cross-scope",
        "digest-mutation",
        "missing-provenance",
        "non-tuple-signals",
        "non-boolean-control",
        "unknown-version",
    ):
        malformed = _malformed_request(label)
        try:
            adapter.execute_transcript_v1(malformed)
        except Exception:
            continue
        problems.append(f"{label}:accepted")


def _malformed_request(label: str) -> RuntimeTranscriptRequestV1:
    request = build_runtime_integration_request_v1(f"malformed-{label}")
    if label == "cross-scope":
        original = request.driver_request
        cross_request = DriverInvocationRequestV2(
            scope_ref=runtime_scope_ref("tenant-other", "run:other"),
            driver_id=original.driver_id,
            invocation_id=original.invocation_id,
            operation=original.operation,
            capability=original.capability,
            idempotency_key=original.idempotency_key,
            payload=dict(original.payload),
        )
        cross_result = DriverInvocationResultV2.for_request(
            cross_request,
            ok=request.driver_result.ok,
            payload=dict(request.driver_result.payload),
            provenance=request.driver_result.provenance,
        )
        object.__setattr__(
            request,
            "driver_request",
            cross_request,
        )
        object.__setattr__(request, "driver_result", cross_result)
    elif label == "digest-mutation":
        original_result = request.driver_result
        object.__setattr__(
            request,
            "driver_result",
            DriverInvocationResultV2(
                scope_ref=original_result.scope_ref,
                driver_id=original_result.driver_id,
                invocation_id=original_result.invocation_id,
                operation=original_result.operation,
                capability=original_result.capability,
                idempotency_key=original_result.idempotency_key,
                request_digest="sha256:" + "f" * 64,
                ok=original_result.ok,
                payload=dict(original_result.payload),
                provenance=original_result.provenance,
            ),
        )
    elif label == "missing-provenance":
        object.__setattr__(request.driver_result, "provenance", "")
        object.__setattr__(request.driver_result, "result_digest", "")
    elif label == "non-tuple-signals":
        object.__setattr__(
            request,
            "verified_signal_requests",
            list(request.verified_signal_requests),
        )
    elif label == "non-boolean-control":
        object.__setattr__(request.control, "cancel_requested", 1)
    elif label == "unknown-version":
        object.__setattr__(
            request,
            "version",
            "pheroos-runtime-integration-transcript-request-v999",
        )
    else:
        raise AssertionError(label)
    _rebind_outer_root(request)
    return request


def _rebind_outer_root(request: RuntimeTranscriptRequestV1) -> None:
    payload = request.to_dict()
    del payload["request_root"]
    object.__setattr__(request, "request_root", document_root("request", payload))


__all__ = [
    "RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1",
    "check",
    "run_runtime_integration_conformance_v1",
]
