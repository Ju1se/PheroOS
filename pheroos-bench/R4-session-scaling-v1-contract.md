# Experimental Session scaling pilot v1

Method `r4_session_scaling_pilot_v1`, environment `r4_task_fixtures_v1`.
This predeclared development pilot never counts toward confirmatory evidence.
All source, config, installed runtime/core, model and dependency identities are
frozen before inference. Earlier R-series source, evidence and thresholds remain
unchanged. Protocol-core requires no new contract.

## Problem and hypothesis

Dividing a fixed amount of work among more constrained private histories can
lose context, while sharing verified work can introduce repeated or obsolete
information and communication overhead. Increasing agent count may help, have
no effect, or hurt. Model size may be more useful than coordination. These are
separate questions, not an assumed monotonic scaling law.

## Task and information boundary

Four versioned finite worlds contain two bounded integer code repairs and two
closed evidence tasks. The evidence sources change at global turn 16 in every
condition. This new 32-turn environment does not cycle or change the meaning of
the frozen six-turn R3 evaluator. Public inspection tools and submission checks
are separate from the hidden final objective. The scorer never selects which
model output to publish or supplies model feedback. The latest current valid
submission is selected by a fixed public rule, then scored independently.
All hidden final/prefix scoring runs after execution and deadline decisions
finish. Its time is exported separately, so early-exiting hidden checks cannot
change how many later model turns are admitted.

These four hand-constructed development worlds do not establish generalization
or a capability threshold across task distributions. No generation seed, task,
parser or outcome criterion is changed after results. World, not agent count,
turn or policy, is the statistical unit; there is one generation seed schedule.
World/condition execution order is shuffled using the declared order seed within
cohort/resource-regime blocks before outcomes. This reduces systematic order
bias; it does not make sequential timing a hardware-controlled replication.

## Treatments and controls

Round-robin agents execute exactly the same global turn slots. N is
1, 2, 4, 8, 16 or 32, with at most 32 aggregate model calls. N=32 must exercise
32 identities in a full run; declaring idle identities is not scaling evidence.
Partial budget/deadline runs retain actual active-agent counts and allocation.
Private evidence completion has a declared structural lower bound: each current
version needs three inspections and one submission by the same agent. With
16 slots per version and N>=8, a private agent has at most two turns and cannot
meet that bound. This is an information-allocation consequence, not a measured
model capability threshold. Strong single-agent and shared-blackboard controls
remain central to comparisons; beating that restricted private arm is insufficient.

All policies have a 32-record aggregate coordination-history bound and select
at most four receipts for a model request. `private` selects the current agent's
own history and supplies the iterative single-agent and independent sampling
controls. `blackboard` shares recent records. `dedup_ttl` removes repeated
provenance and expires receipts after eight turns. `versioned` also filters to
the current task/source version. The simple control is not intentionally made
weak. Agent labels and record IDs are omitted from model prompts: complete
sharing should give an expected-null N control when selected information is
identical. Policy metadata cannot create task evidence or current authority.

The 1.5B cohort runs all four policies at all six N values. The 3B cohort and
the mixed cohort run private and blackboard at N=1,4,16,32. Mixed execution uses
1.5B for slots 0–27 and 3B for slots 28–31, even at N=1. This fixed escalation
schedule is disclosed and every larger-model call is charged. It is not an
adaptive escalation claim; larger model size is not presumed superior.

Both models are official Qwen2.5-Coder Instruct checkpoints, FP16 with no
quantization or remote code. Exact revisions are in the config/manifests. The
3B checkpoint has 3.09B parameters according to its
[official model card](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct).
This is one model family, not cross-family replication. Local inference uses no
paid API. Monetary cost and energy remain unmeasured, rather than zero.

## Shared execution and resource regimes

The external experimental `Session` is the sole state/accounting owner. Every
global turn has a declared work item, lease, one model call and one deterministic
task-tool call. Current public-core authorization gates dispatch/publication.
A verified tool-evaluation fact can record an ordinary invalid action; only its
valid task artifact enters task evidence. Model outputs alone cannot publish.

