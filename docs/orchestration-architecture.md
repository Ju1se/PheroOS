# Bounded agent orchestration over the PheroOS ledger

**An L2–L3 governed runtime with an L1-compatible commitment boundary.**

A thin, framework-independent runtime that lets a small number of declared agents
cooperate through authorized artifacts, with every model call and every tool call
admitted, reserved and settled by the existing PheroOS execution ledger.
Implementation base: commit `e664d2e` (the HEAD recorded before this work began).

> Agents propose actions. The trusted runtime validates them. PheroOS admits and
> records execution. Model output never grants authority to itself.

This document covers authority, state, accounting, recovery and the extension
boundaries. It describes a trusted single-machine serial host. It is not a claim
of adversarial process isolation, of statistical optimality, or of superiority
over any other framework.

## 1. Modules and the dependency boundary

| Module | Role |
| --- | --- |
| `src/pheroos_interaction/*` | pure policy, unchanged except the commitment equality seam (§7) |
| `runner/session.py` | base ledger; gained four seams: `_reserve` (a contract-parameterised reservation body), `_reservation_request` (request-level admission, re-run at dispatch), `_prompt_contract`/`_prompt_settles` (per-call prompt-usage rules) and `_record_artifact` (a publication tail shared with derived artifacts) |
| `runner/platform.py` | work queue, budgets, decomposition; `decompose` split into a transaction wrapper and a `_decompose(db, ...)` body so a composite admission can share one transaction |
| `runner/contracts.py` | validated records and a bounded finite-JSON schema subset |
| `runner/tools.py` | the allowlisted read-only tool registry and fixture store |
| `runner/anthropic.py` | the Anthropic Messages adapter, the fake transport and the model-script format |
| `src/pheroos_interaction/{sequential,commitment,leases}.py`, `runner/policies.py` | the pure L0–L3 colony mechanisms |
| `runner/runtime_policies.py` | the colony policy plane: an adapter over the existing mechanisms, and the runtime's only door to L1–L3 |
| `runner/orchestration.py` | `OrchestrationMixin` + `PlatformMixin` + `Session`: a domain extension of the platform ledger, not a layer beneath it |
| `runner/runtime.py` | the bounded step loop, metrics and the host entry points `start_run`/`resume_run` |
| `runner/audit.py` | read-only offline replay |
| `runner/cli.py` | `orchestrate`, `orchestrate-resume`, `orchestrate-replay` |

The layering is: the agent runtime generates behaviour, the platform ledger
constrains it, and the colony policy plane regulates *collective* behaviour — who
runs now, for how long, and which candidate commits. The plane is pure, so it sits
between the runtime and the ledger in the decision sense, not as a caller of it.

`src/pheroos_interaction` imports no runner module. Everything is standard
library only; the Anthropic adapter uses `urllib` with retries and redirects
disabled, and no provider client is constructed unless an agent declares that
provider. Source identity covers every new module.

## 2. Authority

Authority exists only in host declarations recorded in the ledger.

**Declarations.** `OrchestrationSession.create(path, spec=...)` validates a
workflow spec and writes one row per task into `orchestration_tasks_v1`: the
agents ELIGIBLE to execute it, its allowlisted tools, the producers it may
read (`reads` ⊆ `dependencies`), its output schema, and explicit
`model_steps`/`tool_calls`/`rejections`/`calls`/`tokens` limits. A task writes
`agent: "x"` for one eligible agent or `agents: [...]` for several; the canonical
record is always the list, so nothing downstream can assume a single agent.
Where several are eligible, *which one claims is the allocation decision* (§7), the
claiming agent owns the context and the frozen request, and its tools must lie
within the capability every eligible agent shares. Tasks become
platform work; the `host` identity is reserved and may hold no model config.

**Two durable checkpoints.** `_reservation_request` runs inside the reservation
transaction *and again at dispatch*. It verifies that the call id is exactly the
logical operation key of its own binding, that the binding carries the current
spec digest and task version, that a model call offers only the task's tools plus
the reserved actions, that the frozen request offers exactly those tools, that a
tool call names a declared tool and is bound to a settled model receipt of this
task by digest, that step and tool-call limits are not exhausted, and that every
bound input is still an authorized artifact with an unchanged digest and version.
A context cached between reservation and dispatch therefore retains no revoked
authority; a host task is refused any reservation at all.

