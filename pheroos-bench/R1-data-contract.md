# R1 finite signal experiment v1

Private, provider-free bench experiment implementing reviewed-plan sections 5,
6/R1 and G3. This is a new experiment; E1/E2/E3/R0 evidence is unchanged. It
does not add a public attention API or install a default runtime strategy.

## Freeze and units

`python -m pheroos_bench.r1_signals --config r1-pilot-v1.json --output results/r1-pilot-v1`
creates a new directory exclusively. Before either split runs, `freeze.json`
records SHA-256 of implementation, config, tests and this contract, plus Python
and platform. Episode JSONL is opened exclusively and flushed after every row.
The final report checks those hashes. Existing output directories are refused.
Pilot seeds 0–7 and evaluation seeds 100–131 are disjoint; implementation and
analysis are frozen for both. No tuning takes place between splits.

The independent unit is one generated world, paired across five arms. Seed mod
4 gives equally weighted no-update, source-update, constraint-update and mixed
worlds. There are 8 agents, 4 tasks, 3 independently generated source beliefs
per task, 16 logical ticks, and 24 cloned observations per tick. Each agent
serves exactly one task; all arms have identical agents, inputs, control paths,
source accuracy, horizon, and cap of 96 data deliveries per tick. Actual usage
may differ below the common cap. These are deterministic program agents: LLM
calls and input/output tokens are explicitly zero, not inferred monetary costs.

## Mechanisms and fair baseline

All arms use the same exact task-relevance predicate. `full_relevant` delivers
every relevant observation up to the cap. `source_version_ttl` deduplicates by
recipient, task, source, subject, task/source versions and origin, with a
32-tick TTL; valid version changes bypass old suppression. `candidate` adds
monotonic per-source version suppression. `no_reactivation` removes version
and origin from the TTL key while retaining the same task relevance and
monotonic source-version guard.
`matched_sparse_random` samples the same number of data deliveries as the
candidate at each tick from all relevant observations, using an independent
seeded RNG. Matching uses candidate communication counts, never scoring truth.
The complete sampling index and sample quota are charged as routing traffic.

The strong baseline deliberately includes cheap relevance and competent
version handling. Since this finite world contains no genuinely new origin
for an obsolete version, candidate and baseline may have identical deliveries.
This null is informative: source/version dedup may already suffice. A positive
comparison only with full sharing or the ablation is not evidence that the
candidate is necessary.

Each receiver holds at most one latest belief per declared dependence group;
cloned origin events never increase independent support. The environment
declares three independent groups; no agent ID establishes independence. All
arms ignore stale source/task versions and decide by majority, with a tie or
missing evidence producing no answer. Task 1 changes source versions at tick 6;
task 2 changes its task constraint at tick 8 when selected by world type.
Reliable constraint notification invalidates old task-version evidence.
Task 0 receives stop, cancel and authorization-denial controls at ticks 12–14;
all bypass attention and data caps, block its answer, and are accounted.

World generation produces observations and scoring truth separately. Policy
and receiver interfaces accept observations only. Truth is consumed after
execution by the scorer. Source beliefs can be incorrect (accuracy 0.9); the
scorer does not replace them with truth or alter the policy after a failure.

## Records and analysis

Every scheduled world/arm records complete success or failure, including wrong
answers and missed corrections. Exceptions create explicit error rows and
invalidate the measurement; they cannot support a performance conclusion.
World success requires all agents answering tasks 1–3 correctly and task 0
blocked. Agent accuracy is descriptive, never an independent sample size.
Correction delay is ticks until every consumer of an updated task first holds
a correct answer; unrecovered changes are `null` and counted as missed. The
metric can count an already-correct noisy belief at tick zero after change.
It measures output correction, not proof that new evidence caused that answer.
Duplicate deliveries count repeated recipient/origin pairs; replicated delivery
factor is data deliveries divided by unique delivered recipient/origin pairs.
This process ratio does not increase the independent-source support count.

Costs count canonical UTF-8 JSON bytes at each actual simulated stage:
incoming field encoding, every recipient routing decision, delivered envelopes,
and key/value state reads and writes (including receiver answer computation).
All control traffic is included. Total accounted bytes sums these categories;
the same payload can incur multiple stage costs. This is reproducible logical
data movement, not measured RAM traffic, GPU use, execution time, energy, or
network wire bytes. There are no embeddings, compression, or uncharged selectors.
World construction, external scoring, and report persistence are measurement
infrastructure outside policy cost. Operation counts accompany every category;
delivery operations are messages, routing/read/write operations are internal.

Report all-world and case-stratified arm means and paired world differences in
success and total bytes; failed task episodes remain in both costs and quality.
Pilot and evaluation remain separate. No arbitrary noninferiority threshold,
superiority PASS, confirmatory claim, bootstrap-powered generalization, or
selection of the best arm is authorized by this small descriptive run. Stable
source IDs, trusted version metadata, a reliable transport, fixed subscriptions,
one finite TTL window, and binary tasks limit applicability. Real LLM behavior,
unknown dependence, transport loss and persistent multi-window attention require
separate experiments.
