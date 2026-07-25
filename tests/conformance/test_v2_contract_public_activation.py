from __future__ import annotations

import ast
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys

import pytest

import pheroos.conformance as conformance
from pheroos.conformance import checks
from pheroos.conformance._public_api import (
    PUBLIC_API,
    PUBLIC_API_ORDER_SHA256,
)


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PUBLIC_API_ORDER_SHA256 = (
    "7e79c25d406312ea47cb56da01af516fc268e622237a5c036c33002839961f18"
)
EXPECTED_PUBLIC_API_ORDER = (
    "COMMIT_TCK_ARTIFACT",
    "COMMIT_TCK_SCHEMA_ID",
    "COMMIT_TCK_VERSION",
    "CONFORMANCE_REPORT_SCHEMA_ID",
    "CONFORMANCE_REPORT_VERSION",
    "CheckResult",
    "CommitTckAdapter",
    "CommitTckReport",
    "CommitTckResult",
    "CommitTckVector",
    "ConformanceReport",
    "ConformanceProfile",
    "ConformanceSubjectKind",
    "GovernanceStateStoreConformanceAdapter",
    "GOVERNANCE_STATE_STORE_FAILURE_STAGES",
    "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION",
    "PHEROOS_IMPLEMENTATION_ID",
    "ReferenceCommitTckAdapter",
    "ReferenceGovernanceStateStoreConformanceAdapter",
    "ReferenceTraceStoreConformanceAdapter",
    "TraceStoreConformanceAdapter",
    "TRACE_STORE_CONFORMANCE_VERSION",
    "commit_tck_artifact_root",
    "commit_tck_schema",
    "conformance_report_schema",
    "load_commit_tck_vectors",
    "profile_for_manifest",
    "run_commit_tck",
    "run_conformance",
    "run_governance_state_store_conformance",
    "run_trace_store_conformance",
    "run_source_conformance",
    "validate_manifest",
    "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2",
    "GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2",
    "GOVERNANCE_STATE_STORE_TAMPER_CASES_V2",
    "GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2",
    "GovernanceStateStoreConformanceAdapterV2",
    "ReferenceGovernanceStateStoreConformanceAdapterV2",
    "run_governance_state_store_conformance_v2",
    "GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2",
    "run_governance_authority_session_conformance_v2",
    "GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2",
    "run_governance_baseline_output_conformance_v2",
    "GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2",
    "run_governance_hybrid_replay_conformance_v2",
    "GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2",
    "run_governance_commit_replay_conformance_v2",
    "GOVERNANCE_RISK_CONFORMANCE_VERSION_V2",
    "run_governance_risk_conformance_v2",
    "GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2",
    "run_governance_support_conformance_v2",
    "GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2",
    "run_governance_commit_gate_conformance_v2",
    "GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2",
    "run_governance_commit_evidence_conformance_v2",
    "GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2",
    "CommitCertificateConformanceAdapterV2",
    "IndependentStdlibCommitCertificateConformanceAdapterV2",
    "ReferenceCommitCertificateConformanceAdapterV2",
    "run_governance_commit_certificate_conformance_v2",
    "GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2",
    "run_governance_commit_decision_conformance_v2",
    "GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2",
    "run_governance_distributed_commit_conformance_v2",
    "GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2",
    "run_governance_commit_finality_conformance_v2",
    "DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2",
    "DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2",
    "DriverInvocationStoreConformanceAdapterV2",
    "ReferenceDriverInvocationStoreConformanceAdapterV2",
    "run_driver_invocation_store_conformance_v2",
    "SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2",
    "SCOPED_TRACE_STORE_FAILURE_STAGES_V2",
    "ReferenceScopedTraceStoreConformanceAdapterV2",
    "ScopedTraceStoreConformanceAdapterV2",
    "run_scoped_trace_store_conformance_v2",
    "RUNTIME_BASELINE_PROFILE_VERSION_V1",
    "RUNTIME_COMPATIBILITY_ARTIFACT_V1",
    "RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1",
    "RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1",
    "RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1",
    "RUNTIME_COMPATIBILITY_REPORT_VERSION_V1",
    "RuntimeCompatibilityCapabilitySpecV1",
    "RuntimeCompatibilityClaimV1",
    "RuntimeCompatibilityComponentClaimV1",
    "RuntimeCompatibilityDiagnosticCodeV1",
    "RuntimeCompatibilityDiagnosticV1",
    "RuntimeCompatibilityErrorV1",
    "RuntimeCompatibilityManifestV1",
    "RuntimeCompatibilityProfileSpecV1",
    "RuntimeCompatibilityReportV1",
    "RuntimeCompatibilityRequirementV1",
    "RuntimeCompatibilityStatusV1",
    "build_runtime_compatibility_manifest_v1",
    "create_runtime_compatibility_claim_v1",
    "evaluate_runtime_compatibility_v1",
    "load_runtime_compatibility_manifest_v1",
    "runtime_compatibility_artifact_digest_v1",
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
)
CONTRACT_EXPORTS = {
    "risk_v2_contract": (
        "GOVERNANCE_RISK_CONFORMANCE_VERSION_V2",
        "run_governance_risk_conformance_v2",
    ),
    "support_v2_contract": (
        "GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2",
        "run_governance_support_conformance_v2",
    ),
    "commit_gate_v2_contract": (
        "GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2",
        "run_governance_commit_gate_conformance_v2",
    ),
    "commit_evidence_v2_contract": (
        "GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2",
        "run_governance_commit_evidence_conformance_v2",
    ),
    "commit_certificate_v2_contract": (
        "GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2",
        "CommitCertificateConformanceAdapterV2",
        "IndependentStdlibCommitCertificateConformanceAdapterV2",
        "ReferenceCommitCertificateConformanceAdapterV2",
        "run_governance_commit_certificate_conformance_v2",
    ),
    "commit_decision_v2_contract": (
        "GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2",
        "run_governance_commit_decision_conformance_v2",
    ),
    "distributed_commit_v2_contract": (
        "GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2",
        "run_governance_distributed_commit_conformance_v2",
    ),
    "commit_finality_v2_contract": (
        "GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2",
        "run_governance_commit_finality_conformance_v2",
    ),
}
NEW_EXPORTS = tuple(
    export for exports in CONTRACT_EXPORTS.values() for export in exports
)
WP06_EXTENSION_MODULES = {
    "pheroos.conformance.checks.driver_invocation_v2_contract": (
        "DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2",
        "DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2",
        "DriverInvocationStoreConformanceAdapterV2",
        "ReferenceDriverInvocationStoreConformanceAdapterV2",
        "run_driver_invocation_store_conformance_v2",
    ),
    "pheroos.conformance.checks.scoped_trace_store_v2_contract": (
        "SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2",
        "SCOPED_TRACE_STORE_FAILURE_STAGES_V2",
        "ReferenceScopedTraceStoreConformanceAdapterV2",
        "ScopedTraceStoreConformanceAdapterV2",
        "run_scoped_trace_store_conformance_v2",
    ),
    "pheroos.conformance.runtime_compatibility": (
        "RUNTIME_BASELINE_PROFILE_VERSION_V1",
        "RUNTIME_COMPATIBILITY_ARTIFACT_V1",
        "RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1",
        "RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1",
        "RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1",
        "RUNTIME_COMPATIBILITY_REPORT_VERSION_V1",
        "RuntimeCompatibilityCapabilitySpecV1",
        "RuntimeCompatibilityClaimV1",
        "RuntimeCompatibilityComponentClaimV1",
        "RuntimeCompatibilityDiagnosticCodeV1",
        "RuntimeCompatibilityDiagnosticV1",
        "RuntimeCompatibilityErrorV1",
        "RuntimeCompatibilityManifestV1",
        "RuntimeCompatibilityProfileSpecV1",
        "RuntimeCompatibilityReportV1",
        "RuntimeCompatibilityRequirementV1",
        "RuntimeCompatibilityStatusV1",
        "build_runtime_compatibility_manifest_v1",
        "create_runtime_compatibility_claim_v1",
        "evaluate_runtime_compatibility_v1",
        "load_runtime_compatibility_manifest_v1",
        "runtime_compatibility_artifact_digest_v1",
    ),
    "pheroos.conformance.runtime_integration": (
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
    ),
}
WP06_CALLABLE_OWNERS = {
    "pheroos.conformance.checks.driver_invocation_v2_contract": ("pheroos.conformance"),
    "pheroos.conformance.checks.scoped_trace_store_v2_contract": (
        "pheroos.conformance"
    ),
    "pheroos.conformance.runtime_compatibility": (
        "pheroos.conformance.runtime_compatibility"
    ),
    "pheroos.conformance.runtime_integration": (
        "pheroos.conformance.runtime_integration"
    ),
}


