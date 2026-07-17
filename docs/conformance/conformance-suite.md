# Conformance Suite

`pheroos.conformance` owns protocol-core compatibility checks.

Conformance proves that a manifest or implementation obeys the declared ABI
surface. It is deterministic, provider-free, network-free, and explicit about
the invariant being checked.

## Manifest Check Groups

- manifest schema
- candidate declaration
- quorum policy
- collective policy
- safe collective fallback
- score breakdown contract
- pheromone policy
- pheromone behavior
- pheromone subject scoring
- pheromone kind profile
- pheromone diffusion
- pheromone reinforcement
- pheromone response model
- layer coordination policy
- policy adjustment bounds
- recovery policy
- output contract
- trace contract
- swarm trace contract
- hybrid trace contract
- hybrid authority boundary
- driver contract
- kernel contract
- extension contract

When `collective_commit_policy` is declared, the selected Commit profile adds
the following normative checks:

1. `commit_policy_contract`
2. `commit_numeric_contract`
3. `principal_attestation_contract`
4. `risk_monotonicity_contract`
5. `membership_snapshot_contract`
6. `observation_binding_contract`
7. `counterevidence_contract`
8. `challenge_coverage_contract`
9. `support_lease_contract`
10. `commit_metrics_contract`
11. `commit_channel_separation`
12. `commit_window_contract`
13. `commit_liveness_contract`
14. `commit_authority_boundary`
15. `commit_trace_contract`
16. `commit_certificate_contract`
17. `certificate_output_contract`
18. `distributed_finality_contract`
19. `certificate_conflict_contract`
20. `no_assurance_downgrade`

The selected profile activates the applicable subset of these 20 checks. The
union of the four Commit profiles covers all 20; no temporary alias is part of
the registry.

Source checks are intentionally separate from manifest checks:

- required protocol-core source surfaces
- domain-neutral public core
- package import boundary, including relative imports
- canonical driver lifecycle/registry validation parity
- cross-surface `RuntimeScope` binding
- authority-ledger scope, CAS, atomic state-plus-Trace, and receipt behavior
- public shape/lifecycle artifacts, canonical ownership, diagnostic registries,
  and representative defensive snapshots

## Applicability

Baseline governed protocols are not required to declare swarm behavior.

Swarm-specific checks apply only when a manifest declares a swarm collective
mode.

Pheromone behavior checks are no-op passes when pheromone is not enabled and
active deterministic ABI checks when a manifest declares pheromone-enabled
swarm behavior.

Hybrid pheromone checks apply when a swarm manifest declares at least one hybrid
feature: diffusion, feedback reinforcement, nonlinear response, layer
coordination, or policy-adjustment bounds.

Commit checks apply only when a manifest declares `collective_commit_policy`.
Once selected, every required Commit check returns PASS or FAIL. An active
Commit check cannot be skipped or reported as N/A. A manifest without the
declaration remains on its legacy core, swarm, or Hybrid Swarm profile and is
not forced to adopt Commit Integrity.

## Profiles

Conformance reports include the profile version that was applied.

- `pheroos-manifest-v1` applies to manifest validation.
- `pheroos-core-v1` applies to baseline governed protocols.
- `pheroos-swarm-v1` applies when a manifest declares swarm collective behavior.
- `pheroos-hybrid-swarm-v1` applies when a swarm manifest declares hybrid
  pheromone behavior.
- `pheroos-commit-integrity-v1` applies to advisory Commit declarations and to
  evidence-bound declarations without Hybrid attention.
- `pheroos-hybrid-commit-v1` applies when evidence-bound Commit Integrity and
  Hybrid attention are both declared.
- `pheroos-certified-commit-v1` applies when portable certified assurance is
  declared.
- `pheroos-distributed-commit-v1` applies when distributed assurance is
  declared.
- `pheroos-source-v3` applies only to protocol-core source cohesion, scoped
  cross-surface binding, authority-ledger atomicity, and the provider-neutral
  StateStore/TraceStore adapter contracts. It supersedes source-v2.

Commit profile selection takes precedence over legacy Hybrid authority and
output checks. Certified and distributed manifests that also declare Hybrid
attention retain their declared assurance profile and append the Hybrid
attention checks plus `commit_channel_separation`. Higher assurance is
cumulative: missing portable or distributed finality inputs fails the declared
path or produces a non-commit terminal outcome; it never selects a lower
assurance profile or legacy evaluator.

Profile version changes are ABI changes and should be documented in the
changelog.

The `profile_contract` check fails when a required check for the applied profile
is missing or failing.

Static contract tests separately prove that each built-in Commit Wire branch
and Trace event type has exactly one immutable schema/validator contract.
Unknown authority-relevant built-ins fail closed, while namespaced extension
events remain non-authoritative. Private-engine graph tests reject cycles,
aggregate-facade back-imports, dynamic service registries, and duplicate
algorithm owners without making private module paths part of the public ABI.

