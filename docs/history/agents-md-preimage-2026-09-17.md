# PheroOS

Active scope: the local binary inspection policy, thin execution, the bounded platform transitions explicitly authorized in this round, and the explicitly authorized colony control layer.

- `src/pheroos_interaction` holds only pure policy and records; it must not import runner, experiment ground truth, evaluation, or providers.
- `runner` holds local source access, execution, and replay; pyproject maps the packages explicitly under the single namespace `pheroos_interaction`.
  `experiments/current/inspection-example` keeps only the example data needed to run and is not a Python package.
- Add only the logic that the current policy, the authorized platform transitions, and the authorized colony control layer need; do not restore deleted mechanisms, research commands, OS, or protocol frameworks.
- Keep real scope/version/readers, tool declarations, bounded state, durable reservations, cancellation, and never-retry for unknowns.
  One-step inspection is the policy scope of the default command; multi-step trees are used only inside the explicitly authorized colony control layer, and execution caps come from configuration.
- Model assumptions and losses are configured explicitly; format validation is not content truth, dependency identification, or probability calibration.
- The scope is a trusted single-machine serial task; no claim of the old authority/BFT/finality or malicious-host guarantees.
- Source identity covers every installed core and runner package path, including external directories of editable installs; cover new packages when they are added.
- Historical raw data and the cost ledger stay as they are; new output goes to new directories, and old source is not restored to replay old experiments.
  Current local inspection replay matches the frozen plan and the original receipt; historical source differences must be declared explicitly.
- The generic provider adapter is disabled by default and only the caller injects transport/extract; no real service, credentials, or provider CLI is configured.
  Neither a flag nor a code upload authorizes a paid experiment; tests use only local fake transports and never reset the ledger.
- The existing GitHub push authorization for the pruned tree and README remains in force; keep Git history, never force-push,
  never upload credentials, private state, or local raw data, and do not touch unrelated worktrees or PRs.
- Install with `python -m pip install -e '.[dev]'`; test with `python -m pytest -q`.
  After changes, verify the installed CLI, the credential-free local example, and replay of the relevant original inspection records.

## Authorized platform layer

- `PlatformMixin`/`PlatformSession` live in runner; enumeration, cap transfer, leases, and candidate arbitration are explicit choices
  that do not change `plan_inspection`, the default inspection configuration, or the statistical scope of one-step inspection.
- Work budgets are checked inside the Session's reservation transaction; the "write first, then abandon on overflow" repair path must not return.
  Decomposition must transfer the remaining cap, validate the full dependency graph and the cumulative child/depth/work-item limits, and the parent waits for its children's artifacts.
  Children with a scoped inspection inherit source, tool, arguments, and readers; access must not be widened around the declaration.
- Platform admission operations and claims have a durable operation cap. release, settlement, and cancellation can still drain state after the cap is exhausted;
  no-entry only affects scheduling and cannot resolve an unknown dispatch. Renewal must not shorten expiry and does not change the epoch.
- A candidate's loss is the caller's declaration, not a probability certificate computed by the platform; commit's selection, receipt publication, and decision record must be committed atomically.
  WAIT and no-candidate are non-terminal; abstain is terminal and does not buy the inspection again. Dependencies still require a published artifact; a child's abstention fabricates no artifact,
  its parent stays blocked, and the host cancels or declares a separate application policy; there is no silent retry.
- The worker only does a bounded sweep and ledger recovery; unknowns are never retried, and an existing matching receipt is recovered first. A provider request must be fully frozen before reservation
  and the exact token contract is unchanged; transport/extraction failures after dispatch stay unknown, and a receipt that only exceeds the byte bound with valid usage keeps the existing settlement semantics.
- Do not add message channels, automatic paid instrument runs, or framework-superiority conclusions. LLM decomposition planning exists only
  as the opt-in, host-admitted mode of the authorized orchestration layer below and must not be added anywhere else, least of all to this platform layer or to the worker.
  A LangGraph/ADK/CrewAI comparison must actually be run under the same fault injection and mock scenarios; the local suite cannot stand in for it.

