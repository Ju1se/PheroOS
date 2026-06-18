# Contributing

Thanks for helping improve PheroOS.

PheroOS is a protocol-core package for governed, swarm-native multi-agent runtimes. Contributions should keep the repository small, deterministic, domain-neutral, provider-free by default, and ABI-focused.

## Project Boundaries

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

## Contribution Guidelines

- Prefer explicit dataclasses, pure functions, small schemas, deterministic examples, and direct tests.
- Keep public APIs intentional and documented.
- Keep new behavior covered by tests or conformance.
- Keep examples provider-free, network-free, and domain-neutral.
- Preserve baseline protocol compatibility when adding optional swarm behavior.
- Avoid broad managers, speculative hooks, framework scaffolding, and dependency-heavy implementations.

## API and ABI Changes

Public API or ABI changes should include:

- motivation
- affected public surface
- compatibility impact
- schema impact when applicable
- conformance impact when applicable
- migration notes when behavior changes

Follow [docs/process/api-lifecycle.md](docs/process/api-lifecycle.md) for public API and ABI lifecycle rules.

## Pull Request Checklist

- Public API or ABI impact is described, or the PR has no public API/ABI impact.
- Schema changes are reflected in checked-in schema artifacts, or no schema changed.
- Changelog or migration notes are updated when public behavior changes.
- Protocol models and validation remain domain-neutral.
- Kernel, governance, driver, and trace code do not import app/runtime/provider frameworks.
- Conformance logic remains in `pheroos.conformance`, not product glue.
- Baseline protocols are not forced into swarm-specific requirements.
- CI passes before merge.

## Documentation

Documentation should describe protocol invariants, compatibility boundaries, extension points, and release governance.

Do not turn documentation into product setup guides, provider setup guides, local server runbooks, dashboard instructions, or domain workflow tutorials.
