# Recovery Contract

Recovery is protocol-declared. The recovery engine selects recovery by trigger
targets, roles, tools, trust, maturity, and success/failure conditions.

```json
{
  "recovery_protocols": [
    {
      "recovery_id": "evidence_gap_recovery",
      "trigger_targets": ["gate:evidence_ready"],
      "allowed_agent_roles": ["evidence_scout", "source_auditor"],
      "allowed_capability_tags": ["research"],
      "required_tools": ["provider_web_search"],
      "success_condition": "verified source evidence satisfies gate:evidence_ready",
      "failure_condition": "no independent source after 2 rounds",
      "recovery_failure_candidate": "candidate:review:insufficient_evidence",
      "trace_requirements": ["selected_role", "trigger_target", "tool_result"]
    }
  ]
}
```

Recovery must not require hard-coded agent names. If the protocol cannot
satisfy recovery, the runtime should produce a degraded or insufficient-data
outcome rather than inventing a result.
