from __future__ import annotations


def build_data_contract_descriptor() -> dict:
    return {
        "contract_id": "code-development.data.v1",
        "required_artifacts": [
            "repo_manifest",
            "architecture_map",
            "patch_plan",
            "diff_summary",
            "test_results",
            "gate_results",
            "regression_verdict",
        ],
        "forbidden_artifacts": ["raw_secret", "credential", "unapproved_external_write"],
        "required_before_coder": ["repo_manifest", "architecture_map", "patch_plan"],
        "required_before_acceptance": ["diff_summary", "test_results", "interface_gate", "security_gate"],
    }
