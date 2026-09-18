# PheroOS — operating contract

## 1. Mission

PheroOS is a local binary-inspection decision tool on a durable SQLite execution ledger, with a
bounded agent-orchestration runtime layered over it. Pure decision policy lives in
`src/pheroos_interaction/`; execution, source access, replay and the runtime live in `runner/`.
A workflow is declared, frozen, executed against the ledger, and replayable offline with zero model
or tool calls. Scope is a trusted single-machine serial task — no distributed execution, no
malicious-host guarantee.

**Research question:** individual agents may be unremarkable; a group's allocation, waiting,
competition and commitment behaviour is determined by **protocol, not by prompt**.

## 2. Research contract — what must not be optimized away

This repository is a research artifact. The structures below look like defects to ordinary
engineering judgment and are load-bearing. Each is stated so you can decide against it.

| # | Constraint | Why | Enforced by |
|---|---|---|---|
| R-1 | Do not make `runner/colony.py` reachable from a production entry point, and do not delete it. | Unreachability is the intended state; it is a reference implementation, not dead code. | `UNENFORCED` (pending classification, §7) |
| R-2 | Do not unify the `Runtime` and `run_colony` state machines. | They have different call identities and different semantics; merging them destroys a verifiable comparison. | `UNENFORCED` (F-18) |
| R-3 | The host finalizer is a reserved identity, not a worker. Never give it a cost, a threshold or worker economics. | It has no model configuration; a fabricated price would invent an economic parameter that does not exist. | `test_orchestration_colony.py::test_the_host_finalizer_takes_ready_order_and_is_never_priced` |
| R-4 | L1 commitment stays available at the platform arbitration boundary and unexercised by orchestration. Do not add a runtime entry point for it. | Several eligible executors is an **allocation** decision (L2 picks one), not competing candidates. Seeing `agents[]` and activating L1 is the predictable wrong inference. | `test_orchestration_colony.py::test_the_runtime_exposes_no_candidate_commitment_entry_point`, `::test_orchestration_work_refuses_candidate_arbitration` |
| R-5 | Baseline and treatment arms differ **only** in the declared `policies` block. | Changing a model, tool, budget, fixture or input to make an arm run is a confound, not a fix. | `test_e4_shared_capacity.py::test_the_four_cells_share_one_workload_once_the_policies_block_is_stripped` |
| R-6 | Both arms declare the identical model config. | Different models per worker confound an allocation effect with a model effect. | `test_e4_shared_capacity.py::test_the_scripted_response_follows_the_task_and_step_and_ignores_everything_else` |
| R-7 | Experiment identity never enters `runner/`. No experiment branch, constant or default. | A measured difference must be attributable to the policy, not to an experiment-specific code path. | `test_e4_shared_capacity.py::test_no_policy_layer_module_names_the_experiment_in_its_code` |
| R-8 | A commitment policy selects among admissible candidates; it can never overturn a checker's verdict. | Commitment is not a truth condition. | `test_orchestration_colony.py::test_no_commitment_policy_can_turn_a_failing_checker_into_acceptance` |
| R-9 | Keep the ledger MRO `OrchestrationMixin + PlatformMixin + Session`. Do not reparent to `PlatformSession` for diagram symmetry unless it demonstrably removes duplication or fixes an MRO bug. | These tables are a domain extension of the platform ledger, not a layer beneath it. | `test_orchestration_colony.py::test_the_orchestration_ledger_keeps_the_platform_mro` |

## 3. Where the truth lives

`verified-at` is the commit at which the *sentence* was last checked against the code — a link
checker proves a file exists, not that the claim about it is still true. **`(partial)` means the sha
cannot pin the claim**: the orchestration layer is untracked, so `HEAD` does not contain the code the
sentence is about (F-01). The marker falls away when F-01 lands.

| Question | Source | Verified by | verified-at |
|---|---|---|---|
| Intended architecture? | `ARCHITECTURE.md` **(PLANNED — not yet created)** | `pytest -q tests/interaction/test_orchestration_workflow.py -k "import_no_runner or import_only_the_standard_library"` | `98894c0` (partial) |
| What must never happen? | `docs/invariants.md` | per-invariant, §4 | `e3862f2` |
| Why is X this way? | `docs/decisions/` | `NOT YET ENFORCED` — no checker validates ADR front-matter yet | `e3862f2` |
| Conforming right now? | §6 commands | `python -m pytest -q` | `98894c0` (partial) |
| Migration input for the docs above | `docs/history/agents-md-preimage-2026-09-17.md` (sha256 `24e8f701…`) | `shasum -a 256` against `audit/raw/02-manifest-before.txt` | `98894c0` (partial) |
| What is already known to be wrong? | `audit/FINDINGS.md` (F-01…F-38) | — a report, not a check | `98894c0` (partial) |
| Orchestration detail | **retired** — archived at `docs/history/`, see `docs/decisions/0001-retire-the-orchestration-documents.md` | `NOT YET ENFORCED` — archival only; 20 stale claims, not a current description | `e3862f2` |

