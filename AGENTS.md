# AGENTS.md

## Project Identity

This repository is the PheroOS protocol-core package.

PheroOS is a provider-free governed authority/commit protocol core for
multi-agent runtimes.

Agents are not authority. Protocol is authority.

OSKernel decides what is available. Governance decides what is allowed. Drivers provide capability. Trace explains what happened. Conformance proves compatibility.

The repository must stay small, cohesive, domain-neutral, deterministic, provider-free by default, and ABI-focused.

## Core Mission

Maintain explicit protocol authority, replaceable capability/store contracts,
and deterministic compatibility checks. New behavior should primarily change
its owning module and preserve declared consumer contracts through explicit
versioning and migration.

## Current Strategic Direction

Use the [current support matrix](docs/protocol/current-support.md), checked
public API/lifecycle inventories, and exact Conformance profiles to determine
the supported surface. All public exports remain Draft. The smaller
[consumer candidate](docs/protocol/stable-core-consumer.md) is not formally
Stable.

Attention and pheromone implementations are private experimental details.
Historical Hybrid Pheromone plans do not authorize restoring removed exports
or swarm conformance. Scoped Hybrid Replay v2 and Hybrid Commit remain public
Draft authority contracts; preserve their exact version, replay, and
attention/authority separation requirements. A future public attention contract
requires a separate versioned API and compatibility decision.

The [hardening plan](docs/process/production-readiness-hardening-goal-plan.md)
records historical work and evidence, not current support or permission to
execute its remaining release actions.

## Change Ownership

- Core owns protocol, capability declarations, Governance, Trace, and Conformance.
- External runtimes own scheduling, execution, cancellation, retries, and recovery.
- External adapters own concrete model, tool, and storage integrations; they
  may initially live with the runtime.
- `pheroos-bench/` is an independent package in this repository. Datasets,
  experimental algorithms, controls, and statistics belong there. Its model
  and numerical dependencies must not enter the core distribution or imports.

Use the existing Driver, Store, and Trace contracts for extensions. Every new
public API needs a concrete caller, an explanation of why existing interfaces
are insufficient, and a compatibility/migration decision.

## Allowed Core Surfaces

Executable code should exist only when it directly supports:

- Protocol ABI
- Kernel ABI
- Governance Core
- Driver ABI
- Trace ABI
- Conformance Suite
- provider-free examples
- thin CLI wrappers around core packages
- deterministic ABI/schema/TCK generators and CI/release verification tooling
- tests for the above

A core change must strengthen one of these surfaces. Bench changes follow the
separate package boundary above.

## Non-Goals

Do not restore the removed app runtime.

Do not add:

- FastAPI product APIs
- dashboards or frontend code
- LangGraph graphs
- model-provider routing
- LiteLLM/OpenAI/Ollama/vLLM provider wrappers in core
- endpoint catalogs
- local server wrappers
- visual regression UI tests
- WRDS, finance, investment, valuation, or other domain-specific workflows
- app-specific skills or product features
- background daemons, worker pools, or server infrastructure inside protocol-core
- plugin marketplaces
- broad agent frameworks
- broad safety/protection frameworks

If runtime infrastructure is needed, keep this repository limited to ABI contracts and conformance. Full runtime infrastructure belongs outside protocol-core.

## Implementation Bias

Prefer the smallest explicit change that advances a declared governed path.

Prefer:

- dataclasses
- pure functions
- explicit validation
- small schemas
- deterministic examples
- conformance checks
- direct tests

Avoid:

- speculative abstractions
- generic managers
- unused hooks
- framework scaffolding
- dependency-heavy implementations
- vague protection layers
- app/runtime concerns

A new abstraction is acceptable only if it satisfies at least one condition:

1. It enforces a declared Protocol ABI invariant.
2. It is required by Kernel ABI behavior.
3. It is required by Governance Core semantics.
4. It is required by Driver ABI compatibility.
5. It is required by Trace ABI lineage.
6. It is required by Conformance.
7. It is directly exercised by a test or provider-free example.

