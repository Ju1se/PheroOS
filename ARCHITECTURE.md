# Architecture

How the system is organized. Rules live in `docs/invariants.md` and are cited here by ID only;
reasons live in `docs/decisions/`; the map and the commands live in `AGENTS.md`.

> **This document contains no "was exercised" / "was verified" claims.** Verification status belongs
> in generated output — `docs/generated/verification-status.md` **(PLANNED — not yet created)** —
> never in hand-written prose. This constraint is self-binding and was earned by measurement: when
> the two predecessor documents were verified claim by claim against code, **every** stale and every
> contradicted claim came from the one that recorded what had been run, and **none** came from the one
> that recorded how the system is organized. A record of execution rots the moment the code moves.
> See `docs/decisions/0001-retire-the-orchestration-documents.md`.

## 1. Scope

A local binary-inspection decision tool on a durable SQLite ledger, with a bounded agent-orchestration
runtime layered over it. Execution is serial by construction: no concurrency, scheduling or
networking-server primitive is imported anywhere in `runner/` or `src/pheroos_interaction/`, and state
lives in one local SQLite file per run. "Trusted single-machine" is a disclaimer of guarantees, not a
property of the code — there is no adversarial-isolation or BFT mechanism to inspect.

## 2. Packages and the dependency boundary

One distribution namespace, `pheroos_interaction`, declared explicitly rather than auto-discovered
(`pyproject.toml:21-25`): `pheroos_interaction` → `src/pheroos_interaction`, and
`pheroos_interaction.runner` → `runner`. `dependencies = []` with `requires-python = ">=3.12"`, so the
runtime is standard library only. There is no top-level `runner` package on the installed path.

```text
src/pheroos_interaction/   6 modules   pure decision policy and record types
                                       inspection · sequential · commitment · leases · records
runner/                   19 modules   local source access, ledger execution, the agent runtime,
                                       the provider adapter, the tool registry, offline replay
```

The dependency arrow is one-way: `runner` imports `pheroos_interaction`, never the reverse (L-9).
`src/pheroos_interaction/` imports only the standard library plus intra-package names.

`runner/identity.py:6-21` computes source identity as a sha256 over every `*.py` reachable through
both installed package roots, raising on a digest conflict between roots, so coverage extends to new
modules automatically rather than by a maintained list.

One console script, `pheroos-interaction` (`pyproject.toml:17-18`), with five subcommands defined at
`runner/cli.py:12-31` — `inspect`, `inspect-replay`, `orchestrate`, `orchestrate-resume`,
`orchestrate-replay`. `experiments/current/inspection-example` holds `request.json` and `source/`,
contains no Python file, and is not an installed package.

## 3. The ledger

One SQLite ledger, opened for writing at a single site (`runner/session.py:43`) and read-only by
`runner/audit.py:45` and `runner/inspection.py:257`. **18 tables, declared by `CREATE TABLE`, with no
`ALTER TABLE` anywhere:**

```text
runner/session.py:99-103        run · work · calls · artifacts · events        (5, unversioned)
runner/platform.py:80-84        platform_*_v1                                  (5)
runner/orchestration.py:74-78   orchestration_v1 · orchestration_tasks_v2      (5)
                                orchestration_artifacts_v1 · _accounting_v1 · _decisions_v1
runner/evidence.py:44-46        coordination_*_v1                              (3)
```

**Of the 13 versioned tables, exactly one carries `_v2`** — `orchestration_tasks_v2` — and twelve
carry `_v1`. `orchestration_tasks_v1` is created nowhere; it exists only as a read-side probe target
in `runner/audit.py:36`. That the suffix is being asked to mean both *schema generation* and
*execution eligibility* is recorded as **F-39** in `docs/findings.md`; it is unresolved, and the tables
must not be touched before G2 settles it.

Every model inference and every tool invocation occupies exactly one ledger call. Its durable key is
`orch:` + sha256 of `[run_id, task_id, version, kind, step]`, with an attempt component appended only
when nonzero (`runner/orchestration.py:36-41`), incremented past abandoned rows by
`runner/runtime.py:344-350`.

A task's position is derived only from durable call rows and decision rows
(`runner/runtime.py:313-340`) — never from in-process state. Each `step()` performs at most one model
or tool call, and the transport invocation sits between `dispatch` and `receive`, **outside any
transaction** (`runner/runtime.py:448-459`).

