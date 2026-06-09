from __future__ import annotations

import inspect
from typing import Any

from runtime.capability_registry import CapabilityRegistry
from runtime.capability_runtime import CapabilityEntrypointError, load_capability_descriptor, load_function, safe_entrypoint_path
from runtime.swarm.stop_policy import stop_policy_rules, stop_signal_policy_from_state
from runtime.swarm.target_registry import canonical_target
from runtime.workflows.legacy_dispatch import legacy_builtin_graph_mode, legacy_workflow_handler
from runtime.workflows.routing import workflow_descriptor_from_state, workflow_descriptors_from_state


def apply_domain_workflow_plan(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    """Apply capability-owned workflow execution metadata to an orchestrator result.

    This is intentionally a thin dispatcher. The graph runtime remains generic:
    it asks enabled capabilities whether they own a domain workflow, then the
    capability-specific workflow module returns plan and trace metadata.
    """

    workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state({**state, **result}))
    graph_mode = str(workflow.get("graph_mode") or "").strip()
    if not graph_mode:
        return result
    entrypoint_result = execute_orchestration_entrypoint_if_declared(
        state,
        result,
        workflow=workflow,
        tool_registry=tool_registry,
    )
    if entrypoint_result is not None:
        return entrypoint_result
    fallback_result = execute_legacy_orchestration_fallback(state, result, workflow=workflow, graph_mode=graph_mode)
    if fallback_result is not None:
        return fallback_result
    if not legacy_builtin_graph_mode(graph_mode):
        from runtime.workflows.generic_swarm_workflow import augment_orchestration_result

        return augment_orchestration_result(state, result, workflow=workflow, tool_registry=tool_registry)
    return result


