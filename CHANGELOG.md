# Changelog

All notable changes to PheroOS protocol-core should be documented here.

The project is currently pre-stable. Until the first stable ABI release, entries should call out schema, conformance, and migration impact explicitly.

## Unreleased

### Removed

- Withdrew the unshipped Draft helper
  `commit_replay_receipt_v2_from_v1` before WP-05 public activation. A portable
  v2 replay receipt does not inherit authority from a process-local v1 receipt;
  callers must construct the explicit portable record and obtain authority only
  through StateStore-backed prepare, session, commit, and rehydration. The v1
  receipt ABI itself remains available under the declared compatibility window.

### Deprecated

- Recorded the exact 86-name WP-05 legacy authority cohort as Deprecated with
  fully qualified, public, StateStore-backed v2 replacements and an earliest
  removal version of `0.3.0`. The cohort covers process-local Hybrid replay,
  Commit replay/window/finality, Risk, Membership/Support, certificate/local
  finality, and Distributed authority entrypoints only. Portable historical
  records, codecs, body-root helpers, and independent verification remain
  Draft data surfaces. No legacy implementation or registry is physically
  removed by this lifecycle change.

### Added

- Added a Governance-owned Draft Baseline Output v2 aggregate write entrypoint
  for the Stable promotion candidate. External runtimes pass only a versioned
  Store/domain, portable grant and activation identity, optional host verifier,
  exact portable verified-signal requests, and a portable output request.
  Governance retains opaque capability/session custody and returns only a
  portable commit attempt or Baseline result. Strict consumer and wheel/sdist
  evidence covers committed output, duplicate-free retry, restart recovery,
  revocation, expiry, currentness loss, and blocked publication. The candidate
  remains `formal_stable=false`; no provider, database, runtime, or external
  effect was added.
- Added a clean-commit-only release-candidate dry-run that separates the
  publishable wheel/sdist subject from the comparison-only second build,
  materializes verified raw blobs from the captured Git commit/tree before
  either build without archive attributes or checkout filters, verifies
  identical source/wheel/sdist external-CWD transcripts, and emits an
  allowlisted staging set with artifact-derived CycloneDX/SPDX, Stable-candidate
  ABI diff, migration notes, release manifest, commit/tree identity, and
  SHA-256 bindings. SBOM identity is single-valued and bound to distribution
  filenames and metadata roots. CI tools install only from a hash-closed Ubuntu
  x86_64 wheel lock verified for CPython 3.12–3.14; editable source installation
  is offline and `--no-deps`. The reviewed workflow header and complete job
  blocks have exact execution-context digests. The companion workflow remains
  read-only and cannot tag or publish; disabled `v*` tag update/deletion rules
  are only a WP-13 activation proposal.
- Machine-readable engineering baseline and repository-policy gates for the
  production-readiness program. The baseline records one-way test, Ruff,
  Mypy, complexity, dependency, and artifact-integrity floors; CI exposes one
  required `quality-gate` result and a disabled, reviewable main-branch
  ruleset proposal without claiming that remote protection is active.
- Implemented the additive Draft WP-02 StateStore v2 slice: exact canonical
  Protocol/Governance records, bounded multi-read/single-write atomic commits,
  immutable historical inclusion with `CURRENT`/`SUPERSEDED`/`SEALED`
  observations, typed total failures and reconciliation, atomic domain seals,
  deterministic restart equivalence, a private provider-free reference Store,
  and one exact-version Conformance matrix shared with an independent stdlib
  model. This does not activate an authority v2 manifest profile, add a
  database, or change v1 wire behavior.
- Implemented the public Draft WP-03 Authority Session v2 slice: strict
  portable issuer grants/verifications/requests, opaque store- and run-bound
  capabilities, request-specific least-privilege sessions, atomic
  verified-signal and domain-retirement paths, four authority-critical Trace
  contracts, exact StateStore-version and Trace-batch domain binding, and one
  reusable exact-version Conformance matrix shared by the reference and
  independent stdlib StateStore models. The complete scoped
  authority manifest profile, external verifier TCK, and Output v2 remain
  inactive; no v1 behavior, database, provider, or runtime was added.
