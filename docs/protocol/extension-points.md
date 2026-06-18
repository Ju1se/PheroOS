# Extension Points

PheroOS protocol-core is designed for external implementations to extend behavior without coupling protocol-core to app runtimes, providers, dashboards, or domain workflows.

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

Swarm-specific fields should apply only when `collective_decision_policy.mode` declares a swarm mode.

### Governance Reference Semantics

Governance extensions may add deterministic primitives for:

- authority checks
- evidence requirements
- quorum or collective decision semantics
- recovery behavior
- output authorization boundaries
- pheromone or collective memory behavior

Governance extensions must not call model providers, tools, servers, databases, or queues.

### Driver ABI

Driver extensions may add generic capability descriptors or lifecycle-compatible result fields.

Provider-specific drivers should live outside protocol-core and implement the generic driver ABI.

### Trace ABI

Trace extensions may add provider-neutral event types or lineage metadata.

Trace extensions must stay small and append-only. Trace must not become a database, event bus, queue, logging framework, runtime monitor, or daemon.

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
- swarm-native collective behavior
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

- validation should skip extension-specific requirements unless the manifest opts in
- conformance should skip extension-specific checks unless the manifest declares the behavior
- examples should be added separately rather than rewriting baseline examples

## Pheromone Extension Example

The pheromone layer is an example of an acceptable protocol-core extension:

- protocol declares policy fields and schema shape
- governance implements deterministic reference semantics
- trace records provider-neutral lineage
- conformance proves compatibility and boundaries
- examples remain provider-free

Pheromone remains collective memory. It is not evidence, quorum, permission, or output authority.
