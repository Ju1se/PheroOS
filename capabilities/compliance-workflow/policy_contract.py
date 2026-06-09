from __future__ import annotations


def build_policy_contract_descriptor() -> dict:
    return {
        "contract_id": "compliance-workflow.policy.v1",
        "policy_scope": "internal_policy | contract | regulation | mixed",
        "allowed_actions": ["summarize", "classify", "draft_internal_memo"],
        "restricted_actions": ["external_send", "database_write", "credential_export", "trade_execute"],
        "sensitive_data_classes": [
            "pii",
            "customer_data",
            "employee_data",
            "material_nonpublic_information",
            "trade_secret",
        ],
        "approval_required_for": ["external_send", "legal_advice", "trade_execute", "hr_action"],
        "retention_policy": {"trace_required": True, "default_retention_days": 365, "legal_hold_supported": True},
    }
