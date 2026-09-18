# PheroOS

A local binary inspection tool: it decides whether to inspect from explicitly declared model assumptions and loss configuration, and fixes the action for each outcome before execution.
It keeps only the pure policy, source permissions, durable reservations, call caps, cancellation, never-retry for unknowns, and plan/receipt replay.
An optional bounded platform layer can enumerate and decompose work, handle leases, propose candidates, and commit; the default inspection command still performs one-step inspection.
The colony control layer composes a multi-step inspection tree, commitment rules, allocation thresholds, and lease TTLs into one bounded worker; the default command does not enable it.
An opt-in agent orchestration layer runs bounded model and tool steps for a few declared agents over the same ledger, with artifact-based collaboration, crash recovery and offline audit replay; it has its own commands and is never enabled implicitly.

## Install and run

Requires Python 3.12+; the runtime depends only on the Python standard library.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pheroos-interaction inspect \
  --config experiments/current/inspection-example/request.json \
  --source experiments/current/inspection-example/source \
  --output output/inspection
pheroos-interaction inspect-replay --run output/inspection
python -m pytest -q
```

The output directory must be new. `source.json` declares scope, version, readers, tool, and content digest; `value.json` is read only after the decision to buy,
a durable reservation, and a passed permission check. The example reads only local files and touches no model or cost ledger.

## Core files

- `src/pheroos_interaction/inspection.py`: cost early exit, conservative corner, six branch losses.
- `src/pheroos_interaction/records.py`: lease and error types.
- `runner/inspection.py`: source reading, frozen plan, receipt verification, and read-only replay.
- `runner/session.py`, `evidence.py`, `driver.py`: execution constraints and tool dispatch.
- `runner/identity.py`, `cli.py`: complete source identity and the two command entry points.
- `runner/platform.py`: optional work queue, budget inheritance, and atomic candidate commit.
- `runner/policies.py`, `worker.py`: deterministic claim rules and a bounded worker with no durable state.
- `runner/provider.py`: injected transport adapter, disabled by default, verified only with mocks.
- `src/pheroos_interaction/sequential.py`: finite-horizon inspection tree (K=1 is `plan_inspection`), garbling matrix, and in-box certificate.
- `src/pheroos_interaction/commitment.py`: cross-inhibition commit rule and optimal stopping with recall.
- `src/pheroos_interaction/leases.py`: one-dimensional loss minimization for the lease TTL.
- `runner/colony.py`: the bounded colony worker composing L0–L3.
- `runner/contracts.py`, `tools.py`, `anthropic.py`, `orchestration.py`, `runtime.py`, `audit.py`: the opt-in agent orchestration layer.

The installation contains only `pheroos_interaction` and `pheroos_interaction.runner`.
Old experiments, old policies, and research commands have been deleted; no real model service, credentials, or provider CLI is configured. Historical raw data stays local under
`research-data/results/` and is neither packaged nor uploaded; the current program no longer replays old experiments.
Saved local inspection records can use `inspect-replay --historical --run ...`, which explicitly allows source identity to differ
while still verifying the frozen plan, the original receipt, and the execution record.

## Shared execution ledger

`CoordinationSession` supports several declared agents, work with dependencies, and reads after publication; identities are supplied by the trusted host.
The work's role list decides who may execute; the intersection of the source's and the inspection's two `readers` layers decides who may run the check, publish, and read artifacts.
Dependencies only check that an artifact exists; a consumer's read must still pass the current version and permission checks.

- `publish_received(agent, call_id, verify=...)` reuses a settled receipt; when the lease has expired it atomically re-claims and publishes
  without calling the tool again or consuming cost or call quota. Cancellation, a source change, missing permission, another holder's valid lease,
  or an unknown dispatch on the same work all block a new publication. Once the same receipt is published, a repeated call returns the original reference while permission still holds.
- `artifacts(agent)` enumerates only the currently visible published artifact references, work, versions, and observation keys;
  `read_artifact(agent, ref)` returns a JSON copy, or `None` when invisible or expired.
  A cancelled session or an undeclared reader raises. Neither recovers a lease, runs a tool, or writes an event.

`verify` must be a pure local check; a rejection or exception rolls back this claim and publication, and SQLite cannot roll back a verifier's external side effects.
The local `inspect` already uses this publication entry; an interruption after settlement keeps the original receipt and stops, with no automatic re-run.
`receive` is not bound by the lease, so a late receipt can still settle; an unknown dispatch has no timeout release.
`call`, `snapshot`, and replay are host audit entries, not an agent's content-read interface.

`max_control_operations` caps the total of successful lease claims and accepted source updates, including the re-claim during publication recovery
and repeated submission of the same source update. The existing durable events are the count, so reopening the session does not reset the quota.
When exhausted it raises `BudgetExceeded` and the transaction's state and events all roll back; a failed verification also consumes no quota.
Reads, unclaimed work, and idempotent returns of already-published receipts consume no quota. Call reservation, dispatch, and settlement are separately bound by
`max_calls` and the token caps; expired-lease recovery, cancellation, and settlement of late receipts remain possible after the control quota is exhausted,
and a valid lease can still publish. An expired receipt needs a new lease to publish, so it needs remaining control quota.
When a source update is rejected the original declaration stays, and the host can still cancel the session.
Inspection replay with matching source identity verifies the control count; a historical replay that explicitly allows source differences does not apply the new limit retroactively to old records.

These are execution and access constraints, not evidence of policy benefit. Platform enumeration is in the next section; model calls stay off by default.

## Optional platform layer

`PlatformSession` reuses `Session`'s call, receipt, and cancellation ledger; when source permissions are needed, compose
`class ScopedPlatform(PlatformMixin, CoordinationSession)`. Create a new platform ledger explicitly; an old session
database cannot be used directly as a platform database. The existing inspection CLI does not enable these transitions.

| API | Behavior and boundaries |
| --- | --- |
| `ready_work(agent)` | Read-only: returns id, version, age, depth, parent, and remaining calls/tokens; filters by role, current source/readers, dependencies, unknown dispatches, and no-entry. Expired leases are only projected as claimable; actual recovery happens in the claim transaction. |
| `decompose(lease, children)` | Transfers calls/tokens from the parent's remaining budget; atomically creates the children, releases the parent lease, and adds dependencies. Rejects open reservations, unknown dispatches, cycles in the full graph, or exceeded limits; `parent_depends=False` is rejected. |
| `release` / `renew` | Releases undispatched reservations; with an unknown dispatch the work becomes uncertain. Renewal never shortens the existing expiry and keeps the epoch. |
| `mark_no_entry(work_id, until, reason)` | The host's time-bounded scheduling hint; blocks enumeration and new claims, while existing receipts can still recover through `publish_received`. It does not modify call state. |
| `propose(lease, call_id, certified_loss)` | Accepts only a settled receipt for the current work/version; records the current proposer and artifact digest. The same declaration is idempotent, a conflict is rejected. The loss is the caller's declaration; the platform does not prove its calibration or correctness. |
| `candidates(work_id, agent=...)` | Returns current candidate metadata, checking the caller's current access; omitting agent is the trusted-host audit interface, not an agent read interface. |
| `commit(..., verify, abstain_loss, rule=None)` | Default: minimum loss, ties by call_id; the best loss must be strictly below the abstention loss. The decision, the recovery claim, and the publication inside the shared `publish_received` transaction all commit or all roll back. The publisher defaults to the winning proposer. |
| `work_calls(lease)` / `abstain(lease, reason=...)` | The current lease reads the same work's receipts for recovery; abstention terminates the work and releases undispatched reservations, but cannot terminate an unknown dispatch. |

A custom pure local `rule(candidates, abstain_loss)` returns a candidate call_id, `None` (terminal abstention), or
`{"decision": "wait"}` (non-terminal wait). No candidates returns `no_candidate`. An existing terminal commit returns the recorded decision;
it neither re-decides with a changed threshold nor runs a new call. External side effects of `verify` and `rule` cannot be rolled back by SQLite, so they must stay pure and local.
A terminal abstention has no artifact; a parent or later work depending on it stays blocked, success is not fabricated and reads are not retried, and the host can cancel the session.

The `platform={...}` creation argument can declare `budgets={work_id: {"calls": n, "tokens": n}}`,
`max_children` (cumulative per parent, default 8), `max_depth` (3), `max_candidates` (per work, 8),
`max_work_items` (1024), and `max_platform_operations` (1024). A work cap cannot exceed the run cap; an unspecified
root work uses the run cap as its bound while always remaining under the global cap. Caps are not returned after decomposition.
calls follow Session semantics and count established reservations, including later abandoned ones; tokens count the reserved bound for unsettled calls
and actual usage for settled calls. The check runs in one SQLite transaction, so two writers cannot overspend first and then try to repair.

The platform operation budget counts claim, renew, decompose, no-entry, propose, commit/abstain, and the WAIT state change;
a terminal decision or an idempotent re-read of the same proposal is not charged. release only drains claimed state and still runs after the cap is exhausted,
bounded by the number of admitted claims. The original CoordinationSession claim/source-update control budget continues to apply.
When composed with scoped inspection, children inherit the same source, tool, arguments, and readers and consume the existing index capacity;
this interface does not support switching to another undeclared source during decomposition.

### Claim rules and the worker

`pick_fifo` follows enumeration order; `pick_by_depth` prefers deeper, then older within a level. `pick_threshold` compares the added fee with the
expected waiting loss only under the declared queueing model: with equal cost or no cheaper worker it reduces to FIFO, otherwise
it requires the waiting loss to be strictly greater than the incremental fee. It is an evaluable heuristic, not a proven-optimal scheduler.

`run_worker` does one bounded sweep, visiting each work id at most once; the default bound is the initial ready count, and an explicit
`max_items` can cover work unlocked later. The planner may return `{"purchase": False}` to abstain terminally; the purchase branch
uses the local SessionDriver interface. Existing matching receipts or candidates are recovered from the ledger, so a worker restart does not buy twice.
WAIT keeps the candidates and releases the lease; transport exceptions are classified by the ledger's true state as unknown, settled rejection, or undispatched failure.
The worker implements no LLM decomposition, message passing, or statistical optimality claim.

### Provider adapter boundary

`ProviderDriver` is disabled by default; enabling requires an explicit bool from the caller or `PHEROOS_PROVIDER=1`, plus an injected transport and
`extract(response) -> (artifact_dict, prompt_tokens, completion_tokens)`. There is currently no network transport,
real provider extractor, credential reading, or provider CLI. The enable flag is not a cost authorization.

The full request (with `max_tokens` matching the reservation) is copied and frozen before reserve, and the transport receives the same request content that dispatch returns.
This transport contract uses `max_tokens`; if a real API differs it needs an explicit mapping and instrument
check, and no claim is made that a generic extractor alone fits every provider. Using it with the worker needs an explicit request/token adapter.
The reported prompt tokens must equal the declaration exactly and completion must not exceed the reservation. Transport, extraction, or token-contract failures after dispatch
stay dispatched/unknown with no retry; a receipt that only exceeds the byte bound with valid usage is still settled by the existing Session rule as
`response_rejected`. The ledger check cannot guarantee an external service's actual charge or output bound on its behalf, and it derives no idempotency from JSON fields.

Tests use a local fake transport and cover reopening the ledger, failure recovery, concurrent budget admission, permissions, and cancellation.
This is not a comparison with LangGraph, ADK, or CrewAI; those systems must run the same fault scenarios separately to serve as a comparison.

## Colony control layer

Each of the four insect mechanisms maps to one layer, and every threshold in each layer is derived from the declared loss vector `(ℓ_A, ℓ_R, ℓ_0, c, c_t)`
without new tuning constants; apart from declared draws everything is deterministic and replayable from the ledger.

| Layer | Mechanism | API | Behavior and boundaries |
| --- | --- | --- | --- |
| L0 | Scout inspection → sequential test | `plan_sequential(assumptions, losses, query_cost, horizon)` | Backward induction in joint coordinates at the corner `(q_low, rho_high)`; `horizon=1` equals `plan_inspection` field for field. `certificate` is a rigorous upper bound on the fixed tree's expected risk within the declared box (exact at the corners for K=1). `apply_sequential` walks the frozen tree; unknown means abstain, with no replanning. Each depth must be a distinct declared source. |
| L1 | Stop signals → commitment | `cross_inhibition_rule(CommitmentConfig)`, `optimal_stopping_rule(...)` | Pure local rules for `commit(rule=...)`. ODE version: candidate value v_i=ℓ_0/ℓ̂_i, σ=σ*(v̄), reads only candidate metadata, zero bytes, with bounded integration work (`MAX_STEPS`, `MAX_ITERATIONS`) because the rule runs inside commit's SQLite transaction; deadlock is a terminal abstention; a single candidate degenerates to first-publish-wins when v > v̄ (its loss plus latency strictly below the abstention loss). The DP version may return WAIT. Neither proves calibration or optimality. |
| L2 | Tremble dance → allocation | `pick_threshold`, `pick_response(..., exponent, draw)` | The stimulus is backlog drain time and the threshold is θ_w=Δκ_w/c_t. `exponent=None` is the deterministic step; the Hill form requires a replayable `draw` from the caller. Exactly FIFO with homogeneous costs. A heuristic, not an optimal scheduler. |
| L3 | Pheromone evaporation → authority | `lease_ttl(stage_durations, p_fail, per_tick_cost, false_expiry_cost)` | Minimizes (1−F(τ))·C_dup + τ·p_fail·c_t over the positive part of the empirical support and candidates (0 is not a feasible TTL; a sample with no positive duration raises). Under today's semantics the input is claim-to-dispatch lead time and the TTL bounds no stall. Renewal never shortens expiry. |
| — | worker | `run_colony(session, agent, driver=, planner=, verify=, policy=, rule=, lease_seconds=, wait_hold_seconds=)` | One bounded sweep. The planner returns `{'purchase': False}` (optionally with `abstain_loss` and `rule`, used to commit candidates that already exist) or `{'plan', 'reads', 'outcome', 'abstain_loss', 'rule'}`. The call id is `colony:sha256([work, version, tree_sha256, depth])` and the arguments bind the tree digest; after a reservation abandoned before dispatch (a known non-dispatch, not an unknown) the next attempt at that depth appends the attempt count, and every attempt counts against the work's call cap. Existing candidates are committed before the purchase decision; existing receipts are reused, a mismatch refuses another read, a rejected response forbids a fresh read, unknowns are never retried; a tree whose worst-case remaining reads exceed the work's remaining calls is refused before anything is bought; a root stop with no read abstains as `plan_stop:<action>`. |

`certified_loss` is the leaf's conditional expected loss `stop_risk / (mass_h + mass_n)` and is the caller's declaration. With `wait_hold_seconds`
enabled, WAIT writes a no-entry mark, which is a host scheduling hint. Revision 10 of the reference implementation labels the cross-inhibition ODE as analysis-only
and uses optimal stopping with recall as the rule for a centralized ledger; here both are explicit configuration choices.
This layer adds no LLM decomposition, message channels, or automatic paid runs, claims no statistical optimality, and is not a framework-comparison conclusion.

## Agent orchestration layer

An **L2–L3 governed runtime with an L1-compatible commitment boundary**: a thin, framework-independent runtime that lets a few declared agents cooperate through authorized artifacts, with every model
call and every tool call admitted, reserved and settled by the same ledger. It is opt-in: the `inspect` command never creates an
orchestration session. See [docs/orchestration-architecture.md](docs/orchestration-architecture.md) for authority, state,
accounting, recovery and the extension boundaries, and
[docs/orchestration-verification.md](docs/orchestration-verification.md) for what was actually run, what was observed, the
defects found during verification, and what was not tested.

> Agents propose actions. The trusted runtime validates them. PheroOS admits and records execution. Model output never grants
> authority to itself.

```sh
pheroos-interaction orchestrate --workflow examples/orchestration/workflow.json \
  --script examples/orchestration/script.json --output output/orchestration
