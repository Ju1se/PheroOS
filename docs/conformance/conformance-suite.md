# Conformance Suite

`pheroos.conformance` owns protocol-core compatibility checks.

Checks include:

- manifest schema
- domain-neutral public core
- candidate declaration
- quorum policy
- recovery policy
- output contract
- trace contract
- driver contract
- kernel import boundary

Run:

```bash
pheroos validate examples/toy-protocol/capability.json
pheroos conformance examples/toy-protocol
```

The CLI is thin and delegates to `pheroos.conformance`.
