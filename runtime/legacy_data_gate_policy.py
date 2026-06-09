from __future__ import annotations

import re


LEGACY_COMPLETENESS_REQUIRED_METRICS = {
    "revenue",
    "gross_margin",
    "operating_margin",
    "net_income",
    "diluted_eps",
    "operating_cash_flow",
    "capex",
    "free_cash_flow",
    "cash",
    "debt",
    "shares_outstanding",
}

LEGACY_METRIC_ALIASES = {
    "sales": "revenue",
    "sale": "revenue",
    "revt": "revenue",
    "gaap_gross_margin": "gross_margin",
    "reported_gross_margin": "gross_margin",
    "gross_margin_gaap": "gross_margin",
    "eps": "diluted_eps",
    "gaap_eps": "diluted_eps",
    "diluted_eps_gaap": "diluted_eps",
    "oancf": "operating_cash_flow",
    "operating_cashflow": "operating_cash_flow",
    "capital_expenditures": "capex",
    "ppe_capex": "capex",
    "fcf": "free_cash_flow",
    "che": "cash",
    "cash_and_equivalents": "cash",
    "total_debt": "debt",
    "csho": "shares_outstanding",
}

LEGACY_WRDS_ONLY_LIMITATION_BOX = """**数据限制：WRDS-only 模式**

本报告处于 WRDS-only 模式。所有财务指标主要来自 WRDS/Compustat 标准化数据，并经过内部公式校验，但尚未与 SEC filing、公司财报公告或管理层指引逐项核对。因此，当分析涉及非 GAAP 调整、分部收入、管理层指引或公司特定口径时，结论应视为初步判断，置信度低于 fully verified report。"""

LEGACY_WRDS_ONLY_CLAIM_GUARDRAIL_SOURCE = "legacy_wrds_only_claim_guardrail"
LEGACY_WRDS_ONLY_CLAIM_DEFECT_MEMO_POLICY_SOURCE = "legacy_wrds_only_claim_defect_memo_policy"
LEGACY_WRDS_ONLY_CONFIDENCE_GUARDRAIL_SOURCE = "legacy_wrds_only_confidence_guardrail"
LEGACY_DATA_GATE_REQUIRED_SOURCE = "legacy_data_gate_required_policy"
LEGACY_DATA_GATE_REQUIRED_MATCH_RULES = {
    "committee": "committee",
    "task_type": {"investment": "task_type:investment"},
    "required_agents": {"wrds": "required_agent:wrds"},
}
LEGACY_DATA_DEFECT_MEMO_POLICY_SOURCE = "legacy_data_defect_memo_policy"
LEGACY_DATA_READINESS_MEMO_POLICY_SOURCE = "legacy_data_readiness_memo_policy"
LEGACY_METRIC_ALIAS_SOURCE = "legacy_metric_aliases"
LEGACY_METRIC_REGISTRY_ANNOTATION_SOURCE = "legacy_metric_registry_annotation"
LEGACY_METRIC_REGISTRY_ENTRYPOINT_WARNING_SOURCE = "legacy_metric_registry_entrypoint_warning"
LEGACY_METRIC_REGISTRY_POLICY_SOURCE = "legacy_metric_registry_policy"
LEGACY_METRIC_REGISTRY_WARNING_RULE_SOURCE = "legacy_metric_registry_warning_rule"
LEGACY_PROFILE_POLICY_SOURCE = "legacy_profile_policy"
LEGACY_WRDS_ONLY_METRIC_REQUIREMENT_SOURCE = "legacy_wrds_only_metric_requirement"
LEGACY_WRDS_ONLY_OUTPUT_EFFECT_SOURCE = "legacy_wrds_only_output_effect"
LEGACY_WRDS_ONLY_REQUIRED_PERIOD_SOURCE = "legacy_wrds_only_required_period_policy"
LEGACY_WRDS_ONLY_LIMITATION_SOURCE = "legacy_wrds_only_limitations"
LEGACY_FORMAL_VALUATION_BLOCKED_OUTPUT_EFFECT = "formal_valuation_blocked"
LEGACY_SOURCE_MODE_POLICY_SOURCE = "legacy_source_mode_policy"
LEGACY_SOURCE_RULE_SOURCE = "legacy_source_rules"

LEGACY_WRDS_ONLY_CLAIM_GUARDRAIL_DEFAULT_MESSAGE = "WRDS-only mode disallows this claim."
LEGACY_WRDS_ONLY_DISALLOWED_CLAIMS = (
    {
        "code": "official_verified_claim",
        "pattern": re.compile(r"\b(sec|filing|company|official)[ -]?(verified|reported)\b|SEC[ -]?verified|公司披露|官方披露|公司公告确认", re.IGNORECASE),
        "message": "WRDS-only mode cannot claim SEC/company/official verification.",
    },
    {
        "code": "non_gaap_reconciliation_claim",
        "pattern": re.compile(r"non[- ]?gaap.*reconciliation|non[- ]?gaap EPS|非\s*GAAP.*(调整|调节|确认|EPS)", re.IGNORECASE),
        "message": "WRDS-only mode cannot use non-GAAP EPS or reconciliation unless a reliable dataset is present.",
    },
    {
        "code": "management_guidance_claim",
        "pattern": re.compile(r"management guidance|管理层指引|公司指引", re.IGNORECASE),
        "message": "WRDS-only mode cannot present management guidance as verified fact.",
    },
)


