Goal: Evolve PheroOS into a swarm-native multi-agent operating protocol.

Repository: Ju1se/PheroOS

Project identity:
PheroOS is protocol-core, not an app runtime, agent framework, provider gateway, dashboard, workflow engine, or protection-layer stack.

Core authority model:
- Agents are not authority.
- Protocol is authority.
- OSKernel decides what is available.
- Governance decides what is allowed.
- Drivers provide capability.
- Trace explains what happened.
- Conformance proves compatibility.

Current repository boundary:
Only implement code that directly supports one of these surfaces:

- pheroos.protocol
- pheroos.kernel
- pheroos.governance
- pheroos.drivers
- pheroos.trace, if needed
- pheroos.conformance
- pheroos.cli as a thin wrapper
- provider-free examples
- deterministic tests
- ABI-focused docs

Do not restore the removed app runtime.
Do not add FastAPI product APIs, dashboards, LangGraph graphs, provider routing, LiteLLM/OpenAI/Ollama/vLLM wrappers, endpoint catalogs, local server wrappers, visual UI tests, WRDS/finance/domain workflows, product-specific skills, background daemons, worker pools, plugin marketplaces, or broad agent frameworks.

Swarm-native design goal:
Encode bee-swarm and ant-colony collective decision mechanisms as small protocol/governance/trace/conformance primitives.

Bee-inspired mapping:
- scout bee -> independent agent report
- nest site -> declared protocol candidate
- waggle dance -> recruitment signal
- stop/dissent behavior -> inhibition signal
- quorum threshold -> consensus/commit threshold
- swarm takeoff -> output authorization/publication

Ant-inspired mapping:
- path -> candidate, route, or tool/reasoning trajectory
- pheromone -> accumulated support signal
- evaporation -> confidence decay
- negative pheromone -> inhibition or blocked-route signal
- exploration/exploitation balance -> non-greedy candidate search
- convergence -> committed candidate or safe fallback

Use biology as protocol inspiration, not as implementation baggage.
Do not create a large swarm framework.
Do not use swarm language as marketing.
Encode swarm behavior as deterministic, testable protocol behavior.

Primary implementation objective:
Build the smallest vertical slice that proves PheroOS can express and test a swarm-native collective decision.

Target path:
1. Load a capability manifest.
2. Validate protocol invariants.
3. Read a collective decision policy from the manifest.
4. Create declared candidates and a safe fallback candidate.
5. Produce scout reports with evidence provenance.
6. Apply recruitment signals.
7. Apply inhibition signals.
8. Apply pheromone deposit and evaporation if enabled.
9. Evaluate collective consensus.
10. Commit only a declared candidate, or fall back to the declared safe fallback.
11. Authorize output only if the output contract is satisfied.
12. Emit trace events for swarm decision steps.
13. Pass conformance checks.

Preferred minimal Protocol ABI addition:
Add CollectiveDecisionPolicy.

Suggested fields:
- mode: quorum | bee_swarm | ant_colony | hybrid
- min_independent_scouts: positive integer
- quorum_threshold: positive integer
- recruitment_enabled: boolean
- inhibition_enabled: boolean
- pheromone_enabled: boolean
- pheromone_evaporation_rate: float between 0 and 1
- fallback_candidate: string

Integrate it into ProtocolManifest as an optional policy with safe defaults.
Keep the existing toy protocol compatible.

Validation should check:
- unsupported modes are rejected
- thresholds are positive
- evaporation rate is between 0 and 1
- fallback candidate is declared
- fallback candidate is marked safe_fallback
- if swarm trace events are required, they are present in trace policy

Preferred Governance Core additions:
Add a small collective decision module under pheroos.governance, for example pheroos/governance/collective.py.

Suggested dataclasses:
- ScoutReport
- RecruitmentSignal
- InhibitionSignal
- PheromoneTrail
- PheromonePolicy
- CollectiveDecisionState

Suggested pure functions:
- evaporate_trails(...)
- score_candidates(...)
- evaluate_collective_decision(...)

