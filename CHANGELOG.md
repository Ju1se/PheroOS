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

### Migration Notes

- Draft ABI consumers using the old `PheromoneTrail(candidate_id, strength)` shape can keep using that compatibility path.
- New pheromone-aware consumers should prefer `subject_type` and `subject_id`.
- External runtimes should pass `collective_fallback_id(protocol)` as `fallback_candidate_id` when evaluating collective decisions for policies with empty `fallback_candidate`.
- Draft ABI consumers should move manifest driver payload assumptions from raw dict access to `DriverSpec` attributes.
- External runtimes should keep provider credentials outside manifests and use only opaque external references such as `config_ref`.
- External runtimes should validate manifests against `schemas/capability.schema.json` or the manifest loader before mapping `DriverSpec` declarations.
- External runtimes should treat conformance report `profile` as the applied compatibility profile version.
- External runtimes should use declared `DriverSpec.permissions` for driver exposure and must not substitute capability-level permissions.