def legacy_wrds_only_claim_guardrail_default_message() -> str:
    return LEGACY_WRDS_ONLY_CLAIM_GUARDRAIL_DEFAULT_MESSAGE


LEGACY_WRDS_ONLY_REQUIRED_FIXES = (
    "Remove SEC/company/official verification claims unless verified data is explicitly provided.",
    "Keep confidence at MEDIUM or lower under WRDS-only mode.",
    "Do not use non-GAAP EPS, management guidance, or quarterly triggers unless the metric registry contains the required source/period.",
    "For acquisition-heavy companies without sourced non-GAAP EPS, publish only a GAAP-only preliminary view, not a formal valuation conclusion.",
)

LEGACY_WRDS_ONLY_CLAIM_DEFECT_MEMO_POLICY = {
    "title": "WRDS-only Claim Guardrail Report",
    "intro": "当前版本不可发布为最终投资报告。Writer / Final Judge 生成了超出 WRDS-only 数据权限的表述，系统已拦截。",
    "blocking_claim_issues_heading": "Blocking Claim Issues",
    "required_fixes_heading": "Required Fixes",
    "blocked_draft_preview_heading": "Blocked Draft Preview",
}


def legacy_wrds_only_claim_defect_memo_policy() -> dict[str, object]:
    return dict(LEGACY_WRDS_ONLY_CLAIM_DEFECT_MEMO_POLICY)


LEGACY_FORBIDDEN_CLAIM_SOURCE = "legacy_forbidden_claims"
LEGACY_FORBIDDEN_CLAIMS = (
    "SEC-verified or company-reported unless official reconciliation is explicitly provided",
    "non-GAAP EPS or reconciliation unless a reliable WRDS/IBES/company-specific dataset is present",
    "management guidance unless explicitly sourced",
)

LEGACY_GATE_METRIC_GROUP_SOURCE = "legacy_gate_metric_group"
LEGACY_GATE_SCORE_POLICY_SOURCE = "legacy_gate_score_policy"
LEGACY_NON_GAAP_METRICS = ("non_gaap_eps",)
LEGACY_ESTIMATE_METRICS = ("street_eps", "ibes_actual_eps", "ibes_mean_estimate")
LEGACY_GATE_METRIC_GROUPS = {
    "non_gaap_metrics": LEGACY_NON_GAAP_METRICS,
    "estimate_metrics": LEGACY_ESTIMATE_METRICS,
}
LEGACY_GATE_EVIDENCE_GAP_RULE_SOURCE = "legacy_gate_evidence_gap_rule"
LEGACY_GATE_EVIDENCE_GAP_RULES = {
    "forward_estimates_missing": {
        "severity": "MEDIUM",
        "code": "missing_forward_estimates",
        "message": (
            "No IBES/Street EPS estimate dataset is present. Forward P/E, PEG, price targets, "
            "and analyst-consensus claims must be labeled as unverified or omitted."
        ),
        "blocks_formal_valuation": False,
        "blocks_forward_valuation": True,
    },
}

LEGACY_WRDS_ONLY_LIMITATIONS = (
    "No SEC/company release reconciliation was performed.",
    "All financial metrics are based on WRDS/Compustat only.",
    "Non-GAAP data is unavailable unless separately sourced from a reliable dataset.",
    "Company-specific segment disclosures, management guidance, and customer details are not verified in WRDS-only mode.",
)

LEGACY_DATA_DEFECT_MEMO_POLICY = {
    "title": "Data Defect Report",
    "intro": "当前版本不可发布为投资结论。Data Gate 没有通过，所以系统已停止 Research / Quant / Committee 后续推理。",
    "blocking_issues_heading": "Blocking Issues",
    "warnings_heading": "Warnings",
    "no_blocking_issue_text": "No blocking issue details were recorded.",
    "no_warning_text": "No non-blocking warnings were recorded.",
    "required_fixes_heading": "Required Fixes Before Committee",
    "required_fixes": {
        "WRDS_ONLY": [
            "Fix WRDS internal consistency defects in company identity, period matching, formula validation, and metric basis.",
            "Lock the report `as_of_date` and keep annual, quarterly, and valuation dates explicit.",
            "Rebuild the WRDS metric registry and only then allow Research, Quant, and Committee agents to reason.",
        ],
        "DEFAULT": [
            "Reconcile WRDS metrics against company/SEC reported metrics for revenue, gross margin, EPS, OCF, CapEx, FCF, cash, debt, and shares.",
            "Lock the report `as_of_date` and remove sources after that date in historical mode.",
            "Re-run deterministic metric calculation and only then allow Research, Quant, and Committee agents to reason.",
        ],
    },
    "registry_warning_fix": "Use `reported_gross_margin_candidate`, not raw Compustat `gp/sale`, when D&A materially changes gross margin.",
}


