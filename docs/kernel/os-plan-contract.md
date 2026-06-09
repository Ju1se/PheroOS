# OSPlan Contract

`OSPlan` is the PheroOS kernel planning artifact. It records what the run needs,
what is available, what must be confirmed, and whether runtime materialization
is safe.

```json
{
  "schema_version": "pheroos.os_plan.v0.1",
  "run_id": "run-123",
  "tenant_id": "default",
  "intent": "generic_research",
  "required_capability_types": ["research", "evidence"],
  "enabled_capabilities": ["evidence-research"],
  "missing_capabilities": [],
  "active_connections": ["model_provider"],
  "permission_grants": [
    {"capability_id": "evidence-research", "permission_grants": ["data:read"]}
  ],
  "tool_exposure": [
    {"tool": "provider_web_search", "granted": true}
  ],
  "agent_plan": {},
  "swarm_plan": {},
  "runtime_ready": true,
  "degraded_reasons": []
}
```

The OS kernel may infer capability requirements and permission needs. It must
not perform domain reasoning or bypass protocol governance.
