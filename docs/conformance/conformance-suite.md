# PheroOS Conformance Suite

PheroOS conformance proves that a capability or driver can mount into the
kernel without editing core runtime files.

## CLI

```bash
pheroos validate capabilities/toy-review/capability.json
pheroos conformance capabilities/toy-review
pheroos-conformance capabilities/toy-review
```

The initial CLI validates capability manifests and protocol diagnostics through
the same loader used by the reference runtime. Future conformance levels should
add sandbox checks, signature checks, fixture execution, and trace replay.

## Initial Checks

```text
manifest_schema
protocol_validation
candidate_declaration
quorum_fallback
recovery_protocol
tool_contract
output_contract
trace_contract
domain_leakage_guard
```

## Compatibility Definition

A third-party capability is compatible when it can be:

- discovered by the capability registry;
- matched by OS planning;
- mounted into RuntimeContext;
- exposed through permission-gated tools/drivers;
- governed by declared targets, candidates, recovery, and output policies;
- traced with protocol rule lineage;
- tested without editing `graph.py`, quorum, recovery, writer, or final judge
  core modules.
