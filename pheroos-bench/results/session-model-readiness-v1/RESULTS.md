# Session model readiness v1

## Problem

The newly downloaded larger checkpoint needed an actual GPU load/generation
check and an installed-consumer exercise through the experimental Session.

## Hypothesis and mechanism

One 3B FP16 model can fit the available RTX 5070 Laptop GPU and propose a
bounded answer using a verified artifact reference. A separate deterministic
tool and current authority are required before publication. This is an
engineering check, not an algorithmic-efficacy test.

## Baselines and implementation

There is no comparative efficacy baseline in this readiness check. The same
provider-free inspector-to-solver journey was already tested from wheel and
sdist. This run adds exactly one opt-in local-model proposal. The inspector
publishes the declared integers; the solver receives their addressed artifact
reference, restores its private checkpoint after reopening the store, and
requests a strict one-field JSON total. Model replies never create authority.

## Tests and experimental design

The final external wheel and sdist each passed 131 tests, including 27 journey
tests. Frozen runtime/core sources remained unchanged. This run uses the
installed target `/tmp/pheroos-session-site`, external consumer
`tools/run_session_journey_v1.py`, its declared seed 7 and 64-output-token bound.
The config, interpreter, complete model manifest and exact runtime source hashes
are in [report.json](report.json) and [config.json](config.json).

## Results and negative findings

The model loaded and generated successfully: one tool call, one model call,
63 actual tokens, zero reserved tokens and zero unknown calls/tokens. Its raw
proposal was `{"items":[2,3],"total":5}`. The numeric total is correct, but the
extra `items` field violates the predeclared exact schema. The task therefore
**failed**, the run was cancelled, and no final artifact was published.
Committed model-receipt rereading returned identical content without additional
calls or token charges. The failure is retained; the parser was not relaxed.

## Known confounds and what was not proven

This is one stochastic call on a trivial task, not a capability threshold,
scaling experiment, success-rate estimate, timing comparison, or R5 acceptance.
CPU implementation/tests were active elsewhere, so elapsed values are only
diagnostic. Logical JSON byte counts do not represent physical I/O, energy or
money. The development authority adapter and trusted-host limitations remain.

## Identity and next gate

Runtime base commit `e3ef1e8ed0812296601e4a901768af4a1068b5e0`; bench base commit
`b154472becea561ac1f5fc442a7ccf372ab154f8`. Both contain uncommitted work; the
source hashes identify actual code. Method/config identity is `session-journey-v1`,
config SHA256 `a716f7d4a1f45326db25ff22a200f0c54c00961817f94d288825157ad4e81fda`.
Model: Qwen/Qwen2.5-Coder-3B-Instruct revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5`, FP16, no quantization.
Its verified copy is now persisted under the external runtime's
`.local/models/qwen2.5-coder-3b`; the recorded initial path remains unchanged.

Proceed to the separately configured G5 capability diagnostic. This readiness
result counts toward neither confirmatory evidence nor the master-goal verdict.
