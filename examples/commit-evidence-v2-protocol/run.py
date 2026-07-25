"""Provider-free executable proof of the public Commit Evidence v2 ABI."""

from __future__ import annotations

import json

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.checks.commit_evidence_v2_contract import (
    GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2,
    run_governance_commit_evidence_conformance_v2,
)


RESULT_SCHEMA = "pheroos-commit-evidence-v2-example-result-v1"


def run_example() -> dict[str, object]:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    result = run_governance_commit_evidence_conformance_v2(adapter)
    if not result.ok:
        raise RuntimeError(f"Commit Evidence v2 Conformance failed: {result.detail}")
    return {
        "schema": RESULT_SCHEMA,
        "provider_free": True,
        "network_used": False,
        "authority_source": "governance-state-store-v2",
        "conformance_version": GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2,
        "store_implementation": adapter.implementation_id,
        "result": {
            "name": result.name,
            "ok": result.ok,
            "detail": result.detail,
        },
        "proved_invariants": [
            "membership_principal_verification_replay_binding",
            "six_entry_atomic_read_set",
            "append_only_evidence_history",
            "two_principal_qualified_success",
            "single_source_insufficient",
            "opaque_source_authority",
            "canonical_input_order",
            "candidate_claim_subject_isolation",
            "lost_response_exact_retry",
            "restart_rehydration",
            "conflicting_fork_single_winner",
            "trace_derived_root_lineage",
        ],
    }


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
