from __future__ import annotations


def build_evidence_adapter_descriptor() -> dict:
    return {
        "adapter_id": "compliance-workflow.evidence.v1",
        "claim_types": ["policy_claim", "obligation_claim", "privacy_claim", "access_claim", "approval_claim"],
        "accepted_sources": ["policy_clause", "contract_clause", "approval_record", "redacted_document", "audit_trace"],
        "blocking_targets": [
            "compliance:pii",
            "compliance:rbac",
            "compliance:approval_required",
            "compliance:policy_gap",
            "compliance:external_action",
            "compliance:legal_advice",
            "compliance:retention",
        ],
    }
