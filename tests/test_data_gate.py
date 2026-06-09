from __future__ import annotations

from runtime.data_gate import (
    apply_wrds_only_report_policy,
    build_data_contract,
    build_investment_data_controls,
    data_gate_failed,
    data_gate_publication_blocked,
    render_data_defect_memo,
    render_data_readiness_memo,
    validate_wrds_only_report_claims,
)
from runtime.capability_registry import CapabilityRegistry
from runtime.capability_runtime import load_capability_descriptor


def wrds_state(
    row: dict,
    *,
    metadata: dict | None = None,
    quarterly_rows: list[dict] | None = None,
    task: str = "MU",
    company: dict | None = None,
    extra_financials: dict | None = None,
    orchestration: dict | None = None,
) -> dict:
    company_payload = company or {
        "gvkey": "007343",
        "tic": "MU",
        "conm": "MICRON TECHNOLOGY INC",
        "cik": "0000723125",
    }
    company_financials = {
        "status": "matched_with_financials",
        "table": "comp.funda",
        "company": company_payload,
        "rows": [row],
        "quarterly_rows": quarterly_rows or [],
        "quarterly_table": "comp.fundq" if quarterly_rows else None,
    }
    if extra_financials:
        company_financials.update(extra_financials)
    return {
        "task": task,
        "route": "investment",
        "metadata": metadata or {},
        "orchestration": orchestration
        or {"task_type": "investment", "committee": True, "required_agents": {"wrds": True}},
        "wrds_result": {
            "ok": True,
            "data": {
                "company_financials": company_financials
            },
        },
    }


def test_data_contract_uses_capability_workflow_descriptor() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = {
        "task": "Analyze MU",
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    }

    contract = build_data_contract(state)

    assert contract["contract_source"] == "capability_workflow_descriptor"
    assert contract["descriptor_id"] == "value-investing-research.data_contract"
    assert contract["source_mode"] == "WRDS_ONLY"
    assert contract["source_mode_policy_source"] == "data_contract_source_mode_policy"
    assert contract["verification_level"] == "internal_consistency_only"
    assert contract["allowed_sources"] == ["WRDS"]
    assert contract["source_rules_source"] == "data_contract_source_rules"
    assert contract["source_rules"]["filings"] == "only filings released before as_of_date"
    assert contract["source_validation_rules_source"] == "data_contract_source_rules"
    assert contract["source_validation_rules"]["wrds_only_unverified"]["code"] == "wrds_only_unverified"
    assert contract["source_validation_rules"]["official_metric_mismatch"]["code"] == "official_metric_mismatch"
    assert contract["source_validation_rules"]["ambiguous_company_identity"]["code"] == "ambiguous_company_identity"
    assert contract["confidence_policy"]["maximum_confidence"] == "MEDIUM"
    assert contract["confidence_policy"]["source"] == "data_contract_confidence_policy"
    assert "annual/quarterly period mismatch" in contract["confidence_policy"]["downgrade_to_low_when"]
    assert "annual_financials_10y" in contract["required_contract_packages"]
    assert "revenue" in contract["completeness_required_metrics"]
    assert contract["metric_aliases_source"] == "data_contract_metric_aliases"
    assert contract["metric_aliases"]["sales"] == "revenue"
    assert contract["metric_registry_policy_source"] == "data_contract_metric_registry_policy"
    assert contract["metric_registry_policy"]["source_priority"] == ["wrds_compustat"]
    assert contract["metric_registry_policy"]["warning_rules"]["large_margin_gap"]["severity"] == "HIGH"
    assert (
        contract["metric_registry_policy"]["metric_annotations"]["gross_margin"]["formula_by_frequency"]["annual"]
        .startswith("reported_gross_margin_candidate; uses")
    )
    assert contract["metric_registry_policy"]["usage_rules"][0].startswith("Agents must use derived_metrics")
    assert contract["source_mode_limitations_source"] == "data_contract_source_mode_limitations"
    assert contract["source_mode_limitations"]["WRDS_ONLY"]["items"][0] == "No SEC/company release reconciliation was performed."
    assert contract["disallowed_claims"][0] == "SEC/company verified unless reconciled"
    assert contract["disallowed_claims_source"] == "data_contract_forbidden_claims"
    assert contract["claim_guardrails"]["wrds_only_required_fixes"][0].startswith("Remove SEC/company")
    assert contract["claim_guardrails"]["wrds_only_defect_memo"]["title"] == "WRDS-only Claim Guardrail Report"
    assert contract["claim_guardrails"]["wrds_only_disallowed_claims"][0]["code"] == "official_verified_claim"
    assert contract["gate_policy"]["required_when"]["task_types"] == ["investment"]
    assert contract["gate_policy"]["required_when"]["required_agents"] == ["wrds"]
    assert contract["gate_policy"]["estimate_metrics"] == ["street_eps", "ibes_actual_eps", "ibes_mean_estimate"]
    assert contract["gate_policy"]["formula_validation_rules"]["fcf_formula_mismatch"]["code"] == "fcf_formula_mismatch"
    assert contract["gate_policy"]["margin_basis_rules"]["reported_margin_uses_before_depreciation"]["code"] == (
        "reported_margin_uses_before_depreciation"
    )
    assert contract["gate_policy"]["compustat_standard_filter_rules"]["validation_issue"]["code"] == (
        "non_standard_compustat_record"
    )
    assert contract["gate_policy"]["balance_sheet_jump_rules"]["validation_issue"]["code_template"] == (
        "material_{label}_jump_unexplained"
    )
    assert contract["gate_policy"]["output_effects"]["publication_blocked"]["valuation_scope"] == "DATA_READINESS_BLOCKED_PRELIMINARY"
    assert contract["gate_policy"]["readiness_memo"]["title"] == "Data Readiness Defect Report"
    assert contract["gate_policy"]["evidence_gap_rules"]["forward_estimates_missing"]["code"] == "missing_forward_estimates"
    assert contract["gate_policy"]["profile_evidence_rules"]["acquisition_intensive"]["severity"] == "HIGH"
    assert contract["profile_policies"]["financial_company"]["required_evidence"] == ["financial_company_specific_package"]
    assert contract["profile_policies"]["financial_company"]["severity"] == "HIGH"
    assert contract["profile_policies"]["acquisition_intensive"]["reason"].startswith("Company appears acquisition")
    assert contract["profile_policies"]["negative_or_nonmeaningful_earnings"]["required_evidence"] == [
        "alternative_valuation_anchor"
    ]
    assert contract["profile_policies"]["peer_comparison_requested_not_integrated"]["evidence_gap"]["code"] == (
        "missing_peer_comparison"
    )


def test_data_contract_source_rules_can_come_from_custom_descriptor() -> None:
    state = {
        "task": "Analyze XYZ",
        "metadata": {
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "source_rules": {
                    "filings": "custom filings rule",
                    "market_data": "custom market data rule",
                    "empty": "",
                },
            }
        },
    }

    contract = build_data_contract(state)

    assert contract["source_rules_source"] == "data_contract_source_rules"
    assert contract["source_rules"] == {
        "filings": "custom filings rule",
        "market_data": "custom market data rule",
    }


def test_data_contract_forbidden_claims_legacy_fallback_when_descriptor_omits_policy() -> None:
    state = {
        "task": "Analyze XYZ",
        "metadata": {
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    }

    contract = build_data_contract(state)

    assert contract["disallowed_claims_source"] == "legacy_forbidden_claims"
    assert contract["disallowed_claims"] == [
        "SEC-verified or company-reported unless official reconciliation is explicitly provided",
        "non-GAAP EPS or reconciliation unless a reliable WRDS/IBES/company-specific dataset is present",
        "management guidance unless explicitly sourced",
    ]


def test_data_gate_metric_groups_legacy_fallback_when_descriptor_omits_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)
    errors = validate_wrds_only_report_claims("Non-GAAP EPS is the primary valuation anchor.", {**state, **controls})

    assert controls["data_gate"]["non_gaap_metric_group_source"] == "legacy_gate_metric_group"
    assert controls["data_gate"]["estimate_metric_group_source"] == "legacy_gate_metric_group"
    forward_gap = next(gap for gap in controls["data_gate"]["evidence_gaps"] if gap["code"] == "missing_forward_estimates")
    assert forward_gap["policy_source"] == "legacy_gate_evidence_gap_rule"
    issue = next(issue for issue in errors if issue["code"] == "non_gaap_without_source")
    assert issue["source"] == "legacy_wrds_only_metric_requirement"
    assert issue["message"] == "Non-GAAP EPS cannot be used in WRDS-only mode without a reliable non-GAAP dataset."
    assert issue["required_metrics"] == ["non_gaap_eps"]


