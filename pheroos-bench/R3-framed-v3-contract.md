# R3 framed-action pilot v3

`r3_framed_action_pilot_v3` is an experimental engineering pilot. Execution
requires the root review and preceding G4 decision; this implementation does
not itself satisfy either gate. It makes no confirmatory claim and every
episode has `counts_toward_verdict=false`.

The original v2 pilot retained 20 failed episodes and 160 invalid actions. The
separate format audit found 160 sole JSON fences; offline removal of just that
wrapper admitted 14 public-valid actions against their original histories.
That analysis was posthoc, did not run new generations or propagate repaired
history, and did not alter historical outcomes. It motivates this explicit
interface experiment, not an efficacy conclusion or a general model diagnosis.

## One common framing change

Every arm receives the same response adapter. It accepts a strict bare JSON
object, or exactly one lower-case `json` Markdown fence with LF delimiters:

````text
```json
OBJECT
```
````

Exterior JSON whitespace is permitted. The adapter rejects prose outside the
object/fence, multiple or nested fence blocks, different fence labels,
CRLF fence delimiters, trailing header spaces, malformed JSON, duplicate keys,
nonfinite constants and non-object values. It removes only the accepted fence;
it never edits JSON contents, code lines, targets, citations or action schemas.
Rejected responses keep their raw text and remain ordinary failed actions with
their full costs. The unchanged task checker decides semantic validity.

`FramedWorker` wraps the existing external `ToolWorker`. Only the returned
generation view is normalized: `raw_text` preserves the model output, `text`
is the task-checker input, and `framing` records admission and parse diagnostics.
`raw_reply_sha256` binds the complete original canonical runtime reply, including
its raw ledger snapshot. Reconstruct that reply by removing `raw_text`,
`framing`, `processing_cost` and `raw_reply_sha256`, then restoring `text` from
`raw_text`. Its call receipt must exactly equal the durable ledger's received
raw response before any task checking or publication. Tokens always describe
the actual model generation. Formatting never establishes evidence or authority.

## Fixed experiment

All five arms retain v2's exact visibility, tools, task semantics, verifier,
context fitting and selection: single, independent, manager graph, blackboard,
and versioned blackboard. The four existing code/evidence worlds are reused;
they are previously observed worlds, not held-out evaluation. Six main turns
and two artifact-withheld probes at zero-based steps 2 and 4 run per episode.
Probe artifacts never enter main history. Both valid actions must differ
semantically and an eligible artifact must have been removed to count a valid
action change; this observation need not improve the task or prove a downstream
collaboration benefit.

The seed is **1073** plus the same world/step offsets in every arm and its paired
probe. There are 20 episodes, 120 main calls and 40 probes. Per-call output is
at most 256 tokens and prompt plus output reservation is at most 2,048 tokens.
Each main ledger has a 12,288-token cap; each probe ledger has a 4,096-token cap.
The whole declared experiment reserves at most 327,680 tokens. No automatic
retry, stronger verifier, alternate model, prompt change or post-result tuning
is part of this version.

The model remains Qwen/Qwen2.5-Coder-1.5B-Instruct revision
`2e1fd397ee46e1388853d2af2c993145b0f1098a`, float16 without quantization.
Its complete original model manifest is pinned by canonical SHA-256
`6cd1118d77ca168de77066bf7479020136a0fb66f206bf49171aff0ec900ede3`.
The unchanged local runtime uses temperature 0.7, top-p 0.9, top-k 50 and one
resident CUDA model serving logical agents sequentially. This is not N-agent
hardware concurrency or R4 scaling. Any escalation needs a new explicit
configuration and decision; none is automatic here.

## Accounting and integrity

Raw model transport is counted before normalization, including tokenizer,
publication and final-ledger requests. Failed requests retain their attempted
request bytes; missing responses are marked unreceived and are not inferred
free. Each received generation adds logical response-copy, frame-read,
JSON-parse, frame-write and receipt-check operation/byte counters. JSON parsing
counts the exact candidate UTF-8 text bytes; other stages use canonical JSON
byte sizes of their recorded inputs/outputs. Rejected oversized inputs do not
claim an executed parse. Counter metadata and duplicate raw/normalized storage
are included in `serialized_trace_bytes`. These stage counters overlap by
design: a byte processed in several stages incurs several stage costs. They
are not physical memory/disk I/O, GPU energy, money or provider calls.

Parser admissions, public-valid actions and final task success are separate
measurements. Failed tasks retain all main/probe usage and processing costs.
Publication or receipt-validation failure keeps already received usage and raw
text. Timeout/cancellation never releases an unknown dispatched reservation or
reissues a call. A missing final ledger remains unavailable, rather than zero.
Partial traces and received replies survive an INVALID_ABORT; the full declared
episode/probe grid and resolved accounting are required for a complete summary.

Before starting a model worker, the runner verifies installed runtime modules
against the selected source tree, records installed core/runtime package file
hashes and dependency versions, checks every local model-manifest file, and
creates an exclusive output directory with a pre-generation freeze. The freeze
includes this contract/config/test, reused bench sources/tests, runtime sources,
installed artifacts and model identity. Source, installed closure and model
bytes are checked again before a complete summary is emitted. Existing output
directories are never reused. Raw traces, probes, durable ledgers, prefix curves,
episode records and any abort diagnostic remain available.

The v3 loop has explicit new scope and method identifiers because v2 hardcodes
them. Frozen v1/v2 remain solely for exact reproduction; v3 reuses their existing
context-fitting, ledger-reading, withholding, task and evaluator functions
without global mutation. No protocol-core or frozen implementation is changed.

Passing this pilot would establish only the measured interface/task behavior
under its frozen conditions. It does not itself pass G5, demonstrate useful
coordination, establish a capability floor across models, or authorize R4
efficacy conclusions. Runtime development authority, single-host durability and
in-flight cancellation limits remain those of the existing R3 adapter.