def legacy_data_defect_memo_policy() -> dict[str, object]:
    policy = dict(LEGACY_DATA_DEFECT_MEMO_POLICY)
    fixes = policy.get("required_fixes")
    if isinstance(fixes, dict):
        policy["required_fixes"] = {
            str(mode): list(items) if isinstance(items, list) else []
            for mode, items in fixes.items()
        }
    return policy


LEGACY_DATA_READINESS_MEMO_POLICY = {
    "title": "Data Readiness Defect Report",
    "intro": (
        "Data retrieval and governed analysis have run, but Data Gate still has blockers that prevent publication. "
        "The system will return a readiness memo instead of a final report."
    ),
    "publication_blockers_heading": "Publication Blockers",
    "no_blocker_text": "No explicit blocker details were recorded, but publication was not allowed.",
    "warnings_heading": "Important Warnings",
    "required_next_steps_heading": "Required Next Steps",
    "required_next_steps": [
        "Resolve publication blockers before allowing Writer to produce the final output.",
        "Keep unresolved claims and unsupported conclusions out of the final output.",
        "Re-run the governed workflow after required evidence or source coverage improves.",
    ],
}


def legacy_data_readiness_memo_policy() -> dict[str, object]:
    policy = dict(LEGACY_DATA_READINESS_MEMO_POLICY)
    policy["required_next_steps"] = list(LEGACY_DATA_READINESS_MEMO_POLICY["required_next_steps"])
    return policy


LEGACY_CONFIDENCE_DOWNGRADE_RULES = (
    "critical accounting basis ambiguity",
    "missing required financial fields",
    "annual/quarterly period mismatch",
)

LEGACY_SOURCE_RULES = {
    "filings": "only filings released before as_of_date",
    "market_data": "must include price date",
    "estimates": "must be labeled as estimates and snapshot-dated",
    "news": "must be published before as_of_date",
}

LEGACY_SOURCE_VALIDATION_RULES = {
    "financial_period_after_as_of": {
        "severity": "CRITICAL",
        "code": "future_financial_period",
        "message": "Financial statement period is after the report as-of date.",
    },
    "missing_official_reconciliation": {
        "severity": "MEDIUM",
        "code": "missing_official_reconciliation",
        "message": "No company/SEC reported metric set was provided for deterministic WRDS-vs-filing reconciliation.",
    },
    "wrds_only_unverified": {
        "severity": "MEDIUM",
        "code": "wrds_only_unverified",
        "message": "WRDS/Compustat internal checks passed or failed without SEC/company-release reconciliation.",
    },
    "official_metric_mismatch": {
        "severity": "CRITICAL",
        "code": "official_metric_mismatch",
        "message": "WRDS/metric-registry value conflicts with company/SEC reported metric.",
    },
    "ambiguous_company_identity": {
        "severity": "CRITICAL",
        "code": "ambiguous_company_identity",
        "message": "WRDS company resolver returned multiple top-scoring GVKEY candidates.",
    },
}


def legacy_source_validation_rule(name: str) -> dict[str, object]:
    rule = LEGACY_SOURCE_VALIDATION_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}

LEGACY_SOURCE_MODE_POLICIES = {
    "WRDS_ONLY": {
        "verification_level": "internal_consistency_only",
        "allowed_sources": ["WRDS"],
    },
    "DEFAULT": {
        "verification_level": "official_reconciliation_possible",
        "allowed_sources": ["WRDS", "SEC", "company_release"],
    },
}


def legacy_source_mode_policy(mode: str) -> dict[str, object]:
    mode_text = str(mode or "").strip().upper()
    policy = LEGACY_SOURCE_MODE_POLICIES.get(mode_text) or LEGACY_SOURCE_MODE_POLICIES["DEFAULT"]
    return dict(policy)


LEGACY_METRIC_REGISTRY_ENTRYPOINT_WARNING = {
    "severity": "MEDIUM",
    "code": "metric_registry_entrypoint_invalid",
    "message": "Capability metric-registry entrypoint failed; deterministic runtime fallback was used.",
}


def legacy_metric_registry_entrypoint_warning() -> dict[str, object]:
    return dict(LEGACY_METRIC_REGISTRY_ENTRYPOINT_WARNING)


LEGACY_DATA_GATE_REQUIRED_DATA_RULES = {
    "company_financials": {
        "severity": "CRITICAL",
        "code": "missing_wrds_financials",
        "message": "The active data contract requires company financial statements before governed analysis.",
    },
}