All episodes have a 64 runtime-call ceiling, 256 output-token cap,
2,048 prompt-plus-output context bound and the same tools. The full allocation
study uses `fixed_calls`: 32 model calls with a 65,536-token ceiling that is
deliberately nonbinding given the request bound. It can exercise all 32 agents.
Separate `fixed_tokens` episodes impose a binding 8,192 aggregate token ceiling;
they run small private/blackboard at every N and medium private at N=1. They
retain unused declared agents and exact actual allocation when the budget stops
execution early. This is distinct from pretending the large ceiling tests token
scarcity. All conditions within a resource regime share its total budget.
The runner removes oldest selected receipts until the common token bound fits;
it records every trim. It never silently removes task instructions. Call/token
runs stop at the first exhausted ceiling or 32 model turns, not hidden success.

Separate 30-second deadline episodes run private/blackboard with the small
model at every N, plus the medium single-agent control, with the same nonbinding
65,536 token ceiling. A clock check gates
new dispatch and publication. A late generation receipt settles accounting but
does not publish; cancellation fences unfinished work. Every compared success
outcome requires the same final source version. Stopping before the revision
cannot count as final completion even when an earlier answer was correct.
Current-snapshot success and whether the final version was reached are separate
diagnostics; they are never pooled as final success across different versions.
Valid budget/deadline stops are ordinary outcomes; transport, storage, accounting
and unexpected runtime failures remain explicit INVALID/ABORT.

One resident checkpoint serves agents sequentially. N is logical agent count,
not GPU replicas or physical parallelism. Deadline trials begin with resident
weights. Weight loading/replacement is separately timed and exported; mixed
within-episode switching also appears in episode elapsed time. Logical
concurrency is fixed at one throughout. No hardware scaling, equal dollar cost,
or arbitrary parallel GPU capacity is claimed. Additional replicas are not
required to answer this bounded fixed-concurrency allocation question.

## Accounting, evaluator and measurement

Raw model requests/responses, durable SQLite calls, verified tool facts,
selected artifact records, trace events, partial calls and failed work remain
available. The runner checks exact request/response bindings before evaluating
the model reply. Final snapshot totals must reconcile to durable calls. Unknown
usage is not zero; an unreadable ledger is null accounting, not a free episode.

Metrics include final/prefix objective success, actual tokens, larger-model
tokens/calls, active identities and per-agent calls, model/tool call counts,
request/response/trace bytes, selected foreign-record bytes, context trimming,
repeated inspections, current-source coverage, action diversity, elapsed time,
model execution time, model loading and bounded coordination history. Logical
processing operations and bytes include policy reads, context construction,
tokenization, framing, binding verification, tool replay and Session boundaries.
These instrumentation-stage measures overlap raw transport/storage measures;
they are not physical I/O or machine instruction counts. GPU tensor peak memory
excludes other processes and device allocations outside the adapter.

The additive exporter uses unchanged `r_paired_world_mean_v1` with phase
`instrument_check`, one world row per condition, and exact paired grids.
`call_units` means model calls + tool calls + declared logical control operations,
including failed actions; it is not tokens, money or GPU work. Rich raw costs
remain separate. Only matched N/cohort/regime policy contrasts use this adapter.
Any missing, duplicate, inconsistent or INVALID source row blocks usable subset
exports. Valid unresolved source accounting is identified separately and cannot
support known-cost inference. No pilot CI or negative finding changes a gate.

## Validation and gates

Deterministic tests cover hidden/public separation, actual N allocation, shared
prompt invariance, provenance/expiry/current-version behavior, raw receipt
binding, exact types, deadline authority fencing, late costs, invalid grids and
budget accounting. Existing G1/R0 and relevant R3 regressions must remain green.
The G5 capability/Session follow-up must be audited before this study runs.

After execution, independently replay task contexts/evaluators and reconcile
every ledger before reporting. Publish a new phase report with negative findings,
confounds, unproven claims and the next R5 gate. No policy becomes a public/stable
attention ABI, default scheduler, or established swarm-intelligence mechanism
from this pilot. The finite trusted-host runtime and reference authority adapter
still require separate fault testing and are not production custody or general
exactly-once execution guarantees.
