# Protocol Spec v0.1

The protocol manifest is a versioned governance declaration embedded in a
capability manifest under `protocol`, `pheroos_protocol`, or `pheroos`.
`runtime/swarm/protocol_loader.py` loads the declaration and
`runtime/swarm/protocol_validation.py` validates references and trust-sensitive
rules.

## Required Shape

```json
{
  "version": "0.1.0",
  "intents": ["toy_review"],
  "intent_keywords": {"toy_review": ["toy", "review"]},
  "required_capability_types": ["toy.review"],
  "required_capability_types_by_intent": {"toy_review": ["toy.review"]},
  "targets": [
    {
      "target": "gate:toy_evidence_gate",
      "target_type": "gate",
      "aliases": ["toy evidence"],
      "compatible_intents": ["toy_review"]
    }
  ],
  "candidates": [
    {"candidate": "candidate:toy:approve", "target": "gate:toy_evidence_gate"},
    {"candidate": "candidate:toy:insufficient_evidence", "safe_fallback": true}
  ],
  "quorum_policy": {
    "candidates": ["candidate:toy:approve", "candidate:toy:insufficient_evidence"],
    "candidate_fallback": "candidate:toy:insufficient_evidence"
  },
  "stop_signal_policy": {
    "blocked_targets": ["gate:toy_evidence_gate"],
    "blocking_authority_required": 2
  },
  "recovery_protocols": [
    {
      "recovery_id": "toy_evidence_recovery",
      "trigger_targets": ["gate:toy_evidence_gate"],
      "allowed_agent_roles": ["evidence_scout"],
      "success_condition": "verified evidence proposal is available"
    }
  ],
  "evidence_policy": {
    "raw_data_allowed_in_final": false,
    "min_independent_sources": 1
  },
  "tool_policy": {
    "allowed_tool_targets": ["tool:read_file"],
    "required_permissions": ["data:read"]
  },
  "output_policy": {
    "allowed_output_modes": ["normal", "degraded", "defect_memo"],
    "writer_can_create_facts": false
  }
}
```

## Authority Rules

- Agents propose; protocol/governance validates.
- Candidates must be declared before quorum can commit them.
- Recovery is selected by declared trigger targets, allowed roles, required
  tools, and success/failure conditions.
- Writer and FinalJudge consume output, evidence, stop-signal, and conclusion
  permissions; they do not create new facts.
- Trace events should include protocol id/source/version and the rule that
  caused a block, recovery, candidate commit, or publication decision.
