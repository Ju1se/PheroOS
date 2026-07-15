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
- canonical public type ownership and representative defensive snapshots

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
- `pheroos-source-v1` applies only to protocol-core source cohesion.

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

Case 35 inspects the selected profile and callable registry without invoking
the checks, so the TCK cannot recursively call itself. Separate active-report
tests execute every required check and reject skipped, N/A, unregistered, or
constant self-pass results.

Run the manifest profiles and TCK independently:

```bash
python -m pheroos.cli.main conformance examples/hybrid-commit-protocol
python -m pheroos.cli.main conformance examples/distributed-commit-protocol
python -m pytest -q tests/conformance/test_commit_tck.py \
  tests/conformance/test_commit_integrity_conformance.py
```

## Manifest and Source Boundaries

Manifest conformance validates only the ABI profile selected by
`capability.json`; its optional `root` compatibility argument is intentionally
ignored. It must not infer source cohesion from the current working directory.
Source ownership, package boundaries, domain neutrality, and public type
identity are proved only by `pheroos-source-v1`:

```bash
python -m pheroos.cli.main source-conformance /path/to/pheroos-protocol-core
```

When the argument is omitted, the root is resolved from the installed package,
never from the current working directory. Missing protocol, kernel, governance,
drivers, trace, conformance, or CLI surfaces fail the report.

Release verification runs both boundaries. It also runs the same TCK from the
source tree and an isolated wheel under an external working directory; matching
canonical roots and exact results are required.

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
