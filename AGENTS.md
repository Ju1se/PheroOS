# AGENTS.md

## Project identity

This repository is a protocol-governed local multi-agent runtime.

The system is not a simple prompt-chain, agent chat, or app-specific workflow.
It is an AI-as-OS / PheroOS style runtime where capabilities, tools, agents,
data, evidence, candidate decisions, recovery behavior, and final outputs are
governed by explicit protocol contracts.

Core principle:

```text
Agents are not authority.
Protocol is authority.
```

Agents may propose observations, tool calls, evidence, risks, candidates,
recovery actions, and output drafts. They may not directly create verified
facts, hard blockers, committed candidates, publication permission, or final
authority. Those must be produced or validated by the protocol/governance
layer.

## Architectural north star

The project should evolve toward an open-source multi-agent protocol runtime.

The core runtime must stay domain-neutral. Domain-specific systems such as
WRDS, value investing, financial research, web research, code development, and
compliance should be implemented as capabilities, examples, adapters, or
compatibility shims, not as hard-coded assumptions in the core runtime.

Preferred public framing:

```text
Capability declares what is possible.
OSKernel decides what is available.
RuntimeMaterializer builds what is executable.
PheroOS governs what is allowed.
Quorum commits what is justified.
Writer expresses what is permitted.
FinalJudge verifies what can be published.
TraceStore explains why.
```

## Important runtime boundaries

Respect these boundaries when editing code:

- `runtime/graph.py` is a stable execution shell and compatibility bridge. Do
  not add new domain-specific branches here unless there is no
  protocol/capability alternative.
- `runtime/os_kernel.py` handles capability planning, permissions, connection
  requirements, and runtime readiness. It must not perform domain reasoning.
- `runtime/runtime_context.py` materializes tenant-scoped runtime context from
  OS plans, capabilities, connections, permissions, tools, and agents.
- `runtime/tool_registry.py` is the tool execution boundary. Agents must not
  instantiate or bypass tools directly.
- `runtime/swarm/*` implements protocol-governed signal, target, quorum,
  recovery, evidence, stop-signal, trace, and governance behavior.
- `capabilities/*` contains domain capabilities and protocol declarations.
- `tools/*` contains provider/tool adapters. Provider-specific implementations
  belong here or under a capability adapter boundary.
- `docs/protocol/*` should describe public protocol contracts and examples.

## Protocol-first development rules

When implementing new behavior, prefer protocol declarations over core code
changes.

Do not:

- add domain-specific routing branches to `runtime/graph.py`;
- hard-code candidate labels in `runtime/swarm/quorum.py`;
- hard-code agent names in `runtime/swarm/recovery_engine.py`;
- hard-code domain phrases in writer or final judge guardrails;
- let agents directly call external tools outside ToolRegistry;
- make WRDS, value investing, Buy/Sell/Watch/Avoid, formal valuation, or
  investment committee concepts first-class core runtime assumptions.

Do:

- express domain behavior through `capability.json` protocol fields;
- load and validate protocol declarations through protocol schema/loader code;
- route tools through ToolRegistry or a protocol-aware tool bus;
- make candidates protocol-declared;
- make recovery protocol-declared;
- make output permissions protocol-declared or gate-derived;
- preserve traceability for every governance decision;
- keep domain-specific behavior in capabilities, adapters, examples, tests, or
  explicit compatibility shims.

## Capability manifest expectations

A capability should declare as much behavior as practical in its manifest or
protocol block.

Capabilities may include:

```text
id
name
version
capability_types
permissions
required_connections
tools
skills
entrypoints
agents_path
protocol / pheroos_protocol
```

Common runtime entrypoints may include:

```json
{
  "entrypoints": {
    "workflow": "workflow.py:build_workflow_descriptor",
    "data_contract": "data_contract.py:build_data_contract_descriptor",
    "evidence_adapter": "evidence_adapter.py:build_evidence_adapter_descriptor",
    "runtime_nodes": "runtime_nodes.py:build_runtime_descriptor"
  }
}
```

Protocol declarations should be able to govern:

```text
intents
required_capability_types
targets
target_aliases
candidates
quorum_policy
stop_signal_policy
recovery_protocols
agent_selection_policy
evidence_policy
tool_policy
output_policy
swarm_loop_policy
required_governance_actors
```

## WRDS and financial-domain rules

WRDS is a provider adapter and reference capability, not a core runtime concept.

Acceptable WRDS-specific locations:

- `tools/wrds_tools.py`
- `capabilities/wrds-financial-data/`
- `capabilities/examples/financial-data-wrds/`
- WRDS-specific tests
- WRDS-specific docs/examples
- explicit legacy compatibility shims

Avoid WRDS-specific logic in:

- generic runtime nodes;
- protocol core;
- quorum core;
- recovery core;
- writer/final judge core;
- OS kernel domain inference except through capability/protocol metadata.

When replacing WRDS-specific names, prefer generic abstractions such as:

```text
DataProviderDescriptor
DataSourceResult
provider_id
source_kind
dataset_kind
normalized_payload
provenance
coverage
freshness
license
adapter_metadata
```

If backward compatibility requires `wrds_result`, keep it as a legacy alias
derived from generic provider results and document it as compatibility behavior.

## Quorum rules

Quorum must operate on protocol-declared candidates only.

Do not hard-code finance candidates such as:

```text
Buy
Sell
Watch
Avoid
Insufficient Data
```

These labels are valid only when declared by an active capability protocol.

Every quorum trace should include:

```text
protocol_id
protocol_version
candidate set
supporting evidence
challenging evidence
source independence
stop-signal interactions
commit decision
fallback/degraded decision, if any
```

## Recovery rules

