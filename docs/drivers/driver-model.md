# PheroOS Driver Model

Drivers are provider boundaries. They return structured data or services to
the kernel but do not author conclusions.

## Driver Families

```text
ModelDriver
  provider, supported_models, context_limits, tool_call_support,
  streaming_support, auth_requirements, safety_metadata

ToolDriver
  tool_id, input_schema, output_schema, permissions, side_effect_class,
  network_policy, filesystem_policy, provenance_policy

DataProviderDriver
  provider_id, dataset_kind, coverage, freshness, license,
  entitlement_requirements, normalized_result_schema

StorageDriver
  event_log, trace_store, artifact_store, retention_policy, migration_policy

SecretStoreDriver
  backend, auth_method, rotation_policy, audit_policy
```

WRDS is a reference `DataProviderDriver` implemented through
`capabilities/wrds-financial-data/` and `tools/wrds_tools.py`. It is not a
kernel concept.
