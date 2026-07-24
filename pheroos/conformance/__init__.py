"""Static, thread-safe lazy facade for the Conformance public ABI."""

from importlib import import_module as _import_module
from threading import RLock as _RLock
from typing import TYPE_CHECKING, Any as _Any

from pheroos.conformance._public_api import (
    COMPATIBILITY_MODULES as _COMPATIBILITY_MODULES,
    PUBLIC_API as _PUBLIC_API,
)


if TYPE_CHECKING:
    from pheroos.conformance.commit_tck import (
        COMMIT_TCK_ARTIFACT as COMMIT_TCK_ARTIFACT,
    )
    from pheroos.conformance.commit_tck import (
        COMMIT_TCK_SCHEMA_ID as COMMIT_TCK_SCHEMA_ID,
    )
    from pheroos.conformance.commit_tck import COMMIT_TCK_VERSION as COMMIT_TCK_VERSION
    from pheroos.conformance.report import (
        CONFORMANCE_REPORT_SCHEMA_ID as CONFORMANCE_REPORT_SCHEMA_ID,
    )
    from pheroos.conformance.report import (
        CONFORMANCE_REPORT_VERSION as CONFORMANCE_REPORT_VERSION,
    )
    from pheroos.conformance.report import CheckResult as CheckResult
    from pheroos.conformance.commit_tck import CommitTckAdapter as CommitTckAdapter
    from pheroos.conformance.commit_tck import CommitTckReport as CommitTckReport
    from pheroos.conformance.commit_tck import CommitTckResult as CommitTckResult
    from pheroos.conformance.commit_tck import CommitTckVector as CommitTckVector
    from pheroos.conformance.report import ConformanceReport as ConformanceReport
    from pheroos.conformance.profile import ConformanceProfile as ConformanceProfile
    from pheroos.conformance.report import (
        ConformanceSubjectKind as ConformanceSubjectKind,
    )
    from pheroos.conformance.checks.authority_ledger_contract import (
        GOVERNANCE_STATE_STORE_FAILURE_STAGES as GOVERNANCE_STATE_STORE_FAILURE_STAGES,
    )
    from pheroos.conformance.checks.authority_ledger_contract import (
        GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION as GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2 as GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2 as GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        GOVERNANCE_STATE_STORE_TAMPER_CASES_V2 as GOVERNANCE_STATE_STORE_TAMPER_CASES_V2,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2 as GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
    )
    from pheroos.conformance.checks.authority_ledger_contract import (
        GovernanceStateStoreConformanceAdapter as GovernanceStateStoreConformanceAdapter,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        GovernanceStateStoreConformanceAdapterV2 as GovernanceStateStoreConformanceAdapterV2,
    )
    from pheroos.conformance.report import (
        PHEROOS_IMPLEMENTATION_ID as PHEROOS_IMPLEMENTATION_ID,
    )
    from pheroos.conformance.commit_tck import (
        ReferenceCommitTckAdapter as ReferenceCommitTckAdapter,
    )
    from pheroos.conformance.checks.authority_ledger_contract import (
        ReferenceGovernanceStateStoreConformanceAdapter as ReferenceGovernanceStateStoreConformanceAdapter,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        ReferenceGovernanceStateStoreConformanceAdapterV2 as ReferenceGovernanceStateStoreConformanceAdapterV2,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        ReferenceTraceStoreConformanceAdapter as ReferenceTraceStoreConformanceAdapter,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        TRACE_STORE_CONFORMANCE_VERSION as TRACE_STORE_CONFORMANCE_VERSION,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        TraceStoreConformanceAdapter as TraceStoreConformanceAdapter,
    )
    from pheroos.conformance.commit_tck import (
        commit_tck_artifact_root as commit_tck_artifact_root,
    )
    from pheroos.conformance.commit_tck import commit_tck_schema as commit_tck_schema
    from pheroos.conformance.report import (
        conformance_report_schema as conformance_report_schema,
    )
    from pheroos.conformance.commit_tck import (
        load_commit_tck_vectors as load_commit_tck_vectors,
    )
    from pheroos.conformance.profile import profile_for_manifest as profile_for_manifest
    from pheroos.conformance.commit_tck import run_commit_tck as run_commit_tck
    from pheroos.conformance.runner import run_conformance as run_conformance
    from pheroos.conformance.checks.authority_ledger_contract import (
        run_governance_state_store_conformance as run_governance_state_store_conformance,
    )
    from pheroos.conformance.checks.authority_store_v2_contract import (
        run_governance_state_store_conformance_v2 as run_governance_state_store_conformance_v2,
    )
    from pheroos.conformance.checks.authority_session_v2_contract import (
        GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2 as GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.authority_session_v2_contract import (
        run_governance_authority_session_conformance_v2 as run_governance_authority_session_conformance_v2,
    )
    from pheroos.conformance.checks.baseline_output_v2_contract import (
        GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2 as GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.baseline_output_v2_contract import (
        run_governance_baseline_output_conformance_v2 as run_governance_baseline_output_conformance_v2,
    )
    from pheroos.conformance.checks.hybrid_replay_v2_contract import (
        GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2 as GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.hybrid_replay_v2_contract import (
        run_governance_hybrid_replay_conformance_v2 as run_governance_hybrid_replay_conformance_v2,
    )
    from pheroos.conformance.checks.commit_replay_v2_contract import (
        GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2 as GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.commit_replay_v2_contract import (
        run_governance_commit_replay_conformance_v2 as run_governance_commit_replay_conformance_v2,
    )
    from pheroos.conformance.checks.risk_v2_contract import (
        GOVERNANCE_RISK_CONFORMANCE_VERSION_V2 as GOVERNANCE_RISK_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.risk_v2_contract import (
        run_governance_risk_conformance_v2 as run_governance_risk_conformance_v2,
    )
    from pheroos.conformance.checks.support_v2_contract import (
        GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2 as GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.support_v2_contract import (
        run_governance_support_conformance_v2 as run_governance_support_conformance_v2,
    )
    from pheroos.conformance.checks.commit_gate_v2_contract import (
        GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2 as GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.commit_gate_v2_contract import (
        run_governance_commit_gate_conformance_v2 as run_governance_commit_gate_conformance_v2,
    )
    from pheroos.conformance.checks.commit_evidence_v2_contract import (
        GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2 as GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.commit_evidence_v2_contract import (
        run_governance_commit_evidence_conformance_v2 as run_governance_commit_evidence_conformance_v2,
    )
    from pheroos.conformance.checks.commit_certificate_v2_contract import (
        GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2 as GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.commit_certificate_v2_contract import (
        CommitCertificateConformanceAdapterV2 as CommitCertificateConformanceAdapterV2,
    )
    from pheroos.conformance.checks.commit_certificate_v2_contract import (
        IndependentStdlibCommitCertificateConformanceAdapterV2 as IndependentStdlibCommitCertificateConformanceAdapterV2,
    )
    from pheroos.conformance.checks.commit_certificate_v2_contract import (
        ReferenceCommitCertificateConformanceAdapterV2 as ReferenceCommitCertificateConformanceAdapterV2,
    )
    from pheroos.conformance.checks.commit_certificate_v2_contract import (
        run_governance_commit_certificate_conformance_v2 as run_governance_commit_certificate_conformance_v2,
    )
    from pheroos.conformance.checks.commit_decision_v2_contract import (
        GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2 as GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.commit_decision_v2_contract import (
        run_governance_commit_decision_conformance_v2 as run_governance_commit_decision_conformance_v2,
    )
    from pheroos.conformance.checks.distributed_commit_v2_contract import (
        GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2 as GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.distributed_commit_v2_contract import (
        run_governance_distributed_commit_conformance_v2 as run_governance_distributed_commit_conformance_v2,
    )
    from pheroos.conformance.checks.commit_finality_v2_contract import (
        GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2 as GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2,
    )
    from pheroos.conformance.checks.commit_finality_v2_contract import (
        run_governance_commit_finality_conformance_v2 as run_governance_commit_finality_conformance_v2,
    )
    from pheroos.conformance.checks.trace_store_contract import (
        run_trace_store_conformance as run_trace_store_conformance,
    )
    from pheroos.conformance.runner import (
        run_source_conformance as run_source_conformance,
    )
    from pheroos.conformance.runner import validate_manifest as validate_manifest
    from pheroos.conformance.checks.driver_invocation_v2_contract import (
        DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2 as DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2,
        DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2 as DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2,
        DriverInvocationStoreConformanceAdapterV2 as DriverInvocationStoreConformanceAdapterV2,
        ReferenceDriverInvocationStoreConformanceAdapterV2 as ReferenceDriverInvocationStoreConformanceAdapterV2,
        run_driver_invocation_store_conformance_v2 as run_driver_invocation_store_conformance_v2,
    )
    from pheroos.conformance.checks.scoped_trace_store_v2_contract import (
        SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2 as SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2,
        SCOPED_TRACE_STORE_FAILURE_STAGES_V2 as SCOPED_TRACE_STORE_FAILURE_STAGES_V2,
        ReferenceScopedTraceStoreConformanceAdapterV2 as ReferenceScopedTraceStoreConformanceAdapterV2,
        ScopedTraceStoreConformanceAdapterV2 as ScopedTraceStoreConformanceAdapterV2,
        run_scoped_trace_store_conformance_v2 as run_scoped_trace_store_conformance_v2,
    )
    from pheroos.conformance.runtime_compatibility import (
        RUNTIME_BASELINE_PROFILE_VERSION_V1 as RUNTIME_BASELINE_PROFILE_VERSION_V1,
        RUNTIME_COMPATIBILITY_ARTIFACT_V1 as RUNTIME_COMPATIBILITY_ARTIFACT_V1,
        RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1 as RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1,
        RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1 as RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1,
        RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1 as RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1,
        RUNTIME_COMPATIBILITY_REPORT_VERSION_V1 as RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
        RuntimeCompatibilityCapabilitySpecV1 as RuntimeCompatibilityCapabilitySpecV1,
        RuntimeCompatibilityClaimV1 as RuntimeCompatibilityClaimV1,
        RuntimeCompatibilityComponentClaimV1 as RuntimeCompatibilityComponentClaimV1,
        RuntimeCompatibilityDiagnosticCodeV1 as RuntimeCompatibilityDiagnosticCodeV1,
        RuntimeCompatibilityDiagnosticV1 as RuntimeCompatibilityDiagnosticV1,
        RuntimeCompatibilityErrorV1 as RuntimeCompatibilityErrorV1,
        RuntimeCompatibilityManifestV1 as RuntimeCompatibilityManifestV1,
        RuntimeCompatibilityProfileSpecV1 as RuntimeCompatibilityProfileSpecV1,
        RuntimeCompatibilityReportV1 as RuntimeCompatibilityReportV1,
        RuntimeCompatibilityRequirementV1 as RuntimeCompatibilityRequirementV1,
        RuntimeCompatibilityStatusV1 as RuntimeCompatibilityStatusV1,
        build_runtime_compatibility_manifest_v1 as build_runtime_compatibility_manifest_v1,
        create_runtime_compatibility_claim_v1 as create_runtime_compatibility_claim_v1,
        evaluate_runtime_compatibility_v1 as evaluate_runtime_compatibility_v1,
        load_runtime_compatibility_manifest_v1 as load_runtime_compatibility_manifest_v1,
        runtime_compatibility_artifact_digest_v1 as runtime_compatibility_artifact_digest_v1,
    )
    from pheroos.conformance.runtime_integration import (
        RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1 as RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
        RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1 as RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1,
        RUNTIME_INTEGRATION_CONTROL_VERSION_V1 as RUNTIME_INTEGRATION_CONTROL_VERSION_V1,
        RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1 as RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1,
        RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1 as RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1,
        RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1 as RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1,
        RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1 as RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1,
        RuntimeControlInputV1 as RuntimeControlInputV1,
        RuntimeCommitObservationV1 as RuntimeCommitObservationV1,
        IndependentRuntimeIntegrationStoreFactoryV1 as IndependentRuntimeIntegrationStoreFactoryV1,
        RuntimeIntegrationAdapterV1 as RuntimeIntegrationAdapterV1,
        RuntimeIntegrationTranscriptErrorV1 as RuntimeIntegrationTranscriptErrorV1,
        ReferenceRuntimeIntegrationAdapterV1 as ReferenceRuntimeIntegrationAdapterV1,
        RuntimeTranscriptDispositionV1 as RuntimeTranscriptDispositionV1,
        RuntimeTranscriptRequestV1 as RuntimeTranscriptRequestV1,
        RuntimeTranscriptResultV1 as RuntimeTranscriptResultV1,
        RuntimeTranscriptStepV1 as RuntimeTranscriptStepV1,
        build_runtime_integration_request_v1 as build_runtime_integration_request_v1,
        run_runtime_integration_conformance_v1 as run_runtime_integration_conformance_v1,
    )

del TYPE_CHECKING

__all__ = list(_PUBLIC_API)

_PUBLIC_API_LOCK = _RLock()


def __getattr__(name: str) -> _Any:
    target = _PUBLIC_API.get(name)
    compatibility_module = _COMPATIBILITY_MODULES.get(name)
    if target is None and compatibility_module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _PUBLIC_API_LOCK:
        if name in globals():
            return globals()[name]
        if target is not None:
            module_name, attribute = target
            value = getattr(_import_module(module_name), attribute)
        else:
            assert compatibility_module is not None
            value = _import_module(compatibility_module)
        globals()[name] = value
        return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_PUBLIC_API) | set(_COMPATIBILITY_MODULES))