**Proposals are data.** `contracts.parse_proposal` accepts exactly one `tool_use`
block and validates its input against a closed schema (`additionalProperties:
false` everywhere, bounded strings, arrays and numbers, exact integers). No
action, several actions, a truncated response, an unknown or unpermitted name, or
a nonconforming input is a `ContractError`: recorded as a rejection that consumes
a model step and a rejection slot, never executed. There is no field through
which a proposal can name an identity, a permission, a budget or a path — and the
`propose_children` fields that *look* like capabilities are narrowing requests
checked against the parent (§6).

**What an agent sees.** The host builds the context; the agent's tools receive a
resolver limited to that task's authorized artifacts. No agent code and no model
output reaches a `Session`, the audit API, a database handle, credentials, or the
filesystem. A reader tool is scoped at registration to an explicit list of
fixtures and its input schema is the enum of exactly those names, so one agent
cannot read a fixture another task's checker uses as its answer key. Fixture
reads resolve only declared names, refuse any symlinked path component, refuse
anything but a regular file inside the root, and verify the declared size and
SHA-256 before returning bytes. These are trusted-host
application boundaries, not a claim of adversarial isolation.

## 3. State

One SQLite ledger. Existing tables are untouched; new tables are versioned:

| Table | Content |
| --- | --- |
| `orchestration_v1` | the frozen spec, its digest, the template and validator versions |
| `orchestration_tasks_v1` | per-task capability declaration, kind, agent, parent, origin |
| `orchestration_artifacts_v1` | per artifact: `kind` (`output` \| `result`) and lineage |
| `orchestration_accounting_v1` | per call: contract, declared prompt bound, reported usage, violation |
| `orchestration_decisions_v1` | one row per validated model receipt: the record of consumption |

**Four distinct records.** A *received observation* is a settled call receipt. A
*published intermediate artifact* is an `output` derived from a validated
`submit_output` proposal — visible to an authorized reviewer, not an acceptance.
An *acceptance decision* is the host applying the declared rule to bound
evidence. A *final task result* is a `result` artifact carrying the candidate
reference and digest, the checker receipt evidence and the decision provenance.
Publication is never a certificate of semantic correctness; success means the
declared finite checker passed on that exact candidate digest.

**Receipt shapes keep the legacy paths out.** Model receipts store the extracted
message under `message`; tool receipts store `{"ok": bool, ...}` under `result`.
Neither carries `artifact`, so `Session._publish`, `publish_received` and
`propose` structurally refuse them, and `OrchestrationSession` additionally
refuses `publish_received` and `commit` for orchestration work. The only
publication path is `publish_derived`, which inside one transaction re-parses the
proposal from the receipt, requires the value to equal it, refuses any work with
a reserved or dispatched call, writes the lineage row and then enters the shared
`_record_artifact` tail.

**Logical operation keys.** `orch:sha256([run, task, version, kind, step])` with
`kind ∈ {model, tool}`; an attempt component is appended only after a known
pre-dispatch abandonment. `Session._reserve` rejects an existing key whose
request, usage bound or contract differs, so a changed request for an existing
operation is refused rather than treated as a new one.

**Step loop.** `admit task → claim → build authorized context → freeze request →
reserve → dispatch → settle receipt → validate proposal → admit requested
transition → publish output or continue`. One sweep performs at most one model or
tool call per task, so no visible step hides an unmetered loop. Position is
reconciled from rows and decisions: an unresolved dispatch blocks the task, a
reserved row is released as abandoned, a settled model receipt without a decision
row is the pending proposal, and the next step index is one past the highest
recorded step. Nothing with an external effect runs inside a transaction: model
calls, tool execution and the checker all happen strictly between `dispatch` and
`receive`.

**Context.** The brief carries the instructions, the resolved authorized inputs
with their refs and digests, and the remaining step/tool/rejection counters. The
conversation is rebuilt from receipts: each consumed step contributes its
assistant content and the matching `tool_result`, and a rejection contributes an
`is_error` tool result carrying the recorded reason. Every part is a function of
rows with a lower row id than the call, which is what makes replay exact. A
parent's declaration is never mutated; children it admitted become readable
through a derived rule filtered by the admission step, so an earlier step's
context stays reconstructible.

**Bounds.** Per task: `model_steps`, `tool_calls`, `rejections` and the platform
`calls`/`tokens` caps (which also count abandoned attempts). Per run: `max_calls`,
`token_cap`, `context_bytes`, `artifact_bytes`, `max_work_items`, `max_children`,
`max_depth`, `max_platform_operations`. All counts derive from durable rows, so a
restart resets nothing, and a rejected proposal plus its correction step consume
explicit limits.

## 4. Accounting

`exact_v1` is untouched: `Session.reserve` still records it, and every historical
record keeps the equality rule and is never reinterpreted.

