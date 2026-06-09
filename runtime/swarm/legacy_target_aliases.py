from __future__ import annotations


LEGACY_FORMAL_VALUATION_TARGET = "decision:formal_valuation"
LEGACY_REPORT_PUBLICATION_TARGET = "decision:report_publication"
LEGACY_DATA_SOURCE_POLICY_TARGET = "constraint:data_source_policy"
LEGACY_TOOL_WEB_SEARCH_TARGET = "tool:web_search"
LEGACY_TOOL_PROVIDER_WEB_SEARCH_TARGET = "tool:provider_web_search"
LEGACY_TOOL_FETCH_URL_TARGET = "tool:fetch_url"
LEGACY_TOOL_APPROVED_SOURCE_FETCH_TARGET = "tool:approved_source_fetch"
LEGACY_CODE_PUBLIC_API_TARGET = "constraint:code_public_api"
LEGACY_CODE_FORBIDDEN_PATH_TARGET = "constraint:code_forbidden_path"
LEGACY_CODE_TEST_GATE_TARGET = "gate:code_test_gate"
LEGACY_CODE_SECURITY_GATE_TARGET = "gate:code_security_gate"
LEGACY_CODE_DEPENDENCY_GATE_TARGET = "gate:code_dependency_gate"
LEGACY_CODE_PATCH_ACCEPTANCE_TARGET = "decision:code_patch_acceptance"
LEGACY_COMPLIANCE_PII_TARGET = "constraint:compliance_pii"
LEGACY_COMPLIANCE_RBAC_TARGET = "constraint:compliance_rbac"
LEGACY_COMPLIANCE_APPROVAL_TARGET = "decision:compliance_approval"
LEGACY_COMPLIANCE_EXTERNAL_ACTION_TARGET = "constraint:compliance_external_action"
LEGACY_COMPLIANCE_RETENTION_TARGET = "constraint:compliance_retention"
LEGACY_RESEARCH_CITATION_AUDIT_TARGET = "gate:research_citation_audit"
LEGACY_RESEARCH_EVIDENCE_GATE_TARGET = "gate:research_evidence_gate"
LEGACY_RESEARCH_CONTRADICTION_TARGET = "issue:research_contradiction"
LEGACY_RESEARCH_SOURCE_QUALITY_TARGET = "metric:research_source_quality"
LEGACY_RESEARCH_CLAIM_DECOMPOSITION_TARGET = "research:claim_decomposition"
LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET = "research:source_retrieval"

LEGACY_DECISION_TARGET_ALIASES = {
    "formal_valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "formal valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "decision_formal_valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "decision.formal_valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "decision:valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "decision:formal_valuation": LEGACY_FORMAL_VALUATION_TARGET,
    "report_publication": LEGACY_REPORT_PUBLICATION_TARGET,
    "report publication": LEGACY_REPORT_PUBLICATION_TARGET,
    "decision_report_publication": LEGACY_REPORT_PUBLICATION_TARGET,
    "decision.report_publication": LEGACY_REPORT_PUBLICATION_TARGET,
    "publication": LEGACY_REPORT_PUBLICATION_TARGET,
    "final_report": LEGACY_REPORT_PUBLICATION_TARGET,
    "final report": LEGACY_REPORT_PUBLICATION_TARGET,
    "report": LEGACY_REPORT_PUBLICATION_TARGET,
    "decision:report_publication": LEGACY_REPORT_PUBLICATION_TARGET,
}

LEGACY_SOURCE_POLICY_TARGET_ALIASES = {
    "wrds_only": LEGACY_DATA_SOURCE_POLICY_TARGET,
}

LEGACY_WEB_TOOL_TARGET_ALIASES = {
    "web_search": LEGACY_TOOL_WEB_SEARCH_TARGET,
    "provider_web_search": LEGACY_TOOL_PROVIDER_WEB_SEARCH_TARGET,
    "fetch_url": LEGACY_TOOL_FETCH_URL_TARGET,
    "approved_source_fetch": LEGACY_TOOL_APPROVED_SOURCE_FETCH_TARGET,
}

LEGACY_INVESTMENT_TARGET_ALIASES = {
    "target_price": "decision:formal_valuation",
    "target price": "decision:formal_valuation",
    "investment_recommendation": "decision:formal_valuation",
    "investment recommendation": "decision:formal_valuation",
    "recommendation": "decision:formal_valuation",
}

LEGACY_CODE_TARGET_ALIASES = {
    "code:public_api": LEGACY_CODE_PUBLIC_API_TARGET,
    "code_public_api": LEGACY_CODE_PUBLIC_API_TARGET,
    "public api": LEGACY_CODE_PUBLIC_API_TARGET,
    "public_api_changed": LEGACY_CODE_PUBLIC_API_TARGET,
    "code:forbidden_path": LEGACY_CODE_FORBIDDEN_PATH_TARGET,
    "forbidden_file": LEGACY_CODE_FORBIDDEN_PATH_TARGET,
    "forbidden path": LEGACY_CODE_FORBIDDEN_PATH_TARGET,
    "code:test_gate": LEGACY_CODE_TEST_GATE_TARGET,
    "test_gate": LEGACY_CODE_TEST_GATE_TARGET,
    "tests_failed": LEGACY_CODE_TEST_GATE_TARGET,
    "code:security": LEGACY_CODE_SECURITY_GATE_TARGET,
    "security_gate": LEGACY_CODE_SECURITY_GATE_TARGET,
    "code:dependency_policy": LEGACY_CODE_DEPENDENCY_GATE_TARGET,
    "dependency_gate": LEGACY_CODE_DEPENDENCY_GATE_TARGET,
    "code:patch_acceptance": LEGACY_CODE_PATCH_ACCEPTANCE_TARGET,
    "patch_acceptance": LEGACY_CODE_PATCH_ACCEPTANCE_TARGET,
    "accept_patch": LEGACY_CODE_PATCH_ACCEPTANCE_TARGET,
}

