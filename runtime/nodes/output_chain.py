from __future__ import annotations

from typing import Any

from runtime.agent_metrics import metric_started_at, record_agent_metric
from runtime.data_gate import (
    data_gate_failed,
    data_gate_publication_blocked,
    render_data_defect_memo,
    render_data_readiness_memo,
)
from runtime.final_judge_guardrails import apply_final_judge_guardrails, final_judge_system_prompt
from runtime.state import AgentState
from runtime.swarm.patroller_gate import patroller_blocked, render_patroller_defect_memo
from runtime.swarm.stop_signal import report_publication_blocked
from runtime.swarm_pipeline import attach_artifact_cue_governance, attach_review_governance
from runtime.writer_guardrails import apply_writer_guardrails, writer_system_prompt


async def critic_node(runtime: Any, state: AgentState) -> AgentState:
    """Run the generic Critic / Verifier node.

    This node is runtime-owned rather than capability-owned because it is part
    of the cross-domain output safety chain. It still calls models only through
    the runtime model gateway and emits review governance through PheroOS.
    """

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    try:
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.critic,
            fallback_model=None,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Critic / Verifier Agent. Be hostile but fair. Do not rewrite first. "
                        "Identify overclaims, weak evidence, calculation errors, citation gaps, and where "
                        "the conclusion does not follow from the data, including any committed governed "
                        "decision when present. If critical data defects remain, set status to REJECT_CONDITIONAL "
                        "or REJECT_FATAL. Return strict JSON with keys: "
                        "status, issues, overclaims, data_errors, citation_gaps, minimal_fixes, summary."
                    ),
                },
                {"role": "user", "content": graph_runtime.critic_context(state)},
            ],
        )
        result = attach_review_governance(
            state,
            {"review": graph_runtime.apply_review_grounding_policy(graph_runtime.parse_review(content), state)},
        )
        record_agent_metric(
            agent="critic",
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        record_agent_metric(
            agent="critic",
            model=runtime.model_config.critic,
            started_at=started_at,
            status="completed_with_model_failure",
            failure_reason=exc,
        )
        result = {
            "review": {
                "status": "REJECT_CONDITIONAL",
                "issues": [f"Critic model failed: {exc}"],
                "overclaims": [],
                "data_errors": [],
                "citation_gaps": [],
                "minimal_fixes": ["Re-run critic before publishing a governed final answer."],
                "summary": "Critic/Verifier could not complete, so the runtime blocks publication of a final governed report.",
            }
        }
        return attach_review_governance(state, result)


async def writer_node(runtime: Any, state: AgentState) -> AgentState:
    """Run the generic Writer node behind Data Gate and PheroOS guardrails."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    if patroller_blocked(state):
        final = render_patroller_defect_memo(state)
        record_agent_metric(
            agent="writer",
            model=runtime.model_config.writer,
            model_used=False,
            started_at=started_at,
            status="patroller_blocked",
            failure_reason="patroller_gate_blocked",
        )
        return {"draft_final": final, "final": final}
    if data_gate_failed(state):
        final = render_data_defect_memo(state)
        record_agent_metric(
            agent="writer",
            model=runtime.model_config.writer,
            model_used=False,
            started_at=started_at,
            status="data_gate_blocked",
            failure_reason="data_gate_failed",
        )
        return {"draft_final": final, "final": final}
    if data_gate_publication_blocked(state) and not graph_runtime.review_requires_revision_or_stop(state.get("review", {})):
        final = render_data_readiness_memo(state)
        record_agent_metric(
            agent="writer",
            model=runtime.model_config.writer,
            model_used=False,
            started_at=started_at,
            status="data_gate_publication_blocked",
            failure_reason="data_gate_publication_blocked",
        )
        return {"draft_final": final, "final": final}
    if report_publication_blocked(state) and not graph_runtime.review_requires_revision_or_stop(state.get("review", {})):
        final = render_data_readiness_memo(state)
        record_agent_metric(
            agent="writer",
            model=runtime.model_config.writer,
            model_used=False,
            started_at=started_at,
            status="swarm_stop_signal_blocked",
            failure_reason="swarm_publication_blocked",
        )
        return {"draft_final": final, "final": final}
    if graph_runtime.review_requires_revision_or_stop(state.get("review", {})):
        final = graph_runtime.render_review_defect_memo(state)
        record_agent_metric(
            agent="writer",
            model=runtime.model_config.writer,
            model_used=False,
            started_at=started_at,
            status="critic_blocked",
            failure_reason=str((state.get("review") or {}).get("status") or "critic_rejected"),
        )
        return {"draft_final": final, "final": final}
    try:
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.writer,
            fallback_model=None,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": writer_system_prompt(state),
                },
                {"role": "user", "content": graph_runtime.writer_context(state)},
            ],
        )
        final = apply_writer_guardrails(content, state)
        result = {"draft_final": final, "final": final}
        record_agent_metric(
            agent="writer",
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        record_agent_metric(
            agent="writer",
            model=runtime.model_config.writer,
            started_at=started_at,
            status="failed",
            failure_reason=exc,
        )
        raise


async def final_judge_node(runtime: Any, state: AgentState) -> AgentState:
    """Run the generic Final Judge node and artifact-cue governance closeout."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    try:
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.final_judge,
            fallback_model=None,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": final_judge_system_prompt(state),
                },
                {"role": "user", "content": graph_runtime.final_judge_context(state)},
            ],
        )
        final = apply_final_judge_guardrails(content, state)
        result = attach_artifact_cue_governance(state, {"final": final})
        record_agent_metric(
            agent="final_judge",
            model=model_used,
            started_at=started_at,
            status="completed_with_fallback" if fallback_reason else "completed",
            failure_reason=fallback_reason,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        record_agent_metric(
            agent="final_judge",
            model=runtime.model_config.final_judge,
            started_at=started_at,
            status="failed",
            failure_reason=exc,
        )
        raise