def test_data_contract_source_mode_policy_can_come_from_custom_descriptor() -> None:
    state = {
        "task": "Analyze XYZ",
        "metadata": {
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "CUSTOM_MODE",
                "source_mode_policies": {
                    "CUSTOM_MODE": {
                        "verification_level": "custom_verification",
                        "allowed_sources": ["custom_source"],
                    }
                },
            }
        },
    }

    contract = build_data_contract(state)

    assert contract["source_mode_policy_source"] == "data_contract_source_mode_policy"
    assert contract["verification_level"] == "custom_verification"
    assert contract["allowed_sources"] == ["custom_source"]


def test_data_contract_source_mode_policy_legacy_fallback_when_descriptor_omits_policy() -> None:
    state = {
        "task": "Analyze XYZ",
        "metadata": {
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "FULLY_VERIFIED",
            }
        },
    }

    contract = build_data_contract(state)

    assert contract["source_mode_policy_source"] == "legacy_source_mode_policy"
    assert contract["verification_level"] == "official_reconciliation_possible"
    assert contract["allowed_sources"] == ["WRDS", "SEC", "company_release"]


def test_data_gate_required_policy_can_come_from_custom_data_contract() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        orchestration={"task_type": "general_chat", "committee": False, "required_agents": {"custom_gate": True}},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "gate_policy": {
                    "required_when": {
                        "required_agents": ["custom_gate"],
                    }
                },
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_gate"]["data_gate_required"] is True
    assert controls["data_gate"]["data_gate_required_source"] == "data_contract_gate_required_policy"
    assert controls["data_gate"]["data_gate_required_matches"] == ["required_agent:custom_gate"]


def test_data_gate_required_policy_legacy_fallback_when_descriptor_omits_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_gate"]["data_gate_required"] is True
    assert controls["data_gate"]["data_gate_required_source"] == "legacy_data_gate_required_policy"
    assert "task_type:investment" in controls["data_gate"]["data_gate_required_matches"]
    assert "required_agent:wrds" in controls["data_gate"]["data_gate_required_matches"]


def test_missing_required_financials_uses_data_contract_required_data_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = {
        "task": "Analyze MU",
        "route": "investment",
        "orchestration": {"task_type": "investment", "committee": True, "required_agents": {"wrds": True}},
        "metadata": {
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
        "wrds_result": {"ok": True, "data": {"company_financials": {"rows": [], "quarterly_rows": []}}},
    }

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "missing_wrds_financials")

    assert issue["policy_source"] == "data_contract_gate_required_policy"
    assert issue["message"] == "The active data contract requires company financial statements before governed analysis."


def test_missing_required_financials_uses_legacy_required_data_rule_when_descriptor_omits_rule() -> None:
    state = {
        "task": "Analyze XYZ",
        "route": "general_chat",
        "orchestration": {"task_type": "general_chat", "committee": False, "required_agents": {"custom_gate": True}},
        "metadata": {
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
                "gate_policy": {"required_when": {"required_agents": ["custom_gate"]}},
            }
        },
        "wrds_result": {"ok": True, "data": {"company_financials": {"rows": [], "quarterly_rows": []}}},
    }

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "missing_wrds_financials")

    assert controls["data_gate"]["data_gate_required_source"] == "data_contract_gate_required_policy"
    assert issue["policy_source"] == "legacy_data_gate_required_policy"
    assert issue["message"] == "The active data contract requires company financial statements before governed analysis."


def test_data_contract_source_rules_legacy_fallback_when_descriptor_omits_rules() -> None:
    state = {
        "task": "Analyze XYZ",
        "metadata": {
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    }

    contract = build_data_contract(state)

    assert contract["source_rules_source"] == "legacy_source_rules"
    assert contract["source_rules"]["filings"] == "only filings released before as_of_date"
    assert contract["source_validation_rules_source"] == "legacy_source_rules"
    assert contract["source_validation_rules"] == {}


def test_source_reconciliation_warnings_use_data_contract_validation_rules() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "source_mode": "DEFAULT",
            "require_official_reconciliation": True,
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    warning = next(
        warning
        for warning in controls["data_gate"]["warnings"]
        if warning["code"] == "missing_official_reconciliation"
    )

    assert warning["policy_source"] == "data_contract_source_rules"
    assert warning["message"] == "No company/SEC reported metric set was provided for deterministic WRDS-vs-filing reconciliation."


def test_wrds_only_unverified_warning_uses_data_contract_validation_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    warning = next(warning for warning in controls["data_gate"]["warnings"] if warning["code"] == "wrds_only_unverified")

    assert warning["policy_source"] == "data_contract_source_rules"
    assert warning["message"] == "WRDS/Compustat internal checks passed or failed without SEC/company-release reconciliation."


def test_source_reconciliation_warnings_use_legacy_rule_when_descriptor_omits_rule() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)
    warning = next(warning for warning in controls["data_gate"]["warnings"] if warning["code"] == "wrds_only_unverified")

    assert warning["policy_source"] == "legacy_source_rules"
    assert warning["message"] == "WRDS/Compustat internal checks passed or failed without SEC/company-release reconciliation."


def test_metric_registry_uses_capability_workflow_entrypoint() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "oancf": 550,
            "capx": 80,
            "calculated": {"free_cash_flow": 470, "gross_margin": 0.45},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )

    controls = build_investment_data_controls(state)
    trace = controls["metric_registry"]["metric_registry_entrypoint_trace"]

    assert trace[0]["source"] == "capability_metric_registry_entrypoint"
    assert trace[0]["entrypoint"] == "workflow.py:build_metric_registry_adapter"
    assert controls["metric_registry"]["metrics"]


def test_metric_registry_invalid_entrypoint_warning_uses_legacy_policy() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = dict(load_capability_descriptor(manifest)["entrypoints"]["workflow"])
    workflow["metric_registry_entrypoint"] = "workflow.py:missing_metric_registry_adapter"
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "oancf": 550,
            "capx": 80,
            "calculated": {"free_cash_flow": 470, "gross_margin": 0.45},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )

    controls = build_investment_data_controls(state)
    warning = next(
        warning
        for warning in controls["metric_registry"]["warnings"]
        if warning["code"] == "metric_registry_entrypoint_invalid"
    )
    trace = controls["metric_registry"]["metric_registry_entrypoint_trace"]

    assert warning["policy_source"] == "legacy_metric_registry_entrypoint_warning"
    assert warning["message"].startswith("Capability metric-registry entrypoint failed")
    assert trace[0]["status"] == "fallback_runtime"
    assert trace[0]["source"] == "runtime_metric_registry_default"


def test_metric_registry_usage_rules_use_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "metric_registry_policy": {
                    "source_priority": ["custom_source"],
                    "usage_rules": ["Use only the custom descriptor metric registry."]
                },
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_contract"]["metric_registry_policy_source"] == "data_contract_metric_registry_policy"
    assert controls["metric_registry"]["source_priority_source"] == "data_contract_metric_registry_policy"
    assert controls["metric_registry"]["source_priority"][:2] == ["custom_source", "wrds_compustat"]
    assert controls["metric_registry"]["usage_rules_source"] == "data_contract_metric_registry_policy"
    assert controls["metric_registry"]["usage_rules"] == ["Use only the custom descriptor metric registry."]


def test_metric_registry_usage_rules_legacy_fallback_when_descriptor_omits_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_contract"]["metric_registry_policy_source"] == "legacy_metric_registry_policy"
    assert controls["metric_registry"]["source_priority_source"] == "legacy_metric_registry_policy"
    assert controls["metric_registry"]["source_priority"][0] == "wrds_compustat"
    assert controls["metric_registry"]["usage_rules_source"] == "legacy_metric_registry_policy"
    assert controls["metric_registry"]["usage_rules"][0].startswith("Agents must use derived_metrics")


def test_metric_registry_metric_annotations_use_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "gp": 3000,
            "dp": 250,
            "calculated": {
                "gross_profit": 3000,
                "gross_margin": 0.6,
                "reported_gross_margin_candidate": 0.55,
            },
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "metric_registry_policy": {
                    "metric_annotations": {
                        "reported_gross_margin_candidate": {"formula": "custom descriptor reported margin basis"},
                        "gross_margin": {
                            "formula_by_frequency": {
                                "annual": "custom descriptor annual gross margin basis",
                            }
                        },
                    }
                },
            }
        },
    )

    controls = build_investment_data_controls(state)
    metrics = controls["metric_registry"]["metrics"]
    reported = next(metric for metric in metrics if metric["metric"] == "reported_gross_margin_candidate")
    gross_margin = next(metric for metric in metrics if metric["metric"] == "gross_margin")

    assert reported["formula"] == "custom descriptor reported margin basis"
    assert reported["formula_policy_source"] == "data_contract_metric_registry_policy"
    assert gross_margin["formula"] == "custom descriptor annual gross margin basis"
    assert gross_margin["formula_policy_source"] == "data_contract_metric_registry_policy"


