# E2 Couzin result — audited rerun

The preregistration is frozen at `e2-frozen-2026-09-03` (`38b5473`). The single
control correction is frozen at `e2-gossip-fixed-2026-09-03` (`2771003`). The
pre-run prediction remains at `prediction.md`.

## Execution

- Admission was revalidated after the control-only fix: all 12 cells passed.
- The fixed-control treatment was run once with 12 cells and 40 paired seeds
  per cell (`solitary`, `naive_gossip`, and `couzin`).
- Config and source fingerprints matched between the revalidated admission and
  treatment. No gate, codec, seed, or success criterion changed.

## Verdict

`FAIL` under the preregistered primary gate. No informed-fraction cell passed,
so there are no adjacent passing pairs at any N and the scale prediction is not
applicable.

The primary endpoint is the paired median of
`global_regret(couzin) - global_regret(naive_gossip)`:

| N | p=.02 | p=.05 | p=.10 | p=.20 |
|---:|---:|---:|---:|---:|
| 100 | +0.00348 (CI hi +0.00606) | +0.00211 (+0.00604) | +0.00904 (+0.02143) | +0.03552 (+0.04924) |
| 400 | +0.00191 (+0.00663) | +0.00340 (+0.01027) | +0.01094 (+0.02301) | +0.03816 (+0.05743) |
| 1600 | +0.00166 (+0.00714) | +0.00262 (+0.01002) | +0.01104 (+0.02080) | +0.04168 (+0.05686) |

Positive values favor gossip; every CI upper bound is non-negative.

Raw records, summaries, metadata, and the final machine-readable verdict are
in the sibling files under `admission/` and `treatment/`.

## Audit of the superseded first treatment

The first `PASS` verdict is invalid. The original `naive_gossip` control
unconditionally copied one random neighbor's route. With the random ID-regular
topology, this became a voter-model consensus process in position space: it
collapsed to a single consensus position in all seeds and never reached `r*`,
including agents that began adjacent to it. The secondary Couzin-versus-
solitary endpoint also showed a near-zero effect.

The naive_gossip control collapses to a single consensus position in all seeds
and never reaches r*, including agents that began adjacent to it. The PASS
verdict is produced by control failure, not by treatment efficacy. The
secondary endpoint (couzin vs solitary) shows near-zero effect. This result
does not support restoring swarm-native positioning.

The corrected control now adopts a neighbor route only when its static route
cost is strictly lower than the agent's own local best. The superseded raw
result remains recoverable in git commit `2541c89`; the final raw records,
summary, metadata, and machine-readable verdict are under `treatment/`.
