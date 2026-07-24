"""Current provider-neutral runtime compatibility composition catalog."""

from __future__ import annotations

from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any

from pheroos.conformance._runtime_compatibility_contracts import (
    RuntimeCompatibilityCapabilitySpecV1,
    RuntimeCompatibilityManifestV1,
    RuntimeCompatibilityProfileSpecV1,
    RuntimeCompatibilityRequirementV1,
)
from pheroos.conformance.checks.authority_session_v2_contract import (
    GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.baseline_output_v2_contract import (
    GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.commit_certificate_v2_contract import (
    GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.commit_decision_v2_contract import (
    GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.commit_evidence_v2_contract import (
    GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.commit_finality_v2_contract import (
    GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.commit_gate_v2_contract import (
    GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.commit_replay_v2_contract import (
    GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.distributed_commit_v2_contract import (
    GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.driver_invocation_v2_contract import (
    DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.hybrid_replay_v2_contract import (
    GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.risk_v2_contract import (
    GOVERNANCE_RISK_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.scoped_trace_store_v2_contract import (
    SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.support_v2_contract import (
    GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.profile import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    COMMIT_INTEGRITY_PROFILE_VERSION,
    CORE_PROFILE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    HYBRID_COMMIT_PROFILE_VERSION,
    HYBRID_SWARM_PROFILE_VERSION,
    SWARM_PROFILE_VERSION,
)
from pheroos.conformance.public_api_inventory import PUBLIC_API_INVENTORY_VERSION
from pheroos.conformance.report import CONFORMANCE_REPORT_VERSION
from pheroos.drivers import (
    DRIVER_INVOCATION_CHECKPOINT_VERSION_V2,
    DRIVER_INVOCATION_RECEIPT_VERSION_V2,
    DRIVER_INVOCATION_REPLY_VERSION_V2,
    DRIVER_INVOCATION_REQUEST_VERSION_V2,
    DRIVER_INVOCATION_RESULT_VERSION_V2,
    DRIVER_INVOCATION_STORE_VERSION_V2,
)
from pheroos.governance import (
    BASELINE_OUTPUT_REQUEST_SCHEMA_V2,
    BASELINE_OUTPUT_RESULT_SCHEMA_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
)
from pheroos.kernel import (
    KERNEL_PLAN_VERSION_V2,
    RUNTIME_SCOPE_SCHEMA_V1_ID,
    RUNTIME_SCOPE_VERSION,
)
from pheroos.protocol import (
    AUTHORITY_CANONICAL_VERSION_V2,
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    CAPABILITY_SCHEMA_V3_ID,
    PROTOCOL_SCHEMA_V3_ID,
    PROTOCOL_VERSION_V2,
)
from pheroos.trace import (
    SCOPED_TRACE_CHECKPOINT_VERSION_V2,
    SCOPED_TRACE_EVENT_VERSION,
    SCOPED_TRACE_RECORD_VERSION_V2,
    SCOPED_TRACE_STORE_VERSION_V2,
)

from pheroos.conformance._runtime_compatibility_codec import (
    RUNTIME_BASELINE_PROFILE_VERSION_V1,
    RuntimeCompatibilityErrorV1,
)
from pheroos.conformance._runtime_integration_codec import (
    RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
)


RUNTIME_COMPATIBILITY_ARTIFACT_V1 = resources.files("pheroos.conformance").joinpath(
    "abi", "runtime-compatibility-v1.json"
)
_PUBLIC_API_INVENTORY_ARTIFACT = resources.files("pheroos.conformance").joinpath(
    "abi", "public-python-api-v1.json"
)

_REQUIRED_VERSIONS = (
    ("conformance.abi.public-python-api", PUBLIC_API_INVENTORY_VERSION),
    ("conformance.report", CONFORMANCE_REPORT_VERSION),
    (
        "conformance.tck.driver-invocation-store",
        DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2,
    ),
    (
        "conformance.tck.governance-baseline-output",
        GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2,
    ),
    (
        "conformance.tck.governance-state-store",
        GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    ),
    (
        "conformance.tck.scoped-trace-store",
        SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2,
    ),
    (
        "conformance.tck.runtime-integration",
        RUNTIME_INTEGRATION_CONFORMANCE_VERSION_V1,
    ),
    ("drivers.invocation.checkpoint", DRIVER_INVOCATION_CHECKPOINT_VERSION_V2),
    ("drivers.invocation.receipt", DRIVER_INVOCATION_RECEIPT_VERSION_V2),
    ("drivers.invocation.reply", DRIVER_INVOCATION_REPLY_VERSION_V2),
    ("drivers.invocation.request", DRIVER_INVOCATION_REQUEST_VERSION_V2),
    ("drivers.invocation.result", DRIVER_INVOCATION_RESULT_VERSION_V2),
    ("drivers.invocation.store", DRIVER_INVOCATION_STORE_VERSION_V2),
    ("governance.baseline-output.request", BASELINE_OUTPUT_REQUEST_SCHEMA_V2),
    ("governance.baseline-output.result", BASELINE_OUTPUT_RESULT_SCHEMA_V2),
    ("governance.state-store", GOVERNANCE_STATE_STORE_VERSION_V2),
    ("kernel.plan", KERNEL_PLAN_VERSION_V2),
    ("kernel.runtime-scope", RUNTIME_SCOPE_VERSION),
    ("kernel.runtime-scope.schema", RUNTIME_SCOPE_SCHEMA_V1_ID),
    ("protocol.authority-canonical", AUTHORITY_CANONICAL_VERSION_V2),
    ("protocol.baseline-output-policy", BASELINE_OUTPUT_POLICY_VERSION_V2),
    ("protocol.capability.schema", CAPABILITY_SCHEMA_V3_ID),
    ("protocol.manifest", PROTOCOL_VERSION_V2),
    ("protocol.manifest.schema", PROTOCOL_SCHEMA_V3_ID),
    ("trace.scoped-event", SCOPED_TRACE_EVENT_VERSION),
    ("trace.scoped-store.checkpoint", SCOPED_TRACE_CHECKPOINT_VERSION_V2),
    ("trace.scoped-store.record", SCOPED_TRACE_RECORD_VERSION_V2),
    ("trace.scoped-store", SCOPED_TRACE_STORE_VERSION_V2),
)

_OPTIONAL_PROFILE_VERSIONS = (
    ("certified-commit", CERTIFIED_COMMIT_PROFILE_VERSION),
    ("commit-integrity", COMMIT_INTEGRITY_PROFILE_VERSION),
    ("core", CORE_PROFILE_VERSION),
    ("distributed-commit", DISTRIBUTED_COMMIT_PROFILE_VERSION),
    ("hybrid-commit", HYBRID_COMMIT_PROFILE_VERSION),
    ("hybrid-swarm", HYBRID_SWARM_PROFILE_VERSION),
    ("swarm", SWARM_PROFILE_VERSION),
)

_OPTIONAL_CAPABILITY_VERSIONS = (
    (
        "governance-authority-session-v2",
        "governance-authority-session",
        GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-commit-certificate-v2",
        "governance-commit-certificate",
        GOVERNANCE_COMMIT_CERTIFICATE_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-commit-decision-v2",
        "governance-commit-decision",
        GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-commit-evidence-v2",
        "governance-commit-evidence",
        GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-commit-finality-v2",
        "governance-commit-finality",
        GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-commit-gate-v2",
        "governance-commit-gate",
        GOVERNANCE_COMMIT_GATE_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-commit-replay-v2",
        "governance-commit-replay",
        GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-distributed-commit-v2",
        "governance-distributed-commit",
        GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-hybrid-replay-v2",
        "governance-hybrid-replay",
        GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-risk-v2",
        "governance-risk",
        GOVERNANCE_RISK_CONFORMANCE_VERSION_V2,
    ),
    (
        "governance-support-v2",
        "governance-support",
        GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2,
    ),
)


def _requirement(
    component_id: str, version_id: str
) -> RuntimeCompatibilityRequirementV1:
    return RuntimeCompatibilityRequirementV1(component_id, version_id)


def _public_api_inventory_digest() -> str:
    try:
        payload = _PUBLIC_API_INVENTORY_ARTIFACT.read_bytes()
    except OSError as exc:
        raise RuntimeCompatibilityErrorV1(
            "public Python API inventory cannot be read"
        ) from exc
    if not payload:
        raise RuntimeCompatibilityErrorV1(
            "public Python API inventory must not be empty"
        )
    return "sha256:" + sha256(payload).hexdigest()


def build_runtime_compatibility_manifest_v1() -> RuntimeCompatibilityManifestV1:
    """Build the current exact WP-06 composition without runtime claims."""

    required_versions = (
        *_REQUIRED_VERSIONS,
        (
            "conformance.abi.public-python-api.digest",
            _public_api_inventory_digest(),
        ),
    )
    required = tuple(
        _requirement(component_id, version_id)
        for component_id, version_id in sorted(required_versions)
    )
    profiles = tuple(
        RuntimeCompatibilityProfileSpecV1(
            profile_id=profile_id,
            profile_version=version_id,
            requirements=(
                _requirement(f"conformance.profile.{profile_id}", version_id),
            ),
        )
        for profile_id, version_id in sorted(_OPTIONAL_PROFILE_VERSIONS)
    )
    capabilities = tuple(
        RuntimeCompatibilityCapabilitySpecV1(
            capability_id=capability_id,
            requirements=(
                _requirement(f"conformance.tck.{component_suffix}", version_id),
            ),
        )
        for capability_id, component_suffix, version_id in sorted(
            _OPTIONAL_CAPABILITY_VERSIONS
        )
    )
    return RuntimeCompatibilityManifestV1(
        required_profile=RuntimeCompatibilityProfileSpecV1(
            profile_id="scoped-baseline",
            profile_version=RUNTIME_BASELINE_PROFILE_VERSION_V1,
            requirements=required,
        ),
        optional_profiles=profiles,
        optional_capabilities=capabilities,
    )


def load_runtime_compatibility_manifest_v1(
    path: str | Path | Any | None = None,
) -> RuntimeCompatibilityManifestV1:
    """Load the packaged artifact or an explicitly supplied canonical file."""

    if path is None:
        source = RUNTIME_COMPATIBILITY_ARTIFACT_V1
    elif isinstance(path, (str, Path)):
        source = Path(path)
    else:
        source = path
    try:
        data = source.read_bytes()
    except (AttributeError, OSError) as exc:
        raise RuntimeCompatibilityErrorV1(
            "runtime compatibility artifact cannot be read"
        ) from exc
    return RuntimeCompatibilityManifestV1.from_wire(data)


def runtime_compatibility_artifact_digest_v1(
    path: str | Path | Any | None = None,
) -> str:
    """Return the digest of the exact canonical artifact bytes."""

    return load_runtime_compatibility_manifest_v1(path).artifact_digest


__all__ = [
    "RUNTIME_COMPATIBILITY_ARTIFACT_V1",
    "build_runtime_compatibility_manifest_v1",
    "load_runtime_compatibility_manifest_v1",
    "runtime_compatibility_artifact_digest_v1",
]