The Messages API does not accept a predeclared prompt count, so model calls use
the explicitly versioned **`bounded_v2`** contract, recorded per call:

- the reservation is the host's declared `prompt_token_bound + max_new_tokens`,
  checked against the same work and run caps as before (conservative);
- the runtime refuses to send a request whose serialized bytes plus the declared
  `prompt_overhead_tokens` exceed the bound;
- settlement accepts reported prompt usage at or below the bound, where reported
  prompt usage is `input_tokens + cache_creation_input_tokens +
  cache_read_input_tokens`; `calls.actual` records the reported total;
- a report above the bound is not settled. `record_accounting_violation` writes
  the report and an event in its own transaction and the call stays `dispatched`;
- the reported usage is written in the settlement transaction itself, so a crash
  cannot leave a settled receipt without its accounting record and make a clean
  run audit as tampered. Usage members the API reports that are not prompt
  tokens (`service_tier`, `cache_creation`, `server_tool_use`) are copied into
  the receipt and never added to the prompt sum; an unrecognized member is
  refused, because an ignored one could hide prompt tokens.

Declared, not measured: the byte-to-token assumption and the overhead are
parameters of the spec, and the provider renders its own prompt, so they bound
the ledger's reservation, not the provider's tokenizer. After a violation the
token cap no longer bounds what that call may be billed. Cache writes are billed
above the base input rate, so a token count is not a cost bound — which is why
`cache_control`, streaming, thinking, images and other unsupported modes are
refused at freeze rather than translated.

## 5. Recovery

| Crash point | Ledger state on restart | Continuation |
| --- | --- | --- |
| before dispatch | `reserved`, lease expired | abandoned on recovery; next attempt uses an attempt-indexed key; the abandoned row remains and counts against the cap; nothing was sent |
| after dispatch | `dispatched` | blocked unknown, never re-sent; a late `receive` may still settle it, after which the receipt is consumed without new inference |
| after settlement | `received`, no decision row | the proposal is re-derived and consumed; no inference |
| after tool admission | tool call settled, decision row present | the tool is not executed again |
| after child admission | children present, decision row present | no duplicate children; ids are derived and `decompose` refuses duplicates |
| before publication | validated proposal, no artifact | the derived artifact is published; no new call |

Lease fencing, cancellation, publication permissions and the byte-rejected-receipt
rule all keep their existing behaviour. `resume_run` continues only legally
executable unfinished work and resets no budget; it is not a replay and not a new
experiment. Outcomes are distinct: `success`, `abstained`, `dependency_failed`,
`rejected`, `abstained`, `budget_exhausted`, `cancelled`, `blocked_unknown` and
`error`. A run whose tasks all completed but whose declared acceptance rule rejected
the candidate is `rejected`, not `success`: reporting it as success would be a false
success.
An empty ready queue is not success: `blocked_work()` reports any non-terminal
task whose dependency ended without an artifact, which terminates the run as
`dependency_failed` instead of polling, and fabricates nothing.

## 6. Decomposition

