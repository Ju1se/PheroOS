"""Static declarations for the Conformance public facade."""

from types import MappingProxyType


PUBLIC_API_ORDER_SHA256 = "1c44a26c233eca371ec560381807fc81adb6157452e79a9a9b5cd671316e24ae"
PUBLIC_API = MappingProxyType(
    {
        "COMMIT_TCK_ARTIFACT": ("pheroos.conformance.commit_tck", "COMMIT_TCK_ARTIFACT"),
        "COMMIT_TCK_SCHEMA_ID": ("pheroos.conformance.commit_tck", "COMMIT_TCK_SCHEMA_ID"),
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
