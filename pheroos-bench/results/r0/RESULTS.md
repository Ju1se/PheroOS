# R0 instrument and G1 accounting acceptance

The new entry is `r_paired_world_mean_v1`, instrument-only. E3's method, data
contract, gates and prior results were not edited. All records explicitly have
`counts_toward_verdict=false`.

Current result: [instrument-checks-v2.json](instrument-checks-v2.json).

| Synthetic case | Mean quality difference | 95% interval | Interpretation |
| --- | --- | --- | --- |
| 30 wins, 5 losses, 65 ties | 0.25 | [0.15, 0.35] | Known positive signal recovered |
| Reversed positive control | -0.25 | [-0.35, -0.15] | Known negative signal recovered |
| Identical arms | 0 | [0, 0] | Valid data; no measured advantage |
| Two additional successes in 60 worlds × 3 repetitions | 0.011111… | [0, 0.027777…] | 60 independent worlds, not 180 |
| Equal arm means across cells | 0 | [0, 0] | Valid flat cells; insufficient interval resolution |

Single-cell and constant-difference inputs are legal; zero-width intervals are
reported without claiming efficacy. Missing/duplicate episodes, invalid typed
values and unknown episode costs produce `INVALID_ABORT`. Failed, timed-out,
rejected and cancelled episodes retain their quality and actual cost. Known
budget overruns remain observable violations rather than discarded data.

## Actual G1 snapshot reconciliation

The capture tool used the independently installed mock runtime at
`b3c0d4977c466c02a200d4fe63857682de53ddfd`. Runtime module digests and raw
snapshot digests are in [provenance.json](runtime/provenance.json). These are
consistency checks, not authenticity or authority proofs.

| Snapshot | Actual units | Reserved / unknown units | Reconciliation |
| --- | --- | --- | --- |
| [Completed](runtime/completed.json) | 26 | 0 / 0 | VALID, KNOWN |
| [Cancelled after dispatch](runtime/cancelled_unknown.json) | 0 | 1 / 1 | VALID, UNRESOLVED |
| [Late tool receipt](runtime/cancelled_late_receipt.json) | 1 | 0 / 0 | VALID, KNOWN; run remains cancelled |

The completed run has 5,789 payload bytes and 57,460 serialized event bytes.
These are the G1 accounting counters, not total physical storage/network I/O.
Calls, events and reported aggregates were reconciled independently. Historical
overspending is rejected even when later cancellation makes final totals small.

## Validation and debugging record

Full bench suite: **203 passed in 6.26 seconds**, including separate wheel and
sdist installations with R0 execution outside the source directory. Changed
Python files pass Ruff. Existing unrelated lint warnings in E1/E2 files were
not changed. Core code and the external runtime were not modified this round.

[instrument-checks.json](instrument-checks.json) preserves the earlier failed
self-check: the sparse mean differed from the independently computed rational
by one floating-point rounding unit. The corrected numerical comparison uses
absolute tolerance 1e-15; this is not an experimental effect threshold. Earlier
installation testing also found that unpadded world IDs reordered the synthetic
sample under lexical sorting; the fixture now uses fixed-width IDs to reproduce
the independent diagnostic's specified ordering. No E1/E2/E3 gate changed.

G1's real-process crash tests remain the execution-boundary evidence; this
round adds an independent ledger reader and statistical validation. Dollar
pricing, live model version drift, full power analysis and R1–R5 performance
experiments remain pending.

Reproduce the stored-snapshot checks into a new file:

```bash
python -m pheroos_bench.r0_self_check --output /tmp/r0-new-checks.json \
  --runtime-snapshot results/r0/runtime/completed.json \
  --runtime-snapshot results/r0/runtime/cancelled_unknown.json \
  --runtime-snapshot results/r0/runtime/cancelled_late_receipt.json
```