def legacy_data_gate_required_data_rule(name: str) -> dict[str, object]:
    rule = LEGACY_DATA_GATE_REQUIRED_DATA_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


def legacy_data_gate_required_matches(orchestration: dict[str, object], *, task_type: str = "") -> list[str]:
    required = orchestration.get("required_agents") if isinstance(orchestration.get("required_agents"), dict) else {}
    matches: list[str] = []
    committee_match = LEGACY_DATA_GATE_REQUIRED_MATCH_RULES["committee"]
    if orchestration.get("committee") and isinstance(committee_match, str):
        matches.append(committee_match)
    task_type_matches = LEGACY_DATA_GATE_REQUIRED_MATCH_RULES["task_type"]
    if isinstance(task_type_matches, dict):
        match = task_type_matches.get(str(task_type or "").lower())
        if isinstance(match, str):
            matches.append(match)
    required_agent_matches = LEGACY_DATA_GATE_REQUIRED_MATCH_RULES["required_agents"]
    if isinstance(required_agent_matches, dict):
        for agent, match in required_agent_matches.items():
            if required.get(agent) and isinstance(match, str):
                matches.append(match)
    return matches


LEGACY_METRIC_REGISTRY_WARNING_RULES = {
    "large_margin_gap": {
        "severity": "HIGH",
        "annual_issue": (
            "Compustat gross margin before depreciation materially exceeds the filing-like "
            "after-depreciation candidate."
        ),
        "quarterly_issue": (
            "Quarterly Compustat gross margin before depreciation materially exceeds the filing-like "
            "after-depreciation candidate."
        ),
        "annual_instruction": "Do not cite raw Compustat gp/sale as GAAP reported gross margin without reconciliation.",
        "quarterly_instruction": "Do not cite raw Compustat gpq/saleq as GAAP reported gross margin without reconciliation.",
    },
}


def legacy_metric_registry_warning_rule(name: str) -> dict[str, object]:
    rule = LEGACY_METRIC_REGISTRY_WARNING_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_METRIC_REGISTRY_ANNOTATIONS = {
    "reported_gross_margin_candidate": {
        "formula": "WRDS-derived filing-like gross margin candidate; not SEC/company verified in WRDS-only mode",
    },
    "gross_margin": {
        "formula_by_frequency": {
            "annual": (
                "reported_gross_margin_candidate; uses (gross_profit_compustat - dp) / revenue "
                "when D&A materially changes Compustat gross profit"
            ),
            "quarterly": (
                "reported_gross_margin_candidate; uses (gross_profit_compustat - dpq) / revenue "
                "when D&A materially changes Compustat gross profit"
            ),
        },
    },
}


def legacy_metric_registry_annotation(name: str) -> dict[str, object]:
    annotation = LEGACY_METRIC_REGISTRY_ANNOTATIONS.get(name)
    if not isinstance(annotation, dict):
        return {}
    copied = dict(annotation)
    by_frequency = copied.get("formula_by_frequency")
    if isinstance(by_frequency, dict):
        copied["formula_by_frequency"] = dict(by_frequency)
    return copied


LEGACY_WRDS_ONLY_CONFIDENCE_GUARDRAIL_RULE = {
    "severity": "CRITICAL",
    "code": "wrds_only_confidence_too_high",
    "message": "WRDS-only mode cannot publish high-confidence conclusions.",
}


def legacy_wrds_only_confidence_guardrail_rule() -> dict[str, object]:
    return dict(LEGACY_WRDS_ONLY_CONFIDENCE_GUARDRAIL_RULE)


def legacy_formal_valuation_blocked_output_effect() -> str:
    return LEGACY_FORMAL_VALUATION_BLOCKED_OUTPUT_EFFECT


LEGACY_WRDS_ONLY_OUTPUT_EFFECTS = {
    "blocking_errors": {
        "next_action": "stop_and_return_data_defect_report",
    },
    "publication_blocked": {
        "formal_valuation_allowed": False,
        "valuation_scope": "DATA_READINESS_BLOCKED_PRELIMINARY",
        "next_action": "continue_to_committee_but_block_publication",
    },
    LEGACY_FORMAL_VALUATION_BLOCKED_OUTPUT_EFFECT: {
        "valuation_scope": "GAAP_ONLY_PRELIMINARY",
        "next_action": "continue_with_gaap_only_preliminary",
        "validation_issue": {
            "severity": "CRITICAL",
            "code": "formal_valuation_without_non_gaap",
            "message": (
                "Acquisition-heavy company without sourced non-GAAP EPS cannot publish a formal "
                "valuation conclusion; output must remain a GAAP-only preliminary view."
            ),
        },
    },
    "passed": {
        "valuation_scope": "WRDS_ONLY_PRELIMINARY",
        "next_action": "continue_to_research_quant_committee",
    },
}


