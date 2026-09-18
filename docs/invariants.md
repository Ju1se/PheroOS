# Invariants

The authoritative wording. `AGENTS.md` §4 holds the index and never restates an entry; two copies of
a rule is one copy that goes stale.

**IDs are frozen and append-only in both namespaces.** They appear in tests, audit findings, commit
messages and failure text, so an ID is a stable reference, not an index position. Never renumber,
never compact, never reuse.

## Two namespaces

```text
L-n   violated = the system is wrong          (correctness, authority, replay)
R-n   violated = the system is fine — tests green, CI green, code arguably
      cleaner — and the research question is gone
```

The distinction is what a future agent needs when it asks "may I unify these two state machines?".
The answer's nature is *"that breaks the research design, ask the owner"*, not *"that is forbidden"*.

## Admission test — all three must hold

```text
1. It still applies to the current architecture.
2. Violating it changes correctness, authority, or replay semantics.
3. It CAN be checked mechanically or by a behavioural test.
```

Criterion 3 is about **checkability, not current enforcement**. A checkable rule that nothing checks
is admitted with `UNENFORCED` and a closing gate. A rule uncheckable in principle is not an invariant.

## Authoring rules

These are the two ways a tidier formulation silently drops coverage. Both were caught in review; both
will recur.

1. **Enumerate, do not abstract.** A family's wording enumerates its sub-conditions. If a family can
   only be stated by abstracting over what it absorbs, the absorbed items keep their own IDs. L-17 is
   the model: ten absorbed clauses, all individually decidable, because the wording lists them.
2. **A prohibition may be restated as a positive, checkable claim — but the restatement must first be
   tested against the cases the prohibition caught.** Discard the prohibition only for cases the
   positive form provably still catches. L-27 exists only because this check was run: "all inter-task
   data flows through published artifacts" reads true while a derived second store appears anyway.

## Enforcement is typed

```text
kind: test       → the node exists and resolves
kind: fixture    → the definition exists and is autouse or explicitly requested
kind: lint       → a static check
kind: schema     → a declaration-time validation
kind: delegated  → the chain terminates in one of the above or in an UNENFORCED entry; cycles rejected
UNENFORCED (F-xx, gate Gn)  → checkable, unchecked, with a named owner
```

One flat existence test across heterogeneous targets misjudges. `kind: fixture` exists because L-1's
network guard is an autouse fixture, not a test node, and a node-only check would mislabel it.

Test paths below are relative to `tests/interaction/`.

---

# Section 1 — L namespace

### L-1 · Canonical `agents[]` representation
`agents[]` is the canonical runtime representation of a task's eligible executors. Singular `agent`
may appear only at the input boundary, where it is canonicalized. No durable schema, table column or
runtime read may treat a single `agent` as the execution identity.
*Why:* a second representation splits the authority record; the table name stops identifying the
semantics of its contents.
`UNENFORCED (F-03, gate G2)`

### L-2 · No hidden schema fallback
No construct of the form `x.get("new", [x["old"]])`, or any key-presence equivalent, in a live code
path. Compatibility is version-gated at an explicit boundary, never inlined as a default.
*Why:* an inlined default cannot be audited at a boundary, and the version gate stops being the thing
that decides.
`UNENFORCED (F-03, gate G2)` — the live instance is `runner/contracts.py:401-403`, 11 call sites.

### L-3 · v1 audits, v2 executes
A `orchestration-workflow-v1` declaration may be validated and replayed but never executed. v1 records
are audit/replay semantics; v2 is executable semantics. Historical records are never reinterpreted
under current semantics.
*Why:* a v1 ledger was written under single-executor semantics down to its table shape, and nothing
can verify such a record was normalized to today's form.
`kind: test  test_orchestration_audit.py::test_a_v1_workflow_validates_and_audits_but_the_runtime_refuses_to_execute_it`

### L-4 · Frozen decision inputs
Every policy input is read from the frozen run identity, never from live or dynamic history.
- **L-4.a** lease TTL derives from the declared model in the frozen spec.
  `kind: test  test_orchestration_colony.py::test_the_evaporation_lease_comes_from_the_frozen_spec_not_live_history`
- **L-4.b** the allocation draw's inputs are frozen and persisted.
  `kind: delegated  L-14`

### L-5 · Availability is not execution
A capability being present is never reported as having been used. Participation counts come from the
ledger, never hard-coded.
`kind: test  test_e4_shared_capacity.py::test_metric_families_outcome_and_cost_are_present_allocation_and_lease_are_not`

