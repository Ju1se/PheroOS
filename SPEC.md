# PheroOS Protocol-Core Specification

Status: Draft ABI v0.1.0. The exact local scoped-authority v2 profile is
implemented as Draft; no public lifecycle entry is formally Stable.

PheroOS is an open swarm-native multi-agent operating protocol-core package for governed multi-agent runtimes.

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
- Provider-free examples: deterministic compatibility examples for baseline,
  e2e, basic swarm, Hybrid Pheromone, adaptive-record replay, Hybrid Commit,
  portable certificate replay, distributed-finality behavior, and the durable
  scoped-authority v2 journeys.

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

- `schemas/capability.schema.json`
- `schemas/capability-v2.schema.json`
- `schemas/capability-v3.schema.json`
- `schemas/protocol.schema.json`
- `schemas/protocol-v2.schema.json`
- `schemas/protocol-v3.schema.json`
- `schemas/kernel.schema.json`
- `schemas/kernel-v2.schema.json`
- `schemas/runtime-scope-v1.schema.json`
- `schemas/driver.schema.json`
- `schemas/driver-v2.schema.json`
- `schemas/trace.schema.json`
- `schemas/authority-v2.schema.json`
- `schemas/commit.schema.json`
- `schemas/commit-tck.schema.json`
- `schemas/commit-tck-v2.schema.json`
- `schemas/commit-tck-request-v2.schema.json`
- `schemas/commit-tck-response-v2.schema.json`
- `schemas/scoped-authority-tck-v2.schema.json`
- `schemas/conformance-report-v2.schema.json`
- `schemas/scoped-trace-event-v1.schema.json`
- `pheroos/conformance/abi/public-python-api-v1.json`
- `pheroos/conformance/abi/public-python-api-lifecycle-v1.json`
- `pheroos/conformance/abi/runtime-compatibility-v1.json`
- `pheroos/conformance/abi/stable-python-api-v1.json`

The public CLI surfaces cover version/profile inspection, manifest validation,
conformance evaluation, catalog-derived schema list/show/export, typed wire
validation, TCK v1/v2 execution, scoped-authority TCK inspection, runtime
compatibility inspection, and public/candidate ABI show/diff operations. CLI
output is versioned JSON; the CLI does not start a server.

### Schema document versioning

The original unversioned Capability, Protocol, Driver, and Kernel schema IDs
are frozen v1 compatibility roots. Their unversioned CLI aliases remain pinned
to the same documents and must never silently move to a newer document:

| Surface | Frozen v1 `$id` / CLI alias | Additive document and exact selector |
| --- | --- | --- |
| Capability | `https://pheroos.dev/schemas/capability.schema.json` / `capability`, `capability-v1` | `capability-v2.schema.json` / `pheroos-capability-schema-v2`; `capability-v3.schema.json` / `pheroos-capability-schema-v3` |
| Protocol | `https://pheroos.dev/schemas/protocol.schema.json` / `protocol`, `protocol-v1` | `protocol-v2.schema.json` / `pheroos-protocol-schema-v2`; `protocol-v3.schema.json` / `pheroos-protocol-schema-v3` |
| Driver | `https://pheroos.dev/schemas/driver.schema.json` / `driver`, `driver-v1` | `driver-v2.schema.json` / `descriptor_version=pheroos-driver-descriptor-v2` |
| Kernel | `https://pheroos.dev/schemas/kernel.schema.json` / `kernel`, `kernel-v1` | `kernel-v2.schema.json` / `plan_version=pheroos-kernel-plan-v2`; companion `runtime-scope-v1.schema.json` |
| Scoped authority | no legacy alias | `authority-v2.schema.json` / `pheroos-authority-schema-v2`; `scoped-authority-tck-v2.schema.json` / `pheroos-scoped-authority-tck-v2` |

Capability and Protocol v2 identify stricter schema documents whose payloads
continue to carry `protocol_version=pheroos.protocol.v1`. Capability and
Protocol v3 are a separate exact pair for
`protocol_version=pheroos.protocol.v2` and require one closed scoped-authority
policy/profile selection. A v3 document never falls back to a v1 reader, and
readers never infer either semantic version from object shape. Driver's
`descriptor_version` is distinct from the external provider version in
`DriverDescriptor.version`. Kernel plan selection is independently controlled
by `plan_version`; Capability/Protocol v3 does not imply a Kernel Plan v3.

