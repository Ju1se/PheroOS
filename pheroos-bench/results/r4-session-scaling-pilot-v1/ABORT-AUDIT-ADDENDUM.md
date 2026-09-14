The completed independent abort audit reports `ACCOUNTING_AND_ABORT_INTEGRITY_PASS` (exit 0). The original collection remains `INVALID_ABORT`, with `FULL_GRID_INVALID_NO_USABLE_PAIRED_EXPORT`. This integrity result supplies no efficacy verdict, R4 completion, confirmatory evidence, or phase promotion. The original report and raw evidence remain unchanged.

All 264 declared cells are accounted for: 204 completed episodes (160 call-limit stops and 44 budget stops), one attempted aborted episode, and 59 unstarted placeholders. Unstarted accounting remains null. Across the 205 attempted episodes, durable ledgers reconcile to 2,824,212 tokens (2,514,597 input and 309,615 output), 5,891 model calls, and 5,890 tool calls, with zero reserved tokens, unknown tokens, or unknown calls. These totals include failed objectives and the aborted episode.

The audit checked 17,671 authority bindings, 5,935 prompt tokenizations, 5,890 publications, and 53,353 causal events. A final hash recheck matched all 660 frozen inputs, 621 original evidence files, and three audit source files. No inference or GPU generation ran during this audit.

The aborted cell retains 4,248 known tokens from eight model calls and seven tool calls. Its final model receipt charged 554 tokens; no following tool evaluation was dispatched. The recorded `LeaseLost` occurred after that settlement and before the next tool reservation. The requested lease was 3,600 seconds using `time.time`; episode duration used `time.monotonic_ns` and recorded 22.334 seconds. Trace events contain no timestamps, and cancellation cleared the retained lease expiry. Adjacent episode file mtimes show a large wall-clock gap, but they do not establish host suspension or a clock jump. The exact failed lease predicate and external cause remain **undetermined**.

Exact audit identities:

| Artifact | SHA-256 |
| --- | --- |
| [Final audit](abort-independent-audit-v1.json) | `723d36f07fc5cccd1466d55ca6e890983c0a41f68c817e7212189666c31d8bf5` |
| [Command and final hash receipt](abort-independent-audit-execution-v1.json) | `2dbd8ce42b7697c116c013f6dfa65003d29a2f34929ce913297fedf059b86820` |
| [Abort auditor](../../tools/audit_r4_session_scaling_abort.py) | `64749115975131c0f248dd373820ca4fbd0398204cc84701e0d02e37a804a757` |
| [Unchanged complete-grid auditor](../../tools/audit_r4_session_scaling.py) | `37566becd0d2ef9da1cad9e344eca372e3c6e45dd1d2528466643d9c85071877` |
| [Unchanged shared audit helpers](../../tools/audit_r3_session_capability.py) | `e39c1ce04abcc31a067c835c9689c8f2d9641a02fde6bac60fd153c4ec473b3b` |

The command receipt records the exact interpreter, arguments, environment overrides, working directory, observed exit code, and hashes of the audit, progress log, targeted aborted-episode receipt, and checker sources. Completion token IDs were not retained; completion charges reconcile to the durable receipts and frozen adapter implementation.