### L-6 · No self-certification of authority
Identity, authority, provenance and execution success are never derived from data the actor submitted.
The acting agent comes from the lease owner (live), the permission owner (dispatched) or the matching
claim event (undispatched) — never from a binding the model wrote.
`kind: test  test_orchestration_audit.py::test_replay_detects_a_permission_and_a_claim_event_that_disagree`

### L-7 · Declared authority only
A policy decides only within its declared scope. Commitment selects among admissible candidates and
cannot override application truth conditions: a failing checker never becomes a pass.
- **L-7.a** a commitment policy cannot turn a failing checker into acceptance.
  `kind: test  test_orchestration_colony.py::test_no_commitment_policy_can_turn_a_failing_checker_into_acceptance`
- **L-7.b** commitment rules read only candidate metadata — zero bytes of candidate content. A rule
  that cannot read the content structurally cannot overturn a checker: reading and deciding are one
  boundary.
  `kind: test  test_commitment.py::test_commitment_imports_only_dataclasses_hashlib_and_math`
- **L-7.c** capability is rechecked at reservation AND at dispatch, so a cached context retains no
  revoked authority.
  `kind: test  test_platform_atomicity.py::test_committed_scoped_decision_rechecks_current_readers`

### L-8 · No workforce inference
Capacity, cost and cheaper-worker counts are derived from frozen declarations scoped to the task's
eligible agent set. The runtime infers none of them from observed state — who is idle, who claimed last.
`kind: test  test_orchestration_colony.py::test_the_runtime_never_invents_a_capacity_model`

### L-9 · No mechanism leakage into the runtime
The runtime imports no colony mechanism directly and instantiates no concrete policy class; it goes
through the policy-plane adapter.
`kind: test  test_orchestration_colony.py::test_the_runtime_imports_no_colony_mechanism_directly`

### L-10 · Experimental identity is inert
No experiment branch, constant or default inside production semantics. Experimental variation lives in
declared workload fixtures and policy config only.
`kind: test  test_e4_shared_capacity.py::test_no_policy_layer_module_names_the_experiment_in_its_code`

### L-11 · Replayable decisions
The same frozen spec and the same persisted decision inputs reproduce the same externally observable
decision sequence within the declared deterministic boundary.
*Why:* offline replay currently verifies the internal consistency of authority records but never
re-derives the allocation decision, so a fully-consistent forged allocation replays `PASS`.
`UNENFORCED (F-02/F-04, gate G1)`

### L-12 · Observation is not ontology
Absence of evidence is never reported as "does not exist" or "never happened". A value read from a
declaration is never presented as a measurement.
`UNENFORCED (audit §9, gate G3)`

### L-13 · Durable authority requires durable decision evidence
An authority decision recorded in the ledger carries the evidence needed to re-derive it. An execution
that cannot be re-derived from durable rows is unattested.
`UNENFORCED (F-02, gate G1)`

### L-14 · Replay-relevant nondeterminism is frozen
Every replay-relevant nondeterministic input is frozen, persisted, or deterministically derivable from
persisted state. A generated draw that is used but not persisted is a violation.
`UNENFORCED (F-04, gate G1)` — carries L-4.b.

### L-15 · Bounded control, and drain survives exhaustion
Every control operation is bounded by a cap derived from durable rows, **and** exhaustion never blocks
release, settlement or cancellation.
- cap + drain: `kind: test  test_platform_conformance.py::test_platform_operation_exhaustion_cannot_prevent_safe_release`
- caps conserved across settlement, abandonment and unknowns: `kind: test  test_platform_conformance.py::test_multilevel_caps_conserved_with_settlement_abandonment_and_unknowns`
- counts derive from durable rows: `kind: test  test_orchestration_workflow.py::test_metrics_match_the_ledger_rows`
- resume resets no budget: `kind: test  test_orchestration_workflow.py::test_cli_orchestrate_resume_of_a_finished_run_adds_no_calls`
- every attempt counts against the call cap: `kind: test  test_colony.py::test_abandoned_attempts_count_against_the_work_call_cap`
- the sweep is bounded: `kind: test  test_colony.py::test_max_items_bounds_the_sweep`

