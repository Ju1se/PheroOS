# Governance Core

`pheroos.governance` defines the authority model for governed runtime decisions.

Governance owns:

- canonical targets
- signals
- authority levels
- evidence graph
- stop signals
- candidate sets
- quorum decisions
- recovery traces
- output contracts
- trace events
- deterministic collective decision steps

## Invariants

- Agents can propose signals.
- Governance authority is required to verify signals.
- Quorum can commit only declared candidates.
- Stop signals block target actions.
- Recovery follows declared triggers, roles, tags, tools, and failure behavior.
- Output authorization requires a committed candidate, evidence provenance, stop resolution, and publication permission.
- Pheromone is bounded collective memory, not evidence, quorum, permission, or output authority.
- Namespaced pheromone metadata does not score candidates by default.
