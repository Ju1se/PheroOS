# Contributing

This document defines the contribution process for the PheroOS protocol-core
source tree.

PheroOS is a protocol-core package for governed, swarm-native multi-agent runtimes. Contributions should keep the repository small, deterministic, domain-neutral, provider-free by default, and ABI-focused.

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

## Patch Requirements

A change should describe:

- the problem being solved
- the affected public surface
- the user-visible or implementation-visible impact
- compatibility risk
- validation performed

Prefer explicit dataclasses, pure functions, small schemas, deterministic examples, and direct tests.

Keep examples provider-free, network-free, and domain-neutral.

Preserve baseline protocol compatibility when adding optional swarm behavior.

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

- motivation
- affected public surface
- compatibility impact
- schema impact when applicable
- conformance impact when applicable
- migration notes when behavior changes

Follow [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) for public API and ABI lifecycle rules.

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
- Baseline protocols are not forced into swarm-specific requirements.
- CI passes before merge.

## Documentation

Documentation should describe protocol invariants, compatibility boundaries, extension points, and release governance.

Do not turn documentation into product setup guides, provider setup guides, local server runbooks, dashboard instructions, or domain workflow tutorials.