- Accepted scoped authority v2 decision set: an explicit
  `pheroos.protocol.v2` opt-in, separate v3 Capability/Protocol schema
  documents, local and authenticated authority profiles, an atomic bounded
  authority read-set, historical inclusion/current-position separation,
  provider-neutral StateStore and verifier Conformance contracts, a 17-code
  diagnostic registry, and strict v2-or-fail migration with no v1 assurance
  fallback. Existing v1 manifests and schema-document v2 artifacts retain
  their current bytes and meaning.
- Four explicit schema-document tracks with byte-frozen v1 `$id`/CLI aliases
  and separate versioned v2 artifacts: `capability.schema.json`/`capability`
  to `capability-v2.schema.json`, `protocol.schema.json`/`protocol` to
  `protocol-v2.schema.json`, `driver.schema.json`/`driver` to
  `driver-v2.schema.json`, and `kernel.schema.json`/`kernel` to
  `kernel-v2.schema.json`. Unversioned aliases never move to v2 silently.
- Strict Capability and Protocol v2 documents retain payload
  `protocol_version=pheroos.protocol.v1`. Driver v2 uses the independent
  `descriptor_version=pheroos-driver-descriptor-v2` discriminator rather than
  `DriverDescriptor.version`; Kernel v2 independently requires
  `plan_version=pheroos-kernel-plan-v2`.
- Exact typed reader selection and non-lossy v1 migration: Driver upgrade
  rejects non-migratable declarations, while Kernel v1 parses only to
  `LegacyOSPlan` and requires caller-supplied scope, readiness, probe,
  capability, and provider-version facts before v2 authority can exist.
- One schema drift generator that verifies four frozen v1 SHA-256 roots and
  four checked-in v2 artifacts without ever rewriting v1 compatibility files;
  use `python scripts/generate_schema_artifacts.py --check` for the drift gate.
- Cross-surface `RuntimeScope`/`scope_ref` binding for Kernel plans, Driver
  invocation, Governance authority domains, scoped Trace, and conformance.
- Driver ABI v2 descriptors, conflict-safe registration, readiness probes, and
  invocation/result receipts bound to scope, operation, request digest,
  invocation id, and idempotency key without descriptor field loss.
- Provider-neutral `GovernanceStateStore` with CAS heads, immutable prepared
  transitions, atomic state-plus-Trace batches, identity claims, receipts,
  checkpoint rehydration, permanent retirement, and tombstones, plus a
  deterministic in-memory reference adapter.
- Atomic Hybrid Commit `prepare -> commit -> receipt verification -> finalize`
  boundary. Failed or stale transitions cannot expose the proposed evaluation,
  receipt, or durable output authority.
- Versioned Conformance Report v2 with subject kind, implementation identity,
  artifact digest, and stable check projection; manifest and source proof are
  separate subjects.
- Expected-free Commit TCK v2 request/response and JSONL adapter protocol, 23
  declarative cases, an independent standard-library spec model, and negative
  echo/constant/malformed/order/state/timeout harness tests. TCK v1 roots remain
  frozen.
- Checked-in Python public-shape and lifecycle artifacts covering six package
  facades, signatures, dataclass/default/enum/constant/alias shapes,
  compatibility modules, diagnostics, replacements, and removal versions.
- Thin management CLI commands for `version`, `profile`, `schema`, typed
  `wire validate`, TCK v1/v2, and ABI show/diff operations.
- Static Trace event-contract registry and decomposed event/store/validation/
  lineage modules with exactly one validator for every built-in event while
  keeping namespaced non-authoritative extensions open.
- Reference performance budgets for cold imports, manifest validation, TCK,
  Trace append, scope retirement, and diffusion scaling, with hard ceilings
  that baseline refresh cannot relax.
- Reproducible CI/release gates spanning Python 3.12 through 3.14, critical
  lint and incremental typing, ABI/schema/TCK/scope/atomicity checks, isolated
  wheel and sdist consumers, exact CI-tool constraints, deterministic
  CycloneDX/SPDX SBOMs, pinned Actions, and trusted-main provenance
  attestations without requiring write tokens on fork pull requests.
- Legacy pheromone migration APIs: explicit trail lineage normalization and a
  single versioned per-kind runtime profile map.