def legacy_wrds_only_output_effect(name: str) -> dict[str, object]:
    effect = LEGACY_WRDS_ONLY_OUTPUT_EFFECTS.get(name)
    return dict(effect) if isinstance(effect, dict) else {}


def legacy_forbidden_claims() -> list[str]:
    return list(LEGACY_FORBIDDEN_CLAIMS)


def legacy_gate_metric_group(name: str) -> list[str]:
    return list(LEGACY_GATE_METRIC_GROUPS.get(name, ()))


LEGACY_WRDS_ONLY_METRIC_REQUIREMENT_RULES = {
    "non_gaap_metrics": {
        "severity": "CRITICAL",
        "code": "non_gaap_without_source",
        "message": "Non-GAAP EPS cannot be used in WRDS-only mode without a reliable non-GAAP dataset.",
    },
}


def legacy_wrds_only_metric_requirement_rule(name: str) -> dict[str, object]:
    rule = LEGACY_WRDS_ONLY_METRIC_REQUIREMENT_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_WRDS_ONLY_REQUIRED_PERIOD_RULES = {
    "quarterly_trigger": {
        "severity": "CRITICAL",
        "code": "quarterly_trigger_without_quarterly_metric",
        "message": "The report references a quarterly trigger, but the WRDS metric registry has no matching quarterly metrics.",
    },
}


def legacy_wrds_only_required_period_rule(name: str) -> dict[str, object]:
    rule = LEGACY_WRDS_ONLY_REQUIRED_PERIOD_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_FORMULA_VALIDATION_RULE_SOURCE = "legacy_formula_validation_rule"
LEGACY_FORMULA_VALIDATION_RULES = {
    "non_positive_revenue": {
        "severity": "CRITICAL",
        "code": "non_positive_revenue",
        "message": "Revenue must be positive for financial analysis.",
    },
    "fcf_formula_mismatch": {
        "severity": "CRITICAL",
        "code": "fcf_formula_mismatch",
        "message": "Calculated free cash flow does not equal operating cash flow minus capex.",
    },
}


def legacy_formula_validation_rule(name: str) -> dict[str, object]:
    rule = LEGACY_FORMULA_VALIDATION_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_MARGIN_BASIS_RULE_SOURCE = "legacy_margin_basis_rule"
LEGACY_MARGIN_BASIS_RULES = {
    "reported_margin_uses_before_depreciation": {
        "severity": "CRITICAL",
        "code": "reported_margin_uses_before_depreciation",
        "message": (
            "High-depreciation semiconductor analysis cannot use before-depreciation "
            "Compustat gp/sale as the reported gross margin candidate."
        ),
    },
    "high_depreciation_margin_basis": {
        "severity": "HIGH",
        "code": "high_depreciation_margin_basis",
        "message": "High depreciation intensity detected; reports must disclose gross-margin basis explicitly.",
    },
}


def legacy_margin_basis_rule(name: str) -> dict[str, object]:
    rule = LEGACY_MARGIN_BASIS_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_COMPUSTAT_STANDARD_FILTER_RULE_SOURCE = "legacy_compustat_standard_filter_rule"
LEGACY_COMPUSTAT_STANDARD_FILTER_RULE = {
    "allowed_values": {
        "indfmt": ("INDL", None, ""),
        "datafmt": ("STD", "HIST_STD", None, ""),
        "consol": ("C", None, ""),
        "popsrc": ("D", None, ""),
        "curcd": ("USD", None, ""),
        "curcdq": ("USD", None, ""),
    },
    "validation_issue": {
        "severity": "MEDIUM",
        "code": "non_standard_compustat_record",
        "message": "Compustat row uses a non-standard filter value; metrics may not be comparable.",
    },
}


def legacy_compustat_standard_filter_rule() -> dict[str, object]:
    allowed = LEGACY_COMPUSTAT_STANDARD_FILTER_RULE["allowed_values"]
    issue = LEGACY_COMPUSTAT_STANDARD_FILTER_RULE["validation_issue"]
    return {
        "allowed_values": {str(field): list(values) for field, values in allowed.items()},
        "validation_issue": dict(issue),
    }


LEGACY_BALANCE_SHEET_JUMP_RULE_SOURCE = "legacy_balance_sheet_jump_rule"
LEGACY_BALANCE_SHEET_JUMP_RULE = {
    "asset_threshold": 0.05,
    "growth_threshold": 0.50,
    "validation_issue": {
        "severity": "CRITICAL",
        "code_template": "material_{label}_jump_unexplained",
        "message_template": (
            "Material {label} jump detected in {frequency} WRDS data. "
            "WRDS-only mode cannot explain whether this is an acquisition, reclassification, or data artifact; "
            "publication is blocked until reconciled."
        ),
        "blocks_report_publication": True,
        "blocks_formal_valuation": True,
    },
}


