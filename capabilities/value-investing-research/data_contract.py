from __future__ import annotations

from typing import Any


def build_data_contract_descriptor() -> dict[str, Any]:
    return {
        "id": "value-investing-research.data_contract",
        "source_mode": "WRDS_ONLY",
        "source_mode_policies": {
            "WRDS_ONLY": {
                "verification_level": "internal_consistency_only",
                "allowed_sources": ["WRDS"],
            },
            "DEFAULT": {
                "verification_level": "official_reconciliation_possible",
                "allowed_sources": ["WRDS", "SEC", "company_release"],
            },
        },
        "source_rules": {
            "filings": "only filings released before as_of_date",
            "market_data": "must include price date",
            "estimates": "must be labeled as estimates and snapshot-dated",
            "news": "must be published before as_of_date",
        },
        "source_validation_rules": {
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
        },
        "required_packages": [
            "company_identity",
            "annual_financials_10y",
            "quarterly_financials_16q",
            "valuation_snapshot",
            "cash_flow_and_capex",
            "balance_sheet_and_debt",
            "profitability_and_margin",
        ],
        "forbidden_claims": [
            "SEC/company verified unless reconciled",
            "non-GAAP EPS as valuation anchor without explicit dataset",
            "formal valuation when Data Gate blocks decision:formal_valuation",
        ],
        "claim_guardrails": {
            "wrds_only_defect_memo": {
                "title": "WRDS-only Claim Guardrail Report",
                "intro": (
                    "当前版本不可发布为最终投资报告。Writer / Final Judge "
                    "生成了超出 WRDS-only 数据权限的表述，系统已拦截。"
                ),
                "blocking_claim_issues_heading": "Blocking Claim Issues",
                "required_fixes_heading": "Required Fixes",
                "blocked_draft_preview_heading": "Blocked Draft Preview",
            },
            "wrds_only_required_fixes": [
                "Remove SEC/company/official verification claims unless verified data is explicitly provided.",
                "Keep confidence at MEDIUM or lower under WRDS-only mode.",
                "Do not use non-GAAP EPS, management guidance, or quarterly triggers unless the metric registry contains the required source/period.",
                "For acquisition-heavy companies without sourced non-GAAP EPS, publish only a GAAP-only preliminary view, not a formal valuation conclusion.",
            ],
            "wrds_only_disallowed_claims": [
                {
                    "code": "official_verified_claim",
                    "patterns": [
                        r"\b(sec|filing|company|official)[ -]?(verified|reported)\b",
                        r"SEC[ -]?verified",
                        r"公司披露",
                        r"官方披露",
                        r"公司公告确认",
                    ],
                    "message": "WRDS-only mode cannot claim SEC/company/official verification.",
                    "severity": "CRITICAL",
                },
                {
                    "code": "non_gaap_reconciliation_claim",
                    "patterns": [
                        r"non[- ]?gaap.*reconciliation",
                        r"non[- ]?gaap EPS",
                        r"非\s*GAAP.*(调整|调节|确认|EPS)",
                    ],
                    "message": "WRDS-only mode cannot use non-GAAP EPS or reconciliation unless a reliable dataset is present.",
                    "severity": "CRITICAL",
                },
                {
                    "code": "management_guidance_claim",
                    "patterns": [r"management guidance", r"管理层指引", r"公司指引"],
                    "message": "WRDS-only mode cannot present management guidance as verified fact.",
                    "severity": "CRITICAL",
                },
            ],
        },
        "confidence_ceiling": "medium",
        "confidence_policy": {
            "maximum_confidence": "medium",
            "downgrade_to_low_when": [
                "critical accounting basis ambiguity",
                "missing required financial fields",
                "annual/quarterly period mismatch",
            ],
            "validation_issue": {
                "severity": "CRITICAL",
                "code": "wrds_only_confidence_too_high",
                "message": "WRDS-only mode cannot publish high-confidence conclusions.",
            },
        },
        "completeness_required_metrics": [
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
        ],
        "metric_aliases": {
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
        },
        "metric_registry_policy": {
            "source_priority": ["wrds_compustat"],
            "warning_rules": {
                "large_margin_gap": {
                    "severity": "HIGH",
                    "annual_issue": (
                        "Compustat gross margin before depreciation materially exceeds the filing-like "
                        "after-depreciation candidate."
                    ),
                    "quarterly_issue": (
                        "Quarterly Compustat gross margin before depreciation materially exceeds the "
                        "filing-like after-depreciation candidate."
                    ),
                    "annual_instruction": (
                        "Do not cite raw Compustat gp/sale as GAAP reported gross margin without reconciliation."
                    ),
                    "quarterly_instruction": (
                        "Do not cite raw Compustat gpq/saleq as GAAP reported gross margin without reconciliation."
                    ),
                },
            },
            "metric_annotations": {
                "reported_gross_margin_candidate": {
                    "formula": (
                        "WRDS-derived filing-like gross margin candidate; not SEC/company verified in WRDS-only mode"
                    ),
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
            },
            "usage_rules": [
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
            ],
        },
        "source_mode_limitations": {
            "WRDS_ONLY": {
                "box": (
                    "**数据限制：WRDS-only 模式**\n\n"
                    "本报告处于 WRDS-only 模式。所有财务指标主要来自 WRDS/Compustat 标准化数据，并经过内部公式校验，"
                    "但尚未与 SEC filing、公司财报公告或管理层指引逐项核对。因此，当分析涉及非 GAAP 调整、"
                    "分部收入、管理层指引或公司特定口径时，结论应视为初步判断，置信度低于 fully verified report。"
                ),
                "items": [
                    "No SEC/company release reconciliation was performed.",
                    "All financial metrics are based on WRDS/Compustat only.",
                    "Non-GAAP data is unavailable unless separately sourced from a reliable dataset.",
                    "Company-specific segment disclosures, management guidance, and customer details are not verified in WRDS-only mode.",
                ],
            }
        },
        "gate_policy": {
            "required_when": {
                "committee": True,
                "task_types": ["investment"],
                "required_agents": ["wrds"],
            },
            "required_data_rules": {
                "company_financials": {
                    "severity": "CRITICAL",
                    "code": "missing_wrds_financials",
                    "message": "The active data contract requires company financial statements before governed analysis.",
                },
            },
            "estimate_metrics": ["street_eps", "ibes_actual_eps", "ibes_mean_estimate"],
            "non_gaap_metrics": ["non_gaap_eps"],
            "metric_requirement_rules": {
                "non_gaap_metrics": {
                    "severity": "CRITICAL",
                    "code": "non_gaap_without_source",
                    "message": "Non-GAAP EPS cannot be used in WRDS-only mode without a reliable non-GAAP dataset.",
                },
            },
            "required_period_rules": {
                "quarterly_trigger": {
                    "severity": "CRITICAL",
                    "code": "quarterly_trigger_without_quarterly_metric",
                    "message": "The report references a quarterly trigger, but the WRDS metric registry has no matching quarterly metrics.",
                },
            },
            "formula_validation_rules": {
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
            },
            "margin_basis_rules": {
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
            },
            "compustat_standard_filter_rules": {
                "allowed_values": {
                    "indfmt": ["INDL", None, ""],
                    "datafmt": ["STD", "HIST_STD", None, ""],
                    "consol": ["C", None, ""],
                    "popsrc": ["D", None, ""],
                    "curcd": ["USD", None, ""],
                    "curcdq": ["USD", None, ""],
                },
                "validation_issue": {
                    "severity": "MEDIUM",
                    "code": "non_standard_compustat_record",
                    "message": "Compustat row uses a non-standard filter value; metrics may not be comparable.",
                },
            },
            "balance_sheet_jump_rules": {
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
            },
            "profile_evidence_rules": {
                "acquisition_intensive": {
                    "severity": "HIGH",
                    "satisfying_metrics": ["non_gaap_eps", "street_eps", "ibes_actual_eps", "ibes_mean_estimate"],
                    "missing_evidence_code": "missing_non_gaap_eps_for_acquisition_heavy_company",
                    "message": (
                        "Acquisition/intangible-intensive company lacks sourced non-GAAP or Street EPS evidence; "
                        "formal valuation conclusions are blocked and only a GAAP-only preliminary view is allowed."
                    ),
                    "blocks_formal_valuation": True,
                    "valuation_scope_when_blocked": "GAAP_ONLY_PRELIMINARY",
                }
            },
            "profile_warning_rules": {
                "acquisition_intensive_missing_non_gaap": {
                    "severity": "HIGH",
                    "code": "missing_non_gaap_eps_for_acquisition_heavy_company",
                    "message": (
                        "Acquisition-heavy company lacks a sourced non-GAAP EPS dataset; "
                        "formal valuation conclusions are blocked and only a GAAP-only preliminary view is allowed."
                    ),
                    "blocks_formal_valuation": True,
                }
            },
            "evidence_gap_rules": {
                "forward_estimates_missing": {
                    "severity": "MEDIUM",
                    "code": "missing_forward_estimates",
                    "message": (
                        "No IBES/Street EPS estimate dataset is present. Forward P/E, PEG, price targets, "
                        "and analyst-consensus claims must be labeled as unverified or omitted."
                    ),
                    "blocks_formal_valuation": False,
                    "blocks_forward_valuation": True,
                }
            },
            "score_policy": {
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
            },
            "output_effects": {
                "blocking_errors": {
                    "next_action": "stop_and_return_data_defect_report",
                },
                "publication_blocked": {
                    "formal_valuation_allowed": False,
                    "valuation_scope": "DATA_READINESS_BLOCKED_PRELIMINARY",
                    "next_action": "continue_to_committee_but_block_publication",
                },
                "formal_valuation_blocked": {
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
            },
            "defect_memo": {
                "title": "Data Defect Report",
                "intro": (
                    "当前版本不可发布为投资结论。Data Gate 没有通过，所以系统已停止 Research / Quant / Committee 后续推理。"
                ),
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
                "registry_warning_fix": (
                    "Use `reported_gross_margin_candidate`, not raw Compustat `gp/sale`, when D&A materially changes gross margin."
                ),
            },
            "readiness_memo": {
                "title": "Data Readiness Defect Report",
                "intro": (
                    "Data retrieval and governed analysis have run, but Data Gate still has blockers that prevent "
                    "publication. The system will return a readiness memo instead of a final report."
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
            },
        },
        "profile_policies": {
                "acquisition_intensive": {
                    "severity": "HIGH",
                    "reason": (
                        "Company appears acquisition/intangible intensive based on goodwill/intangible asset ratios "
                        "or known acquisition-heavy identity markers."
                    ),
                    "identity_tickers": ["AVGO", "BR", "ORCL", "CSCO"],
                    "identity_name_markers": ["broadcom", "vmware"],
                    "goodwill_to_assets_threshold": 0.15,
                    "intangibles_to_assets_threshold": 0.15,
                    "combined_intangible_assets_threshold": 0.25,
                    "required_evidence": ["ibes_estimates_or_street_eps"],
                    "valuation_policy": (
                        "Formal valuation should use sourced non-GAAP or Street EPS; "
                        "otherwise downgrade to GAAP-only preliminary."
                    ),
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
                    "policy": (
                        "Avoid formal P/E-based cheap/expensive conclusions; use EV/revenue, book value, "
                        "or normalized earnings if appropriate."
                    ),
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
            },
    }