Hybrid conformance proves that pheromone remains collective memory rather than
authority: it cannot create candidates, evidence, quorum, fallback bypasses, or
output permission. Learned and evolutionary layers may propose bounded changes,
but only governance can commit a declared candidate or use the declared safe
fallback.

The Hybrid trace check executes `evaluate_hybrid_collective_step(...)` with
inputs derived from the active manifest, validates the canonical events field by
field, reconstructs candidate and pheromone category/kind/subject scores, and
causally replays deposit, evaporation/expiry, diffusion, and reinforcement into
the scored active-trail snapshot with the same shared source/round budgets. It
also reconstructs coordination from proposals, strategy biases, all six
performance-snapshot metrics, and accepted adjustment bounds before comparing
confidence, weights, conflicts, resolution, fallback, and layer score effects.
Both consensus and safe-fallback decision paths are replayed. A declared event
name or self-consistent reported output is not proof that a transition happened.
Rejected deposit, diffusion, and feedback clips are exercised as real
governance outputs. Conformance mutates every causal payload leaf, each receipt
field, feedback request/delta/reward, source identity/provenance, and topology
binding independently; missing or mismatched payload fingerprints fail the
Hybrid trace check.

Hybrid behavioral checks also exercise every built-in layer action through the
declared coordination thresholds and weights, declared pheromone-kind priority
and positive-suppression behavior, and the exact novelty-decay and stale-route
reopen boundaries. These probes derive strengths, caps, source diversity, and
thresholds from the manifest rather than substituting a conformance-only policy.
Actual replay trace checks require the governance-issued prior
`HybridReplayState`. They reconstruct each complete replay payload, compare it
with the lifecycle-specific receipt in that state, and verify the score anchor.
No prior state permits only an empty replay anchor, so coordinated phantom
events and caller-authored matching hashes fail closed.

## Commit Integrity TCK

The implementation-neutral Commit TCK is the checked-in JSON artifact
`pheroos/conformance/tck/commit-integrity-v1.json`, governed by
`schemas/commit-tck.schema.json`. It contains exactly one vector for each case
1 through 38. Every vector declares its manifest/profile, prior authoritative
state, inputs, exact metrics and roots, progress or outcome, trace sequence,
certificate projection, failure code, and any mutation or permutation probes.

The matrix covers evidence grouping and counterevidence, principal and lease
collapse, risk/membership resets, attention-channel separation, stability and
bounded liveness, action authority, portable certificate mutation/replay,
Byzantine quorum/finality and semantic-value conflict (including benign
same-value envelope retries), no-assurance-downgrade, active-check registration,
unknown critical fields, legacy compatibility, and
source/wheel/external-CWD portability. The reference adapter calls the public
Protocol, Governance, and Trace ABIs and compares the complete result. It does
not copy the commit algorithm or accept “no exception” as conformance.

Golden refresh is an explicit developer operation, never part of runtime
conformance. The generator first replays every base vector and every declared
mutation/permutation twice, then writes the aggregate plus the 38 split review
fixtures. `--check` performs the same replay without changing files:

```bash
python scripts/generate_commit_tck.py --check
# Intentional ABI golden refresh only:
python scripts/generate_commit_tck.py --write
```

Checked conformance always reads the committed artifact; it does not generate
expected results, memoize implementation results, or self-approve drift.
Before invoking an adapter, the harness projects each artifact vector into a
fresh `pheroos-commit-tck-request-v2` input-only request. The request contains
the manifest, prior authoritative state, operation inputs, and case identity,
but never the base expected result or mutation/permutation expectations. Exact
expected values remain harness-owned and are compared only after the adapter
returns.

The public Conformance facade resolves exports lazily through a static mapping.
Artifact-only Commit TCK checks likewise defer the optional reference adapter,
so external-CWD resource proof does not import the Governance engine. This is
an import-boundary optimization only: all 38 vectors, seven mutations, one
permutation, repeat checks, and 92 adapter evaluations remain mandatory.

### Commit TCK v2 adapter protocol

The public, provider-neutral request and response contracts are checked in as
`schemas/commit-tck-request-v2.schema.json` and
`schemas/commit-tck-response-v2.schema.json`. The declarations and strict JSONL
codec live in `pheroos.conformance.commit_tck_v2_protocol`; this module uses only
the Python standard library and does not expose Governance implementation
objects on the wire. A request uses `pheroos-commit-tck-request-v2`, contains an
explicit operation, and never contains `expected`. A response uses
`pheroos-commit-tck-response-v2`, correlates by request id, identifies the
implementation, and contains only the adapter's complete actual result.

The versioned JSONL session is `pheroos-commit-tck-jsonl-v2`:

1. The harness writes one `handshake` containing the session id, TCK/request/
   response versions, and all required operations.
2. The adapter writes one `handshake_ack` containing its stable implementation
   id and version plus every supported TCK/request/response version and
   operation.
3. For each case, the harness writes an `evaluate` envelope containing only a
   fresh request. The adapter writes one ordered `result` envelope containing a
   correlated response.
4. The harness writes `close`; the adapter must finish with `closed` for the
   same session.