Otherwise, do not add it.

## Anti-Overconstraint Rule

Do not block useful protocol evolution with unnecessary rules.

Constraints should protect the project boundary, not freeze the design.

When adding a rule, validator, hook, or denial path, ensure it is:

- tied to a protocol invariant
- observable in trace or conformance
- covered by tests
- small enough to understand locally
- not duplicating an existing check

If a constraint only sounds safe but does not affect protocol correctness, conformance, traceability, or deterministic behavior, do not add it.

## End-to-End Direction

Prefer vertical slices over disconnected primitives.

The governed baseline path is:

1. Load a capability manifest.
2. Validate protocol invariants.
3. Bind scope, capabilities, and current authority under the selected version.
4. Verify evidence-bearing proposals for declared targets and candidates.
5. Commit a declared candidate or return an explicit terminal fallback.
6. Authorize publication or execution only when its current output gates pass.
7. Record causal Trace and verify the selected Conformance contract.

Use the installed-package consumer and independent adapter tests when changing
an extension contract. Callers should be able to replace an implementation
without changing business logic or importing private core modules.

## Protocol Rules

Protocol code owns declarations and validation.

Protocol code may define:

- capability manifests
- protocol manifests
- targets
- signals
- candidates
- quorum policy
- collective decision policy
- recovery policy
- evidence policy
- output policy
- trace policy
- validation diagnostics
- schema helpers

Protocol code must remain pure contract code.

Protocol validation should check:

- declared targets
- declared candidates
- candidate target references
- safe quorum fallback
- safe collective fallback
- recovery trigger references
- recovery failure candidate references
- evidence provenance requirements
- writer fact-creation restrictions
- agent fact-creation restrictions
- trace lineage requirements
- collective decision policy invariants
- hybrid pheromone policy invariants when declared

## Kernel Rules

Kernel code owns runtime planning boundaries.

The kernel may define:

- input envelopes
- OS plans
- capability resolution
- permission grants
- connection requirements
- driver exposure
- tool exposure
- runtime context materialization
- syscall-style request/reply contracts
- run-scoped and tenant-scoped handles

The kernel must not:

- make domain conclusions
- call tools directly
- call model providers directly
- access secrets directly
- become a server
- become a workflow engine
- become an agent framework
- become a swarm runtime

## Governance Rules

Governance code owns authority and decision semantics.

Governance may define:

- authority levels
- canonical targets
- signals
- evidence graphs
- stop signals
- candidate sets
- quorum decisions
- recovery traces
- output contracts
- collective decision primitives
- scout reports
- recruitment signals
- inhibition signals
- pheromone trails
- pheromone feedback records
- layer proposal records
- metacognitive coordination records
- trace-relevant decision records

Governance must enforce:

- agents may propose signals
- governance authority is required to verify signals
- quorum commits only declared candidates
- collective consensus commits only declared candidates
- failed consensus falls back to a declared safe fallback candidate
- stop or inhibition signals can block or reduce candidate support
- learned, evolutionary, and metacognitive layers may propose but cannot directly commit
- pheromone feedback may reinforce memory but cannot create evidence or authority
- runtime policy adjustments must remain inside declared protocol bounds
- output authorization requires committed candidate, evidence provenance, stop resolution, and publication permission

Do not build a large generic policy engine unless tests and conformance require it.

## Driver Rules

Driver code owns generic capability provider contracts.

Driver lifecycle is:

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

## Trace Rules

Trace code owns provider-neutral lineage.

Trace may define:

- trace events
- append-only records
- in-memory trace stores for tests
- required event validation
- lineage helpers

Trace must not become:

- a database
- an event bus
- a queue
- a logging framework
- a runtime monitor daemon

`pheroos.trace.TraceEvent` is the canonical Trace ABI. Other packages may re-export it as a compatibility alias, but should not define a second incompatible trace event object.

## Conformance Rules

Conformance proves ABI compatibility.

