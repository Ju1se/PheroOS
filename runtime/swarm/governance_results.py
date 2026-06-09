from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from runtime.swarm.governance_contracts import GOVERNANCE_CONTRACTS, GovernanceContract
from runtime.swarm.legacy_quorum_targets import legacy_blocked_conclusion_targets_from_quorum_flags
from runtime.swarm.policing import blocking_target_for_violation
from runtime.swarm.target_registry import canonical_target


GovernanceStatus = Literal["pass", "warn", "block"]


@dataclass
class GovernanceResult:
    actor: str
    status: GovernanceStatus
    signals: list[dict[str, Any]] = field(default_factory=list)
    blocked_targets: list[str] = field(default_factory=list)
    required_caveats: list[str] = field(default_factory=list)
    writer_constraints: list[str] = field(default_factory=list)
    final_judge_checks: list[str] = field(default_factory=list)
    profile_updates: list[dict[str, Any]] = field(default_factory=list)
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    report_key: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "status": self.status,
            "signals": self.signals,
            "blocked_targets": self.blocked_targets,
            "required_caveats": self.required_caveats,
            "writer_constraints": self.writer_constraints,
            "final_judge_checks": self.final_judge_checks,
            "profile_updates": self.profile_updates,
            "trace_events": self.trace_events,
            "report_key": self.report_key,
            "summary": self.summary,
        }


def build_governance_results(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        result.to_dict()
        for contract in GOVERNANCE_CONTRACTS.values()
        for result in [result_from_contract(state, contract)]
    ]


def result_from_contract(state: dict[str, Any], contract: GovernanceContract) -> GovernanceResult:
    report = state.get(contract.report_key) if isinstance(state.get(contract.report_key), dict) else {}
    status = result_status(report)
    blocked_target_source = "not_blocking"
    if status == "block":
        blocked_targets, blocked_target_source = blocked_targets_for(contract, report, state=state)
        blocked_targets = sorted({canonical_target(target) for target in blocked_targets})
    else:
        blocked_targets = []
    required_caveats = required_caveats_for(contract, report)
    writer_constraints = writer_constraints_for(contract, report)
    final_judge_checks = final_judge_checks_for(contract, report)
    profile_updates = report.get("profile_updates") if isinstance(report.get("profile_updates"), list) else []
    return GovernanceResult(
        actor=contract.actor,
        report_key=contract.report_key,
        status=status,
        blocked_targets=blocked_targets,
        required_caveats=required_caveats,
        writer_constraints=writer_constraints,
        final_judge_checks=final_judge_checks,
        profile_updates=profile_updates,
        trace_events=[
            {
                "event_type": contract.trace_event,
                "actor": contract.actor,
                "target": governance_trace_target(contract, blocked_targets),
                "summary": summary_for(contract, report, status),
                "payload": {
                    "report_key": contract.report_key,
                    "status": status,
                    "blocked_targets": blocked_targets,
                    "blocked_target_source": blocked_target_source,
                    "contract_enforcement_targets": contract.enforcement_targets,
                },
            }
        ],
        summary=summary_for(contract, report, status),
    )


def governance_trace_target(contract: GovernanceContract, blocked_targets: list[str]) -> str:
    if blocked_targets:
        return ",".join(blocked_targets)
    return ",".join(contract.enforcement_targets) or "run"


def result_status(report: dict[str, Any]) -> GovernanceStatus:
    if not report:
        return "warn"
    status = str(report.get("status") or "").lower()
    if status in {
        "blocked",
        "failing",
        "quarantine_required",
        "violations_detected",
        "blocked_claims",
        "blocked_to_fallback",
        "blocked_to_insufficient_data",
    }:
        return "block"
    if status in {
        "warn",
        "watch",
        "degraded",
        "heightened",
        "unsupported_claims",
        "unstable",
        "penalize_protocol_violations",
        "open_blockers",
    }:
        return "warn"
    return "pass"


