---
id: 0010
kind: architecture
status: accepted
supersedes: []
enforced-by: UNENFORCED (gate G0.5)
---

# 0010 · Fan-out verification method

## Context

Migrating the retired documents required verifying 76 classified claims against code. Two runs were
needed. The first returned **0 of 6** subsystems and the transcripts explain why: a permission gate
refused `python -m pytest -q` with no node id — the exact command the brief named as the source of
`[executed]` evidence — and refused a long multi-statement `awk`. **A refused tool call does not error
from the orchestrator's side.** The agent detours or stalls, the journal shows `started` with no
`result`, and the only trace is in the agent's own transcript. Compounding it, the orchestrator killed
the run at ~15 minutes while all six were still working.

The second run, with corrected command guidance and a per-claim budget, returned 5 of 5 with **zero
rejected tool calls** and no errors.

Separately, seeded confirm-or-refute checks proved their worth: three already-settled results were
planted in the briefs, and all three came back independently reproduced — including a precise wording
("absent by construction, not switched off") that survived unweakened, and a table count re-derived
exactly.

## Decision

Every fan-out brief carries four standing requirements.

**1 · `rejected_tool_calls` is a mandatory output field.** Present even when empty. An absent section
means the run is unreported, not clean — because a refusal is invisible from the outside.

**2 · The brief states the command forms.** Node-scoped `pytest -q "file::test"` works; the bare
full-suite run is gated and will be refused; prefer a short python heredoc over a long multi-statement
`awk`; do not run a CLI that writes an output directory during a read-only pass.

**3 · Never retry a rejected call.** Use a different form and record it.

**4 · Explicit per-claim budget.** Roughly 5–8 tool calls; beyond that return `UNVERIFIABLE` and move
on. Settling ten claims with two honest unverifiables beats settling six perfectly and never reporting
the rest.

**5 · Seed confirm-or-refute checks.** Plant already-settled results in each brief and require the
agent to confirm or refute them. This is cheap verification of the verifiers, and it catches both
fabrication and silent weakening of precise wording.

## Considered alternatives

**Partial result flushing every N claims.** Rejected — **not implementable.** A subagent returns one
structured result; there is no streaming interface to emit partial output back to the orchestrator
mid-run. Recorded here so it is not attempted again.

The substitute: **transcript growth as a liveness signal.** Byte and line counts of an agent's
transcript can be read without consuming context, and they correctly distinguished "working" from
"stuck" — the pilot sat at 852 KB and growing while the earlier killed agents had plateaued. The
per-claim budget is the real control; growth monitoring only tells you whether to keep waiting.

**A longer fixed timeout.** Rejected — it guesses rather than measures, and the first run's failure was
not slowness but a silent refusal that a longer wait would not have resolved.

**Retrying refused calls with elevated permissions.** Rejected — a read-only verification pass must not
escalate to obtain evidence; if a form is gated, a different form is used and the gate is recorded.

## Consequences

- Every fan-out brief grows by a fixed preamble. Accepted: the first run cost a full pass.
- `UNVERIFIABLE` appears more often, by design. A budgeted unverifiable is a result; a silent omission
  is not.
- Seeded checks consume a little agent effort on already-known facts, in exchange for a signal about
  whether the run's novel findings can be trusted.

## How this is mechanically confirmed

```text
1. Every fan-out brief contains the four standing requirements and at least one seeded check.
2. Every returned result carries a rejected_tool_calls field.
3. No brief instructs an agent to run the bare full suite.
```

These are checks over orchestration inputs, not over the repository, so no repository test enforces
them — hence `enforced-by: UNENFORCED`. They bind the orchestrator.
