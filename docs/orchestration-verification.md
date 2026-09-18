# Verification report: bounded agent orchestration v1

```text
PheroOS agent orchestration v1
─────────────────────────────
Execution:            bounded agent runtime
Governance:           Session / Platform / Orchestration ledger
Colony policy plane:  L2 ACTIVE
                      L3 ACTIVE
                      L1 AVAILABLE AT PLATFORM ARBITRATION ONLY
                      L0 EVIDENCE ACQUISITION ONLY
```

Named precisely: **an L2–L3 governed runtime with an L1-compatible commitment
boundary**, not an "L1–L3 runtime". The runtime asks the plane for two decisions.

This report records what was actually run and what was actually observed. It is
not a summary of intent: every number below came from a command in this
repository, and the limitations section states plainly what was not tested.

## Base and scope

- Implementation base: `e664d2e9d1790f40eef0b15b25f23155ea9294a6`, which was the
  checkout's HEAD when this work began (`git rev-parse HEAD`, recorded before any
  change). The repository had not advanced past the reviewed reference, so no
  adaptation to a newer contract was required and nothing was reset.
- Baseline before any change: `python -m pytest -q` reported **509 passed**, with
  no pre-existing failures. The installed inspection example ran to
  `COMPLETE/abstain` with one call and zero unknown calls, and
  `inspect-replay` reported `PASS` with `source_match: true` and
  `new_tool_calls: 0`.

## Reproducible commands

```sh
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q

# the pre-existing inspection path, unchanged
pheroos-interaction inspect --config experiments/current/inspection-example/request.json \
  --source experiments/current/inspection-example/source --output output/inspection
pheroos-interaction inspect-replay --run output/inspection

# the three credential-free orchestration examples and their offline audits
pheroos-interaction orchestrate --workflow examples/orchestration/workflow.json \
  --script examples/orchestration/script.json --output output/orch-fixed
pheroos-interaction orchestrate-replay --run output/orch-fixed

pheroos-interaction orchestrate --workflow examples/orchestration/workflow-expected.json \
  --script examples/orchestration/script-expected.json --output output/orch-reuse
pheroos-interaction orchestrate-replay --run output/orch-reuse

pheroos-interaction orchestrate --workflow examples/orchestration/workflow-decomposition.json \
  --script examples/orchestration/script-decomposition.json --output output/orch-decomposed
pheroos-interaction orchestrate-replay --run output/orch-decomposed

# continuing an interrupted run (adds no calls to a finished one)
pheroos-interaction orchestrate-resume --run output/orch-fixed \
  --script examples/orchestration/script.json
```

Exit codes: `orchestrate`/`orchestrate-resume` return 0 for `success` and 2
otherwise; `orchestrate-replay` returns 0 for `PASS`, 1 for `FAIL` and 2 for
`LIMITED`.

## Observed results

Recorded on 2026-09-17 against the working tree of this change.

**Test suite.** `python -m pytest -q` reports **964 passed, 0 failed, 0 xfailed,
0 skipped**, stable across repeated runs. `git archive HEAD` into a
temporary tree collects exactly 509 tests, so the baseline is intact: no
pre-existing test was deleted, and the only pre-existing test files touched are
`conftest.py` (a new opt-in loopback fixture), `test_layout.py` (source-identity
entries for the new modules) and `test_commitment.py` (one assertion widened to
allow the new clock stamp on a `platform.waited` record). 455 tests are new:

| Suite | Tests | Covers |
| --- | --- | --- |
| `test_orchestration_authority.py` | 77 | proposal validation, authority widening, binding refusals at reservation and dispatch, budget exhaustion, decomposition atomicity, accounting violations |
| `test_orchestration_recovery.py` | 50 | crashes at five points, restart, stable logical ids, unknowns never redispatched, late settlement, dependency failure, abstention, cancellation, bounded WAIT |
| `test_orchestration_workflow.py` | 43 | end-to-end completion, the candidate → checker → result digest chain, decomposition narrowing, the reuse configuration, sweep discipline, the three CLI commands, the dependency boundary |
| `test_orchestration_audit.py` | 43 | replay PASS with zero execution, unchanged records, nine tampering cases, LIMITED on a source change, the commitment equality seam through `PlatformSession.commit` |
| `test_anthropic.py` | 144 | request freezing, unsupported-mode refusals, extraction, transport failure modes, a loopback fixture server, the model-script format |
| `test_tools.py` | 35 | registry validation, argument checking before execution, output bounds, fixture traversal/symlink/digest guards, reader scoping, the checkers |
| `test_orchestration_hardening.py` | 28 | regressions for every defect the final adversarial review found (below) |
| `test_orchestration_colony.py` | 35 | the colony policy plane: coupling (the runtime imports no mechanism directly), L2 allocation and its non-starvation invariant, L3 lease derivation, L1 arbitration over real candidate competition, and the boundary that no commitment policy can turn a failing checker into acceptance |

