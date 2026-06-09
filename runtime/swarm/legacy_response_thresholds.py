from __future__ import annotations

from typing import Any


def legacy_role_demand_from_thresholds(
    thresholds: dict[str, Any],
    context: dict[str, float],
) -> tuple[str, float, str] | None:
    if "data_audit" in thresholds:
        return (
            "data_audit",
            context["evidence_gap_strength"],
            "data gaps or source coverage require audit",
        )
    if "risk_review" in thresholds:
        return (
            "risk_review",
            context["risk_strength"],
            "unresolved risk or stop-signals require review",
        )
    if "adversarial_review" in thresholds:
        return (
            "adversarial_review",
            context["risk_strength"],
            "committee needs a bear-case challenge",
        )
    if "valuation_review" in thresholds:
        return (
            "valuation_review",
            context["conclusion_demand"],
            "conclusion demand depends on declared output permission readiness",
        )
    if "business_quality" in thresholds:
        return ("business_quality", 0.65, "protocol role requires business-quality judgment")
    if "industry_structure" in thresholds:
        return ("industry_structure", 0.6, "protocol role requires industry structure review")
    if "final_decision" in thresholds:
        return ("final_decision", 0.75, "committee chair is needed to resolve candidates")
    if "market_setup" in thresholds:
        return ("market_setup", 0.45, "entry timing is secondary unless market data is available")
    return None


def legacy_role_demand_from_terms(
    terms: set[str],
    context: dict[str, float],
) -> tuple[str, float, str] | None:
    if ("data" in terms and ("audit" in terms or "auditor" in terms)) or "gatekeeper" in terms:
        return (
            "data_audit",
            context["evidence_gap_strength"],
            "data gaps or source coverage require audit",
        )
    if "risk" in terms or "veto" in terms:
        return (
            "risk_review",
            context["risk_strength"],
            "unresolved risk or stop-signals require review",
        )
    if "red_team" in terms or "red-team" in terms or "skeptic" in terms:
        return (
            "adversarial_review",
            context["risk_strength"],
            "committee needs a bear-case challenge",
        )
    if "valuation" in terms or "quant" in terms or "metrics" in terms:
        return (
            "valuation_review",
            context["conclusion_demand"],
            "conclusion demand depends on declared output permission readiness",
        )
    if "business_quality" in terms or "fundamental" in terms or "moat" in terms:
        return ("business_quality", 0.65, "protocol role requires business-quality judgment")
    if "industry" in terms or "competition" in terms or "strategy" in terms:
        return ("industry_structure", 0.6, "protocol role requires industry structure review")
    if "chair" in terms or "cio" in terms or "decision" in terms:
        return ("final_decision", 0.75, "committee chair is needed to resolve candidates")
    if "market" in terms or "execution" in terms or "timing" in terms:
        return ("market_setup", 0.45, "entry timing is secondary unless market data is available")
    return None


def legacy_mandatory_committee_from_terms(terms: set[str]) -> bool:
    return "chair" in terms or "cio" in terms