def _run_child(source: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-c", source],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value


def test_v2_contract_exports_have_exact_order_hash_and_count() -> None:
    assert tuple(PUBLIC_API) == EXPECTED_PUBLIC_API_ORDER
    assert tuple(conformance.__all__) == EXPECTED_PUBLIC_API_ORDER
    assert len(PUBLIC_API) == len(set(PUBLIC_API)) == 118
    observed = sha256("\n".join(PUBLIC_API).encode()).hexdigest()
    assert PUBLIC_API_ORDER_SHA256 == EXPECTED_PUBLIC_API_ORDER_SHA256
    assert observed == EXPECTED_PUBLIC_API_ORDER_SHA256


def test_direct_contract_and_root_exports_preserve_identity_and_module() -> None:
    for module_name, expected_exports in CONTRACT_EXPORTS.items():
        direct = import_module(f"pheroos.conformance.checks.{module_name}")
        assert tuple(direct.__all__) == expected_exports
        for name in expected_exports:
            direct_value = getattr(direct, name)
            assert getattr(conformance, name) is direct_value
            if callable(direct_value):
                assert direct_value.__module__ == "pheroos.conformance"


def test_wp06_direct_and_root_exports_preserve_identity_and_owner() -> None:
    for module_name, expected_exports in WP06_EXTENSION_MODULES.items():
        direct = import_module(module_name)
        assert set(expected_exports) <= set(direct.__all__)
        if module_name.endswith("driver_invocation_v2_contract"):
            assert set(direct.__all__) - set(expected_exports) == {"check"}
        else:
            assert tuple(direct.__all__) == expected_exports
        for name in expected_exports:
            direct_value = getattr(direct, name)
            assert getattr(conformance, name) is direct_value
            if callable(direct_value):
                assert direct_value.__module__ == WP06_CALLABLE_OWNERS[module_name]


def test_root_type_checking_block_covers_every_lazy_export() -> None:
    path = ROOT / "pheroos/conformance/__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    blocks = [
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "TYPE_CHECKING"
    ]
    assert len(blocks) == 1
    imported = {
        alias.asname or alias.name
        for node in blocks[0].body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert imported == set(EXPECTED_PUBLIC_API_ORDER)


def test_checks_namespace_exposes_all_eight_contract_modules() -> None:
    assert set(CONTRACT_EXPORTS) <= set(checks.__all__)
    for module_name in CONTRACT_EXPORTS:
        direct = import_module(f"pheroos.conformance.checks.{module_name}")
        assert getattr(checks, module_name) is direct


def test_fresh_lazy_activation_does_not_load_the_legacy_registry() -> None:
    result = _run_child(
        f"""
import importlib
import json
import sys
import pheroos.conformance as conformance

exports = {NEW_EXPORTS!r}
cold_cached = [name for name in exports if name in conformance.__dict__]
identity = []
for name in exports:
    value = getattr(conformance, name)
    module_name, attribute = conformance._PUBLIC_API[name]
    identity.append(value is getattr(importlib.import_module(module_name), attribute))
print(json.dumps({{
    "cold_cached": cold_cached,
    "identity": all(identity),
    "legacy_registry_loaded": (
        "pheroos.governance._legacy.authority_registry" in sys.modules
    ),
}}))
"""
    )
    assert result == {
        "cold_cached": [],
        "identity": True,
        "legacy_registry_loaded": False,
    }


def test_unknown_names_do_not_leak_from_root_or_checks() -> None:
    unknown = "GOVERNANCE_UNKNOWN_CONFORMANCE_VERSION_V2"
    with pytest.raises(
        AttributeError,
        match="module 'pheroos.conformance' has no attribute",
    ):
        getattr(conformance, unknown)
    with pytest.raises(AttributeError, match=unknown):
        getattr(checks, unknown)
    assert unknown not in conformance.__dict__
    assert unknown not in conformance.__all__
    assert unknown not in dir(conformance)
    assert unknown not in vars(checks)
    assert unknown not in checks.__all__
    assert unknown not in dir(checks)
