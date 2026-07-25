"""Public expected-free Runtime Integration transcript ABI v1.

The ABI describes a deterministic composition transcript.  It does not run a
provider, schedule agents, create clocks, or grant Governance authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pheroos.conformance.runtime_compatibility import RuntimeCompatibilityClaimV1
from pheroos.drivers import (
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceVerifiedSignalRequestV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
)
from pheroos.governance.commit_decision_v2 import CommitDecisionOutcomeV2
from pheroos.governance.commit_finality_v2 import CommitFinalityProjectionV2
from pheroos.governance.commit_certificate_v2 import (
    VerifiedCommitCertificateStateV2,
)
from pheroos.kernel import RuntimeScope
from pheroos.protocol import ScopedCapabilityManifestV2
from pheroos.trace import ScopedTraceCheckpointV2

from pheroos.conformance._runtime_integration_codec import (
    RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
    RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1,
    RUNTIME_INTEGRATION_CONTROL_VERSION_V1,
    RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1,
    RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1,
    RuntimeIntegrationTranscriptErrorV1,
)
from pheroos.conformance._runtime_integration_contracts import (
    RuntimeCommitObservationV1,
    RuntimeControlInputV1,
    RuntimeIntegrationAdapterV1,
    RuntimeTranscriptDispositionV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    RuntimeTranscriptStepV1,
)
from pheroos.conformance._runtime_integration_fixture import (
    build_runtime_integration_request_v1,
)
from pheroos.conformance._runtime_integration_reference import (
    ReferenceRuntimeIntegrationAdapterV1,
)
from pheroos.conformance._runtime_integration_store_factory import (
    IndependentRuntimeIntegrationStoreFactoryV1,
)
from pheroos.conformance.report import CheckResult


# Re-homed public records retain postponed annotations.  These hidden bindings
# keep ``typing.get_type_hints`` functional without expanding ``__all__``.
_ANNOTATION_GLOBALS = (
    Any,
    Mapping,
    Sequence,
    RuntimeCompatibilityClaimV1,
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    GovernanceIssuerGrantV2,
    GovernanceVerifiedSignalRequestV2,
    AuthorityDomainV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
    BaselineOutputRequestV2,
    BaselineOutputResultV2,
    CommitDecisionOutcomeV2,
    CommitFinalityProjectionV2,
    VerifiedCommitCertificateStateV2,
    RuntimeScope,
    ScopedCapabilityManifestV2,
    ScopedTraceCheckpointV2,
)


def run_runtime_integration_conformance_v1(
    adapter: RuntimeIntegrationAdapterV1,
) -> CheckResult:
    """Run the exact v1 matrix without creating a runtime or provider."""

    from pheroos.conformance.checks.runtime_integration_v1_contract import (
        run_runtime_integration_conformance_v1 as _run,
    )

    return _run(adapter)


_PUBLIC_MODULE = __name__
for _item in (
    RuntimeCommitObservationV1,
    RuntimeControlInputV1,
    RuntimeIntegrationAdapterV1,
    RuntimeIntegrationTranscriptErrorV1,
    ReferenceRuntimeIntegrationAdapterV1,
    IndependentRuntimeIntegrationStoreFactoryV1,
    RuntimeTranscriptDispositionV1,
    RuntimeTranscriptRequestV1,
    RuntimeTranscriptResultV1,
    RuntimeTranscriptStepV1,
    build_runtime_integration_request_v1,
    run_runtime_integration_conformance_v1,
):
    _item.__module__ = _PUBLIC_MODULE
del _item


__all__ = [
    "RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1",
    "RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1",
    "RUNTIME_INTEGRATION_CONTROL_VERSION_V1",
    "RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1",
    "RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1",
    "RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1",
    "RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1",
    "RuntimeControlInputV1",
    "RuntimeCommitObservationV1",
    "IndependentRuntimeIntegrationStoreFactoryV1",
    "RuntimeIntegrationAdapterV1",
    "RuntimeIntegrationTranscriptErrorV1",
    "ReferenceRuntimeIntegrationAdapterV1",
    "RuntimeTranscriptDispositionV1",
    "RuntimeTranscriptRequestV1",
    "RuntimeTranscriptResultV1",
    "RuntimeTranscriptStepV1",
    "build_runtime_integration_request_v1",
    "run_runtime_integration_conformance_v1",
]
