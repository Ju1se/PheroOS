# Migration From Current PheroOS

This repository already contains a large PheroOS governance layer. The open
protocol migration is additive: preserve useful compatibility while moving
authority into manifest-declared protocol contracts.

## Compatibility Aliases

- `wrds_result` remains as a WRDS-specific public alias.
- `data_source_results` and `provider_results` are the preferred generic
  provider result fields.
- `committee_outputs` and `committee_decision` remain for legacy value
  investing clients.
- `agent_outputs` and `agent_decision` are the preferred generic agent fields.

## Where Domain Code Belongs

- WRDS provider logic: `tools/wrds_tools.py` and
  `capabilities/wrds-financial-data/`.
- Value investing protocol and runtime nodes:
  `capabilities/value-investing-research/`.
- Generic governance: `runtime/swarm/*`.
- Compatibility shims: explicitly named `legacy_*` modules.

## Migration Checklist

1. Add a capability manifest with protocol declarations.
2. Declare candidates, targets, tool policy, evidence policy, recovery, output,
   and trace needs in the manifest.
3. Add provider descriptors via `data_sources` when the capability supplies
   data.
4. Route tools through `ToolRegistry`.
5. Keep runtime agents behind model gateway boundaries.
6. Add tests that prove the capability runs without editing core graph,
   quorum, recovery, writer, or final judge modules.
