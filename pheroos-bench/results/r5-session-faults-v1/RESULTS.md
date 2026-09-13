# R5 installed Session fault pilot: results

Status: **collected once; independent audit v2 INTEGRITY_PASS; PENDING_ROOT_REVIEW**.
Method `r5_session_faults_v1`; `counts_toward_verdict=false`. This is finite engineering evidence. The source study, its 38 outcomes, and the first audit failure remain unchanged.

## Problem, hypothesis, and mechanism

The concrete question is whether the installed Session retains cost uncertainty and fences stale execution across selected process, transport, and store faults in the existing two-agent inspect → verified artifact reference → submit journey. The hypothesis is that durable reservation/dispatch/receipt/publication transitions, current public-core authorization, lease epochs, and immutable artifact references preserve each declared invariant at its specified injection boundary.

Session remains the single accounting owner. Only an independently verified artifact matching a settled `tool.evaluate` receipt can be published. Model receipts remain proposals. A checkpoint or mailbox message carries data and references; it cannot restore revoked permission or an expired lease.

## Baselines, implementation, and design

This pilot has no comparative policy arm or efficacy baseline. Each case has a fixed expected state/effect/accounting oracle. The five earlier PilotLedger fault cases remain historical evidence and do not substitute for Session checks. Protocol-core and the frozen installed runtime were unchanged.

The [frozen configuration](freeze.json) declares all 38 identities below, two agents, two work items, version 1, and the same deterministic exact-integer evaluator. Limits are 64 tokens, 8 calls, 2,048 context bytes, 1,024 artifact bytes, and a mailbox of 2 messages / 1,024 bytes; the byte-limit counterexample explicitly uses a one-byte bound. Synthetic model usage is prompt 2, maximum completion 8, actual received completion 1. These are bookkeeping fixtures, with zero actual model generations and zero paid-provider calls.

The [source execution receipt](execution-receipt.json) records one invocation, process exit 0, and the reviewed R4 prerequisite. Nine cases retain the selected control marker, worker exit `-9`, and no acknowledgment after SIGKILL, followed by inspection in a fresh process. The precommit case interrupts an actual SQLite receipt update before commit. Three lock cases use a second SQLite connection and retry the blocked storage operation after release. Two cancellation cases execute the two deliberately serialized process orders. Delayed reply settles after committed cancellation; lost reply observes the declared 50 ms timeout before killing the child. Malformed packets, wrong correlations, adapter failures, and corrupted proposals are deterministic caller injections. Database corruption affects a disposable copy; the intact original is retained.

## Tests and independent audit

The prepared v1 checker passed 52 temporary-fixture sensitivity tests. After collection, v1 exited 2 with one `AUDIT_MISMATCH`: it expected the literal exception label `ValueError` for malformed JSON, while the unchanged harness correctly retained the concrete subclass `JSONDecodeError`. The exact packet is `malformed JSON`; parsing reproduces `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`. This was a checker error, with no observed harness or runtime defect.

The separately identified [v2 adapter](../../tools/audit_r5_session_faults_v2.py) pins and runs every v1 check. Its sole correction requires that exact packet, full refusal text, original unpublished dispatch, and 10 unknown tokens / 1 unknown call. Twelve targeted tests passed, including rejection of the old literal label, altered text/packet, missing uncertainty, missing raw inspector fields, and an altered legacy expectation. A separate agent reviewed the adapter without edits or study execution. No fault case was rerun.

The [v2 audit](independent-audit-v2.json) completed with all 38 `INTEGRITY_PASS`. It binds raw inspector output to exports, reads committed SQLite and sidecar stores with integrity and journal checks, reconciles receipts and costs, checks direct mailbox/checkpoint tables, replays 53 current-authority projections and artifact lineage, and checks case-specific effects and terminal dispositions. All 628 frozen inputs and 163 original study files matched afterward; two additional retained files are the unchanged v1 audit and its execution receipt. The [v2 execution receipt](independent-audit-execution-v2.json) records exact command, interpreter, exit, hashes, and correction validation.

## Results and accounting

All 38 source invariants passed: 0 `FAIL`, 0 `INVALID_ABORT`, and no finalization errors. Passing an invariant does not imply completed recovery. Runtime dispositions are 13 `RUNNING`, 10 `UNRESOLVED`, 1 `COMPLETED`, 11 `CANCELLED`, 2 `REVOKED`, and 1 `ABORT_UNAVAILABLE`.

