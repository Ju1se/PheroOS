"""Public-only Conformance matrix for durable Support v2 authority.

The matrix drives Principal Verification, Membership, and Support exclusively
through :mod:`pheroos.governance.support_v2`.  It uses no private reducer,
expected-value oracle, legacy Support owner, or adapter mutation hook.
"""

from __future__ import annotations

from pheroos.conformance.checks._support_v2_core_support import (
    run_support_v2_core_matrix,
)
from pheroos.conformance.checks._support_v2_finality_race_support import (
    run_support_v2_finality_race_matrix,
)
from pheroos.conformance.checks._support_v2_integrity_support import (
    run_support_v2_integrity_matrix,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult


GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2 = "pheroos-governance-support-conformance-v2"

_CHECK_NAME = "support_v2_contract"


def run_governance_support_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the complete active public Support v2 authority matrix."""

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
        problems.extend(run_support_v2_core_matrix(adapter))
        problems.extend(run_support_v2_integrity_matrix(adapter))
        problems.extend(run_support_v2_finality_race_matrix(adapter))
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


run_governance_support_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_SUPPORT_CONFORMANCE_VERSION_V2",
    "run_governance_support_conformance_v2",
]
