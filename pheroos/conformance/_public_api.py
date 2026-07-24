"""Static declarations for the Conformance public facade."""

from types import MappingProxyType


PUBLIC_API_ORDER_SHA256 = (
    "7e79c25d406312ea47cb56da01af516fc268e622237a5c036c33002839961f18"
)
PUBLIC_API = MappingProxyType(
    {
        "COMMIT_TCK_ARTIFACT": (
            "pheroos.conformance.commit_tck",
            "COMMIT_TCK_ARTIFACT",
        ),
        "COMMIT_TCK_SCHEMA_ID": (
            "pheroos.conformance.commit_tck",
            "COMMIT_TCK_SCHEMA_ID",
        ),
        "COMMIT_TCK_VERSION": ("pheroos.conformance.commit_tck", "COMMIT_TCK_VERSION"),
        "CONFORMANCE_REPORT_SCHEMA_ID": (
            "pheroos.conformance.report",
            "CONFORMANCE_REPORT_SCHEMA_ID",
        ),
        "CONFORMANCE_REPORT_VERSION": (
            "pheroos.conformance.report",
            "CONFORMANCE_REPORT_VERSION",
        ),
        "CheckResult": ("pheroos.conformance.report", "CheckResult"),
        "CommitTckAdapter": ("pheroos.conformance.commit_tck", "CommitTckAdapter"),
        "CommitTckReport": ("pheroos.conformance.commit_tck", "CommitTckReport"),
        "CommitTckResult": ("pheroos.conformance.commit_tck", "CommitTckResult"),
        "CommitTckVector": ("pheroos.conformance.commit_tck", "CommitTckVector"),
        "ConformanceReport": ("pheroos.conformance.report", "ConformanceReport"),
        "ConformanceProfile": ("pheroos.conformance.profile", "ConformanceProfile"),
        "ConformanceSubjectKind": (
            "pheroos.conformance.report",
            "ConformanceSubjectKind",
        ),
        "GovernanceStateStoreConformanceAdapter": (
            "pheroos.conformance.checks.authority_ledger_contract",
            "GovernanceStateStoreConformanceAdapter",
        ),
        "GOVERNANCE_STATE_STORE_FAILURE_STAGES": (
            "pheroos.conformance.checks.authority_ledger_contract",
            "GOVERNANCE_STATE_STORE_FAILURE_STAGES",
        ),
        "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION": (
            "pheroos.conformance.checks.authority_ledger_contract",
            "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION",
        ),
        "PHEROOS_IMPLEMENTATION_ID": (
            "pheroos.conformance.report",
            "PHEROOS_IMPLEMENTATION_ID",
        ),
        "ReferenceCommitTckAdapter": (
            "pheroos.conformance.commit_tck",
            "ReferenceCommitTckAdapter",
        ),
        "ReferenceGovernanceStateStoreConformanceAdapter": (
            "pheroos.conformance.checks.authority_ledger_contract",
            "ReferenceGovernanceStateStoreConformanceAdapter",
        ),
        "ReferenceTraceStoreConformanceAdapter": (
            "pheroos.conformance.checks.trace_store_contract",
            "ReferenceTraceStoreConformanceAdapter",
        ),
        "TraceStoreConformanceAdapter": (
            "pheroos.conformance.checks.trace_store_contract",
            "TraceStoreConformanceAdapter",
        ),
        "TRACE_STORE_CONFORMANCE_VERSION": (
            "pheroos.conformance.checks.trace_store_contract",
            "TRACE_STORE_CONFORMANCE_VERSION",
        ),
        "commit_tck_artifact_root": (
            "pheroos.conformance.commit_tck",
            "commit_tck_artifact_root",
        ),
        "commit_tck_schema": ("pheroos.conformance.commit_tck", "commit_tck_schema"),
        "conformance_report_schema": (
            "pheroos.conformance.report",
            "conformance_report_schema",
        ),
        "load_commit_tck_vectors": (
            "pheroos.conformance.commit_tck",
            "load_commit_tck_vectors",
        ),
        "profile_for_manifest": ("pheroos.conformance.profile", "profile_for_manifest"),
        "run_commit_tck": ("pheroos.conformance.commit_tck", "run_commit_tck"),
        "run_conformance": ("pheroos.conformance.runner", "run_conformance"),
        "run_governance_state_store_conformance": (
            "pheroos.conformance.checks.authority_ledger_contract",
            "run_governance_state_store_conformance",
        ),
        "run_trace_store_conformance": (
            "pheroos.conformance.checks.trace_store_contract",
            "run_trace_store_conformance",
        ),
        "run_source_conformance": (
            "pheroos.conformance.runner",
            "run_source_conformance",
        ),
        "validate_manifest": ("pheroos.conformance.runner", "validate_manifest"),
        "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2",
        ),
        "GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2",
        ),
        "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
        ),
        "GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2",
        ),
        "GovernanceStateStoreConformanceAdapterV2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "GovernanceStateStoreConformanceAdapterV2",
        ),
        "ReferenceGovernanceStateStoreConformanceAdapterV2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "ReferenceGovernanceStateStoreConformanceAdapterV2",
        ),
        "run_governance_state_store_conformance_v2": (
            "pheroos.conformance.checks.authority_store_v2_contract",
            "run_governance_state_store_conformance_v2",
        ),
        "GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.authority_session_v2_contract",
            "GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_authority_session_conformance_v2": (
            "pheroos.conformance.checks.authority_session_v2_contract",
            "run_governance_authority_session_conformance_v2",
        ),
        "GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.baseline_output_v2_contract",
            "GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_baseline_output_conformance_v2": (
            "pheroos.conformance.checks.baseline_output_v2_contract",
            "run_governance_baseline_output_conformance_v2",
        ),
        "GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.hybrid_replay_v2_contract",
            "GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_hybrid_replay_conformance_v2": (
            "pheroos.conformance.checks.hybrid_replay_v2_contract",
            "run_governance_hybrid_replay_conformance_v2",
        ),
        "GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.commit_replay_v2_contract",
            "GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_commit_replay_conformance_v2": (
            "pheroos.conformance.checks.commit_replay_v2_contract",
            "run_governance_commit_replay_conformance_v2",
        ),
        "GOVERNANCE_RISK_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.risk_v2_contract",
            "GOVERNANCE_RISK_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_risk_conformance_v2": (
            "pheroos.conformance.checks.risk_v2_contract",
            "run_governance_risk_conformance_v2",
        ),
        "GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.support_v2_contract",
            "GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_support_conformance_v2": (
            "pheroos.conformance.checks.support_v2_contract",
            "run_governance_support_conformance_v2",
        ),
        "GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.commit_gate_v2_contract",
            "GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_commit_gate_conformance_v2": (
            "pheroos.conformance.checks.commit_gate_v2_contract",
            "run_governance_commit_gate_conformance_v2",
        ),
        "GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.commit_evidence_v2_contract",
            "GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_commit_evidence_conformance_v2": (
            "pheroos.conformance.checks.commit_evidence_v2_contract",
            "run_governance_commit_evidence_conformance_v2",
        ),
        "GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.commit_certificate_v2_contract",
            "GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2",
        ),
        "CommitCertificateConformanceAdapterV2": (
            "pheroos.conformance.checks.commit_certificate_v2_contract",
            "CommitCertificateConformanceAdapterV2",
        ),
        "IndependentStdlibCommitCertificateConformanceAdapterV2": (
            "pheroos.conformance.checks.commit_certificate_v2_contract",
            "IndependentStdlibCommitCertificateConformanceAdapterV2",
        ),
        "ReferenceCommitCertificateConformanceAdapterV2": (
            "pheroos.conformance.checks.commit_certificate_v2_contract",
            "ReferenceCommitCertificateConformanceAdapterV2",
        ),
        "run_governance_commit_certificate_conformance_v2": (
            "pheroos.conformance.checks.commit_certificate_v2_contract",
            "run_governance_commit_certificate_conformance_v2",
        ),
        "GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.commit_decision_v2_contract",
            "GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_commit_decision_conformance_v2": (
            "pheroos.conformance.checks.commit_decision_v2_contract",
            "run_governance_commit_decision_conformance_v2",
        ),
        "GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.distributed_commit_v2_contract",
            "GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_distributed_commit_conformance_v2": (
            "pheroos.conformance.checks.distributed_commit_v2_contract",
            "run_governance_distributed_commit_conformance_v2",
        ),
        "GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.commit_finality_v2_contract",
            "GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2",
        ),
        "run_governance_commit_finality_conformance_v2": (
            "pheroos.conformance.checks.commit_finality_v2_contract",
            "run_governance_commit_finality_conformance_v2",
        ),
        "DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2": (
            "pheroos.conformance.checks.driver_invocation_v2_contract",
            "DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2",
        ),
        "DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.driver_invocation_v2_contract",
            "DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2",
        ),
        "DriverInvocationStoreConformanceAdapterV2": (
            "pheroos.conformance.checks.driver_invocation_v2_contract",
            "DriverInvocationStoreConformanceAdapterV2",
        ),
        "ReferenceDriverInvocationStoreConformanceAdapterV2": (
            "pheroos.conformance.checks.driver_invocation_v2_contract",
            "ReferenceDriverInvocationStoreConformanceAdapterV2",
        ),
        "run_driver_invocation_store_conformance_v2": (
            "pheroos.conformance.checks.driver_invocation_v2_contract",
            "run_driver_invocation_store_conformance_v2",
        ),
        "SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2": (
            "pheroos.conformance.checks.scoped_trace_store_v2_contract",
            "SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2",
        ),
        "SCOPED_TRACE_STORE_FAILURE_STAGES_V2": (
            "pheroos.conformance.checks.scoped_trace_store_v2_contract",
            "SCOPED_TRACE_STORE_FAILURE_STAGES_V2",
        ),
        "ReferenceScopedTraceStoreConformanceAdapterV2": (
            "pheroos.conformance.checks.scoped_trace_store_v2_contract",
            "ReferenceScopedTraceStoreConformanceAdapterV2",
        ),
        "ScopedTraceStoreConformanceAdapterV2": (
            "pheroos.conformance.checks.scoped_trace_store_v2_contract",
            "ScopedTraceStoreConformanceAdapterV2",
        ),
        "run_scoped_trace_store_conformance_v2": (
            "pheroos.conformance.checks.scoped_trace_store_v2_contract",
            "run_scoped_trace_store_conformance_v2",
        ),
        "RUNTIME_BASELINE_PROFILE_VERSION_V1": (
            "pheroos.conformance.runtime_compatibility",
            "RUNTIME_BASELINE_PROFILE_VERSION_V1",
        ),
        "RUNTIME_COMPATIBILITY_ARTIFACT_V1": (
            "pheroos.conformance.runtime_compatibility",
            "RUNTIME_COMPATIBILITY_ARTIFACT_V1",
        ),
        "RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1": (
            "pheroos.conformance.runtime_compatibility",
            "RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1",
        ),
        "RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1": (
            "pheroos.conformance.runtime_compatibility",
            "RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1",
        ),
        "RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1": (
            "pheroos.conformance.runtime_compatibility",
            "RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1",
        ),
        "RUNTIME_COMPATIBILITY_REPORT_VERSION_V1": (
            "pheroos.conformance.runtime_compatibility",
            "RUNTIME_COMPATIBILITY_REPORT_VERSION_V1",
        ),
        "RuntimeCompatibilityCapabilitySpecV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityCapabilitySpecV1",
        ),
        "RuntimeCompatibilityClaimV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityClaimV1",
        ),
        "RuntimeCompatibilityComponentClaimV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityComponentClaimV1",
        ),
        "RuntimeCompatibilityDiagnosticCodeV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityDiagnosticCodeV1",
        ),
        "RuntimeCompatibilityDiagnosticV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityDiagnosticV1",
        ),
        "RuntimeCompatibilityErrorV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityErrorV1",
        ),
        "RuntimeCompatibilityManifestV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityManifestV1",
        ),
        "RuntimeCompatibilityProfileSpecV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityProfileSpecV1",
        ),
        "RuntimeCompatibilityReportV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityReportV1",
        ),
        "RuntimeCompatibilityRequirementV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityRequirementV1",
        ),
        "RuntimeCompatibilityStatusV1": (
            "pheroos.conformance.runtime_compatibility",
            "RuntimeCompatibilityStatusV1",
        ),
        "build_runtime_compatibility_manifest_v1": (
            "pheroos.conformance.runtime_compatibility",
            "build_runtime_compatibility_manifest_v1",
        ),
        "create_runtime_compatibility_claim_v1": (
            "pheroos.conformance.runtime_compatibility",
            "create_runtime_compatibility_claim_v1",
        ),
        "evaluate_runtime_compatibility_v1": (
            "pheroos.conformance.runtime_compatibility",
            "evaluate_runtime_compatibility_v1",
        ),
        "load_runtime_compatibility_manifest_v1": (
            "pheroos.conformance.runtime_compatibility",
            "load_runtime_compatibility_manifest_v1",
        ),
        "runtime_compatibility_artifact_digest_v1": (
            "pheroos.conformance.runtime_compatibility",
            "runtime_compatibility_artifact_digest_v1",
        ),
        "RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1",
        ),
        "RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_COMMIT_OBSERVATION_VERSION_V1",
        ),
        "RUNTIME_INTEGRATION_CONTROL_VERSION_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_CONTROL_VERSION_V1",
        ),
        "RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_MAX_WIRE_BYTES_V1",
        ),
        "RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_TRANSCRIPT_REQUEST_VERSION_V1",
        ),
        "RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_TRANSCRIPT_RESULT_VERSION_V1",
        ),
        "RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1": (
            "pheroos.conformance.runtime_integration",
            "RUNTIME_INTEGRATION_TRANSCRIPT_STEP_VERSION_V1",
        ),
        "RuntimeControlInputV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeControlInputV1",
        ),
        "RuntimeCommitObservationV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeCommitObservationV1",
        ),
        "IndependentRuntimeIntegrationStoreFactoryV1": (
            "pheroos.conformance.runtime_integration",
            "IndependentRuntimeIntegrationStoreFactoryV1",
        ),
        "RuntimeIntegrationAdapterV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeIntegrationAdapterV1",
        ),
        "RuntimeIntegrationTranscriptErrorV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeIntegrationTranscriptErrorV1",
        ),
        "ReferenceRuntimeIntegrationAdapterV1": (
            "pheroos.conformance.runtime_integration",
            "ReferenceRuntimeIntegrationAdapterV1",
        ),
        "RuntimeTranscriptDispositionV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeTranscriptDispositionV1",
        ),
        "RuntimeTranscriptRequestV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeTranscriptRequestV1",
        ),
        "RuntimeTranscriptResultV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeTranscriptResultV1",
        ),
        "RuntimeTranscriptStepV1": (
            "pheroos.conformance.runtime_integration",
            "RuntimeTranscriptStepV1",
        ),
        "build_runtime_integration_request_v1": (
            "pheroos.conformance.runtime_integration",
            "build_runtime_integration_request_v1",
        ),
        "run_runtime_integration_conformance_v1": (
            "pheroos.conformance.runtime_integration",
            "run_runtime_integration_conformance_v1",
        ),
    }
)

COMPATIBILITY_MODULES = MappingProxyType(
    {
        "checks": "pheroos.conformance.checks",
        "commit_tck": "pheroos.conformance.commit_tck",
        "commit_tck_v2_protocol": "pheroos.conformance.commit_tck_v2_protocol",
        "profile": "pheroos.conformance.profile",
        "public_api_inventory": "pheroos.conformance.public_api_inventory",
        "public_api_lifecycle": "pheroos.conformance.public_api_lifecycle",
        "report": "pheroos.conformance.report",
        "runner": "pheroos.conformance.runner",
    }
)


__all__ = ["COMPATIBILITY_MODULES", "PUBLIC_API", "PUBLIC_API_ORDER_SHA256"]
