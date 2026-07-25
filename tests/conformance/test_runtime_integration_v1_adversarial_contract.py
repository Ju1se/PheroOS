from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from pheroos.conformance.runtime_integration import (
    ReferenceRuntimeIntegrationAdapterV1,
    RuntimeIntegrationAdapterV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    run_runtime_integration_conformance_v1,
)
from pheroos.drivers import DriverInvocationReceiptV2
from pheroos.governance import (
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    VerifiedCommitCertificateStateV2,
)


class _ExplodingIdentityAdapter(ReferenceRuntimeIntegrationAdapterV1):
    @property
    def implementation_id(self) -> str:
        raise OSError("identity unavailable")


class _ExecutionFailureAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-execution-failure-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        raise OSError("runtime execution failed")


class _ReboundResultAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-result-rebound-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = super().execute_transcript_v1(request)
        payload = result.to_dict()
        payload["implementation_id"] = "tests:unbound-implementation"
        payload["result_root"] = ""
        return RuntimeTranscriptResultV1.from_dict(payload)


class _CorruptResultWireAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-corrupt-result-wire-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = super().execute_transcript_v1(request)
        object.__setattr__(result, "result_root", "sha256:" + "0" * 64)
        return result


class _DeniedCurrentCertificateActionAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-denied-current-action-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = super().execute_transcript_v1(request)
        payload = result.to_dict()
        payload["publication_authorized"] = False
        payload["execution_authorized"] = False
        payload["result_root"] = ""
        return RuntimeTranscriptResultV1.from_dict(payload)


