"""Public runtime ABI-composition manifest and exact compatibility report.

The manifest declares compatible protocol-core version IDs.  It neither
attests to an implementation nor grants Governance authority; implementation
compatibility still requires the named TCKs and their reports.
"""

from __future__ import annotations

from pheroos.conformance._runtime_compatibility_catalog import (
    RUNTIME_COMPATIBILITY_ARTIFACT_V1,
    build_runtime_compatibility_manifest_v1,
    load_runtime_compatibility_manifest_v1,
    runtime_compatibility_artifact_digest_v1,
)
from pheroos.conformance._runtime_compatibility_codec import (
    RUNTIME_BASELINE_PROFILE_VERSION_V1,
    RUNTIME_COMPATIBILITY_CLAIM_VERSION_V1,
    RUNTIME_COMPATIBILITY_MANIFEST_VERSION_V1,
    RUNTIME_COMPATIBILITY_MAX_WIRE_BYTES_V1,
    RUNTIME_COMPATIBILITY_REPORT_VERSION_V1,
    RuntimeCompatibilityErrorV1,
)
from pheroos.conformance._runtime_compatibility_contracts import (
    RuntimeCompatibilityCapabilitySpecV1,
    RuntimeCompatibilityClaimV1,
    RuntimeCompatibilityComponentClaimV1,
    RuntimeCompatibilityManifestV1,
    RuntimeCompatibilityProfileSpecV1,
    RuntimeCompatibilityRequirementV1,
)
from pheroos.conformance._runtime_compatibility_evaluation import (
    RuntimeCompatibilityDiagnosticCodeV1,
    RuntimeCompatibilityDiagnosticV1,
    RuntimeCompatibilityReportV1,
    RuntimeCompatibilityStatusV1,
    create_runtime_compatibility_claim_v1,
    evaluate_runtime_compatibility_v1,
)


_CANONICAL_MODULE = __name__
for _public_object in (
    RuntimeCompatibilityCapabilitySpecV1,
    RuntimeCompatibilityClaimV1,
    RuntimeCompatibilityComponentClaimV1,
    RuntimeCompatibilityDiagnosticCodeV1,
    RuntimeCompatibilityDiagnosticV1,
    RuntimeCompatibilityErrorV1,
    RuntimeCompatibilityManifestV1,
    RuntimeCompatibilityProfileSpecV1,
    RuntimeCompatibilityReportV1,
    RuntimeCompatibilityRequirementV1,
    RuntimeCompatibilityStatusV1,
    build_runtime_compatibility_manifest_v1,
    create_runtime_compatibility_claim_v1,
    evaluate_runtime_compatibility_v1,
    load_runtime_compatibility_manifest_v1,
    runtime_compatibility_artifact_digest_v1,
):
    _public_object.__module__ = _CANONICAL_MODULE
del _public_object


__all__ = [
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
]
