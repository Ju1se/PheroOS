# AGENTS.md

## Project Identity

This repository is the PheroOS protocol-core package.

PheroOS is a swarm-native multi-agent operating protocol core for governed multi-agent runtimes.

Agents are not authority. Protocol is authority.

OSKernel decides what is available. Governance decides what is allowed. Drivers provide capability. Trace explains what happened. Conformance proves compatibility.

The repository must stay small, cohesive, domain-neutral, deterministic, provider-free by default, and ABI-focused.

## Core Mission

Evolve PheroOS into a swarm-native multi-agent operating protocol without turning it into an app runtime, agent framework, provider gateway, dashboard, or protection-layer stack.

Swarm-native means that bee-swarm and ant-colony decision mechanisms are encoded as protocol/governance/trace/conformance semantics:

- independent exploration
- scout reports
- recruitment signals
- inhibition signals
- pheromone trails
- pheromone evaporation
- collective consensus
- safe fallback when consensus fails
- traceable collective decision lineage

Swarm-native does not mean adding a large swarm framework.

## Current Strategic Direction

The [Hybrid Pheromone ABI](docs/protocol/hybrid-pheromone-abi.md) is an
implemented Draft swarm profile and a regression boundary. The active
production-readiness work is tracked by the
[hardening Goal plan](docs/process/production-readiness-hardening-goal-plan.md).

Preserve the complete declared Hybrid path: subject-aware collective memory,
pheromone diffusion, feedback reinforcement, nonlinear response, layer
proposals, metacognitive coordination, trace lineage, and Conformance. Changes
to that path must use explicit versioned contracts and migration rather than a
minimal scoring substitute. Baseline protocols remain independent and optional
swarm profiles remain explicit. Do not place the external hybrid runtime,
neural networks, evolutionary algorithm runtime, environment simulation, agent
colony, analytics loop, worker infrastructure, or server machinery inside
protocol-core.

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

A change that does not strengthen one of these surfaces should usually not be made in this repository.

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

## Swarm-Inspired Protocol Mapping

Use biology as inspiration, not as implementation baggage.

Bee-swarm mapping:

- scout bee -> independent agent report
- nest site -> declared candidate
- waggle dance -> recruitment signal
- stop/dissent behavior -> inhibition signal
- quorum threshold -> consensus threshold
- swarm takeoff -> output authorization or publication

Ant-colony mapping:

- path -> candidate, route, or tool/reasoning trajectory
- pheromone -> accumulated support signal
- evaporation -> confidence decay
- negative pheromone -> inhibition or blocked route
- alarm pheromone -> emergency caution or fallback pressure
- pheromone diffusion -> bounded local propagation over declared subjects
- feedback reinforcement -> outcome-bound strengthening or weakening
- response saturation -> positive feedback without runaway lock-in
- exploration/exploitation balance -> non-greedy candidate search
- convergence -> committed candidate or safe fallback

Do not use swarm terminology as marketing. Encode it as testable protocol behavior.

## Implementation Bias

Prefer the smallest explicit protocol object that advances an end-to-end swarm decision path.

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

## Preferred Swarm ABI Additions

When implementing swarm-native behavior, prefer adding small pieces under existing surfaces instead of creating a new top-level framework.

Preferred locations:

- `pheroos.protocol` for manifest declarations and validation
- `pheroos.governance` for collective decision primitives
- `pheroos.trace` for lineage and append-only events
- `pheroos.conformance` for compatibility checks
- `examples/swarm-protocol` for a provider-free protocol example
- `tests` for deterministic proof

Preferred concepts:

- `CollectiveDecisionPolicy`
- `ScoutReport`
- `RecruitmentSignal`
- `InhibitionSignal`
- `PheromoneTrail`
- `PheromonePolicy`
- `PheromoneKindProfile`
- `PheromoneDiffusionPolicy`
- `PheromoneFeedback`
- `LayerProposal`
- `LayerCoordinationPolicy`
- `PolicyAdjustmentProposal`
- `CollectiveDecisionState`
- `evaluate_collective_decision`
- `evaporate_trails`
- `diffuse_pheromone_trails`
- `reinforce_pheromone_trails`
- `evaluate_layer_coordination`

These names are preferred, not mandatory. Use existing code style and naming if it gives a cleaner result.

## End-to-End Direction

Prefer vertical slices over disconnected primitives.

The baseline swarm-native path is:

1. Load a capability manifest.
2. Validate protocol invariants.
3. Read a collective decision policy.
4. Declare targets and candidates.
5. Identify a declared safe fallback candidate.
6. Collect independent scout reports with evidence provenance.
7. Apply recruitment signals when enabled.
8. Apply inhibition signals when enabled.
9. Apply pheromone deposit and evaporation when enabled.
10. Apply pheromone diffusion, feedback reinforcement, and response shaping when declared.
11. Evaluate layer proposals and metacognitive coordination when declared.
12. Enforce policy adjustment bounds when runtime layers propose adaptation.
13. Evaluate collective consensus.
14. Commit only a declared candidate, or fall back safely.
15. Authorize output only when the output contract is satisfied.
16. Emit trace events for the collective decision path.
17. Pass conformance.

A swarm-specific feature that does not improve this path should usually be deferred.

When a manifest explicitly selects the Hybrid Pheromone ABI, preserve its
complete declared path: diffusion, feedback reinforcement, nonlinear response,
layer proposals, metacognitive coordination, policy adjustment bounds, trace
lineage, Conformance, and provider-free examples.

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

Swarm-specific conformance checks apply only when a manifest declares swarm behavior.

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

`examples/swarm-protocol` may demonstrate swarm-native collective decision behavior.

Do not turn examples into app runtimes, provider gateways, dashboards, or domain workflows.

## Testing and Validation

Add tests before or alongside behavior.

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

Do not force existing baseline protocols to become swarm protocols.

`examples/toy-protocol` should remain the minimal baseline governed protocol example.

Swarm-native rules apply only when a manifest explicitly declares `collective_decision_policy` with a swarm mode such as `bee_swarm`, `ant_colony`, or `hybrid`.

Baseline quorum-only protocols must continue to validate and pass conformance.

Do not rewrite old protocol examples merely to satisfy new swarm-specific checks. Add a separate `examples/swarm-protocol` example for swarm-native behavior.

## Final Rule

Agents are not authority.

Protocol is authority.

Keep PheroOS small, explicit, deterministic, domain-neutral, provider-free by default, and ABI-focused.
