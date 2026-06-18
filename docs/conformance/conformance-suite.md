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
- kernel import boundary

Run:

```bash
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
pheroos validate examples/swarm-protocol/capability.json
pheroos conformance examples/swarm-protocol
```

The CLI is thin and delegates to `pheroos.conformance`.

Pheromone behavior checks are no-op passes when pheromone is not enabled and active deterministic ABI checks when a manifest declares pheromone-enabled swarm behavior.
