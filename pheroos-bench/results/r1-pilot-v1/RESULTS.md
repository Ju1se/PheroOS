# R1: frozen finite signal experiment, 2026-09-12

The candidate did **not improve on the competent source/version + TTL baseline**.
Both achieved 32/32 world successes on the independent evaluation split and
delivered the same data messages, while the candidate used **6.14% more accounted
bytes**. These results do not support making the candidate a default strategy.

This completes one bounded, provider-free R1 mechanism experiment. It is a
descriptive frozen evaluation, not a confirmatory noninferiority result or a
claim about real LLM swarms. No model, CUDA workload, network call, paid API,
core ABI change, or runtime default change was used.

## Evaluation results

32 independent paired worlds, eight each with no update, source-version update,
task-constraint update, and both updates. Each world has eight agents and five
arms with the same observations, task relevance, 16 ticks and data-delivery cap.
Values below include every scheduled episode, including wrong answers.

| Arm | World success | Mean data messages | Mean total accounted bytes | Missed corrections / 32 |
|---|---:|---:|---:|---:|
| Full relevant sharing | 32/32 | 798 | 613,892.59 | 0 |
| Matched sparse random | 5/32 | 30 | 260,666.84 | 25 |
| Source/version + TTL | 32/32 | 30 | 297,693.03 | 0 |
| Candidate | 32/32 | 30 | 315,959.72 | 0 |
| No-reactivation ablation | 8/32 | 24 | 296,713.47 | 32 |

Candidate minus strong baseline, averaged over paired worlds: success difference
0; byte difference +18,266.69. Candidate minus full sharing: success difference
0; byte difference −297,932.88. Full sharing delivered 768 duplicate
recipient/origin pairs per world on average; candidate and strong baseline
delivered none. Every receiver retained at most three independent source groups.

Candidate, strong baseline and full sharing corrected all 32 evaluated changes
within the tick containing the new evidence. This synchronous finite task does
not establish a recovery-latency advantage. Sparse random corrected seven
changes, with four total ticks of observed delay, and missed 25; missed changes
are retained as null delays, not removed from success or costs.

The no-update negative stratum gives 8/8 successes for candidate, strong baseline
and ablation. The ablation fails all 24 update worlds, showing that versions
must reopen suppression. The strong baseline already implements that rule;
this ablation does not justify a more complex candidate.

Pilot results remain separate: eight paired worlds, with 8/8 successes for
candidate, strong baseline and full sharing, 2/8 for sparse random and ablation.
Pilot outputs did not trigger any parameter or code changes.

## Evidence and validation

- [Frozen source/config/environment](freeze.json): source, config, invariant tests
  and data contract hashed before any pilot/evaluation episode.
- [All 200 episode records](episodes.jsonl): 40 pilot and 160 evaluation rows;
  zero measurement errors; each result includes all five byte categories,
  operations, messages, final answers, independent support and correction delays.
- [Paired and stratified summaries](summary.json): no superiority gate, confidence
  claim, or best-arm selection; frozen hashes remained unchanged.
- [Validation](validation.json): 123 tests passed, including 18 R1 invariants and
  the relevant R0/E3 statistics/measurement regression tests.
- [Independent reproduction audit](audit-v2.json): all 200 episodes reproduce
  exactly after JSON serialization; complete expected record set, matching
  random quotas, reliable controls, source support bounds and zero token calls.

The first [audit](audit.json) compared live Python dictionaries with JSON-loaded
records and reported a mismatch because JSON converts integer task-map keys to
strings. It is retained. The corrected audit normalizes through JSON before
comparison. No experiment code, config, raw episode, or summary was modified.

Run from `pheroos-bench` with a fresh output directory:

```bash
PYTHONPATH=src /tmp/pheroos-wsl2-bench-env/bin/python -m pheroos_bench.r1_signals \
  --config r1-pilot-v1.json --output results/r1-reproduction-new
```

## Limits and next decision

The [data contract](../../R1-data-contract.md) fixes a finite binary task with
trusted provenance, source accuracy 0.9, reliable transport, fixed subscriptions
and one suppression window. Accounted bytes are serialized logical stage costs,
not physical network/RAM traffic, money, wall time or GPU throughput. All arms
scan relevance; candidate state overhead is included. Evidence generation and
external scoring remain outside policy cost, and policy interfaces cannot read
truth. Integer ticks and immediate complete source updates limit delay inference.

The result supports retaining the simple version-aware baseline for this task.
It neither proves narrow noninferiority beyond these 32 evaluation worlds nor
finishes a powered confirmatory study. Any new TTL, transport-loss, hidden-source,
or richer-task experiment requires a new frozen version and independent seeds;
this evidence directory must remain unchanged.