Typed migration is explicit and fail-closed. `upgrade_driver_descriptor_v1`
returns a complete v2 document or raises
`driver_descriptor_v1_not_migratable`; it does not delete duplicate or empty
declarations. `os_plan_v1_from_dict` returns a non-authoritative
`LegacyOSPlan`. `upgrade_os_plan_v1` requires canonical run scope, connection
readiness, driver probes, capabilities, and provider versions from the caller;
missing or contradictory facts reject migration rather than creating defaults.
The normative rules are in
[`docs/process/schema-v1-v2-migration.md`](docs/process/schema-v1-v2-migration.md).

The schema drift gate is:

```bash
python scripts/generate_schema_artifacts.py --check
```

The closed `pheroos.conformance.schema_catalog` is the only schema artifact
registry used by generation and the management CLI. `--write` writes only
catalog entries explicitly marked writeable, verifies frozen entries, and
cannot rewrite the four frozen v1 roots.

### Strict ABI loading

Capability JSON is validated before typed mapping. The internal validator and
checked-in schema artifacts enforce the schema keywords emitted by the schema
generator, including `type`, `enum`, `required`, `properties`, schema-valued
`additionalProperties`, `patternProperties`, `oneOf`, `items`, item-count
bounds, and numeric bounds. Unknown non-namespaced fields and invalid typed
shapes fail closed.

`NaN`, `Infinity`, and `-Infinity` are not valid manifest inputs. Booleans are
not numbers, and public governance entry points validate directly constructed
Python records again at the trust boundary. Inputs, intermediate values,
breakdowns, normalized scores, and final scores must remain finite. Frozen
public records defensively snapshot nested mutable data at their validation
boundary.

### Cohesive facades and static contracts

The reference package exposes cohesive package facades while keeping private
engines low-coupled and one-way. Public records, signatures, aliases, error
types, and canonical `__module__` ownership remain on their declared facades;
private commit-state, support, certificate, distributed, Hybrid, swarm, and
pheromone modules may change without becoming a second public ABI. Private
engines must not import an aggregate facade, form dependency cycles, install a
service locator, or acquire module-global runtime authority.

Built-in Commit Wire branches and Trace event types are declared in immutable
static contract tuples. Those declarations drive schema generation and runtime
validation from one rule owner. Unknown built-in authority records fail closed;
`x-*` and `ext.*` metadata stay open only as non-authoritative extensions.
Closed diagnostic-code registries are lifecycle artifacts, not runtime plugin
registries.

## Compatibility Requirements

A compatible implementation should satisfy these requirements:

1. Protocol manifests declare targets, candidates, quorum policy, trace policy, output policy, and any optional swarm policy they use.
2. Candidates reference declared targets.
3. Candidate commits and fallbacks are scoped to the active target.
4. Quorum fallback references a declared safe fallback candidate for the quorum target.
5. Baseline quorum commits only when support carrying a matching,
   governance-issued `SignalVerification` reaches `commit_threshold`;
   otherwise it falls back safely. A caller-provided `verified` boolean is not
   authority, and directly constructing the verification record does not issue
   it. Direct quorum policies require non-empty target and fallback bindings
   plus a positive integer commit threshold.
6. Collective fallback references a declared safe fallback candidate for the active target or defaults to the quorum fallback.
7. Output authorization requires the configured output contract. A conforming
   contract independently requires a committed candidate, non-empty
   provenance-bearing evidence, at least one `StopResolution` for the decision
   target with no matching resolution blocked, and publication permission.
   None of these gates is disableable. The commit gate also requires a
   protocol-declared candidate and a governance-issued quorum or collective
   decision. Resolutions for other targets neither approve nor block that
   output.