## 4. Invariant index

IDs are frozen and append-only in both namespaces. Wording lives in `docs/invariants.md` — never
restate it here. The **R-namespace is §2 above**; this indexes L only. Test paths are relative to
`tests/interaction/`.

```text
L-1   Canonical agents[] representation        → UNENFORCED (F-03, G2)
L-2   No hidden schema fallback                → UNENFORCED (F-03, G2)
L-3   v1 audits, v2 executes                   → test_orchestration_audit.py::test_a_v1_workflow_validates_and_audits_but_the_runtime_refuses_to_execute_it
L-4   Frozen decision inputs                   → test_orchestration_colony.py::test_the_evaporation_lease_comes_from_the_frozen_spec_not_live_history
                                                 L-4.b DELEGATED → L-14
L-5   Availability is not execution            → test_e4_shared_capacity.py::test_metric_families_outcome_and_cost_are_present_allocation_and_lease_are_not
L-6   No self-certification of authority       → test_orchestration_audit.py::test_replay_detects_a_permission_and_a_claim_event_that_disagree
L-7   Declared authority only                  → test_orchestration_colony.py::test_no_commitment_policy_can_turn_a_failing_checker_into_acceptance
L-8   No workforce inference                   → test_orchestration_colony.py::test_the_runtime_never_invents_a_capacity_model
L-9   No mechanism leakage into the runtime    → test_orchestration_colony.py::test_the_runtime_imports_no_colony_mechanism_directly
L-10  Experimental identity is inert           → test_e4_shared_capacity.py::test_no_policy_layer_module_names_the_experiment_in_its_code
L-11  Replayable decisions                     → UNENFORCED (F-02/F-04, G1)
L-12  Observation is not ontology              → UNENFORCED (audit §9, G3)
L-13  Durable authority needs durable evidence → UNENFORCED (F-02, G1)
L-14  Replay-relevant nondeterminism is frozen → UNENFORCED (F-04, G1)
L-15  Bounded control; drain survives exhaustion → test_platform_conformance.py::test_platform_operation_exhaustion_cannot_prevent_safe_release
L-16  Atomicity of decision and consequence    → test_platform_atomicity.py::test_composite_commit_failure_rolls_back_publication_and_decision
                                                 L-16.d UNENFORCED (G4)
L-17  Call identity and recovery               → test_colony.py::test_call_ids_are_stable_across_reclaims_unlike_the_epoch_id
L-18  Narrowing-only delegation                → test_orchestration_workflow.py::test_admitted_children_narrow_the_parent_tools_reads_and_limits
L-19  Decomposition admission validated first  → test_platform_conformance.py::test_decompose_rejects_all_dependency_cycles_atomically
L-20  Terminality and dependency satisfaction  → test_platform_conformance.py::test_rule_none_is_explicit_terminal_abstention
L-21  Spend authority                          → test_provider_worker.py::test_provider_disabled_creates_no_call_rows
                                                 L-21.a UNENFORCED (G4)
L-22  The horizon-one identity                 → test_sequential.py::test_horizon_one_reproduces_every_repository_inspection_case_exactly
L-23  Each depth binds a distinct source       → test_sequential.py::test_per_depth_channels_never_buy_a_repeated_source_declared_with_full_copy
L-24  Bounded mechanism work                   → test_commitment.py::test_work_per_commit_is_bounded_explicitly
L-25  Oversized body is a settled rejection    → test_provider_worker.py::test_byte_rejected_receipt_settles_usage_and_is_not_unknown
L-26  Inter-task data flows through artifacts  → UNENFORCED (G3)
L-27  The ledger is the sole durable store     → UNENFORCED (G3)
L-28  Task tools within shared capability      → UNENFORCED (G2)
L-29  exact_v1 is a live contract              → UNENFORCED (G2)
L-30  Negative certification requires a test   → UNENFORCED (G0.5)  target: documentation
```

**Ceiling: 15 unenforced entries** (evaluated against the working tree) — 6 inherited, 9 surfaced,
0 deferred. The itemised register, with a closing gate for every entry, is `docs/invariants.md` §3.
Raising the ceiling fails the gate; baseline changes are their own commit.