### L-16 · Atomicity of decision and consequence
A decision and its durable consequence commit in one transaction, **and** nothing with an external
effect runs inside one.
- decision + consequence atomic: `kind: test  test_platform_atomicity.py::test_composite_commit_failure_rolls_back_publication_and_decision`
- reported usage written in the settlement transaction: `kind: test  test_orchestration_hardening.py::test_reported_usage_settles_in_the_receipt_transaction_so_a_crash_cannot_split_them`
- budgets checked inside the reservation transaction: `kind: test  test_platform_atomicity.py::test_atomic_work_budget_admits_only_one_concurrent_reservation`
- **L-16.d** nothing with an external effect — model call, tool execution, transport — runs inside a
  SQLite transaction. `UNENFORCED (gate G4)`

### L-17 · Call identity and recovery
A logical operation key is stable across re-claims; a matching settled receipt is reused rather than
re-dispatched; a non-matching one refuses another read; a post-dispatch unknown is never retried or
relabelled; a pre-dispatch abandonment is a known non-dispatch whose id is never reused.
- key stable across re-claims: `kind: test  test_colony.py::test_call_ids_are_stable_across_reclaims_unlike_the_epoch_id`
- matching receipt reused: `kind: test  test_colony.py::test_matching_receipt_is_reused_before_reading_the_next_depth`
- non-matching refuses: `kind: test  test_colony.py::test_mismatched_receipt_refuses_another_read`
- unknown stays unknown: `kind: test  test_colony.py::test_driver_failure_after_dispatch_at_depth_one_stays_unknown_across_restart`
- abandoned id never reused: `kind: test  test_colony.py::test_scoped_platform_refuses_undeclared_tree_and_abandoned_id_is_never_reused`

### L-18 · Narrowing-only delegation
A child never widens its parent — agents, tools, reads, limits — and the parent's declaration is never
mutated, so an earlier step's context stays reconstructible.
- narrowing: `kind: test  test_orchestration_workflow.py::test_admitted_children_narrow_the_parent_tools_reads_and_limits`
- readers cannot expand, depth bounded: `kind: test  test_platform_conformance.py::test_decompose_cannot_expand_parent_readers_and_depth_is_bounded`
- scoped inheritance is fenced: `kind: test  test_platform_atomicity.py::test_scoped_child_inherits_tool_arguments_readers_and_source_update_fences`

### L-19 · Decomposition admission is validated before any durable write
The whole proposed graph, its references, the cumulative child/depth/work limits and the transferred
budgets are validated before anything is written, and the parent keeps its declared join reserve.
- cycles rejected atomically: `kind: test  test_platform_conformance.py::test_decompose_rejects_all_dependency_cycles_atomically`
- caps transferred, parent waits: `kind: test  test_platform_conformance.py::test_decompose_transfers_caps_and_parent_waits_for_all_children`
- join reserve preserved: `kind: test  test_orchestration_workflow.py::test_parent_keeps_its_declared_join_reserve_after_admitting_children`
- once per task version: `kind: test  test_orchestration_workflow.py::test_children_are_admitted_once_as_a_single_decompose_decision`

### L-20 · Terminality and dependency satisfaction
WAIT and no-candidate are non-terminal; abstention is terminal and buys nothing again; a dependency is
satisfied only by a published artifact, never fabricated; an empty ready queue is not success.
- WAIT / no-candidate non-terminal: `kind: test  test_platform_conformance.py::test_empty_candidate_and_wait_are_nonterminal_and_cannot_choose_foreign_receipt`
- abstention terminal: `kind: test  test_platform_conformance.py::test_rule_none_is_explicit_terminal_abstention`
- a rejected candidate is not a successful run: `kind: test  test_orchestration_hardening.py::test_a_rejected_candidate_is_not_reported_as_a_successful_run`
- a blocked dependency is reported, not fabricated: `kind: test  test_orchestration_recovery.py::test_an_abstained_dependency_is_reported_by_blocked_work`

### L-21 · Spend authority
No provider client is constructed and no dispatch occurs without explicit host enablement and an
injected transport; credentials stay at the transport boundary; a configured endpoint or an enable
flag is not spending authorization.
- disabled unless enabled: `kind: test  test_provider_worker.py::test_provider_disabled_creates_no_call_rows`
- the flag is an exact boolean, not a truthy string: `kind: test  test_provider_worker.py::test_provider_enable_is_exact_bool`
- no redirects, no proxy: `kind: test  test_anthropic.py::test_the_default_opener_follows_no_redirect_and_reads_no_proxy`
- tests reach no network: `kind: fixture  conftest.py::forbid_network`
- **L-21.a** no provider client is constructed unless an agent declares that provider.
  `UNENFORCED (gate G4)`

