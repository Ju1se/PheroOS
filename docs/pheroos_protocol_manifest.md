# PheroOS Protocol Manifest

Capability protocol manifests declare the governance contract for a capability.
The protocol is the authority; agents may only propose, observe, execute, or
challenge inside that contract.

## Supported Locations

The loader checks these sources in order:

1. `capability.json` field named `protocol`, `pheroos_protocol`, or `pheroos`.
2. Adjacent file `capabilities/<capability-id>/pheroos_protocol.json`.
3. Legacy `capability.json` field `swarm`.

Legacy `swarm` data still loads, but the runtime marks it as
`generated_legacy_protocol` in protocol traces.

## Minimal Example

```json
{
  "id": "toy-review",
  "name": "Toy Review",
  "version": "0.1.0",
  "capability_types": ["toy.review"],
  "permissions": ["skill:read", "data:read"],
  "risk_level": "low",
  "trust_level": "first_party_reviewed",
  "protocol": {
    "version": "1.0.0",
    "intents": ["toy_review"],
    "intent_keywords": {
      "toy_review": ["toy artifact", "toy evidence"]
    },
    "required_capability_types": ["toy.evidence_store"],
    "required_capability_types_by_intent": {
      "toy_review": ["toy.evidence_store"]
    },
    "targets": [
      {
        "target": "gate:toy_evidence_gate",
        "target_type": "gate",
        "description": "Require evidence before publishing the toy review.",
        "required": true,
        "default_pressure": 0.9,
        "aliases": ["toy evidence gate"],
        "compatible_intents": ["toy_review"],
        "allowed_signal_types": ["evidence", "risk", "stop_signal"]
      }
    ],
    "candidates": [
      {
        "candidate": "candidate:toy:approve",
        "description": "Approve the toy artifact.",
        "target": "decision:toy_publish",
        "blocked_by_targets": ["gate:toy_evidence_gate"],
        "required_evidence_targets": ["gate:toy_evidence_gate"],
        "default_priority": 0.6,
        "safe_fallback": false
      },
      {
        "candidate": "candidate:toy:insufficient_evidence",
        "description": "Decline to publish until evidence is complete.",
        "target": "decision:toy_publish",
        "safe_fallback": true
      }
    ],
    "quorum_policy": {
      "candidates": ["candidate:toy:approve", "candidate:toy:insufficient_evidence"],
      "quorum_threshold": 0.6,
      "min_independent_sources": 1,
      "evidence_coverage_weight": 0.4,
      "source_quality_weight": 0.2,
      "candidate_fallback": "candidate:toy:insufficient_evidence",
      "force_fallback_when_blocked": true
    },
    "stop_signal_policy": {
      "blocked_targets": ["gate:toy_evidence_gate"],
      "blocking_authority_required": 3,
      "blocking_lifetime": "until_resolved",
      "action_markers": [
        {
          "action": "writer:publish_toy_review",
          "phrases": ["publish toy review", "ship toy report"]
        }
      ],
      "rules": [
        {
          "id": "evidence_gate_blocks_publish",
          "trigger_targets": ["gate:toy_evidence_gate"],
          "blocked_actions": ["writer:publish_toy_review", "final_judge:approve_publish"]
        }
      ]
    },
    "recovery_protocols": [
      {
        "recovery_id": "toy_evidence_recovery",
        "trigger_targets": ["gate:toy_evidence_gate"],
        "trigger_signal_types": ["risk", "stop_signal"],
        "max_rounds": 2,
        "allowed_agent_roles": ["evidence_scout"],
        "required_tools": ["approved_source_fetch"],
        "recovery_success_condition": "toy evidence gate has at least one verified source",
        "recovery_failure_candidate": "candidate:toy:insufficient_evidence"
      }
    ],
    "evidence_policy": {
      "claim_types": ["toy_claim"],
      "evidence_node_types": ["source", "claim"],
      "required_evidence_for_final_claims": ["gate:toy_evidence_gate"],
      "citation_required": true,
      "raw_data_allowed_in_final": false,
      "raw_data_markers": ["toy-secret-row=", "raw_rows"],
      "unsupported_claim_action": "block"
    },
    "tool_policy": {
      "allowed_tool_targets": ["tool:approved_source_fetch"],
      "source_policy_blocked_tool_targets": ["tool:unapproved_public_web"],
      "source_policy_block_message": "{action} is blocked by declared {source_mode} policy.",
      "source_policy_constraint_message": "Declared {source_mode} policy is active.",
      "required_permissions": ["tool:deterministic-read"],
      "risk_level": "low",
      "quarantine_external_outputs": true
    },
    "output_policy": {
      "allowed_output_modes": ["defect_memo", "caveated_summary"],
      "blocked_phrases": ["unsupported toy claim"],
      "required_caveats": ["Evidence is incomplete until the toy evidence gate passes."],
      "committed_candidate_conflicts": [
        {
          "candidate": "candidate:toy:insufficient_evidence",
          "label": "Insufficient evidence",
          "blocked_phrases": ["Approve", "ready to publish"]
        }
      ],
      "final_claim_evidence_required": true,
      "defect_memo_on_block": true,
      "writer_can_create_facts": false,
      "final_judge_required_checks": ["candidate_consistency", "evidence_graph_consistency"]
    },
    "swarm_loop_policy": {
      "max_rounds": 3,
      "target_pressure_threshold": 0.5,
      "recovery_rounds": 1,
      "quorum_check_frequency": 1,
      "stop_signal_check_frequency": 1,
      "tool_health_check_frequency": 1,
      "arousal_signal_template": "Arousal {arousal_level} is {status}; apply verifier policy.",
      "social_immunity_arousal_signal_template": "Social immunity {status} at {arousal_level}; apply quarantine policy.",
      "social_immunity_recommendations": {
        "quarantine_required": "Quarantine contaminated artifacts.",
        "heightened": "Raise verifier strictness.",
        "clear": "Maintain normal verification."
      },
      "homeostasis_signal_template": "Homeostasis {status}; apply {recommendation_count} recommendation(s).",
      "homeostasis_recommendations": {
        "risk_pressure": "Increase verifier strictness.",
        "token_heat": "Compress agent outputs.",
        "default": "Maintain current swarm balance."
      },
      "lane_policy": {
        "lanes": ["inspection", "execution", "verification", "synthesis", "control"],
        "preferred_lanes": {
          "writer": "synthesis",
          "final_judge": "control"
        },
        "term_lane_preferences": [
          {"lane": "verification", "terms": ["verifier", "evidence", "audit"]}
        ],
        "fallback_order": ["synthesis", "inspection", "control", "verification"],
        "default_lane": "inspection",
        "assignment_signal_template": "Declared lane assignment: {agent} -> {lane}."
      },
      "maturity_policy": {
        "maturity_order": ["observer", "worker", "specialist", "verifier", "blocker"],
        "trust_defaults": {
          "core_system": "worker",
          "trusted_first_party": "worker"
        },
        "default_maturity": "observer",
        "promotion_rules": [
          {"maturity": "specialist", "min_total_runs": 3, "min_reliability": 0.68}
        ],
        "actions": {
          "observer": ["read_trace", "emit_unverified_signal"],
          "specialist": ["emit_unverified_signal", "participate_quorum"]
        },
        "signal_template": "Declared maturity for {agent}: {maturity}."
      },
      "independent_scout_policy": {
        "source_family_rules": [
          {"family": "risk", "terms": ["risk", "red_team"]},
          {"family": "data", "terms": ["data", "quant"]}
        ],
        "default_source_family": "agent",
        "min_independence_score": 0.5,
        "force_fallback_when_low_independence": true,
        "signal_template": "Declared independent scout diversity is {source_diversity}.",
        "low_independence_reason_template": "Declared source diversity below threshold.",
        "forced_fallback_reason_template": "Declared low independence forced {fallback_label}."
      },
      "controller_action_policy": {
        "runtime_budget_default_recommendation": "Maintain declared activation budget.",
        "runtime_budget_target": "swarm:runtime_budget",
        "low_return_reason": "Declared low verified return rate.",
        "verification_policy_reason": "Declared arousal and gate pressure policy.",
        "arousal_verification_target": "agent:verifier_and_final_judge",
        "arousal_verification_reason": "Declared arousal policy requested stricter checks.",
        "quorum_policy_signal_template": "Declared swarm controller updated quorum policy at independence {min_independence_score}.",
        "homeostasis_action_rules": [
          {"terms": ["recruit evidence"], "action": "prioritize_evidence_receivers", "target": "swarm:evidence_receivers"}
        ]
      },
      "encounter_rate_recommendations": {
        "healthy": "Maintain current lanes.",
        "degraded": "Prioritize verifier feedback.",
        "poor": "Route more work to verification."
      },
      "tool_health_recommendations": {
        "failing": "Block or reroute failing tool/model routes.",
        "degraded": "Lower confidence while tool/model routes recover."
      },
      "outcome_feedback_enabled": true
    },
    "required_governance_actors": ["evidence_steward_agent", "quorum_marshal_agent"]
  }
}
```

