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
- One canonical `RuntimeScope`/`scope_ref` binds plans, contexts, driver
  syscalls, results, and the outer Governance/Trace composition.
- Driver and tool exposure require granted permission.
- Missing required capability produces a degraded or not-ready plan.
- Driver exposure is derived from declared provider-neutral driver specs.
- Driver exposure uses declared driver permissions only and does not inherit capability-level permissions by fallback.
- Driver syscall replies require matching driver id, scope, operation,
  invocation id, request digest, and provenance.
- `available` and `runtime_ready` require valid declaration, required
  connections, compatible driver version/capabilities, an available probe,
  and complete permission/exposure grants; missing leaves are structured
  diagnostics.

The original `kernel.schema.json` remains the byte-frozen legacy v1 plan
document. `kernel-v2.schema.json` requires `plan_version`, canonical run scope,
readiness, and probe snapshots. Reading v1 produces a non-authoritative
`LegacyOSPlan`; upgrading requires all missing authority facts explicitly and
never synthesizes them. See the
[schema migration](../process/schema-v1-v2-migration.md).

`runtime-scope-v1.schema.json` is the closed portable wire shape. JSON Schema
validation proves only that shape, version, basic text form, and the 1024-character
per-component resource bound. It cannot prove that `scope_ref` was derived
from the submitted `tenant_id` and `run_id`; authoritative input must also pass
`RuntimeScope.from_dict(...)`, which recomputes and compares that identity.
The typed portable reader also enforces Unicode NFC and rejects unpaired
Unicode surrogate code points, which JSON Schema cannot express here.  This
keeps the derived identity portable across Python and Unicode-scalar-only
implementations.
The length bound is a wire-only portability limit with one internal owner used
by both parser and schema generation. Existing Python construction remains
backward compatible, but a value outside the portable text rules cannot be
serialized or transported as Runtime Scope v1 authority.

## Import Boundary

The kernel may import protocol and driver contracts. It should not import
governance directly and must not depend on app runtime, provider framework,
database, queue, server, or dashboard code.

Governance decisions should be represented through explicit contracts,
dependency injection, or outer runtime and conformance composition.
