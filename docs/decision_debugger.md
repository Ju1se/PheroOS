# Decision Debugger

Decision Debugger explains governance decisions from persisted run trace data.
It is backed by `runtime/swarm/trace_store.py` and exposed through platform API
routes in `app/routes/platform.py`.

## Stored Data

The trace store persists:

- run metadata and OS routing trace
- normalized swarm events from `pheromone_trace`, `swarm_protocol_trace`, and
  `swarm_control_loop.events`
- normalized signal lifecycle events derived from stored pheromone signals
- normalized target-pressure events derived from generic control-loop reports
  or protocol target pressure when explicit events are absent
- pheromone signals
- quorum decisions
- evidence graph nodes and edges
- agent allocation events
- tool policy events
- permission events

Sensitive values are redacted before they are stored.

## Endpoints

The platform exposes:

- `/platform/swarm/runs/{run_id}/timeline`
- `/platform/swarm/runs/{run_id}/why-blocked/{target}`
- `/platform/swarm/runs/{run_id}/why-committed`
- `/platform/swarm/runs/{run_id}/why-agent/{agent_id}`
- `/platform/swarm/runs/{run_id}/evidence-graph`
- `/platform/swarm/runs/{run_id}/recovery-lineage/{target}`
- `/platform/swarm/runs/{run_id}/capability-protocol`

`/runs/{run_id}/trace` exposes the aggregate run trace.

## What It Explains

`why-blocked` returns active blocking signals, related evidence nodes, and
target-scoped protocol lineage. The protocol lineage names matching target
signals, capability protocol declarations, stop-signal rules, and recovery
protocols so the caller can see which capability produced the rule.
When normalized blocking `signal.*` events exist for the target,
`why-blocked` uses those event records before falling back to persisted
pheromone signal rows.

`why-committed` prefers normalized `candidate.committed` events and falls back
to persisted quorum data only when the event is missing. It also returns
candidate protocol lineage, including matching capability-declared candidates,
quorum fallback policy, candidate source, and committed fallback identity when
that data is present in the run protocol bundle.

`why-agent` reports activation status, allocation events, target pressure,
agent-selection policy, routing trace, selected protocol source, and activated
agent lists. It also returns agent protocol lineage, including matching target
signals and capability protocol agent-selection policy for the agent's matched
targets.
When normalized `agent.allocated` or `agent.suppressed` events exist, the
`why-agent` and `agent-allocation` readers use those event records before
falling back to the compatibility allocation table.

The `tool-events` and `permission-events` readers likewise prefer normalized
`tool.*` and `permission.*` timeline events before falling back to their
compatibility tables.

When the persisted Evidence Graph tables are empty, `evidence-graph` derives a
minimal graph from normalized governance events: claim lifecycle events become
claim nodes, artifact quarantine events become artifact blocker nodes, and
blocking signal events become signal nodes.

The timeline and reconstructed governance snapshot include
`target.pressure.updated` events so target-pressure changes can be replayed from
event data instead of only from allocation payloads.
Explicit protocol/control-loop events are persisted before derived fallback
events, so runtime-emitted lifecycle, pressure, candidate, claim, and feedback
events remain the authoritative timeline records when present.
They also include reconstructed `candidate.blocked` and
`outcome_feedback.updated` events when a completed run recorded blocked quorum
candidates or process-only outcome feedback without explicit timeline events.
Quarantined artifacts and claim lifecycle transitions are normalized as
`artifact.quarantined`, `claim.created`, `claim.verified`, and `claim.blocked`
from input preflight, Social Immunity, Receiver Normalizer, and Evidence
Steward reports.
Output lifecycle events are also reconstructed: guardrail-report drafts become
`writer.blocked`, final-judge guardrail reports become `final_judge.rejected`,
and publishable final text becomes `output.published`.
Core run lifecycle events are reconstructed as `input.received`,
`os.plan.created`, and `runtime.materialized`, and declared candidates are
registered as `candidate.created` events.

`recovery-lineage` reports the selected recovery protocol, selected agents,
fallback candidate, recovery events, signal-resolution report, and
target-scoped protocol lineage showing the capability recovery rule.
When a separate recovery trace payload is absent, the endpoint derives a
minimal recovery trace from normalized `recovery.*` events, including status,
target pressure, selected protocol, selected agents, and fallback candidate when
those fields were emitted by the runtime events.

`capability-protocol` returns the protocol bundle that governed the run,
including target signals, policies, validation diagnostics, routing trace, and
OS routing trace.
If the stored run payload lacks a full protocol bundle, the debugger can
reconstruct capability protocols and target signals from normalized
`capability.protocol.loaded` events. The lineage endpoints use the same
event-sourced protocol bundle when explaining blocked targets, committed
candidates, activated agents, and recovery.

## Current Limitation

The debugger surface is protocol-aware, but not every governance transition is
event-authoritative yet. Explicit runtime events are preferred when present, but
some endpoints still fall back to persisted run tables or payload fields when
normalized events are absent.
