# Commit Decision v2 Protocol

This deterministic, provider-free example runs the Draft public Commit
Decision v2 durable conformance journey against both the reference StateStore
and an independent standard-library StateStore implementation.

It commits real StateStore-backed Principal Verification, Membership, Replay,
Evidence, Risk, Support, Stop, Permission, and Decision lineages. The matrix
then proves both bounded missing-input fallback and the complete ready path:
independent evidence assessment, stability, same-step output seal,
evidence-bound finality, restart rehydration, lost-response exact retry, and a
competing-successor CAS race.

```bash
python3 examples/commit-decision-v2-protocol/run.py
```

No model provider, API key, network service, database, worker, or agent runtime
is used. The example demonstrates protocol-core ABI behavior; it is not a
provider gateway or an application runtime.