## Runtime Files

- `runtime/swarm/protocol_schema.py` defines typed protocol dataclasses.
- `runtime/swarm/protocol_manifest.py` defines `CapabilityPheroOSProtocol`.
- `runtime/swarm/protocol_loader.py` loads explicit, adjacent, or legacy
  protocol data.
- `runtime/swarm/protocol_validation.py` validates target references,
  candidate references, recovery references, blocking authority, and raw-data
  defaults.
- `runtime/swarm/protocol.py` preserves the existing normalized bundle shape for
  current goal routing.

`required_capability_types` is a protocol-level dependency list. The OS kernel
uses it, together with the declaring capability's own `capability_types`, to
resolve capability dependencies for protocol-backed intents before falling back
to legacy static requirement maps. Multi-intent protocols can override that
global list with `required_capability_types_by_intent`; an explicit empty list
means the selected intent only requires the declaring capability's own
`capability_types`.

`intent_keywords` declares OS-routing markers per intent. The OS kernel uses
these markers before legacy static hint maps. `targets[].compatible_intents`
limits a target declaration to specific intents. When omitted, the target
applies to every intent exposed by the capability protocol. GoalRouter filters
target pressure by the selected intent before falling back to legacy target
defaults, and OS intent matching only uses target keywords from targets
compatible with the intent being scored.