async def apply_domain_workflow_plan_async(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    """Async-aware workflow plan bridge for the graph runtime."""

    workflow = workflow_with_manifest_defaults(workflow_descriptor_from_state({**state, **result}))
    graph_mode = str(workflow.get("graph_mode") or "").strip()
    if not graph_mode:
        return result
    entrypoint_result = await execute_orchestration_entrypoint_if_declared_async(
        state,
        result,
        workflow=workflow,
        tool_registry=tool_registry,
    )
    if entrypoint_result is not None:
        return entrypoint_result
    fallback_result = execute_legacy_orchestration_fallback(state, result, workflow=workflow, graph_mode=graph_mode)
    if fallback_result is not None:
        return fallback_result
    if not legacy_builtin_graph_mode(graph_mode):
        from runtime.workflows.generic_swarm_workflow import augment_orchestration_result_async

        return await augment_orchestration_result_async(
            state,
            result,
            workflow=workflow,
            tool_registry=tool_registry,
        )
    return result


def execute_legacy_orchestration_fallback(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    graph_mode: str,
) -> dict[str, Any] | None:
    handler = legacy_workflow_handler(graph_mode, kind="orchestration")
    if handler is None:
        return None
    output = handler(state, result, workflow=workflow)
    return attach_workflow_orchestration_trace(
        output,
        legacy_workflow_trace_event(graph_mode=graph_mode, kind="orchestration"),
    )


def legacy_workflow_trace_event(*, graph_mode: str, kind: str) -> dict[str, Any]:
    return {
        "graph_mode": graph_mode,
        "kind": kind,
        "status": "executed",
        "source": "legacy_graph_mode_workflow_fallback",
    }


def execute_orchestration_entrypoint_if_declared(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any] | None:
    entrypoint = str(workflow.get("orchestration_entrypoint") or "").strip()
    if not entrypoint:
        return None
    manifest = manifest_for_workflow(workflow, entrypoint_kind="orchestration_entrypoint")
    output = execute_workflow_entrypoint(
        manifest=manifest,
        entrypoint=entrypoint,
        kind="orchestration_entrypoint",
        state=state,
        result=result,
        workflow=workflow,
        tool_registry=tool_registry,
    )
    return attach_workflow_orchestration_trace(
        output,
        {
            "capability_id": manifest.id,
            "entrypoint": entrypoint,
            "status": "executed",
            "source": "capability_workflow_orchestration_entrypoint",
        },
    )


async def execute_orchestration_entrypoint_if_declared_async(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any] | None:
    entrypoint = str(workflow.get("orchestration_entrypoint") or "").strip()
    if not entrypoint:
        return None
    manifest = manifest_for_workflow(workflow, entrypoint_kind="orchestration_entrypoint")
    output = await execute_workflow_entrypoint_async(
        manifest=manifest,
        entrypoint=entrypoint,
        kind="orchestration_entrypoint",
        state=state,
        result=result,
        workflow=workflow,
        tool_registry=tool_registry,
    )
    return attach_workflow_orchestration_trace(
        output,
        {
            "capability_id": manifest.id,
            "entrypoint": entrypoint,
            "status": "executed",
            "source": "capability_workflow_orchestration_entrypoint",
        },
    )


def manifest_for_workflow(workflow: dict[str, Any], *, entrypoint_kind: str) -> Any:
    capability_id = str(workflow.get("capability_id") or "").strip()
    manifest = CapabilityRegistry().get(capability_id) if capability_id else None
    if manifest is None:
        raise CapabilityEntrypointError(f"{entrypoint_kind} has no capability manifest")
    return manifest


def workflow_with_manifest_defaults(workflow: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(workflow, dict) or not workflow:
        return workflow
    manifest = manifest_for_workflow_id(workflow)
    if manifest is None:
        return workflow
    try:
        declared = load_capability_descriptor(manifest).get("entrypoints", {}).get("workflow")
    except CapabilityEntrypointError:
        return workflow
    if not isinstance(declared, dict) or not declared:
        return workflow
    merged = {**declared, **workflow}
    for key, value in declared.items():
        if descriptor_field_missing(workflow.get(key)):
            merged[key] = value
    if merged != workflow:
        merged.setdefault("descriptor_backfill_source", "capability_workflow_manifest")
    return merged


def manifest_for_workflow_id(workflow: dict[str, Any]) -> Any | None:
    candidates = [
        workflow.get("capability_id"),
        workflow.get("workflow_id"),
        workflow.get("id"),
    ]
    registry = CapabilityRegistry()
    for candidate in candidates:
        capability_id = str(candidate or "").strip()
        if not capability_id:
            continue
        manifest = registry.get(capability_id)
        if manifest is not None:
            return manifest
    return None


def descriptor_field_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def execute_workflow_entrypoint(
    *,
    manifest: Any,
    entrypoint: str,
    kind: str,
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    function = load_workflow_entrypoint_function(manifest=manifest, entrypoint=entrypoint, kind=kind)
    from runtime.workflows.generic_swarm_workflow import accepted_kwargs

    output = function(
        **accepted_kwargs(
            function,
            {
                "state": state,
                "result": result,
                "workflow": workflow,
                "tool_registry": tool_registry,
            },
        )
    )
    if inspect.isawaitable(output):
        close = getattr(output, "close", None)
        if callable(close):
            close()
        raise CapabilityEntrypointError(f"{manifest.id}.{kind} is async; use async workflow execution")
    return normalize_workflow_entrypoint_output(manifest=manifest, output=output, kind=kind)


async def execute_workflow_entrypoint_async(
    *,
    manifest: Any,
    entrypoint: str,
    kind: str,
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    function = load_workflow_entrypoint_function(manifest=manifest, entrypoint=entrypoint, kind=kind)
    from runtime.workflows.generic_swarm_workflow import accepted_kwargs

    output = function(
        **accepted_kwargs(
            function,
            {
                "state": state,
                "result": result,
                "workflow": workflow,
                "tool_registry": tool_registry,
            },
        )
    )
    if inspect.isawaitable(output):
        output = await output
    return normalize_workflow_entrypoint_output(manifest=manifest, output=output, kind=kind)


def load_workflow_entrypoint_function(*, manifest: Any, entrypoint: str, kind: str) -> Any:
    if ":" not in entrypoint:
        raise CapabilityEntrypointError(f"{manifest.id}.{kind} must use path.py:function syntax")
    path_text, function_name = entrypoint.split(":", 1)
    module_path = safe_entrypoint_path(manifest, path_text)
    if not module_path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.{kind} path does not exist: {module_path}")
    return load_function(module_path, function_name)


def normalize_workflow_entrypoint_output(*, manifest: Any, output: Any, kind: str) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise CapabilityEntrypointError(f"{manifest.id}.{kind} returned {type(output).__name__}, expected dict")
    return output


def attach_workflow_orchestration_trace(result: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    trace = [*list(result.get("workflow_orchestration_trace") or []), event]
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {
        **result,
        "workflow_orchestration_trace": trace,
        "metadata": {**metadata, "workflow_orchestration_trace": trace},
    }


def apply_domain_workflow_plan_adapters(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    updated = dict(result)
    for workflow in workflow_descriptors_from_state({**state, **result}):
        entrypoints = workflow.get("plan_entrypoints") if isinstance(workflow.get("plan_entrypoints"), dict) else {}
        if not entrypoints:
            continue
        capability_id = str(workflow.get("capability_id") or "").strip()
        manifest = CapabilityRegistry().get(capability_id) if capability_id else None
        if manifest is None:
            diagnostics.append(
                {
                    "adapter": "",
                    "status": "invalid",
                    "capability_id": capability_id,
                    "error": "missing capability manifest for plan entrypoints",
                }
            )
            continue
        for adapter, entrypoint in entrypoints.items():
            adapter_name = str(adapter)
            entrypoint_text = str(entrypoint or "").strip()
            try:
                output = execute_plan_entrypoint(
                    manifest=manifest,
                    entrypoint=entrypoint_text,
                    adapter=adapter_name,
                    state=state,
                    result=updated,
                    workflow=workflow,
                )
                if isinstance(output.get("plan"), list):
                    updated["plan"] = output["plan"]
                for key, value in output.items():
                    if key not in {"plan", "diagnostics", "status", "handled_tools"}:
                        updated.setdefault("plan_adapter_outputs", {})[adapter_name] = {
                            **updated.get("plan_adapter_outputs", {}).get(adapter_name, {}),
                            key: value,
                        }
                diagnostics.append(
                    {
                        "adapter": adapter_name,
                        "capability_id": capability_id,
                        "entrypoint": entrypoint_text,
                        "status": "executed",
                        "handled_tools": list(output.get("handled_tools") or []),
                        "result_status": output.get("status"),
                    }
                )
            except CapabilityEntrypointError as exc:
                diagnostics.append(
                    {
                        "adapter": adapter_name,
                        "capability_id": capability_id,
                        "entrypoint": entrypoint_text,
                        "status": "invalid",
                        "error": str(exc),
                    }
                )
    return attach_plan_adapter_trace(updated, diagnostics) if diagnostics else result


def execute_plan_entrypoint(
    *,
    manifest: Any,
    entrypoint: str,
    adapter: str,
    state: dict[str, Any],
    result: dict[str, Any],
    workflow: dict[str, Any],
) -> dict[str, Any]:
    if ":" not in entrypoint:
        raise CapabilityEntrypointError(f"{manifest.id}.{adapter} must use path.py:function syntax")
    path_text, function_name = entrypoint.split(":", 1)
    module_path = safe_entrypoint_path(manifest, path_text)
    if not module_path.exists():
        raise CapabilityEntrypointError(f"{manifest.id}.{adapter} path does not exist: {module_path}")
    function = load_function(module_path, function_name)
    from runtime.workflows.generic_swarm_workflow import accepted_kwargs

    output = function(
        **accepted_kwargs(
            function,
            {
                "state": state,
                "result": result,
                "workflow": workflow,
                "adapter": adapter,
            },
        )
    )
    if not isinstance(output, dict):
        raise CapabilityEntrypointError(f"{manifest.id}.{adapter} returned {type(output).__name__}, expected dict")
    return output


def attach_plan_adapter_trace(result: dict[str, Any], diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    trace = [*list(result.get("plan_adapter_trace") or []), *diagnostics]
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {
        **result,
        "plan_adapter_trace": trace,
        "metadata": {**metadata, "plan_adapter_trace": trace},
    }


def plan_adapter_handled_tool(result: dict[str, Any], tool_name: str) -> bool:
    for item in result.get("plan_adapter_trace") or []:
        if not isinstance(item, dict) or item.get("status") != "executed":
            continue
        if tool_name in {str(tool) for tool in item.get("handled_tools") or []}:
            return True
    return False


def apply_domain_workflow_execution_results(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    tool_registry: Any | None = None,
) -> dict[str, Any]:
    """Attach deterministic domain-node outputs after generic executor work.

    Domain workflows still use the shared LangGraph executor. This bridge lets
    capability-owned node bodies interpret execution evidence without adding
    hardcoded business logic to graph.py.
    """

    workflow = workflow_with_manifest_defaults(domain_workflow_from_state({**state, **result}))
    graph_mode = str(workflow.get("graph_mode") or "").strip()
    entrypoint_result = execute_execution_entrypoint_if_declared(
        state,
        result,
        workflow=workflow,
        tool_registry=tool_registry,
    )
    if entrypoint_result is not None:
        return attach_domain_workflow_stop_signals(state, entrypoint_result)
    fallback_result = execute_legacy_execution_fallback(state, result, graph_mode=graph_mode)
    if fallback_result is not None:
        return attach_domain_workflow_stop_signals(state, fallback_result)
    if graph_mode and not legacy_builtin_graph_mode(graph_mode):
        from runtime.workflows.generic_swarm_workflow import augment_execution_result

        return attach_domain_workflow_stop_signals(
            state,
            augment_execution_result(state, result, tool_registry=tool_registry),
        )
    return result


def execute_legacy_execution_fallback(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    graph_mode: str,
) -> dict[str, Any] | None:
    handler = legacy_workflow_handler(graph_mode, kind="execution")
    if handler is None:
        return None
    output = handler(state, result)
    return attach_workflow_execution_trace(
        output,
        legacy_workflow_trace_event(graph_mode=graph_mode, kind="execution"),
    )


def execute_execution_entrypoint_if_declared(
    state: dict[str, Any],
    result: dict[str, Any],
    *,
    workflow: dict[str, Any],
    tool_registry: Any | None = None,
) -> dict[str, Any] | None:
    entrypoint = str(workflow.get("execution_entrypoint") or "").strip()
    if not entrypoint:
        return None
    manifest = manifest_for_workflow(workflow, entrypoint_kind="execution_entrypoint")
    output = execute_workflow_entrypoint(
        manifest=manifest,
        entrypoint=entrypoint,
        kind="execution_entrypoint",
        state=state,
        result=result,
        workflow=workflow,
        tool_registry=tool_registry,
    )
    return attach_workflow_execution_trace(
        output,
        {
            "capability_id": manifest.id,
            "entrypoint": entrypoint,
            "status": "executed",
            "source": "capability_workflow_execution_entrypoint",
        },
    )


def attach_workflow_execution_trace(result: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    trace = [*list(result.get("workflow_execution_trace") or []), event]
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {
        **result,
        "workflow_execution_trace": trace,
        "metadata": {**metadata, "workflow_execution_trace": trace},
    }


def attach_domain_workflow_stop_signals(state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    workflow = domain_workflow_from_state({**state, **result})
    gate_status = workflow.get("gate_status") if isinstance(workflow.get("gate_status"), dict) else {}
    if not bool(gate_status.get("blocked")):
        return result
    policy_state = {**state, **result}
    metadata = {}
    if isinstance(state.get("metadata"), dict):
        metadata.update(state["metadata"])
    if isinstance(result.get("metadata"), dict):
        metadata.update(result["metadata"])
    output = {**result, "metadata": metadata} if metadata else result
    if metadata:
        policy_state["metadata"] = metadata
    policy = stop_signal_policy_from_state(policy_state)
    targets = workflow_blocking_targets(policy)
    if not targets:
        return output
    existing = list(output.get("stop_signals") if isinstance(output.get("stop_signals"), list) else state.get("stop_signals") or [])
    seen_targets = {
        canonical_target(signal.get("target"))
        for signal in existing
        if isinstance(signal, dict) and (signal.get("blocking") or signal.get("verification_state") == "blocking")
    }
    additions = []
    for target in targets:
        canonical = canonical_target(target)
        if canonical in seen_targets:
            continue
        additions.append(domain_gate_stop_signal(workflow, gate_status, canonical))
        seen_targets.add(canonical)
    if not additions:
        return output
    return {**output, "stop_signals": [*existing, *additions]}


def workflow_blocking_targets(policy: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for rule in stop_policy_rules(policy):
        actions = {str(action) for action in rule.get("blocked_actions") or []}
        if not any(action.startswith(("writer:", "final_judge:")) for action in actions):
            continue
        for target in rule.get("trigger_targets") or []:
            canonical = canonical_target(target)
            if canonical and canonical not in targets:
                targets.append(canonical)
    return targets


def domain_gate_stop_signal(workflow: dict[str, Any], gate_status: dict[str, Any], target: str) -> dict[str, Any]:
    blockers = [str(item) for item in gate_status.get("blocking_gates") or [] if str(item).strip()]
    workflow_id = str(workflow.get("workflow_id") or workflow.get("graph_mode") or "domain_workflow")
    detail = ", ".join(blockers) if blockers else "domain workflow gate"
    return {
        "type": "stop_signal",
        "target": target,
        "canonical_target": target,
        "blocking": True,
        "verification_state": "blocking",
        "source_module": "domain_workflow",
        "source_agent": "domain_workflow",
        "content": f"{workflow_id} blocked {target}: {detail}.",
        "metadata": {
            "workflow_id": workflow_id,
            "graph_mode": workflow.get("graph_mode"),
            "blocking_gates": blockers,
            "gate_status": gate_status.get("status"),
        },
    }


def domain_workflow_from_state(state: dict[str, Any]) -> dict[str, Any]:
    workflow = state.get("domain_workflow") if isinstance(state.get("domain_workflow"), dict) else {}
    if workflow:
        return workflow_with_manifest_defaults(workflow)
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    workflow = metadata.get("domain_workflow") if isinstance(metadata.get("domain_workflow"), dict) else {}
    return workflow_with_manifest_defaults(workflow)


def available_tool_names(result: dict[str, Any]) -> set[str]:
    tools = result.get("tool_manifest") if isinstance(result.get("tool_manifest"), list) else []
    return {
        str(tool.get("name") or "")
        for tool in tools
        if isinstance(tool, dict)
        and tool.get("granted") is not False
        and tool.get("connection_granted") is not False
    }


def workflow_agents_by_type(state: dict[str, Any], agent_type: str) -> list[dict[str, Any]]:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    registry = metadata.get("agent_registry") if isinstance(metadata.get("agent_registry"), dict) else {}
    agents = registry.get("agents") if isinstance(registry.get("agents"), list) else []
    return [
        agent
        for agent in agents
        if isinstance(agent, dict) and str(agent.get("agent_type") or "") == agent_type
    ]


def merge_metadata(result: dict[str, Any], **items: Any) -> dict[str, Any]:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    return {**result, "metadata": {**metadata, **items}}
