# Model–interface v1: completed development diagnostic

The authorized 64-cell local diagnostic completed once with CLI exit **0** and
**64/64 VALID_KNOWN** records. Direct answer JSON produced six accepted, correct
answers; the other three arms produced none. Increasing the old envelope's
output allowance from 256 to 1,024 increased token use by **60.19%** without an
accepted submission. These observations do not admit collaboration or reverse
the preceding `COMPLETE_NOT_ADMITTED` result.

## Problem and hypothesis

The prior actionability campaign distinguished an operating execution/accounting
path from weak action and answer reliability. This diagnostic asks whether
reducing output responsibilities or increasing output allowance helps the same
3B model on the same already observed development worlds. It does not expand N,
change tasks or evaluate a new coordination policy.

## Mechanism and baselines

All four arms receive the same complete current evidence through charged tools,
the same local model and sampling, the same runtime/accounting, and the same
public checker and hidden objective. N=1; each cell has one response opportunity.

- `direct_json_256`: answer object only; runtime wraps submit and binds actual
  verified current receipt citations, without calculating or repairing answers.
- `compact_action_256`: compact question/evidence view, full action and citations.
- `envelope_256`: the historical D0 prompt and full action contract.
- `envelope_1024`: byte-identical envelope prompt, same new adapter, larger output allowance.

## Implementation and identities

Executed PheroOS source: **`4ea5208ae5d7d6cd8c847f89e51f44a914143c8d`**
(implementation `232c01d3a78f382cda73ccdc2593127a1cce6c8d`). Runtime:
**`2222d59bb05785528e4301dc14d164d538408ac6`**. This results publication adds
evidence only; those sources, prepared artifacts and all prior results remain
unchanged. The preparation report remains a historical pre-execution snapshot.

Config `model_interface_local_diagnostic_v1`, canonical SHA-256:
`ed833e52d72e5a042fc56f0616c9ced9c52fe534302cfedc630da3445a3c1a8e`.
Contracts: `model_interface_episode_v1`, `model_interface_descriptive_v1`,
`model_interface_cli_v1`. Independent export:
`model_interface_independent_descriptive_export_v1`. No R0 method changed.

Accepted packages: core `0.1.0`, runtime `0.1.0.dev4`, bench `0.1.1.dev5`.
All **685** fixed installed wheel members matched before and after collection
(installer-rewritten `RECORD` excluded). Runtime wheel SHA-256:
`0d4e3d58c8fc23bae7870376df9a81c2032a00ff5523b609f1eb5cfb27170537`;
bench wheel: `eaf9ad0c637152c6c9f4b12f708ca76de40881096d86f6a984ed55134e4285fc`.