8. Trace events use `pheroos.trace.TraceEvent` semantics or a compatible provider-neutral representation.
9. Driver lifecycle follows `declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace`.
10. Driver registration, binding, exposure, and invocation fail closed when descriptors, grants, handles, or provenance are invalid.
11. Driver exposure uses declared driver permissions only; capability-level permissions do not become driver permissions by fallback.
12. Swarm-specific checks apply only when a manifest declares a swarm collective mode.
13. Baseline quorum protocols do not need to declare swarm behavior.
14. Extension metadata is preserved without granting evidence, permission, quorum, commit, or output authority.
15. Implementations pass the relevant versioned conformance profile for their declared protocol behavior.
16. Bee-swarm, ant-colony, and Hybrid scouts have non-empty, distinct identities, evidence identifiers,
    provenance, trace lineage, and matching governance verification before
    they count toward the independent-scout gate.
17. Bee-swarm, ant-colony, and Hybrid recruitment and inhibition inputs carry matching source, subject,
    target, provenance, trace lineage, and governance verification before they
    affect scores.
18. Hybrid candidate, trail, feedback, topology, layer, fallback, and output
    records remain scoped to the active target.
19. Hybrid score totals are exactly reconstructable from their declared score
    breakdown.
20. Learned, evolutionary, reactive, and metacognitive layers submit proposals;
    they do not submit authoritative coordination state, commit candidates, or
    authorize output.
21. `pheroos.protocol.PheromoneKindProfile` is the canonical manifest ABI
    declaration. Any `pheroos.governance.PheromoneKindProfile` compatibility
    export resolves to that same type.
22. Optimal Commit applies only when `collective_commit_policy` is declared;
    manifests without it retain their previous profile and behavior.
23. An active Commit profile derives truth only from governance-issued
    principal, risk, membership, observation, challenge, evidence, lease,
    stop, permission, replay, and prior-state records. Hybrid attention has
    zero direct commit or certificate authority.
24. The declared assurance never downgrades. Missing local, portable, or
    distributed proof yields progress or a declared terminal non-commit
    outcome.
25. Bounded liveness has an immutable absolute deadline. No active evaluation
    remains pending after that deadline, and every issued terminal outcome is
    deliverable.
26. Publication and execution are independent current actions; a historical
    commit certificate does not bypass their target/action/epoch-scoped stop,
    permission, freshness, or conflict gates.
27. Distributed finality verifies the declared Byzantine quorum intersection,
    exact proposal digest, membership epoch, witness replay/equivocation, and
    conflict freeze semantics.
28. One tenant/run `RuntimeScope` and its `scope_ref` bind Kernel plans, Driver
    invocations/results, Governance authority domains, and scoped Trace
    envelopes; cross-scope records fail closed.
29. Driver registration is conflict-safe and descriptor-lossless. Invocation
    receipts bind the exact scope, operation, request digest, invocation id,
    and idempotency key.
30. Durable Governance transitions use explicit current heads and
    compare-and-swap. State and Trace publish atomically, and only a verified
    store receipt may finalize durable output authority.
31. Unknown protocol, wire, profile, report, schema, TCK, or lifecycle-critical
    versions fail closed. Existing version identifiers do not change meaning
    in place.
32. The scoped-authority path accepts only the exact Capability/Protocol v3,
    `pheroos.protocol.v2`, policy, profile, wire, canonical, ledger, Store,
    Trace-batch, and read-set identifiers. Cross-version selection and
    authenticated-to-local fallback fail closed.
33. `AuthorityLevel`, caller booleans, digests, portable records, and public
    legacy issuers are not credentials. Authority v2 issuance requires a
    scope-, operation-, grant-, domain-, request-, epoch-, and Store-bound
    session; the authenticated profile additionally requires a host-selected
    external grant verifier.
34. Historical inclusion and current actionability are independent. A legal
    successor, restart, or domain seal does not erase committed history, while
    a stale, revoked, expired, retired, or conflicting grant cannot authorize a
    current action.
35. Baseline Output v2 commits one complete authority read-set and remains
    deliverable after publication or execution becomes unavailable. Delivery
    never substitutes for a current action permission.
