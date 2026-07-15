# Commit Certificate Replay Example

This provider-free example executes TCK cases 24–26 against the public
certificate and replay ABI. It proves that a fallback/output certificate is not
a commit certificate, every authority leaf mutation is rejected, and a
nonce/receipt cannot be replayed across target, candidate, or epoch.

```bash
.venv/bin/python examples/commit-certificate-replay/replay.py
```

The adapter reconstructs portable roots from JSON-compatible records. It does
not depend on a provider, network, private test object, or repository working
directory.
