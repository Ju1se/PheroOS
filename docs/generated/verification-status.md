---
generated: true
generated-by: tools/generate_verification_status.py
generated-from-commit: 88be335
generated-on: 2026-09-17
edit: never — regenerate instead; a hand-edited generated file is F-24 in its next form
---

# Verification status

Regenerate with `python tools/generate_verification_status.py`.
Every number here is measured, never typed. Hand-maintained counts are F-24's root cause.

| | |
|---|---|
| Suite result | `1016 passed` |
| Tests passed | **1016** |
| Tests failed | **0** |
| Invariants in register | 39 |
| Enforcement references | 67 |
| Unenforced entries | **15** |
| References that do not resolve | **0** |

## Enforcement resolution

| ID | Title | Kind | Reference | Result |
|---|---|---|---|---|
| `L-1` | Canonical `agents[]` representation | UNENFORCED | `—` | F-03, gate G2 |
| `L-2` | No hidden schema fallback | UNENFORCED | `—` | F-03, gate G2 |
| `L-3` | v1 audits, v2 executes | test | `test_orchestration_audit.py::test_a_v1_workflow_validates_and_audits_but_the` | resolves |
| `L-4` | Frozen decision inputs | test | `test_orchestration_colony.py::test_the_evaporation_lease_comes_from_the_froz` | resolves |
| `L-4` | Frozen decision inputs | delegated | `L-14` | delegated to L-14 |
| `L-5` | Availability is not execution | test | `test_e4_shared_capacity.py::test_metric_families_outcome_and_cost_are_presen` | resolves |
| `L-6` | No self-certification of authority | test | `test_orchestration_audit.py::test_replay_detects_a_permission_and_a_claim_ev` | resolves |
| `L-7` | Declared authority only | test | `test_orchestration_colony.py::test_no_commitment_policy_can_turn_a_failing_c` | resolves |
| `L-7` | Declared authority only | test | `test_commitment.py::test_commitment_imports_only_dataclasses_hashlib_and_mat` | resolves |
| `L-7` | Declared authority only | test | `test_platform_atomicity.py::test_committed_scoped_decision_rechecks_current_` | resolves |
| `L-8` | No workforce inference | test | `test_orchestration_colony.py::test_the_runtime_never_invents_a_capacity_mode` | resolves |
| `L-9` | No mechanism leakage into the runtime | test | `test_orchestration_colony.py::test_the_runtime_imports_no_colony_mechanism_d` | resolves |
| `L-10` | Experimental identity is inert | test | `test_e4_shared_capacity.py::test_no_policy_layer_module_names_the_experiment` | resolves |
| `L-11` | Replayable decisions | UNENFORCED | `—` | F-02/F-04, gate G1 |
| `L-12` | Observation is not ontology | UNENFORCED | `—` | audit §9, gate G3 |
| `L-13` | Durable authority requires durable decision evidence | UNENFORCED | `—` | F-02, gate G1 |
| `L-14` | Replay-relevant nondeterminism is frozen | UNENFORCED | `—` | F-04, gate G1 |
| `L-15` | Bounded control, and drain survives exhaustion | test | `test_platform_conformance.py::test_platform_operation_exhaustion_cannot_prev` | resolves |
| `L-15` | Bounded control, and drain survives exhaustion | test | `test_platform_conformance.py::test_multilevel_caps_conserved_with_settlement` | resolves |
| `L-15` | Bounded control, and drain survives exhaustion | test | `test_orchestration_workflow.py::test_metrics_match_the_ledger_rows` | resolves |
| `L-15` | Bounded control, and drain survives exhaustion | test | `test_orchestration_workflow.py::test_cli_orchestrate_resume_of_a_finished_ru` | resolves |
| `L-15` | Bounded control, and drain survives exhaustion | test | `test_colony.py::test_abandoned_attempts_count_against_the_work_call_cap` | resolves |
| `L-15` | Bounded control, and drain survives exhaustion | test | `test_colony.py::test_max_items_bounds_the_sweep` | resolves |
| `L-16` | Atomicity of decision and consequence | test | `test_platform_atomicity.py::test_composite_commit_failure_rolls_back_publica` | resolves |
| `L-16` | Atomicity of decision and consequence | test | `test_orchestration_hardening.py::test_reported_usage_settles_in_the_receipt_` | resolves |
| `L-16` | Atomicity of decision and consequence | test | `test_platform_atomicity.py::test_atomic_work_budget_admits_only_one_concurre` | resolves |
| `L-16` | Atomicity of decision and consequence | UNENFORCED | `—` | gate G4 |
| `L-17` | Call identity and recovery | test | `test_colony.py::test_call_ids_are_stable_across_reclaims_unlike_the_epoch_id` | resolves |
| `L-17` | Call identity and recovery | test | `test_colony.py::test_matching_receipt_is_reused_before_reading_the_next_dept` | resolves |
| `L-17` | Call identity and recovery | test | `test_colony.py::test_mismatched_receipt_refuses_another_read` | resolves |
| `L-17` | Call identity and recovery | test | `test_colony.py::test_driver_failure_after_dispatch_at_depth_one_stays_unknow` | resolves |
| `L-17` | Call identity and recovery | test | `test_colony.py::test_scoped_platform_refuses_undeclared_tree_and_abandoned_i` | resolves |
| `L-18` | Narrowing-only delegation | test | `test_orchestration_workflow.py::test_admitted_children_narrow_the_parent_too` | resolves |
| `L-18` | Narrowing-only delegation | test | `test_platform_conformance.py::test_decompose_cannot_expand_parent_readers_an` | resolves |
| `L-18` | Narrowing-only delegation | test | `test_platform_atomicity.py::test_scoped_child_inherits_tool_arguments_reader` | resolves |
| `L-19` | Decomposition admission is validated before any durable wr | test | `test_platform_conformance.py::test_decompose_rejects_all_dependency_cycles_a` | resolves |
| `L-19` | Decomposition admission is validated before any durable wr | test | `test_platform_conformance.py::test_decompose_transfers_caps_and_parent_waits` | resolves |
| `L-19` | Decomposition admission is validated before any durable wr | test | `test_orchestration_workflow.py::test_parent_keeps_its_declared_join_reserve_` | resolves |
| `L-19` | Decomposition admission is validated before any durable wr | test | `test_orchestration_workflow.py::test_children_are_admitted_once_as_a_single_` | resolves |
| `L-20` | Terminality and dependency satisfaction | test | `test_platform_conformance.py::test_empty_candidate_and_wait_are_nonterminal_` | resolves |
| `L-20` | Terminality and dependency satisfaction | test | `test_platform_conformance.py::test_rule_none_is_explicit_terminal_abstention` | resolves |
| `L-20` | Terminality and dependency satisfaction | test | `test_orchestration_hardening.py::test_a_rejected_candidate_is_not_reported_a` | resolves |
| `L-20` | Terminality and dependency satisfaction | test | `test_orchestration_recovery.py::test_an_abstained_dependency_is_reported_by_` | resolves |
| `L-21` | Spend authority | test | `test_provider_worker.py::test_provider_disabled_creates_no_call_rows` | resolves |
| `L-21` | Spend authority | test | `test_provider_worker.py::test_provider_enable_is_exact_bool` | resolves |
| `L-21` | Spend authority | test | `test_anthropic.py::test_the_default_opener_follows_no_redirect_and_reads_no_` | resolves |
| `L-21` | Spend authority | fixture | `conftest.py::forbid_network` | defined, autouse |
| `L-21` | Spend authority | UNENFORCED | `—` | gate G4 |
| `L-22` | The horizon-one identity | test | `test_sequential.py::test_horizon_one_reproduces_every_repository_inspection_` | resolves |
| `L-23` | Each depth binds a distinct declared source | test | `test_sequential.py::test_per_depth_channels_never_buy_a_repeated_source_decl` | resolves |
| `L-24` | Bounded mechanism work | test | `test_commitment.py::test_work_per_commit_is_bounded_explicitly` | resolves |
| `L-25` | An oversized body is a settled rejection, never an unknown | test | `test_provider_worker.py::test_byte_rejected_receipt_settles_usage_and_is_not` | resolves |
| `L-26` | Inter-task data flows through published artifacts | UNENFORCED | `—` | gate G3 |
| `L-27` | The ledger is the sole durable store of task state | UNENFORCED | `—` | gate G3 |
| `L-28` | Task tools lie within the shared capability | UNENFORCED | `—` | gate G2 |
| `L-29` | `exact_v1` is a live contract | UNENFORCED | `—` | gate G2 |
| `L-30` | Negative certification requires a test  ·  `target: docume | UNENFORCED | `—` | gate G0.5 |
| `R-1` | `runner/colony.py` stays unreachable from production | UNENFORCED | `—` | gate G0.5 |
| `R-2` | `Runtime` and `run_colony` stay separate | UNENFORCED | `—` | gate G0.5 |
| `R-3` | The host finalizer is not a worker | test | `test_orchestration_colony.py::test_the_host_finalizer_takes_ready_order_and_` | resolves |
| `R-4` | L1 stays available and unexercised | test | `test_orchestration_colony.py::test_the_runtime_exposes_no_candidate_commitme` | resolves |
| `R-4` | L1 stays available and unexercised | test | `test_orchestration_colony.py::test_orchestration_work_refuses_candidate_arbi` | resolves |
| `R-5` | Arms differ only in declared policy | test | `test_e4_shared_capacity.py::test_the_four_cells_share_one_workload_once_the_` | resolves |
| `R-6` | Both arms declare the identical model config | test | `test_e4_shared_capacity.py::test_the_scripted_response_follows_the_task_and_` | resolves |
| `R-7` | Experiment identity never enters `runner/` | test | `test_e4_shared_capacity.py::test_no_policy_layer_module_names_the_experiment` | resolves |
| `R-8` | Commitment cannot overturn a checker | test | `test_orchestration_colony.py::test_no_commitment_policy_can_turn_a_failing_c` | resolves |
| `R-9` | Keep the ledger MRO | test | `test_orchestration_colony.py::test_the_orchestration_ledger_keeps_the_platfo` | resolves |

## Enforcement references per test file

| File | References |
|---|---|
| `tests/interaction/test_orchestration_colony.py` | 9 |
| `tests/interaction/test_platform_conformance.py` | 7 |
| `tests/interaction/test_colony.py` | 7 |
| `tests/interaction/test_e4_shared_capacity.py` | 5 |
| `tests/interaction/test_orchestration_workflow.py` | 5 |
| `tests/interaction/test_platform_atomicity.py` | 4 |
| `tests/interaction/test_provider_worker.py` | 3 |
| `tests/interaction/test_orchestration_audit.py` | 2 |
| `tests/interaction/test_commitment.py` | 2 |
| `tests/interaction/test_orchestration_hardening.py` | 2 |
| `tests/interaction/test_sequential.py` | 2 |
| `tests/interaction/test_orchestration_recovery.py` | 1 |
| `tests/interaction/test_anthropic.py` | 1 |

## Unenforced register

The ceiling is the count above. Raising it fails the gate; lowering it is a normal commit.

| ID | Title | Why / closing gate |
|---|---|---|
| `L-1` | Canonical `agents[]` representation | F-03, gate G2 |
| `L-2` | No hidden schema fallback | F-03, gate G2 |
| `L-11` | Replayable decisions | F-02/F-04, gate G1 |
| `L-12` | Observation is not ontology | audit §9, gate G3 |
| `L-13` | Durable authority requires durable decision evidence | F-02, gate G1 |
| `L-14` | Replay-relevant nondeterminism is frozen | F-04, gate G1 |
| `L-16` | Atomicity of decision and consequence | gate G4 |
| `L-21` | Spend authority | gate G4 |
| `L-26` | Inter-task data flows through published artifacts | gate G3 |
| `L-27` | The ledger is the sole durable store of task state | gate G3 |
| `L-28` | Task tools lie within the shared capability | gate G2 |
| `L-29` | `exact_v1` is a live contract | gate G2 |
| `L-30` | Negative certification requires a test  ·  `target: docu | gate G0.5 |
| `R-1` | `runner/colony.py` stays unreachable from production | gate G0.5 |
| `R-2` | `Runtime` and `run_colony` stay separate | gate G0.5 |
