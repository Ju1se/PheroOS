# Historical Hybrid Pheromone v1 Migration

This note records the former Hybrid Pheromone draft ABI. It is retained for
historical reference only: `pheroos-hybrid-swarm-v1` is no longer a supported
public conformance profile, and the implementation is private experimental
attention code. Baseline manifests remain on `pheroos-core-v1`; attention does
not create authority.

## Required consumer changes

1. Validate manifests before typed mapping. Remove unknown non-namespaced
   fields, invalid primitive or collection shapes, and every `NaN`, `Infinity`,
   or `-Infinity` value. Direct Python ABI records must also contain finite,
   correctly bounded numbers.
2. Obtain a governance-issued `SignalVerification` with
   `verify_signal_input(...)` and attach it to quorum, scout, recruitment, and
   inhibition records. Verification is bound to the target, source, subject,
   verifier authority, provenance, and trace lineage. A producer-controlled
   `verified` boolean is not authority, and a directly constructed
   `SignalVerification` is not governance-issued.
3. Submit complete Hybrid scout identities: non-empty `scout_id`,
   `evidence_id`, provenance, active target, trace event id, and matching
   verification. Do the equivalent source, target, provenance, trace, and
   verification binding for recruitment and inhibition records.
4. Replace caller-computed `LayerCoordinationState` score input with
   `LayerProposal`, `LayerPerformanceSnapshot`, and `StrategyBias` records.
   Call `evaluate_hybrid_collective_step(...)` and consume its
   `layer_coordination` field as governance output.
5. Use the complete step result as the reference lineage. Persist
   `HybridCollectiveStep.trace_events` and its lifecycle, replay, and budget
   outputs; do not fabricate lifecycle events that were not returned.
   Continue with `replay_state_from_hybrid_step(previous_step)` and pass that
   governance-issued `HybridReplayState` to the next complete step. Raw
   `processed_pheromone_event_ids`, `processed_feedback_ids`, and
   `processed_adjustment_ids` no longer carry replay authority, and
   `existing_trails` cannot override issued replay memory.
   Processed ids are bound to disjoint immutable deposit, diffusion, feedback,
   and adjustment payload receipts: the same id with a changed payload or a
   different lifecycle owner is rejected rather than treated as an idempotent
   replay. Persist the complete `replay_payload` emitted for `replay_ignored`
   events. When validating an actual replay trace, pass the governance-issued
   prior `HybridReplayState`; matching hashes alone are not replay authority.
   Persist `causal_payload` and `causal_fingerprint` on every rejected
   `pheromone_clip`. Recompute or verify the versioned receipt with
   `pheroos.trace.pheromone_clip_payload_fingerprint(...)`; do not treat the
   digest as evidence or authority. Rejected feedback clips now also carry
   `strength_delta`, and their request must equal
   `abs(strength_delta or reward)`.
6. After the step, authorize output separately. When stop resolution is
   required, provide at least one `StopResolution` whose target equals
   `decision.target` and ensure none of that target's resolutions is blocked,
   together with committed decision, provenance-bearing evidence, and
   publication permission. Pass the active protocol-derived `CandidateSet` so
   the commit gate can verify candidate declaration and governance decision
   issuance. All four output gates are mandatory; manifests and
   `OutputContract` records may not disable them.
7. Historical callers imported the manifest declaration from
   `pheroos.protocol.PheromoneKindProfile`; current callers must treat the
   implementation as private and must not rely on a root export.
8. Do not require a swarm or Hybrid Pheromone manifest profile. Use the current
   baseline or Commit profile and treat attention state as advisory.
9. Treat the two exploration declarations as distinct. The bounded
   `pheromone_exploration_floor` is a nonlinear-response baseline;
   `exploration_floor` is additional novelty pressure applied only when
   `exploration_enabled` is true. Both are constrained to `[0, 1]` and are no
   longer collapsed into one alias value.
10. Novelty trails now require `exploration_enabled=true` to score, and their
    declared novelty decay is applied inside the complete Hybrid lifecycle.
11. `pheromone_score` lineage now includes canonical active-trail records, and
    decision lineage includes recruitment, inhibition, accepted adjustment,
    pheromone, scout, and layer sources. Persist the expanded Draft Trace ABI.
12. Run-scoped global evaporation and response-model adjustments override
    per-kind values for that run so an accepted adjustment has an effective
    semantic result; the source manifest remains immutable.
13. Give every namespaced extension kind that is intended to score its own
    non-empty `scored_subject_types`. Extension profiles no longer inherit the
    policy-wide list merely because a profile object exists.
14. Remove `evidence` from all policy-wide and per-kind scored-subject lists.
    Evidence pheromone remains valid reference-memory metadata but cannot
    contribute to candidate scoring.
15. Treat validated protocol, governance, Kernel, Driver, and trace records as
    immutable snapshots. Do not mutate candidate sets, evidence graphs,
    permissions, exposures, policy bounds, overlays, or nested payloads after
    submitting them across a trust boundary.
16. Keep every layer-weight adjustment envelope inside the corresponding
    declared `layer_weight_bounds`, and keep the cautionary override-threshold
    envelope at or below `pheromone_max_strength`. Direct governance calls now
    enforce these cross-field bounds even when no manifest loader was involved.
17. When reading a legacy two-field trail, call
    `normalize_legacy_pheromone_trail(...)` before deposit or scoring and supply
    the explicit target, source, provenance, and Trace identity. The helper
    resolves the candidate/route/tool subject, rejects conflicts and ambiguity,
    and never invents evidence or authority.
18. Treat `pheroos-pheromone-kind-profile-map-v1` as the single runtime kind
    policy. `canonical_pheromone_kind_profiles(...)` applies the conflict rule:
    an explicitly declared per-kind profile wins in full; legacy scalar weights
    synthesize only missing built-in kinds. Extension kinds are never inferred.

## Compatibility retained

- `PheromoneTrail(candidate_id, strength)` remains a supported Draft
  constructor during the migration window, but new code should normalize it
  immediately. Removal requires a new profile/schema and TCK generation.
- Legacy scalar weight fields remain readable during the same window. Their
  future removal also requires a new profile/schema; v1 double-write behavior
  will not change in place.
- Toy, e2e, baseline quorum, and basic swarm protocols are not forced to become
  Hybrid protocols.
- Learned, evolutionary, reactive, and metacognitive runtimes remain external;
  they submit proposal records rather than authority state.

The full integration contract is in
[runtime-integration.md](runtime-integration.md). ABI invariants and profile
requirements are defined in [../../SPEC.md](../../SPEC.md).
