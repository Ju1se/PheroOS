from __future__ import annotations


def build_evidence_adapter_descriptor() -> dict:
    return {
        "adapter_id": "evidence-research.evidence.v1",
        "claim_types": ["fact", "interpretation", "estimate", "recommendation"],
        "accepted_sources": ["official", "peer_reviewed", "report", "retrieved_web_source", "user_supplied_document"],
        "blocking_targets": [
            "research:fake_citation",
            "research:unsupported_claim",
            "research:contradiction",
            "research:source_quality",
            "research:evidence_gap",
        ],
    }
