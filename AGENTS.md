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
- Do not add LLM decomposition planning, message channels, automatic paid instrument runs, or framework-superiority conclusions.
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
