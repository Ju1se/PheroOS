# Trace Contract

Trace explains governance. It should answer why a target was blocked, why a
candidate was committed, why an agent was activated, which rule caused a
decision, and why output was allowed or degraded.

## Event Families

- run events
- permission events
- tool events
- signal events
- evidence graph events
- stop-signal events
- quorum events
- recovery events
- output and final-judge events

## Required Lineage

Governance events should include:

- `protocol_id` or capability id
- `protocol_version` or schema version
- `protocol_source`
- canonical target
- rule id or policy field
- supporting/challenging evidence references
- provider/tool provenance when data influenced the decision

Legacy traces may expose compatibility fields. New traces should also expose
generic fields such as `agent_decision`, `agent_outputs`,
`data_source_results`, `provider_id`, and canonical targets.
