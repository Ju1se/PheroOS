# Commit Finality v2 Protocol

This deterministic, provider-free example runs the public Commit Finality v2
composite conformance matrix against both the reference StateStore and an
independent standard-library StateStore implementation.

The matrix commits real Certificate, Distributed, and Decision authority
lineages. It proves verified Certificate and Distributed owner handles can
authorize an evidence commit, portable projections and projection roots cannot
replace an opaque owner handle, owner successors invalidate stale Decision
preparations through CAS, a durable Certificate conflict produces a safety
violation, a public verifier-authenticated Distributed conflict observation
commits a freeze-only witness transition whose opaque finality input produces a
Decision safety violation, and a missing handle terminates as finality
unavailable only at the declared deadline. Every path uses real StateStore
transitions; no private reducer or detached frozen state is used.

```bash
python3 examples/commit-finality-v2-protocol/run.py
```

No model provider, API key, network service, database, worker, or agent runtime
is used. The example proves protocol-core ABI behavior; it is not an
application runtime.
