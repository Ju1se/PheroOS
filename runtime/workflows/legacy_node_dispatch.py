from __future__ import annotations

import importlib
from typing import Any

from runtime.state import AgentState


LEGACY_RESEARCH_NODE_FALLBACKS = {
    "compliance_workflow": ("runtime.workflows.compliance_workflow", "research_agent_node"),
    "evidence_research": ("runtime.workflows.evidence_research", "research_agent_node"),
}


async def legacy_research_node_fallback(runtime: Any, state: AgentState, *, graph_mode: str) -> AgentState | None:
    spec = LEGACY_RESEARCH_NODE_FALLBACKS.get(graph_mode)
    if spec is None:
        return None
    module_name, function_name = spec
    handler = getattr(importlib.import_module(module_name), function_name)
    result = await handler(runtime, state)
    return attach_legacy_research_node_trace(result, graph_mode=graph_mode, handler=f"{module_name}.{function_name}")


def attach_legacy_research_node_trace(result: AgentState, *, graph_mode: str, handler: str) -> AgentState:
    trace = list(result.get("workflow_node_trace") if isinstance(result.get("workflow_node_trace"), list) else [])
    trace.append(
        {
            "graph_mode": graph_mode,
            "node": "research_agent",
            "handler": handler,
            "status": "executed",
            "source": "legacy_graph_mode_node_fallback",
        }
    )
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {
        **result,
        "workflow_node_trace": trace,
        "metadata": {**metadata, "workflow_node_trace": trace},
    }