36. A runtime compatibility claim must match the checked exact-version
    compatibility manifest and pass the named implementation TCKs. A
    self-reported root, transport success, or provider result creates no
    protocol authority.

## Scoped Authority v2 Draft Semantics

The exact local scoped-authority path is an implemented Draft vertical slice,
not a Stable or production-identity claim. Capability/Protocol schema v3
selects `pheroos.protocol.v2` plus
`pheroos-scoped-authority-local-v2`. The local profile trusts the
deployment-selected coordinator and StateStore writer. The separate
`pheroos-scoped-authority-authenticated-v2` profile requires a host-selected
issuer-grant verifier and has no fallback to local authority when that verifier
is absent or fails.

`GovernanceStateStoreV2` is the historical trust root. It validates a complete
multi-stream read-set and atomically commits immutable state, canonical
authority-critical Trace, and the exact receipt under compare-and-swap.
`AuthoritySessionV2` binds a non-portable capability to the selected Store,
ledger/domain, `RuntimeScope`, request, operation, grant activation, epoch, and
payload. Portable projections regain authority only after exact Store
inclusion and currentness verification; object identity and same-shaped bytes
are insufficient.

The Governance-owned Baseline Output v2 journey composes activation, verified
signal, action permission, output commit, exact retry, restart recovery,
revocation/expiry, successor currentness, and blocked publication without
exposing an opaque session or capability. Its terminal result is durable and
deliverable. Publication and execution remain separate current actions.
Commit Replay, Hybrid Replay, Risk, Support, Gate, Evidence, Decision,
Certificate, Distributed, and Finality v2 slices use the same portable-history
versus Store-authority separation.

The exact version composition for an external implementation is checked in
[`runtime-compatibility-v1.json`](pheroos/conformance/abi/runtime-compatibility-v1.json)
and documented in
[`runtime-compatibility-v1.md`](docs/conformance/runtime-compatibility-v1.md).
The candidate consumer surface is checked in
[`stable-python-api-v1.json`](pheroos/conformance/abi/stable-python-api-v1.json).
That artifact remains
`draft / promotion_candidate / formal_stable=false`; formal Stable promotion
requires the external-runtime, final-RC, audit, and protected-main gates in the
[API lifecycle](docs/process/api-lifecycle.md).

The detailed authority decision, threat model, migration, Store, session, and
baseline output contracts are:

- [Authority v2 decision](docs/protocol/authority-v2-decision.md)
- [Authority v2 threat model](docs/protocol/authority-trust-model-v2.md)
- [Authority v2 migration](docs/protocol/authority-v2-migration.md)
- [Governance StateStore v2](docs/protocol/authority-store-v2.md)
- [Authority Session v2](docs/protocol/authority-session-v2.md)
- [Baseline Output v2](docs/protocol/baseline-output-v2.md)

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

## Hybrid Pheromone Reference Semantics

A manifest that declares `mode="hybrid"` or another Hybrid-only pheromone
feature activates the complete Hybrid contract. It must not silently receive a
basic-swarm subset of semantics.

`evaluate_hybrid_collective_step(...) -> HybridCollectiveStep` is the public,
pure reference path. Conceptually, it accepts the protocol identity, declared
candidate set, collective policy, active target and step, plus:

- governance-verified scout, recruitment, and inhibition records
- existing and newly deposited trails
- declared subject topology and bounded feedback
- `LayerProposal`, `LayerPerformanceSnapshot`, and `StrategyBias` records
- bounded, run-scoped `PolicyAdjustmentProposal` records
- a governance-issued `HybridReplayState` used to prevent duplicate lifecycle
  application without accepting caller-forged processed identities

The reference step validates the complete batch before applying state changes,
then performs the declared policy-adjustment overlay, deposit, evaporation,
diffusion, feedback reinforcement, nonlinear response, L1-L4 coordination,
score construction, independent-scout gate, and declared-candidate
commit-or-safe-fallback sequence. It does not call providers, tools, networks,
secrets, storage, or runtime infrastructure.

Hybrid response and exploration floors are distinct: the bounded
`pheromone_exploration_floor` is a non-negative response baseline, while the
bounded `exploration_floor` adds novelty pressure only under explicit
`exploration_enabled`. Negative pheromone pressure is never erased by the
response floor, and neither floor bypasses the scout gate.