class _CheckpointFailureAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-checkpoint-failure-v1"

    def read_driver_checkpoint_v1(
        self,
        checkpoint_wire: str,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        raise OSError("checkpoint unavailable")


class _CheckpointBindingAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-checkpoint-binding-v1"

    def read_driver_checkpoint_v1(
        self,
        checkpoint_wire: str,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        return None


class _CheckpointTamperAcceptingAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-checkpoint-tamper-v1"

    def read_driver_checkpoint_v1(
        self,
        checkpoint_wire: str,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        try:
            return super().read_driver_checkpoint_v1(
                checkpoint_wire,
                scope_ref,
                driver_id,
                idempotency_key,
            )
        except Exception:
            return None


class _GovernanceReaderFailureAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-governance-reader-failure-v1"

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        raise OSError("governance recovery unavailable")


class _UnexpectedGovernanceReaderAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-unexpected-governance-reader-v1"

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        return cast(GovernanceStateReaderV2, object())


class _FailingGovernanceReader:
    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        raise OSError("recovered head unavailable")

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        raise OSError("recovered state unavailable")

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        raise OSError("recovered commit view unavailable")


class _RecoveryComputationFailureAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-recovery-computation-failure-v1"

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        reader = super().open_recovered_governance_reader_v1(request_root, scope_ref)
        if reader is None:
            return None
        return _FailingGovernanceReader()


class _CrossBoundGovernanceReaderAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-cross-bound-governance-reader-v1"

    def __init__(self, *, raise_cross_binding: bool) -> None:
        super().__init__()
        self._recovered_reader: GovernanceStateReaderV2 | None = None
        self._raise_cross_binding = raise_cross_binding

    def open_recovered_governance_reader_v1(
        self,
        request_root: str,
        scope_ref: str,
    ) -> GovernanceStateReaderV2 | None:
        reader = super().open_recovered_governance_reader_v1(request_root, scope_ref)
        if reader is not None:
            self._recovered_reader = reader
            return reader
        if self._recovered_reader is None:
            return None
        if self._raise_cross_binding:
            raise OSError("cross-bound governance reader lookup failed")
        return self._recovered_reader


class _CertificateReaderFailureAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-certificate-reader-failure-v1"

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
        raise OSError("certificate recovery unavailable")


class _MalformedCertificateStatesAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-malformed-certificate-states-v1"

    def __init__(self, states: object) -> None:
        super().__init__()
        self._states = states

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
        return cast(
            tuple[
                VerifiedCommitCertificateStateV2,
                VerifiedCommitCertificateStateV2 | None,
            ]
            | None,
            self._states,
        )


class _MalformedCertificateSuccessorAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-malformed-successor-v1"

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
        states = super().open_recovered_certificate_states_v1(
            request_root,
            scope_ref,
        )
        if states is None:
            return None
        return cast(
            tuple[
                VerifiedCommitCertificateStateV2,
                VerifiedCommitCertificateStateV2 | None,
            ],
            (states[0], object()),
        )


class _CertificateObservationAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-certificate-observation-v1"

    def __init__(self, *, raise_cross_binding: bool) -> None:
        super().__init__()
        self._primary_request_root = ""
        self._primary_scope_ref = ""
        self._primary_states: (
            tuple[
                VerifiedCommitCertificateStateV2,
                VerifiedCommitCertificateStateV2 | None,
            ]
            | None
        ) = None
        self._raise_cross_binding = raise_cross_binding

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        result = super().execute_transcript_v1(request)
        self._primary_request_root = request.request_root
        self._primary_scope_ref = request.scope.scope_ref
        return result

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
        if (
            request_root == self._primary_request_root
            and scope_ref == self._primary_scope_ref
        ):
            states = super().open_recovered_certificate_states_v1(
                request_root,
                scope_ref,
            )
            self._primary_states = states
            return states
        if self._raise_cross_binding:
            raise OSError("cross-bound certificate lookup failed")
        return self._primary_states


class _MalformedInputAcceptingAdapter(ReferenceRuntimeIntegrationAdapterV1):
    implementation_id = "tests-runtime-integration-malformed-input-accepting-v1"

    def execute_transcript_v1(
        self,
        request: RuntimeTranscriptRequestV1,
    ) -> RuntimeTranscriptResultV1:
        try:
            return super().execute_transcript_v1(request)
        except Exception:
            return cast(RuntimeTranscriptResultV1, object())


@pytest.mark.parametrize(
    ("adapter", "detail"),
    [
        (cast(RuntimeIntegrationAdapterV1, object()), "adapter_protocol"),
        (_ExplodingIdentityAdapter(), "adapter_exception:OSError"),
        (_ExecutionFailureAdapter(), "adapter_exception:OSError"),
        (_ReboundResultAdapter(), "implementation_binding"),
        (_CorruptResultWireAdapter(), "result_wire"),
        (_DeniedCurrentCertificateActionAdapter(), "action_projection"),
        (_CheckpointFailureAdapter(), "checkpoint_reader:OSError"),
        (_CheckpointBindingAdapter(), "checkpoint_reader_binding"),
        (_CheckpointTamperAcceptingAdapter(), "checkpoint_tamper_accepted"),
        (_GovernanceReaderFailureAdapter(), "governance_recovery_reader:OSError"),
        (_UnexpectedGovernanceReaderAdapter(), "unexpected_governance_recovery_reader"),
        (_RecoveryComputationFailureAdapter(), "governance_recovery_result"),
        (
            _CrossBoundGovernanceReaderAdapter(raise_cross_binding=True),
            "governance_recovery_binding:OSError",
        ),
        (
            _CrossBoundGovernanceReaderAdapter(raise_cross_binding=False),
            "governance_recovery_binding",
        ),
        (_CertificateReaderFailureAdapter(), "certificate_recovery_reader:OSError"),
        (_MalformedCertificateStatesAdapter(object()), "certificate_recovery_reader"),
        (
            _MalformedCertificateStatesAdapter((object(), None)),
            "certificate_recovery_reader",
        ),
        (
            _MalformedCertificateStatesAdapter(
                (cast(VerifiedCommitCertificateStateV2, object()), object())
            ),
            "certificate_recovery_reader",
        ),
        (_MalformedCertificateSuccessorAdapter(), "certificate_recovery_reader"),
        (
            _CertificateObservationAdapter(raise_cross_binding=True),
            "certificate_recovery_binding:OSError",
        ),
        (
            _CertificateObservationAdapter(raise_cross_binding=False),
            "certificate_recovery_binding",
        ),
        (_MalformedInputAcceptingAdapter(), "cross-scope:accepted"),
    ],
)
def test_runtime_integration_public_tck_rejects_adversarial_adapters(
    adapter: RuntimeIntegrationAdapterV1,
    detail: str,
) -> None:
    result = run_runtime_integration_conformance_v1(adapter)
    assert not result.ok
    assert detail in result.detail
