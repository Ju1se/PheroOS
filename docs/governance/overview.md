# Governance Core

`pheroos.governance` defines the authority model for governed runtime decisions.

Governance decides what is allowed. Agents may propose facts, signals, reports,
and candidates; governance authority is required to verify and commit.

## Owned Surface

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
- scout reports
- recruitment signals
- inhibition signals
- pheromone trails and policies

## Invariants

- Agents can propose signals.
- Governance authority is required to verify signals.
- Quorum can commit only declared candidates.
- Stop signals block target actions.
- Recovery follows declared triggers, roles, tags, tools, and failure behavior.
- Output authorization requires a committed candidate, evidence provenance, stop resolution, and publication permission.
- Pheromone is bounded collective memory, not evidence, quorum, permission, or output authority.
- Namespaced pheromone metadata does not score candidates by default.

## Swarm Semantics

Bee-swarm behavior is represented by independent scout reports, recruitment
signals, inhibition signals, consensus thresholds, and safe fallback.

Ant-colony behavior is represented by traceable pheromone memory, evaporation,
bounded contribution, source diversity, and deterministic scoring.

These concepts are protocol semantics, not a swarm runtime.

## Boundary

Governance must not call model providers, tools, servers, databases, queues, or
external runtimes.
