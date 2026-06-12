# AGENTS.md

## Project Identity

This repository is the PheroOS protocol-core package.

PheroOS is an AI-as-OS protocol core for governed, swarm-native multi-agent runtimes.

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
- `CollectiveDecisionState`
- `evaluate_collective_decision`
- `evaporate_trails`

These names are preferred, not mandatory. Use existing code style and naming if it gives a cleaner result.

## End-to-End Direction

Prefer vertical slices over disconnected primitives.

The minimal useful swarm-native path is:

1. Load a capability manifest.
2. Validate protocol invariants.
3. Read a collective decision policy.
4. Declare targets and candidates.
5. Identify a declared safe fallback candidate.
6. Collect independent scout reports with evidence provenance.
7. Apply recruitment signals when enabled.
8. Apply inhibition signals when enabled.
9. Apply pheromone deposit and evaporation when enabled.
10. Evaluate collective consensus.
11. Commit only a declared candidate, or fall back safely.
12. Authorize output only when the output contract is satisfied.
13. Emit trace events for the collective decision path.
14. Pass conformance.

A feature that does not improve this path should usually be deferred.

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
- trace-relevant decision records

Governance must enforce:

- agents may propose signals
- governance authority is required to verify signals
- quorum commits only declared candidates
- collective consensus commits only declared candidates
- failed consensus falls back to a declared safe fallback candidate
- stop or inhibition signals can block or reduce candidate support
- output authorization requires committed candidate, evidence provenance, stop resolution, and publication permission

Do not build a large generic policy engine unless tests and conformance require it.

## Driver Rules

Driver code owns generic capability provider contracts.

Driver lifecycle is:

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
