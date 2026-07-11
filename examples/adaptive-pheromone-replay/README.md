# Adaptive Pheromone Replay Example

This provider-free example demonstrates the external adaptive runtime contract
for pheromone updates.

The replay script behaves like an outside learner, but it does not implement
machine learning, reinforcement learning, storage, scheduling, networking, or
provider integration. It only reads a declared hybrid protocol, derives
deterministic outcome labels from a small trace-like replay fixture, emits ABI
records, and submits those records back through public governance functions.

The important boundary is:

```text
external replay proposes:
  - PheromoneFeedback
  - LayerProposal
  - PolicyAdjustmentProposal

protocol-core governs:
  - candidate declaration checks
  - provenance and trace checks
  - pheromone clipping and reinforcement
  - layer coordination
  - policy adjustment bounds
  - final collective decision semantics
```

The script submits the fixture through `evaluate_hybrid_collective_step`, derives
a governance-issued `HybridReplayState` with
`replay_state_from_hybrid_step(...)`, then runs a second complete step with the
same feedback and adjustment identities to prove that a second application is
a traced, validated no-op. It never supplies raw processed-id sets or a parallel
trail snapshot. Its authority result is
derived from the declared-candidate decision and actual commit/fallback trace,
not from a hard-coded assertion.

Run it from the repository root:

```bash
python examples/adaptive-pheromone-replay/replay.py
```

The JSON output is intentionally small and deterministic so it can be used by
tests and conformance-oriented documentation.
