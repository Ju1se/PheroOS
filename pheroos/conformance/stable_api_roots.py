"""Reviewed root decisions for the Draft Stable Python API candidate.

This is a decision source, not lifecycle metadata.  Every selected binding
remains Draft until the separately governed promotion gate changes the public
lifecycle artifact.  The closure builder follows annotations from these roots
to their canonical public owners; it never creates a second wrapper ABI.
"""

from __future__ import annotations

from types import MappingProxyType


STABLE_API_CANDIDATE_VERSION = "pheroos-stable-python-api-v1"
STABLE_API_CANDIDATE_STATUS = "promotion_candidate"
STABLE_API_CANDIDATE_STABILITY = "draft"
STABLE_API_COMPATIBILITY_MAJOR = 1

STABLE_API_ROOT_BUDGET = 80
STABLE_API_CLOSURE_BUDGET = 128
STABLE_API_GOVERNANCE_ROOT_BUDGET = 24
STABLE_API_GOVERNANCE_CLOSURE_BUDGET = 48

# The plan's hard review budget remains 80.  This lower target records the
# deliberately smaller first candidate and is asserted separately so ordinary
# evolution does not silently consume all of the reviewed headroom.
STABLE_API_CURRENT_ROOT_TARGET = 48


# These are consumer-journey entry points, not an endorsement of every Draft
# helper reachable from their implementation modules.  Constants used only as
# defaults, fingerprints, reference implementations, and narrow replay helpers
# remain outside the manually selected root set unless type closure requires a
# public record.
STABLE_API_CANDIDATE_ROOTS = MappingProxyType(
    {
        "pheroos.protocol": (
            "ProtocolSchemaVersionError",
            "capability_schema_v3",
            "protocol_schema_v3",
            "read_capability_manifest",
            "validate_capability_manifest",
        ),
        "pheroos.kernel": (
            "InputEnvelope",
            "OSKernel",
            "RuntimeMaterializer",
            "RuntimeScope",
            "os_plan_from_dict",
        ),
        "pheroos.drivers": (
            "DriverInvocationReplyV2",
            "DriverInvocationRequestV2",
            "DriverInvocationStoreV2",
            "bind",
            "expose",
            "probe",
            "register",
        ),
        "pheroos.governance": (
            "AuthorityDomainV2",
            "BaselineOutputRequestV2",
            "BaselineOutputResultV2",
            "GovernanceIssuerGrantV2",
            "GovernanceStateStoreV2",
            "IssuerGrantVerifierV2",
            "activate_governance_issuer_grant_v2",
            # Required to construct the exact signal root consumed by the
            # high-level write journey; callers must not invent that binding.
            "baseline_verified_signal_proposal_root_v2",
            "evaluate_and_commit_governed_baseline_output_v2",
            "recover_baseline_output_result_v2",
            # Portable grant lifecycle closure for the candidate's revocation
            # negative path; this returns an attempt and exposes no handle.
            "revoke_governance_issuer_grant_v2",
        ),
        "pheroos.trace": (
            "ScopedTraceEvent",
            "ScopedTraceStoreV2",
            "TraceEvent",
            "validate_event_lineage",
        ),
        "pheroos.conformance": (
            "GovernanceStateStoreConformanceAdapterV2",
            "run_conformance",
            "run_governance_baseline_output_conformance_v2",
            "run_governance_state_store_conformance_v2",
            "run_source_conformance",
        ),
    }
)


# Python has no ``raises`` annotation.  Direct public exception dependencies
# therefore need the same reviewed decision source as roots.  Built-in
# TypeError/ValueError/RuntimeError remain language contracts and are not
# duplicated as PheroOS bindings.
STABLE_API_EXCEPTION_DEPENDENCIES = MappingProxyType(
    {
        "pheroos.protocol.read_capability_manifest": (
            "pheroos.protocol.ProtocolSchemaVersionError",
        ),
        "pheroos.protocol.GovernanceAuthorityReadSetV2": (
            "pheroos.protocol.AuthorityV2ProtocolError",
        ),
        "pheroos.protocol.GovernanceReadPreconditionV2": (
            "pheroos.protocol.AuthorityV2ProtocolError",
        ),
        "pheroos.kernel.os_plan_from_dict": ("pheroos.kernel.KernelPlanVersionError",),
        "pheroos.drivers.DriverInvocationRequestV2": (
            "pheroos.drivers.DriverInvocationWireErrorV2",
        ),
        "pheroos.drivers.DriverInvocationResultV2": (
            "pheroos.drivers.DriverInvocationWireErrorV2",
        ),
        "pheroos.drivers.DriverInvocationReceiptV2": (
            "pheroos.drivers.DriverInvocationWireErrorV2",
        ),
        "pheroos.drivers.DriverInvocationReplyV2": (
            "pheroos.drivers.DriverInvocationWireErrorV2",
        ),
        "pheroos.drivers.DriverInvocationStoreV2": (
            "pheroos.drivers.DriverInvocationStoreErrorV2",
            "pheroos.drivers.DriverInvocationWireErrorV2",
        ),
        "pheroos.governance.activate_governance_issuer_grant_v2": (
            "pheroos.governance.GovernanceAuthorityBindingErrorV2",
        ),
    }
)


