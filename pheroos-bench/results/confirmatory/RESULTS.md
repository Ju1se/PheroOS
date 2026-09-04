# PheroOS field E1 confirmatory result

This record belongs to `experiment.json` and the frozen harness tag
`e1-frozen-2026-09-01-prediction`. It was run after the one permitted pilot had been
discarded. The pilot never entered this verdict.

Run facts:

- 7 densities (`0.05` through `0.35`), 40 paired seeds (`1000` through `1039`), 5 arms, 500 steps: 1,400 raw records.
- The PheroOS dependency was imported and checked at version `0.1.0`, commit `4f292de799b01e57bdbb87e915191f310d219579`.
- All wire events use `canonical-json-v1`; field reads, deposits, and failed writes are included in `bytes` and `messages`.
- Exploration is frozen at `epsilon=0.0` for every arm; the earlier field-only exploration branch is not part of this result.
- The primary endpoint is the paired path-regret difference `stateless_local_aggregate - field_local`. The quality, communication, and recovery floors are secondary gates.

Verdict: **`FAIL_RENAME_REQUIRED`**. No density passed the complete gate, so no adjacent pair passed. With the arm-symmetric epsilon fix, field shock recovery is measurable, and field/centralized communication is roughly 1.96–2.73× rather than an artifact of the exploration tax. The field arm is still worse than the same-agent stateless ablation on the primary endpoint at every density (all bootstrap lower bounds are negative), and the communication gate fails at every density. The absolute field-regret floor is met, but that cannot rescue the failed primary and communication gates.

The exact machine-readable evidence is in `raw.ndjson`, `summary.csv`, `verdict.json`, and `metadata.json`; `density-curve.svg` is a static view of the two principal secondary axes. This result retires the field/swarm claim for this implementation. It is a negative result for this candidate, not a claim that all stigmergic designs are impossible. The repository is now positioned as a governed authority/commit protocol benchmark.