Behavioral requirements:
- A candidate can win only if it is declared.
- Consensus must require enough independent scout support according to policy.
- Recruitment can increase support only when recruitment is enabled.
- Inhibition can decrease support when inhibition is enabled.
- Pheromone must decay when evaporation is applied.
- If no candidate reaches consensus, the decision must return the safe fallback candidate.
- Governance code must not make domain-specific conclusions.

Preferred Trace ABI additions:
If pheroos.trace is missing or too small, add a minimal provider-free trace surface.

Suggested events for swarm protocols:
- explore
- scout_report
- recruit
- inhibit
- pheromone_deposit
- pheromone_evaporate
- candidate_score
- consensus_check
- commit
- fallback
- output

Use a small in-memory append-only trace store for tests if needed.
Do not add a database, daemon, event bus, queue, or logging framework.

Preferred Conformance additions:
Extend conformance with swarm-specific checks only where useful.

Suggested checks:
- collective_policy
- swarm_trace_contract
- safe_fallback_collective
- pheromone_policy

Conformance should remain deterministic, provider-free, and ABI-focused.

Preferred example:
Add examples/swarm-protocol/capability.json.

It must be:
- provider-free
- network-free
- deterministic
- domain-neutral
- small
- conformance-testable

It should demonstrate:
- declared target
- at least two normal candidates
- one safe fallback candidate
- collective decision policy
- quorum policy compatibility
- evidence provenance requirement
- output authorization requirement
- swarm trace requirements

Do not overbuild:
Avoid adding:
- SwarmRuntime
- AgentFramework
- SafetyManager
- ProtectionLayer
- GuardrailStack
- PolicyOrchestrator
- SecurityOrchestrator
- ProviderRouter
- RuntimeFramework
- app servers
- worker pools
- daemon processes
- plugin marketplaces

A new abstraction is acceptable only when it satisfies at least one condition:
1. It is part of Protocol ABI.
2. It is part of Kernel ABI.
3. It is part of Governance Core.
4. It is part of Driver ABI.
5. It is part of Trace ABI.
6. It is required by Conformance.
7. It is directly used by the swarm example or tests.

Import boundaries:
- pheroos.protocol must not import pheroos.kernel, pheroos.governance, pheroos.drivers, pheroos.conformance, CLI, examples, app/runtime modules, provider frameworks, or tools.
- pheroos.kernel may import pheroos.protocol and pheroos.drivers.
- pheroos.kernel should not directly depend on app/runtime/provider code.
- pheroos.governance may import protocol concepts where practical, but must remain independent from app/runtime/provider frameworks.
- pheroos.drivers must remain generic and provider-neutral.
- pheroos.trace must remain generic and provider-neutral.
- pheroos.conformance may compose protocol, kernel, governance, drivers, and trace.
- CLI must stay thin and delegate to core packages.

Testing requirements:
Add or update tests for:
- toy protocol still validates
- toy protocol still passes conformance
- swarm protocol validates
- swarm protocol passes conformance
- consensus succeeds with enough independent scout reports
- consensus falls back when scout threshold is not met
- recruitment increases candidate support when enabled
- inhibition decreases candidate support when enabled
- pheromone evaporation reduces trail strength
- undeclared candidates cannot be committed
- output authorization fails when evidence provenance is missing
- required swarm trace events are checked

Validation commands:
Run before finishing:

python -m pytest -q
python -m pheroos.cli.main validate examples/toy-protocol/capability.json
python -m pheroos.cli.main conformance examples/toy-protocol

If examples/swarm-protocol is added, also run:

python -m pheroos.cli.main validate examples/swarm-protocol/capability.json
python -m pheroos.cli.main conformance examples/swarm-protocol

Acceptance criteria:
- All tests pass.
- Existing toy protocol remains compatible.
- New swarm protocol is provider-free and deterministic.
- No old app runtime is restored.
- No heavy dependencies are added.
- No broad protection framework is added.
- New swarm concepts are encoded as ABI/governance/trace/conformance behavior.
- Every new abstraction is used by tests, examples, or conformance.
- Public core remains domain-neutral.