# Contributing

This document defines the contribution process for the PheroOS protocol-core
source tree.

PheroOS is a governed authority/commit protocol-core package for multi-agent
runtimes. Core contributions should remain deterministic, domain-neutral,
provider-free by default, and ABI-focused. Start with the
[current support matrix](docs/protocol/current-support.md); historical
swarm/Hybrid plans do not authorize restoring private attention APIs.

Protocol is the authority boundary. Contributions should strengthen that
boundary rather than add application runtime behavior.

## Scope

Contributions should strengthen one of these surfaces:

- Protocol ABI
- Kernel ABI
- Governance Core
- Driver ABI
- Trace ABI
- Conformance Suite
- provider-free examples
- ABI-focused documentation
- deterministic tests

Do not add app runtime infrastructure, product APIs, dashboards, provider gateways, model SDK integrations, background services, queues, databases, plugin marketplaces, or domain-specific workflows to protocol-core.

External runtimes own execution, scheduling, cancellation, retry, and run
recovery. Concrete model/tool/storage adapters belong with the external
runtime or in an adapter package. The independent `pheroos-bench/` package in
this repository owns datasets, experimental algorithms, controls, and
statistics. Bench dependencies and delivery checks belong to that package.
See the [extension boundaries](docs/protocol/extension-points.md).

## Patch Requirements

A change should describe:

- a reproducible problem and the current module that owns the behavior
- why any new class, file, or public API is needed
- the user behavior or protocol invariant proved by the test
- the handling of the previous implementation and compatibility impact
- the exact validation performed and any remaining failure

Prefer one independently verifiable behavior change per PR. Keep internal
refactoring, protocol changes, and experimental methods separately reviewable.
Generated diffs must identify their generator and reviewed source changes.
Tests should come from the problem definition, counterexamples, and independent
verification. A failing check does not justify refreshing unrelated snapshots,
lowering a threshold, or replacing expected results with implementation output.

Prefer explicit dataclasses, pure functions, small schemas, deterministic examples, and direct tests.

Keep examples provider-free, network-free, and domain-neutral.

Preserve baseline protocol compatibility when adding an optional contract.

Avoid broad managers, speculative hooks, framework scaffolding, and dependency-heavy implementations.

## Protocol Change Proposals

A PheroOS Improvement Proposal is required when a change alters a public API,
ABI, schema artifact, conformance rule, or protocol invariant.

A proposal should include:

- motivation
- affected public surface
- compatibility impact
- conformance impact
- schema impact
- migration notes
- validation plan

Small documentation fixes, internal refactors, and tests that do not change
public behavior do not need a proposal.

## API and ABI Changes

Public API or ABI changes should include:

- a concrete consumer and why existing interfaces are insufficient
- affected public surface
- compatibility impact
- schema impact when applicable
- conformance impact when applicable
- migration notes when behavior changes

Follow [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) for public API and ABI lifecycle rules.

All current exports are Draft. Ordinary consumers should start with the smaller
[consumer candidate](docs/protocol/stable-core-consumer.md); it is not formally
Stable. Additions and removals need an explicit lifecycle and migration
decision. Use the existing removal ledger for obsolete compatibility paths
rather than retaining multiple algorithms without a consumer or exit plan.

## Validation

Before submitting a substantive change, run the relevant deterministic checks.
When practical, run the full suite:

```bash
python -m pytest -q
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol
python -m pheroos.cli.main validate examples/e2e-protocol/capability.json
python -m pheroos.cli.main conformance examples/e2e-protocol
python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol
```

Schema changes should keep checked-in schema artifacts aligned with schema
export behavior.

## Review Checklist

- Public API or ABI impact is described, or the change has no public API/ABI impact.
- Schema changes are reflected in checked-in schema artifacts and schema export tests, or no schema changed.
- Changelog or migration notes are updated when public behavior changes.
- Protocol models and validation remain domain-neutral.
- Kernel, governance, driver, and trace code do not import app/runtime/provider frameworks.
- Conformance logic remains in `pheroos.conformance`, not product glue.
- Baseline protocols are not forced into newly declared optional requirements.
- CI passes before merge.

## Documentation

Documentation should describe protocol invariants, compatibility boundaries, extension points, and release governance.

Core documentation should not become product setup guides, provider setup
guides, local server runbooks, dashboard instructions, or domain tutorials.
Bench documents its own research setup. Date historical plans and link their
replacement support description; preserve the original experiment and audit
evidence.
