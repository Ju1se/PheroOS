## Review Standard

Before merging, review this change against:

- [PheroOS Swarm Governance Acceptance Audit](../docs/pheroos-acceptance-audit.md)

Use the repository review vocabulary:

- Verdict: `PASS`, `PARTIAL`, `FAIL`, `RISK`, `N/A`
- Severity: `P0`, `P1`, `P2`

Treat the following as P0 blockers:

- Secret leakage to agents, logs, frontend, traces, or final output
- Tool Registry bypass
- Model Gateway bypass
- Data Gate bypass
- WRDS raw data leakage into final output
- Writer bypass of committed quorum candidate
- `web_search` in WRDS-only investment mode
- High-risk permission execution without confirmation

## Checklist

- [ ] Data Gate / Stop-Signal / Quorum behavior remains enforced
- [ ] Writer cannot invent facts or bypass committed candidate
- [ ] Agents do not receive secrets
- [ ] Tool calls go through Tool Registry
- [ ] Model calls go through the model gateway / `runtime/llm.py`
- [ ] Swarm signals are typed, verified, and traceable
- [ ] Dashboard/API responses are redacted and backward compatible
- [ ] Tests cover safety-critical negative cases
