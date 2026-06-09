from __future__ import annotations

from typing import Any

from runtime.agent_metrics import metric_started_at, record_agent_metric
from runtime.state import AgentState


async def memory_agent_node(runtime: Any, state: AgentState) -> AgentState:
    """Build typed memory context without letting memory make final judgments."""

    from runtime import graph as graph_runtime

    started_at = metric_started_at()
    memory = graph_runtime.build_memory_context(state.get("metadata", {}), task=state["task"])
    record_agent_metric(
        agent="memory_agent",
        model=runtime.model_config.memory_agent,
        model_used=False,
        started_at=started_at,
        status="completed" if memory["items"] else "skipped",
    )
    return {"memory_context": memory}