## Authorized colony control layer (2026-09-16)

- This layer is an explicitly authorized bounded extension: `src/pheroos_interaction/sequential.py`, `commitment.py`, `leases.py`,
  and `runner/colony.py`; `runner/policies.py` gains `pick_response`. The default `inspect` command, `plan_inspection`, the default
  inspection configuration, and the statistical scope of one-step inspection are unchanged; `plan_sequential(horizon=1)` must equal
  `plan_inspection` field for field, including the global tie budget.
- The L0 finite-horizon tree does backward induction in joint-probability coordinates only at the declared corner `(q_low, rho_high)`; it computes no posteriors and never divides by a marginal probability.
  The corner's least-favorable status comes from the Blackwell garbling matrix (Theorem 1); it bounds expected loss within the declared family and is not proof of real source independence or calibration.
  The certificate (a Bernstein enclosure over a shared box, or per-source corners) bounds only the fixed tree's expected risk within the declared box, never a single realized loss.
  Each depth must bind a distinct declared source: re-reading the same fingerprint returns the same evidence, not a fresh conditionally independent observation; a repeated source should declare rho=1.
  An unknown observation at any depth terminates as abstain without replanning.
- L1 commitment is a pure local `rule(candidates, abstain_loss)`: the cross-inhibition ODE as a deterministic zero-byte filter
  (v_i=ℓ_0/ℓ̂_i, σ=σ*(v̄), v̄=ℓ_0/(ℓ_0−c_t·T_dec), with the symmetry-breaking perturbation determined by the declared seed and a hash of the call id),
  or optimal stopping with recall. Both read only candidate metadata and exchange no messages; an ODE deadlock is a terminal abstention, and the ODE's integration work is
  explicitly bounded because the rule runs inside commit's transaction.
  `certified_loss` is the leaf's conditional expected loss given the observed history; it remains the caller's declaration and the platform does not prove its calibration.
  Revision 10 of the reference implementation labels the ODE as analysis-only; here both rules are explicit configuration choices and neither is claimed to be the optimal arbiter.
- The L2 response threshold θ_w=Δκ_w/c_t uses backlog drain time as the stimulus; the deterministic step is `pick_threshold`, and the Hill-exponent form requires the caller
  to supply a replayable draw. It is an evaluable heuristic, not a proven-optimal scheduler; with homogeneous costs it reduces exactly to FIFO.
- The L3 lease TTL is a one-dimensional search for argmin (1−F(τ))·C_dup + τ·p_fail·c_t. Under today's "unknown is never retried" semantics the input must be
  claim-to-dispatch lead times, and the TTL bounds no stall time; a zero TTL is excluded from the search; renewal never shortens expiry or changes the epoch; the no-entry mark is only a host scheduling hint and is off by default.
- The colony worker does only a bounded sweep, ledger recovery, and the tree walk: each (work, depth) call id is stable across re-claims and the arguments bind the tree digest;
  an existing matching receipt is reused first and a non-matching one refuses another read; an unknown after dispatch stays unknown; a rejected response forbids a fresh read;
  a reservation abandoned before dispatch is a known non-dispatch, not an unknown: its id is never reused, the next attempt at that depth carries the attempt count, and every attempt
  counts against the work's call cap; a tree whose worst-case remaining reads exceed the remaining calls is refused before any read; existing candidates are committed before a
  planner's purchase decision is honoured; a root stop action with no read terminally abstains as `plan_stop:<action>` because there is no receipt to publish.
  No LLM decomposition, message channels, or automatic paid runs; no claim of statistical optimality.
- The deleted pheromone field, swarm protocols, and OS frameworks are not restored; this layer does not change the trusted single-machine serial scope,
  and it authorizes no paid experiment, provider call, or framework-comparison conclusion.

## Authorized agent orchestration layer (2026-09-17)

