from __future__ import annotations


def build_data_contract_descriptor() -> dict:
    return {
        "contract_id": "evidence-research.data.v1",
        "required_artifacts": [
            "research_questions",
            "atomic_claims",
            "source_candidates",
            "source_quality_scores",
            "claim_evidence_graph",
            "citation_audit",
            "contradiction_map",
        ],
        "claim_support_statuses": ["supported", "partially_supported", "contradicted", "unsupported"],
        "required_before_synthesis": ["claim_evidence_graph", "citation_audit", "contradiction_map"],
    }
