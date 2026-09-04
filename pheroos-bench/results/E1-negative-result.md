# E1 negative result: governed authority/commit protocol benchmark

## Final status

E1 is closed with `FAIL_RENAME_REQUIRED`. The field candidate did not pass at
any density, so the pre-registered requirement for two adjacent passing points
was not met. No E2 task or new mechanism is opened by this report.

The public positioning of `pheroos-bench` is now governed authority and commit
protocol experimentation. The result does not support a claim of emergent,
swarm, or general stigmergic intelligence.

## Pre-registration and frozen execution

- Configuration: [`experiment.json`](../experiment.json)
- Pre-run prediction: [`prediction.md`](prediction.md)
- Freeze tag before the confirmatory run: `e1-frozen-2026-09-01-prediction`
- PheroOS dependency: version `0.1.0`, commit `4f292de799b01e57bdbb87e915191f310d219579`
- Density sweep: `0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35`
- Paired seeds: `1000..1039` (40 per arm/density)
- Arms: random local, greedy local, stateless local aggregate, centralized online, and field local
- Records: 1,400 raw rows and 35 arm/density summary rows
- Exploration: `policy=none`, `epsilon=0.0`, `applies_to=all_arms`
- Pilot: one permitted pilot, explicitly void and excluded from the verdict

The final machine-readable evidence is [`results/confirmatory/verdict.json`](confirmatory/verdict.json), [`results/confirmatory/summary.csv`](confirmatory/summary.csv), and [`results/confirmatory/raw.ndjson`](confirmatory/raw.ndjson). The density plot is [`results/confirmatory/density-curve.svg`](confirmatory/density-curve.svg).

## Gate outcomes

| Gate | Frozen rule | E1 outcome |
| --- | --- | --- |
| Primary path regret vs stateless ablation | Paired bootstrap lower bound `> 0` | FAIL at all densities; lower bounds `-0.1204` to `-0.0333` |
| Quality additive | Field regret ≤ centralized regret + `0.05` | PASS at 0.10, 0.15, 0.20, 0.35; FAIL at 0.05, 0.25, 0.30 |
| Quality absolute | Field regret ≤ `0.15` | PASS at all densities |
| Communication | Field/centralized bytes ≤ `0.70` | FAIL at all densities; median `1.96–2.73×` |
| Recovery | Field/centralized recovery ratio ≤ `0.75` | Measurable and PASS at all densities |
| Overall | Two adjacent density points passing all gates | FAIL; zero passing points |

The primary endpoint remains negative after the arm-symmetric exploration fix.
The communication gate remains structurally unreachable in this topology, and
it is retained unchanged as an E1 result rather than retrofitted after seeing
the data.

## Instrument defects discovered

1. **Arm-asymmetric exploration.** The first run charged only `field_local` an
   8% epsilon branch. That was not part of the hypothesis and made both regret
   and shock recovery incomparable. The branch was removed; the final config
   freezes `epsilon=0.0` for all arms, and the final run was performed under the
   new tag above.
2. **Communication gate/topology mismatch.** Centralized sends one observation
   and one route command per active agent, while local arms serialize a 16-route
   visible window. The resulting gate measures where argmin is executed more
   than the cost of persistent stigmergic memory. The `0.70` gate was not
   changed for E1; this design error is carried into the next pre-registration.
3. **Insufficient coordination space.** Regret is against each agent's own
   16-route local optimum and is averaged over the final 50 steps, by which
   time local agents have observed the useful routes. The task therefore offers
   little information that another agent can contribute. The deterministic
   first-agent-quarter fault is also correlated with route origins and removes
   agents that see the first cheap routes; it is symmetric across arms but
   confounds the interpretation of the fault window.

## Decision

E1 is a valid negative result for this candidate and a measurement of the
instrument's limits. The field/swarm marketing claim is retired. No new task,
mechanism, communication redesign, or harness platform work is started from
this result.