def test_metric_registry_metric_annotations_legacy_fallback_when_descriptor_omits_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "gp": 3000,
            "dp": 250,
            "calculated": {
                "gross_profit": 3000,
                "gross_margin": 0.6,
                "reported_gross_margin_candidate": 0.55,
            },
        },
        quarterly_rows=[
            {
                "datadate": "2025-12-31",
                "fyearq": 2025,
                "fqtr": 4,
                "saleq": 1300,
                "gpq": 780,
                "dpq": 60,
                "calculated": {
                    "gross_profit": 780,
                    "gross_margin": 0.6,
                    "reported_gross_margin_candidate": 0.5538,
                },
            }
        ],
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)
    metrics = controls["metric_registry"]["metrics"]
    reported = next(metric for metric in metrics if metric["metric"] == "reported_gross_margin_candidate")
    annual_margin = next(
        metric for metric in metrics if metric["metric"] == "gross_margin" and metric["period"] == "FY2025"
    )
    quarterly_margin = next(
        metric for metric in metrics if metric["metric"] == "gross_margin" and metric["period"] == "FY2025Q4"
    )

    assert reported["formula"].startswith("WRDS-derived filing-like gross margin candidate")
    assert reported["formula_policy_source"] == "legacy_metric_registry_annotation"
    assert "(gross_profit_compustat - dp) / revenue" in annual_margin["formula"]
    assert annual_margin["formula_policy_source"] == "legacy_metric_registry_annotation"
    assert "(gross_profit_compustat - dpq) / revenue" in quarterly_margin["formula"]
    assert quarterly_margin["formula_policy_source"] == "legacy_metric_registry_annotation"


def test_data_gate_blocks_future_period_in_historical_mode() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={"mode": "historical", "as_of_date": "2025-03-20"},
    )

    controls = build_investment_data_controls(state)

    assert controls["data_gate"]["status"] == "FAIL"
    assert data_gate_failed(controls) is True
    assert controls["data_gate"]["critical_errors"][0]["code"] == "future_financial_period"
    assert controls["data_gate"]["critical_errors"][0]["policy_source"] == "legacy_source_rules"
    assert controls["data_gate"]["critical_errors"][0]["message"] == "Financial statement period is after the report as-of date."
    memo = render_data_defect_memo({**state, **controls})
    assert "不可发布" in memo
    assert "Fix WRDS internal consistency defects" in memo


def test_data_defect_memo_uses_data_contract_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "mode": "historical",
            "as_of_date": "2025-03-20",
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "gate_policy": {
                    "defect_memo": {
                        "title": "Custom Data Defect",
                        "intro": "Custom memo intro.",
                        "required_fixes": {
                            "WRDS_ONLY": ["Custom WRDS fix."],
                        },
                        "registry_warning_fix": "Custom registry warning fix.",
                    },
                },
            },
        },
    )

    controls = build_investment_data_controls(state)
    memo = render_data_defect_memo({**state, **controls})

    assert "# Custom Data Defect" in memo
    assert "Custom memo intro." in memo
    assert "1. Custom WRDS fix." in memo
    assert "Fix WRDS internal consistency defects" not in memo


def test_future_period_guardrail_uses_data_contract_source_validation_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "mode": "historical",
            "as_of_date": "2025-03-20",
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "future_financial_period")

    assert issue["policy_source"] == "data_contract_source_rules"
    assert issue["message"] == "Financial statement period is after the report as-of date."


def test_data_gate_blocks_official_gross_margin_mismatch() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "gp": 23224,
            "dp": None,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {
                "gross_profit": 23224,
                "gross_margin": 0.6213,
                "free_cash_flow": 1668,
            },
        },
        metadata={
            "as_of_date": "2026-05-27",
            "official_metrics": [
                {
                    "period": "FY2025",
                    "metric": "gross_margin",
                    "value": 0.398,
                    "source": "Micron FY2025 official release",
                }
            ],
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_gate"]["status"] == "FAIL"
    assert controls["data_gate"]["critical_errors"][0]["code"] == "official_metric_mismatch"
    assert controls["data_gate"]["critical_errors"][0]["policy_source"] == "legacy_source_rules"


def test_official_metric_mismatch_uses_data_contract_validation_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "gp": 23224,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {
                "gross_profit": 23224,
                "gross_margin": 0.6213,
                "free_cash_flow": 1668,
            },
        },
        metadata={
            "as_of_date": "2026-05-27",
            "official_metrics": [
                {
                    "period": "FY2025",
                    "metric": "gross_margin",
                    "value": 0.398,
                    "source": "Micron FY2025 official release",
                }
            ],
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "official_metric_mismatch")

    assert issue["policy_source"] == "data_contract_source_rules"
    assert issue["message"] == "WRDS/metric-registry value conflicts with company/SEC reported metric."


def test_internal_formula_validation_uses_data_contract_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 999, "gross_margin": 0.6213},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "fcf_formula_mismatch")

    assert issue["policy_source"] == "data_contract_formula_validation_rule"
    assert issue["message"] == "Calculated free cash flow does not equal operating cash flow minus capex."


def test_internal_formula_validation_uses_legacy_rule_when_descriptor_omits_rule() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": -1,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "non_positive_revenue")

    assert issue["policy_source"] == "legacy_formula_validation_rule"
    assert issue["message"] == "Revenue must be positive for financial analysis."


def test_metric_registry_prefers_after_depreciation_gross_margin_candidate() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "gp": 23224,
            "dp": 8351,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {
                "gross_profit": 23224,
                "gross_margin": 0.6213,
                "gross_margin_before_depreciation": 0.6213,
                "gross_profit_after_depreciation": 14873,
                "gross_margin_after_depreciation": 0.398,
                "reported_gross_margin_candidate": 0.398,
                "free_cash_flow": 1668,
            },
        },
        metadata={
            "as_of_date": "2026-05-27",
            "official_metrics": [
                {
                    "period": "FY2025",
                    "metric": "gross_margin",
                    "value": 0.398,
                    "source": "Micron FY2025 official release",
                }
            ],
        },
    )

    controls = build_investment_data_controls(state)
    gross_margin = [
        metric
        for metric in controls["metric_registry"]["metrics"]
        if metric["metric"] == "gross_margin" and metric["period"] == "FY2025"
    ][0]

    assert controls["data_gate"]["status"] == "PASS_WRDS_ONLY"
    assert gross_margin["value"] == 0.398
    assert controls["metric_registry"]["warnings"][0]["severity"] == "HIGH"
    assert controls["metric_registry"]["warnings"][0]["policy_source"] == "legacy_metric_registry_warning_rule"


def test_metric_registry_large_margin_gap_warning_uses_data_contract_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "gp": 23224,
            "dp": 8351,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {
                "gross_profit": 23224,
                "gross_margin": 0.6213,
                "gross_margin_before_depreciation": 0.6213,
                "gross_profit_after_depreciation": 14873,
                "gross_margin_after_depreciation": 0.398,
                "reported_gross_margin_candidate": 0.398,
                "free_cash_flow": 1668,
            },
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    warning = controls["metric_registry"]["warnings"][0]

    assert warning["policy_source"] == "data_contract_metric_registry_policy"
    assert warning["issue"].startswith("Compustat gross margin before depreciation materially exceeds")
    assert warning["instruction"] == "Do not cite raw Compustat gp/sale as GAAP reported gross margin without reconciliation."


def test_wrds_only_report_disallows_official_verified_claim() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("This is an SEC-verified gross margin.", {**state, **controls})
    guarded = apply_wrds_only_report_policy("This is an SEC-verified gross margin.", {**state, **controls})

    assert errors[0]["code"] == "official_verified_claim"
    assert errors[0]["source"] == "data_contract_claim_guardrail"
    assert "WRDS-only Claim Guardrail Report" in guarded
    assert "Memo policy source: `data_contract_claim_defect_memo_policy`" in guarded
    assert "Required fixes source: `data_contract_claim_guardrail`" in guarded


def test_wrds_only_report_claim_guardrails_can_come_from_custom_data_contract() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "claim_guardrails": {
                    "wrds_only_disallowed_claims": [
                        {
                            "code": "custom_forbidden_claim",
                            "phrases": ["custom forbidden phrase"],
                            "message": "Custom data contract blocks this phrase.",
                        }
                    ]
                },
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("This contains a custom forbidden phrase.", {**state, **controls})

    assert errors == [
        {
            "severity": "CRITICAL",
            "code": "custom_forbidden_claim",
            "message": "Custom data contract blocks this phrase.",
            "source": "data_contract_claim_guardrail",
        }
    ]


