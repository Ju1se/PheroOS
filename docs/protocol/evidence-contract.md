# Evidence Contract

Evidence is not the same as prose in an agent response. Agent claims are
proposals until governance connects them to provenance and verifies whether
they may influence quorum or output.

## Evidence Policy Fields

Common fields:

- evidence types and accepted source families
- minimum support requirements
- source independence requirements
- citation and provenance requirements
- contradiction handling
- evidence gap handling
- source quality policy
- raw-data safety policy

Example:

```json
{
  "evidence_policy": {
    "raw_data_allowed_in_final": false,
    "min_independent_sources": 2,
    "source_quality_threshold": "reviewed",
    "contradiction_policy": "surface_and_degrade",
    "evidence_gap_policy": "commit_fallback_candidate"
  }
}
```

Writer-visible evidence should come from the Evidence Graph contract, not from
unverified agent prose or raw provider rows.
