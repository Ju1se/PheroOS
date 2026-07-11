# Changelog

All notable changes to PheroOS protocol-core should be documented here.

The project is currently pre-stable. Until the first stable ABI release, entries should call out schema, conformance, and migration impact explicitly.

## Unreleased

### Added

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

- Historical goal, execution-plan, and migration-inventory Markdown documents from the public source tree.
- The standalone protocol proposal stub after merging its requirements into `CONTRIBUTING.md`.
- The standalone security overview after merging protocol security scope into `SECURITY.md`.
- Unused protocol composition helper, unused protocol error shim, unused driver result re-export, and unused stop-signal manifest parser.

### Compatibility

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
