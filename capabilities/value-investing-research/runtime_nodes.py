from __future__ import annotations

import asyncio
import os
from typing import Any

from runtime.agent_metrics import metric_started_at, record_agent_metric
from runtime.data_gate import build_investment_data_controls
from runtime.legacy_agent_registry import selected_agent_ids_from_metadata
from runtime.state import AgentState
from runtime.swarm.signal_extractor import data_gate_signals, update_state_with_signals


def state_with_agent_outputs(state: AgentState, outputs: dict[str, Any], **extra: Any) -> AgentState:
    """Expose capability agent output under generic state with legacy mirror."""

    return {**state, "agent_outputs": outputs, "committee_outputs": outputs, **extra}


async def data_gate_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned Data Gate node for WRDS-first investment research."""

    started_at = metric_started_at()
    controls = build_investment_data_controls(state)
    state_with_controls = {**state, **controls}
    swarm_update = update_state_with_signals(state_with_controls, data_gate_signals(state_with_controls))
    gate = controls["data_gate"]
    record_agent_metric(
        agent="data_gate",
        model="deterministic",
        model_used=False,
        started_at=started_at,
        status="failed_blocking" if gate.get("blocking") else "completed",
        failure_reason="; ".join(
            str(issue.get("code") or issue.get("message") or issue)
            for issue in gate.get("critical_errors", [])
            if isinstance(issue, dict)
        )
        or None,
    )
    return {**controls, **swarm_update}


async def research_agent_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned research node constrained by Data Gate and Metric Registry."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    if not graph_runtime.should_run_research_agent(state):
        record_agent_metric(
            agent="research_agent",
            model=runtime.model_config.research_agent,
            model_used=False,
            started_at=started_at,
            status="skipped",
        )
        return {"research_brief": graph_runtime.skipped_analysis("research not required")}
    if graph_runtime.source_mode_is_wrds_only(state.get("metadata", {}).get("source_mode")) and state.get("metric_registry"):
        result = {"research_brief": graph_runtime.deterministic_wrds_research_brief(state)}
        record_agent_metric(
            agent="research_agent",
            model="deterministic",
            model_used=False,
            started_at=started_at,
            status="completed_deterministic",
        )
        return result

    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Research Agent. Extract evidence only. Do not make investment, "
                    "academic, or coding judgments. Return strict JSON with keys: status, sources, "
                    "key_facts, evidence_gaps, reliability, source_grounding. Each source should "
                    "include title, url, date if known, key_facts, reliability. Use the Data Contract "
                    "and Metric Registry as hard constraints; do not treat estimates as actuals."
                ),
            },
            {"role": "user", "content": graph_runtime.research_context(state)},
        ]
        content, model_used, _fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.research_agent,
            fallback_model=runtime.model_config.research_agent_fallback,
            temperature=0.0,
            messages=messages,
        )
        result = {
            "research_brief": graph_runtime.parse_research_brief(
                content,
                grounding=graph_runtime.describe_source_grounding(state),
            )
        }
        record_agent_metric(
            agent="research_agent",
            model=model_used,
            started_at=started_at,
            status="completed",
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result = {
            "research_brief": graph_runtime.failed_research_brief(
                exc,
                grounding=graph_runtime.describe_source_grounding(state),
            )
        }
        record_agent_metric(
            agent="research_agent",
            model=runtime.model_config.research_agent,
            started_at=started_at,
            status="completed_with_model_failure",
            failure_reason=exc,
        )
        return result


async def quant_agent_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned quant node that forbids LLM mental math in WRDS-only mode."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    if graph_runtime.source_mode_is_wrds_only(state.get("metadata", {}).get("source_mode")) and state.get("metric_registry"):
        result = {"quant_analysis": graph_runtime.deterministic_wrds_quant_analysis(state)}
        record_agent_metric(
            agent="quant_agent",
            model="deterministic",
            model_used=False,
            started_at=started_at,
            status="completed_deterministic",
        )
        return result
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Quant & Data Agent. Do not calculate metrics from prose. Use only "
                    "the deterministic Metric Registry and clearly label missing metrics. "
                    "If numeric inputs are missing or blocked by the Data Gate, say so instead of inventing numbers. Return "
                    "strict JSON with keys: status, assumptions, formulas, calculations, metrics, "
                    "sensitivity, missing_data, data_quality."
                ),
            },
            {"role": "user", "content": graph_runtime.quant_context(state)},
        ]
        content, model_used, _fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.quant_agent,
            fallback_model=runtime.model_config.quant_agent_fallback,
            temperature=0.0,
            messages=messages,
        )
        result = {"quant_analysis": graph_runtime.parse_quant_analysis(content)}
        record_agent_metric(
            agent="quant_agent",
            model=model_used,
            started_at=started_at,
            status="completed",
        )
        return result
    except Exception as exc:  # noqa: BLE001
        result = {"quant_analysis": graph_runtime.failed_quant_analysis(exc)}
        record_agent_metric(
            agent="quant_agent",
            model=runtime.model_config.quant_agent,
            started_at=started_at,
            status="completed_with_model_failure",
            failure_reason=exc,
        )
        return result


async def committee_opening_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned committee opening plus PheroOS protocol activation."""

    from runtime import graph as graph_runtime

    outputs: dict[str, Any] = {}
    transcript: list[dict[str, Any]] = []
    member_specs = graph_runtime.committee_member_specs_for_state(state)
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    tenant_id = str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")
    trust_badges = graph_runtime.build_trust_badges(member_specs)
    encounter_report = graph_runtime.build_encounter_rate_report(state)
    bottleneck_report = graph_runtime.build_bottleneck_report(state)
    arousal_report = graph_runtime.build_arousal_report(state)
    social_immunity_report = graph_runtime.build_social_immunity_report(state)
    tool_health_sentinel_report = graph_runtime.build_tool_health_sentinel_report(state)
    capability_sandbox_auditor_report = graph_runtime.build_capability_sandbox_auditor_report(state)
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    swarm_loop_policy = swarm_plan.get("swarm_loop_policy") if isinstance(swarm_plan.get("swarm_loop_policy"), dict) else {}
    lane_policy = swarm_loop_policy.get("lane_policy") if isinstance(swarm_loop_policy.get("lane_policy"), dict) else {}
    lane_assignment_report = graph_runtime.build_lane_assignment_report(
        member_specs,
        trust_badges,
        lane_policy=lane_policy,
    )
    maturity_policy = (
        swarm_loop_policy.get("maturity_policy")
        if isinstance(swarm_loop_policy.get("maturity_policy"), dict)
        else {}
    )
    maturity_report = graph_runtime.build_maturity_report(
        member_specs,
        trust_badges,
        tenant_id=tenant_id,
        maturity_policy=maturity_policy,
    )
    protocol_fields = {
        "trust_badges": trust_badges,
        "encounter_rate_report": encounter_report,
        "bottleneck_report": bottleneck_report,
        "arousal_report": arousal_report,
        "social_immunity_report": social_immunity_report,
        "tool_health_sentinel_report": tool_health_sentinel_report,
        "capability_sandbox_auditor_report": capability_sandbox_auditor_report,
        "lane_assignment_report": lane_assignment_report,
        "maturity_report": maturity_report,
    }
    protocol_signals = [
        *graph_runtime.encounter_rate_signals({**state, **protocol_fields}, encounter_report),
        *graph_runtime.bottleneck_signals({**state, **protocol_fields}, bottleneck_report),
        *graph_runtime.arousal_signals({**state, **protocol_fields}, arousal_report),
        *graph_runtime.social_immunity_signals({**state, **protocol_fields}, social_immunity_report),
        *graph_runtime.tool_health_sentinel_signals({**state, **protocol_fields}, tool_health_sentinel_report),
        *graph_runtime.capability_sandbox_auditor_signals({**state, **protocol_fields}, capability_sandbox_auditor_report),
        *graph_runtime.lane_assignment_signals({**state, **protocol_fields}, lane_assignment_report),
        *graph_runtime.maturity_signals({**state, **protocol_fields}, maturity_report),
    ]
    protocol_update = (
        update_state_with_signals({**state, **protocol_fields}, protocol_signals)
        if protocol_signals
        else {}
    )
    state_for_committee = {**state, **protocol_fields, **protocol_update}
    allocation_trace = graph_runtime.build_agent_allocation_trace(member_specs, state_for_committee)
    homeostasis_report = graph_runtime.build_homeostasis_report({**state_for_committee, "agent_allocation_trace": allocation_trace})
    homeostasis_signal_list = graph_runtime.homeostasis_signals(
        {**state_for_committee, "agent_allocation_trace": allocation_trace, "homeostasis_report": homeostasis_report},
        homeostasis_report,
    )
    homeostasis_update = update_state_with_signals(
        {**state_for_committee, "agent_allocation_trace": allocation_trace, "homeostasis_report": homeostasis_report},
        homeostasis_signal_list,
    ) if homeostasis_signal_list else {}
    protocol_fields["homeostasis_report"] = homeostasis_report
    protocol_signals.extend(homeostasis_signal_list)
    state_for_committee = {**state_for_committee, "homeostasis_report": homeostasis_report, **homeostasis_update}
    controller_report = graph_runtime.build_swarm_controller_report(state_for_committee, member_specs)
    controller_signal_list = graph_runtime.swarm_controller_signals(
        {**state_for_committee, "swarm_controller_report": controller_report},
        controller_report,
    )
    controller_update = update_state_with_signals(
        {**state_for_committee, "swarm_controller_report": controller_report},
        controller_signal_list,
    ) if controller_signal_list else {}
    metadata = state.get("metadata", {}) if isinstance(state.get("metadata"), dict) else {}
    explicit_selection = bool(
        graph_runtime.normalize_selected_committee_members(
            selected_agent_ids_from_metadata(metadata)
        )
    )
    controller_can_mutate_committee = bool(
        metadata.get("os_plan")
        or metadata.get("swarm_controller_enabled") is True
        or os.getenv("SWARM_CONTROLLER_MUTATES_COMMITTEE", "").strip().lower() in {"1", "true", "yes"}
    )
    if controller_can_mutate_committee:
        member_specs = graph_runtime.apply_controller_to_member_specs(
            member_specs,
            controller_report,
            explicit_selection=explicit_selection,
        )
    allocation_trace = graph_runtime.build_agent_allocation_trace(
        member_specs,
        {**state_for_committee, "swarm_controller_report": controller_report, **controller_update},
    )
    protocol_fields["swarm_controller_report"] = controller_report
    protocol_signals.extend(controller_signal_list)
    state_for_committee = {
        **state_for_committee,
        "swarm_controller_report": controller_report,
        "agent_allocation_trace": allocation_trace,
        "active_committee_member_specs": member_specs,
        **controller_update,
    }

    data_spec = member_specs[0]
    data_key, data_output = await run_committee_member(runtime, state_for_committee, spec=data_spec, prior_outputs=outputs)
    outputs[data_key] = data_output
    transcript.append(graph_runtime.opening_transcript_entry(data_key, data_output))

    concurrency = max(1, graph_runtime.parse_positive_int(os.getenv("COMMITTEE_OPENING_CONCURRENCY"), 2))
    semaphore = asyncio.Semaphore(concurrency)

    async def run_specialist(spec: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        async with semaphore:
            return await run_committee_member(
                runtime,
                state_for_committee,
                spec=spec,
                prior_outputs=outputs,
            )

    specialist_results = await asyncio.gather(*[run_specialist(spec) for spec in member_specs[1:]])
    for member, output in specialist_results:
        outputs[member] = output
        transcript.append(graph_runtime.opening_transcript_entry(member, output))

    if all(output.get("status") == "failed" for output in outputs.values()):
        raise RuntimeError("all investment committee agents failed")

    outputs_state = state_with_agent_outputs(state_for_committee, outputs)
    receiver_normalizer_report = graph_runtime.build_receiver_normalizer_report(outputs_state)
    receiver_signal_list = graph_runtime.receiver_normalizer_signals(
        state_with_agent_outputs(
            state_for_committee,
            outputs,
            receiver_normalizer_report=receiver_normalizer_report,
        ),
        receiver_normalizer_report,
    )
    receiver_update = update_state_with_signals(
        state_with_agent_outputs(
            state_for_committee,
            outputs,
            receiver_normalizer_report=receiver_normalizer_report,
        ),
        receiver_signal_list,
    ) if receiver_signal_list else {}
    receiver_state = state_with_agent_outputs(
        state_for_committee,
        outputs,
        receiver_normalizer_report=receiver_normalizer_report,
        **receiver_update,
    )
    evidence_steward_report = graph_runtime.build_evidence_steward_report(
        receiver_state,
        receiver_normalizer_report,
    )
    evidence_signal_list = graph_runtime.evidence_steward_signals(
        state_with_agent_outputs(
            receiver_state,
            outputs,
            evidence_steward_report=evidence_steward_report,
        ),
        evidence_steward_report,
    )
    evidence_update = update_state_with_signals(
        state_with_agent_outputs(
            receiver_state,
            outputs,
            evidence_steward_report=evidence_steward_report,
        ),
        evidence_signal_list,
    ) if evidence_signal_list else {}
    protocol_fields["receiver_normalizer_report"] = receiver_normalizer_report
    protocol_fields["evidence_steward_report"] = evidence_steward_report
    protocol_signals.extend([*receiver_signal_list, *evidence_signal_list])
    specs_by_key = {str(spec.get("key")): spec for spec in member_specs}
    evidence_state = state_with_agent_outputs(
        receiver_state,
        outputs,
        evidence_steward_report=evidence_steward_report,
        **evidence_update,
    )
    signal_result = graph_runtime.agent_emitted_signals_from_outputs(
        evidence_state,
        outputs,
        specs_by_key,
    )
    swarm_update = update_state_with_signals(
        evidence_state,
        signal_result["signals"],
    ) if signal_result["signals"] else {}
    swarm_state = state_with_agent_outputs(evidence_state, outputs, **swarm_update)
    verification_result = graph_runtime.verify_agent_signal_proposals(
        swarm_state
    )
    if verification_result["signals"]:
        swarm_update = {
            **swarm_update,
            **update_state_with_signals(
                swarm_state,
                verification_result["signals"],
            ),
        }
        swarm_state = state_with_agent_outputs(evidence_state, outputs, **swarm_update)
    policing_trace = graph_runtime.build_policing_trace(
        swarm_state,
        signal_result["diagnostics"],
    )
    policing_update = (
        update_state_with_signals(
            swarm_state,
            graph_runtime.policing_signals(
                swarm_state,
                policing_trace,
            ),
        )
        if policing_trace.get("violations")
        else {}
    )
    policing_state = state_with_agent_outputs(
        swarm_state,
        outputs,
        policing_trace=policing_trace,
        **policing_update,
    )
    outcome_memory_steward_report = graph_runtime.build_outcome_memory_steward_report(
        state_with_agent_outputs(
            policing_state,
            outputs,
            agent_allocation_trace=allocation_trace,
            agent_signal_diagnostics=signal_result["diagnostics"],
            agent_signal_verification_trace=verification_result["trace"],
        )
    )
    outcome_signal_list = graph_runtime.outcome_memory_steward_signals(
        state_with_agent_outputs(
            state_for_committee,
            outputs,
            outcome_memory_steward_report=outcome_memory_steward_report,
        ),
        outcome_memory_steward_report,
    )
    outcome_update = update_state_with_signals(
        state_with_agent_outputs(
            policing_state,
            outputs,
            outcome_memory_steward_report=outcome_memory_steward_report,
        ),
        outcome_signal_list,
    ) if outcome_signal_list else {}
    protocol_fields["outcome_memory_steward_report"] = outcome_memory_steward_report
    protocol_signals.extend(outcome_signal_list)
    try:
        metadata = state_for_committee.get("metadata") if isinstance(state_for_committee.get("metadata"), dict) else {}
        os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
        tenant_id = str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")
        graph_runtime.update_agent_profiles_from_outputs(outputs, allocation_trace, tenant_id=tenant_id)
    except OSError:
        pass

    governance_extra = {
        **protocol_fields,
        "agent_allocation_trace": allocation_trace,
        "agent_signal_diagnostics": signal_result["diagnostics"],
        "agent_signal_verification_trace": verification_result["trace"],
        "policing_trace": policing_trace,
        **protocol_update,
        **homeostasis_update,
        **controller_update,
        **receiver_update,
        **evidence_update,
        **swarm_update,
        **policing_update,
        **outcome_update,
    }
    governance_state = state_with_agent_outputs(state_for_committee, outputs, **governance_extra)
    governance_results = graph_runtime.build_governance_results(governance_state)
    enforcement_bus = graph_runtime.apply_enforcement_bus(governance_state, governance_results)
    enforcement_update = (
        update_state_with_signals(governance_state, enforcement_bus["signals"])
        if enforcement_bus["signals"]
        else {}
    )
    governance_state = {
        **governance_state,
        "governance_results": governance_results,
        "enforcement_bus_report": enforcement_bus["enforcement_bus_report"],
        **enforcement_update,
    }
    swarm_governance_trace = graph_runtime.build_governance_actor_trace(governance_state)
    return {
        "agent_outputs": outputs,
        "committee_outputs": outputs,
        "discussion_transcript": transcript,
        "agent_allocation_trace": allocation_trace,
        "agent_signal_diagnostics": signal_result["diagnostics"],
        "agent_signal_verification_trace": verification_result["trace"],
        "policing_trace": policing_trace,
        "governance_results": governance_results,
        "enforcement_bus_report": enforcement_bus["enforcement_bus_report"],
        "swarm_protocol_trace": graph_runtime.protocol_signals_to_trace(protocol_signals),
        "swarm_governance_trace": swarm_governance_trace,
        **protocol_fields,
        **protocol_update,
        **homeostasis_update,
        **controller_update,
        **receiver_update,
        **evidence_update,
        **swarm_update,
        **policing_update,
        **outcome_update,
        **enforcement_update,
    }


async def run_committee_member(
    runtime: Any,
    state: AgentState,
    *,
    spec: dict[str, Any],
    prior_outputs: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Run a capability-owned committee member opening statement."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    model_attr = str(spec.get("model_attr") or spec["key"])
    model = runtime.model_config.model_for(model_attr, fallback_attr="committee_member_fallback")
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the {spec['name']} in an investment committee. "
                    f"Your focus: {spec['focus']} "
                    "Create your own sub-plan, then state an evidence-grounded opening view. "
                    "Do not call tools and do not invent facts beyond the provided Research, Quant, Data Gate, and Metric Registry inputs. "
                    "Do not debate unresolved data defects as if they are investment risks. "
                    "Score is 0-100 where 50 means neutral/watch. Data Auditor and Risk Manager may set "
                    "hard_veto=true when data quality or downside risk prevents a reliable decision. "
                    "Return strict JSON with keys: status, sub_plan, thesis, score, confidence, "
                    "evidence_used, missing_data, risks, hard_veto, evidence_requests, role_assessment, "
                    "emitted_signals. emitted_signals must be a list of objects with keys type, target, "
                    "content, strength, confidence, priority, evidence_ref. Only use signal types allowed "
                    "by your swarm_signal_policy; do not claim verified/blocking status."
                ),
            },
            {
                "role": "user",
                "content": graph_runtime.committee_member_context(state, spec=spec, prior_outputs=prior_outputs),
            },
        ]
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=model,
            fallback_model=graph_runtime.committee_member_fallback_model(
                primary_model=model,
                fallback_model=runtime.model_config.committee_member_fallback,
            ),
            temperature=0.0,
            messages=messages,
        )
        parsed = graph_runtime.parse_committee_output(content, member=spec["key"])
        record_agent_metric(
            agent=spec["key"],
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return spec["key"], parsed
    except Exception as exc:  # noqa: BLE001
        parsed = graph_runtime.failed_committee_output(spec["key"], exc)
        record_agent_metric(
            agent=spec["key"],
            model=model,
            started_at=started_at,
            status="failed",
            failure_reason=exc,
        )
        return spec["key"], parsed


async def committee_discussion_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned multi-round challenge/response moderator."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    transcript = list(state.get("discussion_transcript", []))
    rounds_completed = 0
    failure_reason = None
    discussion_model_used = runtime.model_config.committee_challenge
    try:
        while rounds_completed < 3:
            round_number = rounds_completed + 1
            content, model_used, fallback_reason = await runtime._chat_with_fallback(
                primary_model=runtime.model_config.committee_challenge,
                fallback_model=None,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Investment Committee Discussion Moderator. "
                            "Run one structured challenge/response round between the Jane Street-style committee members. "
                            "Prioritize Data Auditor evidence gaps, Risk Manager vetoes, Red Team attacks, and disagreement "
                            "between Fundamental, Quant, Industry, and Market Execution views. "
                            "Do not add new facts. Return strict JSON with keys: round, turns, continue_discussion. "
                            "turns is an array with speaker, target, claim, challenge, response, score_delta, confidence_delta."
                        ),
                    },
                    {
                        "role": "user",
                        "content": graph_runtime.committee_discussion_context(
                            state,
                            transcript=transcript,
                            round_number=round_number,
                        ),
                    },
                ],
            )
            discussion_model_used = model_used
            parsed = graph_runtime.parse_discussion_round(content, round_number=round_number)
            if fallback_reason:
                failure_reason = fallback_reason
            transcript.extend(parsed["turns"])
            rounds_completed += 1
            if rounds_completed >= 1 and not graph_runtime.should_continue_committee_discussion(
                state,
                transcript=transcript,
                model_requested_continue=parsed["continue_discussion"],
                rounds_completed=rounds_completed,
            ):
                break
    except Exception as exc:  # noqa: BLE001
        failure_reason = exc
        if rounds_completed == 0:
            transcript.extend(graph_runtime.fallback_discussion_turns(state, round_number=1))

    record_agent_metric(
        agent="committee_discussion",
        model=discussion_model_used,
        started_at=started_at,
        status="completed_with_fallback" if failure_reason else "completed",
        failure_reason=failure_reason,
    )
    return {"discussion_transcript": transcript}


