# Scoped Baseline Output v2

This provider-free example proves the active Baseline Output v2 ABI from end
to end. It explicitly reads `capability.json` with the Capability Schema v3
selector, activates one local scoped-authority grant, commits two independently
verified signals, lets Governance compute the action permission, and atomically
commits the aggregate output against the complete current read-set.

Run it from the repository root:

```bash
.venv/bin/python -m pheroos.cli.main wire validate capability-v3 \
  examples/scoped-output-protocol/capability.json
.venv/bin/python examples/scoped-output-protocol/run.py
```

The script prints deterministic JSON containing the selected protocol version,
grant operations, computed permission, terminal output, full output read-set,
durable state schemas, and the six Baseline Output trace events.

This is an ABI proof, not an agent runtime or provider gateway. It performs no
network calls, uses no model provider, needs no API key, and does not implement
workers, scheduling, storage infrastructure, or an application server. The
in-memory StateStore is only the provider-free reference implementation of the
public StateStore v2 contract.