- Frozen as **PheroOS agent orchestration v1: an L2-L3 governed runtime with an L1-compatible commitment boundary.**
  Execution is the bounded agent runtime; governance is the Session/Platform/Orchestration ledger; the colony policy plane has
  L2 ACTIVE, L3 ACTIVE, L1 AVAILABLE AT THE PLATFORM ARBITRATION BOUNDARY ONLY, and L0 EVIDENCE ACQUISITION ONLY.
  Do not describe this as an "L1-L3 runtime": the runtime asks the plane for two decisions, not three.

- This layer is an explicitly authorized bounded extension: `runner/contracts.py`, `tools.py`, `anthropic.py`, `orchestration.py`,
  `runtime.py`, `audit.py`, the three `orchestrate*` CLI commands and `examples/orchestration/`. It also amends two existing files,
  and nothing else: `runner/session.py` gains four behaviour-preserving seams (a contract-parameterised reservation body, a
  request-level admission hook re-run at dispatch, a per-call prompt-usage rule, a settlement hook and a shared publication tail),
  and `runner/platform.py` has `decompose` split into a transaction wrapper and a `_decompose(db, ...)` body plus one added field
  on the `platform.waited` event record (a clock stamp). The default `inspect` command, `plan_inspection`, the default inspection
  configuration, one-step inspection's statistical scope, the colony layer and every existing platform behaviour are unchanged,
  and nothing enables this runtime implicitly. It authorizes no distributed execution, no arbitrary code execution,
  no message broker, no autonomous regeneration loop, no paid experiment, and no framework-superiority conclusion.
- The governing rule is: agents propose actions, the trusted runtime validates them, the ledger admits and records execution,
  and model output never grants authority to itself. Every capability comes from a host declaration recorded in `orchestration_tasks_v1`
  and rechecked at reservation AND at dispatch, so a cached context retains no revoked authority. A proposal is data: exactly one
  `tool_use` block, validated against closed finite-JSON schemas; anything else is a recorded rejection that consumes a step and a
  rejection slot, never an instruction. Agents receive resolved inputs and an artifact resolver, never a Session, the audit API,
  a database handle, credentials or a path. This is a trusted-host application boundary, not a claim of adversarial isolation.
- Every model inference and every tool invocation is one ledger call. The durable logical operation key is
  `orch:sha256([run, task, version, kind, step])` with an attempt suffix after a known pre-dispatch abandonment; it survives lease
  changes and restarts, and a changed request for an existing key is refused rather than treated as a new operation. The existing call
  semantics stand unchanged: a settled matching receipt is reused without another dispatch or charge, a post-dispatch unknown is never
  retried or relabelled, a late receipt still settles, and cancellation, lease fencing and publication permissions still apply.
  Consumption is durable: one row in `orchestration_decisions_v1` per validated receipt, written in the same transaction as its
  consequence, so reopening repeats neither inference nor an admitted tool call nor a child admission.
- Typed outputs and final results are derived artifacts published only through `publish_derived`, which revalidates the proposal
  against the receipt inside one transaction and records lineage; `publish_received` and `commit` refuse orchestration work, and model
  and tool receipts carry no `artifact` key, so no legacy path can publish a raw model response. A received observation, a published
  intermediate artifact, an acceptance decision and a final task result are four distinct records. Publication is not a certificate of
  semantic correctness: success means the declared finite checker passed on the exact candidate digest, nothing more.
- Providers that cannot accept a predeclared prompt count use the explicitly versioned `bounded_v2` contract: the reservation is the
  host's declared bound, settlement accepts a reported prompt usage at or below it, and a report above it is recorded as an accounting
  violation while the call stays dispatched. `exact_v1` and every historical record are untouched and are never reinterpreted.
  The byte-to-token assumption and the prompt overhead are declared parameters, not measurements; after a violation the token cap no
  longer bounds what a provider may bill. Cache-control, streaming, thinking, images and other unsupported modes are refused, not translated.
