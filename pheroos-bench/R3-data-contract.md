# R3 local closed-loop pilot v1

This is a finite engineering pilot with real local inference. It does not
declare efficacy, a confirmatory gate, hardware scaling, or full G4 acceptance.
Method: `r3_local_closed_loop_pilot_v1`; every row has
`counts_toward_verdict=false`. R0/E1/E2/E3 contracts and results stay unchanged.

The grid is four fixed worlds (two pure-function repairs, two closed-document
updates) by five arms, one repetition each. Four calls per episode have an
8,192 total input/output token ceiling; generation is limited to 256 tokens
per call and prompt plus generation to 2,048. At most 80 experiment calls and
163,840 reserved total tokens are possible. Known failed candidates still cost
their full measured tokens. Unknown dispatches retain their durable allocation.

All arms share model weights, chat template, tools, verifier, source updates,
episode budget, sampling (temperature .7, top_p .9, top_k 50), and seeds matched
by world/step. One CUDA-resident model executes requests sequentially; agent
IDs denote separate logical roles/working contexts, not concurrent GPU copies.
Arm order rotates by world; timing remains a diagnostic with no causal claim.

- `single`: one agent, complete previous work history.
- `independent`: four independent proposals, no model-visible cross-sample work;
  the same public verifier selects a valid current-version candidate.
- `manager_graph`: fixed planner/implementer/reviewer/finalizer chain, receiving
  the preceding proposal and tool receipt; not a learned dynamic manager.
- `blackboard`: four roles consume the last two proposals and tool receipts.
- `versioned_blackboard`: same bounded board, exact proposal deduplication and
  current task-version filtering. This is a simple R3 rule under test, not an
  efficacy promotion of R1's candidate or a public attention ABI.

Code is interpreted by a finite pure-integer AST evaluator, never executed on
the host. Visible tests feed back; final hidden cases do not. Evidence documents
update at step 2 in every arm. Exact current citation versions are required.
Final selection uses public verification only, never hidden scores. Proposals
do not grant authority: the external runtime requests fresh public Core
Baseline Output gates for generation and for publishing verified artifacts.
The authority backend remains the explicit development reference Store.

The external SQLite ledger commits exact template prompt-token reservations
plus maximum generation before dispatch; usage settles before acknowledgment.
No automatic retry follows an unknown dispatch. Cancellation of arbitrary
in-flight generation and full durable issuer authority are not implemented.
The pilot ledger has its own tested boundaries; G1 guarantees are not inherited.

`freeze.json` is created before loading the model and binds source, tests,
configuration, task contract and model file hashes. Outputs are exclusive;
episodes and traces append and fsync. Transport, budget or usage errors are
`INVALID_ABORT`, not zero-cost statistical failures. Every attempted episode
is retained. Unknown ledger state is explicit and prevents valid measurement.

Raw prompts, model responses, token usage, test receipts, authority projections,
artifact-consumption IDs and selected candidates are preserved. Report each
world/arm quality and actual cost, peak CUDA allocation, elapsed time and JSON
transport bytes. JSON bytes exclude physical I/O and GPU internal transfers.
Observed artifact consumption followed by a different proposal is trace lineage,
not proof of counterfactual causation. Four worlds cannot support a general
quality noninferiority or cost-superiority conclusion.
