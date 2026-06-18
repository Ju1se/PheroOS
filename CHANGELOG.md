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
- CLI schema export tests for protocol, kernel, driver, and trace surfaces.
- Stigmergic Memory ABI draft for swarm-native pheromone behavior.
- Uniform pheromone subject model with candidate, route, tool, evidence, and agent subjects.
- Positive, negative, cautionary, novelty, and stale pheromone semantics.
- Pheromone provenance, trace binding, source caps, deposit caps, source diversity, TTL expiry, and deterministic decay models.
- Pheromone trace events for deposit, evaporate, score, clip, expire, and inhibit.
- `pheromone_behavior` conformance check for runtime pheromone boundaries.

### Changed

- Swarm protocol example now declares bounded, traceable, evidence-bound pheromone policy fields.
- Conformance now covers pheromone behavior boundaries in addition to pheromone policy shape.
- GitHub Actions validation is expected to cover baseline, e2e, and swarm protocol conformance.

### Compatibility

- Baseline toy and e2e protocols remain compatible without declaring swarm behavior.
- Swarm-specific validation and conformance apply only when a manifest declares swarm collective behavior.
- Pheromone is not evidence, quorum, permission, or output authority.

### Migration Notes

- Draft ABI consumers using the old `PheromoneTrail(candidate_id, strength)` shape can keep using that compatibility path.
- New pheromone-aware consumers should prefer `subject_type` and `subject_id`.
- External runtimes should pass `collective_fallback_id(protocol)` as `fallback_candidate_id` when evaluating collective decisions for policies with empty `fallback_candidate`.
