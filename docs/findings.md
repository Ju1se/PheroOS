# Findings — live register

**Numbering is shared with `audit/FINDINGS.md` and continues from it.** F-01…F-38 live there. That
file is a dated archival report of the G0 audit: it is covered by the archival-tree rule, so it is
exempt from currency checks, subject to a digest-integrity check, and **cannot be appended to** —
adding to it would falsify the record it exists to preserve and break its digest.

Numbering therefore continues here at **F-39**. Do not restart at F-01. Finding ids are protocol
vocabulary — `docs/invariants.md`, `ARCHITECTURE.md` and the decision records all cite them by number
— and a second F-01 would break every existing reference.

This file is live: post-audit discoveries are appended here as they are found, and entries are
updated as gates close them.

---

### F-39 · One string carries two meanings: the `_vN` table suffix is both schema generation and execution eligibility
Severity: **high** — Category: schema semantics — Evidence: `[measured]`, `[read]`
Locator: `runner/orchestration.py:74-78` (the five orchestration tables), `runner/audit.py:36,63`
(the dispatch), `runner/orchestration.py:407` (the sole decision INSERT)
Command: AST/regex enumeration of every `CREATE TABLE` and every INSERT/UPDATE/DELETE target across
`runner/*.py`

**What is true.** `[measured]` The repository declares **18 durable tables, 13 of them versioned, and
exactly one carries a `_v2` suffix**:

```text
orchestration_tasks_v2          ← the only _v2 table in the repository
orchestration_v1  orchestration_artifacts_v1  orchestration_accounting_v1  orchestration_decisions_v1
platform_v1  platform_work_v1  platform_candidates_v1  platform_decisions_v1  platform_no_entry_v1
coordination_v1  coordination_sources_v1  coordination_inspections_v1
```

`[read]` The suffix is not cosmetic — it selects behaviour. `runner/audit.py:36` declares
`TASK_TABLES = ("orchestration_tasks_v2", "orchestration_tasks_v1")` and `:63` probes them in order,
choosing the reader by which table exists rather than by the format recorded in
`orchestration_v1.spec`.

`[read]` At the same time, L-3 gives `vN` an executable meaning: **v1 is audit/replay-only, v2 is
executable.** So one string is being asked to carry both *schema generation* and *execution
eligibility*, and a single run writes rows across both generations inside one transaction.

**Why it matters.** Nothing distinguishes "not yet migrated" from "never needed migration". A reader
cannot tell whether `orchestration_decisions_v1` is v1 because its shape predates the v2 work, or
because decisions are audit-only — and those imply opposite things about whether it may be extended.
This blocks G1 directly: allocation provenance (F-02/F-04, L-11/L-13/L-14) has to be recorded
somewhere, and `runner/orchestration.py:407` — the sole `INSERT INTO orchestration_decisions_v1` site — is
the obvious target. **G1 must not add a new decision type to a table whose version meaning is
undecided.**

**Fix shape.** Settle the semantics in **G2 (schema boundary)**, in the direction F-05 / L-3(a)
already names: gate on the format recorded in `orchestration_v1.spec`, and treat the table-name probe
as a fallback that must agree with it. Then decide, explicitly, what the suffix denotes — schema
generation or execution eligibility — and make the remaining tables consistent with that answer.
**Do not touch the tables before then.**

Cost: **M** — Risk of fixing: a table rename changes every recorded digest and needs a version bump,
which the repository already has machinery for. The larger risk is doing it in the wrong order:
recording provenance first (G1) would add a row under semantics that are still ambiguous.

Sequencing: **G2 settles, then G1 records.** Blocks: G1. Related: F-05, L-3, L-11, L-13, L-14.

---

### F-40 · Path-based link checking cannot see a referring expression
Severity: **medium** — Category: verification method — Evidence: `[measured]`
Locator: `README.md:208`; the insufficient check is `docs/decisions/0001-retire-the-orchestration-documents.md`, mechanical check 2

**What is true.** `README.md:208` reads *"L0 … is deliberately not wired into agent reasoning — see
the architecture document for why."* That document was retired to `docs/history/` in `7cb6547`. ADR
0001's check 2 searches for the literal paths `docs/orchestration-architecture.md` and
`docs/orchestration-verification.md`; it passed, because the reference is an English phrase, not a
path.