- Machine-readable D-01 through D-18 removal lifecycle and a human-readable
  architecture removal ledger.

- Optional, profile-selected Optimal Commit Draft ABI with fixed-point evidence
  qualification, counterevidence disposition, challenge coverage, verified
  principal clusters, eligible membership, evidence-bound support leases,
  monotonic risk heads, unique-leader margin, and stable commit windows.
- Bounded commit liveness with immutable deadlines, receipt-backed window
  seals, exact late-finality heartbeats, typed progress/outcomes, and mandatory
  terminal delivery separated from publication and execution.
- Local receipts, independently verifiable evidence certificates, outcome
  certificates, action-scoped stop/permission authority, and complete
  certificate/output leaf verification.
- Static-epoch Byzantine distributed finality with `n >= 3f + 1`, quorum
  intersection, exact witness proposal digests, witness replay/equivocation,
  provisional state, conflict freeze, recovery, and epoch-transition proofs.
- Hybrid attention-only projection, exploration directives, channel binding,
  and the total `evaluate_hybrid_commit_step(request=...)` finalization path;
  attention cannot directly affect commit truth or certificates.
- Explicit Hybrid attention availability isolates malformed or mismatched
  advisory inputs from commit liveness while retaining a bound diagnostic.
- Distributed witnesses bind full proposal envelopes and semantic commit-value
  roots, so equivalent retries do not masquerade as split-brain conflicts.
- Strict 51-branch Commit Wire schema, exported `schemas/commit.schema.json`,
  and CLI `schema export commit` support.
- Event-specific Optimal Commit Trace ABI and replay from principal/risk/
  evidence/lease lineage through metrics, window, certificate/finality,
  outcome, and output action decisions.
- Implementation-neutral 38-case JSON Commit TCK, checked-in aggregate/split
  vectors, exact mutation/permutation runner, and public conformance API.
- Commit integrity, Hybrid Commit, certified, and distributed conformance
  profiles with 20 complete active checks and no skip/N/A path.
- Provider-free Hybrid Commit, certificate replay, and distributed-finality
  examples plus Optimal Commit ABI and migration documentation.

- Formal protocol-core specification in `SPEC.md`.
- API and ABI lifecycle policy in `docs/process/api-lifecycle.md`.
- Extension boundary guidance in `docs/protocol/extension-points.md`.
- Release checklist in `docs/process/release-checklist.md`.
- Concrete kernel, driver, and trace schema export helpers.
- Capability schema artifact and CLI export for the full manifest shape.
- CLI schema export tests for capability, protocol, kernel, driver, and trace surfaces.
- Stigmergic Memory ABI draft for swarm-native pheromone behavior.
- Uniform pheromone subject model with candidate, route, tool, evidence, and agent subjects.
- Positive, negative, cautionary, novelty, and stale pheromone semantics.
- Pheromone provenance, trace binding, source caps, deposit caps, source diversity, TTL expiry, and deterministic decay models.
- Pheromone trace events for deposit, evaporate, score, clip, expire, and inhibit.
- `pheromone_behavior` conformance check for runtime pheromone boundaries.
- Manifest `extensions` metadata for protocol ABI objects, preserved without granting authority.
- Provider-neutral `DriverSpec` manifest declarations with opaque external `config_ref`.
- Namespaced trace extension events using `x-*` or `ext.*`.
- Namespaced pheromone metadata values that validate structurally without scoring candidates by default.
- Step-level collective decision helper for deterministic pheromone evaporation, scoring, and evaluation order.
- Runtime integration contract for external multi-agent runtimes in `docs/protocol/runtime-integration.md`.
- Runtime adapter mapping contract in `docs/protocol/runtime-adapter-guide.md`.
- `extension_contract` conformance check for extension and secret-boundary compatibility.
- Versioned conformance profiles for manifest validation, baseline governed protocols, and swarm protocols.
- Baseline quorum evaluator for threshold-based declared-candidate commits and safe fallback.
- `kernel_contract` conformance check for Kernel ABI planning, materialization, and syscall authority boundaries.
- Governance-issued `SignalVerification` records bound to a target, source,
  subject, verifier authority, provenance, and trace lineage.
