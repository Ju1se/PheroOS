# Open Multi-Agent Protocol Examples

These examples are public reference patterns for adding capabilities without
editing the core runtime.

## Minimal Toy Capability

Use [minimal-toy-protocol.md](../protocol/examples/minimal-toy-protocol.md)
when validating a non-domain workflow with no external connection.

## Mock Tool Provider

A mock provider should declare a normal tool in `tools` and return structured
`ToolResult` data. If the tool supplies evidence or data that affects
governance, normalize it into `DataSourceResult`.

```json
{
  "provider_id": "mock-provider",
  "source_kind": "fixture_provider",
  "dataset_kind": "toy_evidence",
  "normalized_payload": {"status": "available", "record_count": 1},
  "provenance": {"tool_name": "mock_lookup", "capability_id": "toy-review"}
}
```

## Stop Signal

Declare stop targets in protocol, then let governance enforce them:

```json
{
  "stop_signal_policy": {
    "blocked_targets": ["output:publish"],
    "blocking_authority_required": 2,
    "resolution_policy": {"mode": "recover_or_degrade"}
  }
}
```

## Recovery

Recovery recruits by role and capability tags, not by hard-coded names:

```json
{
  "recovery_protocols": [
    {
      "recovery_id": "citation_recovery",
      "trigger_targets": ["gate:research_citation_audit"],
      "allowed_agent_roles": ["citation_auditor"],
      "required_tools": ["approved_source_fetch"],
      "recovery_failure_candidate": "candidate:research:insufficient_sources"
    }
  ]
}
```

## Reference Capabilities

- Toy protocol: `capabilities/toy-review/`
- Generic research: `capabilities/evidence-research/` and
  `capabilities/web-research/`
- WRDS provider adapter: `capabilities/wrds-financial-data/`
- Value investing decision protocol: `capabilities/value-investing-research/`
