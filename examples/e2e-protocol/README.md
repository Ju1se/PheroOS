# E2E Protocol Example

This provider-free example exercises the minimal governed path:

- manifest validation
- kernel plan and runtime context
- driver declaration, probe, bind, expose, and invoke
- evidence provenance
- authority-gated signal verification
- declared-candidate quorum commit
- output authorization
- trace lineage

Run:

```bash
pheroos validate examples/e2e-protocol/capability.json
pheroos conformance examples/e2e-protocol
```
