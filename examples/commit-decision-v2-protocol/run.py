"""Provider-free durable proof of the public Commit Decision v2 ABI."""

from __future__ import annotations

import json

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_decision_v2_contract import (
    GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2,
    run_governance_commit_decision_conformance_v2,
)


RESULT_SCHEMA = "pheroos-commit-decision-v2-example-result-v1"


def run_example() -> dict[str, object]:
    adapters = (
        ReferenceGovernanceStateStoreConformanceAdapterV2(),
        IndependentStdlibGovernanceStateStoreV2Adapter(),
    )
    results = tuple(
        run_governance_commit_decision_conformance_v2(adapter) for adapter in adapters
    )
    failed = tuple(result for result in results if not result.ok)
    if failed:
        detail = ", ".join(result.detail for result in failed)
        raise RuntimeError(f"Commit Decision v2 Conformance failed: {detail}")
    return {
        "schema": RESULT_SCHEMA,
        "provider_free": True,
        "network_used": False,
        "authority_source": "governance-state-store-v2",
        "conformance_version": GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2,
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
            "initialize_missing_progress_deadline_safe_fallback",
            "initialize_ready_stability_seal_evidence_commit",
            "store_restart_rehydrate_lost_response_exact_retry",
            "competing_successor_cas_retry",
        ],
        "proved_invariants": [
            "public_governance_abi_only",
            "reference_and_independent_store_parity",
            "fixed_stream_complete_replacement_state",
            "bounded_missing_input_progress",
            "typed_deliverable_deadline_outcome",
            "closed_candidate_and_evidence_assessment",
            "two_step_stability_window",
            "same_step_output_seal",
            "evidence_bound_finality",
            "atomic_trace_lineage",
            "restart_rehydration",
            "lost_response_exact_retry",
            "stale_parent_cas_retry",
        ],
    }


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
