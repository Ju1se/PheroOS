# Driver ABI

`pheroos.drivers` defines the provider-neutral capability adapter ABI.

Drivers provide capability. Protocol and governance provide authority.

## Owned Surface

- descriptor
- registration
- probe result
- binding
- handle
- result
- health
- registry

## Lifecycle

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

## Rules

- Driver declarations are provider-neutral.
- Provider-specific adapters live outside protocol-core.
- Drivers return structured results with provenance.
- Driver results do not author final conclusions.
- Driver invocation does not bypass governance or output authorization.
- `config_ref` is an opaque external reference owned by an external runtime.
- Protocol-core must not resolve `config_ref` or store provider secrets.

## Manifest Shape

Manifest driver declarations use the `DriverSpec` shape. A compatible external
runtime may map a `DriverSpec` to a real adapter, but that adapter code belongs
outside this repository.

Driver ABI changes should follow the public API and ABI lifecycle rules.
