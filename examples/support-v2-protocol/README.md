# Support v2 protocol example

This provider-free example exercises the public Draft ABI in
`pheroos.governance.support_v2`:

1. commit a principal-verification set;
2. derive and commit Sybil-collapsed membership from the Store-current set;
3. initialize the fixed Support ledger;
4. issue one evidence-bound lease;
5. evaluate support without turning the evaluation into authority; and
6. restart the reference conformance Store and rehydrate from canonical wire.

The reference Store is an in-memory conformance implementation, not production
persistence. The example performs no model-provider or network call.

Run it from the repository root:

```bash
python examples/support-v2-protocol/run.py
```
