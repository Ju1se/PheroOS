# Governance Core

`pheroos.governance` defines the authority model for governed runtime decisions.

Governance decides what is allowed. Agents may propose facts, signals, reports,
and candidates; governance authority is required to verify and commit.

The public positioning is governed authority/commit. The former swarm and
pheromone semantics below are retained as private, historical implementation
profiles only; baseline and Commit conformance do not require them, and they
are not evidence of emergent swarm intelligence.

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
  lineage; recovery records use the canonical `pheroos.trace.TraceEvent`
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
- additive Draft authority v2 contracts for bounded multi-read/single-write
  commits, immutable historical inclusion, total commit views, and atomic
  domain seals; the provider-free in-memory Store remains a private reference

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

The remaining public Draft v1 issuer functions are trusted-host compatibility
surfaces, not production authentication or portable credentials. A host that
passes `AuthorityLevel.GOVERNANCE` is asserting its own trust boundary; the
enum does not prove an identity, possession, or deployment grant. Draft v1
baseline output likewise accepts a host-supplied publication boolean, and its
atomic finalize path tests a receipt against the current head rather than an
immutable historical inclusion proof. These limitations are machine-recorded
in the [WP-00 engineering baseline](../process/engineering-baseline-v1.json)
and are scheduled to be replaced, not extended, by WP-02 through WP-04 of the
production-readiness hardening plan.

External stores provide a `GovernanceStateStoreConformanceAdapter` test fixture
and run `run_governance_state_store_conformance(...)`; the same matrix checks
restart, snapshot restoration, scope isolation, CAS, idempotency, atomic
state-plus-Trace failure, retirement, and tombstones without moving database
lifecycle into Governance.

The Draft v2 equivalent is the exact-version
`GovernanceStateStoreConformanceAdapterV2` and
`run_governance_state_store_conformance_v2(...)` matrix defined by the
[StateStore v2 ABI](../protocol/authority-store-v2.md). It proves the bundled
private reference Store and an independent public-contract-only stdlib model.
It does not activate an authority v2 manifest profile or provide a production
database adapter.

The complementary public Draft
[Authority Session v2 ABI](../protocol/authority-session-v2.md) adds portable
issuer grants and requests, non-portable store-bound capabilities, and
request-specific least-privilege sessions. The session owns the exact selected
writer and captured grant/lifecycle heads; `VERIFY_SIGNAL` and `RETIRE_DOMAIN`
commit their state or seal, authority-critical Trace, receipt, and full
read-set validation in one StateStore boundary. The reusable
`run_governance_authority_session_conformance_v2(...)` matrix passes both the
private reference Store and the independent stdlib Store model. These public
Draft objects do not expose a writer to agents, do not authenticate arbitrary
same-process Python, and do not activate a complete authority profile.

The Draft Stable promotion candidate adds one Governance-owned aggregate write
boundary: `evaluate_and_commit_governed_baseline_output_v2(...)`. An external
runtime passes a versioned Store/domain, portable grant and stable activation
identity/epoch, optional host verifier, exact verified-signal requests, and a
Baseline Output request. Governance keeps capability/session custody internal
and performs signal, permission, and output commits in order. It returns only
a portable `GovernanceCommitAttemptV2` or `BaselineOutputResultV2`. Exact retry
and restart reconcile the same roots; revocation, expiry, stale dependencies,
blocked publication, and verifier failure remain typed fail-closed outcomes.
The entrypoint does not perform the declared external effect.

The Draft [Hybrid Replay v2 ABI](../protocol/hybrid-replay-v2.md) applies the
same trust boundary to Hybrid pheromone memory: portable snapshots are data,
only committed Store inclusion plus an observed position can produce a local
verified wrapper, and only the atomically current parent may advance. It binds
active trails, four receipt classes, cumulative policy overlay, effective
policy, budget, and source lineage without adding a database or swarm runtime.
Its public Draft facade exposes the context-bound evaluator, portable
snapshot/request, Store-backed rehydration, currentness, and atomic advance
journey. The same active Conformance matrix passes the reference and
independent stdlib StateStore adapters, including restart, concurrent stale
parent, source substitution, resource-bound, and exact-retry cases.

The public Draft [Risk State v2 ABI](../protocol/risk-state-v2.md) applies the
same boundary to policy-selected risk thresholds. A portable assessment is
data; only an exact `QUALIFY_EVIDENCE` session and atomic StateStore commit
create durable Risk authority. One target/run/policy binding owns one fixed
stream, while epoch, `parent_epoch`, reset decisions, assessment lineage, and
threshold roots remain versioned state. Risk v2 does not select a candidate,
issue support, authorize output, or provide a database/runtime. Its public
checks matrix and provider-free restart example cover reference and independent
Store implementations without private Governance hooks.

The public Draft [Support v2 ABI](../protocol/support-v2.md) gives Principal
Verification, Membership, and Support separate complete-replacement streams.
Membership cannot invent verified principals, and Support cannot strengthen
evidence; each owner is independently current and remains visible in later
atomic read-sets. The public Draft
[Commit Gate v2 ABI](../protocol/commit-gate-v2.md) similarly separates COMMIT
Stop from COMMIT Permission and rechecks Replay, Risk, Principal Verification,
Membership, and Support before each gate transition. An expired or stale gate
cannot authorize a Decision or output action.

The public Draft [Commit Evidence v2 ABI](../protocol/commit-evidence-v2.md)
owns evidence replacement/history by candidate, claim, and epoch. Its durable
owner verifies Membership, Principal Verification, and Replay in one atomic
read-set; its authority-neutral projection applies bounded integer scoring,
source/failure-domain diversity, challenge coverage, replacement, revocation,
and TTL without creating candidate authority. The
[Commit Certificate v2 ABI](../protocol/commit-certificate-v2.md) binds the
actual historical Decision seal and exactly eight current authority leaves in
one portable body and one twelve-stream durable owner. Its portable verifier
and durable cross-owner Conformance matrices are active.

The [Commit Finality v2 ABI](../protocol/commit-finality-v2.md) gives the shared
projection, owner identity, opaque input type, and canonical stream helpers one
neutral public owner without exposing its private issuer. The public Draft
[Distributed Commit v2 ABI](../protocol/distributed-commit-v2.md) owns separate
epoch, proposal, witness, and certificate streams. A trusted external Byzantine
witness observation may only create a durable frozen witness finding; it cannot
create proposal support, evidence, a certificate, or output authority. The
public Draft
[Commit Decision v2 ABI](../protocol/commit-decision-v2.md) owns assessment,
bounded stability, seal, liveness, and typed terminal outcomes; its dual-Store
Conformance and provider-free terminal journey are active. Decision,
Certificate, Distributed, and the neutral Finality bridge now share one
aggregate-activated, public-only composition matrix. This closes the WP-05
Draft authority path; it does not promote the surface to Stable or describe a
complete application runtime.

The complete Draft semantics are documented in
[the Optimal Commit ABI](../protocol/optimal-commit-abi.md).

## Historical/private swarm semantics

Bee-swarm behavior is represented by independent scout reports, recruitment
signals, inhibition signals, consensus thresholds, and safe fallback.

Ant-colony behavior is represented by traceable pheromone memory, evaporation,
bounded contribution, source diversity, and deterministic scoring.

These concepts are retained implementation details, not a supported public
swarm profile or a swarm runtime.

## Internal Composition

The public Governance modules are cohesive facades over one-way private
engines. Commit state, support, certificates, distributed finality, optional
attention evaluation, and private pheromone lifecycle each have one
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
