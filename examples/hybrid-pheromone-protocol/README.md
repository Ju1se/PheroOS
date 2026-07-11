# Hybrid Pheromone Protocol Example

This example is provider-free, network-free, deterministic, and domain-neutral.

Run the complete reference governance path from the repository root:

```bash
python examples/hybrid-pheromone-protocol/run.py
```

The script submits verified scout reports, topology, deposits, outcome
feedback, learned and metacognitive proposals, and a bounded evolutionary
run-scoped adjustment through
`evaluate_hybrid_collective_step`, then authorizes output through all four
output gates. Its trace contains only lifecycle actions that actually occurred.

It demonstrates the hybrid pheromone ABI:

- route-bound pheromone subjects that diffuse into declared candidate subjects
- feedback reinforcement with provenance and trace lineage
- nonlinear response shaping with saturation and competitive normalization
- layer proposals that may influence scores but cannot commit
- bounded policy-adjustment proposals
- declared safe-fallback authority (the successful example commits its
  consensus candidate; fallback paths are covered by conformance and tests)
- output authorization only after the governed output contract passes

The external hybrid runtime is intentionally absent. Protocol-core owns only the
ABI contracts, deterministic governance reference behavior, trace event names,
conformance checks, and this small example.
