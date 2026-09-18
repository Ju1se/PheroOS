---
id: 0001
kind: architecture
status: accepted
supersedes: []
enforced-by: UNENFORCED (gate G0.5)
---

# 0001 · Retire the two orchestration documents

## Context

`docs/orchestration-architecture.md` (422 lines) and `docs/orchestration-verification.md` (387 lines)
were the orchestration layer's prose record. A §1 classification pass over both, run against code and
test evidence, produced **20 of the 28 stale claims found across the whole migration** — more than the
224-line AGENTS.md preimage contributed.

They are not merely out of date. Three findings decide this:

1. **One of them certifies the absence of a defect that exists.**
   `orchestration-architecture.md:331-333` states that rather than *"scatter
   `task.get("agents", [task["agent"]])` through the runtime and hope, execution refuses it at the
   boundary."* `runner/contracts.py:401-403` is exactly that construct, with 11 live call sites, and it
   is the subject of audit finding F-03. A future agent checking L-2 against the documentation
   concludes the codebase is clean and skips the check. That is an audit-defeating source, not a stale
   sentence. It is also why L-30 exists.
2. **One of them contradicts itself.** `:55` says *"the record is always the list, so nothing
   downstream can assume a single agent"*; `:347` says *"Every task declares one agent."*
3. **Hand-written counts that drift.** `verification.md:71` reports 964 passing tests against an actual
   1016; `:77` claims 455 are new; two of its eight per-file counts have drifted. This is the root
   cause of F-24.

Both were untracked until `336c442`. Retiring an untracked file is indistinguishable from deleting it,
which is why they were committed as-found first.

Migration input for this decision: `docs/history/agents-md-preimage-2026-09-17.md`, sha256
`24e8f70194d877eba0b9b2fa7a7161ee53420f69858aa6d0a2d55feb1fcb6754`, and the classification of both
documents run against code and test evidence.

## Decision

Retire both to `docs/history/`, as-found, byte-identical:

```text
docs/orchestration-architecture.md  → docs/history/orchestration-architecture-2026-09-17.md
docs/orchestration-verification.md  → docs/history/orchestration-verification-2026-09-17.md
```

Surviving content is folded into `ARCHITECTURE.md`, `docs/invariants.md` and the decision records
according to the §1 classification — never copied across wholesale.

**The hand-written test counts are deleted, not migrated.** No count reaches any new document. A
hand-maintained figure that drifts is the defect itself; a count belongs in generated output or
nowhere. The archived originals retain them as evidence of the drift.

`docs/history/**` is frozen archival material: excluded from reference-resolution checking, subject to
a digest-integrity check (`docs/history/MANIFEST.sha256`), and modifiable by no gate.

## Considered alternatives

**Fix in place.** Rejected. Both files mix architecture, verification narrative, invariant wording and
rationale in one text, which is the structure this migration exists to end. Correcting 20 claims would
leave the genre confusion and the drifting counts, and `:331-333`'s certification would have been
rewritten rather than recorded as the thing that defeated an audit.

**Adopt as authoritative annexes, correcting only the errors.** Rejected, and this was the initial
proposal. It would have imported the drift into the new source of truth wholesale. Auditing them first
is what surfaced findings 1–3 above; adoption would have surfaced none of them.

**Delete outright.** Rejected. They hold the source text for 20 stale claims that later decision
records cite as superseded, and `:331-333` is the evidence for L-30. Deleting the evidence of a drift
removes the ability to show the drift happened.

**Keep them tracked in `docs/` with a "superseded" banner.** Rejected. A reader who opens a file in
`docs/` reasonably treats it as current; a banner is prose asking to be ignored, and this repository has
already demonstrated that prose does not hold. `docs/history/` states the status structurally.

## Consequences

- Any reference to `docs/orchestration-*.md` must be repointed; `AGENTS.md` §3 is updated in this pass.
- Content not yet folded exists only in `docs/history/`. Until `ARCHITECTURE.md` is written, the
  orchestration layer has no current prose description — an accepted gap, preferable to a current
  description that is 20 claims wrong.
- The digest manifest must be updated whenever a file is added to `docs/history/`, and never otherwise.
- L-30 is admitted as an invariant because of this decision, with `target: documentation`.

## How this is mechanically confirmed

```text
1. docs/orchestration-architecture.md and docs/orchestration-verification.md do not exist.
2. No tracked document outside the archival trees (docs/history/, audit/) names either path.
   audit/FINDINGS.md is a dated report of the state at audit time; amending it would falsify the
   record it exists to preserve.
3. Every file in docs/history/ matches its digest in docs/history/MANIFEST.sha256.
4. No document outside docs/history/ contains a hand-written test count.
5. Reference-resolution checks skip docs/history/** entirely.
```

Checks 1–2 are runnable today with `git ls-files` and a grep. Checks 3–5 land with the G0.5 checker,
which is why `enforced-by` is `UNENFORCED (gate G0.5)` rather than a test node.
