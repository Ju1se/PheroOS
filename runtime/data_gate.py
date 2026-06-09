from __future__ import annotations

from datetime import date
import re
from typing import Any

from runtime.legacy_data_gate_policy import (
    FORMAL_VALUATION_CONCLUSION_RE,
    HIGH_CONFIDENCE_RE,
    legacy_balance_sheet_jump_rule,
    legacy_balance_sheet_jump_rule_source,
    legacy_compustat_standard_filter_rule,
    legacy_compustat_standard_filter_rule_source,
    legacy_completeness_required_metrics,
    legacy_confidence_downgrade_rules,
    legacy_data_defect_memo_policy_source,
    legacy_data_defect_memo_policy,
    legacy_data_gate_required_data_rule,
    legacy_data_gate_required_matches,
    legacy_data_gate_required_policy_source,
    legacy_data_readiness_memo_policy,
    legacy_data_readiness_memo_policy_source,
    legacy_forbidden_claim_source,
    legacy_formula_validation_rule_source,
    legacy_gate_evidence_gap_rule_source,
    legacy_gate_metric_group_source,
    legacy_formal_valuation_blocked_output_effect,
    legacy_formula_validation_rule,
    legacy_forbidden_claims,
    legacy_gate_evidence_gap_rule,
    legacy_gate_score_policy_source,
    legacy_gate_score_policy,
    legacy_gate_metric_group,
    legacy_margin_basis_rule_source,
    legacy_margin_basis_rule,
    legacy_profile_policy,
    legacy_metric_alias_source,
    legacy_metric_aliases,
    legacy_metric_registry_annotation_source,
    legacy_metric_registry_entrypoint_warning_source,
    legacy_metric_registry_entrypoint_warning,
    legacy_metric_registry_policy_source,
    legacy_metric_registry_source_priority,
    legacy_metric_registry_usage_rules,
    legacy_metric_registry_warning_rule_source,
    legacy_metric_registry_annotation,
    legacy_metric_registry_warning_rule,
    legacy_profile_evidence_rule_source,
    legacy_profile_policy_source,
    legacy_profile_evidence_rule,
    legacy_profile_warning_rule_source,
    legacy_profile_warning_rule,
    legacy_source_mode_policy_source,
    legacy_source_rules,
    legacy_source_rule_source,
    legacy_source_mode_policy,
    legacy_source_validation_rule,
    legacy_wrds_only_claim_defect_memo_policy_source,
    legacy_wrds_only_claim_guardrail_source,
    legacy_wrds_only_confidence_guardrail_source,
    legacy_wrds_only_claim_guardrail_default_message,
    legacy_wrds_only_claim_defect_memo_policy,
    legacy_wrds_only_confidence_guardrail_rule,
    legacy_wrds_only_disallowed_claims,
    legacy_wrds_only_limitation_box,
    legacy_wrds_only_limitation_source,
    legacy_wrds_only_limitations,
    legacy_wrds_only_metric_requirement_source,
    legacy_wrds_only_metric_requirement_rule,
    legacy_wrds_only_output_effect_source,
    legacy_wrds_only_output_effect,
    legacy_wrds_only_required_fixes,
    legacy_wrds_only_required_period_source,
    legacy_wrds_only_required_period_rule,
    NON_GAAP_RE,
    QUARTER_TRIGGER_RE,
)
from runtime.swarm.data_gate_permissions import (
    blocked_conclusion_permissions,
    data_gate_conclusion_permission,
    is_publication_target,
    publication_conclusion_permission_target,
)
from runtime.swarm.source_policy_modes import canonical_wrds_only_source_mode, source_mode_is_wrds_only
from runtime.swarm.legacy_data_gate_permissions import (
    legacy_formal_valuation_allowed_field,
    legacy_formal_valuation_conclusion_target,
    legacy_publication_allowed_field,
)
from runtime.workflows.routing import workflow_descriptor_from_state
from runtime.wrds_planner import build_wrds_data_plan


DATA_CONTRACT_CLAIM_GUARDRAIL_SOURCE = "data_contract_claim_guardrail"
DATA_CONTRACT_CLAIM_DEFECT_MEMO_POLICY_SOURCE = "data_contract_claim_defect_memo_policy"
DATA_CONTRACT_BALANCE_SHEET_JUMP_SOURCE = "data_contract_balance_sheet_jump_rule"
DATA_CONTRACT_COMPUSTAT_STANDARD_FILTER_SOURCE = "data_contract_compustat_standard_filter_rule"
DATA_CONTRACT_CONFIDENCE_POLICY_SOURCE = "data_contract_confidence_policy"
DATA_CONTRACT_DEFECT_MEMO_POLICY_SOURCE = "data_contract_defect_memo_policy"
DATA_CONTRACT_DATA_GATE_REQUIRED_SOURCE = "data_contract_gate_required_policy"
DATA_CONTRACT_READINESS_MEMO_POLICY_SOURCE = "data_contract_readiness_memo_policy"
DATA_CONTRACT_FORBIDDEN_CLAIM_SOURCE = "data_contract_forbidden_claims"
DATA_CONTRACT_FORMULA_VALIDATION_SOURCE = "data_contract_formula_validation_rule"
DATA_CONTRACT_GATE_EVIDENCE_GAP_RULE_SOURCE = "data_contract_gate_evidence_gap_rule"
DATA_CONTRACT_GATE_SCORE_POLICY_SOURCE = "data_contract_gate_score_policy"
DATA_CONTRACT_GATE_METRIC_GROUP_SOURCE = "data_contract_gate_metric_group"
DATA_CONTRACT_MARGIN_BASIS_SOURCE = "data_contract_margin_basis_rule"
DATA_CONTRACT_METRIC_ALIAS_SOURCE = "data_contract_metric_aliases"
DATA_CONTRACT_METRIC_REGISTRY_POLICY_SOURCE = "data_contract_metric_registry_policy"
DATA_CONTRACT_METRIC_REQUIREMENT_SOURCE = "data_contract_metric_requirement"
DATA_CONTRACT_OUTPUT_EFFECT_SOURCE = "data_contract_output_effect"
DATA_CONTRACT_PROFILE_EVIDENCE_RULE_SOURCE = "data_contract_profile_evidence_rule"
DATA_CONTRACT_PROFILE_POLICY_SOURCE = "data_contract_profile_policy"
DATA_CONTRACT_PROFILE_WARNING_RULE_SOURCE = "data_contract_profile_warning_rule"
DATA_CONTRACT_REQUIRED_PERIOD_SOURCE = "data_contract_required_period_policy"
DATA_CONTRACT_SOURCE_MODE_LIMITATION_SOURCE = "data_contract_source_mode_limitations"
DATA_CONTRACT_SOURCE_MODE_POLICY_SOURCE = "data_contract_source_mode_policy"
DATA_CONTRACT_SOURCE_RULE_SOURCE = "data_contract_source_rules"

def build_investment_data_controls(state: dict[str, Any]) -> dict[str, Any]:
    contract = build_data_contract(state)
    registry = build_metric_registry_for_state(state, data_contract=contract)
    gate = evaluate_data_gate(state, data_contract=contract, metric_registry=registry)
    return {"data_contract": contract, "metric_registry": registry, "data_gate": gate}