**Four distinct records.** A received observation, a published intermediate artifact, an acceptance
decision and a final task result are separate rows, not one value reinterpreted. Orchestration
artifacts publish only through `publish_derived` in two kinds, `output` and `result`
(`runner/orchestration.py:28`, `:455-500`); a row in `orchestration_decisions_v1` is written in the
same transaction as an `output`, but not as a `result`.

**The platform layer is partly opt-in and partly not.** Enumeration, cap transfer and candidate
arbitration are reachable only by constructing a `PlatformSession`. Lease acquisition, fencing and
expiry-abandonment are **unconditional base-`Session` machinery**; only lease *renewal* and no-entry
marking are platform additions.

## 4. Task declaration, eligibility and authority

A workflow spec (`runner/contracts.py:511-574`) declares agents, tools, fixtures and tasks. A model
task names its eligible executors as `agent` for one or `agents` for several; `contracts.task_spec`
(`runner/contracts.py:406-450`) canonicalizes a v2 task to `{"agents": [...]}` while a v1 task keeps
`{"agent": ...}` (L-1, L-2).

Two cross-entity rules are enforced at validation: a task's tools must be a subset of the intersection
of every eligible agent's declared capability (`runner/contracts.py:543-545`, L-28), and a threshold or
response allocation requires at least one task whose eligible agents differ in declared cost
(`runner/contracts.py:569-573`, L-8).

`OrchestrationSession.create` writes one row per task into `orchestration_tasks_v2`, whose `agents`
column holds a JSON list produced by `contracts.eligible_agents` (`runner/orchestration.py:75`,
`:84-86`). The table is created unconditionally, with no branch on spec format.

**Allocation is a decision over the `(agent, work)` pair, not over work alone.**
`Runtime._select_work` enumerates workers in declared order and returns that pair
(`runner/runtime.py:118-157`); per-agent ready queues are never deduplicated by work id.
`Runtime.step` refuses an agent outside the task's eligible set and claims with the chosen one
(`runner/runtime.py:280-283`, `:372`). The claimant determines the model config, the authorized inputs
and the `"agent"` field of the frozen request's binding (`runner/runtime.py:282`, `:298`, `:418`,
`:422`).

**Execution is gated to `orchestration-workflow-v2` at four entry points** — `start_run`
(`runner/runtime.py:844`), `resume_run` (`runner/runtime.py:871`), `Runtime.run`
(`runner/runtime.py:657`) and `Runtime.step` (`runner/runtime.py:360`), all
raising unless the format matches (L-3). Offline replay has no such gate and reads both durable task
schemas via `TASK_TABLES` (`runner/audit.py:36`, `:63-73`).

Scoped-inspection inheritance of source, tool, arguments and readers lives in
`runner/platform.py:274-291` behind a `hasattr(self, "_inspection")` guard that only
`CoordinationSession` satisfies, so orchestration decomposition writes no inspection declaration.

## 5. The colony policy plane

Four pure mechanism modules, plus a bounded sweep that composes them, plus one adapter:

```text
src/pheroos_interaction/sequential.py   L0  finite-horizon tree and its certificates
src/pheroos_interaction/commitment.py   L1  cross-inhibition and optimal-stopping rules
runner/policies.py                      L2  pick_fifo · pick_by_depth · pick_threshold · pick_response
src/pheroos_interaction/leases.py       L3  TTL argmin
runner/colony.py                            a bounded sweep composing them over a PlatformSession
runner/runtime_policies.py                  the adapter — the agent runtime's only door to the above
```

`runner/runtime_policies.py` is part of the colony surface and is easy to omit from an enumeration
written before it existed. It defines three slots — allocation (`FIFOAllocation`,
`ThresholdAllocation`, `ResponseThresholdAllocation`), lease (`FixedLease`, `EvaporationLease`) and
commitment (`MinLossCommitment`, `OptimalStoppingCommitment`, `CrossInhibitionCommitment`) — and
`RuntimePolicies` exposes `select_work`, `select_host_work`, `lease_duration` and `commitment_rule`.

`runner/runtime.py` imports no colony mechanism directly (L-9) and calls only `select_work`,
`select_host_work` and `lease_duration` — **two decisions, not three**. `commitment_rule` has no
caller outside tests, and `contracts.POLICY_SLOTS` admits only `allocation` and `lease` in a workflow
spec (R-4).

**Capacity is workflow-level and primitive**: `{latency_cost, service_time, workers: {id: {cost}}}`.
`cheapest_cost` and `cheaper_workers` are derived by the plane, per task, from that task's eligible
set — never declared per agent and never inferred from runtime state (L-8).

