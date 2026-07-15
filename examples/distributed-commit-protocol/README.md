# Distributed Commit Protocol Example

This provider-free example executes the complete static-epoch Byzantine
finality slice through public PheroOS ABI calls. It covers the declared
`n >= 3f + 1` and `2q - n > f` rules, insufficient partitions, one final
quorum, conflicting-certificate freeze, and deadline
`finality_unavailable` output.

```bash
.venv/bin/python -m pheroos.cli.main validate examples/distributed-commit-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/distributed-commit-protocol
.venv/bin/python examples/distributed-commit-protocol/run.py
```

Networking, witness collection, identity keys, storage, and scheduling remain
external runtime responsibilities. This example proves only the deterministic
protocol/governance/trace/conformance contract.
