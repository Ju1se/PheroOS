from __future__ import annotations

from typing import Any

from runtime.workflows.legacy_routing_aliases import (
    legacy_default_workflow_node_order,
    legacy_default_workflow_routing_source,
    legacy_graph_node_alias,
)

ROUTABLE_NODES = {
    "memory_agent",
    "executor",
    "data_gate",
    "research_agent",
    "quant_agent",
    "domain_expert",
    "committee_opening",
    "critic",
    "writer",
}

TERMINAL_NODES = {"final_judge"}

def workflow_node_order_from_state(state: dict[str, Any]) -> list[str]:
    """Return capability-owned graph node order when a workflow descriptor exists."""

    for workflow in ranked_workflow_descriptors_from_state(state):
        order = normalize_workflow_order(workflow.get("graph_nodes") or workflow.get("ordered_nodes"))
        if order:
            return order
    return []


def workflow_descriptor_from_state(state: dict[str, Any]) -> dict[str, Any]:
    workflows = ranked_workflow_descriptors_from_state(state)
    return workflows[0] if workflows else {}


def workflow_descriptors_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    runtime = metadata.get("capability_runtime") if isinstance(metadata.get("capability_runtime"), dict) else {}
    capabilities = runtime.get("capabilities") if isinstance(runtime.get("capabilities"), dict) else {}
    workflows: list[dict[str, Any]] = []
    for descriptor in capabilities.values():
        if not isinstance(descriptor, dict):
            continue
        entrypoints = descriptor.get("entrypoints") if isinstance(descriptor.get("entrypoints"), dict) else {}
        workflow = entrypoints.get("workflow") if isinstance(entrypoints.get("workflow"), dict) else None
        if workflow:
            workflows.append(workflow)
    return workflows


def ranked_workflow_descriptors_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    workflows = workflow_descriptors_from_state(state)
    if len(workflows) < 2:
        return workflows
    selected = selected_skill_names_from_state(state)
    indexed = [
        (workflow_descriptor_rank(workflow, selected_skill_names=selected), index, workflow)
        for index, workflow in enumerate(workflows)
    ]
    indexed.sort(key=lambda item: (-item[0], item[1]))
    return [workflow for _, _, workflow in indexed]


def workflow_descriptor_rank(workflow: dict[str, Any], *, selected_skill_names: set[str]) -> int:
    capability_id = str(workflow.get("capability_id") or "").strip()
    workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or "").strip()
    graph_mode = str(workflow.get("graph_mode") or "").strip()
    score = 0
    if capability_id and capability_id in selected_skill_names:
        score += 100
    if workflow_id and any(workflow_id == name or workflow_id.startswith(f"{name}.") for name in selected_skill_names):
        score += 80
    if graph_mode and graph_mode in selected_skill_names:
        score += 40
    if normalize_workflow_nodes(workflow.get("graph_nodes") or workflow.get("ordered_nodes"), include_terminal=True):
        score += 10
    return score


def selected_skill_names_from_state(state: dict[str, Any]) -> set[str]:
    selected = state.get("selected_skills") if isinstance(state.get("selected_skills"), list) else []
    names = {
        str(skill.get("name") or "").strip()
        for skill in selected
        if isinstance(skill, dict) and str(skill.get("name") or "").strip()
    }
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    requested = metadata.get("requested_skill_names") if isinstance(metadata.get("requested_skill_names"), list) else []
    names.update(str(name).strip() for name in requested if str(name).strip())
    return names


def workflow_all_nodes_from_state(state: dict[str, Any]) -> list[str]:
    workflow = workflow_descriptor_from_state(state)
    return normalize_workflow_nodes(workflow.get("graph_nodes") or workflow.get("ordered_nodes"), include_terminal=True)


def normalize_workflow_order(value: Any) -> list[str]:
    return [node for node in normalize_workflow_nodes(value, include_terminal=False) if node in ROUTABLE_NODES]


def normalize_workflow_nodes(value: Any, *, include_terminal: bool) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        node = legacy_graph_node_alias(item)
        if node in {"orchestrator", "patroller_gate"}:
            continue
        if node in TERMINAL_NODES and not include_terminal:
            continue
        if node not in ROUTABLE_NODES.union(TERMINAL_NODES) or node in seen:
            continue
        seen.add(node)
        output.append(node)
    return output


def active_node_order(state: dict[str, Any]) -> list[str]:
    return workflow_node_order_from_state(state) or legacy_default_workflow_node_order()


def workflow_routing_summary(state: dict[str, Any]) -> dict[str, Any]:
    capability_order = workflow_node_order_from_state(state)
    workflow = workflow_descriptor_from_state(state)
    fallback_order = legacy_default_workflow_node_order()
    return {
        "source": "capability_workflow" if capability_order else legacy_default_workflow_routing_source(),
        "ordered_nodes": capability_order or fallback_order,
        "terminal_nodes": [node for node in workflow_all_nodes_from_state(state) if node in TERMINAL_NODES],
        "domain_nodes": workflow.get("ordered_nodes") if isinstance(workflow.get("ordered_nodes"), list) else [],
        "graph_mode": workflow.get("graph_mode") if isinstance(workflow.get("graph_mode"), str) else None,
        "node_policy": workflow.get("node_policy") if isinstance(workflow.get("node_policy"), dict) else {},
        "data_contract": workflow.get("data_contract") if isinstance(workflow.get("data_contract"), dict) else {},
        "evidence_adapter": workflow.get("evidence_adapter") if isinstance(workflow.get("evidence_adapter"), dict) else {},
        "output_contract": workflow.get("output_contract") if isinstance(workflow.get("output_contract"), dict) else {},
        "runtime_support": workflow.get("runtime_support") if isinstance(workflow.get("runtime_support"), dict) else {},
    }


def workflow_node_required(state: dict[str, Any], node: str) -> bool | None:
    workflow = workflow_descriptor_from_state(state)
    if not workflow:
        return None
    normalized_node = legacy_graph_node_alias(node)
    policy = workflow_node_policy(state, normalized_node)
    if policy and "required" in policy:
        return bool(policy.get("required"))
    return normalized_node in workflow_all_nodes_from_state(state)


def workflow_node_policy(state: dict[str, Any], node: str) -> dict[str, Any]:
    workflow = workflow_descriptor_from_state(state)
    policy = workflow.get("node_policy") if isinstance(workflow.get("node_policy"), dict) else {}
    normalized_node = legacy_graph_node_alias(node)
    item = policy.get(normalized_node)
    return item if isinstance(item, dict) else {}
