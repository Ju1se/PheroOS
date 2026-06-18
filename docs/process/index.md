# Development Process

This directory contains the source-tree process documents for PheroOS
protocol-core.

The process documentation is about changing the protocol source tree. It is
not runtime setup documentation and does not describe provider, server,
database, dashboard, or application deployment workflows.

## Entry Points

- [CONTRIBUTING.md](../../CONTRIBUTING.md) - contribution process and patch requirements.
- [api-lifecycle.md](api-lifecycle.md) - public API and ABI lifecycle rules.
- [release-checklist.md](release-checklist.md) - release validation gates.
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

A release should pass deterministic tests, schema consistency checks, baseline
protocol compatibility, governed e2e compatibility, and swarm compatibility
when swarm behavior is declared.

Release notes should call out public API, ABI, schema, conformance, and
migration impact.