`HybridCollectiveStep` returns the governed decision and collective state,
active trails, layer coordination output, immutable adjustment overlay and
effective policy, deposit/evaporation/diffusion/reinforcement lifecycle
records, exploration observations, processed replay identities, budget state,
and `trace_events: tuple[TraceEvent, ...]`. The trace tuple
contains only lifecycle events that the step actually produced and carries the
lineage needed to reconstruct scoring, coordination, fallback, and commit.
Output authorization remains a separate outer call using evidence, a
target-scoped stop resolution, and publication permission.

A subsequent complete step obtains replay memory only from
`replay_state_from_hybrid_step(...)`. Non-empty raw processed-id sets are
rejected, and caller-provided trails cannot override a governance-issued replay
snapshot.
Replay receipts bind processed deposit, diffusion, feedback, and adjustment
identities to their canonical payloads, and receipt ids are disjoint across
lifecycle maps. Idempotence applies to an identical record, not to a different
record that merely reuses its trace id. Replay trace lineage carries the
complete receipt plus its recomputable digest. Actual-trace conformance must be
given the matching governance-issued prior replay state; caller-authored
matching hashes do not establish prior processing.

Rejected deposit, diffusion, and feedback `pheromone_clip` events carry a
versioned canonical `causal_payload` and SHA-256 `causal_fingerprint` owned by
the Trace ABI. Validation binds every normalized input field to the emitted
lineage and reconstructs the rejected request (including feedback
`strength_delta`/reward precedence). These receipts provide deterministic
append-only integrity only; they do not create evidence or authority.

External callers must not inject a precomputed `LayerCoordinationState` into
Hybrid scoring. That object is governance output. Callers submit proposals,
snapshots, and strategy biases so the reference path can validate bounds and
lineage and recompute the state. See
[`docs/protocol/hybrid-pheromone-v1-migration.md`](docs/protocol/hybrid-pheromone-v1-migration.md).

## Optimal Commit Reference Semantics

An optional `collective_commit_policy` selects one of `advisory`,
`evidence_bound`, `certified`, or `distributed` assurance. The policy declares
fixed-point evidence qualification, counterevidence and challenge rules,
support-lease and membership requirements, monotonic risk bands, a stability
window, an absolute deadline, terminal outcomes, certificate mode, and any
distributed fault model.

Governance computes capped positive evidence, capped counterevidence, net
evidence, unique active support clusters, qualifying source diversity, and the
leader margin. A substantive candidate becomes ready only when every declared
risk-adjusted gate passes. A tie or insufficient margin is not resolved by
candidate identifier or arrival order.

The first ready step is pending. A receipt-backed seal freezes the exact window
and authority roots. Evidence-bound finality is same-step; later certified or
distributed finality requires the exact next-step progress heartbeat. Leader,
gate, policy, epoch, risk, or membership changes reset the window according to
declared bounds. A monotonic replay append requires a freshly issued immutable
evaluation context and action gates and may preserve a continuous ready leader;
replay deletion, substitution, stale use, or a fork is invalid.

`evaluate_hybrid_commit_step(request=...)` is a total finalization boundary for
governance-issued upstream heads. It returns a `HybridCommitEvaluation` with
exactly one progress or outcome record, required proof records, terminal
delivery and current output-action decisions for governance-issued outcomes,
canonical trace, diagnostics, and a root over every authority leaf. A
diagnosable malformed runtime fact does not enter a legacy evaluator or escape
as an uncaught governance decision error. Attention is explicitly
non-authoritative: an invalid or unavailable attention/directive binding emits
a structured diagnostic and empty attention projection without changing the
commit liveness, certificate, output, or trace decision.

The absolute deadline produces one of `evidence_commit`, `safe_fallback`,
`advisory`, `blocked`, `invalid`, `finality_unavailable`, or
`safety_violation`. Only `evidence_commit` is an epistemic commit. All issued
terminal outcomes are deliverable; publication and execution remain separate
current-action decisions.

