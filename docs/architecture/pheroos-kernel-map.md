# PheroOS Kernel Map

```text
User Request
  -> PheroOS Kernel ABI
  -> OSKernel
  -> RuntimeMaterializer
  -> Capability Loader
  -> Tool/Data/Model Drivers
  -> PheroOS Swarm Governance
  -> Evidence / Quorum / Recovery
  -> Output / Trace
```

## Boundary Summary

- `pheroos/protocol/`: public protocol ABI wrappers.
- `pheroos/drivers/`: public driver contracts.
- `runtime/`: reference runtime and current compatibility bridge.
- `runtime/swarm/`: governance subsystem implementation.
- `capabilities/`: reference and example capabilities.
- `tools/`: provider/tool adapters.
- `schemas/`: machine-readable ABI snapshots.
- `tests/conformance/`: compatibility guard tests.