LEGACY_COMPLIANCE_TARGET_ALIASES = {
    "compliance:pii": LEGACY_COMPLIANCE_PII_TARGET,
    "pii": LEGACY_COMPLIANCE_PII_TARGET,
    "sensitive_spans": LEGACY_COMPLIANCE_PII_TARGET,
    "compliance:rbac": LEGACY_COMPLIANCE_RBAC_TARGET,
    "rbac": LEGACY_COMPLIANCE_RBAC_TARGET,
    "access_control": LEGACY_COMPLIANCE_RBAC_TARGET,
    "compliance:approval_required": LEGACY_COMPLIANCE_APPROVAL_TARGET,
    "approval_required": LEGACY_COMPLIANCE_APPROVAL_TARGET,
    "human_approval": LEGACY_COMPLIANCE_APPROVAL_TARGET,
    "compliance:external_action": LEGACY_COMPLIANCE_EXTERNAL_ACTION_TARGET,
    "external_action": LEGACY_COMPLIANCE_EXTERNAL_ACTION_TARGET,
    "email_send": LEGACY_COMPLIANCE_EXTERNAL_ACTION_TARGET,
    "data_export": LEGACY_COMPLIANCE_EXTERNAL_ACTION_TARGET,
    "compliance:retention": LEGACY_COMPLIANCE_RETENTION_TARGET,
    "records_retention": LEGACY_COMPLIANCE_RETENTION_TARGET,
}

LEGACY_RESEARCH_TARGET_ALIASES = {
    "research:citation_audit": LEGACY_RESEARCH_CITATION_AUDIT_TARGET,
    "citation_audit": LEGACY_RESEARCH_CITATION_AUDIT_TARGET,
    "fake_citation": LEGACY_RESEARCH_CITATION_AUDIT_TARGET,
    "research:evidence_gate": LEGACY_RESEARCH_EVIDENCE_GATE_TARGET,
    "evidence_gate": LEGACY_RESEARCH_EVIDENCE_GATE_TARGET,
    "claim_support": LEGACY_RESEARCH_EVIDENCE_GATE_TARGET,
    "research:contradiction": LEGACY_RESEARCH_CONTRADICTION_TARGET,
    "contradiction": LEGACY_RESEARCH_CONTRADICTION_TARGET,
    "contested_source": LEGACY_RESEARCH_CONTRADICTION_TARGET,
    "research:source_quality": LEGACY_RESEARCH_SOURCE_QUALITY_TARGET,
    "source_quality": LEGACY_RESEARCH_SOURCE_QUALITY_TARGET,
    "research:claim_decomposition": LEGACY_RESEARCH_CLAIM_DECOMPOSITION_TARGET,
    "claim_decomposition": LEGACY_RESEARCH_CLAIM_DECOMPOSITION_TARGET,
    "atomic_claims": LEGACY_RESEARCH_CLAIM_DECOMPOSITION_TARGET,
    "research:source_retrieval": LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET,
    "source_retrieval": LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET,
    "source_candidates": LEGACY_RESEARCH_SOURCE_RETRIEVAL_TARGET,
}


def legacy_decision_target_alias(normalized_target: str) -> str | None:
    return LEGACY_DECISION_TARGET_ALIASES.get(str(normalized_target or ""))


def legacy_canonical_target_alias(normalized_target: str) -> str | None:
    text = str(normalized_target or "")
    return (
        LEGACY_DECISION_TARGET_ALIASES.get(text)
        or LEGACY_SOURCE_POLICY_TARGET_ALIASES.get(text)
        or LEGACY_WEB_TOOL_TARGET_ALIASES.get(text)
    )


def legacy_formal_valuation_target() -> str:
    return LEGACY_FORMAL_VALUATION_TARGET


def legacy_report_publication_target() -> str:
    return LEGACY_REPORT_PUBLICATION_TARGET


def legacy_investment_decision_targets() -> tuple[str, str]:
    return (LEGACY_FORMAL_VALUATION_TARGET, LEGACY_REPORT_PUBLICATION_TARGET)


def legacy_target_aliases_by_domain() -> dict[str, dict[str, str]]:
    return {
        "investment": dict(LEGACY_INVESTMENT_TARGET_ALIASES),
        "code": dict(LEGACY_CODE_TARGET_ALIASES),
        "compliance": dict(LEGACY_COMPLIANCE_TARGET_ALIASES),
        "research": dict(LEGACY_RESEARCH_TARGET_ALIASES),
    }