**Inspection path, unchanged.** `pheroos-interaction inspect` → `COMPLETE`,
action `abstain`, 1 call, 0 unknown. `inspect-replay` → `PASS`,
`source_match: true`, `new_tool_calls: 0`.

**Orchestration examples**, each run and then audited offline:

| Workflow | Outcome | Model calls | Tool calls | Artifacts | Known tokens | Sweeps | Replay |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `workflow.json` (fixed two-agent DAG) | `success` | 4 | 2 | 3 | 3820 | 10 / 21 | `PASS`, 63 checks, 0 new calls |
| `workflow-expected.json` (reuse: different agents, tasks and checker) | `success` | 4 | 2 | 3 | 3620 | 10 / 17 | `PASS`, 63 checks, 0 new calls |
| `workflow-decomposition.json` (opt-in decomposition) | `success` | 8 | 3 | 5 | 7720 | 18 / 45 | `PASS`, 115 checks, 0 new calls |

All three examples declare the L2 allocation policy and the L3 lease model, so both
layers are exercised: the lease resolves to 120 s from the declared model rather than
the 60 s default, and each run records its arm as
`{"allocation": "threshold", "lease": "evaporation", "commitment": "min_loss"}`.

The decomposition run admits exactly the two proposed children, transfers their
budgets, keeps the parent's declared join reserve, and the parent's later step
reads both children's artifacts. `orchestrate-resume` on a finished run reports
`success` with the same 4 model calls and the three artifact references, adding
no calls.

**Other outcomes exercised directly**, each observed rather than asserted from a
mock: `abstained` (an agent abstains; its dependents then report
`dependency_failed` and no artifact is fabricated), `budget_exhausted` (a call
cap and a token cap, each leaving zero outstanding reservations), `cancelled`
(cancellation mid-run, no artifacts, unknown calls still unresolved),
`blocked_unknown` (a dispatched call never re-sent; a later `receive` still
settles it and the next sweep consumes it without new inference).

## Seams resolved

All four integration seams named in the task were checked against the actual
checkout before anything was changed.

1. **Equal-loss commitment — confirmed present, fixed.** Reproduced directly:
   `optimal_stopping_rule` returned the candidate's call id when its certified
   loss equalled the ledger's abstention loss, and `PlatformSession.commit`
   then raised `StateError: rule cannot publish at or above abstention loss`.
   The rule now abstains at that boundary. The DP value computation is
   untouched, and the fix is applied only to the `publish` branch, so the recall
   behaviour — a candidate *above* the abstention loss still waiting when
   waiting beats abstaining — is unchanged.
2. **WAIT — confirmed, constrained rather than used.** The default commit rule
   remains minimum loss with strict improvement. `worker.waiting_rule` refuses a
   waiting configuration unless the caller declares a bounded deadline, a
   positive `tick_seconds` and the agents whose candidates may still arrive, and
   returns `None` (selecting the default rule) once every declared source has
   already proposed. `platform.waited` decisions are now clock-stamped and the
   tick is elapsed ledger time, not a poll count: a test drives
   `deadline + 4` consecutive sweeps against a frozen clock and observes every
   stamp identical, every decision `wait` and no artifact, while the same loop
   with the clock advanced by `tick_seconds` reaches the deadline and publishes.
3. **Provider accounting — existing contract inspected first, not weakened.**
   `exact_v1` was read before anything was added; it is untouched and no
   historical record is reinterpreted. The new `bounded_v2` contract is recorded
   per call and applies only to calls reserved under it.
4. **Publication meaning — separated.** A received observation, a published
   intermediate artifact, an acceptance decision and a final task result are four
   distinct records (§3 of the architecture document).

Nothing with an external effect runs inside a SQLite transaction: model calls,
tool execution and the checker all happen strictly between `dispatch` and
`receive`. Planning and reviewing are ordinary metered model operations.

