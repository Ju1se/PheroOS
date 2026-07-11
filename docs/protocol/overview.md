# Protocol ABI

`pheroos.protocol` defines the public manifest and validation surface for
governed runtimes.

The formal protocol-core specification is [SPEC.md](../../SPEC.md). Extension
boundaries are described in [extension-points.md](extension-points.md).
External runtime composition is described in
[runtime-integration.md](runtime-integration.md). Pheromone core simplification
and future adaptive runtime boundaries are described in
[adaptive-pheromone-core-plan.md](adaptive-pheromone-core-plan.md). The complete
audit-driven hardening and delivery plan is documented in
[hybrid-pheromone-full-hardening-plan.md](hybrid-pheromone-full-hardening-plan.md).

Protocol code is contract code. It declares what exists and validates whether a
manifest is structurally compatible with the protocol.

The capability manifest schema is a public ABI artifact. The loader rejects
unknown non-namespaced fields, invalid primitive shapes, and invalid collection
shapes before constructing typed manifest objects.

## Owned Surface

- capability manifests
- protocol manifests
- target declarations
- candidate declarations
- quorum policy
- collective decision policy
- recovery policy
- evidence policy
- output policy
- trace policy
- driver declarations
- extension metadata
- validation diagnostics

## Import Boundary

The protocol package must not import kernel, governance, driver, conformance,
CLI, examples, app runtime modules, provider frameworks, or tools.

## Invariants

- A manifest declares at least one target.
- A manifest declares at least one candidate.
- Every candidate references a declared target.
- Quorum fallback references a declared safe fallback candidate.
- Collective fallback references a declared safe fallback candidate, or defaults
  to the quorum fallback.
- Recovery trigger targets are declared.
- Recovery failure candidates are declared.
- Writer fact creation is not permitted.
- Agent fact creation is denied when the evidence policy forbids it.
- Trace policy includes lineage for block, commit, recovery, and output decisions.
- Swarm trace policy includes collective lineage when swarm behavior is declared.
- Hybrid pheromone policy fields are bounded when declared: subject scoring,
  kind profiles, diffusion, feedback, nonlinear response, layer coordination,
  and policy-adjustment bounds.
- Secret-like manifest fields are rejected or diagnosed.
- Extension metadata is preserved without granting evidence, permission, quorum,
  commit, or output authority.

## Compatibility

Protocol ABI changes should follow
[api-lifecycle.md](../process/api-lifecycle.md).

Schema changes should keep checked-in artifacts under `schemas/` aligned with
schema export behavior.

Baseline protocols must not be forced to opt into swarm-specific behavior.
