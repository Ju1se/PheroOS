from __future__ import annotations

import inspect
from typing import Any

from runtime.capability_registry import CapabilityRegistry
from runtime.capability_runtime import CapabilityEntrypointError, load_function, safe_entrypoint_path
from runtime.swarm.control_loop import run_generic_swarm_control_loop


GENERIC_WORKFLOW_SCHEMA_VERSION = "pheroos.generic_workflow.v1"


def augment_orchestration_result(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    """Attach descriptor-native workflow metadata for arbitrary capabilities."""

    trace = build_generic_workflow_trace(state, result, workflow=workflow)
    control = run_generic_swarm_control_loop(
        {**state, **result, "domain_workflow": trace},
        tool_registry=tool_registry,
    )
    trace = attach_control_loop_trace(trace, control)
    plan = generic_workflow_plan(result, workflow=workflow)
    updated = {
        **result,
        "plan": plan,
        "domain_workflow": trace,
        "swarm_control_loop": control,
        "quorum_trace": control.get("quorum_trace", result.get("quorum_trace", {})),
        "recovery_trace": first_item(control.get("recovery_traces")),
        "recovery_traces": control.get("recovery_traces", []),
        "outcome_feedback": control.get("outcome_feedback", {}),
    }
    state_updates = control.get("state_updates") if isinstance(control.get("state_updates"), dict) else {}
    for key in ("pheromone_field_snapshot", "stop_signals"):
        if key in state_updates:
            updated[key] = state_updates[key]
    if state_updates.get("signal_resolution_report"):
        updated["signal_resolution_report"] = state_updates["signal_resolution_report"]
    return merge_metadata(updated, domain_workflow=trace)


async def augment_orchestration_result_async(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    """Async-aware variant for runtime graph execution."""

    if result.get("defer_generic_workflow_host"):
        trace = build_deferred_generic_workflow_trace(state, result, workflow=workflow)
        plan = generic_workflow_plan(result, workflow=workflow)
        updated = {
            **result,
            "plan": plan,
            "domain_workflow": trace,
            "workflow_host_trace": [
                {
                    "status": "deferred",
                    "node": "workflow_host",
                    "source": "generic_capability_workflow",
                    "workflow_id": trace.get("workflow_id"),
                }
            ],
        }
        return merge_metadata(updated, domain_workflow=trace)

    trace = await build_generic_workflow_trace_async(state, result, workflow=workflow)
    control = run_generic_swarm_control_loop(
        {**state, **result, "domain_workflow": trace},
        tool_registry=tool_registry,
    )
    trace = attach_control_loop_trace(trace, control)
    plan = generic_workflow_plan(result, workflow=workflow)
    updated = {
        **result,
        "plan": plan,
        "domain_workflow": trace,
        "swarm_control_loop": control,
        "quorum_trace": control.get("quorum_trace", result.get("quorum_trace", {})),
        "recovery_trace": first_item(control.get("recovery_traces")),
        "recovery_traces": control.get("recovery_traces", []),
        "outcome_feedback": control.get("outcome_feedback", {}),
    }
    state_updates = control.get("state_updates") if isinstance(control.get("state_updates"), dict) else {}
    for key in ("pheromone_field_snapshot", "stop_signals"):
        if key in state_updates:
            updated[key] = state_updates[key]
    if state_updates.get("signal_resolution_report"):
        updated["signal_resolution_report"] = state_updates["signal_resolution_report"]
    return merge_metadata(updated, domain_workflow=trace)


def augment_execution_result(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    workflow = domain_workflow_from_state({**state, **result})
    if not workflow:
        return result
    control = run_generic_swarm_control_loop(
        {**state, **result, "domain_workflow": workflow},
        tool_registry=tool_registry,
    )
    workflow = attach_control_loop_trace(dict(workflow), control)
    updated = {
        **result,
        "domain_workflow": workflow,
        "swarm_control_loop": control,
        "quorum_trace": control.get("quorum_trace", result.get("quorum_trace", {})),
        "recovery_trace": first_item(control.get("recovery_traces")),
        "recovery_traces": control.get("recovery_traces", []),
        "outcome_feedback": control.get("outcome_feedback", {}),
    }
    return merge_metadata(updated, domain_workflow=workflow)


async def execute_graph_workflow_host(
    state: dict[str, Any],
    *,
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    trace = await build_generic_workflow_trace_async(state, state, workflow=workflow)
    trace["graph_host_node"] = "workflow_host"
    control = run_generic_swarm_control_loop({**state, "domain_workflow": trace}, tool_registry=tool_registry)
    trace = attach_control_loop_trace(trace, control)
    trace["graph_host_node"] = "workflow_host"
    updated = {
        "domain_workflow": trace,
        "swarm_control_loop": control,
        "quorum_trace": control.get("quorum_trace", state.get("quorum_trace", {})),
        "recovery_trace": first_item(control.get("recovery_traces")),
        "recovery_traces": control.get("recovery_traces", []),
        "outcome_feedback": control.get("outcome_feedback", {}),
        "workflow_host_trace": [
            {
                "status": "executed",
                "node": "workflow_host",
                "source": "generic_capability_workflow",
                "workflow_id": trace.get("workflow_id"),
                "executed_count": len(
                    [
                        item
                        for item in trace.get("entrypoint_diagnostics") or []
                        if isinstance(item, dict) and item.get("status") == "executed"
                    ]
                ),
            }
        ],
    }
    state_updates = control.get("state_updates") if isinstance(control.get("state_updates"), dict) else {}
    for key in ("pheromone_field_snapshot", "stop_signals"):
        if key in state_updates:
            updated[key] = state_updates[key]
    if state_updates.get("signal_resolution_report"):
        updated["signal_resolution_report"] = state_updates["signal_resolution_report"]
    return merge_metadata(updated, domain_workflow=trace)


def build_generic_workflow_trace(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or workflow.get("graph_mode") or "generic-workflow")
    ordered_nodes = [str(item) for item in workflow.get("ordered_nodes") or [] if str(item).strip()]
    node_policy = workflow.get("node_policy") if isinstance(workflow.get("node_policy"), dict) else {}
    node_outputs = generic_node_outputs(ordered_nodes, node_policy=node_policy)
    entrypoint_report = execute_node_entrypoints(
        state,
        result,
        workflow=workflow,
        ordered_nodes=ordered_nodes,
    )
    node_outputs.update(entrypoint_report["node_outputs"])
    return {
        "schema_version": GENERIC_WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "capability_id": workflow.get("capability_id"),
        "graph_mode": str(workflow.get("graph_mode") or "generic_swarm_workflow"),
        "ordered_nodes": ordered_nodes,
        "required_protocols": [str(item) for item in workflow.get("required_protocols") or []],
        "writer_contract": workflow.get("writer_contract"),
        "data_contract": workflow.get("data_contract") if isinstance(workflow.get("data_contract"), dict) else {},
        "evidence_adapter": workflow.get("evidence_adapter") if isinstance(workflow.get("evidence_adapter"), dict) else {},
        "output_contract": workflow.get("output_contract") if isinstance(workflow.get("output_contract"), dict) else {},
        "runtime_support": workflow.get("runtime_support") if isinstance(workflow.get("runtime_support"), dict) else {},
        "node_policy": node_policy,
        "node_entrypoints": workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {},
        "node_outputs": node_outputs,
        "entrypoint_diagnostics": entrypoint_report["diagnostics"],
        "writer_policy": {
            "contract": workflow.get("writer_contract"),
            "source": "capability_workflow_descriptor",
        },
        "status": "executed" if entrypoint_report["executed_count"] else "planned",
        "source": "generic_capability_workflow",
        "task": state.get("task") or result.get("task"),
    }


def build_deferred_generic_workflow_trace(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or workflow.get("graph_mode") or "generic-workflow")
    ordered_nodes = [str(item) for item in workflow.get("ordered_nodes") or [] if str(item).strip()]
    node_policy = workflow.get("node_policy") if isinstance(workflow.get("node_policy"), dict) else {}
    return {
        "schema_version": GENERIC_WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "capability_id": workflow.get("capability_id"),
        "graph_mode": str(workflow.get("graph_mode") or "generic_swarm_workflow"),
        "ordered_nodes": ordered_nodes,
        "required_protocols": [str(item) for item in workflow.get("required_protocols") or []],
        "writer_contract": workflow.get("writer_contract"),
        "data_contract": workflow.get("data_contract") if isinstance(workflow.get("data_contract"), dict) else {},
        "evidence_adapter": workflow.get("evidence_adapter") if isinstance(workflow.get("evidence_adapter"), dict) else {},
        "output_contract": workflow.get("output_contract") if isinstance(workflow.get("output_contract"), dict) else {},
        "runtime_support": workflow.get("runtime_support") if isinstance(workflow.get("runtime_support"), dict) else {},
        "node_policy": node_policy,
        "node_entrypoints": workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {},
        "node_outputs": generic_node_outputs(ordered_nodes, node_policy=node_policy),
        "entrypoint_diagnostics": [],
        "writer_policy": {
            "contract": workflow.get("writer_contract"),
            "source": "capability_workflow_descriptor",
        },
        "status": "deferred",
        "deferred_to_graph_node": "workflow_host",
        "source": "generic_capability_workflow",
        "task": state.get("task") or result.get("task"),
    }


async def build_generic_workflow_trace_async(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or workflow.get("graph_mode") or "generic-workflow")
    ordered_nodes = [str(item) for item in workflow.get("ordered_nodes") or [] if str(item).strip()]
    node_policy = workflow.get("node_policy") if isinstance(workflow.get("node_policy"), dict) else {}
    node_outputs = generic_node_outputs(ordered_nodes, node_policy=node_policy)
    entrypoint_report = await execute_node_entrypoints_async(
        state,
        result,
        workflow=workflow,
        ordered_nodes=ordered_nodes,
    )
    node_outputs.update(entrypoint_report["node_outputs"])
    return {
        "schema_version": GENERIC_WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "capability_id": workflow.get("capability_id"),
        "graph_mode": str(workflow.get("graph_mode") or "generic_swarm_workflow"),
        "ordered_nodes": ordered_nodes,
        "required_protocols": [str(item) for item in workflow.get("required_protocols") or []],
        "writer_contract": workflow.get("writer_contract"),
        "data_contract": workflow.get("data_contract") if isinstance(workflow.get("data_contract"), dict) else {},
        "evidence_adapter": workflow.get("evidence_adapter") if isinstance(workflow.get("evidence_adapter"), dict) else {},
        "output_contract": workflow.get("output_contract") if isinstance(workflow.get("output_contract"), dict) else {},
        "runtime_support": workflow.get("runtime_support") if isinstance(workflow.get("runtime_support"), dict) else {},
        "node_policy": node_policy,
        "node_entrypoints": workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {},
        "node_outputs": node_outputs,
        "entrypoint_diagnostics": entrypoint_report["diagnostics"],
        "writer_policy": {
            "contract": workflow.get("writer_contract"),
            "source": "capability_workflow_descriptor",
        },
        "status": "executed" if entrypoint_report["executed_count"] else "planned",
        "source": "generic_capability_workflow",
        "task": state.get("task") or result.get("task"),
    }


def generic_workflow_plan(result: dict[str, Any], *, workflow: dict[str, Any]) -> list[dict[str, Any]]:
    existing = [step for step in result.get("plan") or [] if isinstance(step, dict)]
    ordered_nodes = [str(item) for item in workflow.get("ordered_nodes") or [] if str(item).strip()]
    generic_steps = []
    for node in ordered_nodes:
        if node in {"orchestrator", "writer", "final_judge", "quorum"}:
            continue
        if any(str(step.get("id") or "") == node for step in existing):
            continue
        generic_steps.append(
            {
                "id": node,
                "title": node.replace("_", " ").title(),
                "objective": f"Execute capability-declared workflow node {node}.",
                "source": "capability_workflow_descriptor",
            }
        )
    return existing + generic_steps


def generic_node_outputs(ordered_nodes: list[str], *, node_policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = {}
    for node in ordered_nodes:
        if node in {"orchestrator", "writer", "final_judge", "quorum"}:
            continue
        policy = node_policy.get(node) if isinstance(node_policy.get(node), dict) else {}
        outputs[node] = {
            "status": "planned",
            "required": bool(policy.get("required", True)),
            "source": "capability_workflow_descriptor",
        }
    return outputs


def execute_node_entrypoints(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    ordered_nodes: list[str],
) -> dict[str, Any]:
    raw_entrypoints = workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {}
    if not raw_entrypoints:
        return {"node_outputs": {}, "diagnostics": [], "executed_count": 0}
    capability_id = workflow_capability_id(workflow)
    manifest = CapabilityRegistry().get(capability_id) if capability_id else None
    diagnostics = []
    outputs: dict[str, dict[str, Any]] = {}
    executed_count = 0
    if manifest is None:
        return {
            "node_outputs": {},
            "diagnostics": [
                {
                    "status": "invalid",
                    "reason": "missing capability manifest for node entrypoints",
                    "capability_id": capability_id,
                }
            ],
            "executed_count": 0,
        }
    for node in ordered_nodes:
        entrypoint = str(raw_entrypoints.get(node) or "").strip()
        if not entrypoint:
            continue
        try:
            output = execute_node_entrypoint(
                manifest=manifest,
                entrypoint=entrypoint,
                node=node,
                state=state,
                result=result,
                workflow=workflow,
            )
            outputs[node] = output
            diagnostics.append({"node": node, "entrypoint": entrypoint, "status": "executed"})
            executed_count += 1
        except CapabilityEntrypointError as exc:
            diagnostics.append({"node": node, "entrypoint": entrypoint, "status": "invalid", "error": str(exc)})
            outputs[node] = {"status": "entrypoint_error", "error": str(exc), "source": "capability_workflow_descriptor"}
    return {"node_outputs": outputs, "diagnostics": diagnostics, "executed_count": executed_count}


async def execute_node_entrypoints_async(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    ordered_nodes: list[str],
) -> dict[str, Any]:
    raw_entrypoints = workflow.get("node_entrypoints") if isinstance(workflow.get("node_entrypoints"), dict) else {}
    if not raw_entrypoints:
        return {"node_outputs": {}, "diagnostics": [], "executed_count": 0}
    capability_id = workflow_capability_id(workflow)
    manifest = CapabilityRegistry().get(capability_id) if capability_id else None
    diagnostics = []
    outputs: dict[str, dict[str, Any]] = {}
    executed_count = 0
    if manifest is None:
        return {
            "node_outputs": {},
            "diagnostics": [
                {
                    "status": "invalid",
                    "reason": "missing capability manifest for node entrypoints",
                    "capability_id": capability_id,
                }
            ],
            "executed_count": 0,
        }
    for node in ordered_nodes:
        entrypoint = str(raw_entrypoints.get(node) or "").strip()
        if not entrypoint:
            continue
        try:
            output = await execute_node_entrypoint_async(
                manifest=manifest,
                entrypoint=entrypoint,
                node=node,
                state=state,
                result=result,
                workflow=workflow,
            )
            outputs[node] = output
            diagnostics.append({"node": node, "entrypoint": entrypoint, "status": "executed"})
            executed_count += 1
        except CapabilityEntrypointError as exc:
            diagnostics.append({"node": node, "entrypoint": entrypoint, "status": "invalid", "error": str(exc)})
            outputs[node] = {"status": "entrypoint_error", "error": str(exc), "source": "capability_workflow_descriptor"}
    return {"node_outputs": outputs, "diagnostics": diagnostics, "executed_count": executed_count}


def execute_node_entrypoint(
    *,
    manifest: Any,
    entrypoint: str,
    node: str,
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    if ":" not in entrypoint:
        raise CapabilityEntrypointError(f"{manifest.id}.{node} must use path.py:function syntax")
    path_text, function_name = entrypoint.split(":", 1)
    module_path = safe_entrypoint_path(manifest, path_text)
    if not module_path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.{node} path does not exist: {module_path}")
    function = load_function(module_path, function_name)
    kwargs = accepted_kwargs(
        function,
        {
            "state": state,
            "result": result,
            "workflow": workflow,
            "node": node,
        },
    )
    output = function(**kwargs)
    if inspect.isawaitable(output):
        close = getattr(output, "close", None)
        if callable(close):
            close()
        raise CapabilityEntrypointError(f"{manifest.id}.{node} is async; use async workflow execution")
    if not isinstance(output, dict):
        raise CapabilityEntrypointError(f"{manifest.id}.{node} returned {type(output).__name__}, expected dict")
    return {
        **output,
        "source": output.get("source") or "capability_node_entrypoint",
        "node": output.get("node") or node,
    }


async def execute_node_entrypoint_async(
    *,
    manifest: Any,
    entrypoint: str,
    node: str,
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    if ":" not in entrypoint:
        raise CapabilityEntrypointError(f"{manifest.id}.{node} must use path.py:function syntax")
    path_text, function_name = entrypoint.split(":", 1)
    module_path = safe_entrypoint_path(manifest, path_text)
    if not module_path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.{node} path does not exist: {module_path}")
    function = load_function(module_path, function_name)
    kwargs = accepted_kwargs(
        function,
        {
            "state": state,
            "result": result,
            "workflow": workflow,
            "node": node,
        },
    )
    output = function(**kwargs)
    if inspect.isawaitable(output):
        output = await output
    if not isinstance(output, dict):
        raise CapabilityEntrypointError(f"{manifest.id}.{node} returned {type(output).__name__}, expected dict")
    return {
        **output,
        "source": output.get("source") or "capability_node_entrypoint",
        "node": output.get("node") or node,
    }


def accepted_kwargs(function: Any, values: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(function)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return values
    return {key: value for key, value in values.items() if key in signature.parameters}


def workflow_capability_id(workflow: dict[str, Any]) -> str:
    for key in ("capability_id", "capability"):
        text = str(workflow.get(key) or "").strip()
        if text:
            return text
    workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or "").strip()
    if CapabilityRegistry().get(workflow_id) is not None:
        return workflow_id
    return ""


def attach_control_loop_trace(workflow: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    node_outputs = dict(workflow.get("node_outputs") if isinstance(workflow.get("node_outputs"), dict) else {})
    node_outputs["generic_swarm_control_loop"] = {
        "status": control.get("status"),
        "schema_version": control.get("schema_version"),
        "activated_agents": control.get("activated_agents", []),
        "recovery_statuses": [
            item.get("status")
            for item in control.get("recovery_traces") or []
            if isinstance(item, dict)
        ],
        "committed_candidate": committed_candidate_id(control.get("quorum_trace")),
        "outcome_feedback": control.get("outcome_feedback", {}),
    }
    return {
        **workflow,
        "status": control.get("status") or workflow.get("status"),
        "gate_status": {
            "blocked": control.get("status") == "blocked",
            "status": control.get("status"),
        },
        "node_outputs": node_outputs,
        "control_loop_status": control.get("status"),
    }


def committed_candidate_id(quorum: Any) -> str | None:
    if not isinstance(quorum, dict):
        return None
    candidate = quorum.get("committed_candidate")
    if not isinstance(candidate, dict):
        return None
    return candidate.get("id") or candidate.get("label")


def domain_workflow_from_state(state: dict[str, Any]) -> dict[str, Any]:
    workflow = state.get("domain_workflow") if isinstance(state.get("domain_workflow"), dict) else {}
    if workflow:
        return workflow
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    workflow = metadata.get("domain_workflow") if isinstance(metadata.get("domain_workflow"), dict) else {}
    return workflow


def first_item(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return {}


def merge_metadata(result: dict[str, Any], **items: Any) -> dict[str, Any]:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {**result, "metadata": {**metadata, **items}}