**Why it matters.** The check reported green over a broken pointer it was structurally incapable of
seeing. Same disease as F-42 in another form: a check coarser than the thing it checks.

**Fix shape.** Widen check 2 to catch referring expressions ("the architecture document", "the
verification report") alongside literal paths, or require every cross-document reference to be a path
so the check has something to resolve. Related: F-42, F-43.
Cost: **S** — Risk: a phrase list will over-match; prefer requiring paths.

### F-41 · The reason L0 is not wired existed in no current document
Severity: **high** — Category: rationale loss — Evidence: `[measured]`
Locator: `README.md:207-208` (the dangling pointer); source recovered from
`docs/history/orchestration-architecture-2026-09-17.md:365-370`, sha256 `2e32c034…`

**What is true.** After the retirement, the rationale for L0 remaining unwired into agent reasoning
existed only in an archival file. `docs/invariants.md` has no L0 entry, and no current document held
the reason. `README.md` asserted the fact and pointed at the retired document for the why.

**Why it matters.** This is rationale loss of the species the audit's §J measured: a decision whose
reason survives nowhere a future agent will read. The specific reason — that an agent model step is
open-ended generation rather than a binary observation from a channel with calibrated `q`/`rho`, so
treating the n-th inference as a measurement channel would fabricate an uncalibrated statistical model
— is not derivable from the code.

**Status: resolved in this pass.** Recovered verbatim from the archival source and written into
`ARCHITECTURE.md` §5, citing `docs/history/` by digest. Kept in the register because the *class* of
loss is what matters: retirement moved the text and the rationale went with it (F-43).
Cost: **S** — Risk: none; the archival source is digest-pinned.

### F-42 · Line-based phrase search under-reports on hard-wrapped prose — measured 2 of 4
Severity: **high** — Category: verification method — Evidence: `[measured]`
Locator: `runner/runtime_policies.py:14`, `:284` (the two instances a line-based search cannot see)

**What is true.** A `grep` for the superseded "each task declares one agent" premise across `runner/`
returns **two** live sites. A whitespace-normalized search over the same tree returns **four**:

```text
runner/orchestration.py:548     "Each task declares one agent"          found by grep
runner/runtime.py:23            "each task a single agent"              found by grep
runner/runtime_policies.py:14   "gives each task one agent"             INVISIBLE to grep
runner/runtime_policies.py:284  "gives each task one agent"             INVISIBLE to grep
```

The two missed instances wrap across a line boundary — `one` ends line 14, `agent` begins line 15 —
and `grep` matches within a line. The search was not truncated; it was structurally incapable.

**Why it matters.** A 50% miss rate on the exact defect the counter-source gate exists to fix, and the
half it misses is arbitrary — determined by where the wrap happens to fall. **This finding also
corrects the scope of gate G0.6 from two sites to four.** Any G0.6 brief written against the grep
result would have corrected half the problem and reported done.

**Fix shape.** Checks over prose operate on semantic units, not lines: normalize whitespace across
line boundaries before matching. Recorded as checker-contract rule (f). Related: F-40, F-43.
Cost: **S** — Risk: normalization must not cross a code/prose boundary and match a string literal.

### F-43 · Retirement moved the files but not the rationale they held
Severity: **medium** — Category: procedure — Evidence: `[measured]`
Locator: `7cb6547` (the retirement commit); consequences at `README.md:207-208`, and F-41

**What is true.** `7cb6547` moved both orchestration documents to `docs/history/` and repointed every
path reference. It did not confirm that the rationale those documents held had a current home. One
rationale — the L0 reason — became unreachable, and a referring expression to it was left dangling.

**Why it matters.** Distinct from F-40, where the *check* missed it, and from F-41, where *one*
rationale was lost. This is the procedure lacking a step, so the same loss recurs at every future
retirement.

**Fix shape.** Add to the retirement procedure: before retiring any document, enumerate the rationale
it holds and confirm each has a current home — folded, or explicitly recorded as dropped. Related:
F-40, F-41.
Cost: **S** — Risk: none.