def build_metric_registry_for_state(state: dict[str, Any], *, data_contract: dict[str, Any]) -> dict[str, Any]:
    workflow = workflow_descriptor_from_state(state)
    entrypoint = str(workflow.get("metric_registry_entrypoint") or "").strip()
    if not entrypoint:
        registry = build_metric_registry(state.get("wrds_result", {}), data_contract=data_contract)
        return attach_metric_registry_entrypoint_trace(
            registry,
            {
                "status": "default_runtime",
                "source": "runtime_metric_registry_default",
                "entrypoint": None,
            },
        )
    try:
        from runtime.capability_runtime import CapabilityEntrypointError
        from runtime.workflows.domain_execution import execute_workflow_entrypoint, manifest_for_workflow

        manifest = manifest_for_workflow(workflow, entrypoint_kind="metric_registry_entrypoint")
        output = execute_workflow_entrypoint(
            manifest=manifest,
            entrypoint=entrypoint,
            kind="metric_registry_entrypoint",
            state=state,
            result={"data_contract": data_contract},
            workflow=workflow,
        )
        registry = output.get("metric_registry") if isinstance(output.get("metric_registry"), dict) else {}
        if not registry:
            raise CapabilityEntrypointError(f"{manifest.id}.metric_registry_entrypoint did not return metric_registry")
        return attach_metric_registry_entrypoint_trace(
            registry,
            {
                "capability_id": manifest.id,
                "entrypoint": entrypoint,
                "status": "executed",
                "source": output.get("source") or "capability_metric_registry_entrypoint",
                "result_status": output.get("status"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        registry = build_metric_registry(state.get("wrds_result", {}), data_contract=data_contract)
        warning = legacy_metric_registry_entrypoint_warning()
        warning["error"] = str(exc)
        warning["policy_source"] = legacy_metric_registry_entrypoint_warning_source()
        registry.setdefault("warnings", []).append(warning)
        return attach_metric_registry_entrypoint_trace(
            registry,
            {
                "entrypoint": entrypoint,
                "status": "fallback_runtime",
                "source": "runtime_metric_registry_default",
                "error": str(exc),
            },
        )


def attach_metric_registry_entrypoint_trace(registry: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    trace = [*list(registry.get("metric_registry_entrypoint_trace") or []), event]
    return {**registry, "metric_registry_entrypoint_trace": trace}


def build_data_contract(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    descriptor = descriptor_data_contract(state)
    wrds_company = extract_wrds_company(state.get("wrds_result", {}))
    as_of_date = str(metadata.get("as_of_date") or date.today().isoformat())
    mode = str(metadata.get("mode") or "current").strip().lower() or "current"
    wrds_only_source_mode = canonical_wrds_only_source_mode()
    source_mode = (
        str(metadata.get("source_mode") or descriptor.get("source_mode") or wrds_only_source_mode).strip().upper()
        or wrds_only_source_mode
    )
    forbid_future = bool(metadata.get("forbidden_sources_after_as_of")) or mode == "historical"
    orchestration = state.get("orchestration") if isinstance(state.get("orchestration"), dict) else {}
    wrds_data_plan = build_wrds_data_plan(
        task=str(state.get("task") or ""),
        orchestration=orchestration,
        data_packages=orchestration.get("required_data_packages") if isinstance(orchestration, dict) else None,
    )
    descriptor_confidence_policy = descriptor.get("confidence_policy") if isinstance(descriptor.get("confidence_policy"), dict) else {}
    confidence_ceiling = str(
        descriptor_confidence_policy.get("maximum_confidence") or descriptor.get("confidence_ceiling") or ""
    ).strip().upper()
    maximum_confidence = confidence_ceiling or ("MEDIUM" if source_mode_is_wrds_only(source_mode) else "HIGH")
    confidence_policy_source = (
        DATA_CONTRACT_CONFIDENCE_POLICY_SOURCE
        if descriptor_confidence_policy or str(descriptor.get("confidence_ceiling") or "").strip()
        else legacy_wrds_only_confidence_guardrail_source()
    )
    confidence_downgrade_rules = (
        string_list(descriptor_confidence_policy.get("downgrade_to_low_when"))
        or list(legacy_confidence_downgrade_rules())
    )
    descriptor_metric_aliases = normalize_metric_aliases(descriptor.get("metric_aliases"))
    metric_aliases = descriptor_metric_aliases or dict(legacy_metric_aliases())
    descriptor_forbidden_claims = string_list(descriptor.get("forbidden_claims"))
    descriptor_source_mode_limitations = (
        descriptor.get("source_mode_limitations") if isinstance(descriptor.get("source_mode_limitations"), dict) else {}
    )
    descriptor_source_rules = source_rules_descriptor(descriptor.get("source_rules"))
    descriptor_source_validation_rules = (
        descriptor.get("source_validation_rules") if isinstance(descriptor.get("source_validation_rules"), dict) else {}
    )
    descriptor_source_mode_policies = normalize_source_mode_policies(descriptor.get("source_mode_policies"))
    source_mode_policy = source_mode_policy_for_mode(descriptor_source_mode_policies, source_mode)
    return {
        "status": "created",
        "contract_source": "capability_workflow_descriptor" if descriptor else "runtime_default",
        "descriptor_id": descriptor.get("id") or descriptor.get("contract_id"),
        "mode": mode,
        "source_mode": source_mode,
        "verification_level": str(source_mode_policy.get("verification_level") or "internal_consistency_only"),
        "allowed_sources": string_list(source_mode_policy.get("allowed_sources")),
        "source_mode_policy": source_mode_policy,
        "source_mode_policy_source": (
            DATA_CONTRACT_SOURCE_MODE_POLICY_SOURCE if descriptor_source_mode_policies else legacy_source_mode_policy_source()
        ),
        "disallowed_claims": descriptor_forbidden_claims or legacy_forbidden_claims(),
        "disallowed_claims_source": (
            DATA_CONTRACT_FORBIDDEN_CLAIM_SOURCE if descriptor_forbidden_claims else legacy_forbidden_claim_source()
        ),
        "claim_guardrails": descriptor.get("claim_guardrails") if isinstance(descriptor.get("claim_guardrails"), dict) else {},
        "metric_aliases": metric_aliases,
        "metric_aliases_source": DATA_CONTRACT_METRIC_ALIAS_SOURCE if descriptor_metric_aliases else legacy_metric_alias_source(),
        "completeness_required_metrics": string_list(descriptor.get("completeness_required_metrics"))
        or sorted(legacy_completeness_required_metrics()),
        "confidence_policy": {
            "maximum_confidence": maximum_confidence,
            "downgrade_to_low_when": confidence_downgrade_rules,
            "validation_issue": descriptor_confidence_policy.get("validation_issue")
            if isinstance(descriptor_confidence_policy.get("validation_issue"), dict)
            else legacy_wrds_only_confidence_guardrail_rule(),
            "validation_issue_source": (
                DATA_CONTRACT_CONFIDENCE_POLICY_SOURCE
                if isinstance(descriptor_confidence_policy.get("validation_issue"), dict)
                else legacy_wrds_only_confidence_guardrail_source()
            ),
            "source": confidence_policy_source,
        },
        "as_of_date": as_of_date,
        "forbidden_sources_after_as_of": forbid_future,
        "ticker": wrds_company.get("tic"),
        "company_name": wrds_company.get("conm"),
        "gvkey": wrds_company.get("gvkey"),
        "cik": wrds_company.get("cik"),
        "fiscal_year_end": "unknown",
        "research_questions": orchestration.get("research_questions") if isinstance(orchestration.get("research_questions"), list) else [],
        "required_data_packages": wrds_data_plan.get("data_packages", []),
        "required_contract_packages": string_list(descriptor.get("required_packages")),
        "profile_policies": descriptor.get("profile_policies") if isinstance(descriptor.get("profile_policies"), dict) else {},
        "gate_policy": descriptor.get("gate_policy") if isinstance(descriptor.get("gate_policy"), dict) else {},
        "metric_registry_policy": descriptor.get("metric_registry_policy")
        if isinstance(descriptor.get("metric_registry_policy"), dict)
        else {},
        "metric_registry_policy_source": (
            DATA_CONTRACT_METRIC_REGISTRY_POLICY_SOURCE
            if isinstance(descriptor.get("metric_registry_policy"), dict)
            else legacy_metric_registry_policy_source()
        ),
        "source_mode_limitations": descriptor_source_mode_limitations,
        "source_mode_limitations_source": (
            DATA_CONTRACT_SOURCE_MODE_LIMITATION_SOURCE if descriptor_source_mode_limitations else legacy_wrds_only_limitation_source()
        ),
        "wrds_data_plan": wrds_data_plan,
        "required_actual_periods": wrds_data_plan.get("required_actual_periods", {}),
        "source_rules": descriptor_source_rules or dict(legacy_source_rules()),
        "source_rules_source": DATA_CONTRACT_SOURCE_RULE_SOURCE if descriptor_source_rules else legacy_source_rule_source(),
        "source_validation_rules": descriptor_source_validation_rules,
        "source_validation_rules_source": (
            DATA_CONTRACT_SOURCE_RULE_SOURCE if descriptor_source_validation_rules else legacy_source_rule_source()
        ),
    }


def descriptor_data_contract(state: dict[str, Any]) -> dict[str, Any]:
    direct = state.get("data_contract_descriptor") if isinstance(state.get("data_contract_descriptor"), dict) else {}
    if direct:
        return direct
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    direct = metadata.get("data_contract_descriptor") if isinstance(metadata.get("data_contract_descriptor"), dict) else {}
    if direct:
        return direct
    workflow = workflow_descriptor_from_state(state)
    descriptor = workflow.get("data_contract") if isinstance(workflow.get("data_contract"), dict) else {}
    return descriptor


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def source_rules_descriptor(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    rules: dict[str, str] = {}
    for key, rule in value.items():
        key_text = str(key or "").strip()
        rule_text = str(rule or "").strip()
        if key_text and rule_text:
            rules[key_text] = rule_text
    return rules


def normalize_source_mode_policies(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    policies: dict[str, dict[str, Any]] = {}
    for mode, policy in value.items():
        mode_text = str(mode or "").strip().upper()
        if not mode_text or not isinstance(policy, dict):
            continue
        verification_level = str(policy.get("verification_level") or "").strip()
        allowed_sources = string_list(policy.get("allowed_sources"))
        normalized: dict[str, Any] = {}
        if verification_level:
            normalized["verification_level"] = verification_level
        if allowed_sources:
            normalized["allowed_sources"] = allowed_sources
        if normalized:
            policies[mode_text] = normalized
    return policies


def source_mode_policy_for_mode(policies: dict[str, dict[str, Any]], source_mode: str) -> dict[str, Any]:
    mode = str(source_mode or "").strip().upper()
    if mode in policies:
        return policies[mode]
    if "DEFAULT" in policies:
        return policies["DEFAULT"]
    return legacy_source_mode_policy(mode)


def normalize_metric_aliases(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    aliases: dict[str, str] = {}
    for alias, canonical in value.items():
        alias_text = normalize_metric_token(alias)
        canonical_text = normalize_metric_token(canonical)
        if alias_text and canonical_text:
            aliases[alias_text] = canonical_text
    return aliases


def metric_aliases_for_contract(data_contract: dict[str, Any] | None) -> dict[str, str]:
    if isinstance(data_contract, dict):
        aliases = normalize_metric_aliases(data_contract.get("metric_aliases"))
        if aliases:
            return aliases
    return dict(legacy_metric_aliases())


def profile_policy(data_contract: dict[str, Any], profile: str) -> dict[str, Any]:
    policies = data_contract.get("profile_policies") if isinstance(data_contract.get("profile_policies"), dict) else {}
    policy = policies.get(profile)
    return policy if isinstance(policy, dict) else {}


def profile_policy_with_source(data_contract: dict[str, Any], profile: str) -> tuple[dict[str, Any], str]:
    declared = profile_policy(data_contract, profile)
    if declared:
        return declared, DATA_CONTRACT_PROFILE_POLICY_SOURCE
    fallback = legacy_profile_policy(profile)
    return fallback, legacy_profile_policy_source()


def build_profile_record(
    data_contract: dict[str, Any],
    profile: str,
    *,
    severity: str,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy, source = profile_policy_with_source(data_contract, profile)
    return {
        "profile": profile,
        "severity": policy_text(policy, "severity", severity),
        "reason": policy_text(policy, "reason", ""),
        "policy_source": source,
        "metrics": metrics or {},
        "required_evidence": string_list(policy.get("required_evidence")),
        "policy": policy_text(policy, "policy", ""),
    }


def profile_evidence_gap(data_contract: dict[str, Any], profile: str, *, severity: str) -> dict[str, Any]:
    policy, source = profile_policy_with_source(data_contract, profile)
    gap = policy.get("evidence_gap") if isinstance(policy.get("evidence_gap"), dict) else {}
    return {
        "severity": str(gap.get("severity") or severity),
        "code": str(gap.get("code") or profile),
        "message": str(gap.get("message") or ""),
        "blocks_formal_valuation": gap.get("blocks_formal_valuation") is True,
        "required_evidence": string_list(gap.get("required_evidence")) or string_list(policy.get("required_evidence")),
        "policy_source": source,
        **({"blocks_forward_valuation": True} if gap.get("blocks_forward_valuation") is True else {}),
        **({"blocks_peer_valuation": True} if gap.get("blocks_peer_valuation") is True else {}),
    }


def gate_policy(data_contract: dict[str, Any]) -> dict[str, Any]:
    policy = data_contract.get("gate_policy") if isinstance(data_contract.get("gate_policy"), dict) else {}
    return policy


def metric_registry_policy(data_contract: dict[str, Any]) -> dict[str, Any]:
    policy = data_contract.get("metric_registry_policy") if isinstance(data_contract.get("metric_registry_policy"), dict) else {}
    return policy


def metric_registry_usage_rules(data_contract: dict[str, Any]) -> tuple[str, list[str]]:
    rules = string_list(metric_registry_policy(data_contract).get("usage_rules"))
    if rules:
        return DATA_CONTRACT_METRIC_REGISTRY_POLICY_SOURCE, rules
    return legacy_metric_registry_policy_source(), list(legacy_metric_registry_usage_rules())


def metric_registry_warning_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    warnings = metric_registry_policy(data_contract).get("warning_rules")
    rules = warnings if isinstance(warnings, dict) else {}
    rule = rules.get(name)
    if isinstance(rule, dict):
        return rule, DATA_CONTRACT_METRIC_REGISTRY_POLICY_SOURCE
    return legacy_metric_registry_warning_rule(name), legacy_metric_registry_warning_rule_source()


def metric_registry_metric_formula(
    data_contract: dict[str, Any],
    name: str,
    *,
    frequency: str = "",
    default: str = "",
) -> tuple[str, str]:
    annotations = metric_registry_policy(data_contract).get("metric_annotations")
    declared_annotations = annotations if isinstance(annotations, dict) else {}
    declared = declared_annotations.get(name)
    formula = formula_from_metric_annotation(declared if isinstance(declared, dict) else {}, frequency=frequency)
    if formula:
        return formula, DATA_CONTRACT_METRIC_REGISTRY_POLICY_SOURCE
    legacy = legacy_metric_registry_annotation(name)
    formula = formula_from_metric_annotation(legacy, frequency=frequency)
    if formula:
        return formula, legacy_metric_registry_annotation_source()
    return default, legacy_metric_registry_annotation_source()


def formula_from_metric_annotation(annotation: dict[str, Any], *, frequency: str = "") -> str:
    by_frequency = annotation.get("formula_by_frequency") if isinstance(annotation, dict) else {}
    if isinstance(by_frequency, dict) and frequency:
        formula = str(by_frequency.get(frequency) or "").strip()
        if formula:
            return formula
    return str(annotation.get("formula") or "").strip() if isinstance(annotation, dict) else ""


def gate_policy_section(data_contract: dict[str, Any], name: str) -> dict[str, Any]:
    policy = gate_policy(data_contract)
    section = policy.get(name) if isinstance(policy.get(name), dict) else {}
    return section


def gate_score_policy(data_contract: dict[str, Any], name: str) -> dict[str, Any]:
    policy, _source = gate_score_policy_with_source(data_contract, name)
    return policy


def gate_score_policy_with_source(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    scores = gate_policy_section(data_contract, "score_policy")
    section = scores.get(name) if isinstance(scores.get(name), dict) else {}
    fallback = legacy_gate_score_policy(name)
    if section:
        return {**fallback, **section}, DATA_CONTRACT_GATE_SCORE_POLICY_SOURCE
    return fallback, legacy_gate_score_policy_source()


def gate_output_effect(data_contract: dict[str, Any], name: str) -> dict[str, Any]:
    effect, _source = gate_output_effect_with_source(data_contract, name)
    return effect


def gate_output_effect_with_source(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    effects = gate_policy_section(data_contract, "output_effects")
    effect = effects.get(name) if isinstance(effects.get(name), dict) else {}
    if data_contract.get("contract_source") == "capability_workflow_descriptor" and effect:
        return effect, DATA_CONTRACT_OUTPUT_EFFECT_SOURCE
    return legacy_wrds_only_output_effect(name), legacy_wrds_only_output_effect_source()


def data_defect_memo_policy_with_source(data_contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    declared = gate_policy_section(data_contract, "defect_memo")
    fallback = legacy_data_defect_memo_policy()
    if declared:
        policy = {**fallback, **declared}
        fallback_fixes = fallback.get("required_fixes") if isinstance(fallback.get("required_fixes"), dict) else {}
        declared_fixes = declared.get("required_fixes") if isinstance(declared.get("required_fixes"), dict) else {}
        policy["required_fixes"] = {**fallback_fixes, **declared_fixes}
        return policy, DATA_CONTRACT_DEFECT_MEMO_POLICY_SOURCE
    return fallback, legacy_data_defect_memo_policy_source()


def data_readiness_memo_policy_with_source(data_contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    declared = gate_policy_section(data_contract, "readiness_memo")
    fallback = legacy_data_readiness_memo_policy()
    if declared:
        return {**fallback, **declared}, DATA_CONTRACT_READINESS_MEMO_POLICY_SOURCE
    return fallback, legacy_data_readiness_memo_policy_source()


def gate_metric_requirement_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = gate_policy_section(data_contract, "metric_requirement_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_METRIC_REQUIREMENT_SOURCE
    return legacy_wrds_only_metric_requirement_rule(name), legacy_wrds_only_metric_requirement_source()


def gate_required_period_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = gate_policy_section(data_contract, "required_period_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_REQUIRED_PERIOD_SOURCE
    return legacy_wrds_only_required_period_rule(name), legacy_wrds_only_required_period_source()


def gate_required_data_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = gate_policy_section(data_contract, "required_data_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_DATA_GATE_REQUIRED_SOURCE
    return legacy_data_gate_required_data_rule(name), legacy_data_gate_required_policy_source()


def formula_validation_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = gate_policy_section(data_contract, "formula_validation_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_FORMULA_VALIDATION_SOURCE
    return legacy_formula_validation_rule(name), legacy_formula_validation_rule_source()


def margin_basis_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = gate_policy_section(data_contract, "margin_basis_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_MARGIN_BASIS_SOURCE
    return legacy_margin_basis_rule(name), legacy_margin_basis_rule_source()


def compustat_standard_filter_rule(data_contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    rule = gate_policy_section(data_contract, "compustat_standard_filter_rules")
    if rule:
        return rule, DATA_CONTRACT_COMPUSTAT_STANDARD_FILTER_SOURCE
    return legacy_compustat_standard_filter_rule(), legacy_compustat_standard_filter_rule_source()


def balance_sheet_jump_rule(data_contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    rule = gate_policy_section(data_contract, "balance_sheet_jump_rules")
    if rule:
        return rule, DATA_CONTRACT_BALANCE_SHEET_JUMP_SOURCE
    return legacy_balance_sheet_jump_rule(), legacy_balance_sheet_jump_rule_source()


def source_validation_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = data_contract.get("source_validation_rules") if isinstance(data_contract.get("source_validation_rules"), dict) else {}
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_SOURCE_RULE_SOURCE
    return legacy_source_validation_rule(name), legacy_source_rule_source()


def gate_evidence_gap_rule(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    rules = gate_policy_section(data_contract, "evidence_gap_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    if rule:
        return rule, DATA_CONTRACT_GATE_EVIDENCE_GAP_RULE_SOURCE
    return legacy_gate_evidence_gap_rule(name), legacy_gate_evidence_gap_rule_source()


def build_gate_evidence_gap(
    data_contract: dict[str, Any],
    name: str,
    *,
    required_evidence: list[str],
    default_severity: str,
) -> dict[str, Any]:
    rule, source = gate_evidence_gap_rule(data_contract, name)
    return {
        "severity": policy_text(rule, "severity", default_severity),
        "code": policy_text(rule, "code", name),
        "message": policy_text(rule, "message", ""),
        "blocks_formal_valuation": rule.get("blocks_formal_valuation") is True,
        "blocks_forward_valuation": rule.get("blocks_forward_valuation") is not False,
        "required_evidence": string_list(rule.get("required_evidence")) or required_evidence,
        "policy_source": source,
    }


def gate_policy_metrics(data_contract: dict[str, Any], key: str) -> list[str]:
    metrics = string_list(gate_policy(data_contract).get(key))
    return metrics or legacy_gate_metric_group(key)


def gate_policy_metrics_source(data_contract: dict[str, Any], key: str) -> str:
    return DATA_CONTRACT_GATE_METRIC_GROUP_SOURCE if string_list(gate_policy(data_contract).get(key)) else legacy_gate_metric_group_source()


def profile_evidence_rule(data_contract: dict[str, Any], profile: str) -> dict[str, Any]:
    rules = gate_policy_section(data_contract, "profile_evidence_rules")
    rule = rules.get(profile) if isinstance(rules.get(profile), dict) else {}
    return rule


def profile_evidence_rule_with_source(data_contract: dict[str, Any], profile: str) -> tuple[dict[str, Any], str]:
    declared = profile_evidence_rule(data_contract, profile)
    if declared:
        return declared, DATA_CONTRACT_PROFILE_EVIDENCE_RULE_SOURCE
    return legacy_profile_evidence_rule(profile), legacy_profile_evidence_rule_source()


def profile_warning_rule(data_contract: dict[str, Any], name: str) -> dict[str, Any]:
    rules = gate_policy_section(data_contract, "profile_warning_rules")
    rule = rules.get(name) if isinstance(rules.get(name), dict) else {}
    return rule


def profile_warning_rule_with_source(data_contract: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    declared = profile_warning_rule(data_contract, name)
    if declared:
        return declared, DATA_CONTRACT_PROFILE_WARNING_RULE_SOURCE
    return legacy_profile_warning_rule(name), legacy_profile_warning_rule_source()


def policy_float(policy: dict[str, Any], key: str, default: float) -> float:
    value = numeric(policy.get(key), default)
    return default if value is None else value


def policy_number(policy: dict[str, Any], key: str, default: float) -> float:
    value = numeric(policy.get(key), default)
    return default if value is None else value


def policy_text(policy: dict[str, Any], key: str, default: str) -> str:
    value = str(policy.get(key) or "").strip()
    return value or default


def completeness_required_metrics(data_contract: dict[str, Any]) -> set[str]:
    metrics = string_list(data_contract.get("completeness_required_metrics"))
    aliases = metric_aliases_for_contract(data_contract)
    return {normalize_metric_name(metric, aliases=aliases) for metric in metrics} or set(legacy_completeness_required_metrics())


def large_margin_gap_warning(
    calculated: dict[str, Any],
    *,
    data_contract: dict[str, Any],
    period: str,
    frequency: str,
) -> dict[str, Any]:
    rule, rule_source = metric_registry_warning_rule(data_contract, "large_margin_gap")
    issue_key = "quarterly_issue" if frequency == "quarterly" else "annual_issue"
    instruction_key = "quarterly_instruction" if frequency == "quarterly" else "annual_instruction"
    return {
        "severity": policy_text(rule, "severity", "HIGH"),
        "period": period,
        "issue": policy_text(rule, issue_key, ""),
        "before_depreciation": calculated.get("gross_margin_before_depreciation") or calculated.get("gross_margin"),
        "after_depreciation": calculated.get("gross_margin_after_depreciation"),
        "instruction": policy_text(rule, instruction_key, ""),
        "policy_source": rule_source,
    }


def build_metric_registry(wrds_result: dict[str, Any], *, data_contract: dict[str, Any]) -> dict[str, Any]:
    financials = extract_company_financials(wrds_result)
    rows = financials.get("rows") if isinstance(financials.get("rows"), list) else []
    quarterly_rows = financials.get("quarterly_rows") if isinstance(financials.get("quarterly_rows"), list) else []
    metrics: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    raw_fields = build_raw_wrds_fields(financials)
    prior_quarter_by_period = prior_fiscal_quarter_by_period(quarterly_rows)
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = row_period(row)
        source = {
            "type": "wrds_compustat",
            "table": financials.get("table"),
            "company": financials.get("company"),
            "datadate": row.get("datadate"),
            "fyear": row.get("fyear"),
        }
        calculated = row.get("calculated") if isinstance(row.get("calculated"), dict) else {}
        reported_gross_margin_formula, reported_gross_margin_formula_source = metric_registry_metric_formula(
            data_contract,
            "reported_gross_margin_candidate",
            frequency="annual",
        )
        gross_margin_formula, gross_margin_formula_source = metric_registry_metric_formula(
            data_contract,
            "gross_margin",
            frequency="annual",
        )
        debt = numeric(row.get("dltt"), 0) + numeric(row.get("dlc"), 0)
        add_metric(metrics, "revenue", row.get("sale") if row.get("sale") is not None else row.get("revt"), period, source, "sale or revt")
        add_metric(
            metrics,
            "gross_profit_compustat",
            calculated.get("gross_profit"),
            period,
            source,
            "gp if available, otherwise sale - cogs",
            components={"gp": row.get("gp"), "sale": row.get("sale"), "cogs": row.get("cogs")},
            canonical=False,
        )
        add_metric(
            metrics,
            "gross_margin_before_depreciation",
            calculated.get("gross_margin_before_depreciation") or calculated.get("gross_margin"),
            period,
            source,
            "gross_profit_compustat / revenue",
            components={"gross_profit_compustat": calculated.get("gross_profit"), "revenue": row.get("sale")},
            canonical=False,
        )
        add_metric(
            metrics,
            "gross_margin_after_depreciation_candidate",
            calculated.get("gross_margin_after_depreciation"),
            period,
            source,
            "(gross_profit_compustat - depreciation_and_amortization) / revenue",
            components={
                "gross_profit_compustat": calculated.get("gross_profit"),
                "depreciation_and_amortization": row.get("dp"),
                "revenue": row.get("sale"),
            },
            canonical=False,
        )
        add_metric(
            metrics,
            "reported_gross_margin_candidate",
            calculated.get("reported_gross_margin_candidate") or calculated.get("gross_margin"),
            period,
            source,
            reported_gross_margin_formula,
            components={
                "gross_profit_compustat": calculated.get("gross_profit"),
                "depreciation_and_amortization": row.get("dp"),
                "revenue": row.get("sale"),
            },
            canonical=False,
            formula_policy_source=reported_gross_margin_formula_source,
        )
        add_metric(
            metrics,
            "gross_margin",
            calculated.get("reported_gross_margin_candidate") or calculated.get("gross_margin"),
            period,
            source,
            gross_margin_formula,
            components={
                "gross_profit_compustat": calculated.get("gross_profit"),
                "depreciation_and_amortization": row.get("dp"),
                "revenue": row.get("sale"),
            },
            formula_policy_source=gross_margin_formula_source,
        )
        if large_margin_gap(calculated):
            warnings.append(
                large_margin_gap_warning(calculated, data_contract=data_contract, period=period, frequency="annual")
            )
        add_metric(metrics, "operating_margin", calculated.get("operating_margin"), period, source, "ebit / revenue")
        add_metric(metrics, "net_income", row.get("ni") if row.get("ni") is not None else row.get("ib"), period, source, "ni or ib")
        add_metric(metrics, "diluted_eps", row.get("epsfi") if row.get("epsfi") is not None else row.get("epspi"), period, source, "epsfi or epspi")
        interest_expense = numeric(row.get("xint"))
        ebit = numeric(row.get("ebit"))
        ebitda = numeric(row.get("ebitda") if row.get("ebitda") is not None else row.get("oibdp"))
        assets = numeric(row.get("at"))
        goodwill = numeric(row.get("gdwl"))
        intangibles = numeric(row.get("intan"))
        dividends_common = numeric(row.get("dvc"), 0)
        dividends_preferred = numeric(row.get("dvp"), 0)
        share_repurchases = numeric(row.get("prstkc"), 0)
        share_issuance = numeric(row.get("sstk"), 0)
        add_metric(metrics, "interest_expense", row.get("xint"), period, source, "xint", canonical=False)
        add_metric(metrics, "interest_coverage", safe_divide_local(ebit, interest_expense), period, source, "ebit / xint", canonical=False)
        add_metric(metrics, "debt_to_ebitda", safe_divide_local(debt, ebitda), period, source, "(dltt + dlc) / ebitda_or_oibdp", components={"debt": debt, "ebitda": ebitda}, canonical=False)
        add_metric(metrics, "r_and_d", row.get("xrd"), period, source, "xrd", canonical=False)
        add_metric(metrics, "goodwill", row.get("gdwl"), period, source, "gdwl", canonical=False)
        add_metric(metrics, "intangibles", row.get("intan"), period, source, "intan", canonical=False)
        add_metric(metrics, "goodwill_to_assets", safe_divide_local(goodwill, assets), period, source, "gdwl / at", canonical=False)
        add_metric(metrics, "intangibles_to_assets", safe_divide_local(intangibles, assets), period, source, "intan / at", canonical=False)
        add_metric(metrics, "common_dividends", row.get("dvc"), period, source, "dvc", canonical=False)
        add_metric(metrics, "preferred_dividends", row.get("dvp"), period, source, "dvp", canonical=False)
        add_metric(metrics, "share_repurchases", row.get("prstkc"), period, source, "prstkc", canonical=False)
        add_metric(metrics, "share_issuance", row.get("sstk"), period, source, "sstk", canonical=False)
        add_metric(
            metrics,
            "net_capital_return",
            dividends_common + dividends_preferred + share_repurchases - share_issuance,
            period,
            source,
            "dvc + dvp + prstkc - sstk",
            components={
                "dvc": row.get("dvc"),
                "dvp": row.get("dvp"),
                "prstkc": row.get("prstkc"),
                "sstk": row.get("sstk"),
            },
            canonical=False,
        )
        add_metric(metrics, "split_adjustment_factor", row.get("ajex"), period, source, "ajex", canonical=False)
        add_metric(metrics, "operating_cash_flow", row.get("oancf"), period, source, "oancf")
        add_metric(metrics, "capex", row.get("capx"), period, source, "capx")
        add_metric(
            metrics,
            "free_cash_flow",
            calculated.get("free_cash_flow"),
            period,
            source,
            "operating_cash_flow - capex",
            components={"operating_cash_flow": row.get("oancf"), "capex": row.get("capx")},
        )
        add_metric(metrics, "cash", row.get("che"), period, source, "che")
        add_metric(metrics, "debt", debt, period, source, "dltt + dlc", components={"dltt": row.get("dltt"), "dlc": row.get("dlc")})
        add_metric(metrics, "shares_outstanding", row.get("csho"), period, source, "csho")
        add_working_capital_metrics(
            metrics,
            period,
            source,
            revenue=row.get("sale") if row.get("sale") is not None else row.get("revt"),
            cogs=row.get("cogs"),
            inventory=row.get("invt"),
            receivables=row.get("rect"),
            payables=row.get("ap"),
            days=365,
            basis="ending annual balance sheet value / annual income-statement flow",
        )
        price_source = {
            **source,
            "price_date": row.get("datadate"),
            "price_source": "Compustat prcc_f fiscal-year close price",
            "share_count_source": "Compustat csho",
            "financial_period": period,
        }
        add_metric(metrics, "market_price", row.get("prcc_f"), period, price_source, "prcc_f", canonical=False)

    for row in quarterly_rows:
        if not isinstance(row, dict):
            continue
        period = row_period(row)
        source = {
            "type": "wrds_compustat_quarterly",
            "table": financials.get("quarterly_table"),
            "company": financials.get("company"),
            "datadate": row.get("datadate"),
            "fyearq": row.get("fyearq"),
            "fqtr": row.get("fqtr"),
        }
        calculated = row.get("calculated") if isinstance(row.get("calculated"), dict) else {}
        reported_gross_margin_formula, reported_gross_margin_formula_source = metric_registry_metric_formula(
            data_contract,
            "reported_gross_margin_candidate",
            frequency="quarterly",
        )
        gross_margin_formula, gross_margin_formula_source = metric_registry_metric_formula(
            data_contract,
            "gross_margin",
            frequency="quarterly",
        )
        debt = numeric(row.get("dlttq"), 0) + numeric(row.get("dlcq"), 0)
        add_metric(metrics, "revenue", row.get("saleq") if row.get("saleq") is not None else row.get("revtq"), period, source, "saleq or revtq")
        add_metric(
            metrics,
            "gross_margin_before_depreciation",
            calculated.get("gross_margin_before_depreciation") or calculated.get("gross_margin"),
            period,
            source,
            "gross_profit_compustat / revenue",
            components={"gross_profit_compustat": calculated.get("gross_profit"), "revenue": row.get("saleq")},
            canonical=False,
        )
        add_metric(
            metrics,
            "gross_margin_after_depreciation_candidate",
            calculated.get("gross_margin_after_depreciation"),
            period,
            source,
            "(gross_profit_compustat - depreciation_and_amortization) / revenue",
            components={
                "gross_profit_compustat": calculated.get("gross_profit"),
                "depreciation_and_amortization": row.get("dpq"),
                "revenue": row.get("saleq"),
            },
            canonical=False,
        )
        add_metric(
            metrics,
            "reported_gross_margin_candidate",
            calculated.get("reported_gross_margin_candidate") or calculated.get("gross_margin"),
            period,
            source,
            reported_gross_margin_formula,
            components={
                "gross_profit_compustat": calculated.get("gross_profit"),
                "depreciation_and_amortization": row.get("dpq"),
                "revenue": row.get("saleq"),
            },
            canonical=False,
            formula_policy_source=reported_gross_margin_formula_source,
        )
        add_metric(
            metrics,
            "gross_margin",
            calculated.get("reported_gross_margin_candidate") or calculated.get("gross_margin"),
            period,
            source,
            gross_margin_formula,
            components={
                "gross_profit_compustat": calculated.get("gross_profit"),
                "depreciation_and_amortization": row.get("dpq"),
                "revenue": row.get("saleq"),
            },
            formula_policy_source=gross_margin_formula_source,
        )
        if large_margin_gap(calculated):
            warnings.append(
                large_margin_gap_warning(calculated, data_contract=data_contract, period=period, frequency="quarterly")
            )
        add_metric(metrics, "operating_margin", calculated.get("operating_margin"), period, source, "oiadpq / revenue")
        add_metric(metrics, "net_income", row.get("niq") if row.get("niq") is not None else row.get("ibq"), period, source, "niq or ibq")
        add_metric(metrics, "diluted_eps", row.get("epsfiq") if row.get("epsfiq") is not None else row.get("epspxq"), period, source, "epsfiq or epspxq")
        interest_expense = numeric(row.get("xintq"))
        operating_income = numeric(row.get("oiadpq"))
        ebitda = numeric(row.get("oibdpq"))
        assets = numeric(row.get("atq"))
        goodwill = numeric(row.get("gdwlq"))
        intangibles = numeric(row.get("intanq"))
        dividends_ytd = numeric(row.get("dvy"), 0)
        share_repurchases_ytd = numeric(row.get("prstkcy"), 0)
        share_issuance_ytd = numeric(row.get("sstky"), 0)
        add_metric(metrics, "interest_expense", row.get("xintq"), period, source, "xintq", canonical=False)
        add_metric(metrics, "interest_coverage", safe_divide_local(operating_income, interest_expense), period, source, "oiadpq / xintq", canonical=False)
        add_metric(metrics, "debt_to_ebitda", safe_divide_local(debt, ebitda), period, source, "(dlttq + dlcq) / oibdpq", components={"debt": debt, "ebitda": ebitda}, canonical=False)
        add_metric(metrics, "r_and_d", row.get("xrdq"), period, source, "xrdq", canonical=False)
        add_metric(metrics, "goodwill", row.get("gdwlq"), period, source, "gdwlq", canonical=False)
        add_metric(metrics, "intangibles", row.get("intanq"), period, source, "intanq", canonical=False)
        add_metric(metrics, "goodwill_to_assets", safe_divide_local(goodwill, assets), period, source, "gdwlq / atq", canonical=False)
        add_metric(metrics, "intangibles_to_assets", safe_divide_local(intangibles, assets), period, source, "intanq / atq", canonical=False)
        add_metric(metrics, "dividends_ytd", row.get("dvy"), period, source, "dvy (year-to-date)", canonical=False)
        add_metric(metrics, "share_repurchases_ytd", row.get("prstkcy"), period, source, "prstkcy (year-to-date)", canonical=False)
        add_metric(metrics, "share_issuance_ytd", row.get("sstky"), period, source, "sstky (year-to-date)", canonical=False)
        add_metric(
            metrics,
            "net_capital_return_ytd",
            dividends_ytd + share_repurchases_ytd - share_issuance_ytd,
            period,
            source,
            "dvy + prstkcy - sstky (year-to-date)",
            components={"dvy": row.get("dvy"), "prstkcy": row.get("prstkcy"), "sstky": row.get("sstky")},
            canonical=False,
        )
        add_metric(metrics, "split_adjustment_factor", row.get("ajexq"), period, source, "ajexq", canonical=False)
        add_metric(metrics, "operating_cash_flow", row.get("oancfy"), period, source, "oancfy (year-to-date)")
        add_metric(metrics, "capex", row.get("capxy"), period, source, "capxy (year-to-date)")
        prior_quarter = prior_quarter_by_period.get(period)
        operating_cash_flow_quarter = incremental_ytd_value(row, prior_quarter, "oancfy")
        capex_quarter = incremental_ytd_value(row, prior_quarter, "capxy")
        add_metric(
            metrics,
            "operating_cash_flow_quarter",
            operating_cash_flow_quarter,
            period,
            source,
            "oancfy minus prior fiscal-quarter oancfy; Q1 uses oancfy because YTD equals standalone quarter",
            components={"oancfy": row.get("oancfy"), "prior_oancfy": prior_quarter.get("oancfy") if isinstance(prior_quarter, dict) else None},
            canonical=False,
        )
        add_metric(
            metrics,
            "capex_quarter",
            capex_quarter,
            period,
            source,
            "capxy minus prior fiscal-quarter capxy; Q1 uses capxy because YTD equals standalone quarter",
            components={"capxy": row.get("capxy"), "prior_capxy": prior_quarter.get("capxy") if isinstance(prior_quarter, dict) else None},
            canonical=False,
        )
        add_metric(
            metrics,
            "free_cash_flow_quarter",
            operating_cash_flow_quarter - capex_quarter
            if operating_cash_flow_quarter is not None and capex_quarter is not None
            else None,
            period,
            source,
            "operating_cash_flow_quarter - capex_quarter",
            components={"operating_cash_flow_quarter": operating_cash_flow_quarter, "capex_quarter": capex_quarter},
            canonical=False,
        )
        add_metric(
            metrics,
            "free_cash_flow",
            calculated.get("free_cash_flow_ytd"),
            period,
            source,
            "operating_cash_flow_ytd - capex_ytd",
            components={"operating_cash_flow": row.get("oancfy"), "capex": row.get("capxy")},
        )
        add_metric(metrics, "cash", row.get("cheq"), period, source, "cheq")
        add_metric(metrics, "debt", debt, period, source, "dlttq + dlcq", components={"dlttq": row.get("dlttq"), "dlcq": row.get("dlcq")})
        add_metric(metrics, "shares_outstanding", row.get("cshoq"), period, source, "cshoq")
        add_working_capital_metrics(
            metrics,
            period,
            source,
            revenue=row.get("saleq") if row.get("saleq") is not None else row.get("revtq"),
            cogs=row.get("cogsq"),
            inventory=row.get("invtq"),
            receivables=row.get("rectq"),
            payables=row.get("apq"),
            days=90,
            basis="ending quarterly balance sheet value / standalone quarterly income-statement flow",
        )
        price_source = {
            **source,
            "price_date": row.get("datadate"),
            "price_source": "Compustat prccq quarterly close price",
            "share_count_source": "Compustat cshoq",
            "financial_period": period,
        }
        add_metric(metrics, "market_price", row.get("prccq"), period, price_source, "prccq", canonical=False)

    add_ttm_metrics(metrics, quarterly_rows, financials)
    add_crsp_market_metrics(metrics, financials)
    add_capital_iq_profile_metrics(metrics, financials)
    add_optionmetrics_security_metrics(metrics, financials)
    add_ibes_estimate_metrics(metrics, financials)
    add_compustat_segment_metrics(metrics, financials)
    add_peer_comparison_metrics(metrics, financials)
    metric_series = build_metric_series(metrics)
    annual_metric_series = build_metric_series(metrics, period_type="annual")
    quarterly_metric_series = build_metric_series(metrics, period_type="quarterly")
    ttm_metric_series = build_metric_series(metrics, period_type="ttm")
    usage_rules_source, usage_rules = metric_registry_usage_rules(data_contract)
    source_priority_source, source_priority = build_source_priority(metrics, data_contract=data_contract)
    return {
        "status": "created" if metrics else "empty",
        "as_of_date": data_contract.get("as_of_date"),
        "source_mode": data_contract.get("source_mode", canonical_wrds_only_source_mode()),
        "raw_fields": raw_fields,
        "derived_metrics": metrics,
        "metrics": metrics,
        "metric_series": metric_series,
        "annual_metric_series": annual_metric_series,
        "quarterly_metric_series": quarterly_metric_series,
        "ttm_metric_series": ttm_metric_series,
        "warnings": warnings,
        "source_priority": source_priority,
        "source_priority_source": source_priority_source,
        "usage_rules": usage_rules,
        "usage_rules_source": usage_rules_source,
    }


def evaluate_data_gate(
    state: dict[str, Any],
    *,
    data_contract: dict[str, Any],
    metric_registry: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = list(metric_registry.get("warnings") or [])
    decision_blockers: list[dict[str, Any]] = []
    wrds_result = state.get("wrds_result", {})
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}

    financials = extract_company_financials(wrds_result)
    rows = financials.get("rows") if isinstance(financials.get("rows"), list) else []
    quarterly_rows = financials.get("quarterly_rows") if isinstance(financials.get("quarterly_rows"), list) else []
    gate_requirement = data_gate_required_decision(state, data_contract=data_contract)
    if gate_requirement["required"] and not rows:
        required_data_rule, required_data_rule_source = gate_required_data_rule(data_contract, "company_financials")
        errors.append(
            {
                "severity": policy_text(required_data_rule, "severity", "CRITICAL"),
                "code": policy_text(required_data_rule, "code", "required_data_missing"),
                "message": policy_text(required_data_rule, "message", ""),
                "policy_source": required_data_rule_source,
            }
        )

    for issue in validate_company_identity(financials, data_contract=data_contract):
        errors.append(issue)
    for issue in validate_compustat_standard_filters(rows, quarterly_rows, data_contract=data_contract):
        warnings.append(issue)
    for issue in validate_margin_basis(rows, quarterly_rows, data_contract=data_contract):
        if issue.get("severity") == "CRITICAL":
            errors.append(issue)
        else:
            warnings.append(issue)
    for issue in validate_material_balance_sheet_jumps(rows, quarterly_rows, data_contract=data_contract):
        warnings.append(issue)
        if issue.get("blocks_report_publication"):
            decision_blockers.append(issue)

    as_of_date = str(data_contract.get("as_of_date") or "")
    if data_contract.get("forbidden_sources_after_as_of"):
        for row in rows:
            datadate = str(row.get("datadate") or "")
            if datadate and as_of_date and datadate > as_of_date:
                source_rule, source_rule_policy_source = source_validation_rule(
                    data_contract,
                    "financial_period_after_as_of",
                )
                errors.append(
                    {
                        "severity": policy_text(source_rule, "severity", "CRITICAL"),
                        "code": policy_text(source_rule, "code", "source_rule_violation"),
                        "message": policy_text(source_rule, "message", ""),
                        "policy_source": source_rule_policy_source,
                        "period": row_period(row),
                        "datadate": datadate,
                        "as_of_date": as_of_date,
                    }
                )

    for issue in validate_internal_formulas(rows, data_contract=data_contract):
        errors.append(issue)

    official_metrics = normalize_official_metrics(
        metadata.get("official_metrics") or metadata.get("company_reported_metrics"),
        data_contract=data_contract,
    )
    for issue in compare_official_metrics(metric_registry.get("metrics") or [], official_metrics, data_contract=data_contract):
        errors.append(issue)

    if official_reconciliation_required(state, rows, official_metrics):
        source_rule, source_rule_policy_source = source_validation_rule(
            data_contract,
            "missing_official_reconciliation",
        )
        warnings.append(
            {
                "severity": policy_text(source_rule, "severity", "MEDIUM"),
                "code": policy_text(source_rule, "code", "source_reconciliation_missing"),
                "message": policy_text(source_rule, "message", ""),
                "policy_source": source_rule_policy_source,
            }
        )

    source_mode = str(data_contract.get("source_mode") or canonical_wrds_only_source_mode()).upper()
    if source_mode_is_wrds_only(source_mode):
        source_rule, source_rule_policy_source = source_validation_rule(
            data_contract,
            "wrds_only_unverified",
        )
        warnings.append(
            {
                "severity": policy_text(source_rule, "severity", "MEDIUM"),
                "code": policy_text(source_rule, "code", "source_unverified"),
                "message": policy_text(source_rule, "message", ""),
                "policy_source": source_rule_policy_source,
            }
        )

    data_profiles = detect_company_data_profiles(
        financials,
        metric_registry,
        data_contract=data_contract,
    )
    profile_names = {str(profile.get("profile") or "") for profile in data_profiles if isinstance(profile, dict)}
    acquisition_heavy = "acquisition_intensive" in profile_names
    non_gaap_metrics = gate_policy_metrics(data_contract, "non_gaap_metrics")
    estimate_metrics = gate_policy_metrics(data_contract, "estimate_metrics")
    non_gaap_metric_source = gate_policy_metrics_source(data_contract, "non_gaap_metrics")
    estimate_metric_source = gate_policy_metrics_source(data_contract, "estimate_metrics")
    non_gaap_available = any(
        metric_registry_has_metric(metric_registry, metric_name, data_contract=data_contract)
        for metric_name in non_gaap_metrics
    )
    street_eps_available = any(
        metric_registry_has_metric(metric_registry, metric_name, data_contract=data_contract)
        for metric_name in estimate_metrics
    )
    evidence_gaps = evaluate_profile_evidence_gaps(
        data_profiles,
        metric_registry=metric_registry,
        data_contract=data_contract,
    )
    if gate_requirement["required"] and not street_eps_available:
        evidence_gaps.append(
            build_gate_evidence_gap(
                data_contract,
                "forward_estimates_missing",
                required_evidence=estimate_metrics,
                default_severity="MEDIUM",
            )
        )
    formal_valuation_allowed = not any(gap.get("blocks_formal_valuation") for gap in evidence_gaps)
    blocked_gap_scope = next(
        (
            str(gap.get("valuation_scope") or "").strip()
            for gap in evidence_gaps
            if gap.get("blocks_formal_valuation") and str(gap.get("valuation_scope") or "").strip()
        ),
        "",
    )
    if not formal_valuation_allowed:
        valuation_scope = blocked_gap_scope or policy_text(
            gate_output_effect(data_contract, legacy_formal_valuation_blocked_output_effect()),
            "valuation_scope",
            "",
        )
    else:
        valuation_scope = policy_text(
            gate_output_effect(data_contract, "passed"),
            "valuation_scope",
            "",
    )
    legacy_formal_allowed_field = legacy_formal_valuation_allowed_field()
    legacy_publication_field = legacy_publication_allowed_field()
    if acquisition_heavy and not non_gaap_available:
        acquisition_warning, acquisition_warning_source = profile_warning_rule_with_source(
            data_contract,
            "acquisition_intensive_missing_non_gaap",
        )
        acquisition_warning_blocks = acquisition_warning.get("blocks_formal_valuation", True) is not False
        warnings.append(
            {
                "severity": policy_text(acquisition_warning, "severity", "HIGH"),
                "code": policy_text(
                    acquisition_warning,
                    "code",
                    "acquisition_intensive_missing_non_gaap",
                ),
                "message": policy_text(acquisition_warning, "message", ""),
                "valuation_scope": valuation_scope,
                "policy_source": acquisition_warning_source,
                legacy_formal_allowed_field: not acquisition_warning_blocks,
            }
        )
    for gap in evidence_gaps:
        if gap.get("code") == "missing_non_gaap_eps_for_acquisition_heavy_company":
            continue
        warnings.append(gap)
        if gap.get("blocks_report_publication"):
            decision_blockers.append(gap)
    if decision_blockers:
        formal_valuation_allowed = False
        valuation_scope = policy_text(
            gate_output_effect(data_contract, "publication_blocked"),
            "valuation_scope",
            "",
        )

    blocking = bool(errors)
    status = compute_data_gate_status(
        blocking=blocking,
        source_mode=source_mode,
        official_metrics=official_metrics,
    )
    confidence = compute_gate_confidence(status=status, source_mode=source_mode, warnings=warnings)
    data_quality_policy, data_quality_score_source = gate_score_policy_with_source(data_contract, "data_quality")
    data_completeness_policy, data_completeness_score_source = gate_score_policy_with_source(
        data_contract,
        "data_completeness",
    )
    decision_readiness_policy, decision_readiness_score_source = gate_score_policy_with_source(
        data_contract,
        "decision_readiness",
    )
    quality_score = score_data_quality(errors, warnings, policy=data_quality_policy)
    data_completeness_score = score_data_completeness(
        metric_registry,
        required_metrics=completeness_required_metrics(data_contract),
        aliases=metric_aliases_for_contract(data_contract),
        policy=data_completeness_policy,
    )
    decision_readiness_score = score_decision_readiness(
        errors,
        warnings,
        evidence_gaps=evidence_gaps,
        decision_blockers=decision_blockers,
        policy=decision_readiness_policy,
    )
    report_publication_allowed = not blocking and not decision_blockers
    next_action = data_gate_next_action(
        data_contract,
        blocking=blocking,
        report_publication_allowed=report_publication_allowed,
        formal_valuation_allowed=formal_valuation_allowed,
    )
    return {
        "status": status,
        "data_gate_required": gate_requirement["required"],
        "data_gate_required_source": gate_requirement["source"],
        "data_gate_required_matches": gate_requirement["matches"],
        "source_mode": source_mode,
        "verification_level": data_contract.get("verification_level", "internal_consistency_only"),
        "blocking": blocking,
        "critical_errors": errors,
        "warnings": warnings,
        "decision_blockers": decision_blockers,
        "official_metrics_checked": official_metrics,
        "confidence": confidence,
        "limitations": wrds_only_limitations(data_contract) if source_mode_is_wrds_only(source_mode) else [],
        "data_profiles": data_profiles,
        "evidence_gaps": evidence_gaps,
        "conclusion_permissions": {
            legacy_formal_allowed_field: formal_valuation_allowed,
            "valuation_scope": valuation_scope,
            "pe_valuation_allowed": "negative_or_nonmeaningful_earnings" not in profile_names,
            "ev_ebitda_allowed": "financial_company" not in profile_names,
            "segment_claims_allowed": not any(gap.get("code") == "missing_segment_data" for gap in evidence_gaps),
            "market_timing_allowed": not any(gap.get("code") == "missing_crsp_market_data" for gap in evidence_gaps),
            "forward_valuation_allowed": not any(gap.get("blocks_forward_valuation") for gap in evidence_gaps),
            "peer_valuation_allowed": not any(gap.get("blocks_peer_valuation") for gap in evidence_gaps),
            legacy_publication_field: report_publication_allowed,
        },
        "acquisition_heavy": acquisition_heavy,
        "non_gaap_available": non_gaap_available,
        "non_gaap_metric_group_source": non_gaap_metric_source,
        "street_eps_available": street_eps_available,
        "estimate_metric_group_source": estimate_metric_source,
        "valuation_scope": valuation_scope,
        legacy_formal_allowed_field: formal_valuation_allowed,
        "quality_score": quality_score,
        "quality_score_source": data_quality_score_source,
        "data_completeness_score": data_completeness_score,
        "data_completeness_score_source": data_completeness_score_source,
        "decision_readiness_score": decision_readiness_score,
        "decision_readiness_score_source": decision_readiness_score_source,
        legacy_publication_field: report_publication_allowed,
        "next_action": next_action,
    }


def render_data_defect_memo(state: dict[str, Any]) -> str:
    gate = state.get("data_gate", {}) if isinstance(state.get("data_gate"), dict) else {}
    contract = state.get("data_contract", {}) if isinstance(state.get("data_contract"), dict) else {}
    registry = state.get("metric_registry", {}) if isinstance(state.get("metric_registry"), dict) else {}
    memo_policy, _memo_policy_source = data_defect_memo_policy_with_source(contract)
    source_mode = str(contract.get("source_mode") or "").upper()
    required_fixes_by_mode = memo_policy.get("required_fixes") if isinstance(memo_policy.get("required_fixes"), dict) else {}
    required_fixes = string_list(
        required_fixes_by_mode.get(source_mode)
        if source_mode in required_fixes_by_mode
        else required_fixes_by_mode.get("DEFAULT")
    )
    lines = [
        f"# {policy_text(memo_policy, 'title', 'Defect Report')}",
        "",
        policy_text(memo_policy, "intro", ""),
        "",
        f"- Task: `{state.get('task')}`",
        f"- Mode: `{contract.get('mode', 'current')}`",
        f"- Source mode: `{contract.get('source_mode', 'unknown')}`",
        f"- As-of date: `{contract.get('as_of_date', 'unknown')}`",
        f"- Company: `{contract.get('company_name') or 'unknown'}`",
        f"- Ticker: `{contract.get('ticker') or 'unknown'}`",
        f"- Quality score: `{gate.get('quality_score', 'unknown')}`",
        "",
        f"## {policy_text(memo_policy, 'blocking_issues_heading', 'Blocking Issues')}",
    ]
    errors = gate.get("critical_errors") if isinstance(gate.get("critical_errors"), list) else []
    if errors:
        for index, issue in enumerate(errors, start=1):
            lines.append(f"{index}. **{issue.get('code', 'data_error')}**: {issue.get('message', issue)}")
            details = {k: v for k, v in issue.items() if k not in {"code", "message", "severity"}}
            if details:
                lines.append(f"   - Details: `{details}`")
    else:
        lines.append(policy_text(memo_policy, "no_blocking_issue_text", "No issue details were recorded."))
    lines.append("")
    lines.append(f"## {policy_text(memo_policy, 'warnings_heading', 'Warnings')}")
    warnings = gate.get("warnings") if isinstance(gate.get("warnings"), list) else []
    if warnings:
        for index, issue in enumerate(warnings, start=1):
            lines.append(f"{index}. **{issue.get('code', issue.get('severity', 'warning'))}**: {issue.get('message') or issue.get('issue') or issue}")
    else:
        lines.append(policy_text(memo_policy, "no_warning_text", "No warnings were recorded."))
    lines.append("")
    lines.append(f"## {policy_text(memo_policy, 'required_fixes_heading', 'Required Fixes')}")
    lines.extend(f"{index}. {fix}" for index, fix in enumerate(required_fixes, start=1))
    if registry.get("warnings"):
        registry_warning_fix = policy_text(memo_policy, "registry_warning_fix", "")
        if registry_warning_fix:
            lines.append(f"{len(required_fixes) + 1}. {registry_warning_fix}")
    return "\n".join(lines)


def data_gate_required_decision(
    state: dict[str, Any],
    *,
    data_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    orchestration = state.get("orchestration") if isinstance(state.get("orchestration"), dict) else {}
    task_type = str(orchestration.get("task_type") or state.get("route") or "").lower()
    required = orchestration.get("required_agents") if isinstance(orchestration.get("required_agents"), dict) else {}
    contract = data_contract if isinstance(data_contract, dict) else {}
    if not contract:
        contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    if not contract:
        contract = build_data_contract(state)
    policy = gate_policy_section(contract, "required_when")
    matches: list[str] = []
    if policy:
        if policy.get("always") is True:
            matches.append("always")
        if policy.get("committee") is True and orchestration.get("committee"):
            matches.append("committee")
        task_types = {item.lower() for item in string_list(policy.get("task_types"))}
        if task_type and task_type in task_types:
            matches.append(f"task_type:{task_type}")
        routes = {item.lower() for item in string_list(policy.get("routes"))}
        route = str(state.get("route") or "").lower()
        if route and route in routes:
            matches.append(f"route:{route}")
        for agent in string_list(policy.get("required_agents")):
            if required.get(agent):
                matches.append(f"required_agent:{agent}")
        return {
            "required": bool(matches),
            "source": DATA_CONTRACT_DATA_GATE_REQUIRED_SOURCE,
            "matches": matches,
        }
    legacy_matches = legacy_data_gate_required_matches(orchestration, task_type=task_type)
    return {
        "required": bool(legacy_matches),
        "source": legacy_data_gate_required_policy_source(),
        "matches": legacy_matches,
    }


def data_gate_required(state: dict[str, Any], *, data_contract: dict[str, Any] | None = None) -> bool:
    return bool(data_gate_required_decision(state, data_contract=data_contract)["required"])


def data_gate_failed(state: dict[str, Any]) -> bool:
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    return bool(gate.get("blocking")) or str(gate.get("status") or "").upper() == "FAIL"


def data_gate_publication_blocked(state: dict[str, Any]) -> bool:
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    if not gate:
        return False
    if data_gate_failed(state):
        return True
    if any(
        is_publication_target(permission.get("canonical_target") or permission.get("target"))
        for permission in blocked_conclusion_permissions(gate)
    ):
        return True
    blockers = gate.get("decision_blockers")
    return isinstance(blockers, list) and bool(blockers)


def render_data_readiness_memo(state: dict[str, Any]) -> str:
    gate = state.get("data_gate", {}) if isinstance(state.get("data_gate"), dict) else {}
    contract = state.get("data_contract", {}) if isinstance(state.get("data_contract"), dict) else {}
    blockers = gate.get("decision_blockers") if isinstance(gate.get("decision_blockers"), list) else []
    warnings = gate.get("warnings") if isinstance(gate.get("warnings"), list) else []
    publication_target = publication_conclusion_permission_target(gate)
    publication_allowed = data_gate_conclusion_permission(gate, publication_target)
    memo_policy, memo_policy_source = data_readiness_memo_policy_with_source(contract)
    next_steps = string_list(memo_policy.get("required_next_steps") or memo_policy.get("next_steps"))
    lines = [
        f"# {policy_text(memo_policy, 'title', 'Data Readiness Memo')}",
        "",
        policy_text(memo_policy, "intro", ""),
        "",
        f"- Task: `{state.get('task')}`",
        f"- Source mode: `{contract.get('source_mode', gate.get('source_mode', 'unknown'))}`",
        f"- Company: `{contract.get('company_name') or 'unknown'}`",
        f"- Ticker: `{contract.get('ticker') or 'unknown'}`",
        f"- Data completeness score: `{gate.get('data_completeness_score', gate.get('quality_score', 'unknown'))}`",
        f"- Decision readiness score: `{gate.get('decision_readiness_score', 'unknown')}`",
        f"- Publication target: `{publication_target}`",
        f"- Publication allowed: `{publication_allowed}`",
        f"- Memo policy source: `{memo_policy_source}`",
        "",
        f"## {policy_text(memo_policy, 'publication_blockers_heading', 'Blockers')}",
    ]
    if blockers:
        for index, issue in enumerate(blockers, start=1):
            lines.append(f"{index}. **{issue.get('code', 'decision_blocker')}**: {issue.get('message') or issue.get('issue') or issue}")
            details = {k: v for k, v in issue.items() if k not in {"code", "message", "issue", "severity"}}
            if details:
                lines.append(f"   - Details: `{details}`")
    else:
        lines.append(
            policy_text(
                memo_policy,
                "no_blocker_text",
                "No blocker details were recorded.",
            )
        )
    lines.append("")
    lines.append(f"## {policy_text(memo_policy, 'warnings_heading', 'Warnings')}")
    for index, issue in enumerate(warnings[:10], start=1):
        lines.append(f"{index}. **{issue.get('code', issue.get('severity', 'warning'))}**: {issue.get('message') or issue.get('issue') or issue}")
    lines.append("")
    lines.append(f"## {policy_text(memo_policy, 'required_next_steps_heading', 'Next Steps')}")
    lines.extend(f"{index}. {step}" for index, step in enumerate(next_steps, start=1))
    return "\n".join(lines)


def wrds_only_mode(state: dict[str, Any]) -> bool:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    return (
        source_mode_is_wrds_only(contract.get("source_mode") or gate.get("source_mode"))
        or str(gate.get("status") or "").upper() == "PASS_WRDS_ONLY"
    )


def validate_wrds_only_report_claims(text: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    if not wrds_only_mode(state):
        return []
    content = str(text or "")
    errors: list[dict[str, Any]] = []
    for rule in wrds_only_claim_guardrail_rules(state):
        if claim_guardrail_rule_matches(rule, content):
            errors.append(
                {
                    "severity": rule.get("severity") or "CRITICAL",
                    "code": rule["code"],
                    "message": rule["message"],
                    "source": rule["source"],
                }
    )
    if HIGH_CONFIDENCE_RE.search(content):
        source, maximum_confidence, confidence_issue = wrds_only_confidence_policy_source(state)
        errors.append(
            {
                "severity": policy_text(confidence_issue, "severity", "CRITICAL"),
                "code": policy_text(confidence_issue, "code", "confidence_policy_violation"),
                "message": policy_text(confidence_issue, "message", ""),
                "source": source,
                "maximum_confidence": maximum_confidence,
                "validation_issue_source": str(
                    confidence_issue.get("source") or confidence_issue.get("policy_source") or source
                ),
            }
    )
    if NON_GAAP_RE.search(content) and not has_metric(state, "non_gaap_eps"):
        source, required_metrics, metric_requirement_rule = wrds_only_metric_requirement_source(
            state,
            "non_gaap_metrics",
        )
        errors.append(
            {
                "severity": policy_text(metric_requirement_rule, "severity", "CRITICAL"),
                "code": policy_text(metric_requirement_rule, "code", "metric_requirement_missing"),
                "message": policy_text(metric_requirement_rule, "message", ""),
                "source": source,
                "required_metrics": required_metrics,
            }
        )
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    if (
        data_gate_conclusion_permission(gate, legacy_formal_valuation_conclusion_target()) is False
        and FORMAL_VALUATION_CONCLUSION_RE.search(content)
    ):
        blocked_effect = legacy_formal_valuation_blocked_output_effect()
        source, valuation_scope, next_action, validation_issue = wrds_only_output_effect_source(
            state,
            blocked_effect,
        )
        errors.append(
            {
                "severity": policy_text(validation_issue, "severity", "CRITICAL"),
                "code": policy_text(validation_issue, "code", blocked_effect),
                "message": policy_text(validation_issue, "message", ""),
                "source": source,
                "valuation_scope": valuation_scope,
                "next_action": next_action,
            }
        )
    for match in QUARTER_TRIGGER_RE.finditer(content):
        q1, y1, y2, q2 = match.groups()
        quarter = q1 or q2
        year = y1 or y2
        period = f"FY{year}Q{quarter}"
        if not registry_has_period(state, period):
            source, required_periods, required_period_rule = wrds_only_required_period_source(state)
            errors.append(
                {
                    "severity": policy_text(required_period_rule, "severity", "CRITICAL"),
                    "code": policy_text(required_period_rule, "code", "required_period_missing"),
                    "message": policy_text(required_period_rule, "message", ""),
                    "period": period,
                    "source": source,
                    "required_periods": required_periods,
                }
            )
    return dedupe_issue_codes(errors)


def wrds_only_claim_guardrail_rules(state: dict[str, Any]) -> list[dict[str, Any]]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    guardrails = contract.get("claim_guardrails") if isinstance(contract.get("claim_guardrails"), dict) else {}
    declared = normalize_claim_guardrail_rules(
        guardrails.get("wrds_only_disallowed_claims") or guardrails.get("source_mode_disallowed_claims"),
        source=DATA_CONTRACT_CLAIM_GUARDRAIL_SOURCE,
    )
    if declared:
        return declared
    return [
        {
            "code": str(rule.get("code") or "wrds_only_disallowed_claim"),
            "message": str(rule.get("message") or legacy_wrds_only_claim_guardrail_default_message()),
            "severity": str(rule.get("severity") or "CRITICAL"),
            "compiled_patterns": [rule["pattern"]],
            "phrases": [],
            "source": legacy_wrds_only_claim_guardrail_source(),
        }
        for rule in legacy_wrds_only_disallowed_claims()
    ]


def wrds_only_confidence_policy_source(state: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    policy = contract.get("confidence_policy") if isinstance(contract.get("confidence_policy"), dict) else {}
    maximum_confidence = str(policy.get("maximum_confidence") or "MEDIUM").strip().upper() or "MEDIUM"
    issue = (
        policy.get("validation_issue")
        if isinstance(policy.get("validation_issue"), dict)
        else legacy_wrds_only_confidence_guardrail_rule()
    )
    source = str(policy.get("source") or "").strip()
    if source == DATA_CONTRACT_CONFIDENCE_POLICY_SOURCE:
        return DATA_CONTRACT_CONFIDENCE_POLICY_SOURCE, maximum_confidence, issue
    return legacy_wrds_only_confidence_guardrail_source(), maximum_confidence, issue


def wrds_only_metric_requirement_source(
    state: dict[str, Any],
    policy_key: str,
) -> tuple[str, list[str], dict[str, Any]]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    metrics = gate_policy_metrics(contract, policy_key)
    rule, rule_source = gate_metric_requirement_rule(contract, policy_key)
    if gate_policy_metrics_source(contract, policy_key) == DATA_CONTRACT_GATE_METRIC_GROUP_SOURCE and metrics:
        return DATA_CONTRACT_METRIC_REQUIREMENT_SOURCE, metrics, rule
    return rule_source, metrics, rule


def wrds_only_output_effect_source(state: dict[str, Any], effect_name: str) -> tuple[str, str, str, dict[str, Any]]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    gate = state.get("data_gate") if isinstance(state.get("data_gate"), dict) else {}
    effect, source = gate_output_effect_with_source(contract, effect_name)
    validation_issue = effect.get("validation_issue") if isinstance(effect.get("validation_issue"), dict) else {}
    valuation_scope = str(gate.get("valuation_scope") or effect.get("valuation_scope") or "")
    next_action = str(effect.get("next_action") or gate.get("next_action") or "")
    return source, valuation_scope, next_action, validation_issue


def wrds_only_required_period_source(state: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    periods = contract.get("required_actual_periods") if isinstance(contract.get("required_actual_periods"), dict) else {}
    rule, rule_source = gate_required_period_rule(contract, "quarterly_trigger")
    if contract.get("contract_source") == "capability_workflow_descriptor" and periods:
        return DATA_CONTRACT_REQUIRED_PERIOD_SOURCE, periods, rule
    return rule_source, periods, rule


def normalize_claim_guardrail_rules(value: Any, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rules: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        message = str(item.get("message") or "").strip()
        patterns = claim_guardrail_string_list(item.get("patterns") or item.get("pattern"))
        phrases = claim_guardrail_string_list(item.get("phrases") or item.get("keywords"))
        if not code or not message or (not patterns and not phrases):
            continue
        rules.append(
            {
                "code": code,
                "message": message,
                "severity": str(item.get("severity") or "CRITICAL").strip() or "CRITICAL",
                "patterns": patterns,
                "phrases": phrases,
                "source": source,
            }
        )
    return rules


def claim_guardrail_rule_matches(rule: dict[str, Any], content: str) -> bool:
    for pattern in rule.get("compiled_patterns") or []:
        if pattern.search(content):
            return True
    for pattern in claim_guardrail_string_list(rule.get("patterns")):
        try:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        except re.error:
            continue
    lowered = content.lower()
    return any(phrase.lower() in lowered for phrase in claim_guardrail_string_list(rule.get("phrases")))


def claim_guardrail_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def wrds_only_required_fixes(state: dict[str, Any]) -> tuple[str, list[str]]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    guardrails = contract.get("claim_guardrails") if isinstance(contract.get("claim_guardrails"), dict) else {}
    fixes = string_list(guardrails.get("wrds_only_required_fixes") or guardrails.get("required_fixes"))
    if fixes:
        return DATA_CONTRACT_CLAIM_GUARDRAIL_SOURCE, fixes
    return legacy_wrds_only_claim_guardrail_source(), list(legacy_wrds_only_required_fixes())


def wrds_only_claim_defect_memo_policy_with_source(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    guardrails = contract.get("claim_guardrails") if isinstance(contract.get("claim_guardrails"), dict) else {}
    declared = guardrails.get("wrds_only_defect_memo")
    if not isinstance(declared, dict):
        declared = guardrails.get("defect_memo")
    if not isinstance(declared, dict):
        declared = {}
    fallback = legacy_wrds_only_claim_defect_memo_policy()
    if declared:
        return {**fallback, **declared}, DATA_CONTRACT_CLAIM_DEFECT_MEMO_POLICY_SOURCE
    return fallback, legacy_wrds_only_claim_defect_memo_policy_source()


def apply_wrds_only_report_policy(text: str, state: dict[str, Any]) -> str:
    if not wrds_only_mode(state):
        return text
    errors = validate_wrds_only_report_claims(text, state)
    if errors:
        return render_wrds_only_claim_defect_memo(state, errors=errors, blocked_text=text)
    _limitation_source, limitation_box = wrds_only_limitation_box(state)
    if limitation_box in text:
        return text
    return f"{limitation_box}\n\n{text}"


def render_wrds_only_claim_defect_memo(
    state: dict[str, Any],
    *,
    errors: list[dict[str, Any]],
    blocked_text: str,
) -> str:
    required_fix_source, required_fixes = wrds_only_required_fixes(state)
    memo_policy, memo_policy_source = wrds_only_claim_defect_memo_policy_with_source(state)
    lines = [
        f"# {policy_text(memo_policy, 'title', 'Claim Guardrail Report')}",
        "",
        policy_text(memo_policy, "intro", ""),
        "",
        f"- Task: `{state.get('task')}`",
        f"- Source mode: `{canonical_wrds_only_source_mode()}`",
        f"- Memo policy source: `{memo_policy_source}`",
        f"- Required fixes source: `{required_fix_source}`",
        "",
        f"## {policy_text(memo_policy, 'blocking_claim_issues_heading', 'Blocking Claim Issues')}",
    ]
    for index, issue in enumerate(errors, start=1):
        lines.append(f"{index}. **{issue.get('code')}**: {issue.get('message')}")
        if issue.get("period"):
            lines.append(f"   - Period: `{issue.get('period')}`")
    lines.extend(
        [
            "",
            f"## {policy_text(memo_policy, 'required_fixes_heading', 'Required Fixes')}",
        ]
    )
    for index, fix in enumerate(required_fixes, start=1):
        lines.append(f"{index}. {fix}")
    lines.extend(
        [
            "",
            f"## {policy_text(memo_policy, 'blocked_draft_preview_heading', 'Blocked Draft Preview')}",
            str(blocked_text or "")[:1_500],
        ]
    )
    return "\n".join(lines)


def has_metric(state: dict[str, Any], metric_name: str) -> bool:
    registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    metrics = registry.get("metrics") if isinstance(registry.get("metrics"), list) else []
    data_contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    aliases = metric_aliases_for_contract(data_contract)
    target = normalize_metric_name(metric_name, aliases=aliases)
    return any(
        isinstance(metric, dict) and normalize_metric_name(metric.get("metric"), aliases=aliases) == target
        for metric in metrics
    )


def registry_has_period(state: dict[str, Any], period: str) -> bool:
    registry = state.get("metric_registry") if isinstance(state.get("metric_registry"), dict) else {}
    metrics = registry.get("metrics") if isinstance(registry.get("metrics"), list) else []
    return any(isinstance(metric, dict) and str(metric.get("period") or "").upper() == period.upper() for metric in metrics)


def dedupe_issue_codes(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for error in errors:
        key = (str(error.get("code") or ""), str(error.get("period") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(error)
    return unique


def official_reconciliation_required(
    state: dict[str, Any],
    rows: list[Any],
    official_metrics: list[dict[str, Any]],
) -> bool:
    if not rows or official_metrics:
        return False
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    if source_mode_is_wrds_only(metadata.get("source_mode") or canonical_wrds_only_source_mode()):
        return False
    if metadata.get("require_official_reconciliation"):
        return True
    return False


def compute_data_gate_status(
    *,
    blocking: bool,
    source_mode: str,
    official_metrics: list[dict[str, Any]],
) -> str:
    if blocking:
        return "FAIL"
    if not source_mode_is_wrds_only(source_mode) and official_metrics:
        return "PASS_VERIFIED"
    return "PASS_WRDS_ONLY"


def compute_gate_confidence(*, status: str, source_mode: str, warnings: list[dict[str, Any]]) -> str:
    if status == "FAIL":
        return "low"
    if source_mode_is_wrds_only(source_mode):
        if any(isinstance(warning, dict) and warning.get("blocks_report_publication") for warning in warnings):
            return "low"
        has_accounting_basis_warning = any(
            str(warning.get("severity") or "").upper() == "HIGH"
            and (
                "gross margin" in str(warning.get("issue") or warning.get("message") or "").lower()
                or "depreciation" in str(warning.get("issue") or warning.get("message") or "").lower()
            )
            for warning in warnings
            if isinstance(warning, dict)
        )
        return "low" if has_accounting_basis_warning else "medium"
    return "high"


def source_mode_limitation_policy(data_contract: dict[str, Any] | None, source_mode: str) -> dict[str, Any]:
    contract = data_contract if isinstance(data_contract, dict) else {}
    policies = contract.get("source_mode_limitations") if isinstance(contract.get("source_mode_limitations"), dict) else {}
    for key in (source_mode, source_mode.upper(), source_mode.lower()):
        policy = policies.get(key)
        if isinstance(policy, dict):
            return policy
    return {}


def wrds_only_limitation_box(state: dict[str, Any]) -> tuple[str, str]:
    contract = state.get("data_contract") if isinstance(state.get("data_contract"), dict) else {}
    policy = source_mode_limitation_policy(contract, canonical_wrds_only_source_mode())
    box = str(policy.get("box") or "").strip()
    if box:
        return DATA_CONTRACT_SOURCE_MODE_LIMITATION_SOURCE, box
    return legacy_wrds_only_limitation_source(), legacy_wrds_only_limitation_box()


def wrds_only_limitations(data_contract: dict[str, Any] | None = None) -> list[str]:
    policy = source_mode_limitation_policy(data_contract, canonical_wrds_only_source_mode())
    items = string_list(policy.get("items") or policy.get("limitations"))
    return items or list(legacy_wrds_only_limitations())


def metric_registry_has_metric(
    metric_registry: dict[str, Any],
    metric_name: str,
    *,
    data_contract: dict[str, Any] | None = None,
) -> bool:
    metrics = metric_registry.get("metrics") if isinstance(metric_registry.get("metrics"), list) else []
    aliases = metric_aliases_for_contract(data_contract)
    target = normalize_metric_name(metric_name, aliases=aliases)
    return any(
        isinstance(metric, dict) and normalize_metric_name(metric.get("metric"), aliases=aliases) == target
        for metric in metrics
    )


def detect_company_data_profiles(
    financials: dict[str, Any],
    metric_registry: dict[str, Any],
    *,
    data_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    company = financials.get("company") if isinstance(financials.get("company"), dict) else {}
    ticker = str(company.get("tic") or "").upper()
    name = str(company.get("conm") or "").lower()
    metrics = metric_registry.get("metrics") if isinstance(metric_registry.get("metrics"), list) else []
    profiles: list[dict[str, Any]] = []

    latest_goodwill_to_assets = latest_metric_value(metrics, "goodwill_to_assets")
    latest_intangibles_to_assets = latest_metric_value(metrics, "intangibles_to_assets")
    combined_intangible_ratio = sum(
        value
        for value in (latest_goodwill_to_assets, latest_intangibles_to_assets)
        if value is not None
    )
    acquisition_policy, acquisition_policy_source = profile_policy_with_source(data_contract, "acquisition_intensive")
    acquisition_tickers = {item.upper() for item in string_list(acquisition_policy.get("identity_tickers"))}
    acquisition_name_markers = [item.lower() for item in string_list(acquisition_policy.get("identity_name_markers"))]
    goodwill_threshold = policy_float(acquisition_policy, "goodwill_to_assets_threshold", 0.15)
    intangibles_threshold = policy_float(acquisition_policy, "intangibles_to_assets_threshold", 0.15)
    combined_threshold = policy_float(acquisition_policy, "combined_intangible_assets_threshold", 0.25)
    acquisition_requirements = string_list(acquisition_policy.get("required_evidence"))
    acquisition_valuation_policy = policy_text(acquisition_policy, "valuation_policy", "")
    acquisition_hint = ticker in acquisition_tickers or any(marker in name for marker in acquisition_name_markers)
    if (
        acquisition_hint
        or (latest_goodwill_to_assets is not None and latest_goodwill_to_assets >= goodwill_threshold)
        or (latest_intangibles_to_assets is not None and latest_intangibles_to_assets >= intangibles_threshold)
        or combined_intangible_ratio >= combined_threshold
    ):
        profiles.append(
            {
                "profile": "acquisition_intensive",
                "severity": policy_text(acquisition_policy, "severity", "HIGH"),
                "reason": policy_text(acquisition_policy, "reason", ""),
                "policy_source": acquisition_policy_source,
                "metrics": {
                    "goodwill_to_assets": latest_goodwill_to_assets,
                    "intangibles_to_assets": latest_intangibles_to_assets,
                    "combined_goodwill_intangibles_to_assets": round(combined_intangible_ratio, 4),
                    "identity_hint": acquisition_hint,
                },
                "required_evidence": acquisition_requirements,
                "policy": acquisition_valuation_policy,
            }
        )

    sic = str(company.get("sic") or "")
    naics = str(company.get("naics") or "")
    if sic.startswith("6") or naics.startswith("52"):
        financial_policy, financial_policy_source = profile_policy_with_source(data_contract, "financial_company")
        profiles.append(
            {
                "profile": "financial_company",
                "severity": policy_text(financial_policy, "severity", "HIGH"),
                "reason": policy_text(
                    financial_policy,
                    "reason",
                    "",
                ),
                "policy_source": financial_policy_source,
                "metrics": {"sic": sic, "naics": naics},
                "required_evidence": string_list(financial_policy.get("required_evidence")),
                "policy": policy_text(
                    financial_policy,
                    "policy",
                    "",
                ),
            }
        )

    latest_eps = latest_metric_value(metrics, "diluted_eps")
    latest_net_income = latest_metric_value(metrics, "net_income")
    if (latest_eps is not None and latest_eps <= 0) or (latest_net_income is not None and latest_net_income <= 0):
        earnings_policy, earnings_policy_source = profile_policy_with_source(data_contract, "negative_or_nonmeaningful_earnings")
        profiles.append(
            {
                "profile": "negative_or_nonmeaningful_earnings",
                "severity": policy_text(earnings_policy, "severity", "MEDIUM"),
                "reason": policy_text(
                    earnings_policy,
                    "reason",
                    "",
                ),
                "policy_source": earnings_policy_source,
                "metrics": {"diluted_eps": latest_eps, "net_income": latest_net_income},
                "required_evidence": string_list(earnings_policy.get("required_evidence")),
                "policy": policy_text(
                    earnings_policy,
                    "policy",
                    "",
                ),
            }
        )

    required_packages = set(data_contract.get("required_data_packages") or [])
    if "compustat_segments" in required_packages and not metric_registry_has_source(metric_registry, "wrds_compustat_segments"):
        profiles.append(
            build_profile_record(data_contract, "segment_data_requested_not_integrated", severity="MEDIUM")
        )
    if "crsp_market_data" in required_packages and not metric_registry_has_source(metric_registry, "wrds_crsp"):
        profiles.append(
            build_profile_record(data_contract, "crsp_market_data_requested_not_integrated", severity="MEDIUM")
        )
    if "peer_comparison" in required_packages and not metric_registry_has_source(metric_registry, "wrds_peer_comparison"):
        profiles.append(
            build_profile_record(data_contract, "peer_comparison_requested_not_integrated", severity="MEDIUM")
        )
    return profiles


def acquisition_profile_required_evidence(profiles: list[dict[str, Any]], data_contract: dict[str, Any]) -> list[str]:
    for profile in profiles:
        if not isinstance(profile, dict) or profile.get("profile") != "acquisition_intensive":
            continue
        requirements = string_list(profile.get("required_evidence"))
        if requirements:
            return requirements
    policy, _source = profile_policy_with_source(data_contract, "acquisition_intensive")
    return string_list(policy.get("required_evidence"))


def evaluate_profile_evidence_gaps(
    profiles: list[dict[str, Any]],
    *,
    metric_registry: dict[str, Any],
    data_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    profile_names = {str(profile.get("profile") or "") for profile in profiles if isinstance(profile, dict)}
    acquisition_rule, acquisition_rule_source = profile_evidence_rule_with_source(data_contract, "acquisition_intensive")
    acquisition_satisfying_metrics = (
        string_list(acquisition_rule.get("satisfying_metrics"))
        or [
            *gate_policy_metrics(data_contract, "non_gaap_metrics"),
            *gate_policy_metrics(data_contract, "estimate_metrics"),
        ]
    )
    acquisition_evidence_available = any(
        metric_registry_has_metric(metric_registry, metric_name, data_contract=data_contract)
        for metric_name in acquisition_satisfying_metrics
    )
    if "acquisition_intensive" in profile_names and not acquisition_evidence_available:
        acquisition_requirements = acquisition_profile_required_evidence(profiles, data_contract)
        gaps.append(
            {
                "severity": policy_text(acquisition_rule, "severity", "HIGH"),
                "code": policy_text(
                    acquisition_rule,
                    "missing_evidence_code",
                    "acquisition_intensive_missing_evidence",
                ),
                "message": policy_text(acquisition_rule, "message", ""),
                "blocks_formal_valuation": acquisition_rule.get("blocks_formal_valuation", True) is not False,
                "valuation_scope": policy_text(
                    acquisition_rule,
                    "valuation_scope_when_blocked",
                    policy_text(
                        gate_output_effect(data_contract, legacy_formal_valuation_blocked_output_effect()),
                        "valuation_scope",
                        "",
                    ),
                ),
                "required_evidence": acquisition_requirements,
                "policy_source": acquisition_rule_source,
            }
        )
    if "segment_data_requested_not_integrated" in profile_names:
        gaps.append(profile_evidence_gap(data_contract, "segment_data_requested_not_integrated", severity="MEDIUM"))
    if "crsp_market_data_requested_not_integrated" in profile_names:
        gaps.append(profile_evidence_gap(data_contract, "crsp_market_data_requested_not_integrated", severity="MEDIUM"))
    if "peer_comparison_requested_not_integrated" in profile_names:
        gaps.append(profile_evidence_gap(data_contract, "peer_comparison_requested_not_integrated", severity="MEDIUM"))
    return gaps


def data_gate_next_action(
    data_contract: dict[str, Any],
    *,
    blocking: bool,
    report_publication_allowed: bool,
    formal_valuation_allowed: bool,
) -> str:
    if blocking:
        return policy_text(
            gate_output_effect(data_contract, "blocking_errors"),
            "next_action",
            "",
        )
    if not report_publication_allowed:
        return policy_text(
            gate_output_effect(data_contract, "publication_blocked"),
            "next_action",
            "",
        )
    if not formal_valuation_allowed:
        return policy_text(
            gate_output_effect(data_contract, legacy_formal_valuation_blocked_output_effect()),
            "next_action",
            "",
        )
    return policy_text(
        gate_output_effect(data_contract, "passed"),
        "next_action",
        "",
    )


def metric_registry_has_source(metric_registry: dict[str, Any], source_type: str) -> bool:
    metrics = metric_registry.get("metrics") if isinstance(metric_registry.get("metrics"), list) else []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        source = metric.get("source") if isinstance(metric.get("source"), dict) else {}
        if str(source.get("type") or "") == source_type:
            return True
    return False


def latest_metric_value(metrics: list[dict[str, Any]], metric_name: str) -> float | None:
    target = normalize_metric_name(metric_name)
    candidates = [
        metric
        for metric in metrics
        if isinstance(metric, dict) and normalize_metric_name(metric.get("metric")) == target
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda metric: financial_period_sort_key(str(metric.get("period") or "")), reverse=True)
    return numeric(candidates[0].get("value"))


def build_raw_wrds_fields(financials: dict[str, Any]) -> list[dict[str, Any]]:
    raw_fields: list[dict[str, Any]] = []
    for frequency, rows_key, table_key in (
        ("annual", "rows", "table"),
        ("quarterly", "quarterly_rows", "quarterly_table"),
    ):
        rows = financials.get(rows_key) if isinstance(financials.get(rows_key), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            fields = {
                key: value
                for key, value in row.items()
                if key != "calculated" and not isinstance(value, (dict, list))
            }
            raw_fields.append(
                {
                    "frequency": frequency,
                    "period": row_period(row),
                    "table": financials.get(table_key),
                    "fields": fields,
                }
            )
    advanced_rows = (
        ("crsp_daily", "crsp_market_data", "daily_rows", "table"),
        ("ciq_company", "capital_iq_profile", "company_rows", "company_table"),
        ("ciq_symbol", "capital_iq_profile", "symbol_rows", "symbol_table"),
        ("ciq_description", "capital_iq_profile", "description_rows", "description_table"),
        ("optionmetrics_security", "optionmetrics_security", "security_rows", "table"),
        ("optionmetrics_borrow", "optionmetrics_security", "borrow_rows", "borrow_table"),
        ("optionmetrics_historical_volatility", "optionmetrics_security", "historical_volatility_rows", "historical_volatility_table"),
        ("ibes_summary", "ibes_estimates", "summary_rows", "summary_table"),
        ("ibes_actual", "ibes_estimates", "actual_rows", "actual_table"),
        ("segment", "compustat_segments", "rows", "table"),
        ("peer_comparison", "peer_comparison", "peer_rows", "table"),
    )
    for frequency, data_key, rows_key, table_key in advanced_rows:
        dataset = financials.get(data_key) if isinstance(financials.get(data_key), dict) else {}
        rows = dataset.get(rows_key) if isinstance(dataset.get(rows_key), list) else []
        for row in rows[:50]:
            if not isinstance(row, dict):
                continue
            raw_fields.append(
                {
                    "frequency": frequency,
                    "period": str(row.get("date") or row.get("fpedats") or row.get("pends") or row.get("datadate") or "unknown"),
                    "table": dataset.get(table_key),
                    "fields": {
                        key: value
                        for key, value in row.items()
                        if not isinstance(value, (dict, list))
                    },
                }
            )
    return raw_fields


def validate_company_identity(
    financials: dict[str, Any],
    *,
    data_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates = financials.get("candidates") if isinstance(financials.get("candidates"), list) else []
    if len(candidates) < 2:
        return []
    scored = [candidate for candidate in candidates if isinstance(candidate, dict)]
    scores = [numeric(candidate.get("match_score")) for candidate in scored]
    top_score = max([score for score in scores if score is not None], default=None)
    if top_score is None or top_score < 90:
        return []
    tied = [
        candidate
        for candidate in scored
        if numeric(candidate.get("match_score"), 0) == top_score
    ]
    distinct_gvkeys = {str(candidate.get("gvkey") or "") for candidate in tied if candidate.get("gvkey")}
    if len(distinct_gvkeys) <= 1:
        return []
    rule, rule_source = source_validation_rule(data_contract or {}, "ambiguous_company_identity")
    return [
        {
            "severity": policy_text(rule, "severity", "CRITICAL"),
            "code": policy_text(rule, "code", "source_identity_ambiguous"),
            "message": policy_text(rule, "message", ""),
            "policy_source": rule_source,
            "top_score": top_score,
            "candidates": [
                {
                    "gvkey": candidate.get("gvkey"),
                    "tic": candidate.get("tic"),
                    "conm": candidate.get("conm"),
                    "source": candidate.get("source"),
                }
                for candidate in tied
            ],
        }
    ]


def validate_compustat_standard_filters(
    annual_rows: list[Any],
    quarterly_rows: list[Any],
    *,
    data_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    rule, rule_source = compustat_standard_filter_rule(data_contract or {})
    allowed_values = rule.get("allowed_values") if isinstance(rule.get("allowed_values"), dict) else {}
    validation_issue = rule.get("validation_issue") if isinstance(rule.get("validation_issue"), dict) else {}
    for row in [*annual_rows, *quarterly_rows]:
        if not isinstance(row, dict):
            continue
        period = row_period(row)
        for field, allowed in allowed_values.items():
            if field not in row:
                continue
            value = row.get(field)
            if value not in allowed:
                warnings.append(
                    {
                        "severity": policy_text(validation_issue, "severity", "MEDIUM"),
                        "code": policy_text(validation_issue, "code", "non_standard_source_record"),
                        "message": policy_text(validation_issue, "message", ""),
                        "policy_source": rule_source,
                        "period": period,
                        "field": field,
                        "value": value,
                    }
                )
    return warnings


def validate_margin_basis(
    annual_rows: list[Any],
    quarterly_rows: list[Any],
    *,
    data_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    industry_profile = str((data_contract.get("wrds_data_plan") or {}).get("industry_profile") or "")
    is_capital_intensive_semiconductor = industry_profile == "semiconductor_memory"
    for row in [*annual_rows, *quarterly_rows]:
        if not isinstance(row, dict):
            continue
        calculated = row.get("calculated") if isinstance(row.get("calculated"), dict) else {}
        before = numeric(calculated.get("gross_margin_before_depreciation") or calculated.get("gross_margin"))
        after = numeric(calculated.get("gross_margin_after_depreciation"))
        candidate = numeric(calculated.get("reported_gross_margin_candidate"))
        revenue = numeric(row.get("sale") if row.get("sale") is not None else row.get("saleq"))
        depreciation = numeric(row.get("dp") if row.get("dp") is not None else row.get("dpq"))
        depreciation_intensity = None if revenue in (None, 0) or depreciation is None else depreciation / revenue
        if not is_capital_intensive_semiconductor or before is None or candidate is None:
            continue
        if depreciation_intensity is not None and depreciation_intensity > 0.10 and abs(candidate - before) <= 0.0001:
            rule, rule_source = margin_basis_rule(data_contract, "reported_margin_uses_before_depreciation")
            issues.append(
                {
                    "severity": policy_text(rule, "severity", "CRITICAL"),
                    "code": policy_text(rule, "code", "margin_basis_validation_failed"),
                    "message": policy_text(rule, "message", ""),
                    "policy_source": rule_source,
                    "period": row_period(row),
                    "depreciation_to_revenue": round(depreciation_intensity, 4),
                    "before_depreciation": before,
                    "after_depreciation": after,
                    "candidate": candidate,
                }
            )
        elif depreciation_intensity is not None and depreciation_intensity > 0.10:
            rule, rule_source = margin_basis_rule(data_contract, "high_depreciation_margin_basis")
            issues.append(
                {
                    "severity": policy_text(rule, "severity", "HIGH"),
                    "code": policy_text(rule, "code", "margin_basis_validation_warning"),
                    "message": policy_text(rule, "message", ""),
                    "policy_source": rule_source,
                    "period": row_period(row),
                    "depreciation_to_revenue": round(depreciation_intensity, 4),
                    "before_depreciation": before,
                    "after_depreciation": after,
                    "candidate": candidate,
                }
            )
    return issues


def validate_material_balance_sheet_jumps(
    annual_rows: list[Any],
    quarterly_rows: list[Any],
    *,
    data_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rule, rule_source = balance_sheet_jump_rule(data_contract or {})
    asset_threshold = policy_number(rule, "asset_threshold", 0.05)
    growth_threshold = policy_number(rule, "growth_threshold", 0.50)
    validation_issue = rule.get("validation_issue") if isinstance(rule.get("validation_issue"), dict) else {}
    for rows, fields, frequency in (
        (annual_rows, ("intan", "gdwl", "at"), "annual"),
        (quarterly_rows, ("intanq", "gdwlq", "atq"), "quarterly"),
    ):
        ordered = sorted(
            [row for row in rows if isinstance(row, dict) and row_period(row) != "unknown"],
            key=lambda row: financial_period_sort_key(row_period(row)),
        )
        for prior, current in zip(ordered, ordered[1:]):
            for field, label in ((fields[0], "intangibles"), (fields[1], "goodwill")):
                prior_value = numeric(prior.get(field), 0)
                current_value = numeric(current.get(field), 0)
                assets = numeric(current.get(fields[2]))
                if current_value is None or assets in (None, 0):
                    continue
                delta = current_value - (prior_value or 0)
                asset_ratio = abs(delta) / abs(assets)
                growth_ratio = None if not prior_value else abs(delta) / max(abs(prior_value), 1.0)
                jump_from_zero = (prior_value or 0) == 0 and current_value > 0 and asset_ratio >= asset_threshold
                material_growth = (
                    prior_value not in (None, 0)
                    and growth_ratio is not None
                    and growth_ratio >= growth_threshold
                    and asset_ratio >= asset_threshold
                )
                if not jump_from_zero and not material_growth:
                    continue
                format_values = {"label": label, "frequency": frequency}
                code_template = policy_text(validation_issue, "code_template", "material_balance_sheet_jump_unexplained")
                message_template = policy_text(validation_issue, "message_template", "")
                issues.append(
                    {
                        "severity": policy_text(validation_issue, "severity", "CRITICAL"),
                        "code": code_template.format(**format_values),
                        "message": message_template.format(**format_values),
                        "policy_source": rule_source,
                        "period": row_period(current),
                        "prior_period": row_period(prior),
                        "field": field,
                        "prior_value": prior_value,
                        "current_value": current_value,
                        "assets": assets,
                        "delta_to_assets": round(asset_ratio, 4),
                        "growth_ratio": None if growth_ratio is None else round(growth_ratio, 4),
                        "blocks_report_publication": validation_issue.get("blocks_report_publication", True) is not False,
                        "blocks_formal_valuation": validation_issue.get("blocks_formal_valuation", True) is not False,
                    }
                )
    return issues


def validate_internal_formulas(rows: list[Any], *, data_contract: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    contract = data_contract or {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sale = numeric(row.get("sale") if row.get("sale") is not None else row.get("revt"))
        if sale is not None and sale <= 0:
            rule, rule_source = formula_validation_rule(contract, "non_positive_revenue")
            errors.append(
                {
                    "severity": policy_text(rule, "severity", "CRITICAL"),
                    "code": policy_text(rule, "code", "formula_validation_failed"),
                    "message": policy_text(rule, "message", ""),
                    "policy_source": rule_source,
                    "period": row_period(row),
                    "value": sale,
                }
            )
        calculated = row.get("calculated") if isinstance(row.get("calculated"), dict) else {}
        fcf = calculated.get("free_cash_flow")
        oancf = numeric(row.get("oancf"))
        capx = numeric(row.get("capx"))
        if fcf is not None and oancf is not None and capx is not None and abs(float(fcf) - (oancf - capx)) > 0.1:
            rule, rule_source = formula_validation_rule(contract, "fcf_formula_mismatch")
            errors.append(
                {
                    "severity": policy_text(rule, "severity", "CRITICAL"),
                    "code": policy_text(rule, "code", "formula_validation_failed"),
                    "message": policy_text(rule, "message", ""),
                    "policy_source": rule_source,
                    "period": row_period(row),
                    "reported": fcf,
                    "expected": oancf - capx,
                }
            )
    return errors


def compare_official_metrics(
    registry_metrics: list[dict[str, Any]],
    official_metrics: list[dict[str, Any]],
    *,
    data_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not official_metrics:
        return errors
    aliases = metric_aliases_for_contract(data_contract)
    required_metrics = (
        completeness_required_metrics(data_contract)
        if isinstance(data_contract, dict)
        else set(legacy_completeness_required_metrics())
    )
    registry_index: dict[tuple[str, str], dict[str, Any]] = {}
    for metric in registry_metrics:
        if not isinstance(metric, dict) or not metric.get("canonical", True):
            continue
        key = (normalize_metric_name(metric.get("metric"), aliases=aliases), str(metric.get("period") or ""))
        registry_index[key] = metric
    for official in official_metrics:
        metric_name = normalize_metric_name(official.get("metric"), aliases=aliases)
        period = str(official.get("period") or "")
        if metric_name not in required_metrics:
            continue
        candidate = registry_index.get((metric_name, period))
        if not candidate:
            continue
        expected = numeric(official.get("value"))
        actual = numeric(candidate.get("value"))
        if expected is None or actual is None:
            continue
        tolerance = metric_tolerance(metric_name, expected)
        if abs(actual - expected) > tolerance:
            source_rule, source_rule_policy_source = source_validation_rule(
                data_contract or {},
                "official_metric_mismatch",
            )
            errors.append(
                {
                    "severity": policy_text(source_rule, "severity", "CRITICAL"),
                    "code": policy_text(source_rule, "code", "source_metric_mismatch"),
                    "message": policy_text(source_rule, "message", ""),
                    "policy_source": source_rule_policy_source,
                    "metric": metric_name,
                    "period": period,
                    "registry_value": actual,
                    "official_value": expected,
                    "tolerance": tolerance,
                    "source": official.get("source"),
                }
            )
    return errors


def normalize_official_metrics(value: Any, *, data_contract: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("metrics") if isinstance(value.get("metrics"), list) else [value]
    if not isinstance(value, list):
        return []
    aliases = metric_aliases_for_contract(data_contract)
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "metric": normalize_metric_name(item.get("metric"), aliases=aliases),
                "period": str(item.get("period") or ""),
                "value": item.get("value"),
                "source": item.get("source"),
            }
        )
    return normalized


def metric_tolerance(metric: str, expected: float) -> float:
    if "margin" in metric:
        return 0.02
    if metric.endswith("eps"):
        return 0.1
    return max(abs(expected) * 0.02, 0.1)


def score_data_quality(
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
) -> int:
    """Score internal data quality without confusing coverage and publication readiness.

    A run can have strong WRDS field coverage while still being unsuitable for a
    formal report because it lacks non-GAAP, segment, or official reconciliation
    evidence. Quality therefore uses capped severity-weighted penalties; the
    separate decision_readiness_score carries the harder publication blockers.
    """

    high = sum(1 for warning in warnings if str(warning.get("severity") or "").upper() == "HIGH")
    medium = sum(1 for warning in warnings if str(warning.get("severity") or "").upper() == "MEDIUM")
    low = sum(1 for warning in warnings if str(warning.get("severity") or "").upper() in {"LOW", "INFO"})
    unknown = max(0, len(warnings) - high - medium - low)
    score_policy = policy if isinstance(policy, dict) else {}
    score = 100.0
    score -= policy_number(score_policy, "critical_error_penalty", 0) * len(errors)
    score -= policy_number(score_policy, "high_warning_penalty", 0) * min(
        high,
        int(policy_number(score_policy, "high_warning_cap", high)),
    )
    score -= policy_number(score_policy, "medium_warning_penalty", 0) * min(
        medium,
        int(policy_number(score_policy, "medium_warning_cap", medium)),
    )
    score -= policy_number(score_policy, "low_warning_penalty", 0) * min(
        low,
        int(policy_number(score_policy, "low_warning_cap", low)),
    )
    score -= policy_number(score_policy, "unknown_warning_penalty", 0) * min(
        unknown,
        int(policy_number(score_policy, "unknown_warning_cap", unknown)),
    )
    return int(max(0, min(100, round(score))))


def score_data_completeness(
    metric_registry: dict[str, Any],
    *,
    required_metrics: set[str],
    aliases: dict[str, str] | None = None,
    policy: dict[str, Any] | None = None,
) -> int:
    metrics = metric_registry.get("metrics") if isinstance(metric_registry.get("metrics"), list) else []
    if not metrics:
        return 0
    present = {
        normalize_metric_name(metric.get("metric"), aliases=aliases)
        for metric in metrics
        if isinstance(metric, dict) and metric.get("value") is not None
    }
    required = {normalize_metric_name(metric, aliases=aliases) for metric in required_metrics}
    if not required:
        return 100
    required_score = round(100 * len(required & present) / len(required))
    score_policy = policy if isinstance(policy, dict) else {}
    period_bonus = 0.0
    series = metric_registry.get("metric_series") if isinstance(metric_registry.get("metric_series"), dict) else {}
    quarterly = metric_registry.get("quarterly_metric_series") if isinstance(metric_registry.get("quarterly_metric_series"), dict) else {}
    annual = metric_registry.get("annual_metric_series") if isinstance(metric_registry.get("annual_metric_series"), dict) else {}
    if annual:
        period_bonus += policy_number(score_policy, "annual_series_bonus", 0)
    if quarterly:
        period_bonus += policy_number(score_policy, "quarterly_series_bonus", 0)
    if any(str(period).startswith("TTM_") for values in series.values() if isinstance(values, list) for period in [item.get("period") for item in values if isinstance(item, dict)]):
        period_bonus += policy_number(score_policy, "ttm_series_bonus", 0)
    return int(max(0, min(100, round(required_score + period_bonus))))


def score_decision_readiness(
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    *,
    evidence_gaps: list[dict[str, Any]],
    decision_blockers: list[dict[str, Any]],
    policy: dict[str, Any] | None = None,
) -> int:
    score_policy = policy if isinstance(policy, dict) else {}
    score = 100.0
    score -= policy_number(score_policy, "critical_error_penalty", 0) * len(errors)
    score -= policy_number(score_policy, "decision_blocker_penalty", 0) * len(decision_blockers)
    score -= policy_number(score_policy, "high_evidence_gap_penalty", 0) * sum(
        1 for gap in evidence_gaps if str(gap.get("severity") or "").upper() == "HIGH"
    )
    score -= policy_number(score_policy, "medium_evidence_gap_penalty", 0) * sum(
        1 for gap in evidence_gaps if str(gap.get("severity") or "").upper() == "MEDIUM"
    )
    score -= policy_number(score_policy, "medium_warning_penalty", 0) * sum(
        1 for warning in warnings if str(warning.get("severity") or "").upper() == "MEDIUM"
    )
    return int(max(0, min(100, round(score))))


def add_metric(
    metrics: list[dict[str, Any]],
    metric: str,
    value: Any,
    period: str,
    source: dict[str, Any],
    formula: str,
    *,
    components: dict[str, Any] | None = None,
    canonical: bool = True,
    formula_policy_source: str | None = None,
) -> None:
    if value is None:
        return
    entry = {
        "metric": metric,
        "value": value,
        "period": period,
        "unit": infer_unit(metric),
        "source": source,
        "formula": formula,
        "components": components or {},
        "canonical": canonical,
        "confidence": "medium" if source.get("type") == "wrds_compustat" else "unknown",
    }
    if formula_policy_source:
        entry["formula_policy_source"] = formula_policy_source
    metrics.append(entry)


def add_working_capital_metrics(
    metrics: list[dict[str, Any]],
    period: str,
    source: dict[str, Any],
    *,
    revenue: Any,
    cogs: Any,
    inventory: Any,
    receivables: Any,
    payables: Any,
    days: int,
    basis: str,
) -> None:
    revenue_value = numeric(revenue)
    cogs_value = numeric(cogs)
    inventory_value = numeric(inventory)
    receivables_value = numeric(receivables)
    payables_value = numeric(payables)
    dio = safe_divide_local(inventory_value * days if inventory_value is not None else None, cogs_value)
    dso = safe_divide_local(receivables_value * days if receivables_value is not None else None, revenue_value)
    dpo = safe_divide_local(payables_value * days if payables_value is not None else None, cogs_value)
    cash_conversion_cycle = dio + dso - dpo if dio is not None and dso is not None and dpo is not None else None
    add_metric(metrics, "inventory", inventory_value, period, source, "inventory balance", canonical=False)
    add_metric(metrics, "accounts_receivable", receivables_value, period, source, "receivables balance", canonical=False)
    add_metric(metrics, "accounts_payable", payables_value, period, source, "accounts payable balance", canonical=False)
    add_metric(
        metrics,
        "days_inventory_outstanding",
        dio,
        period,
        source,
        f"inventory / cogs * {days}; {basis}",
        components={"inventory": inventory, "cogs": cogs},
        canonical=False,
    )
    add_metric(
        metrics,
        "days_sales_outstanding",
        dso,
        period,
        source,
        f"receivables / revenue * {days}; {basis}",
        components={"receivables": receivables, "revenue": revenue},
        canonical=False,
    )
    add_metric(
        metrics,
        "days_payables_outstanding",
        dpo,
        period,
        source,
        f"accounts_payable / cogs * {days}; {basis}",
        components={"accounts_payable": payables, "cogs": cogs},
        canonical=False,
    )
    add_metric(
        metrics,
        "cash_conversion_cycle",
        cash_conversion_cycle,
        period,
        source,
        "days_inventory_outstanding + days_sales_outstanding - days_payables_outstanding",
        components={
            "days_inventory_outstanding": dio,
            "days_sales_outstanding": dso,
            "days_payables_outstanding": dpo,
        },
        canonical=False,
    )


def add_ttm_metrics(metrics: list[dict[str, Any]], quarterly_rows: list[Any], financials: dict[str, Any]) -> None:
    rows = sorted(
        [row for row in quarterly_rows if isinstance(row, dict) and row_period(row) != "unknown"],
        key=lambda row: financial_period_sort_key(row_period(row)),
        reverse=True,
    )
    if len(rows) < 4:
        return
    latest_four = rows[:4]
    latest_row = latest_four[0]
    period = f"TTM_{row_period(latest_row)}"
    source = {
        "type": "wrds_compustat_ttm",
        "table": financials.get("quarterly_table"),
        "company": financials.get("company"),
        "datadate": latest_row.get("datadate"),
        "fyearq": latest_row.get("fyearq"),
        "fqtr": latest_row.get("fqtr"),
        "financial_period": period,
        "quarters": [row_period(row) for row in latest_four],
    }
    revenue = sum_row_values(latest_four, "saleq", "revtq")
    net_income = sum_row_values(latest_four, "niq", "ibq")
    operating_income = sum_row_values(latest_four, "oiadpq")
    ebitda = sum_row_values(latest_four, "ebitdaq", "oibdpq")
    prior_quarter_by_period = prior_fiscal_quarter_by_period(quarterly_rows)
    operating_cash_flow = sum_incremental_ytd_values(latest_four, prior_quarter_by_period, "oancfy")
    capex = sum_incremental_ytd_values(latest_four, prior_quarter_by_period, "capxy")
    free_cash_flow = operating_cash_flow - capex if operating_cash_flow is not None and capex is not None else None
    latest_price = numeric(latest_row.get("prccq"))
    latest_shares = numeric(latest_row.get("cshoq"))
    latest_debt = numeric(latest_row.get("dlttq"), 0) + numeric(latest_row.get("dlcq"), 0)
    latest_cash = numeric(latest_row.get("cheq"), 0)
    market_cap = latest_price * latest_shares if latest_price is not None and latest_shares is not None else None
    enterprise_value = market_cap + latest_debt - latest_cash if market_cap is not None else None
    add_metric(
        metrics,
        "ttm_revenue",
        revenue,
        period,
        source,
        "sum latest four quarters: saleq or revtq",
        components=ttm_components(latest_four, "saleq", "revtq"),
    )
    add_metric(
        metrics,
        "ttm_net_income",
        net_income,
        period,
        source,
        "sum latest four quarters: niq or ibq",
        components=ttm_components(latest_four, "niq", "ibq"),
    )
    add_metric(
        metrics,
        "ttm_operating_income",
        operating_income,
        period,
        source,
        "sum latest four quarters: oiadpq",
        components=ttm_components(latest_four, "oiadpq"),
    )
    add_metric(
        metrics,
        "ttm_ebitda",
        ebitda,
        period,
        source,
        "sum latest four quarters: ebitdaq or oibdpq",
        components=ttm_components(latest_four, "ebitdaq", "oibdpq"),
    )
    add_metric(
        metrics,
        "ttm_operating_cash_flow",
        operating_cash_flow,
        period,
        source,
        "sum latest four standalone quarters derived from oancfy YTD deltas",
        components=ttm_ytd_components(latest_four, prior_quarter_by_period, "oancfy"),
    )
    add_metric(
        metrics,
        "ttm_capex",
        capex,
        period,
        source,
        "sum latest four standalone quarters derived from capxy YTD deltas",
        components=ttm_ytd_components(latest_four, prior_quarter_by_period, "capxy"),
    )
    add_metric(
        metrics,
        "ttm_free_cash_flow",
        free_cash_flow,
        period,
        source,
        "ttm_operating_cash_flow - ttm_capex",
        components={"ttm_operating_cash_flow": operating_cash_flow, "ttm_capex": capex},
    )
    add_metric(
        metrics,
        "ttm_market_cap",
        market_cap,
        period,
        {**source, "price_date": latest_row.get("datadate"), "price_source": "Compustat prccq", "share_count_source": "Compustat cshoq"},
        "latest quarter price * latest quarter shares",
        components={"market_price": latest_price, "shares_outstanding": latest_shares},
    )
    add_metric(
        metrics,
        "ttm_enterprise_value",
        enterprise_value,
        period,
        {**source, "price_date": latest_row.get("datadate"), "price_source": "Compustat prccq", "share_count_source": "Compustat cshoq"},
        "market_cap + latest debt - latest cash",
        components={"market_cap": market_cap, "debt": latest_debt, "cash": latest_cash},
    )
    if market_cap is not None and net_income not in (None, 0):
        add_metric(
            metrics,
            "ttm_pe",
            market_cap / net_income,
            period,
            source,
            "ttm_market_cap / ttm_net_income",
            components={"market_cap": market_cap, "ttm_net_income": net_income},
        )
    if enterprise_value is not None and ebitda not in (None, 0):
        add_metric(
            metrics,
            "ttm_ev_ebitda",
            enterprise_value / ebitda,
            period,
            source,
            "ttm_enterprise_value / ttm_ebitda",
            components={"enterprise_value": enterprise_value, "ttm_ebitda": ebitda},
        )
    if enterprise_value is not None and revenue not in (None, 0):
        add_metric(
            metrics,
            "ttm_ev_revenue",
            enterprise_value / revenue,
            period,
            source,
            "ttm_enterprise_value / ttm_revenue",
            components={"enterprise_value": enterprise_value, "ttm_revenue": revenue},
        )
    if enterprise_value is not None and free_cash_flow not in (None, 0):
        add_metric(
            metrics,
            "ttm_ev_fcf",
            enterprise_value / free_cash_flow,
            period,
            source,
            "ttm_enterprise_value / ttm_free_cash_flow",
            components={"enterprise_value": enterprise_value, "ttm_free_cash_flow": free_cash_flow},
        )
    if market_cap is not None and free_cash_flow is not None:
        add_metric(
            metrics,
            "ttm_fcf_yield",
            safe_divide_local(free_cash_flow, market_cap),
            period,
            source,
            "ttm_free_cash_flow / ttm_market_cap",
            components={"ttm_free_cash_flow": free_cash_flow, "market_cap": market_cap},
        )


def add_crsp_market_metrics(metrics: list[dict[str, Any]], financials: dict[str, Any]) -> None:
    crsp = financials.get("crsp_market_data") if isinstance(financials.get("crsp_market_data"), dict) else {}
    latest = crsp.get("latest") if isinstance(crsp.get("latest"), dict) else {}
    if not latest:
        return
    period = str(latest.get("date") or "latest_crsp")
    source = {
        "type": "wrds_crsp",
        "table": crsp.get("table") or "crsp.dsf",
        "date": latest.get("date"),
        "permno": latest.get("permno"),
        "permco": latest.get("permco"),
        "identifier_map": crsp.get("identifier_map"),
    }
    price = numeric(latest.get("prc"))
    if price is not None:
        price = abs(price)
    shares_thousands = numeric(latest.get("shrout"))
    market_cap_millions = price * shares_thousands / 1000 if price is not None and shares_thousands is not None else None
    add_metric(metrics, "crsp_market_price", price, period, source, "abs(crsp.dsf.prc)", canonical=False)
    add_metric(metrics, "market_price", price, period, source, "abs(crsp.dsf.prc)")
    add_metric(
        metrics,
        "crsp_market_cap",
        market_cap_millions,
        period,
        source,
        "abs(prc) * shrout / 1000; CRSP shrout is in thousands",
        components={"price": price, "shrout_thousands": shares_thousands},
        canonical=False,
    )
    add_metric(metrics, "crsp_daily_return", latest.get("ret"), period, source, "ret", canonical=False)
    add_metric(metrics, "crsp_volume", latest.get("vol"), period, source, "vol", canonical=False)
    add_metric(metrics, "crsp_split_price_factor", latest.get("cfacpr"), period, source, "cfacpr", canonical=False)
    add_metric(metrics, "crsp_split_share_factor", latest.get("cfacshr"), period, source, "cfacshr", canonical=False)


def add_capital_iq_profile_metrics(metrics: list[dict[str, Any]], financials: dict[str, Any]) -> None:
    profile = financials.get("capital_iq_profile") if isinstance(financials.get("capital_iq_profile"), dict) else {}
    if not profile:
        return
    company_rows = profile.get("company_rows") if isinstance(profile.get("company_rows"), list) else []
    symbol_rows = profile.get("symbol_rows") if isinstance(profile.get("symbol_rows"), list) else []
    description_rows = profile.get("description_rows") if isinstance(profile.get("description_rows"), list) else []
    if not (company_rows or symbol_rows or description_rows):
        return
    company_row = company_rows[0] if company_rows and isinstance(company_rows[0], dict) else {}
    period = "latest_ciq_profile"
    source = {
        "type": "wrds_capital_iq",
        "table": profile.get("company_table") or "ciq_common.ciqcompany",
        "companyid": profile.get("companyid"),
        "gvkey": profile.get("gvkey"),
    }
    add_metric(metrics, "ciq_profile_available", 1, period, source, "Capital IQ profile row matched", canonical=False)
    add_metric(metrics, "ciq_symbol_count", len(symbol_rows), period, source, "count(ciq.wrds_ciqsymbol rows)", canonical=False)
    add_metric(
        metrics,
        "ciq_business_description_available",
        1 if description_rows else 0,
        period,
        {**source, "table": profile.get("description_table") or "ciq.ciqbusinessdescription"},
        "Capital IQ business description row available",
        canonical=False,
    )
    add_metric(metrics, "ciq_year_founded", company_row.get("yearfounded"), period, source, "ciqcompany.yearfounded", canonical=False)


def add_optionmetrics_security_metrics(metrics: list[dict[str, Any]], financials: dict[str, Any]) -> None:
    optionmetrics = financials.get("optionmetrics_security") if isinstance(financials.get("optionmetrics_security"), dict) else {}
    if not optionmetrics:
        return
    security_rows = optionmetrics.get("security_rows") if isinstance(optionmetrics.get("security_rows"), list) else []
    borrow_rows = optionmetrics.get("borrow_rows") if isinstance(optionmetrics.get("borrow_rows"), list) else []
    volatility_rows = (
        optionmetrics.get("historical_volatility_rows")
        if isinstance(optionmetrics.get("historical_volatility_rows"), list)
        else []
    )
    if not (security_rows or borrow_rows or volatility_rows):
        return
    source = {
        "type": "wrds_optionmetrics",
        "table": optionmetrics.get("table") or "optionm.securd",
        "secid": optionmetrics.get("secid"),
        "ticker": optionmetrics.get("ticker"),
        "cusip": optionmetrics.get("cusip"),
    }
    add_metric(metrics, "optionmetrics_security_match", 1 if security_rows else 0, "latest_optionmetrics", source, "OptionMetrics securd row matched", canonical=False)
    if borrow_rows:
        row = borrow_rows[0] if isinstance(borrow_rows[0], dict) else {}
        add_metric(
            metrics,
            "optionmetrics_borrow_rate",
            row.get("borrowrate"),
            str(row.get("date") or "latest_optionmetrics_borrow"),
            {**source, "table": optionmetrics.get("borrow_table"), "days": row.get("days")},
            "latest accessible optionm.borrateYYYY.borrowrate, excluding WRDS missing sentinel values",
            canonical=False,
        )
    if volatility_rows:
        row = volatility_rows[0] if isinstance(volatility_rows[0], dict) else {}
        add_metric(
            metrics,
            "optionmetrics_historical_volatility",
            row.get("volatility"),
            str(row.get("date") or "latest_optionmetrics_historical_volatility"),
            {**source, "table": optionmetrics.get("historical_volatility_table"), "days": row.get("days")},
            "latest accessible optionm.hvoldYYYY.volatility nearest 30 days",
            canonical=False,
        )


def add_ibes_estimate_metrics(metrics: list[dict[str, Any]], financials: dict[str, Any]) -> None:
    ibes = financials.get("ibes_estimates") if isinstance(financials.get("ibes_estimates"), dict) else {}
    summary_rows = ibes.get("summary_rows") if isinstance(ibes.get("summary_rows"), list) else []
    actual_rows = ibes.get("actual_rows") if isinstance(ibes.get("actual_rows"), list) else []
    for row in summary_rows[:12]:
        if not isinstance(row, dict):
            continue
        period = ibes_period(row)
        source = {
            "type": "wrds_ibes",
            "table": ibes.get("summary_table") or "ibes.statsum_epsus",
            "ticker": row.get("ticker") or ibes.get("ticker"),
            "cusip": row.get("cusip") or ibes.get("cusip"),
            "statpers": row.get("statpers"),
            "fpedats": row.get("fpedats"),
            "measure": row.get("measure"),
            "fpi": row.get("fpi"),
        }
        add_metric(metrics, "street_eps", row.get("meanest"), period, source, "IBES statsum_epsus.meanest", canonical=False)
        add_metric(metrics, "ibes_mean_estimate", row.get("meanest"), period, source, "meanest", canonical=False)
        add_metric(metrics, "ibes_actual_eps", row.get("actual"), period, source, "actual", canonical=False)
        add_metric(metrics, "ibes_num_estimates", row.get("numest"), period, source, "numest", canonical=False)
    for row in actual_rows[:12]:
        if not isinstance(row, dict):
            continue
        period = ibes_period(row)
        source = {
            "type": "wrds_ibes",
            "table": ibes.get("actual_table") or "ibes.act_epsus",
            "ticker": row.get("ticker") or ibes.get("ticker"),
            "cusip": row.get("cusip") or ibes.get("cusip"),
            "anndats": row.get("anndats"),
            "pends": row.get("pends"),
            "measure": row.get("measure"),
        }
        add_metric(metrics, "ibes_actual_eps", row.get("value"), period, source, "IBES act_epsus.value", canonical=False)


def add_compustat_segment_metrics(metrics: list[dict[str, Any]], financials: dict[str, Any]) -> None:
    segments = financials.get("compustat_segments") if isinstance(financials.get("compustat_segments"), dict) else {}
    rows = segments.get("rows") if isinstance(segments.get("rows"), list) else []
    for row in rows[:50]:
        if not isinstance(row, dict):
            continue
        period = str(row.get("datadate") or "unknown_segment_period")
        source = {
            "type": "wrds_compustat_segments",
            "table": segments.get("table") or "compseg.wrds_segmerged",
            "gvkey": row.get("gvkey"),
            "datadate": row.get("datadate"),
            "stype": row.get("stype"),
            "sid": row.get("sid"),
            "segment_name": row.get("snms"),
        }
        add_metric(metrics, "segment_sales", row.get("sales"), period, source, "compseg sales", canonical=False)
        add_metric(
            metrics,
            "segment_operating_profit",
            row.get("ops") if row.get("ops") is not None else row.get("oiadps"),
            period,
            source,
            "ops or oiadps",
            canonical=False,
        )
        add_metric(metrics, "segment_assets", row.get("atlls"), period, source, "atlls", canonical=False)
        add_metric(metrics, "segment_capex", row.get("capxs"), period, source, "capxs", canonical=False)


def add_peer_comparison_metrics(metrics: list[dict[str, Any]], financials: dict[str, Any]) -> None:
    peers = financials.get("peer_comparison") if isinstance(financials.get("peer_comparison"), dict) else {}
    rows = peers.get("peer_rows") if isinstance(peers.get("peer_rows"), list) else []
    if not rows:
        return
    source_base = {
        "type": "wrds_peer_comparison",
        "table": peers.get("table") or "comp.funda",
        "candidate_table": peers.get("candidate_table") or "comp.names",
        "selection_basis": peers.get("selection_basis"),
    }
    add_metric(
        metrics,
        "peer_count",
        len(rows),
        "PEER_SET",
        source_base,
        "count(peer_rows with latest Compustat fundamentals)",
        canonical=False,
    )
    peer_pe_values: list[float] = []
    peer_ev_ebitda_values: list[float] = []
    peer_fcf_margin_values: list[float] = []
    for row in rows[:50]:
        if not isinstance(row, dict):
            continue
        period = str(row.get("fyear") and f"FY{row.get('fyear')}" or row.get("datadate") or "peer_latest")
        source = {
            **source_base,
            "peer_gvkey": row.get("peer_gvkey") or row.get("gvkey"),
            "peer_tic": row.get("peer_tic") or row.get("tic"),
            "peer_conm": row.get("peer_conm") or row.get("conm"),
            "datadate": row.get("datadate"),
            "fyear": row.get("fyear"),
        }
        revenue = numeric(row.get("sale") if row.get("sale") is not None else row.get("revt"))
        net_income = numeric(row.get("ni") if row.get("ni") is not None else row.get("ib"))
        ebitda = numeric(row.get("ebitda") if row.get("ebitda") is not None else row.get("oibdp"))
        operating_cash_flow = numeric(row.get("oancf"))
        capex = numeric(row.get("capx"))
        price = numeric(row.get("prcc_f"))
        shares = numeric(row.get("csho"))
        debt = numeric(row.get("dltt"), 0) + numeric(row.get("dlc"), 0)
        cash = numeric(row.get("che"), 0)
        market_cap = price * shares if price is not None and shares is not None else None
        enterprise_value = market_cap + debt - cash if market_cap is not None else None
        free_cash_flow = operating_cash_flow - capex if operating_cash_flow is not None and capex is not None else None
        peer_pe = safe_divide_local(market_cap, net_income)
        peer_ev_ebitda = safe_divide_local(enterprise_value, ebitda)
        peer_fcf_margin = safe_divide_local(free_cash_flow, revenue)
        if peer_pe is not None:
            peer_pe_values.append(peer_pe)
        if peer_ev_ebitda is not None:
            peer_ev_ebitda_values.append(peer_ev_ebitda)
        if peer_fcf_margin is not None:
            peer_fcf_margin_values.append(peer_fcf_margin)

        add_metric(metrics, "peer_revenue", revenue, period, source, "sale or revt", canonical=False)
        add_metric(metrics, "peer_net_income", net_income, period, source, "ni or ib", canonical=False)
        add_metric(metrics, "peer_market_cap", market_cap, period, source, "prcc_f * csho", components={"prcc_f": price, "csho": shares}, canonical=False)
        add_metric(
            metrics,
            "peer_enterprise_value",
            enterprise_value,
            period,
            source,
            "peer_market_cap + (dltt + dlc) - che",
            components={"market_cap": market_cap, "debt": debt, "cash": cash},
            canonical=False,
        )
        add_metric(metrics, "peer_pe", peer_pe, period, source, "peer_market_cap / peer_net_income", canonical=False)
        add_metric(metrics, "peer_ev_ebitda", peer_ev_ebitda, period, source, "peer_enterprise_value / peer_ebitda", canonical=False)
        add_metric(
            metrics,
            "peer_fcf_margin",
            peer_fcf_margin,
            period,
            source,
            "peer_free_cash_flow / peer_revenue",
            components={"operating_cash_flow": operating_cash_flow, "capex": capex, "revenue": revenue},
            canonical=False,
        )

    add_metric(metrics, "peer_median_pe", median_value(peer_pe_values), "PEER_SET", source_base, "median(peer_pe)", canonical=False)
    add_metric(metrics, "peer_median_ev_ebitda", median_value(peer_ev_ebitda_values), "PEER_SET", source_base, "median(peer_ev_ebitda)", canonical=False)
    add_metric(metrics, "peer_median_fcf_margin", median_value(peer_fcf_margin_values), "PEER_SET", source_base, "median(peer_fcf_margin)", canonical=False)


def ibes_period(row: dict[str, Any]) -> str:
    date_value = row.get("fpedats") or row.get("pends") or row.get("statpers") or row.get("anndats")
    return f"IBES_{date_value}" if date_value else "IBES_unknown"


def median_value(values: list[float]) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return clean[midpoint]
    return (clean[midpoint - 1] + clean[midpoint]) / 2


def build_source_priority(
    metrics: list[dict[str, Any]],
    *,
    data_contract: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    baseline = string_list(metric_registry_policy(data_contract or {}).get("source_priority"))
    policy_source = DATA_CONTRACT_METRIC_REGISTRY_POLICY_SOURCE if baseline else legacy_metric_registry_policy_source()
    priority = baseline or list(legacy_metric_registry_source_priority())
    seen = set(priority)
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_source = metric.get("source") if isinstance(metric.get("source"), dict) else {}
        source_type = str(metric_source.get("type") or "")
        if source_type and source_type not in seen:
            seen.add(source_type)
            priority.append(source_type)
    return policy_source, priority


def sum_row_values(rows: list[dict[str, Any]], *fields: str) -> float | None:
    values: list[float] = []
    for row in rows:
        value = first_numeric(row, *fields)
        if value is None:
            return None
        values.append(value)
    return sum(values)


def first_numeric(row: dict[str, Any], *fields: str) -> float | None:
    for field in fields:
        value = numeric(row.get(field))
        if value is not None:
            return value
    return None


def ttm_components(rows: list[dict[str, Any]], *fields: str) -> dict[str, Any]:
    return {
        row_period(row): {
            field: row.get(field)
            for field in fields
            if row.get(field) is not None
        }
        for row in rows
    }


def ttm_ytd_components(
    rows: list[dict[str, Any]],
    prior_quarter_by_period: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for row in rows:
        period = row_period(row)
        prior = prior_quarter_by_period.get(period)
        components[period] = {
            field: row.get(field),
            f"prior_{field}": prior.get(field) if isinstance(prior, dict) else None,
            "standalone": incremental_ytd_value(row, prior, field),
        }
    return components


def sum_incremental_ytd_values(
    rows: list[dict[str, Any]],
    prior_quarter_by_period: dict[str, dict[str, Any]],
    field: str,
) -> float | None:
    values: list[float] = []
    for row in rows:
        value = incremental_ytd_value(row, prior_quarter_by_period.get(row_period(row)), field)
        if value is None:
            return None
        values.append(value)
    return sum(values)


def build_metric_series(metrics: list[dict[str, Any]], *, period_type: str | None = None) -> dict[str, list[dict[str, Any]]]:
    series_names = {
        "revenue",
        "operating_margin",
        "net_income",
        "diluted_eps",
        "operating_cash_flow",
        "capex",
        "free_cash_flow",
        "debt",
        "cash",
        "market_price",
        "gross_margin",
        "ttm_revenue",
        "ttm_net_income",
        "ttm_ebitda",
        "ttm_operating_cash_flow",
        "ttm_capex",
        "ttm_free_cash_flow",
        "ttm_pe",
        "ttm_ev_ebitda",
        "ttm_ev_revenue",
        "ttm_ev_fcf",
        "ttm_fcf_yield",
        "crsp_market_price",
        "crsp_market_cap",
        "crsp_daily_return",
        "crsp_volume",
        "street_eps",
        "ibes_mean_estimate",
        "ibes_actual_eps",
        "ibes_num_estimates",
        "segment_sales",
        "segment_operating_profit",
        "segment_assets",
        "segment_capex",
        "peer_count",
        "peer_revenue",
        "peer_net_income",
        "peer_market_cap",
        "peer_enterprise_value",
        "peer_pe",
        "peer_ev_ebitda",
        "peer_fcf_margin",
        "peer_median_pe",
        "peer_median_ev_ebitda",
        "peer_median_fcf_margin",
        "interest_expense",
        "interest_coverage",
        "debt_to_ebitda",
        "goodwill",
        "intangibles",
        "goodwill_to_assets",
        "intangibles_to_assets",
        "common_dividends",
        "share_repurchases",
        "share_issuance",
        "net_capital_return",
        "split_adjustment_factor",
        "operating_cash_flow_quarter",
        "capex_quarter",
        "free_cash_flow_quarter",
        "inventory",
        "accounts_receivable",
        "accounts_payable",
        "days_inventory_outstanding",
        "days_sales_outstanding",
        "days_payables_outstanding",
        "cash_conversion_cycle",
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("metric") or "")
        if name not in series_names:
            continue
        period = str(metric.get("period") or "")
        if period_type and metric_period_type(period) != period_type:
            continue
        grouped.setdefault(name, []).append(
            {
                "period": period,
                "value": metric.get("value"),
                "unit": metric.get("unit"),
                "formula": metric.get("formula"),
            }
        )
    for name, values in grouped.items():
        values.sort(key=lambda item: financial_period_sort_key(str(item.get("period") or "")), reverse=True)
        grouped[name] = values[:10]
    return grouped


def metric_period_type(period: str) -> str:
    text = str(period or "").upper()
    if text.startswith("TTM_"):
        return "ttm"
    if re.search(r"FY\s*\d{4}Q[1-4]", text):
        return "quarterly"
    return "annual"


def financial_period_sort_key(period: str) -> tuple[int, int, int]:
    text = str(period or "").upper()
    match = re.search(r"FY\s*(\d{4})(?:Q([1-4]))?", text)
    if match:
        return int(match.group(1)), int(match.group(2) or 0), 1
    match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return (0, 0, 0)


def infer_unit(metric: str) -> str:
    if metric in {
        "ttm_pe",
        "ttm_ev_ebitda",
        "ttm_ev_revenue",
        "ttm_ev_fcf",
        "interest_coverage",
        "debt_to_ebitda",
        "peer_pe",
        "peer_ev_ebitda",
        "peer_median_pe",
        "peer_median_ev_ebitda",
    }:
        return "multiple"
    if "margin" in metric or metric in {"roe", "roa", "goodwill_to_assets", "intangibles_to_assets", "ttm_fcf_yield"}:
        return "ratio"
    if metric in {"days_inventory_outstanding", "days_sales_outstanding", "days_payables_outstanding", "cash_conversion_cycle"}:
        return "days"
    if metric in {"diluted_eps", "market_price", "crsp_market_price", "street_eps", "ibes_mean_estimate", "ibes_actual_eps"}:
        return "currency_per_share"
    if metric in {"ibes_num_estimates", "peer_count"}:
        return "count"
    if metric == "shares_outstanding":
        return "millions"
    return "native_wrds_currency_millions"


def large_margin_gap(calculated: dict[str, Any]) -> bool:
    before = numeric(calculated.get("gross_margin_before_depreciation") or calculated.get("gross_margin"))
    after = numeric(calculated.get("gross_margin_after_depreciation"))
    return before is not None and after is not None and before - after >= 0.1


def extract_company_financials(wrds_result: Any) -> dict[str, Any]:
    if not isinstance(wrds_result, dict):
        return {}
    data = wrds_result.get("data") if isinstance(wrds_result.get("data"), dict) else {}
    financials = data.get("company_financials")
    return financials if isinstance(financials, dict) else {}


def extract_wrds_company(wrds_result: Any) -> dict[str, Any]:
    financials = extract_company_financials(wrds_result)
    company = financials.get("company")
    return company if isinstance(company, dict) else {}


def row_period(row: dict[str, Any]) -> str:
    fyearq = row.get("fyearq")
    fqtr = row.get("fqtr")
    if fyearq not in (None, "") and fqtr not in (None, ""):
        return f"FY{fyearq}Q{fqtr}"
    fyear = row.get("fyear")
    if fyear not in (None, ""):
        return f"FY{fyear}"
    return str(row.get("datadate") or "unknown")


def prior_fiscal_quarter_by_period(rows: list[Any]) -> dict[str, dict[str, Any]]:
    valid_rows = [
        row
        for row in rows
        if isinstance(row, dict) and numeric(row.get("fyearq")) is not None and numeric(row.get("fqtr")) is not None
    ]
    sorted_rows = sorted(valid_rows, key=lambda row: (int(numeric(row.get("fyearq")) or 0), int(numeric(row.get("fqtr")) or 0)))
    latest_by_fyear: dict[int, dict[str, Any]] = {}
    prior_by_period: dict[str, dict[str, Any]] = {}
    for row in sorted_rows:
        fyear = int(numeric(row.get("fyearq")) or 0)
        fqtr = int(numeric(row.get("fqtr")) or 0)
        prior = latest_by_fyear.get(fyear)
        if prior is not None and int(numeric(prior.get("fqtr")) or 0) == fqtr - 1:
            prior_by_period[row_period(row)] = prior
        latest_by_fyear[fyear] = row
    return prior_by_period


def incremental_ytd_value(row: dict[str, Any], prior_quarter: dict[str, Any] | None, field: str) -> float | None:
    current = numeric(row.get(field))
    if current is None:
        return None
    fqtr = int(numeric(row.get("fqtr")) or 0)
    if fqtr <= 1:
        return current
    if not isinstance(prior_quarter, dict):
        return None
    prior = numeric(prior_quarter.get(field))
    if prior is None:
        return None
    return current - prior


def normalize_metric_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text


def normalize_metric_name(value: Any, *, aliases: dict[str, str] | None = None) -> str:
    text = normalize_metric_token(value)
    active_aliases = aliases if aliases is not None else legacy_metric_aliases()
    return active_aliases.get(text, text)


def numeric(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().rstrip("%")) / (100 if str(value).strip().endswith("%") else 1)
    except ValueError:
        return default


def safe_divide_local(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator
