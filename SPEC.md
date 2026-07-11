# PheroOS Protocol-Core Specification

Status: draft ABI v0.1

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
  e2e, basic swarm, Hybrid Pheromone, and adaptive-record replay behavior.

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
- `schemas/protocol.schema.json`
- `schemas/kernel.schema.json`
- `schemas/driver.schema.json`
- `schemas/trace.schema.json`

The public CLI surfaces cover manifest validation, conformance evaluation, and ABI schema export for capability, protocol, kernel, driver, and trace artifacts.

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

The current public ABI is draft `0.1.0`.

Before the first stable ABI release, changes may still refine dataclass fields, schema shape, and conformance checks. Such changes should be documented in `CHANGELOG.md`, reviewed through the contribution and API lifecycle process, and backed by tests or conformance.

The fail-closed Hybrid v1 tightening and consumer actions are recorded in
[`docs/protocol/hybrid-pheromone-v1-migration.md`](docs/protocol/hybrid-pheromone-v1-migration.md).

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
- `pheroos-source-v1` for the separate protocol-core source-surface and import
  boundary proof.

The applied profile is a gate: required checks must be present and passing for
the profile contract to pass.

Release validation is enforced by CI and release governance. The specification defines the invariants and compatibility expectations; it is not a local runbook.

## Governance Principle

Protocol declares what is available. Governance decides what is allowed. Drivers provide capability. Trace explains what happened. Conformance proves compatibility.

No extension should make agents the authority.
