# Decision records

`NNNN-title-with-dashes.md`, zero-padded, **append-only**, MADR-shaped:
Context · Decision · Considered alternatives · Consequences · How this is mechanically confirmed.

"Considered alternatives" is not optional. Rejected options are the part that disappears first, and
the part that stops an agent from re-proposing them.

## Numbering

**Numbers are assigned in the order records are written, not by topic.** They are append-only: never
renumber, never compact, never reuse. There must be no gaps — a gap means a record was planned and
abandoned, and the checker cannot distinguish that from a record that was lost.

One numbering space for all kinds. `kind:` in the front-matter separates them:

```yaml
---
id: 0001
kind: architecture        # architecture | research
status: accepted
supersedes: []
enforced-by: tests/interaction/test_x.py::test_y   # or UNENFORCED (F-xx, gate Gn)
---
```

`kind: research` covers decisions like R3a — a loss model, an EVPI calculation, an economic threshold.
Those record **decision, assumptions, loss vector, summary statistics, limitations and re-evaluation
triggers**, and point at raw evidence rather than copying it:

```text
Raw evidence: local research-data/... (not versioned)
```

Rationale is versioned; raw evidence stays local. Unversioned rationale is invisible to every future
agent, which is why the summary must live here even though the data cannot.

## Assigned and planned

| Number | Title | Status | Subject |
|---|---|---|---|
| `0001` | `retire-the-orchestration-documents` | **written** | Retiring the two orchestration docs to `docs/history/` |
| `0002` | `orchestration-trust-boundary` | planned | Agents propose, the runtime validates, the ledger admits and records |
| `0003` | `canonical-agent-representation` | planned | `agents[]` canonical, `agent` canonicalized at the parser boundary only (L-1, L-2) |
| `0004` | `l1-not-active-in-orchestration` | planned | Multiple eligible executors are an allocation decision, not competing candidates (R-4) |
| `0005` | `durable-allocation-decision` | planned | F-02/F-04 — decision recorded, implemented in G1 (L-11, L-13, L-14) |
| `0006` | `versioned-canonical-serialization` | planned | One canonical serializer; six definitions exist today (F-16) |
| `0007` | `workflow-declared-capacity-model` | planned | Capacity is workflow-level and primitive, derived per task eligible set (L-8) |
| `0008` | `colony-reference-implementation-status` | planned | `runner/colony.py` unreachable by intent (R-1, R-2) |
| `0009` | `r3a-first-read-decision` | planned | `kind: research` — loss model, EVPI, re-evaluation triggers |
| `0010` | `fan-out-verification-method` | **written** | Standing requirements for briefs that fan verification out to sub-agents |

Planned numbers are reserved in that order. A record written out of order takes the next free number
and this table is corrected — the table follows the files, never the reverse.

**Reserved numbers may leave a gap on disk.** `0001` and `0010` exist; `0002`–`0009` are reserved and
unwritten. A checker asserting "no gaps" must therefore read this table: a gap is legal only when it
corresponds to a `planned` row here. An unexplained gap still means a record was written and lost,
which is what the rule exists to catch.

## Provisional numbers used during planning — do not trust them

Earlier planning discussed a set of records by number **before any was written**. `0001` was then
taken by the retirement record, which was written first, so every provisional number is off by one.
Those references survive in planning reports and in this project's conversation history.

| Referred to during planning as | Actually assigned |
|---|---|
| `0001-orchestration-trust-boundary` | `0002` |
| `0002-canonical-agent-representation` | `0003` |
| `0003-l1-not-active-in-orchestration` | `0004` |
| `0004-durable-allocation-decision` | `0005` |
| `0005-versioned-canonical-serialization` | `0006` |
| `0006-workflow-declared-capacity-model` | `0007` |
| `0007-colony-reference-implementation-status` | `0008` |
| `0008-r3a` | `0009` |

**Cite a record by title, not by number, when the number is not yet assigned.** A title survives a
renumbering; a number does not. No tracked file currently references a provisional number — the only
ADR references in the repository are to `0001`, and both are correct.
