from __future__ import annotations

from typing import Any


def build_evidence_adapter_descriptor() -> dict[str, Any]:
    return {
        "id": "value-investing-research.evidence_adapter",
        "accepted_sources": ["metric_registry", "data_gate", "wrds_planner", "verified_swarm_signal"],
        "proposal_sources": ["capability_agent", "critic"],
        "blocked_direct_sources": ["writer", "external_content", "third_party_untrusted"],
        "claim_requirements": {
            "formal_valuation": ["data_gate.formal_valuation_allowed", "metric_registry.valuation_metrics"],
            "report_publication": ["data_gate.report_publication_allowed", "critic.status != REJECT_FATAL"],
        },
    }
