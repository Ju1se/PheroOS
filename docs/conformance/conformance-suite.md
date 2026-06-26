# Conformance Suite

`pheroos.conformance` owns protocol-core compatibility checks.

Conformance proves that a manifest or implementation obeys the declared ABI
surface. It is deterministic, provider-free, network-free, and explicit about
the invariant being checked.

## Check Groups

- manifest schema
- domain-neutral public core
- candidate declaration
- quorum policy
- collective policy
- safe collective fallback
- pheromone policy
- pheromone behavior
- recovery policy
- output contract
- trace contract
- swarm trace contract
- driver contract
- extension contract
- kernel import boundary

## Applicability

Baseline governed protocols are not required to declare swarm behavior.

Swarm-specific checks apply only when a manifest declares a swarm collective
mode.

Pheromone behavior checks are no-op passes when pheromone is not enabled and
active deterministic ABI checks when a manifest declares pheromone-enabled
swarm behavior.

## Profiles

Conformance reports include the profile version that was applied.

- `pheroos-manifest-v1` applies to manifest validation.
- `pheroos-core-v1` applies to baseline governed protocols.
- `pheroos-swarm-v1` applies when a manifest declares swarm collective behavior.

Profile version changes are ABI changes and should be documented in the
changelog.

The `profile_contract` check fails when a required check for the applied profile
is missing or failing.

## Rules

- Conformance checks should prove protocol invariants, not product policy.
- Checks must not require provider credentials, network access, databases, or
  external services.
- New compatibility behavior should include a conformance check when practical.
- The CLI remains a thin wrapper and delegates to `pheroos.conformance`.

## Failure Semantics

A failed conformance check means the manifest or implementation is not
compatible with the relevant PheroOS protocol-core surface. It does not attempt
to diagnose deployment-specific runtime behavior outside protocol-core.
