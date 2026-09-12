# Extension Points

PheroOS protocol-core is designed for external implementations to extend behavior without coupling protocol-core to app runtimes, providers, dashboards, or domain workflows.

The current public contract is governed authority/commit. The collective and
pheromone material in this document is historical/private extension guidance;
it does not define a supported swarm profile or impose swarm conformance on
baseline implementations.

The [current support matrix](current-support.md) binds this guidance to exact
versions and verification entries. All public interfaces remain Draft.

## Ownership of New Behavior

| Owner | Responsibility |
| --- | --- |
| Protocol-core | Protocol and capability declarations, Governance, Trace, versioned compatibility contracts |
| External runtime | Scheduling, execution, cancellation, retry, run recovery, external effects |
| External adapters, initially alongside runtime if useful | Concrete model, tool, and storage integrations |
| Independent `pheroos-bench/` package | Datasets, experiments, controls, measurements, and statistics |

A new backend should primarily change its adapter. A new experimental method
should primarily change bench. Shared repository location does not make bench
part of the core distribution or allow core imports of its dependencies.

## Extension Principles

- Extend through declared ABI surfaces.
- Keep provider integrations outside protocol-core.
- Keep examples deterministic and provider-free.
- Add conformance when an extension introduces compatibility expectations.
- Add validation only when it protects a protocol invariant.
- Prefer small dataclasses and pure functions over managers or framework scaffolding.

## Supported Extension Points

### Protocol Manifests

Extensions may add manifest fields when they are:

- schema-backed
- validated structurally
- documented
- tested
- compatible with baseline protocols that do not opt in

Legacy collective fields are advisory and must not select a public swarm
profile or impose additional conformance requirements.

Manifest extensions should use the explicit `extensions` object or namespaced keys such as `x-*` and `ext.*`.

Extension metadata is preserved for external runtimes, but it does not create evidence, permission, quorum, commit authority, or output authority. Manifests must not contain API keys, tokens, passwords, credentials, secrets, or provider configuration values.

### Governance Reference Semantics

Governance extensions may add deterministic primitives for:

- authority checks
- evidence requirements
- quorum or collective decision semantics
- recovery behavior
- output authorization boundaries
- proposal/authority separation for optional advisory inputs

Governance extensions must not call model providers, tools, servers, databases, or queues.

### Driver ABI

Driver extensions may add generic capability descriptors or lifecycle-compatible result fields.

Provider-specific drivers should live outside protocol-core and implement the generic driver ABI.

Driver declarations in manifests are provider-neutral. `config_ref` may name an external configuration reference, but protocol-core must not resolve that reference or read secrets from it.

### Store and Replacement Acceptance

Use the existing public `GovernanceStateStoreV2`, `DriverInvocationStoreV2`,
and `ScopedTraceStoreV2` contracts for external backends. A replacement must:

- import only public interfaces, with no private reference implementation imports;
- install the package and execute from outside its source directory;
- pass the same exact-version Conformance adapter contract as the reference;
- replace the injected implementation without changing consumer business logic.

Existing [distribution tests](../../tests/packaging/test_stable_candidate_distributions.py)
already inject the independent stdlib Store into the
[candidate consumer](../../tests/typing/stable_consumer.py). The
[Runtime Integration tests](../../tests/conformance/test_runtime_integration_v1_contract.py)
exercise reference and independent adapters. Reuse these acceptance paths for
a real external backend; they do not by themselves prove production storage or
provider behavior. Expand an abstraction only when a concrete second
implementation exposes a contract gap.

### Trace ABI

Trace extensions may add provider-neutral event types or lineage metadata.

Trace extensions must stay small and append-only. Trace must not become a database, event bus, queue, logging framework, runtime monitor, or daemon.

Namespaced trace event types such as `x-*` and `ext.*` may be used for external runtime lineage. They are trace records only and do not grant authority.

### Conformance

Conformance extensions should prove an invariant, not encode product policy.

A conformance check should be:

- deterministic
- provider-free
- network-free
- explicit about the invariant
- scoped to declared behavior

### Examples

Examples should show ABI behavior, not product workflows.

Allowed examples:

- baseline governed protocol
- governed e2e vertical slice
- optional private attention/collective behavior
- provider-free driver lifecycle examples

Disallowed examples:

- provider gateways
- dashboards
- finance or other domain-specific workflows
- app servers
- background worker systems

## Non-Extension Points

Do not extend protocol-core by adding:

- provider SDKs
- FastAPI or other product APIs
- LangGraph graphs
- model routing layers
- persistent storage systems
- queues
- background daemons
- plugin marketplaces
- broad safety or protection frameworks
- domain-specific workflows

These belong in external runtimes or applications that implement the ABI.

## Compatibility Expectations

An extension should not force existing baseline protocols to opt into new behavior.

When an extension is optional:

- extension-specific validation does not apply until the manifest opts in
- extension-specific conformance checks are not selected until the manifest
  declares the behavior
- once behavior is declared, every required check must return PASS or FAIL;
  skip/N/A is not an active compatibility result
- examples should be added separately rather than rewriting baseline examples

## Historical/private attention

The former pheromone path illustrates an earlier Draft design. Its scoring
implementation remains private, and the former swarm conformance requirements
and pheromone exports have been removed. Retained fixtures do not create a
public extension point. Future public attention behavior needs a versioned
contract and concrete consumer; research algorithms belong in bench.

Private attention is not evidence, quorum, permission, or output authority.

## Optimal Commit Extension Boundary

Optimal Commit shows how strict authority can coexist with runtime
extensibility:

- `collective_commit_policy` is optional, so baseline and legacy Hybrid
  manifests remain unchanged;
- noncritical extension metadata may carry adapter hints but stays outside
  metrics, certificates, permissions, and output authority;
- an extension that changes commit truth is critical and must declare a
  supported version, canonical wire form, validation invariant, trace lineage,
  conformance check, and exact TCK vector;
- unknown critical extensions fail closed instead of being treated as metadata;
- external MCP, A2A, provenance, policy, identity, and witness transports map
  into governance proposal/verification records outside protocol-core.

The adapter may change how evidence is collected or transported. It cannot
change what counts as verified evidence or silently create a lower-assurance
commit.
