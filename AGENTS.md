# AGENTS.md

## Project Identity

This repository is the PheroOS protocol-core package.

Agents are not authority. Protocol is authority.

The core package must stay small, cohesive, and domain-neutral. Keep executable code only when it directly supports:

- Protocol ABI
- Kernel ABI
- Governance Core
- Driver ABI
- Trace ABI
- Conformance
- Minimal toy protocol example

## Boundaries

- `pheroos.protocol` must not import `pheroos.kernel`, `pheroos.governance`, app/runtime modules, provider frameworks, tools, or examples.
- `pheroos.kernel` may import `pheroos.protocol` and `pheroos.drivers`.
- `pheroos.governance` may import `pheroos.protocol` concepts, but should remain independent where practical.
- `pheroos.conformance` may import protocol, kernel, governance, and drivers.
- CLI code must stay thin and delegate to core packages.

## Validation

Use:

```bash
.venv/bin/pytest -q
.venv/bin/pheroos validate examples/toy-protocol/capability.json
.venv/bin/pheroos conformance examples/toy-protocol
```

Do not restore the old app runtime to satisfy removed tests.