def test_wrds_only_claim_defect_required_fixes_can_come_from_custom_data_contract() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "claim_guardrails": {
                    "wrds_only_defect_memo": {
                        "title": "Custom Claim Defect Memo",
                        "intro": "Custom claim memo intro.",
                        "blocking_claim_issues_heading": "Custom Blocking Claims",
                        "required_fixes_heading": "Custom Fixes",
                        "blocked_draft_preview_heading": "Custom Draft Preview",
                    },
                    "wrds_only_required_fixes": [
                        "Replace the custom phrase with a registry-backed limitation.",
                    ],
                    "wrds_only_disallowed_claims": [
                        {
                            "code": "custom_forbidden_claim",
                            "phrases": ["custom forbidden phrase"],
                            "message": "Custom data contract blocks this phrase.",
                        }
                    ],
                },
            }
        },
    )
    controls = build_investment_data_controls(state)

    guarded = apply_wrds_only_report_policy("This contains a custom forbidden phrase.", {**state, **controls})

    assert "Required fixes source: `data_contract_claim_guardrail`" in guarded
    assert "# Custom Claim Defect Memo" in guarded
    assert "Custom claim memo intro." in guarded
    assert "## Custom Blocking Claims" in guarded
    assert "## Custom Fixes" in guarded
    assert "## Custom Draft Preview" in guarded
    assert "1. Replace the custom phrase with a registry-backed limitation." in guarded
    assert "WRDS-only Claim Guardrail Report" not in guarded


def test_wrds_only_report_claim_guardrails_legacy_fallback_when_contract_omits_rules() -> None:
    state = {"data_contract": {"source_mode": "WRDS_ONLY"}}
    errors = validate_wrds_only_report_claims(
        "This is an SEC-verified gross margin.",
        state,
    )
    guarded = apply_wrds_only_report_policy("This is an SEC-verified gross margin.", state)

    assert errors[0]["code"] == "official_verified_claim"
    assert errors[0]["source"] == "legacy_wrds_only_claim_guardrail"
    assert "Memo policy source: `legacy_wrds_only_claim_defect_memo_policy`" in guarded
    assert "Required fixes source: `legacy_wrds_only_claim_guardrail`" in guarded


def test_wrds_only_report_claim_guardrails_legacy_default_message_is_compatibility_policy(monkeypatch) -> None:
    import re

    from runtime import data_gate as data_gate_module

    monkeypatch.setattr(
        data_gate_module,
        "legacy_wrds_only_disallowed_claims",
        lambda: (
            {
                "code": "fallback_claim",
                "pattern": re.compile(r"fallback phrase", re.IGNORECASE),
            },
        ),
    )

    errors = data_gate_module.validate_wrds_only_report_claims(
        "This contains a fallback phrase.",
        {"data_contract": {"source_mode": "WRDS_ONLY"}},
    )

    assert errors == [
        {
            "severity": "CRITICAL",
            "code": "fallback_claim",
            "message": "WRDS-only mode disallows this claim.",
            "source": "legacy_wrds_only_claim_guardrail",
        }
    ]


def test_wrds_only_limitations_use_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "source_mode_limitations": {
                    "WRDS_ONLY": {
                        "box": "**Custom WRDS Limitation**\n\nUse only custom-contract data.",
                        "items": ["Custom-contract limitation."],
                    }
                },
            }
        },
    )
    controls = build_investment_data_controls(state)

    guarded = apply_wrds_only_report_policy("Plain report body.", {**state, **controls})

    assert controls["data_contract"]["source_mode_limitations_source"] == "data_contract_source_mode_limitations"
    assert controls["data_gate"]["limitations"] == ["Custom-contract limitation."]
    assert guarded.startswith("**Custom WRDS Limitation**")


def test_wrds_only_limitations_legacy_fallback_when_contract_omits_policy() -> None:
    guarded = apply_wrds_only_report_policy(
        "Plain report body.",
        {"data_contract": {"source_mode": "WRDS_ONLY"}},
    )

    assert "**数据限制：WRDS-only 模式**" in guarded


def test_high_depreciation_semiconductor_blocks_before_depreciation_margin_candidate() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "gp": 23224,
            "dp": 8351,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {
                "gross_profit": 23224,
                "gross_margin": 0.6213,
                "gross_margin_before_depreciation": 0.6213,
                "gross_margin_after_depreciation": 0.398,
                "reported_gross_margin_candidate": 0.6213,
                "free_cash_flow": 1668,
            },
        }
    )

    controls = build_investment_data_controls(state)

    assert controls["data_gate"]["status"] == "FAIL"
    issue = next(
        issue
        for issue in controls["data_gate"]["critical_errors"]
        if issue["code"] == "reported_margin_uses_before_depreciation"
    )
    assert issue["policy_source"] == "legacy_margin_basis_rule"


def test_high_depreciation_margin_basis_uses_data_contract_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "gp": 23224,
            "dp": 8351,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {
                "gross_profit": 23224,
                "gross_margin": 0.6213,
                "gross_margin_before_depreciation": 0.6213,
                "gross_margin_after_depreciation": 0.398,
                "reported_gross_margin_candidate": 0.6213,
                "free_cash_flow": 1668,
            },
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(
        issue
        for issue in controls["data_gate"]["critical_errors"]
        if issue["code"] == "reported_margin_uses_before_depreciation"
    )

    assert issue["policy_source"] == "data_contract_margin_basis_rule"
    assert issue["message"].startswith("High-depreciation semiconductor analysis cannot use")


def test_ambiguous_company_identity_uses_data_contract_source_validation_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
        extra_financials={
            "candidates": [
                {"gvkey": "001", "tic": "XYZ", "conm": "XYZ HOLDINGS", "match_score": 98, "source": "wrds_company_search"},
                {"gvkey": "002", "tic": "XYZ", "conm": "XYZ CORP", "match_score": 98, "source": "wrds_company_search"},
            ]
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "ambiguous_company_identity")

    assert issue["policy_source"] == "data_contract_source_rules"
    assert issue["message"] == "WRDS company resolver returned multiple top-scoring GVKEY candidates."


def test_ambiguous_company_identity_uses_legacy_source_validation_rule_when_descriptor_omits_rule() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
            }
        },
        extra_financials={
            "candidates": [
                {"gvkey": "001", "tic": "XYZ", "conm": "XYZ HOLDINGS", "match_score": 98, "source": "wrds_company_search"},
                {"gvkey": "002", "tic": "XYZ", "conm": "XYZ CORP", "match_score": 98, "source": "wrds_company_search"},
            ]
        },
    )

    controls = build_investment_data_controls(state)
    issue = next(issue for issue in controls["data_gate"]["critical_errors"] if issue["code"] == "ambiguous_company_identity")

    assert issue["policy_source"] == "legacy_source_rules"
    assert issue["message"] == "WRDS company resolver returned multiple top-scoring GVKEY candidates."


def test_compustat_standard_filter_warning_uses_data_contract_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "indfmt": "FS",
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
    )

    controls = build_investment_data_controls(state)
    warning = next(warning for warning in controls["data_gate"]["warnings"] if warning["code"] == "non_standard_compustat_record")

    assert warning["policy_source"] == "data_contract_compustat_standard_filter_rule"
    assert warning["field"] == "indfmt"
    assert warning["message"] == "Compustat row uses a non-standard filter value; metrics may not be comparable."


def test_compustat_standard_filter_warning_uses_legacy_rule_when_descriptor_omits_rule() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "indfmt": "FS",
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.6213},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "thin-contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )

    controls = build_investment_data_controls(state)
    warning = next(warning for warning in controls["data_gate"]["warnings"] if warning["code"] == "non_standard_compustat_record")

    assert warning["policy_source"] == "legacy_compustat_standard_filter_rule"
    assert warning["field"] == "indfmt"


def test_wrds_only_blocks_quarterly_trigger_when_registry_has_only_annual_metrics() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("建议等待 Q2 FY2025 验证。", {**state, **controls})

    issue = next(issue for issue in errors if issue["code"] == "quarterly_trigger_without_quarterly_metric")
    assert issue["source"] == "data_contract_required_period_policy"
    assert issue["message"] == "The report references a quarterly trigger, but the WRDS metric registry has no matching quarterly metrics."
    assert issue["period"] == "FY2025Q2"


def test_wrds_only_quarterly_trigger_guardrail_legacy_source_when_required_period_policy_missing() -> None:
    errors = validate_wrds_only_report_claims(
        "建议等待 Q2 FY2025 验证。",
        {"data_contract": {"source_mode": "WRDS_ONLY"}},
    )

    issue = next(issue for issue in errors if issue["code"] == "quarterly_trigger_without_quarterly_metric")
    assert issue["source"] == "legacy_wrds_only_required_period_policy"
    assert issue["message"] == "The report references a quarterly trigger, but the WRDS metric registry has no matching quarterly metrics."


