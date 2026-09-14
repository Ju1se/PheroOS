# Session capability diagnostic v1 results

**The bounded engineering audit passes. The evidence supports proceeding to a
separately frozen R4 study, subject to root review; it does not support a
coordination improvement, model-superiority claim, or confirmatory verdict.**

## Problem

R3 v3 exercised real local inference but did not establish useful semantic
interaction. Before scaling, the experimental runtime needed a concrete
closed-loop consumer using one Session ledger, plus an explicit larger-model
capability control on the same previously observed tasks.

## Hypothesis and mechanism

The engineering hypothesis was that both pinned models can execute bounded
model/tool work, preserve known costs through rejected task actions, and publish
only independently verified tool-evaluation facts under current authority.
Supplying all current public inspections was a diagnostic for the role of
information gathering versus subsequent action choice. It was not a forced
submission or isolated reasoning test.

## Baselines and implementation

Two Qwen2.5-Coder Instruct models, 1.5B and 3B, share the installed experimental
`Session`/`SessionDriver`, `Qwen2ForCausalLM` class, FP16/no quantization, original
task evaluator and exact v3 framing. No legacy G1 or R3 ledger was charged.
Every declared work item has a current version, dependency on the preceding
published evaluation fact, lease and fresh dispatch/publication authorization.
Model text is a proposal; a separate pure tool executes the original checker.
An invalid task action may yield a valid evaluation fact, whose task artifact
remains null. Session completion therefore does not imply task success.

`autonomous_single` uses six freely chosen actions and the original single-agent
history policy. `supplied_current_inspections` obtains every named public test
or source through real Session tool calls, then supplies those receipts to one
model turn at step 5. This means three code-test or two document inspections,
with the current evidence version 2. The model remains free to inspect or submit.
Session artifact references appear in visible receipt IDs; these newly
collected prompts are not byte-identical historical R3 prompts.

## Tests and experimental design

The complete declared grid is two models × four original worlds × two
conditions: 16 episodes, with condition order alternated by world. Both models
use seed `2081 + world_index * 100 + step`, temperature 0.7, top-p 0.9, top-k 50,
256 maximum new tokens and a 2,048-token prompt-plus-generation bound. Each
episode has the common 12,288-token/16-call ceiling and 65,536-byte context and
artifact bounds. Diagnostic preparation is explicitly not a matched-budget
efficacy control.

Before collection, 18 new provider-free Session-consumer tests and 235 unchanged
task/tool/framing regressions passed. The [validation receipt](provider-free-validation.json)
is copied unchanged from the original test record; its contract hash precedes
the root's final wording/path-only documentation edit. The collection
[freeze](freeze.json) is authoritative for all executed inputs. Earlier external
wheel and sdist acceptance each passed 131 tests, as recorded in the
[readiness report](../session-model-readiness-v1/RESULTS.md).

## Results and negative findings

All 16 Session runs completed, with seven successful task objectives, nine
failed objectives and zero `INVALID_ABORT` episodes. All 56 replies were
admitted as sole JSON fences. Nineteen model actions passed the original public
checker: 12 submissions and seven inspections. The remaining 37 model actions
were retained as invalid task actions with known costs.

| Model | Condition | Successes / 4 | Actual tokens | Model calls | Tool calls |
| --- | --- | ---: | ---: | ---: | ---: |
| 1.5B | autonomous single | 2 | 15,905 | 24 | 24 |
| 1.5B | supplied current inspections | 1 | 3,359 | 4 | 14 |
| 3B | autonomous single | 2 | 16,016 | 24 | 24 |
| 3B | supplied current inspections | 2 | 3,381 | 4 | 14 |

Both autonomous conditions solved `clamp` and `chunk_count` and failed both
evidence-revision worlds. With supplied inspections, 1.5B solved `clamp` but
its `chunk_count` proposal violated the one-source-line-per-string schema; 3B
solved both code worlds. Both models failed both supplied-inspection evidence
worlds. In all four of those final diagnostic calls, the model freely chose
`{"action":"inspect","target":"index_entry"}`, an invalid placeholder target.
This is an observed action-selection failure, not proof of inability to reason
over the supplied documents. The schema, tasks and framing were not relaxed.

Actual usage is **38,661 tokens: 36,581 input and 2,080 completion**, across
56 model and 76 pure-tool calls. The 76 tool calls include 20 preparation
inspections and 56 evaluations of model proposals. All 76 publication
verifications are explicitly recorded separately. Failed episodes retain
18,455 tokens; public-invalid model actions retain 22,184 tokens. These are
overlapping cost slices and must not be added. Reserved tokens, unknown tokens
and unknown calls are all zero.

