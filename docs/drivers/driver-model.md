# Driver ABI

`pheroos.drivers` defines generic capability adapters.

Driver surfaces:

- descriptor
- registration
- probe result
- binding
- handle
- result
- health
- registry

Lifecycle:

```text
declare -> validate -> register -> probe -> bind -> expose -> invoke -> trace
```

Drivers provide capability. Protocol provides authority.

Drivers return structured results with provenance. They do not author final conclusions.
