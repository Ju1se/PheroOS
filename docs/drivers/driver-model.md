# Driver ABI

`pheroos.drivers` defines the provider-neutral capability adapter ABI.

Drivers provide capability. Protocol and governance provide authority.

## Owned Surface

- descriptor
- registration
- probe result
- binding
- handle
- scoped invocation request, result, and receipt
- readiness probe snapshot
- registry

## Lifecycle

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

Lifecycle operations fail closed. Invalid descriptors cannot register, inactive
registrations cannot bind, bindings without granted permissions cannot expose,
and invocations that may feed evidence require provenance.

Registration is canonical and conflict-safe: an identical descriptor is an
idempotent retry, while the same driver id with different version,
capabilities, permissions, configuration reference, or extensions is rejected.
Bindings and invocations carry the tenant/run `scope_ref`. A result must match
the exact driver, operation, invocation id, request digest, and scope; an
idempotency key may replay only the identical request.

Descriptor identity fields must be nonblank strings. Descriptor capability
inputs are defensively snapshotted as immutable values before validation, so a
caller cannot change registered capability state after the trust boundary.

The original `driver.schema.json` remains the byte-frozen legacy v1 document.
New wire integrations use `driver-v2.schema.json` and the independent
`descriptor_version`; provider `version` is not an ABI selector. The explicit
v1 adapter rejects declarations that would require silent removal or
deduplication. See the
[schema migration](../process/schema-v1-v2-migration.md).

## Rules

- Driver declarations are provider-neutral.
- Provider-specific adapters live outside protocol-core.
- Drivers return structured results with provenance.
- Driver results do not author final conclusions.
- Probe availability and runtime readiness are distinct; a driver is ready only
  when schema, connection, version/capability, probe, permission, and exposure
  requirements all pass.
- Driver invocation does not bypass governance or output authorization.
- `config_ref` is an opaque external reference owned by an external runtime.
- Protocol-core must not resolve `config_ref` or store provider secrets.

## Manifest Shape

Manifest driver declarations use the `DriverSpec` shape. A compatible external
runtime may map a `DriverSpec` to a real adapter, but that adapter code belongs
outside this repository.

Driver ABI changes should follow the public API and ABI lifecycle rules.

`DriverHealth` and the five specialized descriptor subclasses remain Draft
compatibility surfaces only. New integrations use `DriverProbeResult` and the
canonical `DriverDescriptor`; their removal gates are recorded in the
[architecture removal ledger](../process/removal-ledger.md).