The L2 stimulus is the length of the acting agent's ready queue from `PlatformSession.ready_work`,
which lists work that is ready or lease-expired, eligible for that agent, dependency-satisfied, not
dispatched, and not held by a no-entry mark. It counts *ready, non-terminal eligible tasks* — not
unserved work: a task whose model call has settled but whose next step has not been consumed is still
counted.

Host acceptance is a separate path in `runner/runtime.py`: a checker receipt bound to the exact
candidate digest sets `accepted`, and that path never consults a commitment rule (R-8, L-7).

**L0 stays on its own branch.** The sequential tree asks "I have several declared independent sources
— is the next observation worth buying?" An agent model step is open-ended generation, not a binary
observation from a channel with a calibrated `q`/`rho`; treating the n-th inference as a measurement
channel would fabricate an uncalibrated statistical model. The evidence-acquisition path keeps
`plan_sequential`; the agent path does not use it. *(Recovered verbatim from
`docs/history/orchestration-architecture-2026-09-17.md:365-370`, sha256 `2e32c034…`, during the
retirement fold; it had no current home. See F-41.)*

## 6. The provider adapter

`runner/anthropic.py` freezes a Messages API body, POSTs it to `base_url + "/v1/messages"` (default
`https://api.anthropic.com`) with `x-api-key` and `anthropic-version: 2023-06-01`, and refuses a
documented `UNSUPPORTED` field set rather than translating it.

Its HTTP door is a hand-built `OpenerDirector` with an explicit handler allowlist
(`runner/anthropic.py:322-328`). **Redirect following and proxy use are absent by construction, not
switched off** — no `HTTPRedirectHandler` and no `ProxyHandler` is ever added, so there is no flag to
flip back.

`runner/runtime.py:814-821` constructs that transport only when an agent declares the `anthropic`
provider *and* the host sets `PHEROOS_PROVIDER=1` with a key in `ANTHROPIC_API_KEY` (L-21). No
credential, base URL or provider CLI is configured in the repository; every shipped example workflow
declares provider `fake`, and `anthropic.FakeTransport` dispatches on an anchored header line the
runtime writes as the first line of the frozen system prompt.

Fixture reader scope lives on the **workflow-level tool entry**, not on the task:
`tools._build_fixture_read` closes both the input schema and the executor over
`entry["config"]["fixtures"]`, while a task declaration (`runner/contracts.py:427`, `runner/contracts.py:444`) names tools by
string and has no `fixtures` member. Two tasks sharing one `fixture.read` entry share its reader set.

## 7. Offline replay

`audit.replay_run` (`runner/audit.py:205-431`) builds a `Runtime` with an empty transports map and a
registry it never executes, and reports `new_model_calls` and `new_tool_calls` as literal zero. It
emits named checks over: spec digest and template version · per-call identity and authority · model
request and binding rebuild · tool declaration, arguments and receipt binding · decision re-parse ·
artifact lineage and rule re-application · accounting bounds · terminality · decision uniqueness.

Its verdict is one of three (`runner/audit.py:417`): `PASS`, `FAIL`, or `LIMITED` when the executable
source identity differs. `orchestrate` and `orchestrate-resume` exit 0 on `success` and 2 otherwise;
`orchestrate-replay` exits 0 / 1 / 2 for PASS / FAIL / LIMITED (`runner/cli.py:43`, `:49`).

**What replay does not do:** it does not re-derive the allocation decision. The record's internal
consistency is checked; which eligible agent should have claimed is not. That gap is L-11 / L-13 /
L-14, unenforced, closing in G1.

## 8. Recovery

The ledger distinguishes **five** durable states on restart, not six. A settled receipt with no
decision row is one signature, reached by two different crash points, because the artifact insert and
the decision insert are atomic. The continuations are:

```text
crash before dispatch     → reservation abandoned; a known non-dispatch, id never reused
crash after dispatch      → call stays dispatched; blocked unknown, never re-sent
crash after settlement    → settled receipt consumed without new inference
crash after tool receipt  → receipt reused, no second tool call
crash after publication   → published artifact found; the step is not repeated
```

A post-dispatch unknown is never retried or relabelled (L-17). A late receipt still settles.

## 9. Where the rest lives

| | |
|---|---|
| Rules that must hold | `docs/invariants.md` — L-1…L-30, R-1…R-9 |
| Why something is this way | `docs/decisions/` |
| Known defects, live register | `docs/findings.md` (F-39+) |
| The G0 audit, archival | `audit/FINDINGS.md` (F-01…F-38) |
| Retired prose, archival | `docs/history/` — integrity-checked, not current truth |
| Map and commands | `AGENTS.md` |
