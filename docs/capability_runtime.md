# Capability Runtime

Capabilities are the extension boundary for PheroOS. New domain behavior should
be declared in capability manifests and local entrypoints, not by adding
domain-specific branches to `runtime/graph.py`, `runtime/swarm/quorum.py`, or
`runtime/swarm/goal_router.py`.

## Loader Surface

The runtime loads capability metadata through:

- `runtime/capability_registry.py`
- `runtime/capability_runtime.py`
- `runtime/runtime_context.py`
- `runtime/workflows/loader.py`
- `runtime/swarm/protocol_loader.py`

Supported capability protocol locations are documented in
`docs/pheroos_protocol_manifest.md`.

## Entrypoints

Common entrypoints are declared under `capability.json`:

```json
{
  "entrypoints": {
    "workflow": "workflow.py:build_workflow_descriptor",
    "data_contract": "data_contract.py:build_data_contract_descriptor",
    "evidence_adapter": "evidence_adapter.py:build_evidence_adapter_descriptor",
    "runtime_nodes": "runtime_nodes.py:build_runtime_descriptor"
  }
}
```

Entrypoint paths are resolved relative to the capability directory and checked
by `safe_entrypoint_path`. Capability code must not call model providers, tools,
or shell commands directly; model calls go through `runtime/llm.py`, and tool
execution goes through `runtime/tool_registry.py`.

## Workflow Descriptors

Workflow descriptors can declare:

- `graph_mode`
- `graph_nodes`
- `ordered_nodes`
- `node_policy`
- `node_entrypoints`
- `plan_entrypoints`
- `orchestration_entrypoint`
- `execution_entrypoint`
- contract bundle entrypoints such as data/evidence/output/runtime support

Known graph nodes still live in the fixed LangGraph shell, but their methods
prefer active capability `node_entrypoints` before compatibility fallbacks.
Unknown non-specialized graph modes defer generic execution into the
`workflow_host` node, which runs capability-owned node entrypoints safely.

## Protocol Authority

Capability protocol sections declare governance truth:

- targets and target aliases
- candidates and quorum policy
- recovery protocols
- stop-signal rules and action markers
- evidence and output policies
- tool policy
- agent selection policy

The OS Kernel and GoalRouter read these declarations before legacy static
fallbacks. Fallbacks must be traceable as compatibility behavior.

## Adding A Capability Without Core Edits

1. Add `capabilities/<id>/capability.json`.
2. Declare `protocol` targets, candidates, recovery, quorum, stop-signal,
   evidence, output, tool, and agent-selection policies.
3. Add workflow/data/evidence/runtime entrypoints only when the capability needs
   executable local behavior.
4. Add agent manifests under `capabilities/<id>/agents/` if the capability owns
   specialist agents.
5. Add tests that enable the capability and prove routing, quorum, recovery,
   stop-signal, and output behavior without editing core routers.

The `toy-review` capability is the proof fixture for this pattern.
