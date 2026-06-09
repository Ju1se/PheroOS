# Capability Authoring

A capability is the extension boundary for the AI OS. It may package tools,
skills, adapters, UI metadata, data packages, and agent manifests, but it should
not edit orchestrator code directly.

## Layout

```text
capabilities/<capability-id>/
  capability.json
  agents/*.json optional
  SKILL.md optional
  tools.py optional
  adapters.py optional
  ui.schema.json optional
```

## Manifest Contract

```json
{
  "id": "wrds-financial-data",
  "name": "WRDS Financial Data",
  "version": "0.1.0",
  "description": "Read-only professional financial data.",
  "capability_types": ["financial_fundamentals", "valuation"],
  "permissions": ["data:read", "network:wrds", "secret:wrds"],
  "risk_level": "low",
  "required_connections": ["wrds"],
  "tools": ["wrds_company_financials"],
  "skills": ["wrds-data"],
  "data_packages": ["annual_financials_10y"],
  "agents_path": "agents",
  "entrypoints": {
    "workflow": "workflow.py:build_workflow_descriptor",
    "data_contract": "data_contract.py:build_data_contract_descriptor",
    "evidence_adapter": "evidence_adapter.py:build_evidence_adapter_descriptor",
    "ui_schema": "ui.schema.json"
  },
  "swarm": {
    "targets": [
      {
        "target": "decision:formal_valuation",
        "demand_strength": 0.92,
        "keywords": ["valuation", "data", "risk"],
        "summary": "Decide whether formal valuation is allowed."
      }
    ],
    "recovery_protocols": [
      {
        "id": "data_gate_recovery",
        "targets": [{"target": "decision:formal_valuation", "demand_strength": 0.9}],
        "max_rounds": 3,
        "recruitment": "target_pressure"
      }
    ],
    "candidate_policy": {
      "candidate_type": "investment_decision",
      "candidates": [
        {"id": "candidate:investment:watch", "label": "Watch"},
        {"id": "candidate:investment:insufficient_data", "label": "Insufficient Data"}
      ]
    },
    "quorum_policy": {
      "candidate_type": "investment_decision",
      "evidence_coverage_weight": 0.35,
      "source_independence_weight": 0.25,
      "source_quality_weight": 0.2,
      "max_swarm_rounds": 3
    },
    "stop_signal_policy": {
      "authority_level_required": 3,
      "blocking_lifetime": "until_resolved",
      "blocked_actions": ["writer:formal_valuation"]
    }
  },
  "ui": {"icon": "database", "accent": "green"}
}
```

## PheroOS Protocol Fields

Capability manifests are now the preferred place to declare PheroOS workflow
governance. The OS Kernel reads these fields before falling back to legacy
intent defaults:

- `swarm.targets` declares canonical goals the capability contributes to.
- `swarm.recovery_protocols` declares target-pressure recovery hooks and the
  maximum recovery rounds.
- `swarm.candidate_policy` declares the candidate set for quorum. This keeps
  non-investment capabilities from inheriting Buy/Watch/Avoid/Sell semantics.
- `swarm.quorum_policy` declares evidence, independence, risk, stop-signal, and
  max-round weights for the swarm loop.
- `swarm.stop_signal_policy` declares which actions can be blocked and what
  authority level is required.

The runtime normalizes these declarations through
`runtime/swarm/protocol.py`; agents still only emit proposals. Data Gate,
Permission Policy, Signal Verifier, Quorum Marshal, Writer Guardrails, and
Final Judge remain the authority-bearing protocol actors.

## Rules

- Secrets never belong in manifests.
- Low-risk read-only capabilities may be auto-enabled by the OS Kernel.
- Dangerous permissions require user confirmation.
- Tools declared by a capability must still be registered through the runtime
  tool boundary.
- A capability can expose agents, but agents are selected separately by the user
  or OS committee planner.
- A capability should declare PheroOS targets and policies instead of requiring
  `runtime/graph.py` or `runtime/swarm/goal_router.py` changes.
