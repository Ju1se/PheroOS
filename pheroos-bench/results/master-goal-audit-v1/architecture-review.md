# Experimental Session architecture review v1

**Decision: the finite consumer has a coherent implementation boundary; final
master acceptance remains open.** At this review R4 is collecting its frozen
264 episodes and the new R5 Session study has not run. This is a source and
existing-evidence audit, not another experiment or a production release review.
No runtime, policy, task, evaluator, frozen artifact or threshold was changed.
No tests or model calls were launched by this audit.

The controlling scope is the accepted master goal summarized in
[the status inventory](../../MASTER-GOAL-status.md), with the explicit finite
consumer in [the architecture inventory](../../EXPERIMENTAL-OS-CANDIDATE.md).
The older external `docs/reviewed-plan.md` is a research proposal, not an
additional acceptance checklist. In particular, its suggested cross-family
replication and context bands do not become new requirements for this running
finite study. Their absence limits generalization.

## Ownership and executable behavior

| Required boundary | Implementation and evidence | Assessment |
| --- | --- | --- |
| Agent and task lifecycle | `Session.create/claim/recover/cancel/revoke`, declared eligible agents/actions, finite dependencies, lease epochs and expiry; installed Session and two-agent journey tests | Present for a declared finite DAG. Waiting is represented by no claimable work; no separate agent-state database is necessary for this consumer. |
| One execution and cost owner | Session SQLite transactions serialize current lease, reserve, dispatch, receipt, cancellation and publication; `SessionDriver` executes outside transactions | Coherent. G1 Store and R3 PilotLedger are historical compatibility owners for different consumers; neither bills a new Session call. |
| Bounded local and shared communication | One bounded checkpoint per agent, current work/version/permission checks, bounded verified-reference mailboxes with address, expiry and acknowledgment; bench selects bounded history | Present for the finite runner. Attention does not delete durable evidence or become authority. |
| Artifacts and objective checking | Publication requires a received `tool.evaluate` call, exact artifact/response lineage, independent verification and fresh current authorization | A verified evaluation fact may report an invalid model action. It is not thereby a successful task answer. Hidden objective scoring remains a separate bench concern. |
| Cancellation, revocation and recovery | Direct control path bypasses the mailbox; durable revoked permission blocks new claims; stale leases cannot dispatch or publish; known late receipts settle without revival | Present in code and installed tests. The new finite R5 experiment must still test its declared fault boundaries. |
| Known and unknown resource use | Exact integer prompt/output reservation, call cap, immutable receipt settlement, conflicting-duplicate rejection; zero-token unknown tool calls counted separately | Present. Oversized replies with valid usage settle cost into a bounded rejected receipt; they cannot replay as usable proposals or publish. Unknown dispatched calls are never automatically reissued. |
| Replaceable capability | `ModelAdapter` plus explicit tool callbacks, opt-in `LocalModelAdapter`, no numerical/model imports by default | Present for this caller. The runtime has one concrete SQLite backend; no untested interchangeable persistence or provider reliability is implied. |
| Core authority and Trace | Public `RuntimeScope`, public governed Baseline Output path and canonical `TraceEvent`; no core runtime dependency introduced | Coherent under the declared trusted-host development profile. Current callbacks, not saved receipts or model messages, supply authorization. |

The authority adapter intentionally uses the public conformance reference
Store, outside the smaller consumer candidate. It creates fresh host authority
and returns non-reusable audit evidence. Session's durable permission state
fences cancel/revoke before another callback can dispatch or publish. This is
an explicit development exception; it does not establish durable issuer
custody, hostile-host authentication, or a production authority store.

The new source modules and all eight original runtime modules were independently
hashed against the installed acceptance manifest. Every external source and
every corresponding installed file matched. The existing wheel and sdist
acceptance each report **131 passing tests** from external working directories.
That is the complete runtime suite, including historical compatibility tests,
not 131 newly added Session tests. This audit checked those receipts and source
identities; it did not repeat their execution. Exact identities and checks are
in [architecture-review.json](architecture-review.json).

## Evidence gates and actual remaining work

