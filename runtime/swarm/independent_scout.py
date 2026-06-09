from __future__ import annotations

from collections import Counter
from typing import Any

from runtime.swarm.candidate_registry import (
    fallbackish_candidate_text,
    legacy_fallbackish_candidate_allowed,
    normalized_candidate_label,
)
from runtime.swarm.agent_outputs import runtime_agent_outputs
from runtime.swarm.types import PheromoneSignal, SignalType, VerificationState
from runtime.swarm.legacy_independent_scout_policy import (
    independent_scout_fallback_label,
    legacy_controller_quorum_policy_override_fields,
    legacy_independent_scout_forced_fallback_reason_template,
    legacy_independent_scout_low_independence_reason_template,
    legacy_independent_scout_policy,
    legacy_independent_scout_policy_source,
    legacy_independent_scout_signal_template,
    render_independent_scout_template,
    source_family_for_agent,
)


DECLARED_INDEPENDENT_SCOUT_POLICY_SOURCE = "capability_swarm_loop_policy"
SWARM_CONTROLLER_QUORUM_POLICY_SOURCE = "swarm_controller_quorum_policy"


def apply_independent_scout_adjustment(quorum_trace: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = quorum_trace.get("candidates") if isinstance(quorum_trace.get("candidates"), list) else []
    outputs = runtime_agent_outputs(state)
    policy, policy_sources = effective_independent_scout_policy(state)
    source_refs = collect_source_refs(outputs, policy=policy)
    min_independence = as_float(policy.get("min_independence_score"), default=0.5)
    force_fallback = policy.get("force_fallback_when_low_independence") is not False
    fallback_candidate = fallback_candidate_for_quorum(quorum_trace, candidates, policy)
    report = {
        "status": "evaluated",
        "support_count": len(source_refs),
        "independent_support_count": len(set(source_refs)),
        "source_diversity": round(len(set(source_refs)) / max(len(source_refs), 1), 3),
        "correlation_penalty": round(1 - (len(set(source_refs)) / max(len(source_refs), 1)), 3) if source_refs else 0.0,
        "min_independence_score": min_independence,
        "independent_scout_policy_source": policy_sources["policy"],
        "source_family_policy_source": policy_sources["source_family"],
        "threshold_policy_source": policy_sources["min_independence_score"],
        "fallback_policy_source": policy_sources["force_fallback_when_low_independence"],
        "independence_gate": {
            "active": False,
            "reason": "",
        },
    }
    adjusted_candidates = []
    low_independence = bool(source_refs) and report["source_diversity"] < min_independence
    has_fallback_candidate = bool(fallback_candidate)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw = float(candidate.get("support_score") or 0)
        effective = max(0.0, raw * max(report["source_diversity"], 0.35) - report["correlation_penalty"] * 0.15)
        gate_committed = (
            low_independence
            and force_fallback
            and has_fallback_candidate
            and candidate_matches(candidate, fallback_candidate)
        )
        gate_uncommitted = (
            low_independence
            and force_fallback
            and has_fallback_candidate
            and not candidate_matches(candidate, fallback_candidate)
        )
        adjusted_candidates.append(
            {
                **candidate,
                "raw_support_score": round(raw, 3),
                "effective_support_score": round(effective, 3),
                "independence_score": report["source_diversity"],
                "correlation_penalty": report["correlation_penalty"],
                "committed": True if gate_committed else False if gate_uncommitted else candidate.get("committed"),
                "reason": forced_fallback_reason(policy, fallback_candidate, report) if gate_committed else candidate.get("reason"),
            }
        )
    if low_independence and force_fallback and has_fallback_candidate:
        report["independence_gate"] = {
            "active": True,
            "reason": low_independence_reason(policy, report),
            "fallback_candidate": fallback_candidate,
            "policy_source": policy_sources["low_independence_reason_template"],
        }
    adjusted = {
        **quorum_trace,
        "candidates": adjusted_candidates,
        "independent_scout": report,
    }
    committed = next((item for item in adjusted_candidates if item.get("committed")), None)
    if committed:
        adjusted["committed_candidate"] = committed
    return adjusted, report


def fallback_candidate_for_quorum(
    quorum_trace: dict[str, Any],
    candidates: list[Any],
    policy: dict[str, Any],
) -> dict[str, Any] | None:
    declared = quorum_trace.get("fallback_candidate") if isinstance(quorum_trace.get("fallback_candidate"), dict) else {}
    if declared:
        return candidate_by_reference(declared, candidates) or dict(declared)
    explicit = policy.get("candidate_fallback") or policy.get("fallback_candidate")
    if explicit:
        match = candidate_by_reference({"id": explicit, "label": explicit}, candidates)
        if match:
            return match
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("safe_fallback"):
            return dict(candidate)
    if legacy_fallbackish_candidate_allowed(quorum_trace):
        for candidate in candidates:
            if isinstance(candidate, dict) and fallbackish_candidate_text(f"{candidate.get('id')} {candidate.get('label')}"):
                return dict(candidate)
    return None


def candidate_by_reference(reference: dict[str, Any], candidates: list[Any]) -> dict[str, Any] | None:
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate_matches(candidate, reference):
            return dict(candidate)
    return None


def candidate_matches(candidate: dict[str, Any], reference: dict[str, Any] | None) -> bool:
    if not reference:
        return False
    return bool(candidate_keys(candidate).intersection(candidate_keys(reference)))


def candidate_keys(value: dict[str, Any]) -> set[str]:
    return {
        key
        for key in (
            normalized_candidate_label(value.get("candidate")),
            normalized_candidate_label(value.get("id")),
            normalized_candidate_label(value.get("label")),
        )
        if key
    }


def independent_scout_signals(state: dict[str, Any], report: dict[str, Any]) -> list[PheromoneSignal]:
    if report.get("support_count", 0) <= 1:
        return []
    template, template_source = independent_scout_signal_template_from_state(state)
    return [
        PheromoneSignal(
            run_id=str(state.get("run_id") or "unknown"),
            tenant_id=str((state.get("metadata") or {}).get("tenant_id") or "default"),
            type=SignalType.INDEPENDENCE,
            target="quorum:source_diversity",
            content=render_independent_scout_template(template, report),
            strength=float(report.get("source_diversity") or 0.0),
            confidence=0.75,
            verification_state=VerificationState.VERIFIED,
            source_module="independent_scout",
            metadata={**report, "signal_template_source": template_source},
        )
    ]


def collect_source_refs(outputs: dict[str, Any], *, policy: dict[str, Any] | None = None) -> list[str]:
    source_policy = policy if isinstance(policy, dict) and policy else legacy_independent_scout_policy()
    refs: list[str] = []
    for agent, output in outputs.items():
        if not isinstance(output, dict):
            continue
        evidence = output.get("evidence_used")
        family = agent_family(str(agent), policy=source_policy)
        if isinstance(evidence, list) and evidence:
            refs.extend(f"{family}:{str(item)}" for item in evidence)
        else:
            refs.append(f"{family}:{str(output.get('evidence_ref') or agent)}")
    return refs


def correlated_support_report(refs: list[str]) -> dict[str, Any]:
    counts = Counter(refs)
    return {"counts": dict(counts), "duplicates": {key: value for key, value in counts.items() if value > 1}}


def agent_family(agent: str, *, policy: dict[str, Any] | None = None) -> str:
    source_policy = policy if isinstance(policy, dict) and policy else legacy_independent_scout_policy()
    return source_family_for_agent(agent, source_policy)


def effective_independent_scout_policy(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    policy = legacy_independent_scout_policy()
    legacy_source = legacy_independent_scout_policy_source()
    sources = {key: legacy_source for key in policy}
    sources["policy"] = legacy_source

    declared = independent_scout_policy_from_state(state)
    if declared:
        policy.update(declared)
        sources.update({key: DECLARED_INDEPENDENT_SCOUT_POLICY_SOURCE for key in declared})
        sources["policy"] = DECLARED_INDEPENDENT_SCOUT_POLICY_SOURCE

    controller_policy = controller_quorum_policy_from_state(state)
    for key in legacy_controller_quorum_policy_override_fields():
        if key in controller_policy:
            policy[key] = controller_policy[key]
            sources[key] = SWARM_CONTROLLER_QUORUM_POLICY_SOURCE
    if (
        "force_insufficient_data_when_low_independence" in controller_policy
        and "force_fallback_when_low_independence" not in controller_policy
    ):
        policy["force_fallback_when_low_independence"] = controller_policy[
            "force_insufficient_data_when_low_independence"
        ]
        sources["force_fallback_when_low_independence"] = SWARM_CONTROLLER_QUORUM_POLICY_SOURCE

    return policy, {
        "policy": sources.get("policy", legacy_source),
        "source_family": first_non_legacy_source(
            sources,
            "source_family_rules",
            "default_source_family",
            default=legacy_source,
        ),
        "signal_template": sources.get("signal_template", legacy_source),
        "min_independence_score": sources.get("min_independence_score", legacy_source),
        "force_fallback_when_low_independence": sources.get(
            "force_fallback_when_low_independence",
            legacy_source,
        ),
        "low_independence_reason_template": sources.get(
            "low_independence_reason_template",
            legacy_source,
        ),
        "forced_fallback_reason_template": sources.get(
            "forced_fallback_reason_template",
            legacy_source,
        ),
    }


def first_non_legacy_source(sources: dict[str, str], *keys: str, default: str) -> str:
    for key in keys:
        source = sources.get(key)
        if source and source != default:
            return source
    for key in keys:
        if key in sources:
            return sources[key]
    return default


def independent_scout_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    policy = swarm_loop_policy_from_state(state)
    declared = policy.get("independent_scout_policy") if isinstance(policy.get("independent_scout_policy"), dict) else {}
    return declared


def controller_quorum_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    controller = state.get("swarm_controller_report") if isinstance(state.get("swarm_controller_report"), dict) else {}
    policy = controller.get("quorum_policy") if isinstance(controller.get("quorum_policy"), dict) else {}
    return policy


def independent_scout_signal_template_from_state(state: dict[str, Any]) -> tuple[str, str]:
    policy, sources = effective_independent_scout_policy(state)
    declared = str(policy.get("signal_template") or "").strip()
    if declared:
        return declared, sources["signal_template"]
    return legacy_independent_scout_signal_template(), legacy_independent_scout_policy_source()


def low_independence_reason(policy: dict[str, Any], report: dict[str, Any]) -> str:
    template = str(policy.get("low_independence_reason_template") or "").strip()
    if not template:
        template = legacy_independent_scout_low_independence_reason_template()
    return render_independent_scout_template(template, report)


def forced_fallback_reason(
    policy: dict[str, Any],
    fallback_candidate: dict[str, Any] | None,
    report: dict[str, Any],
) -> str:
    template = str(policy.get("forced_fallback_reason_template") or "").strip()
    if not template:
        template = legacy_independent_scout_forced_fallback_reason_template()
    return render_independent_scout_template(
        template,
        {**report, "fallback_candidate": fallback_candidate, "fallback_label": independent_scout_fallback_label(fallback_candidate)},
    )


def swarm_loop_policy_from_state(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    return policy


def as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
