"""Provider-free executable proof of the public Distributed Commit v2 ABI."""

from __future__ import annotations

import json

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.distributed_commit_v2_contract import (
    GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2,
    run_governance_distributed_commit_conformance_v2,
)


RESULT_SCHEMA = "pheroos-distributed-commit-v2-example-result-v1"


def run_example() -> dict[str, object]:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    result = run_governance_distributed_commit_conformance_v2(adapter)
    if not result.ok:
        raise RuntimeError(f"Distributed Commit v2 Conformance failed: {result.detail}")
    return {
        "schema": RESULT_SCHEMA,
        "provider_free": True,
        "network_used": False,
        "production_persistence": False,
        "implementation": adapter.implementation_id,
        "conformance_version": (GOVERNANCE_DISTRIBUTED_COMMIT_CONFORMANCE_VERSION_V2),
        "result": {
            "name": result.name,
            "ok": result.ok,
            "detail": result.detail,
        },
        "proved_invariants": [
            "four_fixed_state_store_streams",
            "sealed_decision_and_central_certificate_binding",
            "static_epoch_membership_binding",
            "trusted_witness_attestation",
            "quorum_certificate_verification",
            "canonical_distributed_finality_handle",
            "full_parent_dependency_grant_lifecycle_cas",
            "restart_rehydration_currentness",
            "portable_request_tamper_rejection",
            "external_byzantine_witness_freeze_only",
            "conflict_observation_restart_and_exact_retry",
            "conflict_finality_decision_safety_violation",
            "closed_conflict_trace",
        ],
    }


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