## Bugs found and fixed during verification

Verification and an independent adversarial review of the finished code found
twelve defects. All twelve are fixed, and each has a regression test that now
passes as a real assertion (the last seven live in
`tests/interaction/test_orchestration_hardening.py`).

Found by running the work:

1. **A byte-oversized model response ended the run as `error`.** `Session.receive`
   settles such a response as `response_rejected` with its valid usage and then
   raises; the runtime did not catch it, so a settled step was reported as a
   crash. It is now consumed as a rejection and the next step is told to be brief.
2. **A host-task failure escaped the step classifier and aborted the whole run.**
   The finalization branch ran outside the per-step `try`.
3. **Replay did not check that a settled model receipt carries a decision row.**
4. **`admit_children` enforced only the run-level child bound**, not the task's own
   declared `decomposition.max_children`.
5. **A resumed run reported publication without a reference, and a hard crash after
   dispatch was not reported as blocked.** Both now derive from the ledger.

Found by adversarial review of the finished code:

6. **BLOCKER — a refused decomposition wedged the task permanently.**
   `PlatformMixin._decompose` refuses a cyclic, duplicate or widening graph with a
   plain `ValueError`, which the step loop did not catch. A model proposing
   sibling `a → b → a` produced outcome `error` with *no* decision row, no
   rejection slot consumed, and `resume_run` reproducing the same error forever —
   contradicting the contract's claim that a refused proposal "is a recorded
   rejection … never an instruction". Now caught and recorded; the task continues
   and publishes, and the case is covered for cyclic, duplicate and widened
   proposals plus a resume.
7. **A producer could read the checker's answer key.** `fixture.read` took no
   configuration, so any holder could read any declared fixture — including
   `expected`, the fixture `checker.expected_json` compares against. A scripted
   producer reading it still ended `success`, which would have made that example
   demonstrate nothing. A reader is now scoped at registration to an explicit
   fixture list and its input schema is the enum of exactly those names; the
   examples scope their reader to the data fixture, and `workflow.json` no longer
   declares the unused answer key.
8. **Replay's duplicate-decision check was keyed by work id**, so a second decision
   for the same receipt audited clean unless it happened to be that work's last
   row. Now keyed by call id.
9. **A crash between settlement and the separate usage write made a clean run
   permanently un-auditable** — replay reported `FAIL`, indistinguishable from
   tampering. The reported usage is now written in the settlement transaction.
10. **An unbounded string schema was silently narrowed to length 0**, making every
    value unsatisfiable instead of raising at spec validation. Now refused, as the
    array branch already refused a missing `maxItems`.
11. **The adapter refused documented live usage members** (`service_tier`,
    `cache_creation`, `server_tool_use`), so it would have rejected current real
    responses and stranded the call as unknown. They are now recorded without
    entering the prompt sum; a genuinely unknown member is still refused.
12. **The declared `join_reserve.model_steps` was validated but never enforced**, and
    a child could not request a parent read whose task id is not a legal child name.
    Both fixed.

Two further corrections were made during implementation, each caught by a check
rather than by inspection. Offline replay of the decomposition example initially
failed because admitting children mutated the parent's declaration, which made an
earlier step's context impossible to rebuild; declarations are now immutable and
readable children are derived instead. And `blocked_binding` was removed from the
outcome vocabulary after it proved unreachable — the step index is derived from
recorded bindings, so the loop never recomputes an occupied logical key. The
guard remains as a precise error.

The review also verified, independently and by running commands, that the
example metrics, the replay results, the untouched `exact_v1` contract, the
"no external effect inside a transaction" property, the per-sweep call bound and
the digest chain from candidate to checker to result all hold as documented.

## Limitations — stated plainly

- **No live provider request was made.** The Anthropic Messages adapter is
  implemented and tested offline only: against an injected opener, a local fake
  transport and an in-process loopback HTTP fixture server. No credential was
  read, no money was spent, and no paid experiment was started. Setting
  `PHEROOS_PROVIDER=1` enables the adapter; it is not a spending authorization,
  and nothing here demonstrates live compatibility. Mock measurements are not
  evidence of model quality, cost saving or optimality.
