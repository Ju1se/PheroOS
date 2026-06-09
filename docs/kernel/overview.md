# Kernel ABI

`pheroos.kernel` defines the operating-system boundary for governed runtime planning.

The kernel owns:

- input envelopes
- OS plans
- capability resolution
- permission grants
- connection requirements
- driver exposure
- tool exposure
- runtime context materialization
- kernel syscalls

## Invariants

- The kernel plans availability.
- The kernel does not make conclusions.
- The kernel does not call tools directly.
- The kernel does not access secrets directly.
- Runtime context is tenant-scoped and run-scoped.
- Tool exposure requires granted permission.
- Missing required capability produces a degraded or not-ready plan.
