# Evidence-driven multi-agent OS: execution status

This is the working phase map for the master goal accepted on 2026-09-12.
The master research goal is **complete for the documented experimental OS
candidate**, following the [final root acceptance](results/master-goal-audit-v1/MASTER-ACCEPTANCE-v1.json).
R1–R5 and the consumer/architecture review are complete. Current interface support remains governed
authority/commit Draft contracts, as defined by
[the current support matrix](../docs/protocol/current-support.md).
Swarm-native execution is a research target, not a current efficacy or Stable claim.

## Audited starting state

Core/bench branch `main`, HEAD `b154472becea561ac1f5fc442a7ccf372ab154f8`;
external runtime HEAD `e3ef1e8ed0812296601e4a901768af4a1068b5e0`. Both checkouts
contain preexisting uncommitted research work. Frozen source manifests, rather
than HEAD alone, identify those experiments. Core remains provider-neutral;
runtime lifecycle/adapters stay in the external package; experimental policies,
tasks and measurement remain in bench. Existing contracts do not yet require
a protocol-core change.

| Stage | Current evidence | Next required work |
| --- | --- | --- |
| G1 / R0 | Installed runtime 43 tests, R0 117 tests and fresh known/unknown/late-receipt reconciliation pass. | Preserve accepted semantics while extending concrete runtime consumers. |
| G3 / R1 | [V2 pilot](results/r1-coordination-pilot-v2/RESULTS.md): 64 valid episodes, component ablations, seven paired-world exports; candidate has greater total cost than simple dedup. | Engineering gate passes; retain simple policy choices and negative result. |
| G4 / R2 | [Frozen v1](results/r2-pilot-v1/RESULTS.md): 480 valid episodes; congestion candidate equals FIFO dispatch and adds overhead. [Capacity addendum](results/r2-capacity-audit-v1/RESULTS.md) reproduces every episode/trace and reconciles available/busy/idle/unavailable capacity; dedicated reserve is zero. | Bounded negative phase gate passes; retain conventional scheduling, with no candidate promotion. |
| G5 / R3 | [V3](results/r3-framed-pilot-v3/RESULTS.md) records 160 calls/80,709 tokens with no unknown usage. All five policies solve both code worlds and fail both evidence worlds. The declared valid-action interaction endpoint is zero; three narrower posthoc prefix effects are separately retained. V1/v2 failures remain unchanged. | [Session capability diagnostic](results/r3-session-capability-v1/RESULTS.md): 16 audited episodes, 38,661 known tokens, both models solve autonomous code tasks and fail evidence tasks. [Bounded G5 engineering gate passes](results/r3-session-capability-v1/G5-gate-review.json); no coordination or model-superiority promotion. |
| R4 | The [original pilot](results/r4-session-scaling-pilot-v1/RESULTS.md) remains INVALID: 204 complete rows, one LeaseLost abort and 59 unstarted null rows. Its [abort audit passes](results/r4-session-scaling-pilot-v1/ABORT-AUDIT-ADDENDUM.md). The unchanged [264-episode replication](results/r4-session-scaling-replication-v1/RESULTS.md) and all 56 paired exports pass independent audit; 51 condition/world rows succeed, all evidence-world rows fail, and every quality interval includes zero. | [Bounded R4 engineering/measurement gate passes](results/r4-session-scaling-replication-v1/GATE-ADDENDUM.md). Original and replication known tokens remain separate: 2,824,212 + 3,402,842 = 6,227,054. No subset repair, repeated-world pooling, capability threshold or candidate promotion. |
| R5 | The [38-case Session study](results/r5-session-faults-v1/RESULTS.md) ran once and passes independent audit v2. Available ledgers retain 18 known synthetic tokens, 70 unknown tokens in ten calls, 13 synthetic-model/25 tool dispatches and 33 sidecar invocations; the damaged primary ledger remains unavailable. The initial checker mismatch is retained. | [Bounded R5 engineering gate passes](results/r5-session-faults-v1/GATE-ADDENDUM.md). Passing invariants include unresolved, cancelled, revoked and unavailable dispositions, not universal recovery. No real-provider/GPU failure, soak, general robustness or production claim. |
| Final architecture | External experimental Session owns declared DAG work, leases, durable permission/accounting and bounded checkpoints/artifact references/mailboxes; fresh public-core authorization gates execution/publication. Wheel and sdist acceptance each pass 131 tests; original runtime modules remain unchanged. | The [finite consumer decision](results/master-goal-audit-v1/consumer-exit-decision-v1.md), exact [archived packages](results/master-goal-audit-v1/consumer-artifacts-v1/INSTALL.md), fresh offline install journey and [root master acceptance](results/master-goal-audit-v1/MASTER-ACCEPTANCE-v1.json) complete this experimental candidate. |