- **The `bounded_v2` prompt bound is a declared parameter, not a measurement.**
  The provider renders its own prompt, so the byte-to-token assumption and
  `prompt_overhead_tokens` bound the ledger's reservation, not the provider's
  tokenizer. After a recorded accounting violation the token cap no longer
  bounds what that call may be billed externally.
- **Replay verifies the record, not the world.** It cannot show that a provider
  billed what it reported, that fresh inference would reproduce a prior answer,
  or that an accepted candidate is semantically correct. Success means the
  declared finite checker passed on that exact candidate digest.
- **The scope remains a trusted single-machine serial host.** The capability
  boundaries are application boundaries, not a claim of adversarial process
  isolation. Storage-concurrency checks from the existing suite are preserved,
  but the reference runtime is serial.
- **No framework comparison was run.** LangGraph and the Microsoft Agent
  Framework are neither imported nor benchmarked, and no claim of superiority is
  made anywhere in this work.
- **Not implemented, by contract:** distributed execution, arbitrary code
  execution, a message broker, autonomous replanning loops, vector or shared
  memory, broadcast chat, and automatic paid experiments.

## The colony policy plane

The colony layer was originally a parallel stack the runtime never consulted. It is
now the runtime's decision layer for two of its three slots, through a single
`RuntimePolicies` in `runner/runtime_policies.py`. Two drafts were corrected on the
owner's instruction; the record is kept because the corrections are the substance.

**First correction.** The first attempt routed *host acceptance* through
`PlatformSession.commit(rule=...)` with an L1 rule, turning a deterministic checker
verdict into a commitment decision, and re-seated the ledger MRO onto
`PlatformSession`. Both were wrong and were reverted. Host acceptance is a
verification rule; L1 answers candidate commitment. The MRO change was diagram
tidiness with no behavioural gain.

**Second correction.** The follow-up still overreached in three ways, all now fixed:

- It exposed a `Runtime.commit_candidates()` that no current workflow could reach —
  a door built so L1 would look wired in. Removed. `OrchestrationSession.commit`'s
  explicit refusal of orchestration work is restored, and the commitment slot is no
  longer declarable in a workflow spec, because declaring one where no arbitration
  locus exists is decorative configuration.
- It *derived* the L2 capacity model from which agents happened to be idle, and gave
  the host a fabricated cost equal to the cheapest so the worker interface would
  apply to it. Both fabricate parameters the workflow does not have. The capacity
  model is now declared in full, a declaration that is provably FIFO is refused at
  validation, and the host takes ready order through `select_host_work` because a
  reserved identity with no model configuration is not a worker.
- The plane was named `runner/policy.py`, one character from the existing
  `runner/policies.py`. Renamed to `runner/runtime_policies.py`.

**What is wired now.** L2 and L3 are active; L1 is defined and validated but not
reachable from the runtime.

- **L2** chooses which ready task each sweep advances from a declared capacity model.
  Under one agent per task there is no cheaper capacity, so the shipped workflows
  declare `fifo` and the report does not claim swarm allocation. A threshold whose
  cheaper workers do not exist stalls the run, and the outcome reason says exactly
  that instead of falling back silently. Since degeneracy became a *per-task* check,
  no declaration that validates can reach that stall; the branch stays as a net and
  the test asserts its unreachability rather than pretending it is exercised.
- **L3** derives the lease from a claim-to-dispatch lead-time model frozen in the
  spec — never scanned from live history, so the TTL cannot drift between a run and
  its replay.
- **L1** is validated against a platform session with three agents genuinely
  competing: the baseline, optimal-stopping and cross-inhibition policies are checked
  against the pure mechanisms, including a deadlock abstaining terminally.
- **The boundary is tested directly.** A failing checker is run under every
  commitment policy and acceptance stays false, with no candidate ever recorded.
- **L0 is not wired**, and the reason is recorded: treating the n-th inference as a
  measurement channel with a calibrated `q`/`rho` would fabricate a statistical model.

**Reporting.** A run records what ran apart from what was available:
`runtime_policies` carries the allocation and lease arms, `platform_capabilities`
carries the commitment adapter and its `active_decisions` count, which is zero. An
earlier draft reported all three side by side, which would have implied L1 was
exercised and contradicted the README. The deferral reason was likewise narrowed. The
policy plane does derive *which* eligible agents are cheaper — that is how the count
is computed from primitives — but it returns only a claim or a deferral, never an
identity. So the runtime still cannot tell an absent worker from a busy one, and the
reason it reports asserts neither.