def test_wrds_only_blocks_non_gaap_eps_without_source() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("Non-GAAP EPS is the primary valuation anchor.", {**state, **controls})

    issue = next(issue for issue in errors if issue["code"] == "non_gaap_without_source")
    assert issue["source"] == "data_contract_metric_requirement"
    assert issue["message"] == "Non-GAAP EPS cannot be used in WRDS-only mode without a reliable non-GAAP dataset."
    assert issue["required_metrics"] == ["non_gaap_eps"]
    assert controls["data_gate"]["non_gaap_metric_group_source"] == "data_contract_gate_metric_group"
    assert controls["data_gate"]["estimate_metric_group_source"] == "data_contract_gate_metric_group"
    forward_gap = next(gap for gap in controls["data_gate"]["evidence_gaps"] if gap["code"] == "missing_forward_estimates")
    assert forward_gap["policy_source"] == "data_contract_gate_evidence_gap_rule"
    assert forward_gap["required_evidence"] == ["street_eps", "ibes_actual_eps", "ibes_mean_estimate"]


def test_wrds_only_non_gaap_source_guardrail_legacy_source_when_metric_policy_missing() -> None:
    errors = validate_wrds_only_report_claims(
        "Non-GAAP EPS is the primary valuation anchor.",
        {"data_contract": {"source_mode": "WRDS_ONLY"}},
    )

    issue = next(issue for issue in errors if issue["code"] == "non_gaap_without_source")
    assert issue["source"] == "legacy_wrds_only_metric_requirement"
    assert issue["message"] == "Non-GAAP EPS cannot be used in WRDS-only mode without a reliable non-GAAP dataset."


def test_wrds_only_blocks_high_confidence_report() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("结论：高置信度 Buy。", {**state, **controls})

    issue = next(issue for issue in errors if issue["code"] == "wrds_only_confidence_too_high")
    assert issue["source"] == "data_contract_confidence_policy"
    assert issue["message"] == "WRDS-only mode cannot publish high-confidence conclusions."
    assert issue["maximum_confidence"] == "MEDIUM"


def test_wrds_only_high_confidence_policy_can_come_from_custom_data_contract() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "confidence_policy": {
                    "maximum_confidence": "low",
                    "downgrade_to_low_when": ["custom confidence downgrade"],
                },
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("Confidence: high.", {**state, **controls})

    issue = next(issue for issue in errors if issue["code"] == "wrds_only_confidence_too_high")
    assert controls["data_contract"]["confidence_policy"]["source"] == "data_contract_confidence_policy"
    assert controls["data_contract"]["confidence_policy"]["downgrade_to_low_when"] == ["custom confidence downgrade"]
    assert issue["source"] == "data_contract_confidence_policy"
    assert issue["message"] == "WRDS-only mode cannot publish high-confidence conclusions."
    assert issue["maximum_confidence"] == "LOW"


def test_wrds_only_high_confidence_guardrail_legacy_source_when_descriptor_omits_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-08-31",
            "fyear": 2025,
            "sale": 37378,
            "oancf": 17525,
            "capx": 15857,
            "calculated": {"free_cash_flow": 1668, "gross_margin": 0.4},
        },
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
            }
        },
    )
    controls = build_investment_data_controls(state)

    errors = validate_wrds_only_report_claims("Confidence: high.", {**state, **controls})

    issue = next(issue for issue in errors if issue["code"] == "wrds_only_confidence_too_high")
    assert controls["data_contract"]["confidence_policy"]["source"] == "legacy_wrds_only_confidence_guardrail"
    assert issue["source"] == "legacy_wrds_only_confidence_guardrail"
    assert issue["message"] == "WRDS-only mode cannot publish high-confidence conclusions."


def test_wrds_only_high_confidence_guardrail_legacy_source_when_contract_policy_missing() -> None:
    errors = validate_wrds_only_report_claims(
        "Confidence: high.",
        {"data_contract": {"source_mode": "WRDS_ONLY"}},
    )

    issue = next(issue for issue in errors if issue["code"] == "wrds_only_confidence_too_high")
    assert issue["source"] == "legacy_wrds_only_confidence_guardrail"
    assert issue["message"] == "WRDS-only mode cannot publish high-confidence conclusions."


def test_metric_registry_adds_deterministic_ttm_valuation_and_series() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 1000,
            "oancf": 200,
            "capx": 50,
            "calculated": {"free_cash_flow": 150, "gross_margin": 0.4},
        },
        quarterly_rows=[
            {
                "datadate": "2026-03-31",
                "fyearq": 2026,
                "fqtr": 1,
                "saleq": 120,
                "niq": 12,
                "oibdpq": 30,
                "oiadpq": 20,
                "prccq": 10,
                "cshoq": 100,
                "dlttq": 200,
                "dlcq": 20,
                "cheq": 50,
                "capxy": 25,
                "calculated": {"gross_margin": 0.5, "operating_margin": 0.1667},
            },
            {
                "datadate": "2025-12-31",
                "fyearq": 2025,
                "fqtr": 4,
                "saleq": 110,
                "niq": 11,
                "oibdpq": 28,
                "oiadpq": 18,
                "capxy": 80,
                "calculated": {"gross_margin": 0.5, "operating_margin": 0.1636},
            },
            {
                "datadate": "2025-09-30",
                "fyearq": 2025,
                "fqtr": 3,
                "saleq": 100,
                "niq": 10,
                "oibdpq": 26,
                "oiadpq": 16,
                "capxy": 60,
                "calculated": {"gross_margin": 0.5, "operating_margin": 0.16},
            },
            {
                "datadate": "2025-06-30",
                "fyearq": 2025,
                "fqtr": 2,
                "saleq": 90,
                "niq": 9,
                "oibdpq": 24,
                "oiadpq": 14,
                "capxy": 40,
                "calculated": {"gross_margin": 0.5, "operating_margin": 0.1556},
            },
        ],
    )

    controls = build_investment_data_controls(state)
    metrics = controls["metric_registry"]["metrics"]
    by_name = {metric["metric"]: metric for metric in metrics if str(metric.get("metric", "")).startswith("ttm_")}

    assert by_name["ttm_revenue"]["value"] == 420
    assert by_name["ttm_net_income"]["value"] == 42
    assert by_name["ttm_market_cap"]["value"] == 1000
    assert round(by_name["ttm_pe"]["value"], 2) == 23.81
    assert round(by_name["ttm_ev_ebitda"]["value"], 2) == 10.83
    assert controls["metric_registry"]["annual_metric_series"]["capex"][0]["value"] == 50
    assert "Q" in controls["metric_registry"]["quarterly_metric_series"]["capex"][0]["period"]


def test_metric_registry_adds_working_capital_and_standalone_quarter_cash_flow() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 1000,
            "cogs": 600,
            "invt": 150,
            "rect": 100,
            "ap": 75,
            "oancf": 540,
            "capx": 140,
            "calculated": {"free_cash_flow": 400, "gross_margin": 0.4},
        },
        quarterly_rows=[
            {"datadate": "2025-12-31", "fyearq": 2025, "fqtr": 4, "saleq": 300, "cogsq": 180, "invtq": 140, "rectq": 95, "apq": 70, "niq": 30, "oibdpq": 60, "oancfy": 540, "capxy": 140},
            {"datadate": "2025-09-30", "fyearq": 2025, "fqtr": 3, "saleq": 260, "cogsq": 160, "invtq": 130, "rectq": 85, "apq": 65, "niq": 26, "oibdpq": 55, "oancfy": 380, "capxy": 100},
            {"datadate": "2025-06-30", "fyearq": 2025, "fqtr": 2, "saleq": 230, "cogsq": 150, "invtq": 120, "rectq": 80, "apq": 60, "niq": 23, "oibdpq": 50, "oancfy": 250, "capxy": 60},
            {"datadate": "2025-03-31", "fyearq": 2025, "fqtr": 1, "saleq": 210, "cogsq": 140, "invtq": 110, "rectq": 75, "apq": 55, "niq": 21, "oibdpq": 45, "oancfy": 100, "capxy": 20, "prccq": 10, "cshoq": 100, "dlttq": 200, "dlcq": 20, "cheq": 50},
        ],
    )

    controls = build_investment_data_controls(state)
    metrics = controls["metric_registry"]["metrics"]

    def metric_value(name: str, period: str) -> float:
        for metric in metrics:
            if metric["metric"] == name and metric["period"] == period:
                return metric["value"]
        raise AssertionError(f"missing metric {name} {period}")

    assert round(metric_value("days_inventory_outstanding", "FY2025"), 2) == 91.25
    assert round(metric_value("days_sales_outstanding", "FY2025"), 2) == 36.5
    assert round(metric_value("days_payables_outstanding", "FY2025"), 2) == 45.62
    assert round(metric_value("cash_conversion_cycle", "FY2025"), 2) == 82.12
    assert metric_value("operating_cash_flow_quarter", "FY2025Q2") == 150
    assert metric_value("capex_quarter", "FY2025Q2") == 40
    assert metric_value("free_cash_flow_quarter", "FY2025Q2") == 110
    assert metric_value("ttm_operating_cash_flow", "TTM_FY2025Q4") == 540
    assert metric_value("ttm_capex", "TTM_FY2025Q4") == 140
    assert metric_value("ttm_free_cash_flow", "TTM_FY2025Q4") == 400
    assert "cash_conversion_cycle" in controls["metric_registry"]["quarterly_metric_series"]


