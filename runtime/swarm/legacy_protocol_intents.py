from __future__ import annotations

from collections.abc import Iterable
from typing import Any


LEGACY_CAPABILITY_TYPE_INTENTS = {
    "skill:value-investing-research": "investment_analysis",
    "investment.research": "investment_analysis",
    "portfolio.review": "portfolio_review",
    "evidence.research": "evidence_research",
    "public_web_research": "web_research",
    "skill:web-research": "web_research",
    "code_development": "code_development",
    "skill:code-development": "code_development",
    "compliance.workflow": "compliance_workflow",
    "skill:compliance-workflow": "compliance_workflow",
    "financial_fundamentals": "financial_data_retrieval",
}


def legacy_intents_for_capability_types(capability_types: Iterable[Any]) -> list[str]:
    normalized = {str(item) for item in capability_types if str(item).strip()}
    intents = [
        intent
        for required_type, intent in LEGACY_CAPABILITY_TYPE_INTENTS.items()
        if required_type in normalized
    ]
    return list(dict.fromkeys(intents))