## 5. Working method

Investigate before changing:

1. Open the implementation.
2. Open its callers and its tests.
3. Search for an existing abstraction before adding one. Prefer the smallest existing abstraction;
   introduce a new one only when two concrete use cases justify it.
4. Read the applicable ADR or invariant.
5. Make no claim about code you have not opened.

Then: smallest coherent change · one change per commit with the **why** in the body · a test that
fails before and passes after · nothing unrelated in the diff. If a change needs a new invariant or
reverses a decision, add the record to `docs/decisions/` in the same change.

Two learned the hard way:

- **Never delete a negative test or a structural guard test.** They encode invariants; removing one
  silently removes an invariant. Several here are held by exactly one test (F-06, F-07).
- **Do not leave load-bearing files untracked.** Seven orchestration modules have zero commits, and
  127 lines of this file were lost that way (F-01).

## 6. Commands

```bash
make check            # (PLANNED) canonical entry point; no Makefile exists yet
```

Paths below are relative to the repo root; test paths to `tests/interaction/`.

```text
BASELINE     python -m pip install -e '.[dev]'     editable install
             python -m pytest -q                   green baseline — ~16s, 1016 tests

COMMIT       python -m pytest -q                   ~16s
             pheroos-interaction --help            console script resolves — <1s

ARCHITECTURE pytest -q test_orchestration_workflow.py -k "import_no_runner or
               import_only_the_standard_library"   pure policy never imports runner;
                                                   runner imports only stdlib + pure pkg
             pytest -q test_layout.py              source identity covers every package path

INVARIANTS   pytest -q test_orchestration_colony.py test_e4_shared_capacity.py
                                                   82 tests — R-3..R-8, L-5, L-7..L-10 — ~2s
             pytest -q test_orchestration_authority.py    proposal/authority boundary

REPLAY       pytest -q test_orchestration_audit.py 48 tests, 17 tamper cases — L-3, L-6 — ~1s
             pheroos-interaction orchestrate --workflow examples/orchestration/workflow.json \
               --script examples/orchestration/script.json --output "$TMPDIR/run"
             pheroos-interaction orchestrate-replay --run "$TMPDIR/run"
                                                   offline verify: zero model, zero tool calls

MUTATION     (PLANNED — nothing runs; mutmut generated 233 mutants and executed 0)
             runner/contracts.py        decides what is valid     (MI 0.00 — F-15)
             runner/runtime_policies.py decides who executes      (FIFO stub passes 1007/1016 — F-07)
             runner/audit.py            decides what is verified  (replay_run, CC 68 — F-08)
```

## 7. Repository state warnings — 2026-09-17

CI green does **not** mean conforming. Each entry is dated and finding-linked.

- Seven `runner/*.py` modules and nine test files are **untracked** (F-01). `HEAD` does not contain
  the orchestration layer, so a `verified-at` sha in §3 does not pin that code. Check `git status`.
- `runner/runtime.py:23` and `runner/orchestration.py:548` assert "each task declares one agent".
  **That premise is superseded** — 4 of 7 shipped workflows declare two eligible agents per task.
  Do not re-derive conclusions from those two docstrings (F-03 adjacent; correction gate G0.6).
- `runner/colony.py` is **pending owner classification** (R-1). Do not merge, delete, or add a
  production dependency on it.
- **`audit/FINDINGS.md` is itself untracked** — not ignored, never added. Every `F-xx` id in this file
  resolves only in a working tree that has it; from a clean clone they all dangle. Same defect as
  F-01, one level up: the record of the problem shares the problem.
- The orchestration layer has **no current prose description**. Both former documents were retired to
  `docs/history/` carrying 20 stale claims (F-23, F-24); `ARCHITECTURE.md` has not yet been written.
  An accepted gap — preferable to a current description that is 20 claims wrong.

## 8. Safety boundaries

- No destructive git: no force-push, no history rewrite, no `reset --hard` on work you did not create.
  Prefer reversible operations.
- Never commit credentials, private state or local raw data. `research-data/` is gitignored and stays local.
- Never weaken a test, relax an assertion, or disable a check to make a run pass. If a check is wrong,
  change it in its own commit with the reason.
- A configured endpoint or an enable flag is not spending authorization. No live provider calls.

## 9. Definition of done

```text
[ ] behaviour implemented
[ ] relevant tests pass
[ ] a regression test added that fails before and passes after
[ ] static/structural checks pass
[ ] no invariant moved from enforced to unenforced
[ ] docs consistent with the change
[ ] diff contains nothing unrelated
```
