# Minimal Toy Protocol

This example runs without external connections and without WRDS or finance
assumptions.

```json
{
  "id": "toy-review",
  "name": "Toy Review",
  "version": "0.1.0",
  "description": "A tiny governed review capability.",
  "capability_types": ["toy.review"],
  "permissions": ["data:read"],
  "risk_level": "low",
  "tools": ["read_file"],
  "protocol": {
    "version": "0.1.0",
    "intents": ["toy_review"],
    "intent_keywords": {"toy_review": ["toy", "review"]},
    "targets": [
      {
        "target": "gate:toy_evidence_gate",
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
    "tool_policy": {"allowed_tool_targets": ["tool:read_file"]},
    "output_policy": {"writer_can_create_facts": false}
  }
}
```

The active protocol declares the target, candidates, fallback, tool boundary,
and output authority. No core module needs toy-specific code.