pheroos-interaction orchestrate-replay --run output/orchestration
pheroos-interaction orchestrate-resume --run output/orchestration --script examples/orchestration/script.json
```

`orchestrate` freezes the workflow into a new output directory and runs it to a terminal outcome; `--max-sweeps` overrides the
derived bound. `orchestrate-resume` continues only the unfinished work of a recorded run: budgets are not reset, an unresolved
dispatch is never re-sent, and a settled receipt is consumed rather than repeated. `orchestrate-replay` verifies the record
offline and exits 0 for PASS, 1 for FAIL and 2 for LIMITED. The examples need no credentials and touch no network.

| Module | Responsibility and boundaries |
| --- | --- |
| `runner/contracts.py` | Validated records (agents, tasks, capabilities, limits, fixtures, proposals, outcomes) over a bounded finite-JSON schema subset in which every object is closed. `parse_proposal` accepts exactly one `tool_use` action; anything else is a data-validation failure, never an instruction. |
| `runner/tools.py` | A small allowlisted registry of read-only tools: validated arguments, capability checks, bounded output, deterministic fixture reads guarded against traversal and symlink escape and verified against the declared content digest. Tools receive a resolver for the calling task's authorized artifacts, never a session. |
| `runner/anthropic.py` | One concrete provider adapter for the Anthropic Messages API plus a deterministic fake transport that exercises the identical freeze, extract, proposal, tool and recovery paths. Unsupported modes are refused, not translated; retries and redirects are disabled; credentials are read at the transport boundary only. |
| `runner/orchestration.py` | The ledger extension: per-task capability declarations checked at reservation and dispatch, the `bounded_v2` prompt contract, derived artifacts with lineage, durable decision records, and host-admitted decomposition. |
| `runner/runtime_policies.py` | The colony policy plane and the runtime's only door to L1–L3: allocation (L2), lease (L3) and candidate commitment (L1), each with a baseline and a colony implementation. An adapter over the existing mechanisms, not a reimplementation; every policy is pure. |
| `runner/runtime.py` | The bounded step loop and the host entry points. One call per sweep; state is reconciled from receipts and decisions, never from remembered state. |
| `runner/audit.py` | Offline replay: read-only, rebuilds every frozen request, re-parses proposals, re-applies the host rules, re-checks accounting. Always zero model and tool calls and no mutation. |

The agent runtime generates behaviour, the platform ledger constrains it, and the colony policy plane regulates collective
behaviour. **The runtime actively uses L2–L3 and is architecturally compatible with L1 at real candidate-arbitration
boundaries. L1 is available at the platform candidate-arbitration boundary but is not exercised by the current fixed-DAG
orchestration workflows.** A workflow declares its arm in one optional `policies` block, which is part of the frozen spec and
therefore of the run's identity, and each run records the arm it used — so a baseline and a colony run differ only in the
policy object.

Two honest limits. The L2 capacity model is declared, never inferred from run state: costs are primitive workflow-level facts and
the policy plane derives the cheapest cost and the count of cheaper workers per task, from that task's own eligible set. With one
eligible agent per task there is no cheaper capacity, so the shipped fixed-DAG workflows declare `fifo`; a declaration whose cost
spread no task can use is refused at validation rather than degenerating silently. And host acceptance is a verification rule, not
a commitment: a commitment policy chooses among admissible candidates and can never turn a checker's FAIL into a PASS. L0, the sequential inspection tree, is deliberately
not wired into agent reasoning — see the architecture document for why.

The lifecycle of one step is `admit task -> claim -> build authorized context -> freeze request -> reserve -> dispatch ->
settle receipt -> validate proposal -> admit requested transition -> publish output or continue`. The durable logical operation
key is `orch:sha256([run, task, version, kind, step])`, with an attempt suffix only after a known pre-dispatch abandonment; it
survives lease changes and restarts, and a changed request for an existing key is refused. Outcomes are distinct: `success`,
`rejected`, `abstained`, `dependency_failed`, `budget_exhausted`, `cancelled`, `blocked_unknown` and `error`; a run whose
tasks all completed but whose acceptance rule rejected the candidate is `rejected`, not `success`, and an empty ready queue is not success, and a failed dependency neither polls forever nor fabricates an artifact.

`examples/orchestration/` holds three credential-free configurations: the fixed two-agent DAG (`workflow.json`), the same shape
with different agent names, task ids and checker (`workflow-expected.json`, showing the runtime hardcodes nothing), and the
opt-in decomposition variant (`workflow-decomposition.json`). In each, a producer builds a candidate from a bounded local
dataset, a reviewer reads only permitted artifacts and runs a deterministic checker bound to the exact candidate digest, and a
host task applies the declared acceptance rule and publishes a result carrying the candidate reference, the checker evidence and
the decision provenance.

What this layer does not claim: success means the declared finite checker passed on that exact candidate digest, not that the
answer is semantically correct; an intermediate artifact is available to an authorized reviewer without being accepted; the
`bounded_v2` byte-to-token assumption and the prompt overhead are declared parameters, not measurements, and after a recorded
accounting violation the token cap no longer bounds external billing; different agent identities are not independent evidence and
a model's stated confidence is never a `certified_loss`; offline replay verifies the record, not the world, and never promises
that fresh inference reproduces a prior answer. The Anthropic adapter is implemented and tested offline only, against local fake
transports and a loopback fixture server: no live request was made, and the enable flag is not a spending authorization. This is
not a comparison with LangGraph or any other framework.

## Applicability

Only a fixed prior, symmetric binary measurement, a fixed positive-copy reference, and rectangular parameter ranges are supported; unsupported input is rejected explicitly.
Probability ranges, source description, version, applicability, the three losses, and the query cost must be supplied explicitly.
Passing the format does not mean the real source is independent or the probabilities are calibrated. The query cost is a utility value in the same unit as the error and abstention losses,
not a cost authorization. The default command inspects one step; multi-step trees are used explicitly only inside the colony control layer on distinct declared sources, with call caps declared by configuration.

The applicable scope is a trusted single-machine serial task; there is no general semantic understanding, dependency learning, or malicious-host guarantee. Multi-step inspection happens only on explicitly declared distinct sources and is not general sequential reasoning.
