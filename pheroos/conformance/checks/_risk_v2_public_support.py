"""Orchestrate the public-only adversarial Risk v2 Conformance matrix."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pheroos.conformance.checks._risk_v2_finality_support import (
    run_risk_v2_finality_matrix,
)
from pheroos.conformance.checks._risk_v2_integrity_support import (
    run_risk_v2_integrity_matrix,
)
from pheroos.conformance.checks._risk_v2_race_support import (
    run_risk_v2_race_matrix,
)
from pheroos.conformance.checks._risk_v2_resource_support import (
    run_risk_v2_resource_matrix,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)


def run_public_risk_v2_adversarial_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
) -> list[str]:
    """Run every Risk v2 adversarial lane with no skips or private hooks."""

    problems: list[str] = []
    for runner in (
        run_risk_v2_finality_matrix,
        run_risk_v2_integrity_matrix,
        run_risk_v2_race_matrix,
        run_risk_v2_resource_matrix,
    ):
        problems.extend(
            runner(
                adapter,
                context_factory=context_factory,
                request_factory=request_factory,
                advance_factory=advance_factory,
            )
        )
    return problems


__all__: list[str] = []
