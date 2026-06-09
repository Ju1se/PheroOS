# Tool Contract

Tools are explicit, structured execution boundaries. Runtime agents must not
instantiate provider SDKs, shell commands, web clients, database clients, or
model providers directly.

## Required Properties

Each tool should expose:

- `name`
- `description`
- `args`
- `required_permissions`
- `required_connections`
- `risk_level`
- structured success/failure result

`runtime/tool_registry.py` is the default execution boundary. Capability
manifests and active protocol `tool_policy` decide which tool names are exposed
to a run.

## Provider Tools

Provider adapters belong in `tools/*` or capability-owned runtime nodes.
Provider results should be normalized to `DataSourceResult` when they influence
governance, evidence, or output.

Tool failures must remain data:

```json
{
  "ok": false,
  "data": {"tool": "mock_lookup", "query": "artifact-1"},
  "error": "mock provider is unavailable"
}
```

The runtime may use failures for recovery or degraded output, but agents may
not reinterpret tool failures as verified facts.