## Runtime path and limits

G1 has persistent work, leases, unit reservations, cancelled-work fencing and
verified integer artifacts. R3 has real local inference, a durable token ledger,
bounded receipt context and governed publication, but it does not automatically
inherit G1's cancellation and lease semantics. The new experimental `Session`
and `SessionDriver` provide a common consumer path with bounded mailbox
acknowledgments, restartable private checkpoints, model/tool reservations and
committed-result retrieval. The installed inspector-to-solver journey exercises
these features. Its one-call 3B readiness run generated a correct numeric total
with an extra schema key, so the strict objective failed; all 63 tokens were
retained and no artifact was published. Original G1/R3 implementations remain
available for reproduction; a new Session never charges either legacy ledger.
Closed-loop model integration passed its bounded G5 audit; the separate
38-case R5 Session fault gate now also passes within its declared finite scope.

Private context, persistent artifacts, expiring attention and current authority
remain separate. A stored result or settled late receipt cannot recreate a
cancelled task or permission. The external development authority adapter still
uses the explicitly documented public reference Store; durable issuer custody
and arbitrary external exactly-once effects are not established.

## Execution order and reporting

G3, the R2 capacity addendum, the bounded G5 follow-up, the complete-grid R4
replication and finite R5 fault gate are accepted. The
[master empirical report](results/master-goal-audit-v1/FINAL-REPORT.md) retains
their positive, negative and unresolved findings. The original R4 abort remains
INVALID; its single unchanged replication followed the
[replication contract](SCALING-replication-v1-contract.md), with campaign config
SHA256 is `df9f3cea01a69c0718779c6086cbd644d3b9f80bc30ee9141d19e267eebca00e`;
the [original abort audit](results/r4-session-scaling-pilot-v1/abort-independent-audit-v1.json)
is pinned as `723d36f07fc5cccd1466d55ca6e890983c0a41f68c817e7212189666c31d8bf5`.
That was one fresh 264-episode attempt, without automatic retry or reuse of
original rows. R5 likewise ran once; its narrow v2 checker correction reran no
fault case and did not change source outcomes. Root's
[R5 gate](results/r5-session-faults-v1/R5-gate-review.json) follows the passed
R4 gate. The [finite consumer decision](results/master-goal-audit-v1/consumer-exit-decision-v1.json)
is accepted by the final root review; the [final preservation check](results/master-goal-audit-v1/final-integrity-v1.json)
passes all 3,588 unique retained file identities. The [fresh archive install check](results/master-goal-audit-v1/consumer-install-check-v1.json)
completes the provider-free two-agent journey with two tool calls and no unknown usage.
Historical E1/E2/E3, G1/R0 and
frozen R-series files are never edited. Each new phase/addendum has a separate
method/config, output directory, source hashes, machine-readable accounting and
phase report. Reanalysis is explicitly not a new independent sample. Pilot
results never become confirmatory evidence.

Current tests separate engineering correctness and measurement validity from
efficacy. Negative results are retained; no threshold or baseline is changed to
make a candidate win. The final decision covers implementation, executed studies,
accounting, preservation, compatibility and the empirical map. General swarm
efficacy, production readiness and mature long-soak reliability remain unproven.
