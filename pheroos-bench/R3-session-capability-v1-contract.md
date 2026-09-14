# Session capability diagnostic v1

`r3_session_capability_v1` is a finite engineering follow-up over the same four
previously observed R3 worlds. It supplies a larger local model and a concrete
installed Session consumer before any R4 study. It is not confirmatory evidence,
a matched-budget efficacy comparison, or an R4/G5 completion verdict. Historical
E-series, R3 v1/v2/v3, task fixtures, framing code and thresholds remain unchanged.

The declared grid is two pinned models × four worlds × two conditions, one
episode per cell. Both Qwen2.5-Coder Instruct models (1.5B and 3B) use the same
`LocalModelAdapter`, checked `Qwen2ForCausalLM` class, float16/no quantization,
existing sampling (`temperature=0.7`, `top_p=0.9`, `top_k=50`), 256 maximum new
tokens and 2,048 prompt-plus-generation tokens. Call seeds are
`2081 + world_index * 100 + step`; model identity never changes that rule.
Models load sequentially. Model load and tokenizer work are not generated tokens.
Loading elapsed time and peak/current CUDA allocations are recorded with each
model identity separately from episode generation and ledger costs.

- `autonomous_single`: the same six-turn single-agent task/history policy as R3,
  without efficacy probes. Oldest whole receipts are evicted only when the actual
  tokenizer requires it, using unchanged task/workspace reconstruction.
- `supplied_current_inspections`: select every public step-5 `test_index` or
  `source_index` entry in its declared order. Execute each inspection through a
  real deterministic Session tool call, then provide all resulting current
  receipts to one model turn at step 5. No receipt can be silently evicted in this
  condition. A remaining inspect action or an invalid submission simply fails
  the objective; the orchestrator never repairs or forces a submission.

The diagnostic exposes reading/interpretation versus action planning, with
different preparation and generation counts. It must not be labeled a
matched-budget control or a coordination improvement. There are three current
code-test inspections or two current document inspections; index selection never
consults hidden tests or final answers. Source version is the unchanged step-5
version. All model messages use unchanged `messages_for`; admission uses exactly
the frozen v3 `frame` function (bare strict JSON or a sole exact JSON fence).

Each global turn/inspection is a declared Session work item, chained to the
previous published evaluation fact. Session is the sole execution ledger, with
12,288 total tokens and 16 logical calls per episode. Autonomous episodes execute
six model and six tool calls; supplied-inspection episodes execute one model and
four code-tool or three document-tool calls. Pure tools consume zero model
tokens, but all logical calls, requests, receipts and authority/trace overhead
are retained. Context/artifact wire bounds are 65,536 bytes for both conditions.

Every tool runs unchanged `r3_tool_tasks.apply`. Its result is wrapped as an
evaluation fact and independently recomputed before current publication
authorization. Recomputations and their elapsed time are recorded separately;
they are verifier work, not hidden model or tool dispatches. A correct evaluation
fact may report an invalid action. Its `result.valid=false` and `artifact=null`
remain unchanged, so it cannot become task evidence. Only current public-valid
submitted candidates reach the unchanged final scorer. Hidden scoring occurs
after the episode and never supplies model feedback.

Raw generation/evaluation replies are compared with their settled Session
receipts. Publication remains bound to that tool receipt under current authority.
Known usage survives parsing, verification and publication failures. Dispatched
unknown calls, including zero-token tools, remain explicit and terminate
collection as `INVALID_ABORT`; no retry or silent CPU/model fallback occurs.
Unattempted declared cells remain `INVALID_ABORT/NOT_STARTED` with unavailable
episode accounting, rather than becoming zero-cost failures. Ordinary invalid
actions remain observed failed task behavior. All model sizes' costs are reported.
If a snapshot cannot be read or reconciled for reporting, its available raw data
and original error are retained; unavailable costs/counts are null and the row
remains explicitly invalid and unresolved.

Before either GPU model loads, `freeze.json` records the exact config, contract,
test/task/framing/runtime/core source and public core JSON contract hashes, interpreter binary and package
versions, plus both complete model manifests and verified model-file hashes.
Source/model hashes are checked again after collection. Output is exclusive and
contains per-episode SQLite ledgers, raw requests/replies, published evaluation
facts, framing/context diagnostics, token/call/JSON-byte accounting, environment,
full-grid outcomes and a descriptive summary. Timing includes local overhead and
does not establish GPU throughput or hardware scaling. Any post-observation
change requires a separately identified follow-up and a new output freeze.
The summary checks exact nonnegative integer usage, call states/identities,
request/work/version and evaluation-response bindings, and ledger totals. Session
artifact references appear in visible receipt IDs, so these are newly collected
Session prompts, not byte-identical reproductions of the historical R3 prompts.

Run only after the root's sequential gate, using the installed runtime target:

```bash
PYTHONPATH=/tmp/pheroos-session-site:/home/scott/projects/PheroOS/pheroos-bench/src \
/home/scott/projects/PheroOS-runtime/.local/venv312/bin/python \
  -m pheroos_bench.r3_session_capability \
  --config /home/scott/projects/PheroOS/pheroos-bench/r3-session-capability-v1.json \
  --output NEW_DIRECTORY \
  --runtime-site /tmp/pheroos-session-site \
  --small-model /home/scott/projects/PheroOS-runtime/.local/models/qwen2.5-coder-1.5b \
  --large-model /home/scott/projects/PheroOS-runtime/.local/models/qwen2.5-coder-3b
```
