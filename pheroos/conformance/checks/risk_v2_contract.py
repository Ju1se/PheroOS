"""Public-only Conformance matrix for durable Risk v2 authority.

The matrix composes only public Protocol, authority-session, StateStore, and
Risk v2 ABIs.  It verifies authority, persistence, lineage, replay, fixed
cross-epoch stream identity, finality, concurrency, and resource invariants
without reproducing Risk evaluation or importing a private Governance owner.
"""

from __future__ import annotations

from pheroos.conformance.checks._risk_v2_context_support import (
    advance_v2,
    context_v2,
    request_v2,
)
from pheroos.conformance.checks._risk_v2_core_support import (
    run_risk_v2_core_matrix,
)
from pheroos.conformance.checks._risk_v2_public_support import (
    run_public_risk_v2_adversarial_matrix,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult


GOVERNANCE_RISK_CONFORMANCE_VERSION_V2 = "pheroos-governance-risk-conformance-v2"

_CHECK_NAME = "risk_v2_contract"


def run_governance_risk_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the complete active Risk v2 matrix without private test hooks."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        implementation_id = adapter.implementation_id
        if (
            type(implementation_id) is not str
            or not implementation_id
            or implementation_id != implementation_id.strip()
        ):
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}:{exc}",
        )

    problems: list[str] = []
    try:
        problems.extend(run_risk_v2_core_matrix(adapter))
        problems.extend(
            run_public_risk_v2_adversarial_matrix(
                adapter,
                context_factory=context_v2,
                request_factory=request_v2,
                advance_factory=advance_v2,
            )
        )
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


run_governance_risk_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_RISK_CONFORMANCE_VERSION_V2",
    "run_governance_risk_conformance_v2",
]
