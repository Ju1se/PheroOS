# E3 data contract

Status: implementation/data-integrity repair, not a new preregistration.
No pilot values, thresholds, frozen E1/E2 configs, or historical results are
changed by this repair. Synthetic passing fixtures are not experimental evidence.

## Required configuration

`pheroos-bench-e3-verdict` requires an explicit `--config`; there is no default
E3 calibration. Before collecting records, declare:

| Field | Meaning |
| --- | --- |
| `task.item_ids` | Map of benchmark/cell names to distinct item ID lists, fixed before collection. IDs are paired **within** their benchmark. |
| `arms.static_homog.N` | Nonempty list of distinct positive sizes. |
| `arms.static_diverse.N` | The same list, or `"same set as static_homog"`. |
| `statistics.repetitions_per_item_per_arm` | Positive integer; repetition IDs are `0..R-1`. |
| `statistics.confidence`, `statistics.bootstrap_resamples` | Declared bootstrap settings; existing defaults remain 0.95 and 10,000. |
| `model.provider_model_string` | Exact returned model/version string, not a silent alias substitution. |
| `budget.unit`, `budget.cap_per_item` | `tokens` or `dollars`, and a positive cap for each item/arm/repetition. All control-plane costs count. |
| `admission.arms_run` | `single` and `static_homog at max N` (or its resolved `static_homog@N` name). |
| `status`, `endpoints.quality_floor` | Confirmatory evaluation requires `frozen` and a calibrated quality floor in [0, 1], with no `PILOT` placeholders anywhere. |

Admission may precede treatment calibration, but its own item grid, repetitions,
maximum static size, model and budget must already be explicit. It evaluates
each declared benchmark separately with the existing paired-item bootstrap
gate. Any failed benchmark raises `SystemExit(1)`; no successful admission
output is emitted. This statistical CLI does not dispatch treatment.

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
and cross-cell variance assertion remain in force. Validation changes which
records are admissible, not these statistical thresholds.

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

Missing/inconsistent provider usage and model drift abort collection. Paid POSTs
are not automatically retried: a missing response is unknown spend, not a free
failed attempt. An aborted run is incomplete and may already have incurred
charges; it must not be treated as zero cost or successful evidence. The runner
is not an API billing ledger or a hard pre-call monetary budget enforcer.

Older records lacking phase, model or accounting evidence are rejected. Do not
backfill these fields from assumptions or relabel void pilot as confirmatory.
Keep them as historical evidence; any authorized new collection uses a new
directory and an explicitly reviewed configuration. Data validation alone
cannot prove a single run, dataset provenance, provider immutability, or that
adaptive-random stopping was sampled independently; those remain preregistration
and runner evidence requirements.
