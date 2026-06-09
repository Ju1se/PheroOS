from __future__ import annotations

from runtime.swarm.goal_targets import GoalTarget
from runtime.swarm.legacy_target_aliases import (
    LEGACY_CODE_DEPENDENCY_GATE_TARGET,
    LEGACY_CODE_PATCH_ACCEPTANCE_TARGET,
    LEGACY_CODE_SECURITY_GATE_TARGET,
    LEGACY_CODE_TEST_GATE_TARGET,
    LEGACY_COMPLIANCE_APPROVAL_TARGET,
    LEGACY_COMPLIANCE_PII_TARGET,
    LEGACY_COMPLIANCE_RBAC_TARGET,
    LEGACY_RESEARCH_CITATION_AUDIT_TARGET,
    LEGACY_RESEARCH_CLAIM_DECOMPOSITION_TARGET,
    LEGACY_RESEARCH_CONTRADICTION_TARGET,
    LEGACY_RESEARCH_EVIDENCE_GATE_TARGET,
    LEGACY_RESEARCH_SOURCE_QUALITY_TARGET,
    LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET,
    legacy_formal_valuation_target,
)


LEGACY_DEFAULT_TARGETS_BY_INTENT: dict[str, tuple[GoalTarget, ...]] = {
    "evidence_research": (
        GoalTarget(LEGACY_RESEARCH_CLAIM_DECOMPOSITION_TARGET, 0.82, ("claim", "atomic", "scope"), "Split the research task into checkable claims."),
        GoalTarget(LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET, 0.78, ("source", "retrieval", "coverage"), "Retrieve candidate sources."),
        GoalTarget(LEGACY_RESEARCH_SOURCE_QUALITY_TARGET, 0.78, ("source_quality", "provenance", "authority"), "Rate source quality and provenance."),
        GoalTarget(LEGACY_RESEARCH_EVIDENCE_GATE_TARGET, 0.86, ("evidence", "support", "claim_evidence_graph"), "Gate synthesis on evidence support."),
        GoalTarget(LEGACY_RESEARCH_CITATION_AUDIT_TARGET, 0.72, ("citation", "unsupported", "quote"), "Block unsupported citation use."),
        GoalTarget(LEGACY_RESEARCH_CONTRADICTION_TARGET, 0.68, ("contradiction", "counterevidence", "uncertainty"), "Surface contradictory evidence."),
    ),
    "web_research": (
        GoalTarget(LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET, 0.82, ("source", "retrieval", "coverage", "web"), "Retrieve public web source candidates."),
        GoalTarget(LEGACY_RESEARCH_SOURCE_QUALITY_TARGET, 0.74, ("source_quality", "provenance", "authority"), "Rate source quality."),
        GoalTarget(LEGACY_RESEARCH_EVIDENCE_GATE_TARGET, 0.68, ("evidence", "support"), "Keep findings evidence-linked."),
    ),
    "investment_analysis": (
        GoalTarget(legacy_formal_valuation_target(), 0.92, ("valuation", "financial", "quant", "data", "risk"), "Decide whether formal valuation is allowed."),
    ),
    "portfolio_review": (
        GoalTarget(legacy_formal_valuation_target(), 0.68, ("portfolio", "allocation", "risk", "position"), "Constrain portfolio decisions by evidence and risk."),
    ),
    "code_development": (
        GoalTarget(LEGACY_CODE_TEST_GATE_TARGET, 0.9, ("test", "pytest", "regression"), "Tests must pass before patch acceptance."),
        GoalTarget(LEGACY_CODE_SECURITY_GATE_TARGET, 0.82, ("security", "secret", "risk"), "Scan for security and secret risks."),
        GoalTarget(LEGACY_CODE_DEPENDENCY_GATE_TARGET, 0.72, ("dependency", "interface", "compatibility"), "Check dependencies and interfaces."),
        GoalTarget(LEGACY_CODE_PATCH_ACCEPTANCE_TARGET, 0.88, ("patch", "accept", "regression"), "Commit or reject patch candidate."),
    ),
    "compliance_workflow": (
        GoalTarget("compliance:policy_interpretation", 0.78, ("policy", "scope", "obligation", "control"), "Interpret policy scope and concrete obligations."),
        GoalTarget(LEGACY_COMPLIANCE_PII_TARGET, 0.86, ("pii", "privacy", "dlp", "sensitive"), "Audit PII and sensitive data exposure."),
        GoalTarget(LEGACY_COMPLIANCE_RBAC_TARGET, 0.76, ("rbac", "access", "permission"), "Evaluate access-control constraints."),
        GoalTarget(LEGACY_COMPLIANCE_APPROVAL_TARGET, 0.82, ("approval", "human", "external_action"), "Route required approvals."),
    ),
}


def legacy_default_targets_for_intent(intent: str) -> tuple[GoalTarget, ...]:
    return LEGACY_DEFAULT_TARGETS_BY_INTENT.get(str(intent or ""), ())
