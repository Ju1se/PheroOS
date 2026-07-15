# Optimal Commit ABI

Status: implemented Draft ABI

Optimal Commit is PheroOS's evidence-governed commitment path for a declared
multi-agent target. It is optional: a manifest activates it only by declaring
`collective_commit_policy`. Manifests without that declaration retain their
existing quorum, swarm, or Hybrid behavior.

Agents may explore, report, challenge, and propose support. They do not create
commit authority. Governance-issued records, the declared protocol, and the
selected assurance profile determine the result.

## Profiles and assurance

The manifest selects one assurance level; runtime inputs cannot lower it:

| Assurance | Commit result requirement |
| --- | --- |
| `advisory` | no epistemic commit; terminal advisory/fallback only |
| `evidence_bound` | stable evidence decision plus a current local receipt |
| `certified` | evidence-bound proof plus an independently verifiable portable certificate |
| `distributed` | portable proof plus a static-epoch Byzantine quorum certificate |

The selected assurance determines the conformance profile. Missing proof for
that profile yields progress or a declared terminal non-commit outcome; it
never produces a lower-assurance commit.

## Two independent channels

Hybrid memory remains fully available for exploration:

```text
pheromone / recruitment / inhibition / layer proposals
                         |
                         v
               attention + exploration directive
```

Commit truth uses a separate path:

```text
principal verification
  -> risk + membership heads
  -> verified observations + counterevidence + challenges
  -> evidence binding
  -> evidence-bound support leases
  -> exact commit metrics
  -> stable window
  -> assurance proof
  -> decision outcome
```

Changing only attention inputs cannot change commit metrics, the selected
candidate, a commit certificate, or a terminal commitment result. Attention
may cause an external runtime to collect new evidence; only the newly verified
evidence can affect a later commit assessment.

Attention availability is also non-authoritative. A missing, malformed,
cross-step, or incomplete attention/directive binding produces
`attention_status=unavailable`, an empty advisory projection, and one nonfatal
diagnostic. The independent commit authority path continues unchanged; an
attention failure cannot manufacture `invalid`, block finality, or veto output.

## Exact evidence semantics

All authority-bearing numeric values are bounded integers. The normative scale
is `1_000_000`; floating-point values are not part of Commit Wire truth.

For each substantive candidate, governance computes:

- `P`: capped positive evidence, grouped by declared independence group;
- `N`: capped counterevidence after verified disposition;
- `Nw = floor(counter_weight_ppm * N / 1_000_000)`: weighted counterevidence;
- `V = P - Nw`: net evidence;
- `S`: unique verified principal clusters with active evidence-bound leases;
- `D`: qualifying source-domain diversity;
- `margin`: the leader's net-evidence advantage over the strongest competing
  candidate, with the competing baseline floored at zero.

A candidate becomes ready only when every risk-adjusted gate passes, including
challenge coverage, critical counterevidence resolution, support, diversity,
margin, replay/equivocation checks, the current `commit` stop resolution, and
the current `commit` permission. Ties do not fall back to identifier or arrival
order.

## Stable window and bounded liveness

The first ready assessment is pending. A commit requires the same unique leader
and all gates to remain ready for the declared stability window. Leader, gate,
epoch, policy, risk, or membership changes reset the window according to the
manifest's fixed reset rules and budgets. A replay fork, stale head, deletion,
or substitution is invalid. A valid append-only replay advance for newly
verified evidence instead requires governance to issue a fresh evaluation
context and action gates; it may preserve the window when the unique leader and
every gate remain continuous.

A receipt-backed `CommitWindowSeal` freezes the exact ready window and all
authority roots. Evidence-bound finality is same-step. Certified or distributed
proof that arrives later must carry the exact next-step `DecisionProgress`
heartbeat for that seal. A gap, substituted head, stale progress, or unseal
invalidates late finality.

The runtime supplies monotonically increasing logical steps and continues
calling the evaluator. The core does not create a scheduler or clock. At the
absolute deadline, the evaluator cannot return pending. It emits one declared
terminal outcome:

- `evidence_commit`;
- `safe_fallback`;
- `advisory`;
- `blocked`;
- `invalid`;
- `finality_unavailable`;
- `safety_violation`.

Every governance-issued terminal outcome is deliverable to the caller.
Delivery is not publication. `publish` and `execute` are separately authorized
against their current target/action/epoch-scoped stop resolution, permission,
certificate, and distributed-state heads.