Logical serialization measures are 311,806 request bytes, 62,579 response bytes
and 252,247 trace bytes. All response bytes are retained; the retained-response
counter is another view of those same 62,579 bytes. These overlapping logical
measures are not physical I/O, energy or money. Model loading is recorded
separately: approximately 6.08 seconds for 1.5B and 12.15 seconds for 3B. Peak
generation tensor allocations were 3,201,861,632 and 6,420,271,104 bytes,
respectively, excluding other device/process memory. These are descriptive
engineering observations, not comparative hardware performance results.

## Independent audit

The additive [audit](independent_audit.json) passes. It verified all 654 frozen
input hashes, including six public core JSON contracts and both complete model
file sets, against the collection's freeze and after-check. It opened all 16
SQLite databases in immutable/read-only mode, checked database integrity, and
matched every run, work, call, artifact and event row to the original exports.

Replay independently reconstructed all single-agent history selection, current
inspection indices, raw framing, exact model/tool requests, published receipt
references, original public evaluations and final task selection/evaluation.
The frozen offline tokenizers reproduced all 56 prompt counts. It recomputed
208 public-core authority projections and all 564 ordered lifecycle events,
including request/receipt/publication bindings, and reconciled summary, token,
call and byte accounting. Original evidence hashes remained unchanged. The
[audit tool](../../tools/audit_r3_session_capability.py) generated no model calls.

## Known confounds and what was not proven

These are four previously observed worlds and one declared seed per step, with
no held-out sampling, statistical noninferiority test or confirmatory evidence.
The larger-model control is implemented; stronger general capability is not
established by these observations. The supplied-inspection condition changes
preparation and generation counts. No causal coordination benefit or useful
multi-agent interaction is measured by this single-agent follow-up.

One model occupied one GPU at a time. Other CPU implementation/test work was
active, so timings are descriptive and not an isolated latency, throughput or
scaling comparison. Generated token IDs were not stored: completion counts
reconcile to durable receipts and the frozen tensor-length implementation,
rather than independent reconstruction from decoded text. Runtime trace
ordering and authority projections are checked; the final ledger does not
independently reconstruct historical wall-clock lease expiry. Cancellation,
crash/recovery faults, malicious hosts, durable issuer custody and arbitrary
external exactly-once effects remain outside this pilot's evidence.

## Identity and next gate

Method/config: `r3_session_capability_v1`, phase `capability_diagnostic`,
`counts_toward_verdict=false`. Config SHA256:
`9976a1276881c320524e78e1cf29adb3e191abf16555c8e90bb5f922a6252c94`.
Runner SHA256:
`e08d0585800b02302391915216bc0c5eeed5ecbcf37fbffa139227bdb26102ab`.
The freeze contains the complete source, test, contract, interpreter and model
identities. Audit-time base HEADs remain bench/core
`b154472becea561ac1f5fc442a7ccf372ab154f8` and external runtime
`e3ef1e8ed0812296601e4a901768af4a1068b5e0`; uncommitted work makes the recorded
source hashes, rather than HEAD alone, the actual implementation identity.

Models are `Qwen/Qwen2.5-Coder-1.5B-Instruct` revision
`2e1fd397ee46e1388853d2af2c993145b0f1098a` and
`Qwen/Qwen2.5-Coder-3B-Instruct` revision
`488639f1ff808d1d3d0ba301aef8c11461451ec5`, persisted under the external runtime's
`.local/models/`. Both used Python 3.12.3, PyTorch 2.11.0+cu128,
Transformers 4.57.3, CUDA 12.8 and an RTX 5070 Laptop GPU. The installed Session
target is `/tmp/pheroos-session-site`; shared runtime-environment source files
and all frozen task/evaluator files were preserved.

**Recommendation for root review: accept this bounded G5 engineering follow-up
and allow the separately frozen R4 study to proceed.** Exact model identities,
common runtime/class/task/evaluator controls, coherent Session execution,
complete failed-action costs and the larger-model/preparation controls have
been exercised and audited. Positive efficacy is not an engineering gate
requirement, and no strategy promotion follows. The original R3 interaction
finding remains negative; R4, R5 and the master goal are not completed by this
report. Historical E1/E2/E3 and prior R-series evidence remain unchanged.