### L-22 · The horizon-one identity
`plan_sequential(horizon=1)` equals `plan_inspection` field for field, including the global tie budget.
*Why:* the sequential layer is an extension of the inspection core, not a replacement; divergence at
horizon one means the core changed silently.
`kind: test  test_sequential.py::test_horizon_one_reproduces_every_repository_inspection_case_exactly`

### L-23 · Each depth binds a distinct declared source
Re-reading the same fingerprint returns the same evidence, not a fresh conditionally independent
observation; a repeated source must declare `rho=1`.
`kind: test  test_sequential.py::test_per_depth_channels_never_buy_a_repeated_source_declared_with_full_copy`

### L-24 · Bounded mechanism work
A rule that runs inside a transaction has an explicitly bounded amount of work.
`kind: test  test_commitment.py::test_work_per_commit_is_bounded_explicitly`

### L-25 · An oversized body is a settled rejection, never an unknown
A receipt that exceeds only the byte bound, with valid usage, settles under existing semantics rather
than becoming an unresolved dispatch.
`kind: test  test_provider_worker.py::test_byte_rejected_receipt_settles_usage_and_is_not_unknown`

### L-26 · Inter-task data flows through published artifacts
All data passing between tasks flows through published artifacts.
*Why:* if data flows outside artifacts, artifact lineage stops describing what happened, and replay's
account of the run becomes incomplete — so every claim made from the ledger overclaims.
`UNENFORCED (gate G3)`

### L-27 · The ledger is the sole durable store of task state
No component maintains a parallel store, index, cache or memory of task state.
*Why:* if a second store exists the ledger stops being the complete record, and claims made from it
overclaim in exactly the way audit §9 describes. Exists only because L-26's positive restatement was
tested for narrowed coverage: a derived second store passes L-26 and fails here.
`UNENFORCED (gate G3)`

### L-28 · Task tools lie within the shared capability
A task's declared tools are a subset of the capability every eligible agent shares.
`UNENFORCED (gate G2)` — enforced in code at `runner/contracts.py:545`, with no test.

### L-29 · `exact_v1` is a live contract
`exact_v1` remains the base ledger's prompt-usage contract and orchestration's tool-call contract; only
model calls use `bounded_v2`. Its semantics are never changed and historical records are never
reinterpreted under it.
`UNENFORCED (gate G2)` — no test in the repository references `exact_v1`.

### L-30 · Negative certification requires a test  ·  `target: documentation`
A negative claim in documentation — "the codebase does not do X" — requires a test enforcing X's
absence. An unfalsifiable negative claim is not permitted in prose.
*Why:* `docs/history/orchestration-architecture-2026-09-17.md:331-333` certified the absence of the defect that
exists at `runner/contracts.py:401-403`. A future agent checking L-2 against the docs concludes the
codebase is clean and skips it. Documentation that certifies is documentation that can defeat an audit.
`UNENFORCED (gate G0.5)` — enforcement runs against docs in the doc gate, not against code in the suite.

---

# Section 2 — R namespace

Violating one of these leaves the system working and the research question gone. The correct response
to wanting to change one is *ask the owner*, not *it is forbidden*.

### R-1 · `runner/colony.py` stays unreachable from production
Do not make it reachable from a production entry point, and do not delete it. Unreachability is the
intended state: it is a reference implementation, not dead code.
*Why:* 286 LOC, zero call sites outside `test_colony.py`, unreachable from all five CLI subcommands —
it reads exactly like dead code, which is why the constraint must be written down.
`UNENFORCED (gate G0.5)` — asserted as unreachability; inverting it would mandate wiring it in.

### R-2 · `Runtime` and `run_colony` stay separate
Do not unify the two state machines.
*Why:* different call identities (`orch:` vs `colony:`) and different semantics; merging them destroys
a verifiable comparison rather than removing duplication.
`UNENFORCED (gate G0.5)` — from the divergence of the two call-identity schemes.

### R-3 · The host finalizer is not a worker
It is a reserved identity with no model configuration. Never give it a cost, a threshold or worker
economics to unify the interface.
`kind: test  test_orchestration_colony.py::test_the_host_finalizer_takes_ready_order_and_is_never_priced`