def legacy_balance_sheet_jump_rule() -> dict[str, object]:
    issue = LEGACY_BALANCE_SHEET_JUMP_RULE["validation_issue"]
    return {
        "asset_threshold": LEGACY_BALANCE_SHEET_JUMP_RULE["asset_threshold"],
        "growth_threshold": LEGACY_BALANCE_SHEET_JUMP_RULE["growth_threshold"],
        "validation_issue": dict(issue),
}


LEGACY_GATE_SCORE_POLICIES = {
    "data_quality": {
        "critical_error_penalty": 30,
        "high_warning_penalty": 12,
        "high_warning_cap": 4,
        "medium_warning_penalty": 6,
        "medium_warning_cap": 6,
        "low_warning_penalty": 2,
        "low_warning_cap": 8,
        "unknown_warning_penalty": 3,
        "unknown_warning_cap": 6,
    },
    "data_completeness": {
        "annual_series_bonus": 4,
        "quarterly_series_bonus": 4,
        "ttm_series_bonus": 2,
    },
    "decision_readiness": {
        "critical_error_penalty": 35,
        "decision_blocker_penalty": 25,
        "high_evidence_gap_penalty": 10,
        "medium_evidence_gap_penalty": 6,
        "medium_warning_penalty": 3,
    },
}


def legacy_gate_score_policy(name: str) -> dict[str, object]:
    policy = LEGACY_GATE_SCORE_POLICIES.get(name)
    return dict(policy) if isinstance(policy, dict) else {}


def legacy_gate_evidence_gap_rule(name: str) -> dict[str, object]:
    rule = LEGACY_GATE_EVIDENCE_GAP_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_METRIC_REGISTRY_USAGE_RULES = (
    "Agents must use derived_metrics from this registry, not raw WRDS fields, when reasoning or writing.",
    "Agents must cite TTM valuation multiples only from registry TTM metrics, never from mental math.",
    "Agents must cite multi-year annual capex/revenue history only from annual_metric_series.",
    "Quarterly YTD cash-flow metrics must not be annualized; use operating_cash_flow_quarter, capex_quarter, free_cash_flow_quarter, or TTM cash-flow metrics from the registry.",
    "Working-capital claims must use days_inventory_outstanding, days_sales_outstanding, days_payables_outstanding, and cash_conversion_cycle from the registry.",
    "Raw Compustat gp/sale must not be described as reported/company GAAP gross margin in WRDS-only mode.",
    "Use gross_margin_before_depreciation, gross_margin_after_depreciation_candidate, and reported_gross_margin_candidate with explicit basis.",
    "Estimates and actuals must remain separate.",
    "Non-GAAP EPS is unavailable unless a reliable separate dataset is explicitly present.",
    "Peer valuation claims must use peer_* metrics from deterministic peer_comparison rows, not model memory.",
)
LEGACY_METRIC_REGISTRY_SOURCE_PRIORITY = ("wrds_compustat",)

LEGACY_ACQUISITION_HINT_TICKERS = {"AVGO", "BR", "ORCL", "CSCO"}
LEGACY_ACQUISITION_HINT_NAME_MARKERS = ("broadcom", "vmware")
LEGACY_ACQUISITION_INTENSIVE_REQUIREMENTS = ("ibes_estimates_or_street_eps",)
LEGACY_ACQUISITION_VALUATION_POLICY = "Formal valuation should use sourced non-GAAP or Street EPS; otherwise downgrade to GAAP-only preliminary."
LEGACY_PROFILE_POLICY_DEFAULTS = {
    "acquisition_intensive": {
        "severity": "HIGH",
        "reason": (
            "Company appears acquisition/intangible intensive based on goodwill/intangible asset ratios "
            "or known acquisition-heavy identity markers."
        ),
        "identity_tickers": sorted(LEGACY_ACQUISITION_HINT_TICKERS),
        "identity_name_markers": list(LEGACY_ACQUISITION_HINT_NAME_MARKERS),
        "goodwill_to_assets_threshold": 0.15,
        "intangibles_to_assets_threshold": 0.15,
        "combined_intangible_assets_threshold": 0.25,
        "required_evidence": list(LEGACY_ACQUISITION_INTENSIVE_REQUIREMENTS),
        "valuation_policy": LEGACY_ACQUISITION_VALUATION_POLICY,
    },
    "financial_company": {
        "severity": "HIGH",
        "reason": "Company appears to be a financial institution based on SIC/NAICS.",
        "required_evidence": ["financial_company_specific_package"],
        "policy": "Do not use industrial EV/EBITDA or FCF valuation framing as a formal conclusion.",
    },
    "negative_or_nonmeaningful_earnings": {
        "severity": "MEDIUM",
        "reason": "Latest GAAP EPS or net income is non-positive, making P/E conclusions non-meaningful.",
        "required_evidence": ["alternative_valuation_anchor"],
        "policy": "Avoid formal P/E-based cheap/expensive conclusions; use EV/revenue, book value, or normalized earnings if appropriate.",
    },
    "segment_data_requested_not_integrated": {
        "severity": "MEDIUM",
        "reason": "Planner requested segment data, but no segment metrics are present in the metric registry.",
        "required_evidence": ["compustat_segments"],
        "policy": "Do not make strong segment-mix or segment-margin claims.",
        "evidence_gap": {
            "code": "missing_segment_data",
            "message": "Segment data was requested but is not present in the metric registry.",
            "blocks_formal_valuation": False,
        },
    },
    "crsp_market_data_requested_not_integrated": {
        "severity": "MEDIUM",
        "reason": "Planner requested CRSP data, but market metrics are still using Compustat price fields.",
        "required_evidence": ["crsp_market_data"],
        "policy": "Market setup and valuation-date conclusions should stay preliminary until CRSP is integrated.",
        "evidence_gap": {
            "code": "missing_crsp_market_data",
            "message": "CRSP market data was requested but is not present in the metric registry.",
            "blocks_formal_valuation": False,
        },
    },
    "peer_comparison_requested_not_integrated": {
        "severity": "MEDIUM",
        "reason": "Planner requested peer comparison data, but no peer metrics are present in the metric registry.",
        "required_evidence": ["peer_comparison"],
        "policy": "Do not make formal relative-valuation or peer multiple claims.",
        "evidence_gap": {
            "code": "missing_peer_comparison",
            "message": "Peer comparison data was requested but is not present in the metric registry.",
            "blocks_formal_valuation": False,
            "blocks_peer_valuation": True,
        },
    },
}


