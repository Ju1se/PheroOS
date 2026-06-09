# Agent Authoring

Agents are plugin units inside capabilities. They describe a role and routing
metadata; they do not own tools, secrets, or data connections.

## Example

```json
{
  "key": "earnings_quality_agent",
  "name": "Earnings Quality Agent",
  "description": "Audits accruals, cash conversion, one-time items, and accounting risk.",
  "agent_type": "investment_committee_member",
  "committee_role": "quality_reviewer",
  "focus": ["cash conversion", "accruals", "accounting risk"],
  "model_attr": "fundamental_analyst_agent",
  "default_enabled": true,
  "order": 35,
  "tags": ["quality", "accounting", "cash-flow"],
  "required_capabilities": ["investment.research", "valuation"],
  "required_tools": ["metric_registry.compute"],
  "risk_level": "low",
  "swarm": {
    "initial_thresholds": {
      "evidence_verification": 0.25
    },
    "response_demand_profiles": {
      "evidence_verification": {
        "demand": 0.65,
        "reason": "declared evidence-verification demand"
      }
    },
    "signal_emit_permissions": ["evidence", "risk", "quorum"],
    "quorum_weight": 0.7,
    "can_block": false
  },
  "ui": {"accent": "emerald"}
}
```

## Swarm Metadata

The optional `swarm` object lets an agent participate in insect-inspired
governance:

- `initial_thresholds`: response thresholds by task type.
- `response_demand_profiles` / `demand_profiles`: optional task-type demand
  and reason text for response-threshold allocation.
- `signal_emit_permissions`: signal types this agent may emit.
- `quorum_weight`: relative vote/support weight in candidate decisions.
- `can_block`: whether the agent may emit blocking stop-signals.

Use `can_block=true` only for verifier-style agents such as Data Auditor, Risk
Manager, or Red Team. Writer-style agents should not be able to block or verify
evidence.

## Emitting Swarm Signals

Committee agents can propose signals by adding `emitted_signals` to their JSON
output:

```json
{
  "status": "completed",
  "thesis": "The available data supports only a preliminary view.",
  "emitted_signals": [
    {
      "type": "risk",
      "target": "valuation",
      "content": "Formal valuation lacks TTM market data from the metric registry.",
      "strength": 0.7,
      "confidence": 0.6
    }
  ]
}
```

The runtime validates each proposal against the manifest allowlist. Agent
signals are never allowed to self-promote to verified/blocking system facts:
`risk`, `negative`, and `stop_signal` proposals become `contested`; evidence and
quorum proposals remain `unverified`. Rejected proposals appear in
`agent_signal_diagnostics` so the dashboard can explain why they did not enter
the pheromone field. A deterministic verifier may promote a contested
`stop_signal` only when an existing system gate already supports the same target.

## Runtime Behavior

- `AgentRegistry` discovers manifests from `capabilities/*/agents/*.json`.
- Dashboard displays dashboard-safe metadata only.
- Users may select committee members manually.
- `RuntimeMaterializer` passes selected agents into graph metadata.
- `runtime/graph.py` builds committee prompts from the selected agent specs.

Agents should not call WRDS, web, filesystem, or shell tools directly. They
reason over evidence and metric registries produced by deterministic workers.
