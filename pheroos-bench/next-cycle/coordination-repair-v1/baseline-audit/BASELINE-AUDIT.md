# Coordination repair baseline audit v1

This is a new read-only audit of historical inputs, not a model experiment or
an efficacy result. `baseline-audit.json` contains exact SHA-256/byte identities,
local branch/dirty state, selected publication-manifest checks and the next-cycle
requirement checklist. `run_audit.py` reproduces this audit without opening any
historical SQLite, WAL or SHM file. All historical inputs were rehashed unchanged.

The original working directories remain dirty on `main`: PheroOS
`b154472becea561ac1f5fc442a7ccf372ab154f8`, runtime
`e3ef1e8ed0812296601e4a901768af4a1068b5e0`. Relevant experimental source and raw
records match their published manifest identities at reviewed PR snapshots
`3604f5ce358ed6051c67e48906d240ac0b581f14` and
`c94a2efd13ace1ac424b5ccb1dc0f885b810f82c`. Current remote resolution and installed
package checks are part of the root audit; these local revisions are not claims
that current remote `main` contains the PRs.

## Confirmed historical findings

* **R1 coordination v2:** all 64 raw rows were read. Candidate and dedup+TTL each
  succeed in 7/8 worlds. Candidate mean deliveries decrease from 108.25 to 98.75
  (-8.77598%), while metered logical operations increase from 5527.75 to 6356.5
  (+14.99254%) and logical bytes from 327623.375 to 393127.375 (+19.99369%).
  Fewer messages did not establish a net efficiency advantage.
* **R2:** the supplied independent rules reconstruction reproduces all 480 raw
  episode result dictionaries, completion counts, p95 waits, retries and pressure
  ticks. Separately, 160 frozen-source replays match original trace hashes and
  reconstructed dispatches. All 80 candidate/FIFO dispatch pairs are identical.
  The 32 bottleneck evaluation worlds contain 438 pressure ticks and mean 59.46875
  extra pressure inspections. This mechanism does not change work selection here.
* **R4 replication:** all 264 raw episodes contain 7,134 received model dispatches,
  one abandoned pre-dispatch reservation, and 7,085 received evaluations. There
  are 6,268 rejected public actions (88.4686%). Their model calls consume
  2,970,028 of 3,402,842 known tokens (87.2808%). Prompt tokens total 3,030,343.
  The 52 budget and 52 deadline stops remain in the audit.

The authoritative tool receipt gives the following rejection breakdown:

| Primary stage | Actions | Model tokens |
| --- | ---: | ---: |
| Undeclared test/source target | 3,416 | 1,510,742 |
| Missing current inspection evidence | 1,345 | 734,511 |
| Action or `code_lines` schema | 1,342 | 633,551 |
| JSON parsing/format | 98 | 55,396 |
| Missing/stale citation metadata | 29 | 16,153 |
| Noninteger execution result | 24 | 13,884 |
| Unsupported public code statement | 14 | 5,791 |

No explicit public-test failure occurred in these raw feedback records. Public
rejection is therefore not synonymous with malformed JSON. Two received rejected
evaluations were not copied into their top-level record before execution stopped;
using only top-level `feedback` misses one schema and one target rejection.
Separately, 49 records have known model responses without evaluation and 53 have
no recorded response. These are retained, not relabeled as successful actions.

* Of 398 published valid inspections, 173 repeat the same episode-local origin
  identity. This is repeated inspection provenance, not independent support and
  not the denominator for every model or tool call.
* Across 84 fixed-call shared-history N comparisons, all 2,688 common model inputs
  and response signatures are identical. `same-input-pairs.json` identifies each
  pair. Source confirms agent labels are omitted from prompts and work is the
  predetermined `step % N` chain. These are valid expected-null instruments, not
  evidence of autonomous organization or intelligence scaling.
* Source versions change at step 16, leaving 16 final-version turns. Private
  N=8/16/32 gives each active agent at most 2/1/1 final-version opportunities,
  below three current inspections plus a submission. These evidence conditions
  are structurally unreachable under the historical private visibility rule.
* Mixed-model selection switches at step 28 regardless of outcome. Small-model
  tokens are 413,350 and medium-model tokens 65,612. Escalation is scheduled; no
  adaptive capability-routing claim follows.

## Consequences for the new implementation

Concrete legal targets and durable version-aware evidence retrieval address the
largest observed failure groups. Attention eviction, evidence retention and
bounded error feedback need separate state. Task ownership must change actual
work selection, and pure-read reuse must reduce executed inspections rather than
only reduce prompt copies. D0/D1/D2 diagnostics and public-tool reference solutions
should establish reachability before one small 2–4-agent collaboration campaign.

Every arm must share the corrected interface, runtime, tools, evidence facilities,
accounting and hidden evaluator. Candidate allocation/reuse needs explicit
ablations. Relevant/withheld/irrelevant sharing forks require full downstream
rollouts, independent current permissions, separate branch accounting and
unconditional objective outcomes. World-level and nested observations must remain
distinct. No confirmatory or Stable claim is authorized.

## Scope and limitations

Python 3.14.7 ran this provider-free audit. The supplied independent script was
read in full and executed with only its hardcoded output destination changed to
this isolated directory; its JSON result exactly matches the supplied JSON after
normal JSON key normalization. The original four supplied input files were not
changed. This audit adds raw-record checks beyond the supplied aggregate audit.

No inference, network, package installation, historical database inspection or
original full test suite was run. Selected source/raw files were checked against
publication manifests; this is not a repeat of the entire archive verification.
The R2 source replay is self-consistency evidence; the separately implemented
rules reconstruction supplies the independent comparison. Four historical tiny
task worlds do not establish broad task generalization. Historical INVALID,
negative and unresolved records remain unchanged.
