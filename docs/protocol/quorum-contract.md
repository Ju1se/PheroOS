# Quorum Contract

Quorum commits protocol-declared candidates. It must not invent candidate
labels or assume a domain-specific decision set.

## Candidate Declaration

```json
{
  "candidates": [
    {
      "candidate": "candidate:review:accept",
      "label": "Accept",
      "target": "decision:review_outcome",
      "required_evidence_targets": ["gate:evidence_ready"]
    },
    {
      "candidate": "candidate:review:insufficient_evidence",
      "label": "Insufficient evidence",
      "safe_fallback": true
    }
  ],
  "quorum_policy": {
    "candidates": [
      "candidate:review:accept",
      "candidate:review:insufficient_evidence"
    ],
    "quorum_threshold": 0.6,
    "min_independent_sources": 1,
    "candidate_fallback": "candidate:review:insufficient_evidence"
  }
}
```

## Trace Requirements

Every quorum trace should include:

- protocol source/id/version
- declared candidate set
- supporting and challenging evidence
- source independence checks
- stop-signal interactions
- committed candidate or fallback/degraded candidate
