from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import (
    CapabilityManifest,
    is_swarm_policy,
    required_swarm_trace_events,
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None or not is_swarm_policy(policy):
        return CheckResult("swarm_trace_contract", True)
    missing = sorted(
        required_swarm_trace_events(policy)
        - set(manifest.protocol.trace_policy.required_events)
    )
    return CheckResult("swarm_trace_contract", not missing, ", ".join(missing))