Conformance may compose protocol, kernel, governance, drivers, and trace.

Conformance checks should remain:

- deterministic
- provider-free
- network-free
- small
- explicit about the invariant being checked

The removed swarm and Hybrid-swarm profiles are not public Conformance
contracts. A legacy attention declaration without Commit selects the core
profile. Commit profiles retain their explicit attention bounds and
channel-separation checks; private scoring is not proof of swarm efficacy.

## Import Boundaries

Maintain strict package boundaries.

- `pheroos.protocol` must not import `pheroos.kernel`, `pheroos.governance`, `pheroos.drivers`, `pheroos.conformance`, CLI, examples, app/runtime modules, provider frameworks, or tools.
- `pheroos.kernel` may import `pheroos.protocol` and `pheroos.drivers`.
- `pheroos.kernel` should not import `pheroos.governance` directly. If governance decisions are needed, represent them through explicit contracts, dependency injection, or outer runtime/conformance composition.
- `pheroos.governance` may import protocol concepts where practical, but should remain independent of kernel runtime machinery and provider frameworks.
- `pheroos.drivers` should remain generic and must not depend on app/runtime/provider frameworks.
- `pheroos.trace` should remain generic and must not depend on app/runtime/provider frameworks.
- `pheroos.conformance` may import protocol, kernel, governance, drivers, and trace.
- CLI code must stay thin and delegate to core packages.

Do not weaken these boundaries to make a test pass. Fix the design instead.

## Dependency Rules

Keep dependencies minimal.

Prefer the Python standard library.

Do not add heavy dependencies for protocol, governance, trace, conformance, examples, or tests unless the dependency is essential to an ABI invariant and cannot be replaced by a small local dataclass or function.

Do not add provider SDKs, model clients, web frameworks, queues, databases, or background infrastructure to protocol-core.

## Example Rules

Examples must stay provider-free, network-free, deterministic, and domain-neutral.

Use examples to prove ABI behavior, not to create product workflows.

`examples/toy-protocol` remains the minimal baseline governed protocol example.

`examples/e2e-protocol` may demonstrate the minimal governed vertical slice.

`examples/swarm-protocol` and `examples/hybrid-pheromone-protocol` are legacy
private-attention fixtures, not demonstrations of established swarm efficacy.

Do not turn examples into app runtimes, provider gateways, dashboards, or domain workflows.

## Testing and Validation

Add tests before or alongside behavior.

Derive tests from the problem, counterexamples, and independently checkable
invariants. Do not fix failures by refreshing unrelated snapshots, weakening
thresholds, or changing expected outcomes to match the implementation.

Tests should prove:

- protocol validation invariants
- governance authority and decision semantics
- driver lifecycle compatibility
- trace lineage requirements
- conformance checks
- provider-free examples
- backward compatibility for existing examples

Before finishing substantive changes, run the relevant subset and, when practical:

```bash
python -m pytest -q
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol
python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol
```

If the shell does not provide `python`, use the repository virtual environment or available interpreter and report that clearly.

Release and production-readiness changes must also follow
`docs/process/release-checklist.md`.

## Documentation Rules

Docs should stay short and ABI-focused.

Document invariants, boundaries, conformance behavior, and provider-free examples.

Do not add marketing copy, product runtime documentation, dashboard docs, provider setup guides, or domain workflow instructions.

## Backward Compatibility Rule

Follow the API lifecycle and removal ledger for declared compatibility cohorts.
Draft is not permission to silently change a contract or retain duplicate
algorithms without a consumer and an exit decision.

`examples/toy-protocol` should remain the minimal baseline governed protocol example.

Baseline quorum-only protocols must continue to validate and pass conformance.

Do not rewrite baseline examples to make them opt into a new contract. Add a
separate versioned example and migration evidence for newly declared behavior.

## Final Rule

Agents are not authority.

Protocol is authority.

Keep PheroOS small, explicit, deterministic, domain-neutral, provider-free by default, and ABI-focused.