## Total Hybrid entry

`evaluate_hybrid_commit_step(request=...)` is the fail-closed finalization
boundary. The request carries governance-issued attention, assessment, window,
replay, risk, membership, lease, optional certificate/finality, and current
output-action records. The result is a `HybridCommitEvaluation` containing:

- the verified attention/commit channel binding;
- the exact assessment, window, and replay heads;
- exactly one `DecisionProgress` or `DecisionOutcome`;
- the proof required by the declared assurance when available;
- delivery, publication, and execution decisions for governance-issued
  terminal outcomes;
- canonical trace events and structured diagnostics;
- a root binding every request and result authority leaf.

Malformed runtime facts do not enter a legacy evaluator and do not escape as an
uncaught governance decision error. If the authority envelope is usable, they
produce an issued `invalid` outcome and delivery decision. If the authority
envelope itself cannot be established, the call still returns an explicit
non-authoritative invalid diagnostic envelope.

Upstream evidence collection remains compositional. External runtimes use the
public principal, observation, challenge, evidence, lease, risk, assessment,
and Hybrid attention APIs before invoking the total finalization boundary.
PheroOS does not embed an agent loop, provider, witness collector, network, or
worker runtime.

## Portable and distributed proofs

Portable certificates bind the exact manifest, policy, risk, membership,
evidence, challenge, lease, window, replay, stop, permission, claim, candidate,
and output roots. Independent verifiers reject any leaf mutation, replay, or
cross-target/candidate/epoch substitution.

Distributed assurance uses a declared static epoch with `n >= 3f + 1`, quorum
`q`, and the intersection rule `2q - n > f`. Every verified witness signs the
same full proposal digest and its semantic commit-value root and is bound to
the epoch membership, principal cluster, failure domain, nonce, target,
candidate, and expiry. The semantic root includes the candidate, claim,
output, and every authority/truth root, but excludes proposal, receipt,
and certificate envelope identifiers plus proposal-time and transport
metadata. Authority roots still bind their own provenance and trace lineage.
Insufficient quorum is provisional, never final.

Different envelopes or proof identifiers for the same semantic value are
retries, not witness equivocation or certificate conflict. Two final
certificates with different semantic roots freeze the epoch, produce a
`safety_violation`, and deny publication/execution. Recovery requires the
declared recovery authority and an epoch-transition certificate; it cannot be
performed by an agent proposal or an ordinary fallback.

## Trace and conformance

Commit Trace ABI records the path from principal attestation through risk,
membership, observation, challenge, evidence, lease, metrics, window,
certificate/finality, outcome, and output decisions. Event identifiers and
record references are canonical content roots. Replay is append-only,
idempotent for identical records, and rejects payload substitution or missing
causal predecessors.

The checked-in Commit TCK contains all 38 adversarial matrix cases from the
hardening plan. JSON vectors contain exact metrics, roots, progress/outcome,
trace sequence, certificate projection, and failure code. The reference adapter
uses only public Protocol, Governance, and Trace APIs. Active Commit profiles
run registered PASS/FAIL checks; they do not use skip, N/A, or hard-coded
self-pass behavior.

## Extensibility boundary

Optimal Commit is strict about authority, not about application design:

- activation is optional and legacy manifests remain unchanged;
- assurance levels let deployments choose local, portable, or distributed proof;
- external runtimes own models, tools, identity providers, storage, networks,
  schedulers, and agent topology;
- noncritical extension metadata remains open and does not affect authority;
- new critical semantics require a declared version, validator, trace contract,
  conformance proof, and deterministic test vector;
- unknown critical fields fail closed instead of being silently ignored.

This boundary preserves provider and domain extensibility while preventing an
extension, pheromone signal, or caller-controlled boolean from becoming an
undeclared truth or output authority.

External interoperability maps into the ABI without adding provider code to
protocol-core:

| External concern | PheroOS boundary record |
| --- | --- |
| MCP/resource observation | `ObservationAttestation` followed by governance verification |
| A2A agent support message | `SupportLeaseProposal`; it counts only after lease issuance |
| A2A distributed witness | `QuorumWitness` followed by governance witness verification |
| provenance/PROV graph | opaque provenance and trace references bound into canonical roots |
| OPA or another policy service | external input to issuance of `StopResolutionVerification` or `ActionPermission` |

The adapter is responsible for authenticating and translating the external
message. The external message itself is never authority inside PheroOS.
