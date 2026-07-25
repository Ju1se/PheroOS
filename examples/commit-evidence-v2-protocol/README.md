# Commit Evidence v2 Protocol

This deterministic, provider-free example executes the public Commit Evidence
v2 Conformance journey against the reference StateStore v2 adapter. It commits
Principal Verification, Membership, Replay receipts, and one complete Evidence
replacement; verifies the exact six-stream CAS read set and Trace lineage;
rejects portable look-alikes as authority; restarts and rehydrates the Store;
proves that two independent principals can satisfy the declared gates while a
single principal cannot; and proves that conflicting genesis proposals produce
one current head.

```bash
python3 examples/commit-evidence-v2-protocol/run.py
```

No model provider, API key, network service, database, worker, or agent runtime
is used. The reference adapter is deterministic Conformance infrastructure, not
a production persistence recommendation. A production runtime supplies its own
StateStore v2 implementation and must pass the same public Conformance matrix.
