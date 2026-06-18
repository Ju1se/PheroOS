# PheroOS Protocol-Core Specification

Status: draft ABI v0.1

PheroOS is an open AI-as-OS protocol-core package for governed, swarm-native multi-agent runtimes.

Agents are not authority. Protocol is authority.

This specification defines the public protocol-core architecture, compatibility surfaces, and extension rules for implementations that want to interoperate with PheroOS.

## Scope

PheroOS protocol-core defines:

- Protocol ABI: manifests, schemas, loading, validation, diagnostics, and compatibility helpers.
- Kernel ABI: input envelopes, capability planning, permission grants, runtime contexts, and syscall-style request/reply contracts.
- Governance Core: authority, evidence, quorum, collective decision, recovery, output authorization, and swarm decision semantics.
- Driver ABI: generic capability descriptor, lifecycle, binding, exposure, invocation, and result contracts.
- Trace ABI: canonical provider-neutral trace events and append-only test stores.
- Conformance Suite: deterministic checks that prove protocol-core compatibility.
- Provider-free examples: deterministic compatibility examples for baseline, e2e, and swarm protocol behavior.

PheroOS protocol-core does not define:

- an app runtime
- an agent framework
- a model-provider gateway
- a web API server
- a dashboard
- a queue, database, worker pool, or daemon
- provider SDK integrations
- domain-specific workflows

Runtime implementations may exist outside this repository as long as they implement the ABI and pass conformance.

## Public Surfaces

The public Python package surfaces are:

- `pheroos.protocol`
- `pheroos.kernel`
- `pheroos.governance`
- `pheroos.drivers`
- `pheroos.trace`
- `pheroos.conformance`
- `pheroos.cli`

The public schema artifacts are:

- `schemas/protocol.schema.json`
- `schemas/kernel.schema.json`
- `schemas/driver.schema.json`
- `schemas/trace.schema.json`

The public CLI surfaces cover manifest validation, conformance evaluation, and ABI schema export for protocol, kernel, driver, and trace artifacts.

## Compatibility Requirements

A compatible implementation should satisfy these requirements:

1. Protocol manifests declare targets, candidates, quorum policy, trace policy, output policy, and any optional swarm policy they use.
2. Candidates reference declared targets.
3. Quorum fallback references a declared safe fallback candidate.
4. Collective fallback references a declared safe fallback candidate or defaults to the quorum fallback.
5. Output authorization requires the configured output contract.
6. Trace events use `pheroos.trace.TraceEvent` semantics or a compatible provider-neutral representation.
7. Driver lifecycle follows `declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace`.
8. Swarm-specific checks apply only when a manifest declares a swarm collective mode.
9. Baseline quorum protocols do not need to declare swarm behavior.
10. Extension metadata is preserved without granting evidence, permission, quorum, commit, or output authority.
11. Implementations pass the relevant conformance profile for their declared protocol behavior.

## Swarm-Native Semantics

Swarm-native behavior is encoded as protocol, governance, trace, and conformance semantics. It is not a swarm framework.

Bee-swarm-inspired semantics include:

- independent exploration
- scout reports
- recruitment signals
- inhibition signals
- quorum or collective consensus
- safe fallback when consensus fails

Ant-colony-inspired semantics include:

- pheromone trails
- pheromone evaporation
- positive, negative, cautionary, novelty, and stale pheromone kinds
- bounded source contribution
- evidence and trace binding
- traceable collective decision lineage

Pheromone is external collective memory. It is not evidence, truth, quorum, permission, or output authority.

## Extension Rules

Extensions should preserve low coupling and provider neutrality.

Allowed extension points include:

- new provider-free examples
- additional deterministic conformance checks
- new manifest fields with schema and validation support
- new governance primitives directly tied to protocol invariants
- external runtime implementations that consume the ABI
- external provider adapters outside protocol-core

Manifest extensions should use an explicit `extensions` object or namespaced keys such as `x-*` and `ext.*`.

Provider-specific configuration, API keys, tokens, passwords, credentials, and secrets must stay outside protocol manifests.

Driver declarations are provider-neutral. `config_ref` is an opaque external reference owned by an external runtime; protocol-core does not resolve it.

Namespaced trace and pheromone extensions may record external runtime lineage or metadata, but unknown extensions do not score candidates or authorize decisions by default.

Extensions should not add:

- provider SDKs to protocol-core
- app runtime infrastructure
- background services
- dashboards
- domain-specific workflows
- broad policy or protection frameworks without conformance-backed invariants

## Versioning

The current public ABI is draft `0.1.0`.

Before the first stable ABI release, changes may still refine dataclass fields, schema shape, and conformance checks. Such changes should be documented in `CHANGELOG.md`, reviewed through the PheroOS Improvement Process, and backed by tests or conformance.

After a stable ABI release, incompatible changes should require:

- a version bump
- migration notes
- schema update
- conformance update
- deprecation window when practical

## Conformance

Conformance is the compatibility gate for protocol-core. Checks should remain:

- deterministic
- provider-free
- network-free
- explicit about the invariant being checked
- scoped to declared protocol behavior

Release validation is enforced by CI and release governance. The specification defines the invariants and compatibility expectations; it is not a local runbook.

## Governance Principle

Protocol declares what is available. Governance decides what is allowed. Drivers provide capability. Trace explains what happened. Conformance proves compatibility.

No extension should make agents the authority.
