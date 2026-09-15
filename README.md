# PheroOS Interaction Lab

A small experimental package for local evidence visibility and finite multi-agent
interaction. This branch extracts the current v1/v2 behavior; it introduces no
new coordination algorithm and is not the historical protocol-core product.

Default runtime dependencies: **Python standard library only**. No old `pheroos`
or `pheroos-runtime`, provider SDK, model, credentials or network is needed.

## Install and run

```sh
python -m pip install .
pheroos-interaction mock --output /tmp/interaction-mock
pheroos-interaction api-dry-run --output /tmp/interaction-dry
```

The default mock uses a tiny synthetic `fresh_a/stale` task, two agents and two
fixed decision windows. It exercises genuine source publication, version updates,
historical reads, necessary inspections and final evaluation. Mock byte counts
are instrumentation units, not provider token usage or model evidence.

Select another unchanged factorial-v2 cell with `--world fresh_b/complete` and
`--condition owner_script` (also owner_current, eligibility_script,
eligibility_current). All output directories must be new.

## Replay the retained observations

The archive is separate from the active package; see [evidence/INDEX.md](evidence/INDEX.md).
After restoring its payload, use the installed command from any directory:

```sh
pheroos-interaction replay --run /path/to/visibility-prototype-v1/run --output /tmp/v1-replay
pheroos-interaction replay --run /path/to/visibility-factorial-v2/run --output /tmp/v2-replay
```

Replay reconstructs visible records, full projections and exact messages before
using recorded responses. It compares parsing/rejection reasons, direct parents,
real tools versus reuse, original usage, tariff and objective evaluation. A changed
request fails. Replayed responses are labeled offline replay; they are never new
provider receipts or predictions for changed prompts.

## Scope and execution checks

The host is trusted, local and serialized, and the only built-in tool is a synthetic
source read. Leases, source readers/current versions, declared tools/arguments,
bounded private state, durable pre-dispatch reservations, cancellation and unknown
spend retention are real checks. Duplicate IDs do not cause retries. One Session
owns task/call/token state; one existing MoneyLedger owns monetary spending.

Old authority, certificate, BFT/finality, hostile-host, multi-tenant security and
distributed exactly-once guarantees are withdrawn. This is a distinct package/API
and local storage format, not a compatible substitute for frozen core 0.1.0.
Historical authority fields are read only as provenance during replay.

## Optional API boundary

`api-dry-run` validates actual text payloads from a mock path; it never opens a
MoneyLedger, reads credentials or sends a request. Pure policy imports do not
import adapters or task evaluators.

`live` is explicit and requires a **new separate user authorization** for one
exact four-request cell, plus an existing shared ledger. Existing keys or unused
historical budgets are not authorization. `live --help` describes the required
arguments. The authorization JSON must exactly name purpose
`new-paid-interaction-cell`, model `kimi-k2.6`, max_requests `4`, the chosen `world`
and `condition`, data_scope `synthetic-public-only`, and the resolved `ledger` path.
It is a trusted-host declaration, not a security certificate. The adapter retains
the archived tariff and ledger schema; reconfirm provider availability/pricing
before any future separately authorized live work. This migration made no paid calls.

## Tests and migration evidence

```sh
python -m pip install '.[dev]'
python -m pytest -q
```

Tests are network-blocked and use small fixtures and temporary ledgers; retired
core tests are archived, not represented as passing here. The migration report
records independent installation, exact historical replay, package contents,
source/dependency counts, narrowed guarantees and remaining limitations.

[Migration report](MIGRATION.md) · [Future experiment sketch](experiments/current/NEXT.md)
