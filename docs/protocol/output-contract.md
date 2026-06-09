# Output Contract

Writer and FinalJudge are constrained protocol actors, not free-form answer
generators.

## Output Policy

```json
{
  "output_policy": {
    "allowed_output_modes": ["normal", "degraded", "defect_memo", "readiness_memo"],
    "prohibited_claims": ["unsupported recommendation"],
    "required_caveats": ["Evidence is incomplete."],
    "required_evidence_display": ["citations", "evidence_gaps"],
    "publication_permissions": ["decision:publication"],
    "writer_can_create_facts": false,
    "degraded_output_modes": ["defect_memo"],
    "final_judge_checks": ["candidate_commitment", "stop_signals", "raw_data_policy"]
  }
}
```

Normal output requires:

- committed quorum candidate where the protocol requires one
- no unresolved hard stop signal blocking the output action
- evidence contract satisfied or an allowed degraded mode
- Data Gate conclusion permission for conclusion-bearing claims
- raw-data safety policy satisfied

If output is blocked, the runtime should return a protocol-compliant defect
memo, readiness memo, or degraded output.