async def investment_committee_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned CIO decision node with quorum and PheroOS enforcement."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the CIO / Investment Committee Chair. Synthesize the committee outputs and "
                    "discussion transcript into an auditable Buy / Watch / Avoid / Sell decision. "
                    "Do not add new facts. Data Auditor and Risk Manager vetoes must be explicitly handled. "
                    "Return strict JSON with keys: decision, final_decision, conviction, position_size, "
                    "time_horizon, core_thesis, key_evidence, main_risk, invalidation_point, consensus, "
                    "dissent, hard_vetoes, scorecard, confidence, open_questions, evidence_limitations."
                ),
            },
            {"role": "user", "content": graph_runtime.investment_committee_context(state)},
        ]
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.investment_committee,
            fallback_model=runtime.model_config.investment_committee_fallback,
            temperature=0.0,
            messages=messages,
        )
        decision = graph_runtime.parse_agent_decision(content, state=state)
        record_agent_metric(
            agent="investment_committee",
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return finalize_investment_committee_decision(state, decision)
    except Exception as exc:  # noqa: BLE001
        record_agent_metric(
            agent="investment_committee",
            model=runtime.model_config.investment_committee,
            started_at=started_at,
            status="completed_with_model_failure",
            failure_reason=exc,
        )
        decision = graph_runtime.fallback_agent_decision(
            state,
            summary=f"Investment committee chair model failed: {exc}",
        )
        return finalize_investment_committee_decision(state, decision)


def finalize_investment_committee_decision(state: AgentState, decision: dict[str, Any]) -> AgentState:
    """Close the committee decision through quorum, evidence graph, and enforcement bus."""

    from runtime import graph as graph_runtime

    state_with_decision = {**state, "agent_decision": decision, "committee_decision": decision}
    resolution_update = graph_runtime.apply_stop_signal_resolution(state_with_decision)
    state_for_quorum = {**state_with_decision, **resolution_update}
    quorum_trace, independence_report = graph_runtime.apply_independent_scout_adjustment(
        graph_runtime.build_quorum_trace(state_for_quorum),
        state_for_quorum,
    )
    protocol_decision = graph_runtime.apply_protocol_decision_boundary(
        {**state_for_quorum, "quorum_trace": quorum_trace},
        decision,
    )
    state_for_quorum = {**state_for_quorum, "protocol_decision": protocol_decision}
    scout_update = update_state_with_signals(
        {**state_for_quorum, "quorum_trace": quorum_trace, "independence_report": independence_report},
        graph_runtime.independent_scout_signals(
            {**state_for_quorum, "quorum_trace": quorum_trace, "independence_report": independence_report},
            independence_report,
        ),
    )
    quorum_marshal_report = graph_runtime.build_quorum_marshal_report(
        {**state_for_quorum, "quorum_trace": quorum_trace, "independence_report": independence_report, **scout_update},
        quorum_trace,
    )
    quorum_marshal_update = update_state_with_signals(
        {
            **state_for_quorum,
            "quorum_trace": quorum_trace,
            "independence_report": independence_report,
            "quorum_marshal_report": quorum_marshal_report,
            **scout_update,
        },
        graph_runtime.quorum_marshal_signals(
            {
                **state_for_quorum,
                "quorum_trace": quorum_trace,
                "independence_report": independence_report,
                "quorum_marshal_report": quorum_marshal_report,
                **scout_update,
            },
            quorum_marshal_report,
        ),
    )
    state_for_evidence_graph = {
        **state_for_quorum,
        "quorum_trace": quorum_trace,
        "independence_report": independence_report,
        "quorum_marshal_report": quorum_marshal_report,
        **scout_update,
        **quorum_marshal_update,
    }
    evidence_graph = graph_runtime.build_evidence_graph(state_for_evidence_graph)
    governance_state = {**state_for_evidence_graph, "evidence_graph": evidence_graph}
    governance_results = graph_runtime.build_governance_results(governance_state)
    enforcement_bus = graph_runtime.apply_enforcement_bus(governance_state, governance_results)
    enforcement_update = (
        update_state_with_signals(governance_state, enforcement_bus["signals"])
        if enforcement_bus["signals"]
        else {}
    )
    swarm_governance_trace = graph_runtime.build_governance_actor_trace(
        {
            **governance_state,
            "governance_results": governance_results,
            "enforcement_bus_report": enforcement_bus["enforcement_bus_report"],
            **enforcement_update,
        }
    )
    return {
        "agent_decision": decision,
        "committee_decision": decision,
        "protocol_decision": protocol_decision,
        "domain_analysis": graph_runtime.agent_decision_to_domain_analysis(decision),
        "quorum_trace": quorum_trace,
        "independence_report": independence_report,
        "quorum_marshal_report": quorum_marshal_report,
        "governance_results": governance_results,
        "enforcement_bus_report": enforcement_bus["enforcement_bus_report"],
        "swarm_governance_trace": swarm_governance_trace,
        **resolution_update,
        **scout_update,
        **quorum_marshal_update,
        **enforcement_update,
        "evidence_graph": evidence_graph,
    }