Distributed assurance uses static verified membership and requires
`n >= 3f + 1` and `2q - n > f`. Witnesses bind both the full proposal digest
and its semantic commit-value root, plus exact target/candidate/epoch/
membership/failure-domain/nonce/expiry leaves. Different envelopes that prove
the same value are retries, not safety conflicts. Two final certificates with
different candidate, claim, output, or authority-root values freeze the epoch
and require declared recovery plus an epoch-transition certificate.

Hybrid pheromone, recruitment, inhibition, and layer proposals continue to
drive attention and external evidence collection, but do not enter commit
metrics or certificate truth roots. See
[`docs/protocol/optimal-commit-abi.md`](docs/protocol/optimal-commit-abi.md) and
[`docs/protocol/optimal-commit-v1-migration.md`](docs/protocol/optimal-commit-v1-migration.md).

## Scoped State and Atomic Trace

`RuntimeScope` is the cross-surface tenant/run identity. Its canonical
`scope_ref` is carried by Kernel runtime records, Driver invocation envelopes,
Governance `AuthorityDomain`, and `ScopedTraceEvent`. Matching payload data in
another scope is neither a retry nor reusable authority.

The legacy Draft `GovernanceStateStore` remains available for its declared
compatibility cohort. The exact scoped-authority path uses
`GovernanceStateStoreV2`, with explicit multi-stream heads, immutable prepared
transitions, complete read-sets, atomic state-plus-Trace batches, CAS,
idempotent transition ids, identity claims, receipts, inclusion proofs,
snapshots, historical rehydration, domain sealing, retirement, and tombstones.
`InMemoryGovernanceStateStoreV2` is the deterministic reference adapter for
tests and examples. It is not a production database.

The durable Hybrid Commit boundary is `prepare -> atomic_commit -> receipt
verification -> finalize`. A prepared evaluation is a proposal. State must not
advance without its exact Trace batch; stale heads request a retry; failures
redact output authority; retirement is permanent for that scope. External
runtimes may implement database-backed adapters outside protocol-core and must
pass the same scope, restart, CAS, idempotency, atomicity, and retirement
conformance.

`ScopedTraceStoreV2` is the separate provider-neutral append-only lineage
boundary for scope-bound canonical events, checkpoints, idempotent append, and
restart. `DriverInvocationStoreV2` provides the corresponding
provider-neutral invocation receipt/checkpoint boundary. Neither Store creates
Governance authority. External StateStore, TraceStore, and DriverInvocationStore
fixtures use the public conformance-adapter Protocols and execute the same
exact-version matrices as the bundled in-memory references.

The provider-free Runtime Integration v1 transcript composes the compatibility
manifest, RuntimeScope, Protocol, Kernel, Driver, Governance, output, and Trace
layers. It verifies restart recovery and current action gates through the
adapter's public Store readers rather than trusting booleans or self-reported
roots. A real provider, production database, process boundary, transactional
outbox, wall-clock cancellation, and external effect remain responsibilities
of an independent runtime.

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

External runtimes map `DriverSpec` declarations to real adapters outside
protocol-core. That mapping must preserve the governance, trace, evidence, and
secret-boundary rules defined by this specification.

Namespaced trace and pheromone extensions may record external runtime lineage or metadata, but unknown extensions do not score candidates or authorize decisions by default.

Extensions should not add:

- provider SDKs to protocol-core
- app runtime infrastructure
- background services
- dashboards
- domain-specific workflows
- broad policy or protection frameworks without conformance-backed invariants

## Versioning

The current package and public ABI version is Draft `0.1.0`.

The package version has one dependency-free owner, `pheroos._version`, and is
re-exported as `pheroos.__version__`. The legacy manifest path accepts the
explicitly supported `pheroos.protocol.v1`. The separate exact authority
manifest readers accept `pheroos.protocol.v2` only with Capability/Protocol
schema v3 and a complete scoped-authority declaration. Neither reader maps an
unknown or mismatched version to current defaults.

Before the first stable ABI release, changes may still refine dataclass fields, schema shape, and conformance checks. Such changes should be documented in `CHANGELOG.md`, reviewed through the contribution and API lifecycle process, and backed by tests or conformance.

