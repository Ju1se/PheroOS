# PheroOS Minimal

PheroOS Minimal is the no-key reference distro. It proves that PheroOS can run
as a generic AI-as-OS kernel path without WRDS, financial assumptions, external
model providers, or provider secrets.

## Commands

```bash
pheroos init minimal ./minimal-workspace
pheroos run "review this toy claim" --distro minimal --workspace ./minimal-workspace
pheroos trace latest --workspace ./minimal-workspace
```

## Runtime Contract

- Capability: `toy-review`
- Model driver: deterministic mock model
- Tool driver: deterministic mock lookup
- Storage driver: local JSONL trace store
- Network: none
- Secrets: none

The trace records capability lineage, mock driver usage, candidate set,
committed candidate, required caveats, and publication permission. Agents remain
proposal-only; protocol-owned governance commits the output state.

The model, tool, and evidence path is deterministic, but protocol authority is
not mocked. `pheroos run --distro minimal` loads `toy-review` from
`capabilities/toy-review/capability.json` and derives the candidate set,
fallback candidate, required caveats, and FinalJudge checks from that active
capability protocol. The workspace config must also validate as no-network and
no-secrets before a run is recorded.