- Full `evaluate_hybrid_collective_step(...)` reference path and
  `HybridCollectiveStep` result, including governed decision state, active
  trails, coordination and adjustment outputs, lifecycle records, replay and
  budget state, and canonical `trace_events`.
- `pheroos-hybrid-swarm-v1` conformance profile for the complete Hybrid
  Pheromone contract and `pheroos-source-v1` for separate source-boundary proof.
- Event-specific Hybrid trace lineage and defensive append-only trace
  snapshots.
- Versioned rejected-pheromone-clip causal receipts, with public canonical
  payload and SHA-256 fingerprint helpers in `pheroos.trace` and matching
  conditional JSON Schema contracts.
- Source conformance proof for canonical public type ownership, immutable
  driver-registry inspection, and representative defensive snapshots.
- Causal Hybrid trace conformance that replays lifecycle transitions into
  active memory and recomputes full proposal/snapshot coordination state.
- Provider-free Hybrid Pheromone and adaptive-record replay examples.

### Changed

- Public API inventory canonicalizes version-specific private `pathlib`
  storage modules to the stable public type identity, so one checked artifact
  is valid across Python 3.12, 3.13, and 3.14.
- Repeated SHA-256 authority validation now uses one shared, strict,
  C-backed validator. Accepted syntax and fail-closed errors are unchanged;
  the TCK performance gate is met without raising its locked ceiling.
- The TCK v1 performance gate now uses the median process-tree CPU time of
  complete runs, including completed child processes. This excludes hosted
  runner scheduling waits without hiding isolated-subprocess work. Feature
  branches run CI through the pull request event only; `push` remains enabled
  on `main` for provenance.
- Commit canonicalization now fast-paths exact JSON builtins, and Hybrid
  attention/replay verification reuses already verified intermediate roots.
  Subclasses, custom containers, public fail-closed entry points, errors, TCK
  roots, all 92 evaluations, and isolated subprocess checks remain unchanged.
- Source conformance is versioned as `pheroos-source-v3`; it adds a public
  `TraceStore` Protocol and reusable external StateStore/TraceStore adapter
  matrices instead of proving only the bundled in-memory implementations.
- Unknown protocol and other critical ABI versions now fail closed instead of
  falling through to current defaults.
- Governance is a generated static lazy facade; importing a submodule no longer
  eagerly imports the complete commit/swarm engine graph.
- Conformance now uses a static, thread-safe lazy facade with its compatibility
  modules covered by the lifecycle artifact. The Commit TCK artifact path also
  defers the optional reference adapter, avoiding Governance imports without
  changing any of the 92 evaluations or the locked performance ceiling.
- Canonical Commit TCK dataclass annotations now resolve correctly from their
  public module on every supported Python version; identity, signatures,
  type hints, and pickle round trips remain stable across lazy resolution.
- Legacy process authority registries are quarantined behind one private
  compatibility adapter. New durable authority modules cannot import it.
- Hybrid pheromone scalar/profile double writes now have one deterministic
  rule: an explicit per-kind profile wins in full and legacy scalars synthesize
  only missing built-in kinds.
- `evaluate_hybrid_commit_step(request=...)` is the single total evaluator
  entry. `evaluate_hybrid_commit_evaluation(...)` is a warning compatibility
  alias over the same engine.
- Package import conformance now rejects database, web-server, provider SDK,
  queue/worker, and removed runtime framework roots from protocol-core.
- Completed multi-thousand-line execution plans are retired to short historical
  stubs after their normative content moved into maintained ABI, migration,
  runtime, conformance, lifecycle, and release documents.

- `collective_commit_policy`, when explicitly declared, now takes profile
  precedence over legacy swarm selection without changing manifests that omit
  it.
- Hybrid pheromone, recruitment, inhibition, and layer contributions are
  commitment-independent attention inputs under active Commit profiles; only
  newly governance-verified evidence can affect a later assessment.
- Public Protocol, Governance, Trace, and Conformance exports now include the
  complete Optimal Commit wire, authority, finality, replay, and TCK surfaces.

