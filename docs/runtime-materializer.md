# Runtime Materializer

The runtime materializer builds a tenant-scoped `RuntimeContext` for each run.
This is what makes connections and capabilities hot-effective without process
restart.

```text
active connections
+ enabled capabilities
+ selected agents
+ permission grants
+ model gateway
+ capability-scoped tool registry
+ data source registry
+ skill registry
-> RuntimeContext
```

## Validation

`RuntimeContext.validate()` returns dashboard-safe issues such as:

- missing model provider,
- missing WRDS connection,
- pending permission confirmation,
- enabled WRDS capability without registered WRDS tools,
- OS plan not runtime-ready.

Validation issues are included in run metadata for trace/debugging.

Blocking validation issues now trigger a hard preflight stop before LangGraph
execution. The runtime returns a PatrollerGate defect memo and does not call the
orchestrator model, tools, WRDS, committee agents, writer, or final judge. This
keeps missing model providers, missing WRDS credentials, disabled capability
dependencies, and not-ready OS plans in the control plane instead of letting
worker agents improvise around invalid runtime state.

For OS-materialized runs, `ToolRegistry` is filtered to the tools declared by
enabled capability manifests. A WRDS capability can expose WRDS tools, a web
research capability can expose web tools, and disabled or absent capabilities
cannot leave their tools visible in the runtime manifest.