def legacy_profile_policy(profile: str) -> dict[str, object]:
    policy = LEGACY_PROFILE_POLICY_DEFAULTS.get(profile)
    return dict(policy) if isinstance(policy, dict) else {}


LEGACY_PROFILE_EVIDENCE_RULE_SOURCE = "legacy_profile_evidence_rule"
LEGACY_PROFILE_EVIDENCE_RULES = {
    "acquisition_intensive": {
        "severity": "HIGH",
        "missing_evidence_code": "missing_non_gaap_eps_for_acquisition_heavy_company",
        "message": (
            "Acquisition/intangible-intensive company lacks sourced non-GAAP or Street EPS evidence; "
            "formal valuation conclusions are blocked and only a GAAP-only preliminary view is allowed."
        ),
        "blocks_formal_valuation": True,
        "valuation_scope_when_blocked": "GAAP_ONLY_PRELIMINARY",
    },
}


def legacy_profile_evidence_rule(profile: str) -> dict[str, object]:
    rule = LEGACY_PROFILE_EVIDENCE_RULES.get(profile)
    return dict(rule) if isinstance(rule, dict) else {}


LEGACY_PROFILE_WARNING_RULE_SOURCE = "legacy_profile_warning_rule"
LEGACY_PROFILE_WARNING_RULES = {
    "acquisition_intensive_missing_non_gaap": {
        "severity": "HIGH",
        "code": "missing_non_gaap_eps_for_acquisition_heavy_company",
        "message": (
            "Acquisition-heavy company lacks a sourced non-GAAP EPS dataset; "
            "formal valuation conclusions are blocked and only a GAAP-only preliminary view is allowed."
        ),
        "blocks_formal_valuation": True,
    },
}


def legacy_profile_warning_rule(name: str) -> dict[str, object]:
    rule = LEGACY_PROFILE_WARNING_RULES.get(name)
    return dict(rule) if isinstance(rule, dict) else {}


def legacy_balance_sheet_jump_rule_source() -> str:
    return LEGACY_BALANCE_SHEET_JUMP_RULE_SOURCE


def legacy_compustat_standard_filter_rule_source() -> str:
    return LEGACY_COMPUSTAT_STANDARD_FILTER_RULE_SOURCE


def legacy_completeness_required_metrics() -> set[str]:
    return set(LEGACY_COMPLETENESS_REQUIRED_METRICS)


def legacy_confidence_downgrade_rules() -> list[str]:
    return list(LEGACY_CONFIDENCE_DOWNGRADE_RULES)


def legacy_data_defect_memo_policy_source() -> str:
    return LEGACY_DATA_DEFECT_MEMO_POLICY_SOURCE


def legacy_data_gate_required_policy_source() -> str:
    return LEGACY_DATA_GATE_REQUIRED_SOURCE


def legacy_data_readiness_memo_policy_source() -> str:
    return LEGACY_DATA_READINESS_MEMO_POLICY_SOURCE


def legacy_forbidden_claim_source() -> str:
    return LEGACY_FORBIDDEN_CLAIM_SOURCE


def legacy_formula_validation_rule_source() -> str:
    return LEGACY_FORMULA_VALIDATION_RULE_SOURCE


def legacy_gate_evidence_gap_rule_source() -> str:
    return LEGACY_GATE_EVIDENCE_GAP_RULE_SOURCE


def legacy_gate_metric_group_source() -> str:
    return LEGACY_GATE_METRIC_GROUP_SOURCE