- Source-tree documentation is organized around stable protocol, process, security, and conformance documents.
- `CONTRIBUTING.md` now contains the protocol change proposal requirements.
- `SECURITY.md` now describes protocol-core security scope and no longer documents removed runtime behavior.
- Swarm protocol example now declares bounded, traceable, evidence-bound pheromone policy fields.
- Conformance now covers pheromone behavior boundaries in addition to pheromone policy shape.
- GitHub Actions validation is expected to cover baseline, e2e, and swarm protocol conformance.
- Capability driver declarations are loaded as typed provider-neutral driver specs while preserving compatibility with generic driver ABI behavior.
- Trace validation accepts namespaced extension events while preserving canonical built-in event validation.
- Trace event validation now enforces a non-empty `reason`, matching the trace schema required field.
- Manifest loading now rejects invalid raw JSON shapes before typed defaults or coercion are applied.
- Exported capability, protocol, kernel, driver, and trace schemas now declare stricter unknown-field boundaries.
- Driver lifecycle operations now fail closed for invalid descriptors, inactive registrations, unpermissioned exposure, and missing invocation provenance.
- Kernel driver syscalls now reject unready runtime contexts and unpermissioned driver exposures.
- Conformance reports now include the applied profile version.
- Governance commits, quorum fallback, collective fallback, and recovery failure candidates are now scoped to declared targets.
- Output authorization now requires non-empty provenance-bearing evidence when the output contract requires evidence.
- Kernel driver exposure no longer falls back from missing driver permissions to capability-level permissions.
- Conformance profiles now enforce required checks through `profile_contract`.
- Driver conformance now requires declared driver capabilities and driver permissions.
- Exported kernel schema now covers the full `OSPlan` authority surface instead of only runtime context identity fields.
- Kernel runtime materialization now filters unpermissioned driver exposures and exposes no callable resources from not-ready plans.
- Kernel driver syscalls now reject driver results without provenance.
- Quorum support now fails closed unless it carries a matching
  governance-issued `SignalVerification`; the legacy caller-controlled
  `verified` boolean and directly constructed verification records no longer
  grant authority.
- Bee, ant, and Hybrid scout, recruitment, and inhibition records now require complete
  identity, target, provenance, trace, and verification bindings before they
  count or score.
- Output authorization now treats commit, evidence provenance, target-scoped
  stop resolution, and publication permission as four independent gates.
  Empty resolutions and resolutions for another target cannot authorize
  output. These gates cannot be disabled by manifest or `OutputContract`
  flags, and commit authorization is bound to a protocol-derived candidate set
  plus a governance-issued quorum or collective decision.
- Direct quorum evaluation now rejects empty target/fallback bindings and
  non-positive, boolean, fractional, or otherwise non-integer commit
  thresholds before counting signals.
- Manifest loading and internal schema validation now reject non-finite JSON,
  invalid typed shapes, unsupported schema branches, invalid bounds, and
  unknown non-namespaced fields before typed mapping. Governance entry points
  independently enforce finite numeric records constructed in Python.
- `pheroos.protocol.PheromoneKindProfile` is the canonical public declaration;
  the governance compatibility export refers to the same type instead of a
  second representation.
- Hybrid layer coordination is recomputed from validated `LayerProposal`,
  `LayerPerformanceSnapshot`, and `StrategyBias` inputs. Caller-constructed
  `LayerCoordinationState` is no longer accepted as authoritative Hybrid score
  input.
- Hybrid conformance is profile-driven and manifest-driven, and returns a
  structured report even when an individual check raises or a valid manifest
  contains only a safe fallback candidate.
- The two Draft Hybrid exploration controls now have separate deterministic
  semantics: `pheromone_exploration_floor` is a bounded response baseline and
  `exploration_floor` is bounded novelty pressure gated by
  `exploration_enabled`; both are constrained to `[0, 1]`.
- Novelty trails are now no-score when exploration is disabled, and full-step
  evaporation preserves the declared novelty-decay effect before advancing
  lifecycle time.
- Hybrid score trace now records canonical active trails and complete upstream
  score lineage; conformance reconstructs those scores and rejects impossible
  manifest bounds or adjustment authority.
- Run-scoped global evaporation and response-model adjustments now take
  precedence over per-kind overrides for that run, preventing accepted but
  behaviorally shadowed adjustments.
