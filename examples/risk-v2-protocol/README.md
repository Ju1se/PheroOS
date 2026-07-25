# Risk v2 Protocol

This deterministic, provider-free example exercises the public durable Risk
v2 ABI from a Protocol Schema v3 manifest. It activates one least-privilege
`QUALIFY_EVIDENCE` grant, commits an assessment, serializes only the portable
request, reconstructs a fresh StateStore reader, rehydrates Store-backed
authority, and advances the same fixed lineage from epoch 7 to epoch 137.

```bash
python3 examples/risk-v2-protocol/run.py
```

The epoch jump demonstrates that epoch does not participate in Risk stream
identity. A per-epoch design spanning 130 later epochs would exceed the
StateStore's 127 non-lifecycle-stream bound; the public Conformance lane prepares
all 130 epoch proposals and proves that their stream set has size one. The
example then commits the final direct jump: revision two records
`parent_epoch=7`, requires a commit-window reset, supersedes revision one, and
emits the two closed Risk v2 Trace events atomically.

The reference Conformance adapter and its restart helper are deterministic test
infrastructure only. They are not a database, persistence recommendation,
runtime, provider integration, credential system, or production source of
authority. A production runtime supplies its own StateStore v2 adapter and must
pass the public Conformance matrix.
