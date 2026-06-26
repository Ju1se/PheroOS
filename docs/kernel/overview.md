# Kernel ABI

`pheroos.kernel` defines the planning boundary for governed runtime
composition.

The kernel decides what is available. It does not decide what is allowed and it
does not execute provider calls.

## Owned Surface

- input envelopes
- OS plans
- capability resolution
- permission grants
- connection requirements
- driver exposure
- tool exposure
- runtime context materialization
- syscall-style request and reply contracts

## Invariants

- The kernel plans availability.
- The kernel does not make conclusions.
- The kernel does not call tools directly.
- The kernel does not call model providers directly.
- The kernel does not access secrets directly.
- Runtime context is tenant-scoped and run-scoped.
- Tool exposure requires granted permission.
- Missing required capability produces a degraded or not-ready plan.
- Driver exposure is derived from declared provider-neutral driver specs.
- Driver exposure uses declared driver permissions only and does not inherit capability-level permissions by fallback.

## Import Boundary

The kernel may import protocol and driver contracts. It should not import
governance directly and must not depend on app runtime, provider framework,
database, queue, server, or dashboard code.

Governance decisions should be represented through explicit contracts,
dependency injection, or outer runtime and conformance composition.
