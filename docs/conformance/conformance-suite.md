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

## Profiles

Conformance reports include the profile version that was applied.

- `pheroos-manifest-v1` applies to manifest validation.
- `pheroos-core-v1` applies to baseline governed protocols.
- `pheroos-swarm-v1` applies when a manifest declares swarm collective behavior.
- `pheroos-hybrid-swarm-v1` applies when a swarm manifest declares hybrid
  pheromone behavior.
- `pheroos-source-v1` applies only to protocol-core source cohesion.

Profile version changes are ABI changes and should be documented in the
changelog.

The `profile_contract` check fails when a required check for the applied profile
is missing or failing.

Manifest conformance never treats an unavailable source tree as an N/A pass or
as proof of source cohesion. Run the independent source profile with an explicit
root:

```bash
pheroos source-conformance /path/to/pheroos-protocol-core
```

When the argument is omitted, the root is resolved from the installed package,
never from the current working directory. Missing protocol, kernel, governance,
drivers, trace, conformance, or CLI surfaces fail the report.

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