Across 37 readable primary ledgers: 18 known synthetic tokens, 0 reserved tokens, 70 unknown tokens, 10 unknown calls, 13 synthetic-model dispatches, and 23 tool dispatches. The foreign-session auxiliary ledger adds one zero-token tool dispatch. The intact original before copy corruption adds another. Thus unique available ledgers contain **13 synthetic-model + 25 tool dispatches**, retaining the same **18 known / 70 unknown tokens and 10 unknown calls**. The damaged copy's accounting remains null and unavailable. Its intact original is disclosed separately, without counting the corrupted copy as another execution.

The sidecars record **33 invocations**, with no duplicated logical call invocation in the observed fixtures. The foreign session shares one physical sidecar with its primary session; its effects are counted once. A dispatch killed before adapter invocation can have zero effects and still remain unknown. Zero unknown tokens never erase an unknown tool call.

Every row below passed the declared invariant and the corrected audit. Costs are primary-ledger costs; effects include the foreign auxiliary or intact-original invocation where applicable. All available reserved-token totals are zero.

| Exact case ID | Runtime disposition | Known tokens | Unknown tokens / calls | Sidecar invocations |
| --- | --- | ---: | ---: | ---: |
| `reserved_worker_kill:tool` | RUNNING | 0 | 0 / 0 | 0 |
| `reserved_worker_kill:model` | RUNNING | 0 | 0 / 0 | 0 |
| `dispatched_worker_kill:tool` | UNRESOLVED | 0 | 0 / 1 | 0 |
| `dispatched_worker_kill:model` | UNRESOLVED | 0 | 10 / 1 | 0 |
| `receipt_before_commit:default` | UNRESOLVED | 0 | 10 / 1 | 1 |
| `receipt_committed_before_ack:default` | RUNNING | 3 | 0 / 0 | 1 |
| `publication_committed_before_ack:default` | UNRESOLVED | 0 | 10 / 1 | 1 |
| `coordinator_restart_after_checkpoint:default` | COMPLETED | 0 | 0 / 0 | 2 |
| `transient_store_lock:reserve` | RUNNING | 0 | 0 / 0 | 0 |
| `transient_store_lock:receive` | RUNNING | 0 | 0 / 0 | 1 |
| `transient_store_lock:publish` | RUNNING | 0 | 0 / 0 | 1 |
| `cancellation_dispatch_order:cancel_first` | CANCELLED | 0 | 0 / 0 | 0 |
| `cancellation_dispatch_order:dispatch_first` | CANCELLED | 0 | 0 / 0 | 1 |
| `revocation_after_receipt:default` | REVOKED | 0 | 0 / 0 | 1 |
| `stale_lease_publication:default` | RUNNING | 0 | 0 / 0 | 1 |
| `reordered_duplicate_receipts:default` | RUNNING | 6 | 0 / 0 | 2 |
| `mailbox:duplicate` | CANCELLED | 0 | 0 / 0 | 1 |
| `mailbox:reverse` | CANCELLED | 0 | 0 / 0 | 2 |
| `mailbox:count` | CANCELLED | 0 | 0 / 0 | 1 |
| `mailbox:bytes` | CANCELLED | 0 | 0 / 0 | 1 |
| `mailbox:expiry` | CANCELLED | 0 | 0 / 0 | 1 |
| `provenance_substitution:unknown_reference` | CANCELLED | 0 | 0 / 0 | 1 |
| `provenance_substitution:foreign_reference` | CANCELLED | 0 | 0 / 0 | 2 |
| `provenance_substitution:wrong_version` | RUNNING | 0 | 0 / 0 | 1 |
| `provenance_substitution:mismatched_artifact` | RUNNING | 0 | 0 / 0 | 1 |
| `provenance_substitution:model_as_evidence` | RUNNING | 3 | 0 / 0 | 1 |
| `provenance_substitution:boolean_objective` | RUNNING | 0 | 0 / 0 | 1 |
| `oversized_reply_known_usage:default` | RUNNING | 3 | 0 / 0 | 1 |
| `transport:delayed_reply` | CANCELLED | 3 | 0 / 0 | 1 |
| `transport:lost_reply` | UNRESOLVED | 0 | 10 / 1 | 1 |
| `transport:malformed_reply` | UNRESOLVED | 0 | 10 / 1 | 1 |
| `transport:wrong_correlation` | UNRESOLVED | 0 | 10 / 1 | 1 |
| `adapter_failure:tool_before_effect` | UNRESOLVED | 0 | 0 / 1 | 0 |
| `adapter_failure:tool_after_effect` | UNRESOLVED | 0 | 0 / 1 | 1 |
| `adapter_failure:synthetic_provider` | UNRESOLVED | 0 | 10 / 1 | 0 |
| `stale_checkpoint:default` | REVOKED | 0 | 0 / 0 | 0 |
| `corrupted_signal:default` | CANCELLED | 0 | 0 / 0 | 1 |
| `corrupted_database_copy:default` | ABORT_UNAVAILABLE | unavailable | unavailable | 1 |

