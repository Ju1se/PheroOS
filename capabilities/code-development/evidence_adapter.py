from __future__ import annotations


def build_evidence_adapter_descriptor() -> dict:
    return {
        "adapter_id": "code-development.evidence.v1",
        "claim_types": ["patch_claim", "test_claim", "interface_claim", "security_claim", "dependency_claim"],
        "accepted_sources": ["repo_manifest", "architecture_map", "diff_summary", "test_results", "gate_results"],
        "blocking_targets": [
            "code:public_api",
            "code:forbidden_path",
            "code:test_suite",
            "code:dependency_policy",
            "code:security",
            "code:patch_acceptance",
        ],
    }