- Direct governance policy-adjustment validation now enforces the same
  cross-field envelope as Protocol ABI validation: layer-weight adjustments
  must stay inside the owning `layer_weight_bounds`, and cautionary override
  thresholds must stay within `pheromone_max_strength`.
- Complete Hybrid replay now accepts only a governance-issued
  `HybridReplayState` derived with `replay_state_from_hybrid_step(...)`;
  caller-forged processed-id sets and trail overrides are rejected.
- Hybrid replay receipts bind each processed deposit, diffusion, feedback, and
  adjustment id to its immutable payload; same-id payload substitution and
  cross-lifecycle trace-id reuse fail closed. Replay trace events carry the
  complete canonical receipt so Trace can recompute the digest.
- Hybrid trace conformance accepts replay claims only with the matching
  governance-issued prior `HybridReplayState`; matching caller-authored hashes
  or a coordinated score-anchor rewrite are not replay authority.
- Rejected deposit, diffusion, and feedback `pheromone_clip` events now bind
  every normalized lifecycle input in `causal_payload` and
  `causal_fingerprint`. Trace validation reconstructs deposit strength,
  diffusion attenuation, feedback delta/reward requests, source state, timing,
  and topology lineage before accepting the event. The receipt is integrity
  lineage only and grants no evidence or governance authority.
- Candidate, evidence, protocol-policy, Driver, Kernel, governance-result, and
  replay authority collections now use immutable defensive snapshots across
  their trust boundaries.

### Removed

- Duplicate Kernel/Driver immutable helpers, duplicate Protocol snapshot
  helpers, scattered Governance primitive validators, the Trace store private
  compatibility property, and the eager Governance facade implementation.
- Scattered module-owned mutable authority dictionaries and registry locks;
  remaining v1 compatibility state has one explicitly quarantined owner.

- Historical goal, execution-plan, and migration-inventory Markdown documents from the public source tree.
- The standalone protocol proposal stub after merging its requirements into `CONTRIBUTING.md`.
- The standalone security overview after merging protocol security scope into `SECURITY.md`.
- Unused protocol composition helper, unused protocol error shim, unused driver result re-export, and unused stop-signal manifest parser.

### Compatibility

- Existing v1 manifest, schema, Trace, Commit Wire, profile-selection, example,
  and TCK v1 roots remain compatibility artifacts. New semantics use new
  version identifiers instead of changing published identifiers in place.
- The legacy two-field `PheromoneTrail` constructor and scalar weight fields
  remain Draft compatibility surfaces. New consumers should normalize explicit
  lineage and consume the canonical per-kind profile map before their future
  profile-version removal.
- The frozen blended-score selector remains only in `_legacy/hybrid_v1.py` for
  baseline profile compatibility and cannot issue certificate, store, Trace,
  or output authority.

- Optimal Commit is opt-in. Baseline toy/e2e, basic swarm, and Hybrid Pheromone
  v1 manifests keep their prior profile, result, and trace behavior when they
  do not declare `collective_commit_policy`.
- An active assurance never falls back to a lower proof. Missing proof produces
  progress or a declared terminal non-commit outcome.
- Every issued terminal outcome remains deliverable; fallback, advisory,
  invalid, blocked, finality-unavailable, and safety-violation outcomes are not
  evidence commits.
- Unknown critical Commit fields or versions fail closed. Noncritical extension
  metadata remains open but cannot create evidence, authority, or output
  permission.

- Baseline toy and e2e protocols remain compatible without declaring swarm behavior.
- Swarm-specific validation and conformance apply only when a manifest declares swarm collective behavior.
- Pheromone is not evidence, quorum, permission, or output authority.
- Extension metadata is not evidence, permission, quorum, commit authority, or output authority.
- Secret-like manifest fields are rejected or diagnosed instead of being accepted silently.
- Draft ABI manifests with unknown non-namespaced fields or invalid primitive/list/object shapes are rejected at load time.
- Draft ABI driver invocation paths must expose only granted permissions and include provenance when invoking through the core lifecycle helper.
- Draft ABI multi-target protocols must keep fallback and commit candidates scoped to the active target.
- Draft ABI output flows with `requires_evidence_contract` must provide at least one provenance-bearing evidence node.
- Draft ABI kernel plans should serialize the complete OSPlan surface when validated against `schemas/kernel.schema.json`.
- Draft ABI kernel conformance now requires `kernel_contract` for baseline and swarm protocol profiles.
- Draft ABI quorum and Hybrid collective callers must obtain
  `SignalVerification` from governance authority; self-asserted verification
  and bare booleans are ignored or rejected.
