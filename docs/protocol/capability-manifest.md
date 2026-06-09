# Capability Manifest Contract

Capabilities are the extension boundary. A capability manifest declares what a
capability can provide; the OS kernel decides whether it is available in a
tenant/run, and the runtime materializer decides what is executable.

## Key Fields

```json
{
  "id": "toy-review",
  "name": "Toy Review",
  "version": "0.1.0",
  "description": "Review a toy artifact with protocol-governed evidence.",
  "capability_types": ["toy.review"],
  "permissions": ["data:read"],
  "required_connections": [],
  "tools": ["read_file"],
  "skills": [],
  "entrypoints": {
    "workflow": "workflow.py:build_workflow_descriptor",
    "runtime_nodes": "runtime_nodes.py:build_runtime_node_descriptor",
    "data_provider": "runtime_nodes.py:build_data_provider_descriptor"
  },
  "data_sources": [],
  "protocol": {}
}
```

`entrypoints` must stay inside the capability directory. Runtime descriptors
are loaded by `runtime/capability_runtime.py`.

## Data Providers

Capabilities that provide data should declare `data_sources` entries. The
runtime publishes these as `DataProviderDescriptor` records in
`RuntimeContext.data_source_registry`.

```json
{
  "provider_id": "mock-provider",
  "source_kind": "mock_data_provider",
  "dataset_kind": "toy_evidence",
  "normalized_result_schema": "open-multi-agent.data_source_result.v0.1",
  "coverage": {"scope": "local fixture"},
  "freshness": {"policy": "static_fixture"},
  "license": {"kind": "example"},
  "adapter_entrypoint": "runtime_nodes.py:build_data_provider_descriptor",
  "provenance_policy": {"include_tool_name": true}
}
```

Provider-specific public fields may remain as compatibility aliases. New
callers should prefer `data_source_results` and `provider_results`.