# These public values are referenced by selected wire/store records.  They are
# recorded and shape-frozen in the candidate artifact, but are not type roots:
# consumers obtain the canonical value from the versioned record itself and do
# not need to import a parallel constant binding.
STABLE_API_CONSTANT_DEPENDENCIES = MappingProxyType(
    {
        "pheroos.kernel.RuntimeScope": ("pheroos.kernel.RUNTIME_SCOPE_VERSION",),
        "pheroos.drivers.DriverInvocationRequestV2": (
            "pheroos.drivers.DRIVER_INVOCATION_REQUEST_VERSION_V2",
        ),
        "pheroos.drivers.DriverInvocationResultV2": (
            "pheroos.drivers.DRIVER_INVOCATION_RESULT_VERSION_V2",
        ),
        "pheroos.drivers.DriverInvocationReceiptV2": (
            "pheroos.drivers.DRIVER_INVOCATION_RECEIPT_VERSION_V2",
        ),
        "pheroos.drivers.DriverInvocationReplyV2": (
            "pheroos.drivers.DRIVER_INVOCATION_REPLY_VERSION_V2",
        ),
        "pheroos.drivers.DriverInvocationStoreV2": (
            "pheroos.drivers.DRIVER_INVOCATION_STORE_VERSION_V2",
        ),
        "pheroos.governance.GovernanceStateStoreV2": (
            "pheroos.governance.GOVERNANCE_STATE_STORE_VERSION_V2",
        ),
        "pheroos.trace.ScopedTraceEvent": ("pheroos.trace.SCOPED_TRACE_EVENT_VERSION",),
        "pheroos.trace.ScopedTraceStoreV2": (
            "pheroos.trace.SCOPED_TRACE_STORE_VERSION_V2",
        ),
    }
)


# Exact local authority handles are intentionally available in the wider Draft
# Expert API, but can never enter this promotion candidate.  Their authority is
# store-bound and non-portable; freezing them would turn an implementation
# custody mechanism into a cross-runtime Stable ABI.
STABLE_API_FORBIDDEN_BINDINGS = frozenset(
    {
        "pheroos.governance.GovernanceAuthoritySessionV2",
        "pheroos.governance.GovernanceIssuerCapabilityV2",
    }
)


# Explicit exclusions keep attractive but unsafe shortcuts out of a later
# promotion review.  This list is intentionally categorical rather than an
# exhaustive mirror of the much larger Draft Expert API.
STABLE_API_EXCLUSION_REASONS = MappingProxyType(
    {
        "compatibility_alias": "compatibility bindings are not canonical owners",
        "deprecated": "deprecated bindings cannot acquire a Stable promise",
        "fingerprint_helper": "fine-grained codec helpers remain Expert Draft",
        "legacy_authority": "legacy process-local authority cannot enter Stable",
        "opaque_local_authority": (
            "non-portable store-bound capability/session handles remain Expert Draft"
        ),
        "reference_store": "reference implementations are not required contracts",
    }
)


__all__ = [
    "STABLE_API_CANDIDATE_ROOTS",
    "STABLE_API_CANDIDATE_STABILITY",
    "STABLE_API_CANDIDATE_STATUS",
    "STABLE_API_CANDIDATE_VERSION",
    "STABLE_API_CLOSURE_BUDGET",
    "STABLE_API_COMPATIBILITY_MAJOR",
    "STABLE_API_CONSTANT_DEPENDENCIES",
    "STABLE_API_CURRENT_ROOT_TARGET",
    "STABLE_API_EXCEPTION_DEPENDENCIES",
    "STABLE_API_EXCLUSION_REASONS",
    "STABLE_API_FORBIDDEN_BINDINGS",
    "STABLE_API_GOVERNANCE_CLOSURE_BUDGET",
    "STABLE_API_GOVERNANCE_ROOT_BUDGET",
    "STABLE_API_ROOT_BUDGET",
]
