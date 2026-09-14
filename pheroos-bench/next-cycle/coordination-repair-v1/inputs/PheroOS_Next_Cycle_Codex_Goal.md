# NEXT-CYCLE GOAL: Make PheroOS Collaboration Behaviorally Real Before Scaling

## Mission and scope

Improve the existing PheroOS experimental OS candidate by addressing the bottlenecks exposed in PheroOS PR #35 and pheroos-runtime PR #1. Do not rebuild the OS or repeat the previous broad Master Goal.

This cycle must deliver:

1. A diagnosed and improved action interface.
2. Retrievable, version-aware evidence separated from attention and failure feedback.
3. Less duplicate work through safe reuse and task ownership.
4. A small, genuine 2–4-agent collaboration experiment with complete downstream rollouts and strong simple controls.
5. A bounded, reproducible engineering and research handoff, including negative results.

Biology-inspired coordination remains the research motivation. The immediate question is whether local information and outcome feedback change useful work, not whether the implementation looks like an ant colony.

Positive efficacy is not a completion requirement. An unexecuted experiment is not a negative result and cannot be marked complete.

## 1. Establish the actual starting state

Repositories:

- https://github.com/Ju1se/PheroOS.git
- https://github.com/Ju1se/pheroos-runtime.git

Previously reviewed snapshots, not assertions about the latest branches:

