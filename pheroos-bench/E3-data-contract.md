# E3 data contract

Status: versioned estimand and collection repair, not a new preregistration.
`paired_item_mean_v1` changes the statistic used by admission, superiority and
the quality floor. It requires a new prospective analysis plan. Frozen E1/E2
configs and historical results remain unchanged. Synthetic fixtures and power
diagnostics are not experimental evidence.

## Required configuration

`pheroos-bench-e3-verdict` requires an explicit `--config`; there is no default
E3 calibration. Before collecting records, declare:

| Field | Meaning |
| --- | --- |
| `task.item_ids` | Map of benchmark/cell names to distinct item ID lists, fixed before collection. IDs are paired **within** their benchmark. |
| `arms.static_homog.N` | Nonempty list of distinct positive sizes. |
| `arms.static_diverse.N` | The same list, or `"same set as static_homog"`. |
| `statistics.repetitions_per_item_per_arm` | Positive integer; repetition IDs are `0..R-1`. |
| `statistics.estimand` | Must explicitly be `paired_item_mean_v1`; absent or legacy methods are rejected, not silently reinterpreted. |
| `statistics.confidence`, `statistics.bootstrap_resamples` | Declared bootstrap settings; existing defaults remain 0.95 and 10,000. |
| `model.provider_model_string` | Exact returned model/version string, not a silent alias substitution. |
| `budget.unit`, `budget.cap_per_item` | `tokens` or `dollars`, and a positive cap for each item/arm/repetition. All control-plane costs count. |
| `admission.arms_run` | `single` and `static_homog at max N` (or its resolved `static_homog@N` name). |
| `status`, `endpoints.quality_floor` | Confirmatory evaluation requires `frozen` and a calibrated quality floor in [0, 1], with no `PILOT` placeholders anywhere. |

Admission may precede treatment calibration, but its own item grid, repetitions,
maximum static size, model and budget must already be explicit. It evaluates
each declared benchmark separately. The point estimate is the mean paired
item difference, and the interval bootstraps that same mean. The retained gate
requires a nondegenerate interval and a gap greater than ten interval
halfwidths. Any failed benchmark raises `AdmissionRejected`, a `SystemExit(1)`
subclass carrying the report. The CLI prints and optionally saves that report
before exiting 1. This statistical CLI does not dispatch treatment.

## Estimand and uncertainty

First average repetitions within each `(cell, item_id, arm)`, subtract the two
arm means within each item, then average those differences. Each item has equal
weight: benchmarks contribute in proportion to their declared item counts.
Repetitions do not count as extra independent items. Confirmatory intervals
resample paired items within benchmark strata while retaining each stratum's
size; admission evaluates each benchmark on its own.

The primary and every co-primary use two-sided percentile intervals, normally
95%, and require a lower bound strictly above zero. The corresponding nominal
directional alpha is 0.025; this is not a guarantee of finite-sample calibration.
The median and its interval are robustness diagnostics only. The quality floor
also uses the mean across item means. Intervals with endpoints within `1e-12`
are marked `INSUFFICIENT_RESOLUTION`. Any such primary/co-primary interval gives
an `INCONCLUSIVE` verdict and cannot pass automatically.

Reports disclose actual quality and cost by benchmark and arm, including sums
and means. A shared cap does not establish equal expenditure: the research
question is quality under the same cap, not demonstrated quality per token.

## Required records

Input is JSONL, one aggregate record per `(cell, item_id, repetition, arm)`:

```json
{"cell":"example","item_id":"item-0","repetition":0,"arm":"single","model":"exact-model-version","quality":1.0,"tokens":123,"phase":"admission","counts_toward_verdict":false}
```

Quality must be finite and in [0, 1]; the runner emits exact-match 0/1 scores.
Token usage must be a known nonnegative integer. Dollar-budget records instead
need known finite nonnegative `dollars`, including the declared pricing basis
in the collection evidence. The current chat runner reports tokens only.

Admission requires both arms on every declared item and repetition.
Confirmatory records require `adaptive_K`, `adaptive_random`, **every** configured
homogeneous and diverse static arm, `phase="confirmatory"`, and
`counts_toward_verdict=true`. If `arms.single` is declared, its complete grid is
also required and `adaptive_K_vs_single` is reported as secondary only, never
added to a success gate. Missing/extra/duplicate grid entries, mismatched
models, exceeded budgets and non-finite measurements are errors, not exclusions
from pairing. Admission and pilot records cannot enter a confirmatory verdict.

The primary comparison remains adaptive K versus adaptive random. Co-primary
success still requires beating every declared static arm; the quality floor
and cross-cell variance assertion remain in force. Gate constants are retained,
but the versioned mean statistic changes their interpretation and needs
prospective calibration.

## Collection and migration

Each input JSONL item needs a nonempty `question` (or `problem`) and a known,
nonempty ground-truth `answer`. Direct `run(items=...)` callers must additionally
provide distinct nonempty `item_id` strings. These are checked before any model
call: missing labels cannot make an empty response count as a correct answer.

The E3 chat runner accepts `--phase admission` or `--phase pilot` and writes
`calls.ndjson`, aggregate `admission.ndjson` (also for void pilot), and metadata
to a fresh output directory. Every record includes its phase; the filename is
not permission to use pilot data for admission. Run single and maximum-N static
collection explicitly, then supply their combined grid to the admission CLI.

Preview the item/arm/repetition call count with `--dry-run`; it needs no API key
and performs no model/tokenizer calls or output-directory writes. Live CLI
collection requires both `--output` and an explicit positive `--max-calls`;
Python callers must supply `run(max_calls=...)`. A plan above this limit fails
before dispatch. The limit is per invocation, not across separate runs.
`max_tokens` bounds completion tokens only. The preview reports unknown input,
total-token and monetary upper bounds as null.

Credentials and request bodies pass to curl over stdin rather than process
arguments. Only one worker-sized batch is submitted at a time. A failed batch
is drained to preserve returned usage and stops later submissions. Aborted
collection writes diagnostics and available receipts, not aggregate evidence
eligible for admission. Already dispatched requests can still incur charges.

Missing/inconsistent provider usage and model drift abort collection. Paid POSTs
are not automatically retried: a missing response is unknown spend, not a free
failed attempt. An aborted run is incomplete and may already have incurred
charges; it must not be treated as zero cost or successful evidence. The runner
is not an API billing ledger or a hard pre-call monetary budget enforcer.

Older configurations without the estimand version and records lacking phase,
model or accounting evidence are rejected. Do not
backfill these fields from assumptions or relabel void pilot as confirmatory.
Keep them as historical evidence; any authorized new collection uses a new
directory and an explicitly reviewed configuration. Data validation alone
cannot prove a single run, dataset provenance, provider immutability, or that
adaptive-random stopping was sampled independently; those remain preregistration
and runner evidence requirements.

## Known limitations before freezing

- Ten times a 95% interval halfwidth is about 19.6 standard errors under a
  normal approximation. This gate needs its own justification and joint power
  analysis; correcting the estimand does not validate its feasibility.
- The retained cross-cell variance assertion rejects a single-benchmark
  confirmatory run and can reject valid arms whose benchmark means coincide.
  It is an uncalibrated design constraint, not proof that a control works.
- Adaptive-K, the independent random stopping distribution, calibrated quality
  floor and full joint success power are not implemented/frozen here.
- Input pricing and a pre-dispatch monetary limit are unresolved. Unknown
  failed-request spend cannot be reconstructed from a call-count limit.

See the [unfrozen prediction draft](results/e3/prediction.md) and its offline
synthetic sensitivity evidence for assumptions and outstanding decisions.
