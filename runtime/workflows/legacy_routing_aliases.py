from __future__ import annotations

from typing import Any


LEGACY_GRAPH_NODE_ALIASES = {
    "executor_wrds": "executor",
    "wrds_executor": "executor",
    "deterministic_research": "research_agent",
    "research": "research_agent",
    "deterministic_quant": "quant_agent",
    "quant": "quant_agent",
    "domain": "domain_expert",
    "committee": "committee_opening",
}
LEGACY_DEFAULT_WORKFLOW_NODE_ORDER = [
    "memory_agent",
    "executor",
    "data_gate",
    "research_agent",
    "quant_agent",
    "domain_expert",
    "critic",
    "writer",
]
LEGACY_DEFAULT_WORKFLOW_ROUTING_SOURCE = "legacy_default_graph"


def legacy_graph_node_alias(value: Any) -> str:
    text = str(value)
    return LEGACY_GRAPH_NODE_ALIASES.get(text, text)


def legacy_default_workflow_node_order() -> list[str]:
    return list(LEGACY_DEFAULT_WORKFLOW_NODE_ORDER)


def legacy_default_workflow_routing_source() -> str:
    return LEGACY_DEFAULT_WORKFLOW_ROUTING_SOURCE