def test_metric_registry_adds_advanced_wrds_package_metrics() -> None:
    state = wrds_state(
        {
            "datadate": "2025-10-31",
            "fyear": 2025,
            "sale": 1000,
            "ebit": 180,
            "ebitda": 260,
            "xint": 20,
            "dltt": 300,
            "dlc": 50,
            "che": 100,
            "gdwl": 220,
            "intan": 180,
            "at": 1200,
            "dvc": 30,
            "dvp": 0,
            "prstkc": 50,
            "sstk": 10,
            "ajex": 2,
            "oancf": 200,
            "capx": 40,
            "calculated": {"free_cash_flow": 160, "gross_margin": 0.5},
        }
    )

    controls = build_investment_data_controls(state)
    metrics = controls["metric_registry"]["metrics"]
    latest = {metric["metric"]: metric["value"] for metric in metrics if metric.get("period") == "FY2025"}

    assert latest["interest_expense"] == 20
    assert latest["interest_coverage"] == 9
    assert round(latest["debt_to_ebitda"], 2) == 1.35
    assert latest["goodwill"] == 220
    assert latest["intangibles"] == 180
    assert round(latest["goodwill_to_assets"], 4) == 0.1833
    assert latest["net_capital_return"] == 70
    assert latest["split_adjustment_factor"] == 2


def test_acquisition_heavy_missing_non_gaap_forces_gaap_only_preliminary() -> None:
    state = wrds_state(
        {
            "datadate": "2025-10-31",
            "fyear": 2025,
            "sale": 68282,
            "ni": 24972,
            "epsfi": 5.23,
            "oancf": 22000,
            "capx": 623,
            "gdwl": 90000,
            "intan": 80000,
            "at": 220000,
            "calculated": {"free_cash_flow": 21377, "gross_margin": 0.65},
        },
        task="AVGO",
        company={"gvkey": "180711", "tic": "AVGO", "conm": "BROADCOM INC", "cik": "0001730168"},
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]

    assert gate["status"] == "PASS_WRDS_ONLY"
    assert gate["blocking"] is False
    assert any(profile["profile"] == "acquisition_intensive" for profile in gate["data_profiles"])
    assert gate["acquisition_heavy"] is True
    assert gate["non_gaap_available"] is False
    assert gate["formal_valuation_allowed"] is False
    assert gate["valuation_scope"] == "GAAP_ONLY_PRELIMINARY"
    assert gate["next_action"] == "continue_with_gaap_only_preliminary"
    warning = next(
        issue
        for issue in gate["warnings"]
        if issue["code"] == "missing_non_gaap_eps_for_acquisition_heavy_company"
    )
    assert warning["policy_source"] == "legacy_profile_warning_rule"


def test_generic_high_goodwill_company_missing_street_eps_gets_same_policy() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "ni": 300,
            "epsfi": 1.25,
            "oancf": 550,
            "capx": 80,
            "gdwl": 1800,
            "intan": 500,
            "at": 6000,
            "calculated": {"free_cash_flow": 470, "gross_margin": 0.45},
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]

    assert gate["acquisition_heavy"] is True
    profile = next(profile for profile in gate["data_profiles"] if profile["profile"] == "acquisition_intensive")
    assert profile["policy_source"] == "legacy_profile_policy"
    assert profile["severity"] == "HIGH"
    assert profile["reason"].startswith("Company appears acquisition/intangible intensive")
    gap = next(gap for gap in gate["evidence_gaps"] if gap["code"] == "missing_non_gaap_eps_for_acquisition_heavy_company")
    assert gap["policy_source"] == "legacy_profile_evidence_rule"
    assert gap["severity"] == "HIGH"
    assert gate["formal_valuation_allowed"] is False
    assert gate["valuation_scope"] == "GAAP_ONLY_PRELIMINARY"
    assert gate["conclusion_permissions"]["formal_valuation_allowed"] is False


def test_data_gate_profile_policy_uses_data_contract_descriptor_thresholds() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "ni": 300,
            "epsfi": 1.25,
            "oancf": 550,
            "capx": 80,
            "gdwl": 100,
            "intan": 0,
            "at": 1000,
            "calculated": {"free_cash_flow": 470, "gross_margin": 0.45},
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "profile_policies": {
                    "acquisition_intensive": {
                        "severity": "CRITICAL",
                        "reason": "Custom acquisition profile reason.",
                        "goodwill_to_assets_threshold": 0.05,
                        "intangibles_to_assets_threshold": 0.5,
                        "combined_intangible_assets_threshold": 0.5,
                        "required_evidence": ["custom_eps_bridge"],
                        "valuation_policy": "Custom EPS bridge required before formal valuation.",
                    }
                },
                "gate_policy": {
                    "profile_evidence_rules": {
                        "acquisition_intensive": {
                            "severity": "CRITICAL",
                            "missing_evidence_code": "missing_non_gaap_eps_for_acquisition_heavy_company",
                            "message": "Custom acquisition evidence missing.",
                            "blocks_formal_valuation": True,
                            "valuation_scope_when_blocked": "CUSTOM_SCOPE",
                        }
                    }
                },
            }
        },
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]
    profile = next(profile for profile in gate["data_profiles"] if profile["profile"] == "acquisition_intensive")
    gap = next(gap for gap in gate["evidence_gaps"] if gap["code"] == "missing_non_gaap_eps_for_acquisition_heavy_company")

    assert controls["data_contract"]["profile_policies"]["acquisition_intensive"]["goodwill_to_assets_threshold"] == 0.05
    assert profile["policy_source"] == "data_contract_profile_policy"
    assert profile["severity"] == "CRITICAL"
    assert profile["reason"] == "Custom acquisition profile reason."
    assert profile["required_evidence"] == ["custom_eps_bridge"]
    assert profile["policy"] == "Custom EPS bridge required before formal valuation."
    assert gap["policy_source"] == "data_contract_profile_evidence_rule"
    assert gap["severity"] == "CRITICAL"
    assert gap["message"] == "Custom acquisition evidence missing."
    assert gap["valuation_scope"] == "CUSTOM_SCOPE"
    assert gap["required_evidence"] == ["custom_eps_bridge"]
    assert gate["formal_valuation_allowed"] is False


def test_data_gate_completeness_metrics_use_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "calculated": {"gross_margin": 0.45},
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "completeness_required_metrics": ["revenue"],
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_contract"]["completeness_required_metrics"] == ["revenue"]
    assert controls["data_gate"]["data_completeness_score"] == 100


def test_data_gate_metric_aliases_use_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "completeness_required_metrics": ["top-line"],
                "metric_aliases": {"top-line": "revenue"},
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_contract"]["metric_aliases_source"] == "data_contract_metric_aliases"
    assert controls["data_contract"]["metric_aliases"]["top_line"] == "revenue"
    assert controls["data_gate"]["data_completeness_score"] == 100


def test_data_gate_metric_aliases_legacy_fallback_when_descriptor_omits_aliases() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "completeness_required_metrics": ["sales"],
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_contract"]["metric_aliases_source"] == "legacy_metric_aliases"
    assert controls["data_contract"]["metric_aliases"]["sales"] == "revenue"
    assert controls["data_gate"]["data_completeness_score"] == 100
    assert controls["data_gate"]["data_completeness_score_source"] == "legacy_gate_score_policy"


def test_data_gate_score_policy_uses_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "completeness_required_metrics": ["revenue", "gross_margin"],
                "gate_policy": {
                    "score_policy": {
                        "data_completeness": {
                            "annual_series_bonus": 25,
                            "quarterly_series_bonus": 0,
                            "ttm_series_bonus": 0,
                        }
                    }
                },
            }
        },
    )

    controls = build_investment_data_controls(state)

    assert controls["data_contract"]["gate_policy"]["score_policy"]["data_completeness"]["annual_series_bonus"] == 25
    assert controls["data_gate"]["data_completeness_score"] == 75
    assert controls["data_gate"]["data_completeness_score_source"] == "data_contract_gate_score_policy"
    assert controls["data_gate"]["quality_score_source"] == "legacy_gate_score_policy"
    assert controls["data_gate"]["decision_readiness_score_source"] == "legacy_gate_score_policy"


