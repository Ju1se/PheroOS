# Hybrid Commit Protocol Example

This provider-free example walks the checked-in Optimal Commit TCK through the
complete Hybrid separation and liveness path. It executes real public
Protocol, Governance, and Trace APIs through the reference adapter; it does not
print a prerecorded result.

The selected vectors demonstrate critical counterevidence, attention-channel
invariance, first-ready pending, a stable evidence commit, deadline
terminality, declared safe fallback, current publication authority, and no
assurance downgrade. Hybrid pheromone/layer inputs remain attention-only.

```bash
.venv/bin/python -m pheroos.cli.main validate examples/hybrid-commit-protocol/capability.json
.venv/bin/python -m pheroos.cli.main conformance examples/hybrid-commit-protocol
.venv/bin/python examples/hybrid-commit-protocol/run.py
```

`capability.json` activates the Hybrid Commit profile. The script uses the
packaged TCK resource, so it also runs from an installed wheel and an unrelated
working directory.