- PheroOS: `3604f5ce358ed6051c67e48906d240ac0b581f14` (PR #35).
- Runtime: `c94a2efd13ace1ac424b5ccb1dc0f885b810f82c` (PR #1).

Read current root and nested AGENTS.md files, both repositories' working-tree status, installed package identities, support matrices, final reports, gate addenda, source and tests. Resolve the actual relevant branches and compare them with these snapshots before editing. Do not assume main contains the PRs. Do not switch away from or overwrite uncommitted user work. Reuse a compatible existing workspace; otherwise create isolated worktrees/branches.

Start from these source entry points and their current successors:

- `pheroos-bench/results/master-goal-audit-v1/FINAL-REPORT.md`
- `pheroos-bench/EXPERIMENTAL-OS-CANDIDATE.md`
- `pheroos-bench/src/pheroos_bench/r4_tasks.py`
- `pheroos-bench/src/pheroos_bench/r4_session_scaling.py`
- `pheroos-bench/src/pheroos_bench/r2_scheduling.py`
- `src/pheroos_runtime/session_v1.py`
- `src/pheroos_runtime/session_driver_v1.py`
- `docs/session-v1.md`

Confirm rather than assume the audit findings: R1 added overhead versus simple dedup+TTL; R2 pressure did not change FIFO dispatch; much R4 cost went to publicly rejected actions; repeated inspections persisted despite context deduplication; shared-history N changes often preserved identical model inputs; some private high-N evidence conditions were structurally unreachable; mixed-model escalation was scheduled, not adaptive.

Public rejection is not synonymous with malformed JSON. Distinguish formatting, target selection, missing evidence, public-test failure and execution errors before choosing a fix.

## 2. Preserve ownership, history and safety boundaries

Keep protocol-core provider-neutral and unchanged unless an executable consumer demonstrates a concrete contract deficiency. Runtime owns execution state, leases, resource accounting, cancellation, receipts and artifact access. Bench owns tasks, experimental policies, model diagnostics, hidden evaluation and statistics.

Use existing public interfaces. Runtime additions must have concrete callers and tests. Do not import private core internals, introduce a second ledger owner, or add general-purpose manager layers merely to match this Goal.

Preserve E1/E2/E3, G1/R0, R1–R5, original failures, gates, source-bound artifacts and negative findings. Do not overwrite frozen files, normalize historical records or change old method meanings. Restore archived evidence only into an isolated, quiescent location; do not modify original SQLite/WAL/SHM through inspection.

New work gets a distinct experimental namespace such as `coordination_repair_v1`, new configs and fresh result directories. Keep changed behavior out of frozen historical entry points. This permits focused refactoring of live, unfrozen code and removal of newly introduced dead code, not deletion of reproducibility dependencies.

Do not push, merge, publish releases, alter system drivers, replace global environments or modify external services without separate authorization. Use the current verified local model/backend where available. Never silently substitute models.

## 3. Phase A — Diagnose actionability and prove task reachability

### A1. Decompose failure

Record a stable primary failure stage and optional secondary diagnostics for:

- transport/format;
- action schema;
- undeclared target;
- capability/current permission;
- missing or stale evidence;
- public semantic/test rejection;
- runtime/lease failure;
- budget/deadline stop;
- hidden final objective failure.

Preserve raw model responses, normalized representations, actual feedback and all incurred costs. Invalid actions remain in denominators. Hidden correctness must never be fed back to execution policies.

### A2. Repair the interface, not the answer

Expose concrete public target IDs and action schemas. Eliminate executable-looking placeholders such as `index_entry` or `function_name` from instructions where models can copy them as actions.

Prefer a small structured interface using public legal-action information. Use constrained decoding/tool schemas only when already supported or clearly justified, and apply the same interface to every compared method. It may restrict syntax and public target names; it must not encode the correct answer or silently turn a bad semantic choice into a good one.

Never silently repair semantic output. Charge retries and expose bounded actionable error feedback. Keep permissions independent from schema validity.

### A3. Run three separate capability diagnostics

Use separately identified development worlds:

- D0: obtain all required current evidence through metered tools, supply it, and require submission. This isolates integration/submission more than exploration.
- D1: obtain and supply that evidence, but allow normal free action selection.
- D2: require autonomous evidence acquisition, integration and submission.

Preparation is charged and disclosed. D0/D1 are not matched-budget collaboration efficacy arms. Their success does not establish autonomous intelligence.

Before collection, declare task IDs, budgets, model identities, validity metrics, diagnostic admission criteria and stopping rules. These are new design choices, not retroactive standards for old experiments. Do not repeatedly tune and rerun until a gate passes.

### A4. Demonstrate feasible completion independently

For each primary task/condition, construct a trusted scripted reference policy that solves it through the same public tools, visibility, permissions, version rules and resource limits. Do not let it read hidden answers. Charge its actions and mark it as an instrument diagnostic, not a learned baseline.

Check the minimum acquisition and submission opportunities after source updates. A condition that cannot supply enough actions or information must be labeled a structural negative control, not included as evidence of a model's capability limit.

Include both beneficial-sharing opportunities and tasks where sharing is unnecessary or distracting. New seeds of one tiny template do not by themselves establish broad task generalization.

### Phase A gate

Proceed to collaboration collection only when actions have an auditable failure taxonomy, the primary tasks have feasible public-tool solutions, and diagnostic evidence does not leave an obvious dominant interface failure unexplained. Otherwise finish provider-free development and report the unresolved bottleneck; do not spend an efficacy-sized budget reproducing it.

## 4. Phase B — Separate evidence, attention and work ownership

### B1. Make current evidence retrievable

Maintain a scope-bound index of immutable tool artifacts by source identity and version, with explicit provenance, supersession and validity metadata. Reuse existing Session artifact contracts where possible.

Attention TTL controls prominence, not the existence of still-valid evidence. Eviction from a four-item prompt window must not be the only way to lose access to a required current receipt. Preserve historical versions without treating them as current.

Verified provenance/receipt identity is not proof of arbitrary semantic truth. Keep tool verification, evidence validity, hidden task correctness and execution authority distinct.

### B2. Keep context bounded and queries visible

Provide bounded manifests/references and explicit metered retrieval. Do not replace bounded context with a free global transcript or unbounded hidden memory. Count index lookups, reads, refreshes, materialization, serialization and resulting model tokens.

Separate critical evidence from bounded private error feedback. Repeated invalid-action feedback must not indefinitely displace necessary evidence. A policy may query evidence that its access rights allow; do not silently grant global visibility to private controls.

Version notifications may expose only the public metadata allowed by the task. They must not leak updated content or answers without the same charged access used by controls.

### B3. Reduce repeated execution, not just repeated messages

For pure read/inspection operations, use version-aware reuse and in-flight task ownership. Key reuse by scope, tool/version, arguments and relevant source/work versions or state fingerprints. Disable reuse when freshness or side effects make equivalence unjustified.

If a matching inspection is already running, another agent can select different useful work or await its result rather than blindly repeating it. A valid existing receipt can be reused through the same access and accounting rules. Reuse does not create independent evidence.

Keep accounting-owned dispatch separate from work de-duplication. Never automatically redispatch an unresolved external call. Distinct source versions, revoked access and expired ownership must be handled explicitly.

### B4. Required tests

Cover duplicate/reordered delivery, concurrent attempts to claim identical work, source updates, stale cache entries, cross-scope access, cancelled/expired leases, unknown outcomes and late known receipts. Critical cancellation/revocation controls bypass ordinary attention suppression.

Record separate measurements for message duplicates, selected-provenance duplicates, repeated tool work and reusable artifacts. None is a substitute for the others.

## 5. Phase C — Create real 2–4-agent work organization

Stay within the finite Session architecture. A predeclared public task DAG is acceptable for this cycle; do not build a universal natural-language planner or dynamic graph engine without need.

Replace the experiment's fixed `agent = step % N` action chain as the primary coordination treatment. Agents must have bounded local/private state and actual eligible work choices. Task ownership and local demand should influence which unresolved work is undertaken next.

A minimal candidate may:

1. observe local unresolved demand and available artifact references;
2. choose and claim an eligible task;
3. produce a model/tool result;
4. publish an allowed artifact or bounded failure feedback;
5. update demand, release/reassign work, or request complementary capability.

Do not hard-code the correct solution or assign a privileged oracle to the candidate. All arms receive the same public task decomposition and information opportunities. Record real assignment, retrieval and dependency-resolution changes, not just messages or agent labels.

Sequential execution on one GPU is acceptable. It is not physical GPU concurrency. A single resident model can serve agents with distinct bounded state; do not load N model copies simply to claim N agents.

### C1. Keep the first comparison small

Begin with a lean declared grid, not the previous 1–32 sweep:

- one agent with the same total resource budget and reasonable multi-step tool access;
- strong simple blackboard plus provenance dedup/TTL at N=2 and N=4;
- the candidate at N=2 and N=4.

Add a manager or independent-sampling control only where relevant and budgeted. If a larger model is used, report it as a distinct capability/cost factor; do not hide it inside the candidate.

All methods share the corrected action interface, available tools, durable evidence facilities, evaluator and accounting. Candidate-specific work allocation/reuse must be isolated by ablation, not bundled invisibly with an interface or capability upgrade.

### C2. Check intervention relevance before expensive collection

On provider-free and development cases, measure whether candidate and control actually differ in work selection, evidence access or task composition.

Preserve same-input/agent-relabeling expected-null controls as instrument tests. Do not advertise those as primary intelligence scaling experiments. Identical behavior in development is a useful null finding and a reason not to launch a larger redundant grid.

## 6. Phase D — Test the causal value of sharing

From predeclared eligible prefixes, fork the same task/environment state into:

- relevant shared verified artifact references;
- withheld optional cross-agent sharing;
- size-matched irrelevant information, clearly non-authoritative or genuinely unrelated, without fabricated evidence.

Do not remove required permission records or make a branch fail through broken API preconditions. Use controlled mock/reference policies to verify each fork is semantically well-formed.

Execute full downstream rollouts with the same remaining budget, model/backend, declared random-stream policy, tools and exogenous update schedule. Fork state, prefix hashes and access differences must be recorded.

Fork task state into independently accounted branch sessions. Preserve origin lineage and validate imported artifacts through the declared trusted boundary. Do not transplant live leases, reuse parent permission roots as current authority, or let one branch mutate another. Any branch setup/reissuance work is measured and applied consistently.

Do not select prefixes because the actual branch already succeeded. Predeclare fork eligibility and sampling. Report eligible, ineligible and executed forks, including invalid actions and missing receipts.

The main diagnostic is unconditional downstream objective success and cost. Do not count only pairs where both actions are valid: valid-to-invalid changes are meaningful observations. Keep branch-conditional behavior measures secondary.

Matched irrelevant content must not carry false authority or hidden answers. Measure actual token lengths; disclose residual length differences instead of claiming exact matching.

Multiple forks or policies from one world are nested observations, not new independent tasks. Preserve prefix cost separately from incremental rollout cost and disclose the total diagnostic expense.

## 7. Measurement and experiment integrity

Use new method/config IDs. Do not silently reinterpret `r_paired_world_mean_v1` or historical `call_units`. Reuse it only when the endpoint and sampling structure fit; add a versioned analysis for nested forks or different estimands when necessary.

Report:

- total objective success and invalid-action stages;
- current-source coverage: globally observed, retained, accessible to each agent, and actually materialized in prompts;
- repeated inspections and reuse, with explicit denominators;
- input/output tokens, actual model/tool calls, control operations and overlapping logical byte counters separately;
- failed, rejected, cancelled and late work;
- first verified progress and final/stable success separately;
- sampled task worlds, repetitions, conditions and forks separately.

Do not equate equally weighted Python control operations with model calls, dollars or physical I/O. Token reduction is not a monetary/energy finding without the corresponding measurements.

Predeclare the completion/stop rule from observable public criteria; never use hidden scoring to stop execution early. Retain budget/timeout failures. Separate invalid evidence from valid task failure, and never silently drop costly or unresolved rows.

If not already covered in the current R0 code, add small synthetic checks for nonzero signed cost differences and unequal cell sizes. The 10-world all-one plus 90-world all-zero example must yield 0.10 under equal-world weighting, not 0.50.

Use worlds or task families as the sampling units justified by the design. Repeated seeds, agents, traces and resampled rows do not create independent evidence. Clearly distinguish self-consistency replay from an independently implemented oracle.

No confirmatory study is authorized in this cycle. Use pilot data to propose a separately frozen confirmatory design, power assumptions and test partition; do not call that proposal an executed result.

## 8. Local execution and resource limits

Use the existing working WSL/Linux and accepted Python/model environments. Record source commits/dirty-source manifests, model revisions, tokenizer/generation settings, package versions, GPU identity and actual inference concurrency. Do not install a new CUDA/PyTorch stack merely for this Goal.

Perform provider-free diagnostics first. Live collection is local-only with existing models. Default new-call ceilings for the entire cycle are:

- 500,000 input-plus-output tokens, including diagnostic branches;
- 1,000 model dispatches;
- at most one actionability campaign and one collaboration campaign;
- no paid API calls, automatic new model downloads or confirmatory collection.

These are conservative execution limits, not efficacy thresholds. Record the final configuration before dispatch. Respect any lower user-configured limit.

Reserve worst-case output against a campaign budget shared across workers: known settled usage plus outstanding reserved/unknown upper bounds must remain within the cap. A post-dispatch failure does not free unknown spending. Report observed over-budget or inconsistent usage as an explicit violation or unresolved observation; never erase it to make the budget appear respected. Do not silently raise limits or rerun failed campaigns. Finish independent implementation work and report blocked/incomplete collection when resources or hardware are unavailable.

Retain raw output, prompt identity, token-counting basis and receipt lineage. Save generated token IDs or suitable bounded reproducibility evidence when feasible; do not claim independent completion-token reconstruction from decoded text alone.

## 9. Bounded runtime and delivery hardening

Do only the runtime work required by this cycle and a small separate boundary-test set:

- real concurrent claim and cancel/dispatch/publication attempts using explicit process barriers;
- late receipt settlement without cancelled-task revival;
- fake-clock backward/forward behavior and documented restart semantics, without changing the host clock;
- explicit limits on the new index/cache/feedback retention.

Do not weaken transactional current-authority checks to improve throughput. Investigate read-lock contention only when measured; preserve linearizable cancellation/dispatch boundaries.

Do not add multi-host consensus, neural/evolutionary pheromones, Kubernetes, a plugin marketplace, a new public Governance layer, or 8h/24h soak work to this Goal.

Use a distinct experimental package identity and retain the previous cohort. Add an installed-Session integration job for the new consumer. Missing-Session skips are not integration passes. Run the relevant core, runtime, bench and installation regressions, and identify any interrupted/unrun suites honestly.

## 10. Deliverables and completion states

Produce a concise next-cycle directory containing:

1. baseline audit, scope and exact input identities;
2. targeted source changes in their owning repository;
3. behavior/contract tests and regression results;
4. actionability and reachability diagnostics;
5. frozen pilot configs, raw records, summaries and accounting;
6. intervention-relevance checks and full-rollout sharing diagnostics;
7. an installation/reproduction guide;
8. a final report and machine-readable status.

The final report must separate:

- engineering implementation;
- instrument validity;
- actionability/capability;
- coordination efficacy;
- finite fault behavior;
- unexecuted work and limits.

Allowed cycle states:

- `IMPLEMENTED_PILOT_COMPLETE_NO_PROMOTION`;
- `IMPLEMENTED_PILOT_COMPLETE_SIGNAL_REQUIRES_CONFIRMATION`;
- `IMPLEMENTED_COLLECTION_BLOCKED`;
- `ENGINEERING_GATE_FAILED`.

Use the existing repository vocabulary if equivalent, but preserve these distinctions. A pilot signal never creates a Stable or general swarm claim. A failed algorithm can still be a completed research delivery; a missing experiment cannot.

Keep reports and evidence proportional. Do not create an expanding hierarchy of acceptance gates, duplicate audits or new public dataclasses without a concrete need. Test count, archive size and number of PASS labels are not the objective.

## 11. Execution instructions

Do not stop after producing a plan. Audit, implement the smallest vertical slice, test it, run authorized bounded pilots when prerequisites are met, and report actual results.

Resolve ordinary implementation decisions from the repositories and this Goal. Request approval only for genuinely external or destructive actions, added spending/model downloads, raising caps, or unresolved scientific decisions that would change frozen evidence or the question being tested.

Proceed through the phases in order. Do not require a positive pilot result to report honestly, and do not replace an unpromising mechanism with a more complex one merely to obtain PASS.

The intended outcome is a system where shared evidence changes useful work in a demonstrable way. If the simpler strategy is as good or better, retain it as the preferred experimental default and explain the candidate's failure mechanism.
