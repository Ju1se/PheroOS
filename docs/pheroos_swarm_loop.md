# PheroOS Swarm Loop

The generic swarm loop is the protocol runtime that sits between OS planning
and final output. It does not make domain truth by itself. It reads capability
protocol declarations, turns them into target pressure and governance state, and
lets system authorities decide what can be verified, blocked, recovered, or
published.

## Flow

```text
InputEnvelope
-> OSPlan
-> capability protocol bundle
-> target pressure and initial signals
-> generic control loop
-> recovery, quorum, stop-signal resolution
-> Writer and Final Judge contracts
```

The main implementation is in `runtime/swarm/control_loop.py`. Generic workflow
hosting for arbitrary descriptor graph modes lives in
`runtime/workflows/generic_swarm_workflow.py`; the LangGraph shell delegates
those modes to the `workflow_host` node in `runtime/graph.py`.

## Protocol Inputs

The loop consumes these capability-declared sections from the OS swarm plan:

- `target_signals`
- `candidate_policy`
- `quorum_policy`
- `stop_signal_policy`
- `recovery_protocols`
- `evidence_policy`
- `output_policy`
- `agent_selection_policy`
- `tool_policy`

Capabilities define the targets and candidates. Agents may propose evidence,
signals, or conclusions, but the protocol remains the authority.

## Recovery

Recovery is target-driven. `runtime/swarm/recovery_engine.py` selects recovery
protocols by canonical target, then recruits by declared roles, capability tags,
trust, maturity, and active target pressure. Required recovery tools execute
through `runtime/tool_registry.py`; failures are structured and may trigger a
declared fallback candidate.

## Quorum

Quorum candidates come from capability protocol declarations through
`runtime/swarm/candidate_registry.py`. The quorum code does not create
investment candidates for other capabilities. Buy/Watch/Avoid/Sell work only
when the value-investing capability declares them.

## Stop Signals

Stop signals are active blockers over canonical targets and actions. A
capability can declare which targets block which actions through
`stop_signal_policy.rules`. It can also declare `action_markers` so Writer or
Final Judge action detection is capability-owned rather than a central phrase
table.

Global safety policy remains non-weakenable. A capability may add restrictions,
but it cannot override secret redaction, tool policy, source policy, prompt
injection quarantine, or raw-data final-output guards.

## Output

Writer and Final Judge consume `OutputPolicy` and `EvidencePolicy` through
`runtime/output_contract.py`, `runtime/writer_guardrails.py`, and
`runtime/final_judge_guardrails.py`. Final text must respect committed
candidates, required caveats, evidence graph constraints, defect-memo
requirements, and raw-data restrictions.

## Trace

The swarm loop writes normalized governance events and signals into
`runtime/swarm/trace_store.py`. Decision Debugger endpoints can explain why a
target was blocked, why a candidate was committed, why an agent activated, how
recovery ran, and which capability protocol supplied the rule.
