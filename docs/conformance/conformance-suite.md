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
the same loader used by the reference runtime. It also checks the minimum public
profile needed for a governed capability to prove that protocol, not agents,
owns candidate commitment, recovery, output permission, and trace lineage.

Future conformance levels should add sandbox checks, signature checks, fixture
execution, and trace replay.

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
core_runtime_domain_leakage_guard
```

## Basic Profile Semantics

- `candidate_declaration`: quorum and recovery failure candidates must be
  protocol-declared candidates.
- `quorum_fallback`: quorum must declare a fallback candidate, and that
  candidate must be marked `safe_fallback`.
- `recovery_protocol`: recovery declarations must include trigger targets,
  protocol-selectable roles/tags/tools, a success condition, and a failure
  candidate.
- `tool_contract`: tools, connections, and protocol tool policies must be
  backed by explicit manifest permissions.
- `output_contract`: writer cannot create facts; candidate-based outputs must
  require FinalJudge `committed_candidate` checks; raw data cannot be allowed in
  the public final output profile.
- `trace_contract`: protocols must declare traceable targets and at least one
  policy source such as candidates, quorum, recovery, evidence, tools, or
  output policy.
- `domain_leakage_guard`: the public ABI surface must stay domain-neutral.
- `core_runtime_domain_leakage_guard`: OSKernel, RuntimeMaterializer, quorum,
  recovery, control loop, writer, final judge, and output-chain surfaces must
  stay domain-neutral; provider/domain behavior belongs in capabilities,
  drivers, examples, fixtures, or explicit legacy compatibility shims.

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
