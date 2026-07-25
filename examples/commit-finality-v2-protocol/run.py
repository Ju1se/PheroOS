"""Provider-free durable proof of the public Commit Finality v2 ABI."""

from __future__ import annotations

import json

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_finality_v2_contract import (
    GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2,
    run_governance_commit_finality_conformance_v2,
)


RESULT_SCHEMA = "pheroos-commit-finality-v2-example-result-v1"


def run_example() -> dict[str, object]:
    adapters = (
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        IndependentStdlibGovernanceStateStoreV2Adapter(),
    )
    results = tuple(
        run_governance_commit_finality_conformance_v2(adapter) for adapter in adapters
    )
    failed = tuple(result for result in results if not result.ok)
    if failed:
        detail = ", ".join(result.detail for result in failed)
        raise RuntimeError(f"Commit Finality v2 Conformance failed: {detail}")
    return {
        "schema": RESULT_SCHEMA,
        "provider_free": True,
        "network_used": False,
        "authority_source": "governance-state-store-v2",
        "conformance_version": GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2,
        "implementations": [adapter.implementation_id for adapter in adapters],
        "results": [
            {
                "name": result.name,
                "ok": result.ok,
                "detail": result.detail,
            }
            for result in results
        ],
        "durable_journeys": [
            "certificate_verified_to_evidence_commit",
            "certificate_conflict_to_safety_violation",
            "certificate_owner_successor_cas_retry",
            "distributed_verified_to_evidence_commit",
            "distributed_frozen_to_safety_violation",
            "distributed_owner_successor_cas_retry",
            "missing_opaque_handle_to_finality_unavailable",
        ],
        "proved_invariants": [
            "public_governance_abi_only",
            "reference_and_independent_store_parity",
            "opaque_owner_verified_finality_input",
            "portable_projection_cannot_replace_owner_handle",
            "portable_projection_root_cannot_replace_owner_handle",
            "durable_certificate_conflict_safety_terminal",
            "durable_distributed_conflict_safety_terminal",
            "atomic_owner_successor_currentness",
            "bounded_missing_handle_deadline_terminal",
        ],
        "coverage_notes": ["distributed_conflict_uses_public_freeze_only_ingress"],
    }


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
