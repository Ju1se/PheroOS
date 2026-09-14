# Model–interface diagnostic v1 — prepared, unexecuted

## Problem

The closed diagnostic published at `89650f532198abe86c2bd74cf8b5c679a1ae260c`
completed 28 valid known episodes, 113 model calls and 65,662 tokens. It did not
pass admission: D0 answered 0/8 correctly, D1 and D2 each 2/8. Two intervention
pairs changed actual inspection behavior without successful outcomes. These are
capability and interface findings, not an infrastructure abort or a collaboration
effect estimate. The earlier thresholds and stop decision remain unchanged.

## Hypothesis

Some failures may come from asking the model to reproduce an action envelope
and citations; others may persist when it receives a direct question with all
evidence. A larger output allowance may help, or simply extend envelope copying.
This small diagnostic distinguishes those possibilities before further scheduling
or scaling work. No improvement is assumed.

## Mechanism and baselines

Every cell receives the same task rule and complete current source contents,
through charged preparation at step 2, then exactly one response opportunity.

| Arm | Model output | Output cap |
| --- | --- | ---: |
| `direct_json_256` | Answer object only; runtime serializes submit and current receipt citations | 256 |
| `compact_action_256` | Submit, answer and citations using a compact question/source view | 256 |
| `envelope_256` | Historical D0 prompt and action contract | 256 |
| `envelope_1024` | Byte-identical historical D0 prompt and action contract | 1,024 |

Direct mode performs no answer repair or deterministic task solving. It still
requires an answer schema and is not unconstrained prose. Runtime-supplied
citations come from actual verified current receipts; this arm does **not** measure
model citation selection. All arms use the original public checker and separate
hidden objective after terminal cleanup. Public acceptance is not answer truth.

## Implementation

Bench source commit: `232c01d3a78f382cda73ccdc2593127a1cce6c8d`.
Runtime source commit: `2222d59bb05785528e4301dc14d164d538408ac6`.

The new bench modules are `model_interface_v1` and `model_interface_v1_pilot`.
The runtime adds the experimental `recorded_local_v3` adapter because the frozen
v1/v2 generation path caps output at 256. Both output-budget arms use this new
adapter. Its 2,048-token context bound, sampling, generated-token records and
existing Session/Driver/Campaign accounting are preserved. Protocol-core and
the old adapters, runners, task definitions and results are unchanged.

Version identities are bench `0.1.1.dev5`, runtime `0.1.0.dev4`, core `0.1.0`.
Accepted wheel SHA-256 values:

- Bench: `eaf9ad0c637152c6c9f4b12f708ca76de40881096d86f6a984ed55134e4285fc`.
- Runtime: `0d4e3d58c8fc23bae7870376df9a81c2032a00ff5523b609f1eb5cfb27170537`.

The existing installed dev2/dev3 CI consumers now explicitly install the retained
accepted bench dev4 wheel, so a new package version cannot retarget old runners.
The new consumer has its own installed-package check.

## Tests

- Full bench: **1,385 passed and 12 subtests passed**, zero skips.
- Fresh installed core/runtime/bench consumer: **149 passed**, zero skips;
  includes the new subprocess/Session cases, existing coordination consumer and
  all four R0 suites.
- Runtime wheel and sdist: each **206 passed and 12 subtests passed**, including
  G1 with final value 204 and 26 call units. Fourteen focused adapter tests pass.
- Behavior checks cover unchanged D0 prompt bytes, no hidden-answer exposure,
  current receipts, no answer repair, invalid/unknown accounting, partial grids,
  retained prior costs, and installed CLI exit/file/JSON behavior.

These checks use scripted model instruments, not GPU inference. A separate CPU
tokenizer preflight uses the existing local tokenizer and the real input-building
method: all 32 distinct world/arm prompts fit with their declared output reserve.
Input lengths are 121–261 direct, 155–318 compact, and 380–754 envelope tokens.
It loads no model weights and makes no generation calls. Its fixture reads are
engineering checks; real campaign preparation is independently charged.

The prior data head's GitHub CI finished with 85 successful checks, one skipped
check and no failures; the observation is retained separately. This is not a
claim about a subsequent publication head's CI.

## Experimental design

Config: [`pilot-config-proposal.json`](pilot-config-proposal.json), identifier
`model_interface_local_diagnostic_v1`, canonical SHA-256
`ed833e52d72e5a042fc56f0616c9ced9c52fe534302cfedc630da3445a3c1a8e`.
Episode contract: `model_interface_episode_v1`; descriptive method:
`model_interface_descriptive_v1`; CLI contract: `model_interface_cli_v1`.

The fixed grid has **64 cells**: eight already observed development worlds × two
seed bases (1729, 2718, plus 100 × world index) × four arms. Arm order rotates by
world and seed index, independently of JSON key ordering. N=1, one response per
cell, no feedback rounds or automatic retries. The existing local
`Qwen/Qwen2.5-Coder-3B-Instruct` revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5` uses temperature 0.7, top-p 0.9,
top-k 50 and the same 2,048-token context in every arm.

Additional caps are **64 intent slots and 131,072 input-plus-output tokens**.
The closed campaigns retain 114 intent slots and 65,662 tokens, giving combined
worst-case totals of **178 slots and 196,734 tokens**, within the original
1,000/500,000 caps. Unknown post-dispatch spending remains reserved. Invalid,
unresolved or incomplete collection prevents valid-subset summaries; unstarted
rows have null outcome/cost. Complete valid negative results exit 0; invalid or
unresolved collection exits 2. There is no new admission threshold and no
collaboration entry point.

The retained predecessor hashes, source identities, complete grid, prompts,
responses, generated token IDs, receipts, snapshots, and accounting are part of
the collector path. Repetitions are averaged within worlds for descriptive
quality outputs. Raw resource counts remain available; repeated seeds are not
independent task samples. This method does not change `r_paired_world_mean_v1`
or produce an efficacy verdict.

## Results and negative findings

**PREPARED_UNEXECUTED**: new live dispatches = 0; new live tokens = 0. No new
model capability, interface improvement, output-budget benefit, sharing benefit
or collaboration efficacy has been measured. The previous
`COMPLETE_NOT_ADMITTED` result remains the latest real observation.

## Known confounds

The direct/compact contrast changes output burden and citation responsibility
together. The compact/envelope contrast changes a presentation bundle, not just
length. Only the two envelope arms isolate output allowance. This four-arm
design does not estimate interface-by-budget interactions. Two seeds offer
limited repeatability evidence, and eight previously inspected development
worlds do not establish generalization. Synchronous local inference does not
test concurrency. Tokens and logical control units are not dollars or energy.

## What was not proven

No stronger-model control, fresh heldout validation, autonomous acquisition,
multi-agent advantage, production robustness or confirmatory result is included.
Already observed pilot worlds must not be relabeled as fresh heldout worlds.
Runtime validation remains distinct from semantic answer verification.

## Next gate

The implementation and installation artifacts are reviewable. Actual collection
requires one new, explicit authorization for this 64-cell local diagnostic:
the separately authorized preceding campaign is closed, and the retained
[cycle instruction](../coordination-repair-v1/inputs/PheroOS_Next_Cycle_Codex_Goal.md)
limits campaign count. Remaining token budget is not permission to rerun.

After authorization and installation/CI checks, freeze the source/config identity
and execute once. Interpret the full declared grid even if every answer fails;
do not tune thresholds or continue into collaboration. Any resulting interface
choice needs a separately frozen set of newly reserved worlds and repeated
validation. An independent stronger-model control additionally needs an exact
provider/model, data scope, request limit and spending cap before paid collection;
this preparation does not select a provider or use credentials.