Disabled unless a task declares it. The model's `propose_children` output is an
ordinary recorded model operation; a deterministic host step admits it. Inside
one transaction the host derives child ids from the parent id and the proposed
names, checks that each child narrows the parent (same agent, tools ⊆ parent
tools, reads ⊆ parent reads ∪ siblings, `model_steps`/`tool_calls`/`rejections`
≤ the parent's), checks that the parent retains its declared join reserve of
calls, tokens AND model steps, and
then calls the existing `_decompose`, which validates the full dependency graph,
the cumulative child/depth/work limits and the budget transfer. Any failure
leaves no child, no transfer and no consumed receipt, and is recorded as a
rejection. At most one decomposition per task version; there is no replanning
loop. Scoped-inspection inheritance of source, tool, arguments and readers is
untouched — orchestration tasks are not inspections and switch to no undeclared
source.

## 7. The colony policy plane

The runtime is the state machine for *how an agent step executes*. The colony layer
answers three questions and no others: who executes now, how long the lease runs, and
which of several competing candidates is committed.

`runner/runtime_policies.py` holds the plane — named apart from the existing
`runner/policies.py` claim rules, which it adapts rather than reimplements. The
runtime owns one `RuntimePolicies` and imports no colony mechanism itself, so a
baseline arm and a colony arm differ in the policy object alone with model, tools,
context, budgets, task graph, provider and artifact semantics held constant. The arm
is declared in the frozen spec, so it is part of the spec digest and the run's
identity: a ledger cannot be continued under a swapped policy config.

| Slot | Baseline | Colony | State |
| --- | --- | --- | --- |
| Allocation (L2) | `FIFOAllocation` | `ThresholdAllocation`, `ResponseThresholdAllocation` | active |
| Lease (L3) | `FixedLease` | `EvaporationLease` | active |
| Commitment (L1) | `MinLossCommitment` | `OptimalStoppingCommitment`, `CrossInhibitionCommitment` | defined, not active |

**L2, allocation.** Each sweep advances exactly one task:
`ready_work(agent) → policy → chosen work id or no claim → Runtime.step(work_id)`.

The capacity model is **declared, never derived from run state**, and it is
workflow-level rather than per-agent:

```json
"capacity": {"latency_cost": 1.0, "service_time": 1.0,
             "workers": {"expensive": {"cost": 6.0}, "cheap": {"cost": 1.0}}}
```

Only *primitives* are declared. A worker declares its `cost` and nothing else;
`cheapest_cost` and `cheaper_workers` are **derived** by the policy plane. Declaring
them per agent, as an earlier draft did, let two workers contradict each other about
who was cheapest — a spec could assert `cheaper_workers: 0` for both. The derivation
reads the frozen declaration and nothing else: not who is idle, not who is online,
not who claimed last.

`service_time` is **one shared scalar, not a per-worker field**. The incumbent
`pick_threshold`/`pick_response` mechanism accepts a single service time, so
declaring one per worker would force an unjustified aggregation (whose time? the
mean? the harmonic mean?) and would introduce a new scheduling model under the old
name. Heterogeneous service rates need their own mechanism; until one exists the
declaration cannot express them.

**The decision locus is a task's eligible set, not the workforce.** `cheapest_cost`
and `cheaper_workers` are derived per candidate task from the agents that may legally
execute *that* task. If agent A is the only eligible executor, a cheaper agent B is
not cheaper capacity for it, and A claims. Degeneracy is judged the same way: a
threshold or response allocation is refused unless at least one task's eligible
agents differ in declared cost. A cost spread no task can use would be FIFO in
disguise.

A consequence worth stating plainly: **for any declaration that validates, the
deferral deadlock is unreachable.** An agent defers only when a cheaper agent is
eligible for the same task, and that cheaper agent is then the cheapest of that set,
so it claims. The runtime keeps a reason for the stall as a net, and a test asserts
the unreachability rather than pretending the branch is exercised.

**The decision object is the pair `(agent, work)`, not `work`.** One task can sit in
several workers' ready queues at once, so the queues are never deduplicated by work
id — doing so would erase the second worker's legal opportunity, which is exactly
what a shared-capacity workload exists to expose. Each ready row carries its own
task's eligible set, so every row is weighed against the agents that may execute it.

**Worker-enumeration order is workload identity.** The serial host consults workers in
the order the spec *declares* them (`contracts.worker_order`). Which worker is offered
a shared task first decides who claims it under an arm that never defers, so a silent
reordering would change an experimental condition without changing the arm. `agents`
is a JSON list and canonicalization sorts only object keys, so the order is already
inside the spec digest.

**What the "backlog" actually counts.** The stimulus handed to L2 is the number of
*ready, non-terminal eligible tasks*, not unserved work. A task whose model call has
settled but whose next step has not been consumed is still ready and still counted. It
is an honest measure of outstanding eligible work, not a queue of untouched items, and
the distinction matters when reading any response curve derived from it.

A host finalizer is not a worker. It is a reserved identity with no model
configuration: dependencies ready → deterministic rule → result. It has no price, no
cheaper alternative and no response threshold, so `select_host_work` takes ready
order. That is a domain distinction, not a special case; giving the host a fabricated
cost equal to the cheapest would invent an economic parameter that does not exist.

The graded Hill form needs a declared replayable draw. It is derived from the frozen
seed and spec digest, the acting agent, the candidate task and the ledger's own call
count — all identical at the same decision point on a resume or replay — so nothing
is drawn at random inside the runtime. The draw is keyed to the `(agent, work)` pair
because that pair, not the work alone, is what the policy decides.

**Schema versions.** `orchestration-workflow-v1` declared one executor per task
(`"agent"`) and recorded it in a durable `orchestration_tasks_v1` table with an
`agent` column. `orchestration-workflow-v2` declares the eligible set (`"agents"`) and
records it in `orchestration_tasks_v2`. The split is enforced, not advisory:

```text
start_run / resume_run / Runtime.run / Runtime.step   v2 only
offline replay                                        v1 and v2
```

A v1 ledger was written and run under single-executor semantics down to its table
shape, and nothing can verify such a record was normalized to today's form. Rather
than scatter `task.get("agents", [task["agent"]])` through the runtime and hope,
execution refuses it at the boundary. **v1 is historical audit semantics; v2 is
executable semantics.**

**L3, lease TTL.** `EvaporationLease` minimizes `(1−F(τ))·C_dup + τ·p_fail·c_t` over
the declared support. The sample is frozen in the workflow spec and never read from
live history: scanning recent runs at execution time would make the same workflow
yield a different TTL tomorrow and destroy replay. Under the ledger's never-retry rule
the declared durations must be claim-to-dispatch lead times, not full model response
times: the TTL bounds no stall time and cannot resolve a call already dispatched.

**L1, commitment — defined, not active.** L1 answers *candidate commitment*: given
proposals carrying declared losses, publish one, keep waiting, or abstain. Its home is
`PlatformSession.commit(rule=...)`.

There is no arbitration locus in orchestration today. Every task declares one agent,
the platform is created with `max_candidates` of one, and `OrchestrationSession.commit`
refuses orchestration work outright. So the plane exposes `commitment_rule(...)`, it is
validated against a platform session with genuinely competing candidates, and the
runtime has no entry point for it. No candidate contest was manufactured to give it a
caller.

Host acceptance is a different question and does not go through it. That step is a
*verification rule*: a checker receipt bound to the exact candidate digest decides
`accepted`, and the result publishes through the derived transition. The ordering is

    candidate proposals → L1 selection → deterministic verifier
                        → host acceptance rule → final artifact

**L1 controls commitment among admissible candidate states; it does not override
application truth conditions.** A parametrized test drives a failing checker under
every commitment policy and acceptance stays false.

**L0 stays on its own branch.** The sequential tree asks "I have several declared
independent sources — is the next observation worth buying?" An agent model step is
open-ended generation, not a binary observation from a channel with a calibrated
`q`/`rho`; treating the n-th inference as a measurement channel would fabricate an
uncalibrated statistical model. The evidence-acquisition path keeps `plan_sequential`
and the agent path does not use it.

## 8. Commitment seams fixed in this round

- `optimal_stopping_rule` returns `None` (abstain) when the programme would
  publish a candidate whose loss equals the ledger's abstention loss, because the
  ledger publishes only on strict improvement. The DP value computation is
  unchanged and the recall branch is untouched: a candidate above the abstention
  loss still waits when waiting beats abstaining.
- `worker.waiting_rule` refuses a waiting configuration unless the caller
  declares a bounded deadline, a positive `tick_seconds`, and the agents whose
  candidates may still arrive. Its tick is `floor((now - first recorded wait) /
  tick_seconds)`, read from the clock stamps that `platform.waited` decisions now
  carry, so a tight polling loop advances no decision clock at all. It returns
  `None` — selecting the default minimum-loss rule — once every declared source
  has already proposed, because waiting for an arrival that cannot come would be
  fictitious. The arrival probability remains a declared per-tick assumption of
  the caller, not a calibrated rate. The default commit rule remains minimum loss
  with strict improvement.

## 9. Offline replay and observability

`audit.replay_run(path)` opens the ledger read-only (`mode=ro` with
`query_only`), never instantiating a `Session`. It re-validates the spec and its
digest, and for every model call rebuilds the request from rows recorded before
it — the same builder the runtime uses, so the two cannot drift — and compares
both the request and its binding byte for byte. It re-checks every call id
against its logical key, every tool call against its arguments digest and bound
model receipt, every decision against a fresh parse of its receipt, every
artifact against its lineage and its validated proposal, every `result` against a
fresh application of the declared rule, and every accounting row against its
contract. It executes no tool, builds no transport and writes nothing: the
reported new model and tool calls are always zero. A mismatch is `FAIL`; a
differing executable source identity is `LIMITED`; only a clean run is `PASS`.

Per-run metrics: model and tool calls, known tokens, outstanding reservations,
unknown calls and tokens, accounting violations, proposal rejections, decisions,
reuse events, artifacts, blocked dependencies, sweeps used against the bound.
Measurements taken against the fake transport are not evidence of model quality,
cost saving or optimality.

## 10. Extension boundaries

Another provider is another freeze/extract/transport triple that keeps
credentials at the transport boundary and the frozen request exact; it changes no
ledger semantics. Another tool is a registered read-only, schema-checked,
byte-bounded function that never receives a session. A future framework driver
must defer governed-call status, budgets and publication authority to this
ledger rather than keep competing execution truth.

Out of scope by contract: restoring deleted OS frameworks or pheromone fields,
distributed execution, arbitrary code execution, a message broker, autonomous
replanning loops, automatic paid experiments, and framework comparisons.
