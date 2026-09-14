# Finite Session consumer exit decision — draft v1

**Disposition: retain the current experimental consumer; final master acceptance
is pending R4 and R5.** This draft identifies the code and compatibility decision
to accept after those gates. It adds no public core API, package release,
database migration, default experimental policy or production claim. Existing
authorized development and experiments continue under their own contracts.

## Concrete caller and API cohort

The reference consumer is the installed external
[`run_session_journey_v1.py`](/home/scott/projects/PheroOS-runtime/tools/run_session_journey_v1.py):
one agent inspects, publishes a separately verified tool artifact and sends its
reference to a second agent; the second restores bounded context, reads that
artifact, submits through a deterministic verifier, and retrieves committed
receipts after reopening. Model generation is optional. Real model consumers
also exist in the completed Session capability diagnostic and the frozen R4
runner. The new R5 harness exercises the same Session transitions directly.

Use these direct module imports and exercised operations:

| Consumer need | Cohort to retain |
| --- | --- |
| Declare/reopen finite work and control it | `pheroos_runtime.session_v1.Session`: constructor, `create`, `claim`, `recover`, `cancel`, `revoke`, `snapshot` |
| Restore private work and exchange verified references | Session `context`, `checkpoint`, `artifact`, `send`, `mailbox`, `ack` |
| Account and authorize one call/publication | Session `reserve`, `dispatch`, `receive`, `call`, `publish`; direct consumers must preserve current authorization and independent verification callbacks |
| Execute a replaceable adapter outside the ledger transaction | `pheroos_runtime.session_driver_v1.SessionDriver`: `generate`, `evaluate`, `replay`; `current_authorization` is the existing trusted-host development adapter |
| Supply capability and interpret lifecycle failures | Optional `LocalModelAdapter`; duck-typed models expose `identity`, `count_tokens`, `generate`; tool registry entries are explicit callbacks. Reused `pheroos_runtime.store.Lease`, `StateError`, `BudgetExceeded`, `LeaseLost` keep their identities. |

The model response is a proposal. Publishing a tool's verified evaluation fact
does not turn an invalid task action into objective success. Availability in a
registry, a saved checkpoint, a received message or a replayed receipt grants
no execution authority. New Session calls have exactly one cost owner: Session.

This cohort is identified by the recorded source/distribution hashes, not the
shared `0.1.0.dev1` label. The accepted source hashes are
`a1c0750b12ea2d3b3cfabc42c29f2616c6160ef0b1641cd573d67db3d6d9a39e`
for Session and
`4bc372f2f64d01efa0b4c1da896db27793b8ef473bd85e20cbba025e13839b08`
for SessionDriver. [The architecture receipt](architecture-review.json) binds
the wheel, sdist, core wheel and installed/source comparisons. Its reported
131 tests per distribution include historical compatibility tests; they are
not 131 new fault experiments. The [current installed-core comparison](current-installed-core-comparison-v2.json)
matches all 613 current package Python/JSON files. The
[core support matrix](../../../docs/protocol/current-support.md) remains Draft;
the authority adapter still uses its declared public reference-Store exception.

## Compatibility and retained ownership

Create a new SQLite path with `Session.create`; reopen only an existing database
created under this same Session v1 cohort. Do not pass G1 Store or PilotLedger
databases to Session, reinterpret their units as tokens, or migrate them
implicitly. Internal tables and implementation helpers are not new public core
contracts. Any later incompatible Session/schema change needs a separate
version and an explicit consumer migration decision.