**Coupling.** `runtime.py` imports no colony mechanism — a test parses it with `ast`
and asserts `commitment`, `leases`, `sequential` and `policies` never appear, and
that the words `cheaper_workers`, `cheapest_cost` and `"cost"` do not either. The arm
is declared in the frozen spec, so swapping it changes the spec digest and a ledger
cannot be continued under another.

## Correctness defects fixed alongside the refactor

Four defects unrelated to the policy plane were found and fixed, each with a test:

1. **An admitted decomposition left its `propose_children` action unanswered.**
   `_conversation` handled the `tool` and `rejected` decisions but not `decompose`,
   so the parent's next request contained an assistant `tool_use` with no matching
   `tool_result` — a malformed conversation that a real Messages API would reject.
   Reproduced on the shipped decomposition example before the fix.
2. **A rejected candidate was reported as a successful run.** Every task completed
   and every artifact published, but the declared acceptance rule had rejected the
   candidate. That is now the distinct outcome `rejected`, not `success`.
3. **A tool call was bound to its proposal only by digest.** Admission now re-reads
   the source receipt and requires it to propose exactly this tool with exactly these
   arguments, so a substituted argument set with a consistent digest is refused.
4. **Resume did not check the frozen record against the ledger it reopened.** A
   self-consistent `frozen.json` describing a different workflow was accepted;
   `resume_run` now compares its digest with the ledger's recorded spec digest.

## Unresolved issues

- **The per-parent run-level `max_children` check inside `PlatformMixin._decompose`
  is unreachable through `admit_children`**, because a task's declared bound is now
  enforced and spec validation forbids a task bound above the run bound. It stays
  reachable through `PlatformMixin.decompose` directly and is covered there. A
  redundancy, not a hole, but worth recording.
- **`max_depth` is not exercised end to end by the orchestration suite.** Admitted
  children carry `decomposition: None`, so every admission happens at depth 0 and a
  second level cannot be reached through a model proposal. Nested decomposition is
  deliberately not implemented; the platform suite covers the depth bound.
- **Tool failures are settled, not left unknown.** A `ToolError` is recorded as
  `{"ok": false, "error": ...}` on the receipt. This is sound only because every
  registered tool is local, read-only and effect-free. A future tool with an
  external effect must leave the call dispatched instead, and that distinction is
  currently a convention rather than an enforced property.
- **The fake transport routes on a header line the host writes into the system
  prompt.** It is host-authored and matched with an anchored pattern on the first
  line only, but the deterministic fake does depend on prompt structure rather than
  an out-of-band channel.
- **The reader-scoping fix is per tool, not per task.** Two tasks sharing one
  `fixture.read` entry share its scope; a spec needing different scopes must
  declare differently named reader tools. There is no per-task fixture allowlist.
- **`REPORTED_DETAIL` is a fixed list of usage members.** If the API adds another
  non-prompt member, `extract` will refuse the response and the call will stay
  dispatched until the list is extended. That is the deliberate direction of the
  trade: refusing is safe, ignoring could hide prompt tokens.
- **L2 rarely changes the order in the shipped examples.** Their DAGs are sequential,
  so two agents are seldom ready at once and the policy reduces to FIFO. The deferral
  path is exercised by tests that make both tasks ready, not by the examples.
- **L1 has no arbitration locus inside orchestration.** Each task declares one agent,
  `max_candidates` is one, and `OrchestrationSession.commit` refuses orchestration
  work outright. The slot is defined and tested against real platform competition,
  but the runtime has no entry point for it and none was invented.
- **L2 is FIFO in every shipped workflow.** With one agent per task there is no
  cheaper capacity to declare, so the colony arm of L2 is exercised by unit tests
  over the policy, not by the examples. No claim of real swarm allocation is made.
- **The planned FIFO-versus-response-threshold comparison has not been run**, and
  cannot be meaningfully run until a workflow has shared tasks or multi-worker
  capacity. The arms exist and are recorded per run; no measurement is claimed.
- **The declared allocation and lease parameters are assumptions, not measurements.**
  `service_time`, `latency_cost` and the stage durations are the host's declarations;
  nothing in this repository measures them, and the L2 threshold is an evaluable
  heuristic rather than a proven-optimal scheduler.
- **No live provider test, and therefore no evidence about real prompt accounting.**
  See the limitations above.