Model: `Qwen/Qwen2.5-Coder-3B-Instruct`, revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5`; manifest SHA-256
`cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777`.
Python 3.12.3, PyTorch 2.11.0+cu128, Transformers 4.57.3, CUDA 12.8,
RTX 5070 Laptop GPU (8,151 MiB), driver 616.92, WSL kernel
6.18.33.2-microsoft-standard-WSL2. The existing environment and local files were
used; no model download, remote model or paid API was invoked.

## Tests and execution gate

The exact authorized source head completed **86 successful CI checks** with one
expected `provenance` skip (that job only runs on a trusted main push), zero
failures, before dispatch. Both old installed consumers and the new consumer
passed. Runtime has no standalone CI workflow; the exact accepted runtime wheel
is pinned in the new consumer, with retained installed wheel/sdist acceptance.

The unchanged preparation evidence records full bench **1,385 + 12 subtests**,
installed consumer **149**, and runtime wheel/sdist each **206 + 12 subtests**,
including G1 and the four R0 suites. These local suites were not relabeled as
new data-publication test runs. New audit helper counterexamples pass **10/10**.

Independent post-run audit: **4,922 checks, zero findings**. It recomputes public
acceptance and objective answers from public task inputs, checks every retained
Session/coordination snapshot against SQLite, generated token counts, prompt-ID
hashes against frozen tokenizer preflight, receipts, source identity, complete
grid, prior liabilities and summary arithmetic. It does not reimplement
Governance proof semantics, replay inference or calibrate hardware timing.

A second audit using the published data copy and wheels extracted into a new
directory also passes 4,922 checks. Reproduced CSVs are byte-identical. This is
portability verification of the same data, not additional experimental evidence.

## Experimental design

Eight previously observed development worlds × two seed bases × four arms =
64 execution cells, **eight worlds**, not 64 independent tasks. Two repeats are
averaged within each world. Counterbalanced order, prompts, task versions,
sampling (temperature 0.7, top-p 0.9, top-k 50), scoring and the 2,048-token
context are unchanged from the approved proposal. The complete grid is retained.

The one additional campaign was explicitly authorized. Its cap was 64 model
intent slots / 131,072 input-plus-output tokens. Ordinary invalid model answers
continued through the grid; configuration drift, permission failures, unknown
accounting or infrastructure failure would stop collection. No retry occurred.
There is no capability threshold or collaboration entry in this diagnostic.

## Results

| Arm | Public accepted | Correct | Output cap hits | Input tokens | Output tokens | Total tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct_json_256 | 6/16 | 6/16 | 0/16 | 2,832 | 264 | 3,096 |
| compact_action_256 | 0/16 | 0/16 | 0/16 | 3,600 | 842 | 4,442 |
| envelope_256 | 0/16 | 0/16 | 16/16 | 9,326 | 4,096 | 13,422 |
| envelope_1024 | 0/16 | 0/16 | 4/16 | 9,326 | 12,175 | 21,501 |

Each arm uses 16 model calls, 52 tool calls, 532 control operations and 600
logical call units. Totals: **64 model calls**, **208 tools = 144 preparation
inspections + 64 validations**, **2,128 control operations**, **2,400 call units**,
and **42,461 tokens = 25,084 input + 17,377 output**. All usage is known; no
unstarted, INVALID_ABORT or unresolved records were dropped (their counts are zero).
Prior usage remains **65,662 tokens / 114 intent slots**. Combined usage is
**108,123 tokens / 178 slots**, within the original 500,000 / 1,000 limits.

Direct successes by family: interval **0/4**, dependency **2/4**, inventory
**2/4**, version correction **2/4**. Six worlds succeed on exactly one of their
two seeds; **no world succeeds on both seeds**. All six public-accepted direct
answers are correct in this sample; this does not establish general reliability.

Model-generation durations sum to 568.105 seconds, episode durations to 630.830
seconds, and the process to 648.107 seconds including initialization and other
overhead. These are retained monotonic durations. UTC timestamp subtraction
differs from process duration by about 6.765 seconds; the cause is unmeasured
and UTC labels are not used for latency calculations. Dollars, energy and power
mode are unmeasured, not zero.

## Negative findings and behavior

All 16 envelope pairs have identical messages, prompt-token-ID hashes, and first
256 generated IDs. All 32 outputs start by reproducing the agent envelope.
The larger allowance yields 12 parseable wrong-shaped objects and four capped
transport failures, adding **8,079 tokens** without an accepted action.

Compact presentation changes the generated object toward a submit action, but
all 16 responses use the wrong answer shape, often a scalar/list where a nested
answer object is required. Six carry correctly shaped current citations; answer
shape still prevents acceptance. Direct has nine schema failures and one
transport failure (an unevaluated arithmetic expression inside JSON), alongside
its six successes. No response is repaired or rescored.

These behavioral categories were examined **after collection**; definitions,
raw record references and hashes are in `behavior-observations.py/json`. They
explain observations without changing frozen scoring or creating a new gate.

## Known confounds and what was not proven

Direct versus compact jointly changes output burden and citation responsibility;
compact versus envelope changes a presentation bundle. Only the two envelope
arms isolate output allowance. Direct runtime-provided citations are not evidence
of model citation selection. Reduced token use is not coordination efficiency:
all cells are single-agent and receive complete prepared evidence.

The worlds were already observed, repeats are sparse, and no confidence interval
or confirmatory verdict is computed. Shorter interfaces do not yet yield stable
action reliability. This study establishes neither generalization, autonomous
acquisition, stronger-model limits, swarm advantage, robustness nor production
readiness. Prior NOT_ADMITTED remains intact; collaboration is **UNMEASURED**.

## Next gate

This authorized campaign is closed. The local evidence favors investigating
answer-schema responsibility and narrow worker interfaces before increasing
output limits or N. Any revised interface, stronger-model control, new reserved
worlds or additional collection needs a separate frozen design and authorization.
Nothing was merged, released Stable, or automatically advanced to collaboration.

## Data and offline reproduction

`collection/` retains every prompt, output, generated token-ID list, receipt,
SQLite ledger, snapshot, complete grid, configuration and accounting record.
Prompt IDs are retained as SHA-256 digests, not raw ID arrays. The 64-row
[`episodes.csv`](descriptive-export/episodes.csv), 32-row
[`world-seed-means.csv`](descriptive-export/world-seed-means.csv),
[`summary.json`](descriptive-export/summary.json), audit receipts, authorization,
hardware and CI observations accompany them. CSV blank numeric fields mean
unknown, never zero.

For a standard-library-only audit, verify the three accepted wheel hashes in
`installed-artifacts.json`, then extract those wheels into one arbitrary directory
with `python3 -m zipfile -e WHEEL /tmp/interface-audit-site`. No package imports,
model files, GPU or network are needed for this verification. From the repo root:

```bash
python3 pheroos-bench/next-cycle/model-interface-live-v1/audit.py \
  --campaign pheroos-bench/next-cycle/model-interface-live-v1/collection \
  --prepared pheroos-bench/next-cycle/model-interface-v1 \
  --predecessor pheroos-bench/next-cycle/coordination-repair-live-v1/campaign/actionability \
  --source-site /tmp/interface-audit-site --output /tmp/interface-audit.json
python3 pheroos-bench/next-cycle/model-interface-live-v1/export.py \
  --audit /tmp/interface-audit.json --output /tmp/interface-export
```

Use fresh output paths. Source relocation verifies every original frozen SHA
without rewriting path identities; it does not rerun the campaign. The
[`publication/manifest.json`](publication/manifest.json) covers the delivered
payload. Audit portability and checksum reproduction are distinct from model
repeatability or an additional independent sample.