- Decomposition is opt-in, disabled unless a task declares it, and admitted by the host, never by the model: the whole proposed graph,
  its references, the cumulative child/depth/work limits and the transferred budgets are validated before anything is written, and the
  parent keeps its declared join reserve. Children narrow and never widen: same agent, a subset of the parent's tools, reads limited to
  the parent's reads and their siblings, and step/tool/rejection limits at or below the parent's. A parent's declaration is never mutated,
  so an earlier step's context stays reconstructible. Scoped-inspection inheritance of source, tool, arguments and readers is untouched;
  orchestration tasks are not inspections and switch to no undeclared source. There is no replanning loop and no second decomposition per task version.
- The colony policy plane (`runner/runtime_policies.py`, named apart from the existing `runner/policies.py` claim rules it adapts) is the
  runtime's only door to L1-L3, so a baseline arm and a colony arm differ in the policy object alone and a measured difference is
  attributable to the algorithm rather than to a runtime rewrite. The arm is declared in the frozen spec and is therefore part of the
  spec digest and the run identity. A run records what RAN apart from what was merely AVAILABLE
  (`runtime_policies` for the allocation and lease arms, `platform_capabilities` for the commitment adapter and its
  `active_decisions` count), because reporting a commitment arm beside them would imply L1 was exercised when it was not.
- A model task declares the agents ELIGIBLE to execute it (`agent` for one, `agents` for several; the canonical record is the list).
  Where several are eligible, which one claims IS the allocation decision: the claiming agent owns the context and the frozen request,
  and offline replay recovers it from the call's own durable permission rather than from the binding it is checking. A task's tools must
  lie within the capability every eligible agent shares.
- L2 chooses which ready task a sweep advances. The worker capacity model is DECLARED on each agent, never derived: the runtime must not infer
  cheaper capacity from which agents happen to be idle, because that fabricates a workforce the workflow does not have. A declaration
  with no cheaper capacity, or naming the cheapest worker, is refused at validation rather than degenerating silently into FIFO, and a
  declaration is refused unless every agent declares a capacity and at least one has real cheaper capacity - an individually cheapest
  worker legitimately has none, but a workforce where no agent does has no choice to make. A declaration that defers everything stalls
  the run with an explicit reason - but the reason states only what was observed,
  because the declaration is a COUNT of cheaper workers and never an identification: the runtime cannot tell an absent worker
  from a busy one and must assert neither. Under one agent per task L2 IS FIFO; say so,
  do not claim swarm allocation. A host finalizer is a reserved identity with no model configuration, not a worker: it takes ready order
  and must never be given a fabricated cost to unify the interface.
- L3 derives the lease from a declared claim-to-dispatch lead-time model frozen in the spec. Never scan live history at execution time:
  the same workflow must yield the same TTL on every resume and replay. The TTL bounds no stall time and cannot resolve a dispatched call.
- L1 is DEFINED BUT NOT ACTIVE. It answers candidate commitment - among proposals carrying declared losses, publish one, wait, or abstain -
  and its home is `commit(rule=...)`. Orchestration has no arbitration locus: each task declares one agent, `max_candidates` is one, and
  `commit` refuses orchestration work. Do not add a runtime entry point for it, do not put a commitment block in the workflow spec, and do
  not manufacture a candidate contest to give it a caller. Validate it against a platform session with genuine competing candidates.
- Host acceptance is a verification rule and must NOT be routed through a commitment policy. A checker receipt bound to the exact candidate
  digest decides acceptance and the result publishes through the derived transition. The ordering is candidate proposals -> L1 selection ->
  deterministic verifier -> host acceptance -> final artifact: a commitment policy may choose among admissible candidates and may never turn
  a checker's FAIL into a PASS. L1 controls commitment among admissible candidate states; it does not override application truth conditions.
  A run whose tasks all completed but whose acceptance rule rejected the candidate is `rejected`, not `success`.
