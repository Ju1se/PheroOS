# Governance Core

`pheroos.governance` defines the authority model for governed runtime decisions.

Governance decides what is allowed. Agents may propose facts, signals, reports,
and candidates; governance authority is required to verify and commit.

## Owned Surface

- target-scoped candidate sets and decisions; target declarations remain owned
  by `pheroos.protocol.TargetSpec`
- signals
- authority levels
- evidence graph
- stop signals
- candidate sets
- quorum decisions
- recovery decisions and canonical `TraceEvent(event_type="recovery")`
  lineage; `RecoveryTrace` is compatibility-only
- output contracts
- governance lineage and a type-identical `TraceEvent` compatibility export
- deterministic collective decision steps
- scout reports
- recruitment signals
- inhibition signals
- pheromone trails and policies
- verified principals, observations, counterevidence, and challenges
- eligible membership, support leases, and risk heads
- Optimal Commit metrics, stable windows, bounded liveness, and outcomes
- local, portable, and distributed commit certificates
- action-scoped delivery, publication, and execution decisions
- scoped authority domains, CAS heads, atomic state-plus-Trace batches,
  receipts, rehydration, retirement, and tombstones

## Invariants

- Agents can propose signals.
- Governance authority is required to verify signals.
- Quorum can commit only declared candidates for the active target.
- Baseline quorum commits only when verified support reaches the declared threshold.
- Failed quorum or collective consensus falls back only to a declared safe candidate for the active target.
- Stop signals block target actions.
- Recovery follows declared triggers, roles, tags, tools, and failure behavior.
- Output authorization requires a committed candidate, non-empty provenance-bearing evidence, stop resolution, and publication permission.
- Pheromone is bounded collective memory, not evidence, quorum, permission, or output authority.
- Namespaced pheromone metadata does not score candidates by default.
- Hybrid attention may direct exploration but cannot enter Optimal Commit
  metrics or certificate truth roots.
- A ready candidate commits only after every declared risk-adjusted gate holds
  for the complete stability window; ties never commit by identifier order.
- Missing higher-assurance proof remains pending or produces a declared
  terminal non-commit result; assurance never downgrades implicitly.
- Every governance-issued terminal outcome is deliverable. Publication and
  execution require separate current action authority.
- Distributed finality enforces the declared Byzantine intersection rule;
  conflicting final certificates freeze the epoch.
- New durable authority paths never depend on module-global mutable registries.
  A prepared transition has no durable output authority until its exact state
  and Trace batch receives a verified store receipt.

## Optimal Commit

The optional Optimal Commit path is a composition of small governance-issued
records. Principal, risk, membership, evidence, challenge, lease, stop,
permission, replay, and prior-window heads are exact inputs to
`assess_optimal_commit(...)`. `evaluate_hybrid_commit_step(request=...)` then
advances bounded liveness, verifies the declared finality level, decides output
actions, and emits a reconstructable trace.

External runtimes that need durable authority supply a
`GovernanceStateStore`, prepare against the current scoped head, atomically
commit state and Trace, and finalize only after receipt verification.
`InMemoryGovernanceStateStore` is a deterministic reference adapter, not a
database. Frozen v1 process-local issuers are quarantined under `_legacy` and
must not gain new semantics.

External stores provide a `GovernanceStateStoreConformanceAdapter` test fixture
and run `run_governance_state_store_conformance(...)`; the same matrix checks
restart, snapshot restoration, scope isolation, CAS, idempotency, atomic
state-plus-Trace failure, retirement, and tombstones without moving database
lifecycle into Governance.

The complete Draft semantics are documented in
[the Optimal Commit ABI](../protocol/optimal-commit-abi.md).

## Swarm Semantics

Bee-swarm behavior is represented by independent scout reports, recruitment
signals, inhibition signals, consensus thresholds, and safe fallback.

Ant-colony behavior is represented by traceable pheromone memory, evaporation,
bounded contribution, source diversity, and deterministic scoring.

These concepts are protocol semantics, not a swarm runtime.

## Internal Composition

The public Governance modules are cohesive facades over one-way private
engines. Commit state, support, certificates, distributed finality, Hybrid
evaluation, swarm orchestration, and pheromone lifecycle each have one
implementation owner. Facades preserve public identity and signatures; private
engines do not import the aggregate facade, form cycles, dynamically register
services, or share hidden mutable authority.

Commit Wire and Trace validation use immutable static contract registries.
Adding an authoritative built-in branch requires an ABI/schema, validator,
trace, conformance, and lifecycle change; a namespaced extension remains
non-authoritative by default.

## Boundary

Governance must not call model providers, tools, servers, queues, or external
runtimes. It contains no database implementation, SDK, connection, migration,
or replication machinery. Durable paths may call only the provider-neutral
`GovernanceStateStore` interface explicitly supplied by an outer runtime; the
adapter and its database operations stay outside protocol-core.

`pheroos.trace.TraceEvent` remains the sole canonical Trace ABI type.
Governance may emit and re-export that type, but it does not own a second trace
event representation.
