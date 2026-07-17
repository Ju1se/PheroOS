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
- [project-architecture-hardening-plan.md](project-architecture-hardening-plan.md)
  is the completed, non-normative record of the project-wide architecture
  audit, decoupling, extensibility, cleanup, and release hardening work.
- [removal-ledger.md](removal-ledger.md) - D-01 through D-18 disposition, replacements, and removal gates.
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

A release should pass the Python matrix, deterministic tests, schema/static
contract drift checks, source and selected manifest profiles, TCK v1/v2,
separate external-CWD wheel/sdist consumers, and the exact-artifact
SBOM/provenance gates in the release checklist.

Release notes should call out public API, ABI, schema, conformance, and
migration impact.