| Phase | Current evidence | Remaining requirement |
| --- | --- | --- |
| G1 / R0 | Existing installed runtime regressions and mean-instrument/reconciliation checks passed; focused core checks passed | Retain the receipts. The interrupted full core suite is not a pass. |
| R1 | 64 complete pilot episodes, strong simple controls and ablations; candidate costs more than simple dedup+TTL | Bounded negative is acceptable. Do not promote the candidate or reinterpret flat quality intervals as noninferiority. |
| R2 | 480 frozen episodes/traces reproduced; capacity reconciles; dedicated reserve is explicitly zero; candidate matches FIFO behavior with overhead | Bounded negative is acceptable. The addendum adds no independent sample or reserve-policy efficacy evidence. |
| R3 | Frozen framed study plus the audited 16-episode Session capability diagnostic; explicit bounded G5 engineering decision | Retain failures and capability limits. Neither diagnostic establishes coordination superiority or a generally stronger 3B model. |
| R4 | Frozen 66-condition, four-world design is running: N=1,2,4,8,16,32; small/medium/mixed cohorts; fixed calls, binding fixed tokens and fixed deadline | Finish or explicitly account for interruption; audit complete grid, receipts, identities, retained accounting, common-final objective and exports; write its phase/negative report before the R5 gate. |
| R5 | New 38-case Session fault harness, behavior tests and independent harness review exist; historical five PilotLedger cases remain separate | Execute the frozen finite study after R4 review. Retain every PASS/FAIL/INVALID_ABORT, verify actual injection boundaries and cost/effect/Trace observations, and make a bounded engineering decision. Tests alone do not satisfy this phase. |
| Final consumer decision | Concrete installed inspect → artifact reference → submit journey and Session consumers exist; ownership and compatibility boundaries are documented | After R4/R5 review, record the exact supported consumer cohort, backend guarantees, simplest supported default and explicit non-claims. Master completion cannot be inferred from this audit. |

No additional missing implementation was identified as necessary for this
finite master target. The open items are substantive phase execution, audit
and the final compatibility decision. A fault-study violation would create a
concrete implementation gap; it must not be reclassified as a harmless negative
efficacy result. A scientifically negative coordination result can complete a
research phase without justifying a more complicated default policy.

## Limits that must survive a final exit decision

- This is a fixed-DAG, single-host consumer. Dynamic task admission, arbitrary
  worker process supervision and a persistent service loop are not implemented
  claims. R4 executes one model call at a time; logical N is not GPU concurrency.
  Concurrency and deadline admission are enforced by that finite consumer, not
  advertised as a general Session resource scheduler.
- Current checkpoints and retained mailbox entries/bytes are bounded. Repeated
  trusted checkpoint/send/ack operations can append arbitrarily many Trace
  events. Lifetime event-log growth is not bounded by work/call limits alone.
  Finite runner loops bound the observed study; this does not justify an 8-hour
  or 24-hour soak, production retention, or long-running memory claims.
- Tools are declared trusted callbacks; the code fixture uses a bounded integer
  interpreter. This does not provide a general sandbox for arbitrary code or
  external irreversible effects. Unknown dispatch remains unresolved instead of
  claiming general exactly-once execution.
- SQLite process-boundary evidence does not establish physical power-loss
  durability, multi-host failover, hostile data-store integrity or repair of
  corrupted state. The R5 corruption case observes explicit abort on a damaged
  disposable copy; it is not a recovery guarantee for arbitrary corruption.
- R4 has two sizes from one model family at one context cap and four constructed
  development worlds. Mixed assignment is fixed, not learned escalation. The
  private-history evidence task has a predeclared information-allocation lower
  bound at high N; failures there cannot identify an intelligence threshold.
  Primary candidate comparisons must retain blackboard and dedup+TTL controls.
- R1–R4 pilots and diagnostics are not confirmatory evidence. Source IDs, agent
  IDs, repeated calls and model diversity do not create independent worlds.

## Minimal compatibility and exit recommendation

Keep `pheroos_runtime.session_v1.Session` and
`pheroos_runtime.session_driver_v1.SessionDriver` an **experimental, explicitly
versioned consumer cohort**, pinned by source, wheel and installed-core hashes.
The shared `0.1.0.dev1` distribution label alone cannot identify the candidate.
The module contract uses new database paths; it promises no migration of G1
Store or PilotLedger databases. Preserve those historical modules and their
archived evidence until their declared consumers migrate under a separate
compatibility decision. Their existence is not active dual ownership.

Retain the simplest explicit single-agent/simple-sharing path; do not install
the R1 candidate as a default based on its negative pilot. Decide any narrower
R4-supported profile only after its frozen analysis and R5 acceptance. The final
candidate may be useful despite negative efficacy results, provided the stated
finite engineering guarantees hold and its capabilities and limits are reported
without a Stable, production, general swarm advantage or exactly-once claim.
