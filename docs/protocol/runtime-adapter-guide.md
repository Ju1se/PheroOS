# Runtime Adapter Guide

Status: draft adapter mapping contract

This document describes how an external runtime maps PheroOS `DriverSpec`
declarations to real model, tool, data, storage, or sandbox adapters.

Protocol-core does not implement provider adapters.

## Boundary

PheroOS protocol-core owns:

- provider-neutral driver declarations
- generic driver lifecycle objects
- kernel planning contracts
- governance authority boundaries
- trace event ABI
- conformance checks

An external runtime owns:

- adapter registry
- provider SDK calls
- tool execution
- database or memory backend access
- credential loading
- retry, timeout, and circuit-breaker policy
- deployment-specific sandboxing

Provider code belongs outside protocol-core.

## DriverSpec Fields

`DriverSpec` is the manifest-level declaration consumed by an external runtime.

| Field | Meaning | Runtime responsibility |
| --- | --- | --- |
| `id` | Stable manifest driver id. | Use as the declared adapter instance id. |
| `kind` | Provider-neutral capability class. | Map to an external adapter factory. |
| `version` | Declared driver contract version. | Check compatibility before binding. |
| `capabilities` | Exposed capability names. | Match requested operations to declared capability. |
| `permissions` | Permissions requested by the capability. | Bind only granted permissions. |
| `config_ref` | Opaque external configuration reference. | Resolve outside protocol-core. |
| `extensions` | Namespaced metadata. | Preserve for external runtime use without granting authority. |

The manifest must not contain API keys, tokens, passwords, credentials, or
provider configuration values.

## Adapter Registry

An external runtime should maintain its own adapter registry.

The registry maps a provider-neutral `DriverSpec` to an adapter factory. The
mapping may use `kind`, `capabilities`, `version`, or namespaced extension
metadata.

Example mapping classes:

- `model`
- `tool`
- `data`
- `storage`
- `sandbox`
- `ext.<runtime>.model`
- `x-<runtime>-tool`

Namespaced kinds are runtime-owned. They do not add protocol authority by
themselves.

## Mapping Sequence

External runtimes should map drivers in this order:

```text
load manifest
-> validate manifest
-> create kernel plan
-> read DriverSpec declarations
-> find external adapter factory
-> resolve config_ref outside protocol-core
-> probe adapter availability
-> bind tenant/run scope and granted permissions
-> expose runtime handle
-> invoke adapter through runtime policy
-> return structured result with provenance
-> emit trace event
-> convert eligible result into evidence
-> let governance decide commit/output authority
```

The adapter invocation result does not commit a candidate and does not
authorize output.

## Config References

`config_ref` is an opaque string.

Protocol-core must not resolve it, dereference it, validate provider-specific
shape, read secrets from it, or treat it as authority.

Valid uses include pointing to external runtime configuration such as:

```text
runtime.model.primary
tenant.default.search-tool
secrets://runtime-owned/model-provider
```

Those examples are identifiers only. The manifest must not include the resolved
secret values.

## Adapter Requirements

A compatible external adapter should:

- fail closed when its `DriverSpec` cannot be mapped
- fail closed when `config_ref` cannot be resolved by the runtime
- expose only declared capabilities
- bind only declared driver permissions that were granted by the runtime
- never treat capability-level permissions as driver permissions by fallback
- return structured results
- include provenance when a result may become evidence
- emit trace lineage for expose and invoke behavior
- never make final governance or output decisions

Adapter results may become evidence only when the evidence policy and
governance rules allow it.

## Trace and Evidence

Trace records explain what happened. They do not grant permission.

A runtime may emit built-in trace event types or namespaced extension event
types. Namespaced event types are useful for runtime lineage, but they remain
trace records only.

When an adapter result is used as evidence, the runtime should preserve:

- driver id
- adapter operation
- provenance id or source reference
- trace event id
- run id or tenant-scoped context when available

Governance still decides whether the evidence satisfies the output contract.

## Failure Semantics

An external runtime should distinguish:

- unknown driver id
- unsupported driver kind
- incompatible driver version
- unresolved `config_ref`
- failed probe
- missing permission grant
- unavailable provider
- invocation failure
- result without required provenance

These failures may degrade availability or deny a runtime operation. They must
not bypass governance, synthesize evidence, commit a candidate, or authorize
output.

## Conformance

Conformance checks the protocol-facing side of the adapter boundary:

- manifest shape
- driver declaration shape
- secret-boundary behavior
- trace contract
- output contract
- extension contract
- package boundary rules

It does not test external provider SDK behavior. External runtimes should add
their own adapter tests around provider-specific behavior.