def test_ibes_crsp_and_segments_unlock_profile_evidence_gaps() -> None:
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 5000,
            "ni": 300,
            "epsfi": 1.25,
            "oancf": 550,
            "capx": 80,
            "gdwl": 1800,
            "intan": 500,
            "at": 6000,
            "calculated": {"free_cash_flow": 470, "gross_margin": 0.45},
        },
        task="XYZ",
        company={"gvkey": "999999", "tic": "XYZ", "conm": "GENERIC SOFTWARE HOLDINGS INC", "cik": "0009999999"},
        extra_financials={
            "crsp_market_data": {
                "table": "crsp.dsf",
                "latest": {
                    "permno": 12345,
                    "permco": 54321,
                    "date": "2026-05-26",
                    "prc": -50,
                    "ret": 0.02,
                    "vol": 100000,
                    "shrout": 1000000,
                    "cfacpr": 1,
                    "cfacshr": 1,
                },
                "daily_rows": [],
            },
            "ibes_estimates": {
                "summary_table": "ibes.statsum_epsus",
                "actual_table": "ibes.act_epsus",
                "summary_rows": [
                    {
                        "ticker": "XYZ",
                        "statpers": "2026-05-15",
                        "fpedats": "2026-12-31",
                        "measure": "EPS",
                        "fpi": "1",
                        "meanest": 2.5,
                        "actual": None,
                        "numest": 12,
                    }
                ],
                "actual_rows": [
                    {
                        "ticker": "XYZ",
                        "pends": "2025-12-31",
                        "measure": "EPS",
                        "anndats": "2026-02-01",
                        "value": 1.8,
                    }
                ],
            },
            "compustat_segments": {
                "table": "compseg.wrds_segmerged",
                "rows": [
                    {
                        "gvkey": "999999",
                        "stype": "BUSSEG",
                        "sid": "1",
                        "snms": "Software",
                        "sales": 3000,
                        "ops": 900,
                        "atlls": 2000,
                        "capxs": 20,
                        "datadate": "2025-12-31",
                    }
                ],
            },
        },
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]
    metrics = controls["metric_registry"]["metrics"]
    metric_names = {metric["metric"] for metric in metrics}

    assert gate["acquisition_heavy"] is True
    assert gate["street_eps_available"] is True
    assert gate["formal_valuation_allowed"] is True
    assert gate["conclusion_permissions"]["formal_valuation_allowed"] is True
    assert gate["conclusion_permissions"]["segment_claims_allowed"] is True
    assert gate["conclusion_permissions"]["market_timing_allowed"] is True
    assert not any(gap["code"] == "missing_non_gaap_eps_for_acquisition_heavy_company" for gap in gate["evidence_gaps"])
    assert {"street_eps", "ibes_actual_eps", "crsp_market_price", "crsp_market_cap", "segment_sales"} <= metric_names


def test_peer_comparison_metrics_unlock_relative_valuation_permission() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    base_row = {
        "datadate": "2025-12-31",
        "fyear": 2025,
        "sale": 5000,
        "ni": 300,
        "epsfi": 1.25,
        "oancf": 550,
        "capx": 80,
        "calculated": {"free_cash_flow": 470, "gross_margin": 0.45},
    }
    orchestration = {
        "task_type": "investment",
        "committee": True,
        "required_agents": {"wrds": True},
        "required_data_packages": ["peer_comparison"],
    }
    metadata = {
        "capability_runtime": {
            "capabilities": {
                "value-investing-research": {"entrypoints": {"workflow": workflow}},
            }
        }
    }

    missing_state = wrds_state(base_row, task="XYZ", metadata=metadata, orchestration=orchestration)
    missing_controls = build_investment_data_controls(missing_state)
    assert missing_controls["data_gate"]["conclusion_permissions"]["peer_valuation_allowed"] is False
    peer_profile = next(
        profile
        for profile in missing_controls["data_gate"]["data_profiles"]
        if profile["profile"] == "peer_comparison_requested_not_integrated"
    )
    peer_gap = next(gap for gap in missing_controls["data_gate"]["evidence_gaps"] if gap["code"] == "missing_peer_comparison")
    assert peer_profile["policy_source"] == "data_contract_profile_policy"
    assert peer_profile["severity"] == "MEDIUM"
    assert peer_gap["policy_source"] == "data_contract_profile_policy"

    present_state = wrds_state(
        base_row,
        task="XYZ",
        metadata=metadata,
        orchestration=orchestration,
        extra_financials={
            "peer_comparison": {
                "table": "comp.funda",
                "candidate_table": "comp.names",
                "selection_basis": ["gsubind:45202030"],
                "peer_rows": [
                    {
                        "peer_gvkey": "002000",
                        "peer_tic": "PEER",
                        "peer_conm": "PEER INC",
                        "datadate": "2025-12-31",
                        "fyear": 2025,
                        "sale": 10000,
                        "ni": 1000,
                        "oancf": 1500,
                        "capx": 300,
                        "dltt": 2000,
                        "dlc": 100,
                        "che": 500,
                        "oibdp": 2500,
                        "prcc_f": 50,
                        "csho": 1000,
                    }
                ],
            }
        },
    )
    present_controls = build_investment_data_controls(present_state)
    metric_names = {metric["metric"] for metric in present_controls["metric_registry"]["metrics"]}

    assert present_controls["data_gate"]["conclusion_permissions"]["peer_valuation_allowed"] is True
    assert not any(gap["code"] == "missing_peer_comparison" for gap in present_controls["data_gate"]["evidence_gaps"])
    assert {"peer_count", "peer_market_cap", "peer_pe", "peer_ev_ebitda", "peer_median_pe"} <= metric_names


def test_financial_company_profile_disallows_industrial_ev_ebitda_permission() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-12-31",
            "fyear": 2025,
            "sale": 10000,
            "ni": 1000,
            "epsfi": 5.0,
            "oancf": 1200,
            "capx": 100,
            "calculated": {"free_cash_flow": 1100, "gross_margin": 0.4},
        },
        task="BANK",
        company={"gvkey": "888888", "tic": "BANK", "conm": "GENERIC BANK INC", "sic": "6021", "naics": "522110"},
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]

    profile = next(profile for profile in gate["data_profiles"] if profile["profile"] == "financial_company")
    assert profile["policy_source"] == "data_contract_profile_policy"
    assert profile["severity"] == "HIGH"
    assert profile["required_evidence"] == ["financial_company_specific_package"]
    assert gate["conclusion_permissions"]["ev_ebitda_allowed"] is False


def test_wrds_only_blocks_formal_valuation_when_gaap_only_preliminary() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-10-31",
            "fyear": 2025,
            "sale": 68282,
            "ni": 24972,
            "epsfi": 5.23,
            "oancf": 22000,
            "capx": 623,
            "gdwl": 90000,
            "intan": 80000,
            "at": 220000,
            "calculated": {"free_cash_flow": 21377, "gross_margin": 0.65},
        },
        task="AVGO",
        company={"gvkey": "180711", "tic": "AVGO", "conm": "BROADCOM INC", "cik": "0001730168"},
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            }
        },
    )
    controls = build_investment_data_controls(state)
    gap = next(
        gap
        for gap in controls["data_gate"]["evidence_gaps"]
        if gap["code"] == "missing_non_gaap_eps_for_acquisition_heavy_company"
    )

    errors = validate_wrds_only_report_claims("Decision: Watch. Broadcom is fairly valued.", {**state, **controls})
    guarded = apply_wrds_only_report_policy("Decision: Watch. Broadcom is fairly valued.", {**state, **controls})

    warning = next(
        issue
        for issue in controls["data_gate"]["warnings"]
        if issue["code"] == "missing_non_gaap_eps_for_acquisition_heavy_company"
    )
    assert gap["policy_source"] == "data_contract_profile_evidence_rule"
    assert warning["policy_source"] == "data_contract_profile_warning_rule"
    issue = next(issue for issue in errors if issue["code"] == "formal_valuation_without_non_gaap")
    assert issue["source"] == "data_contract_output_effect"
    assert issue["message"].startswith("Acquisition-heavy company without sourced non-GAAP EPS")
    assert issue["valuation_scope"] == "GAAP_ONLY_PRELIMINARY"
    assert issue["next_action"] == "continue_with_gaap_only_preliminary"
    assert "WRDS-only Claim Guardrail Report" in guarded


def test_wrds_only_formal_valuation_guardrail_legacy_source_when_output_effect_missing() -> None:
    errors = validate_wrds_only_report_claims(
        "Decision: Watch. The stock is fairly valued.",
        {
            "data_contract": {"source_mode": "WRDS_ONLY"},
            "data_gate": {"formal_valuation_allowed": False},
        },
    )

    issue = next(issue for issue in errors if issue["code"] == "formal_valuation_without_non_gaap")
    assert issue["source"] == "legacy_wrds_only_output_effect"
    assert issue["message"].startswith("Acquisition-heavy company without sourced non-GAAP EPS")
    assert issue["valuation_scope"] == "GAAP_ONLY_PRELIMINARY"


def test_wrds_only_formal_valuation_guardrail_uses_declared_conclusion_permission() -> None:
    state = {
        "data_contract": {"source_mode": "WRDS_ONLY"},
        "data_gate": {
            "conclusion_permissions": {
                "decision:formal_valuation": {"allowed": False, "label": "formal valuation"},
            }
        },
    }

    errors = validate_wrds_only_report_claims("Decision: Watch. The stock is fairly valued.", state)
    guarded = apply_wrds_only_report_policy("Decision: Watch. The stock is fairly valued.", state)

    issue = next(issue for issue in errors if issue["code"] == "formal_valuation_without_non_gaap")
    assert issue["source"] == "legacy_wrds_only_output_effect"
    assert "WRDS-only Claim Guardrail Report" in guarded