def blocked_targets_for(
    contract: GovernanceContract,
    report: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> tuple[list[str], str]:
    if contract.actor == "protocol_police_agent":
        targets = []
        for item in report.get("violations") if isinstance(report.get("violations"), list) else []:
            if not isinstance(item, dict):
                continue
            violation_type = str(item.get("type") or "")
            target = blocking_target_for_violation(item, state=state)
            if violation_type in {"writer_violation", "raw_data_leak", "tool_policy_violation"} and target:
                targets.append(target)
        return sorted(set(targets)), "runtime_protocol_police_violations" if targets else "contract_enforcement_targets"
    if contract.actor == "quorum_marshal_agent":
        targets = [
            canonical_target(target)
            for target in report.get("blocked_conclusion_targets") or []
            if str(target or "").strip()
        ]
        if targets:
            return sorted(set(targets)), "runtime_blocked_conclusion_targets"
        legacy_targets = legacy_blocked_conclusion_targets_from_quorum_flags(report)
        if legacy_targets:
            return sorted(set(legacy_targets)), "legacy_quorum_boolean_fallback"
    if contract.actor == "evidence_steward_agent":
        targets = []
        for item in report.get("blocked_claims") if isinstance(report.get("blocked_claims"), list) else []:
            if isinstance(item, dict):
                target = str(item.get("blocked_target") or "decision:blocked_output")
                targets.append(target if ":" in target else f"decision:{target}")
        return sorted(set(targets)), "runtime_evidence_steward_blocked_claims" if targets else "contract_enforcement_targets"
    if contract.actor == "social_immunity_agent":
        targets = [f"artifact:{item.get('artifact_id')}" for item in report.get("contaminants") or [] if isinstance(item, dict)]
        return targets, "runtime_social_immunity_contaminants" if targets else "contract_enforcement_targets"
    if contract.actor == "capability_sandbox_auditor_agent":
        targets = [f"capability:{item.get('capability_id')}" for item in report.get("findings") or [] if isinstance(item, dict) and item.get("severity") == "high"]
        return targets, "runtime_capability_sandbox_findings" if targets else "contract_enforcement_targets"
    if contract.actor == "tool_health_sentinel_agent":
        return ["system:tool_routes"], "runtime_tool_health_report"
    targets = [target for target in contract.enforcement_targets if target]
    return targets, "contract_enforcement_targets"


def required_caveats_for(contract: GovernanceContract, report: dict[str, Any]) -> list[str]:
    caveats: list[str] = []
    if contract.actor == "tool_health_sentinel_agent" and report.get("status") in {"degraded", "failing"}:
        caveats.append("Tool/model route reliability is degraded; keep confidence conservative.")
    if contract.actor == "evidence_steward_agent" and report.get("unsupported_claim_count"):
        caveats.append("Unsupported agent claims were excluded from the final report.")
    if contract.actor == "social_immunity_agent" and report.get("quarantine_count"):
        caveats.append("Contaminated or prompt-injection-like artifacts were quarantined.")
    return caveats


def writer_constraints_for(contract: GovernanceContract, report: dict[str, Any]) -> list[str]:
    constraints: list[str] = []
    if contract.actor == "evidence_steward_agent":
        writer = report.get("writer_constraints") if isinstance(report.get("writer_constraints"), dict) else {}
        blocked_permissions = writer.get("blocked_output_permissions") if isinstance(writer.get("blocked_output_permissions"), list) else []
        allowed_permissions = writer.get("allowed_output_permissions") if isinstance(writer.get("allowed_output_permissions"), list) else []
        declared_permissions = writer.get("conclusion_permissions") if isinstance(writer.get("conclusion_permissions"), list) else []
        for key, value in writer.items():
            key_text = str(key or "").strip()
            if not key_text or key_text.endswith("_allowed"):
                continue
            if value is True:
                append_unique(constraints, key_text)
        if writer.get("drop_unsupported_claims") or report.get("unsupported_claim_count"):
            append_unique(constraints, "drop_unsupported_claims")
        if report.get("blocked_claim_count"):
            append_unique(constraints, "drop_blocked_claims")
        if blocked_permissions or any(key.endswith("_allowed") and value is False for key, value in writer.items()):
            append_unique(constraints, "respect_blocked_output_permissions")
        if blocked_permissions or allowed_permissions or declared_permissions:
            append_unique(constraints, "respect_declared_output_permissions")
    if contract.actor == "quorum_marshal_agent":
        committed = report.get("committed_candidate") if isinstance(report.get("committed_candidate"), dict) else {}
        if committed.get("label"):
            append_unique(constraints, f"final_decision_must_match:{committed.get('label')}")
    if contract.actor == "protocol_police_agent" and report.get("violations"):
        append_unique(constraints, "do_not_publish_until_protocol_violations_resolved")
    return constraints


def final_judge_checks_for(contract: GovernanceContract, report: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    if contract.actor in {"evidence_steward_agent", "quorum_marshal_agent", "protocol_police_agent"}:
        checks.extend(writer_constraints_for(contract, report))
    if contract.actor == "social_immunity_agent" and report.get("quarantine_count"):
        checks.append("verify_quarantined_artifacts_absent_from_final")
    return checks


def summary_for(contract: GovernanceContract, report: dict[str, Any], status: str) -> str:
    if not report:
        return f"{contract.actor} did not run; contract status is warn."
    if contract.actor == "evidence_steward_agent":
        return f"{status}: linked={report.get('linked_claim_count', 0)} unsupported={report.get('unsupported_claim_count', 0)} blocked={report.get('blocked_claim_count', 0)}"
    if contract.actor == "quorum_marshal_agent":
        committed = report.get("committed_candidate") if isinstance(report.get("committed_candidate"), dict) else {}
        return f"{status}: committed={committed.get('label') or 'pending'}"
    if contract.actor == "protocol_police_agent":
        return f"{status}: violations={len(report.get('violations') or [])}"
    return f"{status}: {report.get('status') or 'complete'}"


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
