# Commit Certificate v2 Protocol

This deterministic, provider-free example runs the public Commit Certificate
v2 portable-verification matrix against two independent verifier adapters. It
proves canonical round trips, the complete eight-authority leaf set, separate
current-Decision and actual-seal bindings, body and envelope tamper rejection,
strict expected-context checks, and the rule that portable certificate bytes
never become governance authority by themselves.

```bash
python3 examples/commit-certificate-v2-protocol/run.py
```

No model provider, API key, network service, database, worker, or agent runtime
is used. The reference and standard-library adapters are deterministic
portable-verification examples, not production trust-store recommendations.
This example does not claim durable StateStore-owner portability. That public
matrix remains behind the shared Decision + Certificate + Distributed
activation gate. A production runtime supplies its own trusted
issuer-attestation verifier and separately proves its StateStore v2 contract.
