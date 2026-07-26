# Development Process

This directory contains the source-tree process documents for PheroOS
protocol-core.

The process documentation is about changing the protocol source tree. It is
not runtime setup documentation and does not describe provider, server,
database, dashboard, or application deployment workflows.

## Entry Points

- [CONTRIBUTING.md](../../CONTRIBUTING.md) - contribution process and patch requirements.
- [api-lifecycle.md](api-lifecycle.md) - public API and ABI lifecycle rules.
- [schema-v1-v2-migration.md](schema-v1-v2-migration.md) - frozen legacy
  schema roots, strict versioned documents, reader selection, and migration.
- [authority-v2-decision.md](../protocol/authority-v2-decision.md),
  [authority-trust-model-v2.md](../protocol/authority-trust-model-v2.md), and
  [authority-v2-migration.md](../protocol/authority-v2-migration.md) define the
  accepted version, trust boundary, and migration contract for the active Draft
  local profile; authenticated production promotion remains gated.
- [project-architecture-hardening-plan.md](project-architecture-hardening-plan.md)
  is the completed, non-normative record of the project-wide architecture
  audit, decoupling, extensibility, cleanup, and release hardening work.
- [production-readiness-hardening-goal-plan.md](production-readiness-hardening-goal-plan.md)
  is the active, non-normative Goal execution plan for authority trust roots,
  durable replay/finality, a Stable Core ABI, engineering quality gates,
  release governance, and an external reference runtime.
- [receptor-ligand-field-comparative-study-plan.md](receptor-ligand-field-comparative-study-plan.md)
  is the preregistration draft for comparing a receiver-gated ligand field
  against full, sparse, blackboard, retrieval-routing, learned-pruning, and
  current scalar-pheromone controls without changing Commit truth or importing
  an experiment runtime into protocol-core.
- [receptor-ligand-field-experiment-profile-v0.1.md](receptor-ligand-field-experiment-profile-v0.1.md)
  is the preserved first G0 draft, superseded before any arm execution after an
  independent design audit found baseline and mass-conservation ambiguities.
- [receptor-ligand-field-experiment-profile-v0.2.md](receptor-ligand-field-experiment-profile-v0.2.md)
  is the preserved first executable G0-G3 freeze, superseded after the first
  qualification run found executable-fidelity and public-label leakage
  blockers without reading sealed outcomes.
- [receptor-ligand-field-experiment-profile-v0.3.md](receptor-ligand-field-experiment-profile-v0.3.md)
  is the preserved G1-G3 qualification amendment: it freezes manifest-declared topology,
  a ground-truth label firewall, typed logs and diagnostics, strong-baseline
  qualification, complete-cost requirements, and corrected provider canaries;
  it was superseded before outcome-bearing execution when dynamic topology
  epochs required a separate frozen contract.
- [receptor-ligand-field-experiment-profile-v0.4.md](receptor-ligand-field-experiment-profile-v0.4.md)
  is the preserved topology-epoch qualification amendment. It froze canonical,
  prefix-causal eight-ligand epochs and an exact T4 graph-shift fixture, and was
  superseded before outcome-bearing execution by the complete G2 environment
  and intent-matrix freeze.
- [receptor-ligand-field-experiment-profile-v0.5.md](receptor-ligand-field-experiment-profile-v0.5.md)
  is the preserved G2 deterministic-environment and intent-matrix amendment. It
  froze the T4 scheduler state machine, sealed prefix boundary, compact scale
  eligibility, exact smoke/attack/budget/scale counts, and fresh-process replay,
  and was superseded before G2 qualification when attack-label ambiguity was
  found.
- [receptor-ligand-field-experiment-profile-v0.6.md](receptor-ligand-field-experiment-profile-v0.6.md)
  is the active G2 attack-label firewall amendment. It separates
  variable-severity injection, task-intrinsic challenge, mandatory probes, and
  T4 environment stress without changing the 7,252-intent matrix or any
  protocol-core ABI.
- [receptor-ligand-field-g0-g3-qualification-report.md](receptor-ligand-field-g0-g3-qualification-report.md)
  records the current external qualification checkpoint: G0/G1 passed,
  G2/G3 remain blocked by the full simulator matrix, P durable replay, and
  actual cost ledgers; no provider network request or H1-H6 conclusion was
  authorized.
- [stable-core-consumer.md](../protocol/stable-core-consumer.md) defines the
  public-facade, strict-typing, aggregate-journey, and external-adapter boundary
  for the Draft Stable promotion candidate without claiming formal stability.
- [authority-store-v2.md](../protocol/authority-store-v2.md) is the normative
  Draft WP-02 StateStore ABI: canonical contracts, atomic commit, historical
  finality, seal semantics, restart equivalence, and adapter Conformance.