| Existing code | Required current consumer; retention decision |
| --- | --- |
| G1 `store.py`, `engine.py`, `adapters.py`, `cli.py` | Frozen G1 FIFO/blackboard execution, installed-package acceptance and `capture_r0_runtime.py` reproduction still consume them. Session also directly reuses the Lease/error declarations from `store.py`. Retain the modules and their frozen artifacts. |
| `r3_ledger.py` / `PilotLedger` | Historical R3 v1/v2/v3 model-worker protocol and the original five-case R5 ledger study require this accounting implementation. Retain it for those consumers. It does not bill Session calls. |
| `r3_local.py` | Historical workers still use its JSONL handler, while the current optional LocalModelAdapter reuses its LocalModel implementation. The module imports PilotLedger for the historical handler; SessionDriver does not call that handler or ledger. Retain the exact shared implementation. |
| `authority.py` and canonical public core types | Both cohorts use the existing authorization adapter; Session additionally uses public RuntimeScope/TraceEvent. Retain these dependencies without treating stored audit projections as durable execution permissions. |

No old accounting owner is silently replaced by the new one. Removing a legacy
module later requires an archived executable source/wheel closure, migration of
its declared consumers, preserved reproduction commands, and compatibility
evidence. No removal is proposed for this exit.

## Small cleanup finding; no frozen edit

All public Session operations have an actual journey, driver, benchmark or
fault-harness caller. The one unconsumed new declaration found is
`ModelAdapter(Protocol)`: current code neither imports that symbol into a typed
consumer nor annotates/checks adapter values against it. The duck-typed behavior
is exercised by the real LocalModelAdapter and synthetic adapters; the Protocol
symbol itself supplies no runtime checking or typed-consumer linkage.

Keep it byte-identical in this frozen cohort. In a future version, either use it
in a concrete typed consumer/check or omit the unused declaration. This small
cleanup is not a final-gate blocker and does not justify another interface,
manager, registry or runtime rewrite. No other unused new runtime abstraction
was identified in this bounded source/caller review.

## Remaining gates and final disposition

1. **R4 original integrity:** finish and pin the independent whole-campaign
   abort audit. The original 264-row study remains `INVALID_ABORT` with 204
   complete, one interrupted and 59 unstarted rows. A positive integrity audit
   does not make a usable subset or successful R4 grid.
2. **R4 fresh replication:** complete the separately declared
   [`r4_full_grid_replication_v1`](../../SCALING-replication-v1-contract.md)
   attempt using the unchanged inner method and new ledgers; independently
   audit its complete grid, raw/SQLite receipts, current authority, model/source
   identities, accounting, common-final objective and exports. Preserve both
   attempts and costs without counting repeated worlds as new independence.
   Write the bounded quality/cost/capability report and R4 gate decision. A
   further abort remains explicit; there is no automatic retry or tail repair.
3. **R5 finite engineering evidence:** after that R4 gate, execute the declared
   [38-case Session matrix](../../R5-session-faults-v1-contract.md), audit actual
   injection boundaries and every outcome, and report effect counts, retained
   costs, fencing, cancellation, references, recovery/uncertainty and Trace.
   The existing harness tests and five historical PilotLedger cases cannot
   substitute for this study. A witnessed invariant violation requires a
   concrete fix and new versioned evidence; it is not a harmless negative
   efficacy result.
4. **Exit record:** replace this draft with an explicitly identified decision
   citing those phase reports, exact consumer/build identities and backend
   guarantees. Keep Session policy-neutral and model loading opt-in; callers
   explicitly select their benchmark profile, and G1 keeps its existing FIFO
   default. Do not promote R1's candidate after its adverse cost result. A
   recommended R4 profile must wait for its frozen analysis and R5 decision.

At draft creation the full original abort-audit report is still pending, the
replication has not been launched, and the Session fault study has not run.
This review ran no models or tests and edited no runtime or frozen evidence.

Acceptance, if later granted, must remain limited to finite declared DAGs on
the tested single-host SQLite backend with trusted callbacks. Retained context
and mailboxes are bounded; arbitrary repeated checkpoint/send/ack operations
can grow Trace without a lifetime bound. Clock discontinuities may stop progress;
the original R4 interruption does not establish suspend as its cause. There is
no general sandbox, durable issuer-custody, multi-host, power-loss repair,
arbitrary external-effect exactly-once, long-soak, Stable or production claim.
Negative efficacy findings can complete a research phase; none establish
robustness or a coordination advantage merely because tests pass.