- L0 is NOT wired into agent reasoning and must not be. The sequential tree buys observations from declared binary sources with a declared
  `(prior, q, rho)`; an agent model step is open-ended generation, and treating the n-th inference as a measurement channel would fabricate an
  uncalibrated statistical model. The evidence-acquisition path keeps `plan_sequential`; the agent path does not use it.
- Keep the ledger MRO `OrchestrationMixin + PlatformMixin + Session`. These tables are a domain extension of the platform ledger, not a layer
  beneath it; do not reparent for diagram tidiness. Do not unify `Runtime` with `run_colony`: their state machines and call identities differ.
- Collaboration is the existing artifact mechanism only: no broadcast, broker, second store, vector memory or parallel message ledger.
  Provider conversation messages are serialized request data, not an authorization channel. Different agent identities are not independent
  evidence, and a model's self-reported confidence never becomes a `certified_loss`.
- Resume continues only legally executable unfinished work and resets no budget. Offline replay is separate: it opens the ledger read-only,
  rebuilds every frozen request from the recorded spec, receipts and authorized artifacts, re-parses proposals, re-applies the host rules
  and re-checks the accounting, with zero model and tool calls and no mutation; tampering or an unsupported source identity produces FAIL or
  LIMITED, never a silent pass. A new run is a new explicitly authorized experiment, not a replay. No claim is made that fresh inference
  reproduces a prior answer, and mock measurements are not evidence of model quality, cost saving or optimality.
- The concrete provider adapter targets the Anthropic Messages API, is disabled unless the host sets `PHEROOS_PROVIDER=1` and supplies
  `ANTHROPIC_API_KEY`, freezes the full semantic request before reservation, keeps credentials at the transport boundary and disables all
  retries and redirects. It is implemented and tested offline only, against local fake transports and a loopback fixture server; no live
  request was made and the flag is not a spending authorization.
- Commitment seams fixed in the same round: `optimal_stopping_rule` abstains at the equality boundary because the ledger publishes only on
  strict improvement, with the DP value unchanged; and `worker.waiting_rule` refuses a waiting configuration without a declared tick length, a declared
  source of future candidates and a bounded deadline. Its tick is elapsed ledger time between clock-stamped `platform.waited` decisions,
  so a tight sweep loop advances no decision clock and manufactures no arrival; the arrival probability stays a declared per-tick
  assumption. The default commit rule remains minimum loss with strict improvement.

## E4 preflight: shared-capacity workload (2026-09-17)

- `examples/e4/` holds the minimal workload in which an allocation rule has a choice: two workers both eligible for three independent
  tasks, with declared heterogeneous cost. Four cell specs (FIFO/response x fixed/evaporation lease) are generated from ONE shared
  workload and differ ONLY in the `policies` block, so A->B varies allocation alone and A->C varies lease alone. A test strips
  `policies` from all four and asserts the remaining projection digests to a single value.
- **Both workers declare the IDENTICAL model config.** Different models per worker would confound an allocation effect with a model
  effect and make `Y(response) - Y(fifo)` unreadable. Vary execution-resource identity, declared cost, allocation arm and lease arm --
  never the model, tools, budgets or inputs.
- An experiment is a declared workload fixture and nothing else: same runtime, same policies, same policy code, same verification path.
  Never add an experiment branch, constant or default to `runner/`; otherwise a measured difference cannot be attributed to the policy
  rather than to an experiment-specific code path.
- **Capacity is workflow-level and primitive**: `{latency_cost, service_time, workers: {id: {cost}}}`. `cheapest_cost` and
  `cheaper_workers` are derived by the policy plane per task from that task's eligible set. `service_time` is one shared scalar --
  the incumbent L2 mechanism takes a single value, so a per-worker field would silently define a new scheduling model.
- **The scheduler's decision object is `(agent, work)`**, never `work` alone, and ready queues are never deduplicated by work id.
- **Worker-enumeration order is the declared `agents` order** and is inside the spec digest. Never sort it.
- **Seeds are named in advance**, never searched for a desired treatment difference. The manipulation check asserts the MECHANISM
  (the Hill probability against the replayable draw), not the identity of whoever executed.