- [authority-session-v2.md](../protocol/authority-session-v2.md) is the
  normative public Draft WP-03 issuer grant/capability/session ABI, including
  the atomic verified-signal and domain-retirement vertical slices and their
  reusable provider-free Conformance matrix.
- [baseline-output-v2.md](../protocol/baseline-output-v2.md) defines the
  scoped, durable terminal-output and current publish/execute authority path.
- [hybrid-replay-v2.md](../protocol/hybrid-replay-v2.md) is the Draft WP-05
  durable Hybrid replay ABI: portable snapshots versus Store-verified local
  authority, exact stream/transition identity, atomic parent/grant/lifecycle
  checks, and historical restart semantics.
- [commit-state-v2.md](../protocol/commit-state-v2.md),
  [risk-state-v2.md](../protocol/risk-state-v2.md), and
  [support-v2.md](../protocol/support-v2.md) define the durable Commit replay,
  Risk, Principal Verification, Membership, and Support owners used by the
  WP-05 production-path candidate.
- [commit-gate-v2.md](../protocol/commit-gate-v2.md),
  [commit-evidence-v2.md](../protocol/commit-evidence-v2.md), and
  [commit-decision-v2.md](../protocol/commit-decision-v2.md) define the current
  gate, evidence, and terminal-decision chain.
- [commit-certificate-v2.md](../protocol/commit-certificate-v2.md),
  [distributed-commit-v2.md](../protocol/distributed-commit-v2.md), and
  [commit-finality-v2.md](../protocol/commit-finality-v2.md) define the two
  durable finality owners and their authority-neutral public bridge. Their
  public-only reference/independent Conformance composition is active while the
  ABI remains Draft.
- [runtime-integration.md](../protocol/runtime-integration.md),
  [runtime-compatibility-v1.md](../conformance/runtime-compatibility-v1.md),
  [scoped-trace-store-v2.md](../protocol/scoped-trace-store-v2.md), and
  [invocation-v2.md](../drivers/invocation-v2.md) define the provider-neutral
  external-runtime composition boundary and exact-version TCK contracts.
- [engineering-baseline-v1.json](engineering-baseline-v1.json) is the
  machine-readable WP-00 engineering baseline and monotonic regression policy;
  refreshes require an explicit reason and may only tighten one-way gates.
- [coverage-scope-v1.json](coverage-scope-v1.json),
  [authority-mutation-v1.json](authority-mutation-v1.json),
  [complexity-scope-v1.json](complexity-scope-v1.json), and
  [reference-performance-v1.json](reference-performance-v1.json) are the
  checked WP-09/WP-10 quality scopes for coverage, deterministic authority
  mutation, complexity, and reference performance.
- [legacy-authority-inventory-v1.json](legacy-authority-inventory-v1.json) is
  the recursive WP-05 migration inventory for legacy registry importers,
  namespaces, process-local cursors, and sentinel issuance candidates. Run
  `python scripts/check_legacy_authority_inventory.py --check`; `--write` may
  record removals but refuses additions relative to the checked artifact.
- [removal-ledger.md](removal-ledger.md) - D-01 through D-18 disposition, replacements, and removal gates.
- [legacy-authority-physical-removal-goal.md](legacy-authority-physical-removal-goal.md) - non-skippable D-06 compatibility-exit and physical deletion gates.
- [release-checklist.md](release-checklist.md) - release validation gates.
  The checked
  [repository settings](../../.github/repository-settings-proposed.json),
  [main ruleset](../../.github/rulesets/main-proposed.json),
  [tag ruleset](../../.github/rulesets/tags-v-proposed.json), and
  [immutable-release policy](../../.github/immutable-releases-proposed.json)
  are inert proposals; remote activation, tag, Release, Stable promotion, and
  merge remain separate explicitly authorized work.
- [SECURITY.md](../../SECURITY.md) - vulnerability reporting and protocol security scope.
- [AGENTS.md](../../AGENTS.md) - repository rules for coding agents.

## Change Classes

Documentation-only changes may update the relevant source-tree document when
they do not alter public behavior.

Implementation changes should identify the affected protocol-core surface:

- Protocol ABI
- Kernel ABI
- Governance Core
- Driver ABI
- Trace ABI
- Conformance Suite
- provider-free examples
- tests

Public API, ABI, schema, conformance, or protocol-invariant changes should be
handled as protocol changes and follow the API lifecycle.

## Patch Standard

A patch should explain the problem, the change, the affected public surface,
compatibility impact, and validation performed.

New abstractions should be small, deterministic, provider-free, and directly
exercised by tests, examples, or conformance.

## Release Standard

A release should pass the Python matrix, deterministic tests, schema/static
contract drift checks, source and selected manifest profiles, TCK v1/v2,
separate external-CWD wheel/sdist consumers, and the exact-artifact
SBOM/provenance gates in the release checklist.

Release notes should call out public API, ABI, schema, conformance, and
migration impact.