## Negative findings and recovery distinctions

The ten unresolved dispatches were retained without redispatch or assumed free completion. Reserve-only kills abandon the reservation and reclaim work at epoch 2. A receipt committed before acknowledgment is replayable without a second charge, but its work remains running; that branch does not complete the journey. Publication survives its committed boundary while an additional 10-token dispatch remains unknown. Only the coordinator-checkpoint restart case completes both work items. Cancellation and revocation remain effective when known late receipts settle. Oversized known-usage output retains its three-token charge and bounded rejection metadata without usable replay or publication. The corrupted copy remains `ABORT_UNAVAILABLE`.

## Confounds and what is not proven

Control markers, exit codes, reported timeouts, committed process orders, and refusal strings are trusted collector observations. Raw control-pipe bytes, kernel kill traces, historical clock instants, and rejected-operation arguments were not retained. Final state and causal authority/artifact bindings are independently replayable; exact failed lease predicates and transient returned contexts/mailboxes are not. `before` snapshots have case-specific capture points and are not uniformly pre-fault.

Logical-clock expiry does not establish suspend or wall-clock-jump robustness; the original R4 interruption's external cause remains undetermined. The two cancellation orders do not sample simultaneous races. `recovery_elapsed_ns` covers crash-inspector work, `inspection_sequence_elapsed_ns` the inspector's full sequence, and `elapsed_ns` the parent case; they are separate descriptive measurements, with no isolated performance or throughput claim.

This bounded local sidecar does not prove exactly-once arbitrary external APIs. The pilot tests no real model/provider failure, GPU recovery, multi-host failover, physical power loss, hostile-host authentication, or long-run reliability. Mailbox/checkpoint bounds do not bound indefinite Trace growth from repeated trusted operations. There are no confidence intervals, policy-effect conclusions, independent efficacy samples, production-readiness claims, or public-API stability promotion. Historical E1/E2/E3 evidence and thresholds remain unchanged.

## Frozen identity and next gate

The installed target was `/tmp/pheroos-session-site`, using `/home/scott/projects/PheroOS-runtime/.local/venv312/bin/python`, Python 3.12.3. Interpreter SHA256: `e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f`. Complete installed core/runtime/JSON identities are in [freeze.json](freeze.json); the contract's pre-execution status is retained as frozen planning text.

- `R5-session-faults-v1-contract.md`: `e294b3063c8cdcf6f940c7f88c16d521ed99c93bfb80eb83079128ae444e0c24`.
- `r5-session-faults-v1.json`: `4ac51c2c114a29cffbfa0c73b47147e801a9e20c9c798e8eeff672f8cc5754d8`.
- `test_r5_session_faults.py`: `8d6db18fb3d3df91790efaa9c1d6c8b16bb5f2b1898985726c215f1b2d37d310`.
- `r5_session_faults.py`: `04c447e434a697106552984921c3fecc4d9d7e2c1b373b92a344f338c6484745`.
- Installed `session_v1.py`: `a1c0750b12ea2d3b3cfabc42c29f2616c6160ef0b1641cd573d67db3d6d9a39e`.
- Installed `session_driver_v1.py`: `4bc372f2f64d01efa0b4c1da896db27793b8ef473bd85e20cbba025e13839b08`.

- Audit v2: `9f0ba43d43c9a997f7634fe1d4d43e2558984f7fc1d269afc61071b757a1eb9f`.
- Execution receipt v2: `c8bef7349660f9aa65e03e2c866ad5ab22a6f1131b930ac2ccd412c89204790c`.
- Preserved failed audit v1: `c08b741735d9e542c9cb4edb5f319793b61dab765864412798f90354f70095ec`.

Recommendation: accept the finite R5 engineering gate after root review of the unchanged study and narrow checker correction. The next decision is a separate runtime-maturity/consumer review with these limits explicit. No soak, new experiment, or further fault rerun is implied by this report.
