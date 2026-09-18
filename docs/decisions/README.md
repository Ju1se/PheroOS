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

| Number | Title | Status | Written by | Subject |
|---|---|---|---|---|
| `0001` | `retire-the-orchestration-documents` | **written** | G0.5 | Retiring the two orchestration docs to `docs/history/` |
| `0002` | `orchestration-trust-boundary` | planned | *unassigned* | agents propose · runtime validates · ledger admits (L-6, L-7) |
| `0003` | `canonical-agent-representation` | planned | **G2** | `agents[]` canonical, `agent` canonicalized at the parser boundary only (L-1, L-2) |
| `0004` | `l1-not-active-in-orchestration` | planned | **G0.6** | Multiple eligible executors are an allocation decision, not competing candidates (R-4) |
| `0005` | `durable-allocation-decision` | planned | **G1** | F-02/F-04 — decision recorded, implemented in G1 (L-11, L-13, L-14) |
| `0006` | `versioned-canonical-serialization` | planned | *unassigned* | one canonical serializer; six definitions exist today (F-16) |
| `0007` | `workflow-declared-capacity-model` | planned | *unassigned* | capacity workflow-level, derived per task eligible set (L-8) |
| `0008` | `colony-reference-implementation-status` | planned | **G0.5** | `runner/colony.py` unreachable by intent (R-1, R-2) |
| `0009` | `r3a-first-read-decision` | planned | *unassigned* | `kind: research` — loss model, EVPI, re-evaluation triggers |
| `0010` | `fan-out-verification-method` | **written** | G0.5 | Standing requirements for briefs that fan verification out to sub-agents |

### A reservation is a decision already made, not work not yet done

An `UNENFORCED` invariant is **work not yet done**, so it must name the gate that will do it or it is
not admissible. **An ADR is a decision already made and not yet written down.** The tests are not the
same, and borrowing one for the other loses records:

```text
decision already made, not yet written   →  planned; a gate may be unassigned, but it WILL be written
decision does not yet exist              →  backlog; holds no number
```

Every row above is a decision taken in an earlier pass. Four have no gate that will write them yet and
say so — `*unassigned*` is a visible state, deliberately, for the same reason an unenforced invariant
is visible. **Releasing a reserved number would assert that the decision will never be recorded**,
which is precisely the rationale loss this gate exists to repair.

**A gap in the numbering is legal if and only if README.md has a matching row with status `planned`.**
`released` is not a value that can fill a gap: with it, "this number was never used" and "this record
was written and lost" both pass, and the check stops distinguishing them — which is the only thing it
was built to do.

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