The fail-closed Hybrid v1 tightening and consumer actions are recorded in
[`docs/protocol/hybrid-pheromone-v1-migration.md`](docs/protocol/hybrid-pheromone-v1-migration.md).
The opt-in Optimal Commit activation and no-downgrade migration are recorded in
[`docs/protocol/optimal-commit-v1-migration.md`](docs/protocol/optimal-commit-v1-migration.md).
The scoped-authority selection, migration, and earliest possible legacy
removal window are recorded in
[`docs/protocol/authority-v2-migration.md`](docs/protocol/authority-v2-migration.md).

`pheroos/conformance/abi/stable-python-api-v1.json` is a reviewed, type-closed
promotion candidate, not a Stable lifecycle inventory. Until the separately
governed promotion gate succeeds, its lifecycle is
`draft / promotion_candidate / formal_stable=false`, and the public lifecycle
inventory contains no formally Stable export. The supported public-facade
consumption path is documented in the
[Stable Core consumer contract](docs/protocol/stable-core-consumer.md).

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

Reports include the applicable profile version:

- `pheroos-manifest-v1` for manifest validation.
- `pheroos-core-v1` for baseline governed protocols.
- `pheroos-swarm-v1` for manifests declaring swarm collective behavior.
- `pheroos-hybrid-swarm-v1` for Hybrid declarations; it includes the core,
  swarm, and Hybrid required checks for subject scoring, kind profiles,
  diffusion, reinforcement, response, layer coordination, adjustment bounds,
  trace lineage, and authority boundaries.
- `pheroos-source-v3` for the separate protocol-core source-surface, lifecycle,
  durable-authority, replaceable StateStore/TraceStore, scope, and import
  boundary proof. It supersedes source-v2 by adding the TraceStore contract.
- `pheroos-commit-integrity-v1` for advisory or evidence-bound Optimal Commit.
- `pheroos-hybrid-commit-v1` for evidence-bound Optimal Commit with Hybrid
  attention semantics.
- `pheroos-certified-commit-v1` for independently verifiable portable proof.
- `pheroos-distributed-commit-v1` for Byzantine quorum finality and conflict
  handling.
- `pheroos-governance-state-store-conformance-v2`,
  `pheroos-governance-authority-session-conformance-v2`, and
  `pheroos-scoped-authority-tck-v2` for the durable scoped-authority trust
  boundary.
- `pheroos-baseline-output-conformance-v2`,
  `pheroos-driver-invocation-store-conformance-v2`,
  `pheroos-scoped-trace-store-conformance-v2`, and
  `pheroos-runtime-integration-conformance-v1` for the provider-neutral
  external-runtime composition.

The applied profile is a gate: required checks must be present and passing for
the profile contract to pass.

The frozen Commit TCK v1 contains 38 exact JSON vectors plus executed
mutation/permutation variants. TCK v2 uses expected-free request/response
records: adapters cannot observe expected results, and the public reference
adapter must agree with an independent standard-library spec-model adapter on
the same declarative cases. Echo/constant, malformed, out-of-order,
state-leaking, and timeout adapters are rejected. Active Commit checks return
PASS or FAIL; skip/N/A is not a compatibility result. Both TCK generations
must run from source and from isolated wheel and sdist installations under an
external working directory.

Release-candidate validation is defined by the local fail-closed dry-run and
the reviewed release workflow. It builds one subject wheel/sdist, uses a
separate comparison build only for reproducibility, validates the subject from
an external working directory, and derives CycloneDX, SPDX, hashes, ABI diff,
and migration evidence from those exact bytes. A real candidate still requires
a clean candidate commit; remote tag, Release, attestation, ruleset activation,
Stable promotion, and GA are separately authorized release actions. CI
provenance does not create protocol evidence, permission, or Governance
authority. This specification defines invariants and compatibility
expectations; it is not a local runbook.

## Governance Principle

Protocol declares what is available. Governance decides what is allowed. Drivers provide capability. Trace explains what happened. Conformance proves compatibility.

No extension should make agents the authority.
