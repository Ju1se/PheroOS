# Independent read-only R3 audit

Result: **PASS_COMPLETE** for evidence consistency, with no observed
`INVALID_ABORT`, missing episode, missing call, incorrect selected outcome,
unaccounted completed call, or altered frozen source. This is an engineering
audit; every episode remains `counts_toward_verdict=false`.

The complete four-world, five-arm grid contains 20 episodes and 80 model calls.
All 20 final selections and declared final verifications reconcile. Eight
episodes succeed. Token totals are 35,584 input plus 4,536 output = **40,120**.
The 63 rejected candidates consume **31,500** of those tokens and remain fully
included. All final SQLite ledgers have zero reserved and zero unknown tokens.
All per-call reservations, cumulative snapshots, and persisted request/receipt
rows agree with the traces and episode summaries.

All 97 authority projections were recomputed through the public core:
80 generation permissions and 17 verified-publication permissions. Task,
version, scope, payload, and permission bindings match. Model prompts contain
exactly the declared system instruction, public task inputs, and earlier
public-feedback records selected by the declared arm. Hidden final cases and
final scores do not appear as feedback. Frozen source hashes match, and all
eight installed runtime module files match their frozen source files.

A separate offline CPU recount retokenized all 80 prompts with the frozen
model's actual chat template: **35,584**, matching every recorded prompt count.
All eight model-file SHA-256 values match the pre-run manifest. Completion
counts reconcile with durable receipts and the frozen implementation's
generated-tensor length; raw generated token IDs were not retained, so decoded
text alone cannot independently reconstruct every special output token.

The frozen `changed_after_shared_consumption` metric reports **nine raw-text
changes**, which must not be described as nine semantic adaptations. Five new
proposals were rejected. Three accepted clamp proposals match their consumed
verified proposals on 585 independent integer input probes each. The fourth
accepted proposal repeats the same evidence answer. These observations supply
no demonstrated improvement from sharing; finite probes are not a general
semantic-equivalence proof. The frozen metric and outcomes were left intact.

Elapsed times are descriptive diagnostics. Concurrent host acceptance tests
contaminate cross-arm timing comparisons; these numbers do not establish
GPU throughput, scaling, or a performance ranking.

Evidence: `independent_audit.py` / `independent_audit.json` and
`independent_prompt_recount.py` / `independent_prompt_recount.json`. The audit
scripts perform no model generation and do not change frozen source, test,
configuration, contract, or outcome files.