`output_policy.defect_memo_on_block` is enforced by the shared output contract.
When a capability `stop_signal_policy` rule blocks `writer:publish_report` or
`final_judge:publish_report`, Writer and Final Judge output must be a defect
memo instead of a normal report.

`stop_signal_policy.action_markers` maps capability-owned output phrases to
writer/final-judge actions. This lets the runtime detect that a draft is trying
to perform a blocked action without hardcoding domain-specific wording in the
Writer or Final Judge.

## Validation Rules

- Every target must have a canonical target.
- `intent_keywords` and `required_capability_types_by_intent` keys and
  `targets[].compatible_intents` values must reference declared protocol
  intents.
- Aliases must not conflict with another known canonical target.
- Candidate `target` values must reference declared non-candidate targets when
  they point at a gate/decision/constraint/evidence target.
- Candidate `blocked_by_targets` and `required_evidence_targets` must reference
  declared targets.
- Quorum `candidates` and `candidate_fallback` must reference declared
  candidates.
- Recovery `trigger_targets` must reference declared targets.
- Recovery `recovery_failure_candidate` must reference a declared candidate.
- Only trusted capabilities may declare hard-blocking authority. Declarations
  from untrusted capabilities are retained for audit diagnostics, but runtime
  stop-policy consumers ignore their rules, action markers, and resolution
  rules. Top-level `blocked_actions` are normalized into source-attributed
  default rules before policy merge so mixed trusted/untrusted policies remain
  filterable.
- Third-party capabilities default to unverified, non-blocking signal treatment.
- `evidence_policy.raw_data_allowed_in_final` defaults to `false`; declaring it
  `true` is retained for validation/privileged-review diagnostics and does not
  weaken final-output raw-data blocking.
- `evidence_policy.raw_data_markers` declares capability-specific raw/sensitive
  output markers; global secret and generic raw-row checks remain
  non-weakenable, and legacy raw-data markers are used only as compatibility
  fallback when a capability does not declare markers.
- `output_policy.writer_can_create_facts` must remain `false`; declaring it
  `true` is retained only as validation/audit metadata and does not weaken the
  writer evidence contract.

## Compatibility

Existing `swarm.targets`, `swarm.candidate_policy`, `swarm.quorum_policy`,
`swarm.stop_signal_policy`, and `swarm.recovery_protocols` still load. The
compatibility loader maps them into `CapabilityPheroOSProtocol` and marks the
result with:

```json
{
  "source": "generated_legacy_protocol",
  "generated_legacy_protocol": true
}
```

The top-level goal-router bundle continues to report
`protocol_source: "capability_manifest"` when a capability manifest supplies
protocol data, preserving current runtime behavior while exposing legacy usage
for later migration.
