# G3 / R1 coordination v2 pilot — 2026-09-12

The engineering and measurement gate passes. The candidate is not promoted:
it delivered fewer observations than simple dedup+TTL but incurred more total
logical operations and bytes. This pilot does not establish efficacy or
task-success noninferiority.

## Problem, hypothesis and mechanism

Repeated, stale and irrelevant observations consume interaction budget. The
hypothesis is that canonical source-claim deduplication, task-local relevance
and version-triggered reactivation reduce redundant interaction while retaining
task success. Candidate suppression is acknowledged only after actual delivery;
cap-deferred observations remain eligible. Four-tick TTL makes replay visible
within the finite horizon. Attention has no authority interface.

## Baselines and implementation

All eight arms use the same deterministic world, receiver, evaluator, cap,
control path and operation/byte meter. Controls are full relevant sharing,
simple origin dedup+TTL, origin/version dedup+TTL, and count-matched sparse
random sharing. Three component ablations remove deduplication, relevance or
version reactivation. The implementation and limitation contract are
[frozen by SHA-256](freeze.json); v1 code and results remain unchanged.

Source base: core/bench `b154472becea561ac1f5fc442a7ccf372ab154f8`. V2 files
were uncommitted at execution; their exact identity is the frozen source
closure, not that base commit alone. Config is `r1_coordination_config_v2`
from `r1-coordination-pilot-v2.json`; episode schema is
`r1_coordination_episode_v2`; paired measurements use the unchanged
`r_paired_world_mean_v1` instrument contract. Python was 3.12.3.

## Tests and experimental design

Eight independent pilot worlds (1000–1007), two per update case, crossed with
eight arms: **64/64 complete episodes**, zero invalid episodes, zero unknown
cost markers, and 454,440 known logical stage operations. Every completed task
failure remains in the data. All LLM/token counters are explicitly zero.

All **558 bench tests passed**, including **222 R1 tests** across historical
v1, v2 behavior and measurement exports. G1 passed **43 tests**, R0 passed
**117**, and the focused core boundary/provider-free suite passed **85**.
Toy and legacy swarm validation/conformance passed. The long full core suite
was interrupted with exit 130 and is not claimed as passing. Core source was
unchanged. Exact commands and accounting checks are in [validation](validation.json).

[Reproduction audit](audit.json) reproduced every episode exactly and verified
all seven paired exports against the unchanged R0 analyzer. Frozen hashes
remained unchanged. The only preexisting tracked file edited by this task was
the bench README; historical R1 v1 source/config/contract/tests/results were
also checked unchanged. No E1/E2/E3 threshold or evidence was edited.

## Results and negative findings

| Arm | Successes / 8 | Mean data deliveries | Mean logical operations | Mean accounted bytes |
| --- | ---: | ---: | ---: | ---: |
| Full relevant | 7 | 798.00 | 7,377.00 | 650,263.38 |
| Dedup+TTL | 7 | 108.25 | 5,527.75 | 327,623.38 |
| Source/version+TTL | 7 | 108.25 | 5,527.75 | 331,248.38 |
| Matched sparse random | 7 | 98.75 | 4,555.25 | 306,206.00 |
| Candidate | 7 | 98.75 | 6,356.50 | 393,127.38 |
| No dedup | 7 | 773.50 | 8,858.00 | 724,699.38 |
| No relevance | 7 | 395.00 | 12,256.00 | 810,533.13 |
| No reactivation | 7 | 96.00 | 6,346.75 | 388,266.38 |

Candidate versus simple dedup+TTL: **8.78% fewer deliveries**, **14.99% more
logical operations**, and **19.99% more accounted bytes**. All arms have the
same final successes in these worlds; paired quality intervals are flat and
reported `INSUFFICIENT_RESOLUTION`, not proof of equivalence.

Candidate and the two dedup baselines correct all eight update events within
the update tick. Removing version reactivation delays four source corrections
by 2–3 ticks; matched sparse random delays four by 2–7 ticks. Every correction
event is retained, including zero delays. None is missed before the horizon.
The candidate's extra stale-version check therefore reduces replay deliveries
but has no observed correction advantage over competent dedup baselines.

## Known confounds and what was not proven

These are short binary tasks with trusted provenance and versions, fixed local
subscriptions, reliable controls and synchronous delivery. Operation totals
weight unlike logical operations equally; byte totals measure serialized stage
traffic, not RAM/network/GPU throughput or monetary cost. Existing noisy answers
can make correction delay zero without proving a causal information effect.
This is neither a real-runtime integration test nor a robustness or production
readiness claim. There is no confirmatory sample, threshold or policy selection.

## Next gate

G3's deterministic engineering and measurement requirements are satisfied.
Retain simple baselines; no further candidate complexity is justified by this
pilot. Continue to G4 by auditing the existing frozen R2 negative experiment
against the master gate, adding missing capacity accounting as a separate
versioned reanalysis without treating it as new independent evidence.
