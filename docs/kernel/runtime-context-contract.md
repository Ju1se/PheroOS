# RuntimeContext Contract

`RuntimeContext` is the hot materialization boundary. It converts an OS plan,
active tenant connections, capability state, permission grants, tool policy,
driver descriptors, and agent manifests into an executable runtime context.

```json
{
  "schema_version": "pheroos.runtime_context.v0.1",
  "tenant_id": "default",
  "protocols": [],
  "capabilities": [],
  "agents": [],
  "tools": [],
  "drivers": [],
  "permission_grants": [],
  "connection_handles": [],
  "trace_policy": {},
  "validation_issues": []
}
```

RuntimeContext may expose compatibility fields for the reference runtime, but
new integrations should prefer protocol, driver, and generic agent/provider
fields over domain-specific aliases.
