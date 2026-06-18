# Conformance Suite

`pheroos.conformance` owns protocol-core compatibility checks.

Checks include:

- manifest schema
- domain-neutral public core
- candidate declaration
- quorum policy
- collective policy
- safe collective fallback
- pheromone policy
- pheromone behavior
- recovery policy
- output contract
- trace contract
- swarm trace contract
- driver contract
- extension contract
- kernel import boundary

The CLI is thin and delegates to `pheroos.conformance`.

Pheromone behavior checks are no-op passes when pheromone is not enabled and active deterministic ABI checks when a manifest declares pheromone-enabled swarm behavior.