### R-4 · L1 stays available and unexercised
L1 commitment stays available at the platform candidate-arbitration boundary and unexercised by
orchestration. Do not add a runtime entry point for it.
*Why:* several eligible executors is an **allocation** decision — L2 picks one executor, yielding one
admitted execution path — not multiple competing publishable candidates. Seeing `agents[]` and
activating L1 is the predictable wrong inference.
`kind: test  test_orchestration_colony.py::test_the_runtime_exposes_no_candidate_commitment_entry_point`
`kind: test  test_orchestration_colony.py::test_orchestration_work_refuses_candidate_arbitration`

### R-5 · Arms differ only in declared policy
Baseline and treatment cells differ only in the declared `policies` block. Changing a model, tool,
budget, fixture or input to make an arm run is a confound, not a fix.
`kind: test  test_e4_shared_capacity.py::test_the_four_cells_share_one_workload_once_the_policies_block_is_stripped`

### R-6 · Both arms declare the identical model config
*Why:* different models per worker confound an allocation effect with a model effect.
`kind: test  test_e4_shared_capacity.py::test_the_scripted_response_follows_the_task_and_step_and_ignores_everything_else`

### R-7 · Experiment identity never enters `runner/`
No experiment branch, constant or default in the policy layer.
`kind: test  test_e4_shared_capacity.py::test_no_policy_layer_module_names_the_experiment_in_its_code`

### R-8 · Commitment cannot overturn a checker
A commitment policy selects among admissible candidates and can never overturn a checker's verdict.
`kind: test  test_orchestration_colony.py::test_no_commitment_policy_can_turn_a_failing_checker_into_acceptance`

### R-9 · Keep the ledger MRO
Keep `OrchestrationMixin + PlatformMixin + Session`. Do not reparent to `PlatformSession` for diagram
symmetry unless it demonstrably removes duplication or fixes an MRO bug.
*Why:* these tables are a domain extension of the platform ledger, not a layer beneath it.
`kind: test  test_orchestration_colony.py::test_the_orchestration_ledger_keeps_the_platform_mro`

---

# Section 3 — The unenforced baseline

```text
ceiling: 15   (evaluated against the working tree)
```

The parenthetical is permanent: it names the evaluation basis, not today's state. Raising this ceiling
fails the gate outright. Lowering it is a normal commit. **Baseline changes are their own commit,
never bundled with code.**

| ID | Why unenforced | Closing gate |
|---|---|---|
| L-1 | `eligible_agents` dispatches on key presence, 11 live call sites | G2 |
| L-2 | same site; the fallback is inlined, not version-gated | G2 |
| L-4.b | delegated to L-14 | *(via L-14)* |
| L-11 | replay never re-derives the allocation decision | G1 |
| L-12 | no check that a declared value is not reported as measured | G3 |
| L-13 | no durable allocation row exists to re-derive from | G1 |
| L-14 | the response draw is generated and never persisted | G1 |
| L-16.d | no check that external effects stay outside transactions | G4 |
| L-21.a | no check that a provider client requires a declaring agent | G4 |
| L-26 | no side-channel check | G3 |
| L-27 | no second-store check | G3 |
| L-28 | enforced in code, no test | G2 |
| L-29 | no test references `exact_v1` | G2 |
| L-30 | no documentation gate exists yet | G0.5 |
| R-1 | no reachability assertion | G0.5 |
| R-2 | no call-identity divergence assertion | G0.5 |

**Count: 15.** L-4.b is delegated, not counted — its debt is carried once, by L-14.

```text
inherited (L-1…L-14) : 6    L-1, L-2 (G2) · L-11, L-13, L-14 (G1) · L-12 (G3)
surfaced             : 9    L-30, R-1, R-2 (G0.5) · L-26, L-27 (G3)
                            L-28, L-29 (G2) · L-16.d, L-21.a (G4)
deferred             : 0    every entry names a briefed gate
```

## Gates

```text
G0.5  knowledge baseline — this gate; closes L-30, R-1, R-2 via the doc/structure checker
G0.6  counter-source correction — prose only; the docstrings and the certifying doc claim
G1    allocation provenance — closes L-11, L-13, L-14 (F-02/F-04)
G2    schema boundary — closes L-1, L-2, L-28, L-29 (F-03)
G3    epistemic claims — closes L-12, L-26, L-27, L-30's sibling concerns (audit §9)
G4    execution boundaries — closes L-16.d, L-21.a
```