def legacy_gate_score_policy_source() -> str:
    return LEGACY_GATE_SCORE_POLICY_SOURCE


def legacy_margin_basis_rule_source() -> str:
    return LEGACY_MARGIN_BASIS_RULE_SOURCE


def legacy_metric_alias_source() -> str:
    return LEGACY_METRIC_ALIAS_SOURCE


def legacy_metric_aliases() -> dict[str, str]:
    return dict(LEGACY_METRIC_ALIASES)


def legacy_metric_registry_annotation_source() -> str:
    return LEGACY_METRIC_REGISTRY_ANNOTATION_SOURCE


def legacy_metric_registry_entrypoint_warning_source() -> str:
    return LEGACY_METRIC_REGISTRY_ENTRYPOINT_WARNING_SOURCE


def legacy_metric_registry_policy_source() -> str:
    return LEGACY_METRIC_REGISTRY_POLICY_SOURCE


def legacy_metric_registry_source_priority() -> list[str]:
    return list(LEGACY_METRIC_REGISTRY_SOURCE_PRIORITY)


def legacy_metric_registry_usage_rules() -> list[str]:
    return list(LEGACY_METRIC_REGISTRY_USAGE_RULES)


def legacy_metric_registry_warning_rule_source() -> str:
    return LEGACY_METRIC_REGISTRY_WARNING_RULE_SOURCE


def legacy_profile_evidence_rule_source() -> str:
    return LEGACY_PROFILE_EVIDENCE_RULE_SOURCE


def legacy_profile_policy_source() -> str:
    return LEGACY_PROFILE_POLICY_SOURCE


def legacy_profile_warning_rule_source() -> str:
    return LEGACY_PROFILE_WARNING_RULE_SOURCE


def legacy_source_mode_policy_source() -> str:
    return LEGACY_SOURCE_MODE_POLICY_SOURCE


def legacy_source_rules() -> dict[str, object]:
    return dict(LEGACY_SOURCE_RULES)


def legacy_source_rule_source() -> str:
    return LEGACY_SOURCE_RULE_SOURCE


def legacy_wrds_only_claim_defect_memo_policy_source() -> str:
    return LEGACY_WRDS_ONLY_CLAIM_DEFECT_MEMO_POLICY_SOURCE


def legacy_wrds_only_claim_guardrail_source() -> str:
    return LEGACY_WRDS_ONLY_CLAIM_GUARDRAIL_SOURCE


def legacy_wrds_only_confidence_guardrail_source() -> str:
    return LEGACY_WRDS_ONLY_CONFIDENCE_GUARDRAIL_SOURCE


def legacy_wrds_only_disallowed_claims() -> tuple[dict[str, object], ...]:
    return tuple(LEGACY_WRDS_ONLY_DISALLOWED_CLAIMS)


def legacy_wrds_only_limitation_box() -> str:
    return LEGACY_WRDS_ONLY_LIMITATION_BOX


def legacy_wrds_only_limitation_source() -> str:
    return LEGACY_WRDS_ONLY_LIMITATION_SOURCE


def legacy_wrds_only_limitations() -> list[str]:
    return list(LEGACY_WRDS_ONLY_LIMITATIONS)


def legacy_wrds_only_metric_requirement_source() -> str:
    return LEGACY_WRDS_ONLY_METRIC_REQUIREMENT_SOURCE


def legacy_wrds_only_output_effect_source() -> str:
    return LEGACY_WRDS_ONLY_OUTPUT_EFFECT_SOURCE


def legacy_wrds_only_required_fixes() -> list[str]:
    return list(LEGACY_WRDS_ONLY_REQUIRED_FIXES)


def legacy_wrds_only_required_period_source() -> str:
    return LEGACY_WRDS_ONLY_REQUIRED_PERIOD_SOURCE


HIGH_CONFIDENCE_RE = re.compile(r"\bhigh confidence\b|confidence\s*[:：]\s*high|置信度\s*[:：]?\s*高|高置信度", re.IGNORECASE)
QUARTER_TRIGGER_RE = re.compile(r"\bQ([1-4])\s*FY\s*(20\d{2})\b|FY\s*(20\d{2})\s*Q([1-4])", re.IGNORECASE)
NON_GAAP_RE = re.compile(r"non[- ]?gaap EPS|非\s*GAAP.*EPS", re.IGNORECASE)
FORMAL_VALUATION_CONCLUSION_RE = re.compile(
    r"\b(final\s+decision|decision|rating)\s*[:：]\s*(buy|sell|watch|avoid|hold)\b|"
    r"\b(buy|sell|watch|avoid|hold)\s+(recommendation|rating)\b|"
    r"\b(undervalued|overvalued|fairly\s+valued)\b|"
    r"(正式)?(投资|估值)?结论\s*[:：]?\s*(买入|卖出|观察|回避|持有)|"
    r"(低估|高估|估值合理)",
    re.IGNORECASE,
)