def test_material_intangibles_jump_blocks_report_publication_but_not_committee() -> None:
    state = wrds_state(
        {
            "datadate": "2025-09-30",
            "fyear": 2025,
            "sale": 400000,
            "ni": 100000,
            "epsfi": 7.5,
            "oancf": 120000,
            "capx": 10000,
            "at": 350000,
            "intan": 0,
            "gdwl": 0,
            "calculated": {"free_cash_flow": 110000, "gross_margin": 0.45},
        },
        task="AAPL",
        company={"gvkey": "001690", "tic": "AAPL", "conm": "APPLE INC", "cik": "0000320193"},
        quarterly_rows=[
            {
                "datadate": "2025-12-31",
                "fyearq": 2026,
                "fqtr": 1,
                "saleq": 120000,
                "niq": 30000,
                "atq": 360000,
                "intanq": 0,
                "gdwlq": 0,
                "oancfy": 35000,
                "capxy": 5000,
                "calculated": {"free_cash_flow": 30000, "gross_margin": 0.45},
            },
            {
                "datadate": "2026-03-31",
                "fyearq": 2026,
                "fqtr": 2,
                "saleq": 110000,
                "niq": 28000,
                "atq": 374000,
                "intanq": 21334,
                "gdwlq": 0,
                "oancfy": 68000,
                "capxy": 9000,
                "calculated": {"free_cash_flow": 59000, "gross_margin": 0.45},
            },
        ],
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]
    combined = {**state, **controls}

    assert gate["status"] == "PASS_WRDS_ONLY"
    assert gate["blocking"] is False
    assert gate["report_publication_allowed"] is False
    assert gate["formal_valuation_allowed"] is False
    assert gate["valuation_scope"] == "DATA_READINESS_BLOCKED_PRELIMINARY"
    assert gate["next_action"] == "continue_to_committee_but_block_publication"
    assert gate["data_completeness_score"] >= 80
    assert gate["decision_readiness_score"] < gate["data_completeness_score"]
    issue = next(issue for issue in gate["decision_blockers"] if issue["code"] == "material_intangibles_jump_unexplained")
    assert issue["policy_source"] == "legacy_balance_sheet_jump_rule"
    assert data_gate_failed(combined) is False
    assert data_gate_publication_blocked(combined) is True
    memo = render_data_readiness_memo(combined)
    assert "Data Readiness Defect Report" in memo
    assert "- Memo policy source: `legacy_data_readiness_memo_policy`" in memo
    assert "- Publication target: `decision:report_publication`" in memo
    assert "- Publication allowed: `False`" in memo
    assert "formal investment report" not in memo.lower()
    assert "committee analysis" not in memo.lower()
    assert "Report publication allowed" not in memo


def test_material_balance_sheet_jump_uses_data_contract_rule() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    workflow = load_capability_descriptor(manifest)["entrypoints"]["workflow"]
    state = wrds_state(
        {
            "datadate": "2025-09-30",
            "fyear": 2025,
            "sale": 400000,
            "ni": 100000,
            "epsfi": 7.5,
            "oancf": 120000,
            "capx": 10000,
            "at": 350000,
            "intan": 0,
            "gdwl": 0,
            "calculated": {"free_cash_flow": 110000, "gross_margin": 0.45},
        },
        task="AAPL",
        company={"gvkey": "001690", "tic": "AAPL", "conm": "APPLE INC", "cik": "0000320193"},
        metadata={
            "capability_runtime": {
                "capabilities": {
                    "value-investing-research": {"entrypoints": {"workflow": workflow}},
                }
            },
        },
        quarterly_rows=[
            {
                "datadate": "2025-12-31",
                "fyearq": 2026,
                "fqtr": 1,
                "saleq": 120000,
                "niq": 30000,
                "atq": 360000,
                "intanq": 0,
                "gdwlq": 0,
                "oancfy": 35000,
                "capxy": 5000,
                "calculated": {"free_cash_flow": 30000, "gross_margin": 0.45},
            },
            {
                "datadate": "2026-03-31",
                "fyearq": 2026,
                "fqtr": 2,
                "saleq": 110000,
                "niq": 28000,
                "atq": 374000,
                "intanq": 21334,
                "gdwlq": 0,
                "oancfy": 68000,
                "capxy": 9000,
                "calculated": {"free_cash_flow": 59000, "gross_margin": 0.45},
            },
        ],
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]
    issue = next(issue for issue in gate["decision_blockers"] if issue["code"] == "material_intangibles_jump_unexplained")

    assert issue["policy_source"] == "data_contract_balance_sheet_jump_rule"
    assert issue["message"].startswith("Material intangibles jump detected in quarterly WRDS data.")


def test_data_readiness_memo_uses_declared_publication_permission() -> None:
    memo = render_data_readiness_memo(
        {
            "task": "Review toy evidence",
            "data_gate": {
                "status": "PASS_WITH_LIMITS",
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                },
            },
        }
    )

    assert "- Publication target: `decision:toy_publish`" in memo
    assert "- Publication allowed: `False`" in memo
    assert "No explicit blocker details were recorded, but publication was not allowed." in memo
    assert "report publication" not in memo.lower()


def test_data_readiness_memo_uses_data_contract_policy() -> None:
    memo = render_data_readiness_memo(
        {
            "task": "Review custom evidence",
            "data_contract": {
                "source_mode": "CUSTOM_ONLY",
                "gate_policy": {
                    "readiness_memo": {
                        "title": "Custom Readiness Memo",
                        "intro": "Custom readiness intro.",
                        "publication_blockers_heading": "Custom Blockers",
                        "no_blocker_text": "Custom no blocker text.",
                        "warnings_heading": "Custom Warnings",
                        "required_next_steps_heading": "Custom Next Steps",
                        "required_next_steps": [
                            "Custom step one.",
                            "Custom step two.",
                        ],
                    },
                },
            },
            "data_gate": {
                "status": "PASS_WITH_LIMITS",
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                },
                "warnings": [
                    {"code": "custom_warning", "message": "Custom warning message."},
                ],
            },
        }
    )

    assert "# Custom Readiness Memo" in memo
    assert "Custom readiness intro." in memo
    assert "## Custom Blockers" in memo
    assert "Custom no blocker text." in memo
    assert "## Custom Warnings" in memo
    assert "## Custom Next Steps" in memo
    assert "1. Custom step one." in memo
    assert "2. Custom step two." in memo
    assert "- Memo policy source: `data_contract_readiness_memo_policy`" in memo
    assert "Data Readiness Defect Report" not in memo


def test_data_gate_output_effects_use_data_contract_descriptor() -> None:
    state = wrds_state(
        {
            "datadate": "2025-09-30",
            "fyear": 2025,
            "sale": 400000,
            "ni": 100000,
            "epsfi": 7.5,
            "oancf": 120000,
            "capx": 10000,
            "at": 350000,
            "intan": 0,
            "gdwl": 0,
            "calculated": {"free_cash_flow": 110000, "gross_margin": 0.45},
        },
        task="AAPL",
        company={"gvkey": "001690", "tic": "AAPL", "conm": "APPLE INC", "cik": "0000320193"},
        quarterly_rows=[
            {
                "datadate": "2025-12-31",
                "fyearq": 2026,
                "fqtr": 1,
                "saleq": 120000,
                "niq": 30000,
                "atq": 360000,
                "intanq": 0,
                "gdwlq": 0,
                "oancfy": 35000,
                "capxy": 5000,
                "calculated": {"free_cash_flow": 30000, "gross_margin": 0.45},
            },
            {
                "datadate": "2026-03-31",
                "fyearq": 2026,
                "fqtr": 2,
                "saleq": 110000,
                "niq": 28000,
                "atq": 374000,
                "intanq": 21334,
                "gdwlq": 0,
                "oancfy": 68000,
                "capxy": 9000,
                "calculated": {"free_cash_flow": 59000, "gross_margin": 0.45},
            },
        ],
        metadata={
            "data_contract_descriptor": {
                "id": "custom-investing.data_contract",
                "source_mode": "WRDS_ONLY",
                "gate_policy": {
                    "output_effects": {
                        "publication_blocked": {
                            "valuation_scope": "CUSTOM_PUBLICATION_HOLD",
                            "next_action": "custom_publication_hold",
                        }
                    }
                },
            }
        },
    )

    controls = build_investment_data_controls(state)
    gate = controls["data_gate"]

    assert gate["report_publication_allowed"] is False
    assert gate["valuation_scope"] == "CUSTOM_PUBLICATION_HOLD"
    assert gate["next_action"] == "custom_publication_hold"