Recovery must be selected by protocol declarations, not hard-coded agent names.

Recovery protocols may use:

```text
trigger_targets
allowed_agent_roles
allowed_capability_tags
trust_requirements
maturity_requirements
required_tools
success_condition
failure_condition
recovery_failure_candidate
trace_requirements
```

If recovery cannot satisfy the protocol, produce a degraded or insufficient-data
outcome rather than inventing a result.

## Evidence and signal rules

Agent signals are proposals unless verified by the governance layer.

A normal agent may not directly create:

- verified facts;
- hard blockers;
- committed candidates;
- publication permission;
- final decision authority.

Evidence-related changes must preserve:

```text
provenance
source quality
source independence
supporting evidence
challenging evidence
contradictions
evidence gaps
raw-data safety constraints
writer-visible evidence contract
```

## Output rules

Writer and FinalJudge are not free-form answer generators. They must enforce:

```text
OutputPolicy
EvidencePolicy
StopSignalPolicy
DataGate conclusion permissions
EvidenceGraph writer contract
raw-data safety policy
required caveats
committed candidate
publication permission
```

If output is blocked, generate a protocol-compliant defect memo, readiness
memo, or degraded output mode. Do not bypass governance to produce a normal
final answer.

## Trace and debugger rules

All governance decisions should be explainable.

When adding or changing governance behavior, preserve or add trace fields that
can answer:

```text
why was this target blocked?
why was this candidate committed?
why was this agent activated?
which protocol rule caused this?
which evidence supported the outcome?
which evidence challenged the outcome?
which tool/provider produced this data?
why was the output allowed or degraded?
```

## Tool and model boundaries

- All model calls must go through `runtime/llm.py` or the configured
  ModelGateway boundary.
- Runtime agents must not call Ollama, LM Studio, OpenAI, Anthropic, vLLM, or
  other model providers directly.
- Tool execution must be explicit, structured, and logged.
- Tool dispatch must go through `runtime/tool_registry.py`.
- Safe tools live in `tools/safe_tools.py`.
- Tools must return structured success/failure data.
- Tools must not execute arbitrary shell commands.
- Workspace file tools must reject paths outside the project root.
- Web tools must reject localhost, private network, file, and metadata URLs.
- Web research answers should include source URLs when web results influence
  the answer.

## Skills and local commands

- Skills must live under `skills/<skill-name>/SKILL.md`.
- Create env: `python3 -m venv .venv`
- Install deps: `.venv/bin/pip install -e ".[dev]"`
- Run tests: `.venv/bin/pytest`
- Run API: `scripts/start_api.sh`
- Run LiteLLM: `scripts/start_litellm.sh`

## Tests and validation

Before finishing a change, run the most relevant tests available in the repo.
If the repo has no specific test for the behavior changed, add one when
practical.

Prefer tests for:

- protocol manifest validation;
- invalid protocol error messages;
- candidate registry enforcement;
- quorum with protocol-declared candidates;
- recovery without hard-coded agent names;
- writer/final judge output enforcement;
- ToolRegistry permission and protocol filtering;
- WRDS isolation as optional provider capability;
- toy protocol running without WRDS or finance assumptions;
- grep-style guards against domain leakage in core runtime.

Do not fake behavior just to satisfy tests. Tests should validate real
protocol-governed behavior.

## Documentation expectations

For public-facing or protocol-level changes, update docs.

Preferred docs locations:

```text
docs/protocol/
docs/examples/
docs/architecture/
```

Documentation should explain how a third party can add a new capability without
editing:

```text
runtime/graph.py
runtime/swarm/quorum.py
runtime/swarm/recovery_engine.py
runtime/writer_guardrails.py
runtime/final_judge_guardrails.py
```

## Migration and compatibility

Prefer additive compatibility over breaking changes.

When moving domain-specific behavior out of core:

- keep old response fields if needed;
- add generic fields next to legacy fields;
- mark legacy fields clearly;
- add migration notes;
- keep existing behavior working through capability adapters or compatibility
  shims when practical.

## Review / acceptance audit rules

When the user asks for a review, code review, audit, acceptance check, 验收, or
审计 of this repository, default to the read-only PheroOS acceptance audit in
`docs/pheroos-acceptance-audit.md`.

- Review means inspect and report first; do not modify files during a review
  unless the user explicitly asks to implement fixes afterward.
- Findings must lead the response and cite concrete file/function/line evidence
  where possible.
- Treat these as P0 issues: secret leakage, ToolRegistry bypass, ModelGateway
  bypass, DataGate bypass, WRDS raw data leakage into final output, Writer
  bypass of committed quorum candidate, `web_search` in WRDS-only investment
  mode, and high-risk permission execution without confirmation.
- Use the verdict vocabulary from `docs/pheroos-acceptance-audit.md`: PASS,
  PARTIAL, FAIL, RISK, N/A, plus P0/P1/P2 severity.

## Long-running refactors

For complex features, architectural refactors, protocol migrations, or changes
touching more than three subsystems, create or update an ExecPlan in
`.agent/PLANS.md` before implementation.

The ExecPlan must include:

- user-visible goal;
- current architecture facts;
- files to inspect;
- milestones;
- tests to run;
- migration and compatibility notes;
- progress log;
- final validation checklist.

Keep the ExecPlan updated as work proceeds.

## Work style

Use small, reviewable changes.

When pursuing a major refactor:

1. inspect current behavior first;
2. identify existing tests and baseline failures;
3. make one architectural move at a time;
4. update tests and docs with the code;
5. summarize remaining compatibility risks.

Do not ask the user for next steps during an active implementation plan.
Continue through the next logical milestone and report what changed, what was
tested, and what remains.
