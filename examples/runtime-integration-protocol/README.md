# Runtime Integration Protocol Fixture

This provider-free fixture implements the Draft Runtime Integration transcript
v1 adapter only through public PheroOS facades. It composes Capability schema
v3, Kernel Plan v2, Driver Invocation/Store v2, Governance StateStore and
Baseline Output v2, Scoped TraceStore v2, and the exact compatibility report.

The fixture deliberately uses independent stdlib Driver and Trace stores, the
independent Governance Store adapter, and a Driver checkpoint format different
from the protocol-core reference format. It is conformance plumbing, not a
provider runtime, database, scheduler, worker, server, or deployment template.
Recovery cases expose only readers recreated from the independent Store image;
Certificate currentness is rechecked through opaque post-restart handles, and
permission/stop staleness advances only the selected dependency head.

Run it from any working directory:

```bash
python /absolute/path/to/examples/runtime-integration-protocol/run.py
```

Success prints one JSON object whose `name` is
`runtime_integration_v1_contract` and whose `ok` value is `true`.