- Draft ABI output callers must provide a non-blocking `StopResolution` whose
  target matches `QuorumDecision.target` when stop resolution is required.
- Draft ABI Hybrid manifests select `pheroos-hybrid-swarm-v1`; baseline quorum
  and basic swarm manifests retain their existing required fields and profile
  scopes.
- Draft ABI JSON inputs must be schema-valid and finite. Inputs that depended
  on coercion, sentinel defaults, `NaN`, infinity, or unknown non-namespaced
  fields now fail closed.
- Draft Hybrid consumers must stop treating the two exploration floors as
  aliases; see the Hybrid v1 migration note for their distinct meanings.
- `PheromoneTrail(candidate_id, strength)` remains a supported compatibility
  constructor.

### Migration Notes

- Carry one `RuntimeScope` per tenant/run through Kernel, Driver, Governance,
  and Trace. Reject rather than translate cross-scope results.
- Production runtimes should implement `GovernanceStateStore` outside core and
  finalize durable output only after verifying its atomic commit receipt.
- Replace new calls to `evaluate_hybrid_commit_evaluation` with
  `evaluate_hybrid_commit_step(request=...)`; the former is deprecated for the
  0.3 removal window.
- Normalize old pheromone trails with
  `normalize_legacy_pheromone_trail(...)`; callers must supply target, source,
  provenance, and trace identities because the migration helper invents none.
- Use `pheroos tck run --version v2` for expected-free adapter proof and retain
  v1 only as the frozen legacy regression generation.

- Draft ABI consumers using the old `PheromoneTrail(candidate_id, strength)` shape can keep using that compatibility path.
- New pheromone-aware consumers should prefer `subject_type` and `subject_id`.
- External runtimes should pass `collective_fallback_id(protocol)` as `fallback_candidate_id` when evaluating collective decisions for policies with empty `fallback_candidate`.
- Draft ABI consumers should move manifest driver payload assumptions from raw dict access to `DriverSpec` attributes.
- External runtimes should keep provider credentials outside manifests and use only opaque external references such as `config_ref`.
- External runtimes should validate manifests against `schemas/capability.schema.json` or the manifest loader before mapping `DriverSpec` declarations.
- External runtimes should treat conformance report `profile` as the applied compatibility profile version.
- External runtimes should use declared `DriverSpec.permissions` for driver exposure and must not substitute capability-level permissions.
- External runtimes invoking drivers through Kernel ABI should return provenance-bearing `DriverResult` objects.
- External runtimes should not expose driver or tool handles from not-ready runtime contexts.
- Hybrid consumers should call `verify_signal_input(...)` with governance
  authority and attach the returned `SignalVerification` to quorum, scout,
  recruitment, and inhibition records. Do not use `QuorumSignal.verified` as
  an authority path.
- Replace externally computed `LayerCoordinationState` inputs with
  `LayerProposal`, `LayerPerformanceSnapshot`, and `StrategyBias` inputs to
  `evaluate_hybrid_collective_step(...)`; consume the returned coordination
  state as output only.
- Record the `TraceEvent` objects returned in
  `HybridCollectiveStep.trace_events`; do not synthesize lifecycle events for
  steps that did not occur.
- Import manifest kind declarations from
  `pheroos.protocol.PheromoneKindProfile`. The governance name remains a
  type-identical compatibility export during the draft migration window.
- Validate persisted or generated manifests again before loading, replace all
  non-finite numbers, and run the manifest-selected profile. Hybrid consumers
  must pass `pheroos-hybrid-swarm-v1`.
- Use `replay_state_from_hybrid_step(previous_step)` for the next complete
  Hybrid step. Do not pass raw processed-id sets or a parallel trail snapshot.
- See `docs/protocol/hybrid-pheromone-v1-migration.md` for the concise Hybrid v1
  consumer migration sequence.
