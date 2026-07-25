# Distributed Commit v2 Protocol

This deterministic, provider-free example runs the public durable Distributed
Commit v2 matrix against the reference StateStore conformance adapter. It
commits the fixed epoch, proposal, witness, and certificate streams; binds a
sealed Decision, a verified central Certificate, static Membership, and the
principal-verification set; verifies one trusted quorum witness; produces the
opaque distributed finality handle; and rehydrates all four current lanes after
a fresh Store restart. It then verifies a fully bound external Byzantine
proposal+witness observation, freezes only the existing witness lane, preserves
the original proposal and certificate authority, rehydrates the complete
conflict finding after restart, emits the existing conflict Trace event, and
drives the next sealed Decision to `SAFETY_VIOLATION`.

```bash
python3 examples/distributed-commit-v2-protocol/run.py
```

No model provider, API key, network service, database, worker, or agent runtime
is used. The reference adapter is an executable protocol proof, not a
production persistence recommendation. The active conformance test runs the
same matrix against both the reference Store and the independent standard
library Store model. Production runtimes must pass that public Store contract
with their own durable adapter.