- This round establishes only that the four cells validate, run, resume and replay, and that the colony allocation produces a legally
  different allocation from FIFO. **No 2x2 result, effect size or comparison is claimed or has been run.** Known limits, recorded rather
  than hidden: the lease factor is declared but inert (nothing in this workload stalls or expires, so A==C and B==D exactly); the
  declared prices put the break-even outside the reachable backlog, so the response arm is constant in the backlog rather than
  backlog-responsive; and deferrals are unrecorded, so allocation pressure cannot be measured retrospectively.

## R3a closure record and first-read decision (2026-09-16)

- Under the economic scenario declared in this round, the labeled R3a data acquisition and monitoring-controller implementation are closed; R3b/P1 remain shelved,
  and the regeneration loop is outside the contract. The closure is a scenario decision, not a theorem that all data or controllers are worthless.
- This scenario compares only U (never read, terminate and abandon) with UA (read once, accept on PASS, otherwise terminate and abandon); fixed UA is selected.
  This is a decision record for a restricted application scenario, not a general default of the installed planner. The existing planner also allows reject and
  accept-without-reading; this scenario declares no complete losses for those alternatives, so it must not be used to rewrite `false_reject`,
  `plan_inspection`'s conservative-corner rule, or the execution entry point, nor does it mean the runner can publish downstream candidate programs.
- The selection rests on an explicit finite prior: p, q, ρ independent, with equal weight on the 21³ grid points p=.30:.02:.70, q=.70:.01:.90, ρ=.00:.01:.20;
  the existing symmetric binary positive-copy channel is used, not real source calibration.
  Losses in dollars: every wrong publication (including undetected ones) 30, a genuine terminate-and-abandon 10, a single read .002.
  Human review is not the abandonment here; the generation cost is already paid and identical for both, and renewal, retry, and switching are not counted.
- Under that prior and action set, U costs 10 and fixed UA has expected cost 8.702; the objective-selection gain is 1.298 per starting item.
  The first-read EVPI is 143214401/463050000 ≈ .30928496 per starting item; U's prior expected regret is
  1.60728496 = 1.298 + .30928496. Fixed UA is accepted at this prior-average regret, with no claim that pointwise regret ≤ .10;
  the roughly $2 objective-selection component of the regeneration model cannot be carried over to the first read.
- The current inspection's publication is receipt publication; there is no downstream candidate publication and no subsequent error-feedback statistics. If undetected errors still carry loss,
  the reporting frequency cannot identify the real error frequency, and independent evidence or a valid bound supporting the detection rate is required.
  If the undetected-error loss is declared zero, the objective, mature follow-up, and selection mechanism must be re-bound; the $30 potential-error-loss result above cannot be reused.
- The gain from this 39-cluster preflight cannot be extrapolated directly to the gain of a 12,000-item adaptive trajectory or to an engineering-cost ceiling.
  A future controller must evaluate regret for both actions and the retained action, declare switching cost, the handling when neither has sufficient assurance,
  exploration and latency, and report cumulative excess loss; fewer switches is not lower regret.
- The following are re-evaluation triggers, not automatic acquisition, implementation authorization, or proven break-even thresholds: steady-state decision volume reaching
  about 120,000 items; wrong-publication loss reaching about $300; undetected-error loss confirmed zero with real downstream publication/error feedback
  observable; or a usable independent executable ground truth appearing. Any change must recompute decision value and cost.
- Executable tests eliminate measurement error only under an H defined by an explicit test set/checker; execution cost, availability, budget,
  unknowns, and replay still have to be handled, a finite test is not general semantic correctness, and q=1, ρ=0 does not automatically cancel the decision to buy the check.
- Local basis: `research-data/results/r3a-monitoring-preflight-20260917T004336Z/`;
  this closure record: `research-data/results/r3a-contract-closure-20260917T010816Z/`.
  Both directories stay local and no historical raw data is uploaded; this record does not extend production capability.