Unknown fields, duplicate JSON keys, non-finite numbers, version mismatch,
unsupported operations, changed implementation ids, malformed output, missing
or reordered responses, missing close, oversized output, non-zero exit, and
timeout all fail the session. The protocol is newline-delimited JSON on standard
input/output; it needs no server, network, provider, or process-global state.

The checked declarative slice is
`pheroos/conformance/tck/commit-integrity-v2.json`, governed by
`schemas/commit-tck-v2.schema.json`. Its contiguous 23-case matrix proves public
fixed-point arithmetic; manifest-derived deadline and terminal selection;
evidence, support, diversity, and margin threshold pairs; every assurance
profile; Byzantine membership, quorum, and fault-model behavior; and the rule
that attention can change prioritization without changing evidence truth or
gaining commit authority. It also exhaustively mutates all 51 scalar authority
leaves of a portable evidence certificate and all 18 scalar authority leaves of
a commit trace lineage; every mutation must fail verification. Golden expected
values are hand-reviewed artifact inputs: the generator does not compute or
rewrite v2 expected values.

Two independent implementations must match every v2 golden exactly:

- `PheroosPublicCommitTckV2Adapter` composes installed public Protocol and
  Governance ABI functions.
- `python -I -m pheroos.conformance.commit_tck_v2_spec_adapter` is a separate
  stdlib spec model. It does not import `pheroos.governance`, the v1 reference
  adapter, or the PheroOS v2 subject adapter.

The v2 slice is additive. The v1 artifact remains byte-frozen, its 38 cases and
semantic root remain authoritative for v1, and `generate_commit_tck.py` still
owns only the explicit v1 replay/refresh workflow. Direct v2 family equivalents
now exist for v1 cases 11, 18, 20, 25, 27, and 28. A one-for-one declarative v2
migration remains for v1 matrix cases 1-10, 12-17, 19, 21-24, 26, and 29-38;
until those additive vectors land, the frozen v1 TCK continues to gate every one
of them. The new manifest-derived and adversarial v2 gates therefore do not
downgrade or replace legacy coverage.

Case 35 inspects the selected profile and callable registry without invoking
the checks, so the TCK cannot recursively call itself. Separate active-report
tests execute every required check and reject skipped, N/A, unregistered, or
constant self-pass results.

Run the manifest profiles and TCK independently:

```bash
python -m pheroos.cli.main conformance examples/hybrid-commit-protocol
python -m pheroos.cli.main conformance examples/distributed-commit-protocol
python -m pytest -q tests/conformance/test_commit_tck.py \
  tests/conformance/test_commit_tck_v2.py \
  tests/conformance/test_commit_integrity_conformance.py
```

## Manifest and Source Boundaries

Manifest conformance validates only the ABI profile selected by
`capability.json`; its optional `root` compatibility argument is intentionally
ignored. It must not infer source cohesion from the current working directory.
Source ownership, package boundaries, domain neutrality, and public type
identity and the replaceable store contracts are proved only by
`pheroos-source-v3`:

```bash
python -m pheroos.cli.main source-conformance /path/to/pheroos-protocol-core
```

When the argument is omitted, the root is resolved from the installed package,
never from the current working directory. Missing protocol, kernel, governance,
drivers, trace, conformance, or CLI surfaces fail the report.

Source-v3 also runs the bundled StateStore and TraceStore reference adapters
through the same public matrices exposed to external runtimes:

```python
from pheroos.conformance import (
    run_governance_state_store_conformance,
    run_trace_store_conformance,
)

state_result = run_governance_state_store_conformance(state_adapter)
trace_result = run_trace_store_conformance(trace_adapter)
```

The StateStore fixture supplies fresh, checkpoint-restored, snapshot-restored,
and deterministically failure-injected stores. The TraceStore fixture supplies
fresh stores. Fixtures declare the exact
`GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION` or
`TRACE_STORE_CONFORMANCE_VERSION`; unknown matrix versions fail closed.
StateStore failure points come from the public
`GOVERNANCE_STATE_STORE_FAILURE_STAGES` tuple.
Its concurrency matrix runs 32 same-batch retries and 32 conflicting-batch
workers. That load is not added to the provider ABI.
Conformance never owns the provider or database lifecycle.

Release verification runs both boundaries. It also runs both TCK generations
from the source tree and from separate wheel and sdist installations under an
external working directory; matching golden roots and exact results are
required.

## Rules

- Conformance checks should prove protocol invariants, not product policy.
- Checks must not require provider credentials, network access, databases, or
  external services.
- New compatibility behavior should include a conformance check when practical.
- Every check is isolated by the runner: an internal exception becomes a
  structured failed `CheckResult`, and later profile checks still run.
- The CLI remains a thin wrapper and delegates to `pheroos.conformance`.

## Failure Semantics

A failed conformance check means the manifest or implementation is not
compatible with the relevant PheroOS protocol-core surface. It does not attempt
to diagnose deployment-specific runtime behavior outside protocol-core.
