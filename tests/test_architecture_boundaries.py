from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def project_files() -> list[Path]:
    roots = [ROOT / "runtime", ROOT / "app", ROOT / "tools", ROOT / "capabilities"]
    output: list[Path] = []
    for root in roots:
        output.extend(
            path
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return sorted(output)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_no_direct_model_provider_sdk_imports_outside_gateway() -> None:
    forbidden = re.compile(r"^\s*(from|import)\s+(openai|anthropic|zhipuai|minimax)\b", re.MULTILINE)
    offenders = [
        relative(path)
        for path in project_files()
        if forbidden.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_litellm_client_instantiation_is_confined_to_runtime_assembly() -> None:
    allowed = {
        "app/routes/dependencies.py",
        "runtime/factory.py",
        "runtime/model_gateway.py",
        "runtime/runtime_context.py",
    }
    instantiation = re.compile(r"\bLiteLLMClient\s*\(")
    offenders = [
        relative(path)
        for path in project_files()
        if relative(path) not in allowed and instantiation.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_capability_manifests_require_model_gateway_sandbox() -> None:
    offenders: list[str] = []
    for manifest in sorted((ROOT / "capabilities").glob("*/capability.json")):
        text = manifest.read_text(encoding="utf-8")
        if '"model:chat"' not in text and '"model_calls"' not in text:
            continue
        if '"model_calls": "gateway_only"' not in text:
            offenders.append(relative(manifest))

    assert offenders == []


def test_network_clients_are_confined_to_gateway_connection_or_tool_layers() -> None:
    allowed = {
        "runtime/model_gateway.py",
        "runtime/llm.py",
        "runtime/connection_control.py",
        "runtime/secret_store.py",
        "tools/public_financial_tools.py",
        "tools/web_tools.py",
    }
    network_client = re.compile(r"\b(httpx|requests)\.")
    offenders = [
        relative(path)
        for path in project_files()
        if relative(path) not in allowed and network_client.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_graph_model_calls_use_model_gateway_boundary() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    match = re.search(
        r"async def _chat_with_fallback\(.*?\n(?P<body>.*?)\n    async def _execute_tool_calls",
        graph_text,
        re.DOTALL,
    )
    assert match is not None
    body = match.group("body")

    assert "self.model_gateway.chat(" in body
    assert "self.llm.chat(" not in graph_text


def test_graph_model_dependency_is_typed_as_runtime_port() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")

    assert "from runtime.ports import ChatModelClient" in graph_text
    assert "LLMClient" not in graph_text
    assert "model_gateway: ChatModelClient" in graph_text


def test_wrds_access_is_confined_to_wrds_adapter_and_tools() -> None:
    allowed = {
        "tools/wrds_tools.py",
        "runtime/financial_data_sources.py",
        "runtime/connection_control.py",
    }
    wrds_access = re.compile(r"\bwrds\.Connection\b|\bread_sql\b|\bpsycopg2\b")
    offenders = [
        relative(path)
        for path in project_files()
        if relative(path) not in allowed and wrds_access.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_tool_implementations_are_instantiated_only_at_registry_boundaries() -> None:
    allowed_by_class = {
        "WorkspaceTools": {"runtime/tool_registry.py"},
        "WebTools": {"runtime/tool_registry.py"},
        "WRDSTools": {"runtime/tool_registry.py", "runtime/connection_control.py"},
        "PublicFinancialDataTools": {"runtime/tool_registry.py", "runtime/runtime_context.py"},
    }
    offenders: list[str] = []
    for path in project_files():
        rel = relative(path)
        text = path.read_text(encoding="utf-8")
        for class_name, allowed in allowed_by_class.items():
            if rel not in allowed and re.search(rf"\b{class_name}\s*\(", text):
                offenders.append(f"{rel}:{class_name}")

    assert offenders == []


def test_shell_execution_is_confined_to_safe_workspace_tools() -> None:
    allowed = {"tools/safe_tools.py"}
    shell_access = re.compile(r"\bsubprocess\.|\bos\.system\b|\bshell=True\b")
    offenders = [
        relative(path)
        for path in project_files()
        if relative(path) not in allowed and shell_access.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_investment_committee_nodes_are_capability_owned() -> None:
    workflow_text = (ROOT / "capabilities/value-investing-research/workflow.py").read_text(encoding="utf-8")
    node_text = (ROOT / "capabilities/value-investing-research/runtime_nodes.py").read_text(encoding="utf-8")
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")

    assert '"value-investing-research"' not in graph_text
    assert "legacy_value_investing_capability_id(" in graph_text

    for node_name in (
        "data_gate_node",
        "research_agent_node",
        "quant_agent_node",
        "committee_opening_node",
        "committee_discussion_node",
        "investment_committee_node",
    ):
        assert f"runtime_nodes.py:{node_name}" in workflow_text
        assert f"async def {node_name}" in node_text

    opening_method = re.search(
        r"async def _committee_opening\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _committee_discussion",
        graph_text,
        re.DOTALL,
    )
    assert opening_method is not None
    opening_body = opening_method.group("body")
    assert 'load_value_investing_runtime_node("committee_opening_node")' in opening_body
    assert "Create your own sub-plan" not in opening_body
    assert "agent_emitted_signals_from_outputs" not in opening_body
    assert "_run_committee_member" not in graph_text

    discussion_method = re.search(
        r"async def _committee_discussion\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _investment_committee",
        graph_text,
        re.DOTALL,
    )
    assert discussion_method is not None
    discussion_body = discussion_method.group("body")
    assert 'load_value_investing_runtime_node("committee_discussion_node")' in discussion_body
    assert "Investment Committee Discussion Moderator" not in discussion_body
    assert "parse_discussion_round" not in discussion_body

    investment_method = re.search(
        r"async def _investment_committee\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _critic",
        graph_text,
        re.DOTALL,
    )
    assert investment_method is not None
    body = investment_method.group("body")
    assert "load_value_investing_runtime_node(\"investment_committee_node\")" in body
    assert "You are the CIO / Investment Committee Chair" not in body
    assert "build_quorum_trace" not in body
    assert "apply_enforcement_bus" not in body


def test_core_writer_and_policing_do_not_own_domain_workflow_fallback_bodies() -> None:
    allowed = "runtime/workflows/legacy_guardrails.py"
    forbidden_by_file = {
        "runtime/writer_guardrails.py": (
            "LEGACY_DOMAIN_WORKFLOW_WRITER_FALLBACK_SOURCE",
            "LEGACY_DOMAIN_WORKFLOW_WRITER_POLICIES",
            "def apply_code_development_writer_policy",
            "def apply_compliance_writer_policy",
            "def apply_evidence_research_writer_policy",
        ),
        "runtime/swarm/policing.py": (
            "LEGACY_DOMAIN_WORKFLOW_POLICING_FALLBACK_SOURCE",
            "LEGACY_DOMAIN_WORKFLOW_VIOLATION_HANDLERS",
            "def code_workflow_violations",
            "def compliance_workflow_violations",
            "def evidence_workflow_violations",
        ),
    }

    for path, forbidden in forbidden_by_file.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{needle} belongs in {allowed}, not {path}"

    compatibility_text = (ROOT / allowed).read_text(encoding="utf-8")
    writer_text = (ROOT / "runtime/writer_guardrails.py").read_text(encoding="utf-8")
    assert "LEGACY_DOMAIN_WORKFLOW_WRITER_POLICIES" in compatibility_text
    assert "LEGACY_DOMAIN_WORKFLOW_VIOLATION_HANDLERS" in compatibility_text
    assert "LEGACY_DOMAIN_WORKFLOW_WRITER_FALLBACK_SOURCE" in compatibility_text
    assert "LEGACY_DOMAIN_WORKFLOW_POLICING_FALLBACK_SOURCE" in compatibility_text
    assert "legacy_domain_workflow_writer_fallback_source(" in writer_text
    assert "def legacy_domain_workflow_writer_fallback_source(" in compatibility_text
    assert "def legacy_domain_workflow_policing_fallback_source(" in compatibility_text


def test_public_boundary_doc_defines_kernel_user_driver_authority() -> None:
    text = (ROOT / "docs/architecture/kernel-user-driver-boundaries.md").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    required = [
        "# Kernel, User, and Driver Boundaries",
        "Kernel-mode actors verify, block, commit, publish, and explain.",
        "User-mode actors propose. They do not hold authority.",
        "Driver-mode adapters expose structured provider capabilities to the kernel.",
        "Governance actors are kernel services, not normal agents and not committee",
        "`runtime/graph.py` remains a reference runtime shell and compatibility bridge.",
        "run pheroos validate",
        "run pheroos-conformance",
    ]
    for item in required:
        assert item in text

    assert "WRDS is a reference `DataProviderDriver`" in text
    assert "WRDS is not a kernel concept" in normalized


def test_domain_execution_bridge_does_not_own_legacy_graph_mode_maps() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    bridge_text = (ROOT / "runtime/workflows/domain_execution.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_dispatch.py").read_text(encoding="utf-8")

    assert "LEGACY_ORCHESTRATION_FALLBACKS =" not in bridge_text
    assert "LEGACY_EXECUTION_FALLBACKS =" not in bridge_text
    assert "LEGACY_ORCHESTRATION_FALLBACKS =" in compatibility_text
    assert "LEGACY_EXECUTION_FALLBACKS =" in compatibility_text
    assert 'graph_mode != "investment_committee"' not in bridge_text
    assert 'graph_mode == "investment_committee"' not in graph_text
    assert "legacy_builtin_graph_mode(" in bridge_text
    assert "legacy_builtin_graph_mode(" in graph_text
    assert "LEGACY_BUILTIN_GRAPH_MODES =" in compatibility_text


def test_graph_does_not_own_legacy_research_node_fallbacks() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_node_dispatch.py").read_text(encoding="utf-8")

    assert "LEGACY_RESEARCH_NODE_FALLBACKS =" not in graph_text
    assert "LEGACY_RESEARCH_NODE_FALLBACKS =" in compatibility_text
    assert "legacy_graph_mode_node_fallback" not in graph_text
    assert "legacy_graph_mode_node_fallback" in compatibility_text


def test_graph_does_not_own_legacy_routing_heuristic_tables() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_graph_routing.py").read_text(encoding="utf-8")

    for name in (
        "LEGACY_TASK_TYPE_ALIASES",
        "LEGACY_CODE_TASK_HINTS",
        "LEGACY_PORTFOLIO_TASK_HINTS",
        "LEGACY_INVESTMENT_TASK_HINTS",
        "LEGACY_DIRECT_ANSWER_COMPLEX_MARKERS",
        "LEGACY_QUANT_HINTS",
        "LEGACY_DOMAIN_HINTS",
    ):
        assert f"{name} =" not in graph_text
        assert f"{name} =" in compatibility_text

    for helper in (
        "legacy_normalize_task_type(value)",
        "legacy_infer_task_type(",
        "legacy_needs_quant_analysis(task)",
        "legacy_needs_domain_analysis(task)",
    ):
        assert helper in graph_text


def test_workflow_routing_delegates_legacy_node_aliases() -> None:
    routing_text = (ROOT / "runtime/workflows/routing.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_routing_aliases.py").read_text(encoding="utf-8")

    for phrase in (
        "GRAPH_NODE_ALIASES =",
        '"committee": "committee_opening"',
        '"deterministic_research": "research_agent"',
        '"executor_wrds": "executor"',
    ):
        assert phrase not in routing_text
        assert phrase in compatibility_text

    assert "legacy_graph_node_alias(" in routing_text
    assert "legacy_default_workflow_node_order(" in routing_text
    assert "legacy_default_workflow_routing_source(" in routing_text
    assert "DEFAULT_NODE_ORDER" not in routing_text
    assert "default_graph" not in routing_text
    assert "LEGACY_DEFAULT_WORKFLOW_NODE_ORDER =" in compatibility_text
    assert "LEGACY_DEFAULT_WORKFLOW_ROUTING_SOURCE" in compatibility_text
    assert "def legacy_graph_node_alias(" in compatibility_text
    assert "def legacy_default_workflow_node_order(" in compatibility_text
    assert "def legacy_default_workflow_routing_source(" in compatibility_text


def test_graph_does_not_own_legacy_orchestration_default_builder() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_orchestration_defaults.py").read_text(encoding="utf-8")

    for phrase in (
        "LEGACY_GRAPH_ORCHESTRATION_AGENT_KEYS =",
        "auto_company_investment",
        "heuristic_investment_default",
        "legacy_parse_agent_flag",
        "legacy_parse_bool_value",
        'task_type == "investment" and not suppress_investment_defaults',
    ):
        assert phrase not in graph_text
        assert phrase in compatibility_text

    assert "legacy_normalize_orchestration_defaults(" in graph_text
    assert "protocol_plan_suppresses_graph_investment_defaults(" in graph_text
    assert "legacy_should_force_direct_answer(" in compatibility_text


def test_graph_does_not_own_legacy_result_default_reasons() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_result_defaults.py").read_text(encoding="utf-8")

    for phrase in (
        "investment committee not required",
        "research not required",
        "quant analysis not required",
        "domain judgment not required",
        "agent decision not required",
        "runtime preflight blocked research",
        "runtime preflight blocked quant analysis",
        "runtime preflight blocked domain analysis",
        "runtime preflight blocked agent decision",
        "runtime preflight blocked committee",
        "Runtime preflight blocked graph execution before model, tool, WRDS, or committee work.",
        "investment_framework",
        "history_summary",
    ):
        assert phrase not in graph_text
        assert phrase in compatibility_text

    assert "legacy_skipped_analysis_reason(" in graph_text
    assert "legacy_runtime_preflight_blocked_summary(" in graph_text
    assert "legacy_memory_context_metadata_keys(" in graph_text
    assert "LEGACY_SKIPPED_ANALYSIS_REASONS =" in compatibility_text
    assert "LEGACY_RUNTIME_PREFLIGHT_BLOCKED_SUMMARY =" in compatibility_text
    assert "LEGACY_MEMORY_CONTEXT_METADATA_KEYS =" in compatibility_text


def test_graph_orchestrator_prompt_does_not_own_domain_guidance() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    orchestration_guidance_text = (ROOT / "runtime/workflows/orchestration_guidance.py").read_text(encoding="utf-8")
    value_workflow_text = (ROOT / "capabilities/value-investing-research/workflow.py").read_text(encoding="utf-8")
    value_capability_text = (ROOT / "capabilities/value-investing-research/capability.json").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_orchestration_guidance.py").read_text(encoding="utf-8")

    for phrase in (
        "For investment tasks",
        "A dedicated WRDS Planner",
        "public company name, stock ticker",
        "Use GLM-style reasoning roles",
    ):
        assert phrase not in graph_text

    assert "orchestration_guidance" in graph_text
    assert "build_orchestrator_system_prompt(" in graph_text
    assert "For investment tasks" in value_workflow_text
    assert "For investment tasks" in compatibility_text
    assert "Use GLM-style reasoning roles" in compatibility_text
    assert "Source mode is {source_mode}: do not include blocked public-web" not in orchestration_guidance_text
    assert "legacy_source_mode_tool_guidance(" in orchestration_guidance_text
    assert "source_mode_guidance" in value_capability_text
    assert "Source mode is {source_mode}: do not include blocked public-web" in compatibility_text


def test_graph_does_not_own_legacy_deterministic_plan_defaults() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_plan_defaults.py").read_text(encoding="utf-8")

    for phrase in (
        "Research public sources",
        "Inspect workspace",
        "No tool required",
        "LEGACY_CODE_PLAN_HINTS",
        "LEGACY_CODE_PLAN_SKILL_NAMES",
    ):
        assert phrase not in graph_text
        assert phrase in compatibility_text

    assert "legacy_deterministic_plan(" in graph_text
    assert "legacy_deterministic_plan_fallback" in graph_text


def test_graph_does_not_own_source_tool_helper_tables() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    web_planner_text = (ROOT / "runtime/web_research_planner.py").read_text(encoding="utf-8")
    legacy_plan_text = (ROOT / "runtime/workflows/legacy_plan_defaults.py").read_text(encoding="utf-8")
    evidence_research_text = (ROOT / "runtime/workflows/evidence_research.py").read_text(encoding="utf-8")
    legacy_guardrails_text = (ROOT / "runtime/workflows/legacy_guardrails.py").read_text(encoding="utf-8")
    legacy_source_grounding_text = (ROOT / "runtime/workflows/legacy_source_grounding.py").read_text(encoding="utf-8")
    helper_text = (ROOT / "runtime/workflows/source_tool_helpers.py").read_text(encoding="utf-8")
    tool_names_text = (ROOT / "runtime/tool_names.py").read_text(encoding="utf-8")
    tool_registry_text = (ROOT / "runtime/tool_registry.py").read_text(encoding="utf-8")

    for name in (
        "SEARCH_TOOL_NAMES",
        "FETCH_TOOL_NAMES",
        "WRDS_COMPANY_TOOL_NAMES",
    ):
        assert f"{name} =" not in graph_text
        assert f"{name} =" in helper_text

    assert "SOURCE_GROUNDING_KEYWORDS =" not in graph_text
    assert "SOURCE_GROUNDING_KEYWORDS =" not in helper_text
    assert "LEGACY_SOURCE_GROUNDING_KEYWORDS =" in legacy_source_grounding_text
    assert "legacy_source_grounding_keywords(" in helper_text
    assert "def legacy_source_grounding_keywords(" in legacy_source_grounding_text

    for name in (
        "WEB_SEARCH_TOOL_NAME",
        "PROVIDER_WEB_SEARCH_TOOL_NAME",
        "FETCH_URL_TOOL_NAME",
        "APPROVED_SOURCE_FETCH_TOOL_NAME",
    ):
        assert f"{name} =" not in graph_text
        assert f"{name} =" not in helper_text
        assert f"{name} =" in tool_names_text
        assert name in tool_registry_text

    for text in (graph_text, web_planner_text, legacy_plan_text, evidence_research_text):
        assert "from runtime.tool_names import" in text

    for literal in (
        '"web_search"',
        '"provider_web_search"',
        '"fetch_url"',
        '"approved_source_fetch"',
    ):
        assert literal not in graph_text
        assert literal not in helper_text
        assert literal not in tool_registry_text
        assert literal in tool_names_text

    assert "SEARCH_TOOL_NAMES =" not in web_planner_text
    assert '"web_search"' not in web_planner_text
    assert "SEARCH_TOOL_NAMES" in web_planner_text
    assert "WEB_SEARCH_TOOL_NAME" in web_planner_text
    assert '"web_search"' not in legacy_plan_text
    assert "WEB_SEARCH_TOOL_NAME" in legacy_plan_text
    assert "SEARCH_TOOL_NAMES =" not in evidence_research_text
    assert "FETCH_TOOL_NAMES =" not in evidence_research_text
    for name in (
        "APPROVED_SOURCE_FETCH_TOOL_NAME",
        "FETCH_URL_TOOL_NAME",
        "PROVIDER_WEB_SEARCH_TOOL_NAME",
        "WEB_SEARCH_TOOL_NAME",
    ):
        assert name in evidence_research_text

    assert "Only source candidates are available; recruit evidence recovery before confirmed synthesis." not in evidence_research_text
    assert "Only source candidates are available; recruit evidence recovery before confirmed synthesis." in legacy_guardrails_text
    assert "legacy_source_candidate_only_caveat(" in evidence_research_text
    assert "def legacy_source_candidate_only_caveat(" in legacy_guardrails_text

    for helper in (
        "should_auto_fetch_search_results(",
        "select_search_result_urls(",
        "summarize_execution_metric_status(",
        "should_upgrade_search_to_provider(",
        "requires_source_grounding(",
        "describe_source_grounding(",
    ):
        assert f"source_tool_helpers.{helper}" in graph_text


def test_graph_does_not_own_wrds_payload_safety_tables() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    audit_text = (ROOT / "runtime/audit_log.py").read_text(encoding="utf-8")
    helper_text = (ROOT / "runtime/workflows/wrds_payload_safety.py").read_text(encoding="utf-8")

    assert "RAW_WRDS_PUBLIC_KEYS =" not in graph_text
    assert "RAW_WRDS_PUBLIC_KEYS =" in helper_text
    assert "sanitize_wrds_public_payload(" not in graph_text
    assert "sanitize_wrds_public_payload(" in helper_text
    assert "raw WRDS row data is not exposed through public run responses" not in graph_text
    assert "raw WRDS row data is not exposed through public run responses" in helper_text
    assert "public_safe_wrds_result(" in graph_text
    assert "summarize_wrds_result_for_model(" in graph_text
    assert "def summarize_wrds_result(" not in audit_text
    assert "audit_safe_wrds_result_summary(" in audit_text
    assert "def audit_safe_wrds_result_summary(" in helper_text


def test_audit_log_uses_generic_agent_output_summary() -> None:
    audit_text = (ROOT / "runtime/audit_log.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in audit_text
    assert "summarize_committee_outputs" not in audit_text
    assert "runtime_agent_output_artifacts(" in audit_text
    assert '"agent_outputs"' in audit_text
    assert '"legacy_agent_outputs"' in audit_text
    assert '"agent_output_source"' in audit_text
    assert "committee_outputs" in compatibility_text


def test_audit_log_uses_generic_agent_decision_summary() -> None:
    audit_text = (ROOT / "runtime/audit_log.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_decisions.py").read_text(encoding="utf-8")

    assert "committee_decision" not in audit_text
    assert "summarize_committee_decision" not in audit_text
    assert "runtime_agent_decision_artifacts(" in audit_text
    assert '"agent_decision"' in audit_text
    assert '"legacy_agent_decision"' in audit_text
    assert '"agent_decision_source"' in audit_text
    assert "committee_decision" in compatibility_text


def test_audit_log_delegates_legacy_data_gate_permission_fields() -> None:
    audit_text = (ROOT / "runtime/audit_log.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_data_gate_permissions.py").read_text(encoding="utf-8")
    summary = re.search(
        r"def summarize_data_gate\(gate: Any\) -> dict\[str, Any\]:\n(?P<body>.*?)\n\n",
        audit_text,
        re.DOTALL,
    )

    assert summary is not None
    body = summary.group("body")
    assert '"report_publication_allowed"' not in body
    assert "legacy_publication_allowed_field(" in body
    assert '"report_publication_allowed"' in compatibility_text


def test_agent_run_response_exposes_generic_agent_state() -> None:
    route_text = (ROOT / "app/routes/agents.py").read_text(encoding="utf-8")
    response_model = re.search(
        r"class AgentRunResponse\(BaseModel\):\n(?P<body>.*?)\n\n@router\.post",
        route_text,
        re.DOTALL,
    )

    assert response_model is not None
    body = response_model.group("body")
    assert "agent_outputs:" in body
    assert "agent_decision:" in body
    assert "committee_outputs:" in body
    assert "committee_decision:" in body
    assert body.index("agent_outputs:") < body.index("committee_outputs:")
    assert body.index("agent_decision:") < body.index("committee_decision:")


def test_graph_does_not_own_legacy_data_gate_routing_fallback() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_data_gate_routing.py").read_text(encoding="utf-8")

    assert "LEGACY_DATA_GATE_TOOL_NAMES" not in graph_text
    assert "LEGACY_DATA_GATE_TOOL_NAMES =" not in graph_text
    assert "LEGACY_DATA_GATE_TOOL_NAMES =" in compatibility_text
    assert "legacy_data_gate_tool_names(" in graph_text
    assert "def legacy_data_gate_tool_names(" in compatibility_text
    assert "metadata.get(\"require_data_gate\")" not in graph_text
    assert "metadata.get(\"require_data_gate\")" in compatibility_text
    assert "WRDS_COMPANY_TOOL_NAMES | {\"wrds_query\"}" not in graph_text
    assert "legacy_graph_data_gate_required(" in graph_text
    assert "DATA_CONTRACT_DATA_GATE_REQUIRED_SOURCE" in graph_text


def test_source_policy_core_modules_do_not_own_legacy_web_tool_set() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_tool_policy.py").read_text(encoding="utf-8")
    assert "LEGACY_WEB_RESEARCH_TOOL_ACTIONS =" in compatibility_text

    for path in (
        "runtime/swarm/action_policy.py",
        "runtime/swarm/resolution.py",
        "runtime/swarm/tool_plan_policy.py",
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "LEGACY_WEB_RESEARCH_TOOL_ACTIONS =" not in text
        assert "WEB_RESEARCH_TOOL_ACTIONS =" not in text
        assert "WEB_RESEARCH_TOOL_NAMES =" not in text

    signal_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "runtime/swarm/action_policy.py",
            "runtime/swarm/signal_extractor.py",
        )
    )
    for phrase in (
        "current {source_mode} source policy disallows",
        "active WRDS-only source policy",
        "WRDS/metric-registry path; web research is disabled",
        "WRDS_ONLY source policy disables public web research.",
        "{action} is disabled because the current source policy is {source_mode}.",
    ):
        assert phrase not in signal_text
        assert phrase not in graph_text
        assert phrase in compatibility_text

    assert "source_policy_block_message(" in signal_text
    assert "source_policy_constraint_message(" in signal_text
    assert "legacy_source_policy_skill_block_reason(" in graph_text
    assert "legacy_source_policy_tool_disabled_detail(" in graph_text


def test_tool_health_sentinel_delegates_legacy_recommendations() -> None:
    tool_health_text = (ROOT / "runtime/swarm/tool_health.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_tool_health_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "block or reroute failing tool/model path before publication",
        "lower confidence and prefer deterministic fallback routes",
        "maintain current tool route",
        "Tool route health degraded.",
    ):
        assert phrase not in tool_health_text
        assert phrase in compatibility_text

    assert "legacy_tool_health_recommendation(" in tool_health_text
    assert "legacy_tool_health_failure_hints(" in tool_health_text
    assert "legacy_tool_health_recommendation_source(" in tool_health_text
    assert "legacy_tool_health_signal_fallback_content(" in tool_health_text
    assert "LEGACY_TOOL_HEALTH_RECOMMENDATION_SOURCE" not in tool_health_text
    assert "FAILURE_HINTS" not in tool_health_text
    assert "LEGACY_TOOL_HEALTH_RECOMMENDATION_SOURCE" in compatibility_text
    assert "LEGACY_TOOL_HEALTH_RECOMMENDATIONS =" in compatibility_text
    assert "LEGACY_TOOL_HEALTH_FAILURE_HINTS =" in compatibility_text
    assert "def legacy_tool_health_recommendation_source(" in compatibility_text
    assert "def legacy_tool_health_failure_hints(" in compatibility_text
    assert "def legacy_tool_health_signal_fallback_content(" in compatibility_text


def test_encounter_rate_delegates_legacy_recommendations() -> None:
    encounter_text = (ROOT / "runtime/swarm/encounter_rate.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_encounter_rate_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "maintain or expand current active lanes",
        "keep execution conservative and prioritize verifier feedback",
        "reduce expansion and route more work to verification",
        "collect more local return events before adjusting activation",
    ):
        assert phrase not in encounter_text
        assert phrase in compatibility_text

    assert "legacy_encounter_rate_recommendation(" in encounter_text
    assert "legacy_encounter_rate_recommendation_source(" in encounter_text
    assert "LEGACY_ENCOUNTER_RATE_RECOMMENDATION_SOURCE" not in encounter_text
    assert "LEGACY_ENCOUNTER_RATE_RECOMMENDATION_SOURCE" in compatibility_text
    assert "LEGACY_ENCOUNTER_RATE_RECOMMENDATIONS =" in compatibility_text
    assert "def legacy_encounter_rate_recommendation_source(" in compatibility_text


def test_arousal_controller_delegates_legacy_signal_template() -> None:
    arousal_text = (ROOT / "runtime/swarm/arousal.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_arousal_policy.py").read_text(encoding="utf-8")

    assert "Arousal level is {arousal_level}; raise verification intensity." not in arousal_text
    assert "Arousal level is {arousal_level}; raise verification intensity." in compatibility_text
    assert "legacy_arousal_signal_template(" in arousal_text
    assert "legacy_arousal_signal_template_source(" in arousal_text
    assert "LEGACY_AROUSAL_SIGNAL_TEMPLATE_SOURCE" not in arousal_text
    assert "LEGACY_AROUSAL_SIGNAL_TEMPLATE_SOURCE" in compatibility_text
    assert "LEGACY_AROUSAL_SIGNAL_TEMPLATE =" in compatibility_text
    assert "def legacy_arousal_signal_template_source(" in compatibility_text


def test_social_immunity_delegates_legacy_policy_text() -> None:
    social_text = (ROOT / "runtime/swarm/social_immunity.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_social_immunity_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "quarantine contaminated artifacts and require verifier-only handling",
        "raise verifier strictness and keep writer confidence conservative",
        "normal verification intensity",
        "High-risk or contaminated context detected; increase verification intensity.",
    ):
        assert phrase not in social_text
        assert phrase in compatibility_text

    assert "legacy_social_immunity_recommendation(" in social_text
    assert "legacy_social_immunity_policy_source(" in social_text
    assert "LEGACY_SOCIAL_IMMUNITY_POLICY_SOURCE" not in social_text
    assert "LEGACY_SOCIAL_IMMUNITY_POLICY_SOURCE" in compatibility_text
    assert "LEGACY_SOCIAL_IMMUNITY_RECOMMENDATIONS =" in compatibility_text
    assert "def legacy_social_immunity_policy_source(" in compatibility_text


def test_homeostasis_delegates_legacy_policy_text() -> None:
    homeostasis_text = (ROOT / "runtime/swarm/homeostasis.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_homeostasis_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "increase verifier and Red Team strictness",
        "recruit evidence receivers before producing more narrative",
        "deprioritize failing tool route",
        "compress agent outputs before final synthesis",
        "split work into lanes or suppress low-demand agents",
        "maintain current swarm balance",
        "Swarm homeostasis is {status}; apply stability recommendations.",
    ):
        assert phrase not in homeostasis_text
        assert phrase in compatibility_text

    assert "legacy_homeostasis_recommendation(" in homeostasis_text
    assert "legacy_homeostasis_recommendation_rules(" in homeostasis_text
    assert "legacy_homeostasis_policy_source(" in homeostasis_text
    assert "LEGACY_HOMEOSTASIS_POLICY_SOURCE" not in homeostasis_text
    assert "HOMEOSTASIS_RECOMMENDATION_RULES" not in homeostasis_text
    assert "LEGACY_HOMEOSTASIS_POLICY_SOURCE" in compatibility_text
    assert "LEGACY_HOMEOSTASIS_RECOMMENDATIONS =" in compatibility_text
    assert "LEGACY_HOMEOSTASIS_RECOMMENDATION_RULES =" in compatibility_text
    assert "def legacy_homeostasis_policy_source(" in compatibility_text
    assert "def legacy_homeostasis_recommendation_rules(" in compatibility_text


def test_lane_scheduler_delegates_legacy_and_global_lane_policy_text() -> None:
    lane_text = (ROOT / "runtime/swarm/lane_scheduler.py").read_text(encoding="utf-8")
    legacy_text = (ROOT / "runtime/swarm/legacy_lane_policy.py").read_text(encoding="utf-8")
    safety_text = (ROOT / "runtime/swarm/global_lane_safety_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "Assigned {agent} to {lane} lane.",
        '"final_judge": "control"',
        '"control", "chair"',
        '"verification", "verifier", "evidence", "audit", "auditor", "risk"',
    ):
        assert phrase not in lane_text
        assert phrase in legacy_text

    for phrase in (
        "writer cannot enter execution or control lane",
        "agents default to inspection lane",
        "GLOBAL_RESTRICTED_LANES =",
    ):
        assert phrase not in lane_text
        assert phrase in safety_text

    assert "global_lane_violation(" in lane_text
    assert "legacy_lane_policy(" in lane_text
    assert "legacy_lane_policy_source(" in lane_text
    assert "LEGACY_LANE_POLICY_SOURCE" not in lane_text
    assert "LEGACY_LANE_POLICY_SOURCE" in legacy_text
    assert "def legacy_lane_policy_source(" in legacy_text


def test_maturity_lifecycle_delegates_legacy_and_global_policy_text() -> None:
    maturity_text = (ROOT / "runtime/swarm/maturity.py").read_text(encoding="utf-8")
    legacy_text = (ROOT / "runtime/swarm/legacy_maturity_policy.py").read_text(encoding="utf-8")
    safety_text = (ROOT / "runtime/swarm/global_maturity_safety_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "MATURITY_ORDER =",
        "emit_unverified_signal",
        "perform_low_risk_task",
        "participate_quorum",
        "verify_limited_evidence",
        "propose_blocking_signal",
        "Agent maturity is {maturity}.",
    ):
        assert phrase not in maturity_text
        assert phrase in legacy_text

    for phrase in (
        "GLOBAL_TRUST_MATURITY_OVERRIDES =",
        '"third_party_untrusted": "observer"',
        '"user_installed": "worker"',
    ):
        assert phrase not in maturity_text
        assert phrase in safety_text

    assert "global_maturity_override_for_trust(" in maturity_text
    assert "legacy_maturity_policy(" in maturity_text
    assert "legacy_maturity_policy_source(" in maturity_text
    assert "LEGACY_MATURITY_POLICY_SOURCE" not in maturity_text
    assert "LEGACY_MATURITY_POLICY_SOURCE" in legacy_text
    assert "def legacy_maturity_policy_source(" in legacy_text


def test_independent_scout_delegates_legacy_policy_text() -> None:
    scout_text = (ROOT / "runtime/swarm/independent_scout.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_independent_scout_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "Independent scout diversity is {source_diversity}.",
        "source diversity below quorum policy threshold",
        "low independent support diversity; forced {fallback_label}",
        '"red_team"',
        '"fundamental"',
        '"industry"',
        '"market"',
    ):
        assert phrase not in scout_text
        assert phrase in compatibility_text

    assert "legacy_independent_scout_policy(" in scout_text
    assert "legacy_independent_scout_policy_source(" in scout_text
    assert "legacy_controller_quorum_policy_override_fields(" in scout_text
    assert "QUORUM_POLICY_OVERRIDES" not in scout_text
    assert "source_family_for_agent(" in scout_text
    assert "LEGACY_INDEPENDENT_SCOUT_POLICY_SOURCE" not in scout_text
    assert "LEGACY_INDEPENDENT_SCOUT_POLICY_SOURCE" in compatibility_text
    assert "LEGACY_CONTROLLER_QUORUM_POLICY_OVERRIDE_FIELDS =" in compatibility_text
    assert "def legacy_independent_scout_policy_source(" in compatibility_text
    assert "def legacy_controller_quorum_policy_override_fields(" in compatibility_text


def test_swarm_controller_delegates_legacy_action_policy_text() -> None:
    controller_text = (ROOT / "runtime/swarm/controllers.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_swarm_controller_policy.py").read_text(encoding="utf-8")

    for phrase in (
        "maintain current activation",
        "low verified return rate",
        "derived from arousal and Data Gate pressure",
        "critic_and_final_judge",
        "arousal controller requested stricter checks",
        "recruit evidence",
        "split work",
        "Swarm controller updated quorum policy from arousal and independence requirements.",
        "swarm controller action",
    ):
        assert phrase not in controller_text
        assert phrase in compatibility_text

    assert "legacy_swarm_controller_policy(" in controller_text
    assert "legacy_swarm_controller_policy_source(" in controller_text
    assert "controller_homeostasis_action(" in controller_text
    assert "LEGACY_SWARM_CONTROLLER_POLICY_SOURCE" not in controller_text
    assert "LEGACY_SWARM_CONTROLLER_POLICY_SOURCE" in compatibility_text
    assert "def legacy_swarm_controller_policy_source(" in compatibility_text


def test_source_policy_modules_use_shared_source_mode_aliases() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    data_gate_text = (ROOT / "runtime/data_gate.py").read_text(encoding="utf-8")
    action_policy_text = (ROOT / "runtime/swarm/action_policy.py").read_text(encoding="utf-8")
    tool_plan_text = (ROOT / "runtime/swarm/tool_plan_policy.py").read_text(encoding="utf-8")
    orchestration_guidance_text = (ROOT / "runtime/workflows/orchestration_guidance.py").read_text(encoding="utf-8")
    source_mode_text = (ROOT / "runtime/swarm/source_policy_modes.py").read_text(encoding="utf-8")

    for text in (action_policy_text, tool_plan_text):
        assert "WRDS_ONLY_SOURCE_MODES =" not in text
        assert "def source_mode_is_wrds_only(" not in text
        assert "from runtime.swarm.source_policy_modes import" in text
        assert "canonical_wrds_only_source_mode" in text
        assert "source_mode_is_wrds_only" in text
        assert '"WRDS_ONLY"' not in text

    for path in (
        "runtime/web_research_planner.py",
        "runtime/workflows/legacy_plan_defaults.py",
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "from runtime.swarm.tool_plan_policy import source_mode_is_wrds_only" not in text
        assert "from runtime.swarm.source_policy_modes import source_mode_is_wrds_only" in text

    for text in (graph_text, orchestration_guidance_text):
        assert "from runtime.swarm.source_policy_modes import" in text
        assert "canonical_wrds_only_source_mode" in text
        assert "source_mode_is_wrds_only" in text
        assert '"WRDS_ONLY"' not in text

    assert "from runtime.swarm.source_policy_modes import canonical_wrds_only_source_mode, source_mode_is_wrds_only" in data_gate_text
    assert 'source_mode == "WRDS_ONLY"' not in data_gate_text
    assert 'source_mode != "WRDS_ONLY"' not in data_gate_text
    assert 'get("source_mode") or "WRDS_ONLY"' not in data_gate_text
    assert 'source_mode_limitation_policy(contract, "WRDS_ONLY")' not in data_gate_text

    assert "CANONICAL_WRDS_ONLY_SOURCE_MODE =" in source_mode_text
    assert "WRDS_ONLY_SOURCE_MODES =" in source_mode_text
    assert "def canonical_wrds_only_source_mode(" in source_mode_text
    assert "def source_mode_is_wrds_only(" in source_mode_text


def test_output_contract_delegates_legacy_raw_data_markers() -> None:
    output_text = (ROOT / "runtime/output_contract.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_output_contract.py").read_text(encoding="utf-8")

    for marker in ('"gvkey"', '"datadate"', '"sale="', '"cogs="', '"oancf="'):
        assert marker not in output_text
        assert marker in compatibility_text

    assert "LEGACY_RAW_DATA_MARKERS =" not in output_text
    assert "LEGACY_RAW_DATA_MARKERS =" in compatibility_text
    assert '"legacy_raw_data_marker_fallback"' not in output_text
    assert "LEGACY_RAW_DATA_MARKER_FALLBACK_SOURCE" in compatibility_text
    assert "legacy_raw_data_markers(" in output_text
    assert "legacy_raw_data_marker_fallback_source(" in output_text


def test_patroller_uses_source_policy_helper_for_wrds_source_requirements() -> None:
    patroller_text = (ROOT / "runtime/swarm/patroller_gate.py").read_text(encoding="utf-8")
    tool_plan_text = (ROOT / "runtime/swarm/tool_plan_policy.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_tool_policy.py").read_text(encoding="utf-8")

    assert "wrds_source_required_for_state(" in patroller_text
    assert "web_tools_disabled_for_state(" not in patroller_text
    assert "wrds_only_mode" not in patroller_text
    assert "正式估值" not in patroller_text
    assert "WRDS data source is active." not in patroller_text
    assert "WRDS-only mode requires an active WRDS data source." not in patroller_text
    assert "legacy_wrds_source_readiness_detail(" in patroller_text
    assert "def legacy_wrds_source_readiness_detail(" in compatibility_text
    assert "def wrds_source_required_for_state(" in tool_plan_text
    assert '"wrds_only_mode"' not in tool_plan_text
    assert "legacy_os_plan_wrds_only_mode(" in tool_plan_text
    assert "wrds_only_mode" in compatibility_text


def test_research_selection_core_does_not_own_legacy_skill_name_sets() -> None:
    selector_text = (ROOT / "runtime/research_selection.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_research_selection.py").read_text(encoding="utf-8")

    for name in (
        "LEGACY_RESEARCH_SKILL_NAMES",
        "LEGACY_PUBLIC_WEB_RESEARCH_SKILL_NAMES",
        "LEGACY_COMPANY_FINANCIAL_DATA_SKILL_NAMES",
        "LEGACY_INVESTMENT_RESEARCH_SKILL_NAMES",
        "LEGACY_DIRECT_WRDS_DATA_SKILL_NAMES",
        "LEGACY_RESEARCH_CAPABILITY_TYPE_MARKERS",
        "LEGACY_PUBLIC_WEB_RESEARCH_CAPABILITY_TYPE_MARKERS",
        "LEGACY_COMPANY_FINANCIAL_DATA_CAPABILITY_TYPE_MARKERS",
        "LEGACY_INVESTMENT_RESEARCH_CAPABILITY_TYPE_MARKERS",
        "LEGACY_DIRECT_WRDS_DATA_CAPABILITY_TYPE_MARKERS",
        "LEGACY_RESEARCH_METADATA_FLAGS",
        "LEGACY_PUBLIC_WEB_RESEARCH_METADATA_FLAGS",
        "LEGACY_COMPANY_FINANCIAL_DATA_METADATA_FLAGS",
        "LEGACY_INVESTMENT_RESEARCH_METADATA_FLAGS",
        "LEGACY_DIRECT_WRDS_DATA_METADATA_FLAGS",
    ):
        assert f"{name} =" not in selector_text
        assert f"{name} =" in compatibility_text

    assert '"skill:value-investing-research"' not in selector_text
    assert '"skill:value-investing-research"' in compatibility_text
    assert '"skill:web-research"' not in selector_text
    assert '"skill:web-research"' in compatibility_text


def test_wrds_company_planner_does_not_own_legacy_company_detection_markers() -> None:
    planner_text = (ROOT / "runtime/wrds_company_planner.py").read_text(encoding="utf-8")
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    source_helper_text = (ROOT / "runtime/workflows/source_tool_helpers.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_wrds_company_planner.py").read_text(encoding="utf-8")

    for name in (
        "LEGACY_KNOWN_RESEARCH_COMPANY_MARKERS",
        "LEGACY_NON_COMPANY_QUERY_MARKERS",
        "LEGACY_TICKER_EXCLUDED_CODES",
        "LEGACY_CJK_COMPANY_SUFFIXES",
        "LEGACY_COMPANY_QUERY_INTENT_MARKERS",
    ):
        assert f"{name} =" not in planner_text
        assert f"{name} =" in compatibility_text

    for text in (planner_text, graph_text, source_helper_text):
        assert "KNOWN_RESEARCH_MARKERS" not in text
        assert '"wuxi apptec"' not in text
        assert '"release note"' not in text
        assert "known_research_company_markers(" in text

    assert '("公司", "股票", "财报", "估值", "投资", "ticker", "stock", "valuation")' not in planner_text
    assert "legacy_company_query_intent_markers(" in planner_text
    assert "def legacy_company_query_intent_markers(" in compatibility_text


def test_skill_loader_does_not_own_legacy_builtin_skill_matching_hints() -> None:
    loader_text = (ROOT / "runtime/skill_loader.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_skill_matching.py").read_text(encoding="utf-8")
    legacy_os_text = (ROOT / "runtime/legacy_os_intents.py").read_text(encoding="utf-8")

    for name in (
        "LOCAL_WORKSPACE_HINTS",
        "WEB_RESEARCH_HINTS",
        "KNOWN_PUBLIC_ENTITY_NAMES",
        "VALUE_INVESTING_HINTS",
        "DOCUMENT_WRITING_HINTS",
        "DATA_ANALYSIS_HINTS",
        "ENTITY_ANALYSIS_HINTS",
        "WRDS_HINTS",
    ):
        assert f"{name} =" not in loader_text
        assert f"{name} =" in compatibility_text

    for helper in (
        "infer_task_skill_names",
        "needs_wrds_data",
        "needs_web_research",
        "needs_value_investing_research",
        "needs_document_writing",
        "needs_data_analysis",
    ):
        assert f"def {helper}(" not in loader_text
        assert f"def {helper}(" in compatibility_text

    assert "from runtime.legacy_skill_matching import" in loader_text
    assert "from runtime.legacy_skill_matching import" in legacy_os_text


def test_wrds_planner_does_not_own_legacy_investment_package_defaults() -> None:
    planner_text = (ROOT / "runtime/wrds_planner.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_wrds_planner_defaults.py").read_text(encoding="utf-8")

    for name in (
        "BASE_INVESTMENT_PACKAGES",
        "ACCOUNT_AVAILABLE_PACKAGES",
        "ACCOUNT_UNAVAILABLE_PACKAGES",
        "SEMICONDUCTOR_PACKAGES",
        "MARKET_RISK_PACKAGES",
    ):
        assert f"{name} =" not in planner_text
        assert f"{name} =" in compatibility_text

    assert "PACKAGE_CATALOG: dict" not in planner_text
    assert "PACKAGE_CATALOG: dict" in compatibility_text

    for helper in (
        "build_default_data_packages",
        "build_default_research_questions",
        "infer_industry_profile",
        "requires_optionmetrics_market_risk",
    ):
        assert f"def {helper}(" not in planner_text
        assert f"def {helper}(" in compatibility_text

    for phrase in (
        "semiconductor_memory",
        "optionmetrics_security",
        "SK HYNIX",
        "borrow rate",
    ):
        assert phrase not in planner_text
        assert phrase in compatibility_text

    assert 'task_type == "investment"' not in planner_text
    assert 'task_type != "investment"' not in compatibility_text
    assert "LEGACY_INVESTMENT_TASK_TYPE" in compatibility_text
    assert "legacy_wrds_investment_defaults_enabled(" in planner_text
    assert "from runtime.legacy_wrds_planner_defaults import" in planner_text


def test_os_kernel_does_not_own_legacy_intent_vocab_or_required_map() -> None:
    kernel_text = (ROOT / "runtime/os_kernel.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_os_intents.py").read_text(encoding="utf-8")

    for name in (
        "EXPLICIT_INVESTMENT_HINTS",
        "GENERIC_ENTITY_ANALYSIS_HINTS",
        "NON_FINANCIAL_RESEARCH_HINTS",
        "COMMON_PUBLIC_COMPANY_NAMES",
        "NON_TICKER_ACRONYMS",
        "CODE_HINTS",
        "COMPLIANCE_HINTS",
        "EVIDENCE_RESEARCH_HINTS",
        "PORTFOLIO_HINTS",
        "DOCUMENT_HINTS",
        "DATA_ANALYSIS_HINTS",
        "PUBLIC_FINANCIAL_DATA_HINTS",
        "LEGACY_REQUIRED_CAPABILITY_TYPES_BY_INTENT",
    ):
        assert f"{name} =" not in kernel_text
        assert f"{name} =" in compatibility_text

    assert "unknown committee member ignored" not in kernel_text
    assert "unknown committee member ignored" in compatibility_text
    assert "legacy_unknown_committee_member_warning(" in kernel_text
    assert "def legacy_unknown_committee_member_warning(" in compatibility_text


def test_protocol_loader_does_not_own_generated_legacy_intent_map() -> None:
    loader_text = (ROOT / "runtime/swarm/protocol_loader.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_protocol_intents.py").read_text(encoding="utf-8")

    assert "LEGACY_CAPABILITY_TYPE_INTENTS =" not in loader_text
    assert "LEGACY_CAPABILITY_TYPE_INTENTS" not in loader_text
    assert "LEGACY_CAPABILITY_TYPE_INTENTS =" in compatibility_text
    assert "legacy_intents_for_capability_types(" in loader_text
    assert "def legacy_intents_for_capability_types(" in compatibility_text


def test_protocol_schema_delegates_legacy_quorum_field_aliases() -> None:
    schema_text = (ROOT / "runtime/swarm/protocol_schema.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_protocol_fields.py").read_text(encoding="utf-8")

    assert "force_insufficient_data_when_formal_valuation_blocked" not in schema_text
    assert "force_insufficient_data_when_formal_valuation_blocked" in compatibility_text
    assert "legacy_quorum_force_fallback_value(data)" in schema_text
    assert "legacy_quorum_policy_keys()" in schema_text


def test_protocol_loader_delegates_legacy_safe_fallback_label_inference() -> None:
    loader_text = (ROOT / "runtime/swarm/protocol_loader.py").read_text(encoding="utf-8")
    registry_text = (ROOT / "runtime/swarm/candidate_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_protocol_fields.py").read_text(encoding="utf-8")

    assert '"insufficient" in label.lower()' not in loader_text
    assert "LEGACY_SAFE_FALLBACK_LABEL_MARKERS =" not in loader_text
    assert "no capability-declared candidates and no legacy investment fallback matched" not in registry_text
    assert "legacy_candidate_safe_fallback_value(data, label)" in loader_text
    assert "legacy_candidate_registry_missing_policy_reason()" in registry_text
    assert "LEGACY_SAFE_FALLBACK_LABEL_MARKERS =" in compatibility_text
    assert "def legacy_candidate_safe_fallback_value(" in compatibility_text
    assert "LEGACY_CANDIDATE_REGISTRY_MISSING_POLICY_REASON =" in compatibility_text
    assert "def legacy_candidate_registry_missing_policy_reason(" in compatibility_text


def test_source_policy_delegates_legacy_tool_policy_field_aliases() -> None:
    schema_text = (ROOT / "runtime/swarm/protocol_schema.py").read_text(encoding="utf-8")
    action_text = (ROOT / "runtime/swarm/action_policy.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_tool_policy.py").read_text(encoding="utf-8")
    combined_core = f"{schema_text}\n{action_text}"

    for phrase in (
        "source_policy_blocking_tool_targets",
        "source_mode_blocked_tool_targets",
        "web_research_tool_targets",
        "SOURCE_POLICY_TOOL_TARGET_KEYS =",
    ):
        assert phrase not in combined_core
        assert phrase in compatibility_text

    assert "legacy_source_policy_blocked_tool_target_values(" in combined_core


def test_policing_delegates_legacy_default_tool_policy_violation_target() -> None:
    policing_text = (ROOT / "runtime/swarm/policing.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_tool_policy.py").read_text(encoding="utf-8")
    blocker_target = re.search(
        r"def blocking_target_for_violation\(item: dict\[str, Any\], \*, state: dict\[str, Any\] \| None = None\) -> str \| None:\n(?P<body>.*?)\n\n",
        policing_text,
        re.DOTALL,
    )

    assert blocker_target is not None
    body = blocker_target.group("body")
    assert '"web_search"' not in body
    assert "legacy_default_tool_policy_violation_target(" in body
    assert 'LEGACY_DEFAULT_TOOL_POLICY_VIOLATION_TARGET = "tool:web_search"' in compatibility_text


def test_goal_router_does_not_own_legacy_default_targets() -> None:
    router_text = (ROOT / "runtime/swarm/goal_router.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_goal_targets.py").read_text(encoding="utf-8")

    assert "LEGACY_DEFAULT_TARGETS_BY_INTENT" not in router_text
    assert "LEGACY_DEFAULT_TARGETS_BY_INTENT: dict" not in router_text
    assert "LEGACY_DEFAULT_TARGETS_BY_INTENT: dict" in compatibility_text
    assert "GoalTarget(TARGET_" not in router_text
    assert "GoalTarget(LEGACY_" in compatibility_text
    assert "legacy_default_targets_for_intent(intent)" in router_text


def test_data_gate_does_not_own_legacy_policy_tables() -> None:
    data_gate_text = (ROOT / "runtime/data_gate.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_data_gate_policy.py").read_text(encoding="utf-8")

    for name in (
        "LEGACY_COMPLETENESS_REQUIRED_METRICS",
        "LEGACY_METRIC_ALIASES",
        "LEGACY_WRDS_ONLY_LIMITATION_BOX",
        "LEGACY_WRDS_ONLY_CLAIM_GUARDRAIL_SOURCE",
        "LEGACY_WRDS_ONLY_CLAIM_DEFECT_MEMO_POLICY_SOURCE",
        "LEGACY_WRDS_ONLY_CLAIM_DEFECT_MEMO_POLICY",
        "LEGACY_WRDS_ONLY_CONFIDENCE_GUARDRAIL_SOURCE",
        "LEGACY_WRDS_ONLY_CONFIDENCE_GUARDRAIL_RULE",
        "LEGACY_DATA_GATE_REQUIRED_SOURCE",
        "LEGACY_DATA_GATE_REQUIRED_MATCH_RULES",
        "LEGACY_DATA_GATE_REQUIRED_DATA_RULES",
        "LEGACY_FORBIDDEN_CLAIM_SOURCE",
        "LEGACY_FORBIDDEN_CLAIMS",
        "LEGACY_FORMULA_VALIDATION_RULE_SOURCE",
        "LEGACY_FORMULA_VALIDATION_RULES",
        "LEGACY_GATE_EVIDENCE_GAP_RULE_SOURCE",
        "LEGACY_GATE_EVIDENCE_GAP_RULES",
        "LEGACY_MARGIN_BASIS_RULE_SOURCE",
        "LEGACY_MARGIN_BASIS_RULES",
        "LEGACY_GATE_METRIC_GROUP_SOURCE",
        "LEGACY_DATA_DEFECT_MEMO_POLICY_SOURCE",
        "LEGACY_DATA_DEFECT_MEMO_POLICY",
        "LEGACY_DATA_READINESS_MEMO_POLICY_SOURCE",
        "LEGACY_DATA_READINESS_MEMO_POLICY",
        "LEGACY_GATE_SCORE_POLICY_SOURCE",
        "LEGACY_GATE_SCORE_POLICIES",
        "LEGACY_NON_GAAP_METRICS",
        "LEGACY_ESTIMATE_METRICS",
        "LEGACY_GATE_METRIC_GROUPS",
        "LEGACY_METRIC_ALIAS_SOURCE",
        "LEGACY_METRIC_REGISTRY_ANNOTATION_SOURCE",
        "LEGACY_METRIC_REGISTRY_ANNOTATIONS",
        "LEGACY_METRIC_REGISTRY_ENTRYPOINT_WARNING_SOURCE",
        "LEGACY_METRIC_REGISTRY_ENTRYPOINT_WARNING",
        "LEGACY_METRIC_REGISTRY_POLICY_SOURCE",
        "LEGACY_METRIC_REGISTRY_WARNING_RULE_SOURCE",
        "LEGACY_METRIC_REGISTRY_WARNING_RULES",
        "LEGACY_PROFILE_POLICY_SOURCE",
        "LEGACY_WRDS_ONLY_METRIC_REQUIREMENT_SOURCE",
        "LEGACY_WRDS_ONLY_METRIC_REQUIREMENT_RULES",
        "LEGACY_WRDS_ONLY_OUTPUT_EFFECT_SOURCE",
        "LEGACY_WRDS_ONLY_OUTPUT_EFFECTS",
        "LEGACY_FORMAL_VALUATION_BLOCKED_OUTPUT_EFFECT",
        "LEGACY_WRDS_ONLY_REQUIRED_PERIOD_SOURCE",
        "LEGACY_WRDS_ONLY_REQUIRED_PERIOD_RULES",
        "LEGACY_WRDS_ONLY_LIMITATION_SOURCE",
        "LEGACY_SOURCE_MODE_POLICY_SOURCE",
        "LEGACY_SOURCE_RULE_SOURCE",
        "LEGACY_SOURCE_VALIDATION_RULES",
        "LEGACY_WRDS_ONLY_DISALLOWED_CLAIMS",
        "LEGACY_WRDS_ONLY_CLAIM_GUARDRAIL_DEFAULT_MESSAGE",
        "LEGACY_WRDS_ONLY_REQUIRED_FIXES",
        "LEGACY_WRDS_ONLY_LIMITATIONS",
        "LEGACY_CONFIDENCE_DOWNGRADE_RULES",
        "LEGACY_SOURCE_RULES",
        "LEGACY_SOURCE_MODE_POLICIES",
        "LEGACY_METRIC_REGISTRY_USAGE_RULES",
        "LEGACY_METRIC_REGISTRY_SOURCE_PRIORITY",
        "LEGACY_ACQUISITION_HINT_TICKERS",
        "LEGACY_ACQUISITION_HINT_NAME_MARKERS",
        "LEGACY_ACQUISITION_INTENSIVE_REQUIREMENTS",
        "LEGACY_ACQUISITION_VALUATION_POLICY",
        "LEGACY_BALANCE_SHEET_JUMP_RULE_SOURCE",
        "LEGACY_BALANCE_SHEET_JUMP_RULE",
        "LEGACY_COMPUSTAT_STANDARD_FILTER_RULE_SOURCE",
        "LEGACY_COMPUSTAT_STANDARD_FILTER_RULE",
        "LEGACY_PROFILE_POLICY_DEFAULTS",
        "LEGACY_PROFILE_EVIDENCE_RULE_SOURCE",
        "LEGACY_PROFILE_EVIDENCE_RULES",
        "LEGACY_PROFILE_WARNING_RULE_SOURCE",
        "LEGACY_PROFILE_WARNING_RULES",
        "HIGH_CONFIDENCE_RE",
        "QUARTER_TRIGGER_RE",
        "NON_GAAP_RE",
        "FORMAL_VALUATION_CONCLUSION_RE",
    ):
        assert f"{name} =" not in data_gate_text
        assert f"{name} =" in compatibility_text

    assert "LEGACY_" not in data_gate_text
    assert '"formal_valuation_blocked"' not in data_gate_text
    assert "legacy_formal_valuation_blocked_output_effect(" in data_gate_text
    assert "def legacy_formal_valuation_blocked_output_effect(" in compatibility_text
    assert "Acquisition-heavy company without sourced non-GAAP EPS cannot publish" not in data_gate_text
    assert "legacy_wrds_only_output_effect(" in data_gate_text
    assert "def legacy_wrds_only_output_effect(" in compatibility_text
    assert "stop_and_return_data_defect_report" not in data_gate_text
    assert "continue_to_committee_but_block_publication" not in data_gate_text
    assert "continue_to_research_quant_committee" not in data_gate_text
    assert "continue_to_committee_but_block_publication" in compatibility_text
    assert "Non-GAAP EPS cannot be used in WRDS-only mode without a reliable non-GAAP dataset." not in data_gate_text
    assert "legacy_wrds_only_metric_requirement_rule(" in data_gate_text
    assert "def legacy_wrds_only_metric_requirement_rule(" in compatibility_text
    assert "WRDS-only mode cannot publish high-confidence conclusions." not in data_gate_text
    assert "legacy_wrds_only_confidence_guardrail_rule(" in data_gate_text
    assert "def legacy_wrds_only_confidence_guardrail_rule(" in compatibility_text
    assert "WRDS-only mode disallows this claim." not in data_gate_text
    assert "legacy_wrds_only_claim_guardrail_default_message(" in data_gate_text
    assert "def legacy_wrds_only_claim_guardrail_default_message(" in compatibility_text
    assert "The report references a quarterly trigger, but the WRDS metric registry has no matching quarterly metrics." not in data_gate_text
    assert "legacy_wrds_only_required_period_rule(" in data_gate_text
    assert "def legacy_wrds_only_required_period_rule(" in compatibility_text
    assert 'task_type == "investment"' not in data_gate_text
    assert 'required.get("wrds")' not in data_gate_text
    assert "legacy_data_gate_required_matches(" in data_gate_text
    assert "def legacy_data_gate_required_matches(" in compatibility_text
    assert '["WRDS"]' not in data_gate_text
    assert "legacy_source_mode_policy(" in data_gate_text
    assert "def legacy_source_mode_policy(" in compatibility_text
    assert "The active data contract requires company financial statements before governed analysis." not in data_gate_text
    assert "legacy_data_gate_required_data_rule(" in data_gate_text
    assert "def legacy_data_gate_required_data_rule(" in compatibility_text
    assert "Compustat gross margin before depreciation materially exceeds the filing-like" not in data_gate_text
    assert "Do not cite raw Compustat gp/sale as GAAP reported gross margin without reconciliation." not in data_gate_text
    assert "legacy_metric_registry_warning_rule(" in data_gate_text
    assert "def legacy_metric_registry_warning_rule(" in compatibility_text
    assert "WRDS-derived filing-like gross margin candidate; not SEC/company verified in WRDS-only mode" not in data_gate_text
    assert "reported_gross_margin_candidate; uses (gross_profit_compustat - dp) / revenue" not in data_gate_text
    assert "reported_gross_margin_candidate; uses (gross_profit_compustat - dpq) / revenue" not in data_gate_text
    assert "legacy_metric_registry_annotation(" in data_gate_text
    assert "def legacy_metric_registry_annotation(" in compatibility_text
    assert "Capability metric-registry entrypoint failed; deterministic runtime fallback was used." not in data_gate_text
    assert "legacy_metric_registry_entrypoint_warning(" in data_gate_text
    assert "def legacy_metric_registry_entrypoint_warning(" in compatibility_text
    assert "Revenue must be positive for financial analysis." not in data_gate_text
    assert "Calculated free cash flow does not equal operating cash flow minus capex." not in data_gate_text
    assert "legacy_formula_validation_rule(" in data_gate_text
    assert "def legacy_formula_validation_rule(" in compatibility_text
    assert "High-depreciation semiconductor analysis cannot use before-depreciation" not in data_gate_text
    assert "High depreciation intensity detected; reports must disclose gross-margin basis explicitly." not in data_gate_text
    assert "legacy_margin_basis_rule(" in data_gate_text
    assert "def legacy_margin_basis_rule(" in compatibility_text
    assert "WRDS company resolver returned multiple top-scoring GVKEY candidates." not in data_gate_text
    assert "Compustat row uses a non-standard filter value; metrics may not be comparable." not in data_gate_text
    assert "legacy_compustat_standard_filter_rule(" in data_gate_text
    assert "def legacy_compustat_standard_filter_rule(" in compatibility_text
    assert "WRDS-only mode cannot explain whether this is an acquisition, reclassification, or data artifact" not in data_gate_text
    assert "publication is blocked until reconciled." not in data_gate_text
    assert "legacy_balance_sheet_jump_rule(" in data_gate_text
    assert "def legacy_balance_sheet_jump_rule(" in compatibility_text
    assert "Financial statement period is after the report as-of date." not in data_gate_text
    assert "No company/SEC reported metric set was provided for deterministic WRDS-vs-filing reconciliation." not in data_gate_text
    assert "WRDS/Compustat internal checks passed or failed without SEC/company-release reconciliation." not in data_gate_text
    assert "WRDS/metric-registry value conflicts with company/SEC reported metric." not in data_gate_text
    assert "legacy_source_validation_rule(" in data_gate_text
    assert "def legacy_source_validation_rule(" in compatibility_text
    assert "SEC-verified or company-reported unless official reconciliation is explicitly provided" not in data_gate_text
    assert "management guidance unless explicitly sourced" not in data_gate_text
    assert "legacy_forbidden_claims(" in data_gate_text
    assert "def legacy_forbidden_claims(" in compatibility_text
    assert "DEFAULT_NON_GAAP_METRICS =" not in data_gate_text
    assert "DEFAULT_ESTIMATE_METRICS =" not in data_gate_text
    assert "legacy_gate_metric_group(" in data_gate_text
    assert "def legacy_gate_metric_group(" in compatibility_text
    assert "legacy_gate_score_policy(" in data_gate_text
    assert "def legacy_gate_score_policy(" in compatibility_text
    assert "financial_company_specific_package" not in data_gate_text
    assert "alternative_valuation_anchor" not in data_gate_text
    assert "Company appears acquisition/intangible intensive based on goodwill/intangible asset ratios" not in data_gate_text
    assert "known acquisition-heavy identity markers" not in data_gate_text
    assert "Do not make formal relative-valuation or peer multiple claims." not in data_gate_text
    assert "Market setup and valuation-date conclusions should stay preliminary until CRSP is integrated." not in data_gate_text
    assert "Do not make strong segment-mix or segment-margin claims." not in data_gate_text
    assert "legacy_profile_policy(" in data_gate_text
    assert "def legacy_profile_policy(" in compatibility_text
    assert "No IBES/Street EPS estimate dataset is present." not in data_gate_text
    assert "legacy_gate_evidence_gap_rule(" in data_gate_text
    assert "def legacy_gate_evidence_gap_rule(" in compatibility_text
    assert "Acquisition/intangible-intensive company lacks sourced non-GAAP or Street EPS evidence;" not in data_gate_text
    assert "legacy_profile_evidence_rule(" in data_gate_text
    assert "def legacy_profile_evidence_rule(" in compatibility_text
    assert "Acquisition-heavy company lacks a sourced non-GAAP EPS dataset;" not in data_gate_text
    assert "legacy_profile_warning_rule(" in data_gate_text
    assert "def legacy_profile_warning_rule(" in compatibility_text
    assert "当前版本不可发布为投资结论" not in data_gate_text
    assert "Required Fixes Before Committee" not in data_gate_text
    assert "Fix WRDS internal consistency defects in company identity" not in data_gate_text
    assert "Reconcile WRDS metrics against company/SEC reported metrics" not in data_gate_text
    assert "legacy_data_defect_memo_policy(" in data_gate_text
    assert "def legacy_data_defect_memo_policy(" in compatibility_text
    assert "WRDS-only Claim Guardrail Report" not in data_gate_text
    assert "当前版本不可发布为最终投资报告" not in data_gate_text
    assert "legacy_wrds_only_claim_defect_memo_policy(" in data_gate_text
    assert "def legacy_wrds_only_claim_defect_memo_policy(" in compatibility_text

    wrds_claims = re.search(
        r"def validate_wrds_only_report_claims\(text: str, state: dict\[str, Any\]\) -> list\[dict\[str, Any\]\]:\n(?P<body>.*?)\n\n",
        data_gate_text,
        re.DOTALL,
    )
    assert wrds_claims is not None
    wrds_body = wrds_claims.group("body")
    assert 'gate.get("formal_valuation_allowed")' not in wrds_body
    assert "data_gate_conclusion_permission(" in wrds_body
    assert "legacy_formal_valuation_conclusion_target()" in wrds_body


def test_data_gate_permissions_do_not_own_legacy_top_level_fields() -> None:
    permissions_text = (ROOT / "runtime/swarm/data_gate_permissions.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_data_gate_permissions.py").read_text(encoding="utf-8")
    data_gate_policy_compatibility_text = (ROOT / "runtime/legacy_data_gate_policy.py").read_text(encoding="utf-8")
    data_gate_text = (ROOT / "runtime/data_gate.py").read_text(encoding="utf-8")
    evidence_graph_text = (ROOT / "runtime/swarm/evidence_graph.py").read_text(encoding="utf-8")
    resolution_text = (ROOT / "runtime/swarm/resolution.py").read_text(encoding="utf-8")
    arousal_text = (ROOT / "runtime/swarm/arousal.py").read_text(encoding="utf-8")
    stop_signal_text = (ROOT / "runtime/swarm/stop_signal.py").read_text(encoding="utf-8")
    policing_text = (ROOT / "runtime/swarm/policing.py").read_text(encoding="utf-8")
    signal_extractor_text = (ROOT / "runtime/swarm/signal_extractor.py").read_text(encoding="utf-8")
    formal_target_consumer_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "runtime/swarm/arousal.py",
            "runtime/swarm/conclusion_claims.py",
            "runtime/swarm/evidence_contract.py",
            "runtime/swarm/evidence_steward.py",
        )
    )

    assert "LEGACY_TOP_LEVEL_CONCLUSION_PERMISSION_KEYS =" not in permissions_text
    assert "TOP_LEVEL_CONCLUSION_PERMISSION_KEYS =" not in permissions_text
    assert "LEGACY_TOP_LEVEL_CONCLUSION_PERMISSION_KEYS =" in compatibility_text
    assert "LEGACY_FORMAL_VALUATION_CONCLUSION_TARGET =" not in formal_target_consumer_text
    assert "LEGACY_FORMAL_VALUATION_CONCLUSION_TARGET =" in compatibility_text
    assert '"decision:formal_valuation"' not in formal_target_consumer_text
    assert formal_target_consumer_text.count("legacy_formal_valuation_conclusion_target()") >= 4
    assert '"formal_valuation_allowed"' not in formal_target_consumer_text
    assert "legacy_formal_valuation_allowed_field(" in formal_target_consumer_text
    assert '"formal_valuation_allowed"' in compatibility_text
    assert "LEGACY_PUBLICATION_CONCLUSION_TARGET =" not in permissions_text
    assert "LEGACY_PUBLICATION_CONCLUSION_TARGET =" in compatibility_text
    assert "legacy_top_level_conclusion_permission_keys().items()" in permissions_text
    evaluator_start = data_gate_text.index("def evaluate_data_gate(")
    evaluator_end = data_gate_text.index("\ndef render_data_defect_memo", evaluator_start)
    evaluator_body = data_gate_text[evaluator_start:evaluator_end]
    assert '"formal_valuation_allowed"' not in evaluator_body
    assert '"report_publication_allowed"' not in evaluator_body
    assert "legacy_formal_valuation_allowed_field(" in evaluator_body
    assert "legacy_publication_allowed_field(" in evaluator_body
    publication_target_helper = re.search(
        r"def is_publication_target\(target: str\) -> bool:\n(?P<body>.*?)\n\n",
        permissions_text,
        re.DOTALL,
    )
    assert publication_target_helper is not None
    assert '"report_publication"' not in publication_target_helper.group("body")
    assert 'tail.endswith("_publication")' in publication_target_helper.group("body")
    assert '"decision:report_publication"' not in evidence_graph_text
    assert "publication_conclusion_permission_target(" in evidence_graph_text
    assert '"decision:report_publication"' not in resolution_text
    assert "publication_conclusion_permission_target(" in resolution_text
    assert "TARGET_REPORT_PUBLICATION" not in stop_signal_text
    assert "is_publication_target(" in stop_signal_text
    assert "TARGET_REPORT_PUBLICATION" not in policing_text
    assert '"decision:report_publication"' not in policing_text
    assert "publication_conclusion_permission_target(" in policing_text
    assert "legacy_publication_action_conclusion_target(" in policing_text
    assert 'target="report_publication"' not in signal_extractor_text
    assert "publication_conclusion_permission_target(" in signal_extractor_text
    publication_block_helper = re.search(
        r"def data_gate_publication_blocked\(state: dict\[str, Any\]\) -> bool:\n(?P<body>.*?)\n\n",
        data_gate_text,
        re.DOTALL,
    )
    assert publication_block_helper is not None
    assert "report_publication_allowed" not in publication_block_helper.group("body")
    assert "blocked_conclusion_permissions(" in publication_block_helper.group("body")
    assert "is_publication_target(" in publication_block_helper.group("body")
    readiness_memo = re.search(
        r"def render_data_readiness_memo\(state: dict\[str, Any\]\) -> str:\n(?P<body>.*?)\n\n",
        data_gate_text,
        re.DOTALL,
    )
    assert readiness_memo is not None
    readiness_body = readiness_memo.group("body")
    assert "Data Readiness Defect Report" not in data_gate_text
    assert "Data retrieval and governed analysis have run" not in data_gate_text
    assert "Resolve publication blockers before allowing Writer" not in data_gate_text
    assert "legacy_data_readiness_memo_policy(" in data_gate_text
    assert "def legacy_data_readiness_memo_policy(" in data_gate_policy_compatibility_text
    assert "Report publication allowed" not in readiness_body
    assert "formal investment report" not in readiness_body.lower()
    assert "committee analysis" not in readiness_body.lower()
    assert "publication_conclusion_permission_target(" in readiness_body
    assert "data_gate_conclusion_permission(" in readiness_body


def test_policing_delegates_legacy_publication_writer_action_aliases() -> None:
    policing_text = (ROOT / "runtime/swarm/policing.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_data_gate_permissions.py").read_text(encoding="utf-8")
    writer_action_target = re.search(
        r"def writer_action_output_target\(action: str\) -> str:\n(?P<body>.*?)\n\n",
        policing_text,
        re.DOTALL,
    )

    assert writer_action_target is not None
    body = writer_action_target.group("body")
    assert "LEGACY_PUBLICATION_ACTION_TARGET_TAILS =" in compatibility_text
    assert "legacy_publication_action_conclusion_target(" in body
    for phrase in (
        '"publish_report"',
        '"report_publication"',
        '"publication"',
        '"final_report"',
    ):
        assert phrase not in body
        assert phrase in compatibility_text


def test_direct_wrds_node_is_capability_owned() -> None:
    manifest_text = (ROOT / "capabilities/wrds-financial-data/capability.json").read_text(encoding="utf-8")
    node_text = (ROOT / "capabilities/wrds-financial-data/runtime_nodes.py").read_text(encoding="utf-8")
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_wrds_routing.py").read_text(encoding="utf-8")

    assert "runtime_nodes.py:build_runtime_node_descriptor" in manifest_text
    assert "async def wrds_agent_node" in node_text
    assert "async def plan_wrds_action" in node_text
    assert "def normalize_wrds_action" in node_text
    assert "def render_wrds_final" in node_text

    wrds_method = re.search(
        r"async def _wrds_agent\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _executor",
        graph_text,
        re.DOTALL,
    )
    assert wrds_method is not None
    body = wrds_method.group("body")
    assert '"wrds-financial-data"' not in graph_text
    assert 'load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "wrds_agent_node")' in body
    assert 'LEGACY_WRDS_FINANCIAL_DATA_CAPABILITY_ID = "wrds-financial-data"' in compatibility_text
    assert "def legacy_wrds_financial_data_capability_id(" in compatibility_text
    assert "You are the single WRDS Agent" not in body
    assert "_plan_wrds_action" not in graph_text
    assert "WRDS Agent 已完成只读查询" not in graph_text
    assert 'load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "normalize_wrds_action")' in graph_text
    assert 'load_capability_runtime_node(legacy_wrds_financial_data_capability_id(), "render_wrds_final")' in graph_text


def test_capability_runtime_nodes_emit_generic_agent_state_fields() -> None:
    value_text = (ROOT / "capabilities/value-investing-research/runtime_nodes.py").read_text(encoding="utf-8")
    wrds_text = (ROOT / "capabilities/wrds-financial-data/runtime_nodes.py").read_text(encoding="utf-8")

    assert "def state_with_agent_outputs(" in value_text
    assert '"agent_outputs": outputs' in value_text
    assert "governance_state = state_with_agent_outputs(" in value_text
    assert 'state_with_decision = {**state, "agent_decision": decision, "committee_decision": decision}' in value_text
    assert '"agent_decision": decision' in value_text
    assert "graph_runtime.parse_agent_decision(" in value_text
    assert "graph_runtime.fallback_agent_decision(" in value_text
    assert "graph_runtime.agent_decision_to_domain_analysis(" in value_text
    assert "graph_runtime.parse_committee_decision(" not in value_text
    assert "graph_runtime.fallback_committee_decision(" not in value_text
    assert "graph_runtime.committee_decision_to_domain_analysis(" not in value_text

    assert '"agent_outputs": {}' in wrds_text
    assert '"agent_decision": _skipped_analysis(' in wrds_text


def test_value_investing_support_reads_generic_agent_outputs() -> None:
    support_text = (ROOT / "capabilities/value-investing-research/support.py").read_text(encoding="utf-8")

    assert "from runtime.swarm.agent_outputs import runtime_agent_outputs" in support_text
    assert "def agent_outputs_for_state(" in support_text
    assert "runtime_agent_outputs(" in support_text
    assert 'state.get("committee_outputs"' not in support_text
    assert '"agent_outputs": summarized_outputs' in support_text
    assert '"committee_outputs": summarized_outputs' in support_text


def test_graph_agent_decision_helpers_are_generic_with_legacy_wrappers() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    support_text = (ROOT / "capabilities/value-investing-research/support.py").read_text(encoding="utf-8")

    assert 'load_value_investing_support_function("parse_agent_decision")' in graph_text
    assert 'load_value_investing_support_function("fallback_agent_decision")' in graph_text
    assert 'load_value_investing_support_function("agent_decision_to_domain_analysis")' in graph_text
    assert 'load_value_investing_support_function("summarize_agent_outputs_for_model")' in graph_text

    assert 'load_value_investing_support_function("parse_committee_decision")' not in graph_text
    assert 'load_value_investing_support_function("fallback_committee_decision")' not in graph_text
    assert 'load_value_investing_support_function("committee_decision_to_domain_analysis")' not in graph_text
    assert 'load_value_investing_support_function("summarize_committee_outputs_for_model")' not in graph_text

    assert "def parse_agent_decision(" in support_text
    assert "def fallback_agent_decision(" in support_text
    assert "def agent_decision_to_domain_analysis(" in support_text
    assert "def summarize_agent_outputs_for_model(" in support_text
    assert "return parse_agent_decision(content, state=state)" in support_text
    assert "return fallback_agent_decision(state, summary=summary)" in support_text
    assert "return agent_decision_to_domain_analysis(decision)" in support_text
    assert "return summarize_agent_outputs_for_model(outputs)" in support_text


def test_graph_does_not_own_legacy_direct_wrds_routing_defaults() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/workflows/legacy_wrds_routing.py").read_text(encoding="utf-8")

    for name in (
        "default_should_run_wrds_agent",
        "default_should_bypass_graph_to_wrds",
        "default_direct_wrds_orchestration",
    ):
        assert f"def {name}" not in graph_text

    assert 'metadata.get("wrds_sql") or metadata.get("wrds_action")' not in graph_text
    assert 'task.strip().lower().startswith(("select ", "with "))' not in graph_text
    assert "Explicit WRDS data retrieval request; bypassing the general multi-agent workflow." not in graph_text
    assert "WRDS data retrieval" not in graph_text
    assert "Run a single read-only WRDS data retrieval action." not in graph_text

    assert "legacy_should_run_wrds_agent(" in graph_text
    assert "legacy_should_bypass_graph_to_wrds(" in graph_text
    assert "legacy_direct_wrds_orchestration(" in graph_text
    assert "legacy_direct_wrds_plan_step(" in graph_text
    assert 'metadata.get("wrds_sql") or metadata.get("wrds_action")' in compatibility_text
    assert 'task.strip().lower().startswith(("select ", "with "))' in compatibility_text
    assert "WRDS data retrieval" in compatibility_text
    assert "Run a single read-only WRDS data retrieval action." in compatibility_text
    assert "legacy_wrds_routing_fallback" in compatibility_text


def test_platform_wrds_routes_dispatch_through_tool_registry() -> None:
    route_text = (ROOT / "app/routes/wrds.py").read_text(encoding="utf-8")

    assert "ToolRegistry" in route_text
    assert "WRDSTools(" not in route_text
    assert 'run_wrds_tool("wrds_query"' in route_text
    assert "wrds_company_financials" in route_text
    assert route_text.count("run_wrds_tool(") >= 8


def test_committee_authority_and_support_use_shared_manifest_semantics() -> None:
    registry_text = (ROOT / "runtime/agent_registry.py").read_text(encoding="utf-8")
    authority_text = (ROOT / "runtime/swarm/authority.py").read_text(encoding="utf-8")
    value_support_text = (ROOT / "capabilities/value-investing-research/support.py").read_text(encoding="utf-8")

    assert "def committee_capable" in registry_text
    assert "committee_capable(" in authority_text
    assert "committee_capable(" in value_support_text
    assert "investment_committee_member" not in authority_text
    assert "investment_committee_member" not in value_support_text
    assert "LEGACY_DEFAULT_COMMITTEE_CAPABILITY_IDS" not in value_support_text
    assert "legacy_default_committee_capability_ids(" in value_support_text

    compatibility_text = (ROOT / "runtime/legacy_value_investing_support.py").read_text(encoding="utf-8")
    assert 'LEGACY_VALUE_INVESTING_CAPABILITY_ID = "value-investing-research"' in compatibility_text
    assert "def legacy_value_investing_capability_id(" in compatibility_text
    assert 'LEGACY_DEFAULT_COMMITTEE_CAPABILITY_IDS = frozenset({"value-investing-research"})' in compatibility_text
    assert "def legacy_default_committee_capability_ids(" in compatibility_text


def test_agent_registry_does_not_own_legacy_committee_agent_types() -> None:
    registry_text = (ROOT / "runtime/agent_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_agent_registry.py").read_text(encoding="utf-8")

    assert "LEGACY_COMMITTEE_AGENT_TYPES =" not in registry_text
    assert "COMPATIBILITY_COMMITTEE_AGENT_TYPES =" not in registry_text
    assert "investment_committee_member" not in registry_text
    assert "LEGACY_COMMITTEE_AGENT_TYPES =" in compatibility_text
    assert "investment_committee_member" in compatibility_text
    assert "legacy_committee_agent_type(" in registry_text


def test_agent_signal_extractor_uses_generic_proposal_source() -> None:
    extractor_text = (ROOT / "runtime/swarm/signal_extractor.py").read_text(encoding="utf-8")
    authority_text = (ROOT / "runtime/swarm/authority.py").read_text(encoding="utf-8")
    value_adapter_text = (ROOT / "capabilities/value-investing-research/evidence_adapter.py").read_text(encoding="utf-8")

    assert "AGENT_PROPOSAL_MODULE" in extractor_text
    assert 'source_module="committee_agent"' not in extractor_text
    assert "committee signal proposal" not in extractor_text
    assert 'AGENT_PROPOSAL_MODULE = "capability_agent"' in authority_text
    assert "LEGACY_AGENT_PROPOSAL_MODULES" not in authority_text
    assert "legacy_agent_proposal_modules(" in authority_text
    assert '"proposal_sources": ["capability_agent", "critic"]' in value_adapter_text

    compatibility_text = (ROOT / "runtime/legacy_agent_registry.py").read_text(encoding="utf-8")
    assert 'LEGACY_AGENT_PROPOSAL_MODULES = {"committee_agent"}' in compatibility_text
    assert "def legacy_agent_proposal_modules(" in compatibility_text


def test_runtime_metadata_prefers_generic_agent_catalog() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_agent_registry.py").read_text(encoding="utf-8")
    support_text = (ROOT / "capabilities/value-investing-research/support.py").read_text(encoding="utf-8")
    execution_loop_text = (ROOT / "runtime/swarm/execution_loop.py").read_text(encoding="utf-8")

    assert '"agent_catalog": agent_catalog' in graph_text
    assert '"committee_agent_catalog": (context.agent_registry or {}).get("agents", [])' not in graph_text
    assert "legacy_committee_agent_catalog_metadata(agent_catalog)" in graph_text
    assert "LEGACY_COMMITTEE_AGENT_CATALOG_METADATA_KEY" in compatibility_text
    assert 'LEGACY_COMMITTEE_AGENT_CATALOG_METADATA_KEY = "committee_agent_catalog"' in compatibility_text
    assert "def legacy_committee_agent_catalog_from_metadata(" in compatibility_text
    assert 'metadata.get("agent_catalog")' in support_text
    assert 'metadata.get("committee_agent_catalog")' not in support_text
    assert "legacy_committee_agent_catalog_from_metadata(metadata)" in support_text
    assert 'metadata.get("agent_catalog")' in execution_loop_text
    assert 'metadata.get("committee_agent_catalog")' not in execution_loop_text
    assert "legacy_committee_agent_catalog_from_metadata(metadata)" in execution_loop_text


def test_selected_agent_metadata_delegates_legacy_committee_keys() -> None:
    compatibility_text = (ROOT / "runtime/legacy_agent_registry.py").read_text(encoding="utf-8")
    platform_text = (ROOT / "app/routes/platform.py").read_text(encoding="utf-8")

    for path in (
        "runtime/graph.py",
        "runtime/runtime_context.py",
        "capabilities/value-investing-research/support.py",
        "capabilities/value-investing-research/runtime_nodes.py",
    ):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert 'metadata.get("committee_member_ids")' not in text
        assert 'metadata.get("committee_members")' not in text
        assert 'metadata.get("selected_committee_members")' not in text
        assert "selected_agent_ids_from_metadata(" in text

    assert "selected_agent_ids_from_metadata(payload.metadata)" in platform_text
    assert 'GENERIC_SELECTED_AGENT_METADATA_KEYS = ("selected_agent_ids", "agent_ids", "selected_agents")' in compatibility_text
    assert 'LEGACY_SELECTED_AGENT_METADATA_KEYS = ("committee_member_ids", "committee_members", "selected_committee_members")' in compatibility_text


def test_authority_levels_use_generic_trusted_agent_name() -> None:
    authority_text = (ROOT / "runtime/swarm/authority.py").read_text(encoding="utf-8")

    assert "TRUSTED_AGENT = 3" in authority_text
    assert "TRUSTED_COMMITTEE" not in authority_text
    assert '"critic": AuthorityLevel.TRUSTED_AGENT' in authority_text


def test_response_threshold_core_does_not_own_legacy_role_term_fallbacks() -> None:
    threshold_text = (ROOT / "runtime/swarm/response_threshold.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_response_thresholds.py").read_text(encoding="utf-8")

    for phrase in (
        "red_team",
        "gatekeeper",
        "business_quality",
        "market_setup",
        "committee needs a bear-case challenge",
        "entry timing is secondary unless market data is available",
    ):
        assert phrase not in threshold_text
        assert phrase in compatibility_text

    assert "from runtime.swarm.legacy_response_thresholds import" in threshold_text
    assert "response_demand_profiles" in threshold_text
    assert "manifest_role_demand_from_profiles(" in threshold_text
    assert '"committee_review"' not in threshold_text
    assert "default committee participation" not in threshold_text
    assert '"agent_review"' in threshold_text
    assert "default agent participation" in threshold_text


def test_runtime_context_does_not_own_legacy_model_role_alias_tables() -> None:
    context_text = (ROOT / "runtime/runtime_context.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_model_roles.py").read_text(encoding="utf-8")

    for phrase in (
        "red_team_skeptic",
        "critic_agent",
        "market_execution_agent",
        "LEGACY_EXECUTION_MODEL_ROLE_FIELDS",
        "LEGACY_FALLBACK_MODEL_ROLE_FIELDS",
    ):
        assert phrase not in context_text
        assert phrase in compatibility_text

    assert "data_auditor_agent=judgment_model" not in context_text
    assert '"data_auditor_agent": model' not in context_text
    assert "model_roles_for_single_provider(" in context_text
    assert "model_roles_for_provider_mix(" in context_text
    assert "legacy_scoped_agent_field(" in context_text


def test_runtime_context_delegates_legacy_wrds_validation_details() -> None:
    context_text = (ROOT / "runtime/runtime_context.py").read_text(encoding="utf-8")
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/legacy_runtime_validation.py").read_text(encoding="utf-8")

    for phrase in (
        "WRDS capability is enabled but no active WRDS connection is configured.",
        "WRDS capability is enabled but WRDS tools were not registered.",
        '"wrds_capability_without_connection"',
        '"wrds_tools_not_registered"',
    ):
        assert phrase not in context_text
        assert phrase not in graph_text
        assert phrase in compatibility_text

    assert "legacy_wrds_capability_enabled(" in context_text
    assert "legacy_wrds_missing_connection_issue(" in context_text
    assert "legacy_wrds_status_tool_name(" in context_text
    assert "legacy_wrds_tools_not_registered_issue(" in context_text
    assert "legacy_wrds_validation_issue_codes(" in graph_text
    assert "def legacy_wrds_validation_issue_codes(" in compatibility_text


def test_core_writer_modules_do_not_own_legacy_formal_valuation_phrase_tables() -> None:
    core_paths = (
        "runtime/writer_guardrails.py",
        "runtime/swarm/stop_signal.py",
        "runtime/swarm/evidence_contract.py",
        "runtime/swarm/conclusion_claims.py",
        "runtime/swarm/policing.py",
    )
    core_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in core_paths)
    compatibility_text = (ROOT / "runtime/swarm/legacy_output_phrases.py").read_text(encoding="utf-8")

    for phrase in (
        "Strong Buy",
        "target price",
        "目标价",
        "writer:formal_valuation",
        "LEGACY_FORMAL_RECOMMENDATION_RE =",
        "LEGACY_FORMAL_VALUATION_RE =",
        "LEGACY_FORMAL_VALUATION_PHRASES =",
        "LEGACY_INSUFFICIENT_DATA_PHRASES =",
        "LEGACY_FALLBACK_CANDIDATE_CONFLICT_TERMS =",
        "Formal valuation is blocked by swarm stop-signal.",
        "LEGACY_FORMAL_VALUATION_STOP_SIGNAL_REPORT_SOURCE =",
    ):
        assert phrase not in core_text
        assert phrase in compatibility_text

    for helper in (
        "legacy_formal_recommendation_present(",
        "legacy_formal_valuation_present(",
        "legacy_formal_valuation_phrases(",
        "legacy_formal_valuation_writer_action(",
        "legacy_insufficient_data_phrases(",
        "legacy_fallback_candidate_conflict_present(",
        "legacy_formal_valuation_stop_signal_report(",
    ):
        assert helper in core_text


def test_quorum_core_does_not_own_legacy_formal_report_boolean_backfill() -> None:
    core_paths = (
        "runtime/swarm/quorum.py",
        "runtime/swarm/quorum_marshal.py",
        "runtime/swarm/governance_results.py",
        "runtime/audit_log.py",
    )
    core_text = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in core_paths)
    compatibility_text = (ROOT / "runtime/swarm/legacy_quorum_targets.py").read_text(encoding="utf-8")
    target_compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")

    for phrase in (
        "formal_valuation_blocked",
        "report_publication_blocked",
        "LEGACY_QUORUM_FORMAL_FLAG",
        "LEGACY_QUORUM_PUBLICATION_FLAG",
    ):
        assert phrase not in core_text
        assert phrase in compatibility_text

    assert "is_report_publication_target" not in core_text
    assert "legacy_formal_valuation_target(" in compatibility_text
    assert "legacy_report_publication_target(" in compatibility_text
    assert "LEGACY_FORMAL_VALUATION_TARGET" in target_compatibility_text
    assert "LEGACY_REPORT_PUBLICATION_TARGET" in target_compatibility_text

    for helper in (
        "legacy_quorum_block_flags(",
        "legacy_quorum_flags_from_report(",
        "legacy_blocked_conclusion_targets_from_quorum_flags(",
    ):
        assert helper in core_text


def test_target_registry_does_not_own_legacy_domain_alias_audit_tables() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")

    for phrase in (
        "target_price",
        "investment recommendation",
        "public_api_changed",
        "accept_patch",
        "approval_required",
        "email_send",
        "fake_citation",
        "source_candidates",
    ):
        assert phrase not in registry_text
        assert phrase in compatibility_text

    for table_name in (
        "LEGACY_INVESTMENT_TARGET_ALIASES",
        "LEGACY_CODE_TARGET_ALIASES",
        "LEGACY_COMPLIANCE_TARGET_ALIASES",
        "LEGACY_RESEARCH_TARGET_ALIASES",
    ):
        assert table_name not in registry_text
        assert f"{table_name} =" in compatibility_text

    assert "from runtime.swarm.legacy_target_aliases import legacy_canonical_target_alias" in registry_text
    assert "legacy_canonical_target_alias(lowered)" in registry_text
    assert "legacy_target_aliases_by_domain(" in compatibility_text


def test_target_registry_does_not_export_legacy_formal_report_targets() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")

    for phrase in (
        "TARGET_FORMAL_VALUATION",
        "TARGET_REPORT_PUBLICATION",
        "CANONICAL_INVESTMENT_DECISION_TARGETS",
        "def is_formal_valuation_target(",
        "def is_report_publication_target(",
    ):
        assert phrase not in registry_text

    for phrase in (
        "LEGACY_FORMAL_VALUATION_TARGET",
        "LEGACY_REPORT_PUBLICATION_TARGET",
        "def legacy_formal_valuation_target(",
        "def legacy_report_publication_target(",
    ):
        assert phrase in compatibility_text


def test_target_registry_does_not_export_legacy_domain_target_constants() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")

    for phrase in (
        "TARGET_CODE_",
        "TARGET_COMPLIANCE_",
        "TARGET_RESEARCH_",
    ):
        assert phrase not in registry_text

    for phrase in (
        "LEGACY_CODE_TEST_GATE_TARGET",
        "LEGACY_COMPLIANCE_APPROVAL_TARGET",
        "LEGACY_RESEARCH_EVIDENCE_GATE_TARGET",
    ):
        assert phrase in compatibility_text


def test_target_registry_does_not_export_legacy_web_tool_targets() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")

    assert "TARGET_TOOL_" not in registry_text
    assert "LEGACY_WEB_TOOL_TARGET_ALIASES =" in compatibility_text
    for phrase in (
        "LEGACY_TOOL_WEB_SEARCH_TARGET",
        "LEGACY_TOOL_PROVIDER_WEB_SEARCH_TARGET",
        "LEGACY_TOOL_FETCH_URL_TARGET",
        "LEGACY_TOOL_APPROVED_SOURCE_FETCH_TARGET",
    ):
        assert phrase in compatibility_text


def test_target_registry_delegates_legacy_source_policy_aliases_to_compatibility() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")
    registry_aliases = re.search(
        r"CANONICAL_TARGET_ALIASES = \{(?P<body>.*?)\n\}",
        registry_text,
        re.DOTALL,
    )

    assert registry_aliases is not None
    assert '"wrds_only"' not in registry_aliases.group("body")
    assert "LEGACY_SOURCE_POLICY_TARGET_ALIASES =" in compatibility_text
    assert '"wrds_only"' in compatibility_text


def test_target_registry_delegates_legacy_web_tool_aliases_to_compatibility() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")
    registry_aliases = re.search(
        r"CANONICAL_TARGET_ALIASES = \{(?P<body>.*?)\n\}",
        registry_text,
        re.DOTALL,
    )

    assert registry_aliases is not None
    registry_alias_body = registry_aliases.group("body")
    for phrase in (
        '"web_search"',
        '"provider_web_search"',
        '"fetch_url"',
        '"approved_source_fetch"',
    ):
        assert phrase not in registry_alias_body
        assert phrase in compatibility_text


def test_target_registry_delegates_legacy_formal_report_aliases_to_compatibility() -> None:
    registry_text = (ROOT / "runtime/swarm/target_registry.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_target_aliases.py").read_text(encoding="utf-8")
    registry_aliases = re.search(
        r"CANONICAL_TARGET_ALIASES = \{(?P<body>.*?)\n\}",
        registry_text,
        re.DOTALL,
    )

    assert registry_aliases is not None
    registry_alias_body = registry_aliases.group("body")
    assert "LEGACY_DECISION_TARGET_ALIASES =" in compatibility_text
    for phrase in (
        '"formal_valuation"',
        '"formal valuation"',
        '"decision_formal_valuation"',
        '"decision:valuation"',
        '"valuation"',
        '"report_publication"',
        '"report publication"',
        '"decision_report_publication"',
        '"publication"',
        '"final_report"',
        '"report"',
    ):
        assert phrase not in registry_alias_body
        assert phrase in compatibility_text


def test_output_chain_nodes_are_runtime_node_owned() -> None:
    node_text = (ROOT / "runtime/nodes/output_chain.py").read_text(encoding="utf-8")
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")

    for node_name in ("critic_node", "writer_node", "final_judge_node"):
        assert f"async def {node_name}" in node_text

    critic_method = re.search(
        r"async def _critic\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _writer",
        graph_text,
        re.DOTALL,
    )
    writer_method = re.search(
        r"async def _writer\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _final_judge",
        graph_text,
        re.DOTALL,
    )
    final_method = re.search(
        r"async def _final_judge\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n\ndef normalize_wrds_action",
        graph_text,
        re.DOTALL,
    )
    assert critic_method is not None
    assert writer_method is not None
    assert final_method is not None

    assert "critic_node(self, state)" in critic_method.group("body")
    assert "writer_node(self, state)" in writer_method.group("body")
    assert "final_judge_node(self, state)" in final_method.group("body")
    assert "You are the Critic / Verifier Agent" not in graph_text
    assert "writer_system_prompt()" not in graph_text
    assert "final_judge_system_prompt()" not in graph_text
    assert "apply_writer_guardrails" not in graph_text
    assert "apply_final_judge_guardrails" not in graph_text

    for phrase in (
        "investment committee",
        "investment recommendation",
        "final investment report",
        "committee outputs",
        "report publication",
        "data_gate_report_publication_blocked",
        "swarm_report_publication_blocked",
    ):
        assert phrase not in node_text


def test_writer_guardrail_prompt_uses_generic_publication_wording() -> None:
    writer_text = (ROOT / "runtime/writer_guardrails.py").read_text(encoding="utf-8")

    assert "committee outputs" not in writer_text
    assert "report publication" not in writer_text
    assert "blocks publication" in writer_text


def test_shared_publication_block_wording_is_generic() -> None:
    shared_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "runtime/data_gate.py",
            "runtime/swarm/signal_extractor.py",
            "runtime/swarm/homeostasis.py",
            "runtime/writer_guardrails.py",
        )
    )

    for phrase in (
        "report publication",
        "Report publication",
        "committee analysis",
        "committee outputs",
        "formal investment report",
        "formal report publication",
        "Investment workflow requires",
    ):
        assert phrase not in shared_text


def test_homeostasis_uses_generic_agent_output_helper() -> None:
    homeostasis_text = (ROOT / "runtime/swarm/homeostasis.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in homeostasis_text
    assert "runtime_agent_outputs(" in homeostasis_text
    assert "committee_outputs" in compatibility_text


def test_receiver_normalizer_uses_generic_agent_outputs() -> None:
    receiver_text = (ROOT / "runtime/swarm/receiver_normalizer.py").read_text(encoding="utf-8")
    steward_text = (ROOT / "runtime/swarm/evidence_steward.py").read_text(encoding="utf-8")
    governance_text = (ROOT / "runtime/swarm/governance_results.py").read_text(encoding="utf-8")
    contracts_text = (ROOT / "runtime/swarm/governance_contracts.py").read_text(encoding="utf-8")

    for text in (receiver_text, steward_text, governance_text):
        assert "committee claims" not in text

    assert "committee_outputs" not in receiver_text
    assert "runtime_agent_outputs(" in receiver_text
    assert "handoff:agent_claims" in receiver_text
    assert "raw_agent_outputs_are_not_final_ready" in receiver_text
    assert 'input_contract=["agent_outputs"]' in contracts_text
    assert "Normalizes agent prose" in contracts_text


def test_bottleneck_recruitment_uses_generic_agent_outputs() -> None:
    bottleneck_text = (ROOT / "runtime/swarm/bottleneck_recruitment.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in bottleneck_text
    assert "committee_missing_data" not in bottleneck_text
    assert "runtime_agent_outputs(" in bottleneck_text
    assert "agent_missing_data_count(" in bottleneck_text
    assert "data_gate/metric_registry/agent_missing_data" in bottleneck_text
    assert "committee_outputs" in compatibility_text


def test_independent_scout_uses_generic_agent_outputs() -> None:
    scout_text = (ROOT / "runtime/swarm/independent_scout.py").read_text(encoding="utf-8")
    contracts_text = (ROOT / "runtime/swarm/governance_contracts.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in scout_text
    assert "runtime_agent_outputs(" in scout_text
    assert 'input_contract=["agent_outputs", "quorum_trace", "swarm_controller_report"]' in contracts_text
    assert "committee_outputs" in compatibility_text


def test_social_immunity_scans_generic_agent_output_artifacts() -> None:
    social_text = (ROOT / "runtime/swarm/social_immunity.py").read_text(encoding="utf-8")
    contracts_text = (ROOT / "runtime/swarm/governance_contracts.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in social_text
    assert "runtime_agent_output_artifacts(" in social_text
    assert 'input_contract=["execution_log", "research_brief", "wrds_result", "agent_outputs"]' in contracts_text
    assert "legacy_agent_outputs" in compatibility_text
    assert "committee_outputs" in compatibility_text


def test_outcome_memory_uses_generic_agent_outputs() -> None:
    outcome_text = (ROOT / "runtime/swarm/outcome_memory.py").read_text(encoding="utf-8")
    contracts_text = (ROOT / "runtime/swarm/governance_contracts.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in outcome_text
    assert "committee_review" not in outcome_text
    assert "runtime_agent_outputs(" in outcome_text
    assert "agent_outputs.*.thesis" in outcome_text
    assert "legacy_agent_outputs.*.thesis" in outcome_text
    assert 'input_contract=["agent_outputs", "agent_signal_diagnostics", "policing_trace"]' in contracts_text
    assert "committee_outputs" in compatibility_text


def test_outcome_feedback_delegates_legacy_excluded_fields() -> None:
    feedback_text = (ROOT / "runtime/swarm/outcome_feedback.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/legacy_outcome_feedback.py").read_text(encoding="utf-8")

    for phrase in ('"committee_decision"', '"formal_decision"'):
        assert phrase not in feedback_text
        assert phrase in compatibility_text

    assert "legacy_outcome_feedback_excluded_fields(" in feedback_text
    assert "def legacy_outcome_feedback_excluded_fields(" in compatibility_text


def test_quorum_scores_use_generic_agent_outputs() -> None:
    quorum_text = (ROOT / "runtime/swarm/quorum.py").read_text(encoding="utf-8")
    compatibility_text = (ROOT / "runtime/swarm/agent_outputs.py").read_text(encoding="utf-8")

    assert "committee_outputs" not in quorum_text
    assert "runtime_agent_outputs(" in quorum_text
    assert "committee_outputs" in compatibility_text


def test_control_loop_and_quorum_use_generic_agent_decision_helper() -> None:
    control_text = (ROOT / "runtime/swarm/control_loop.py").read_text(encoding="utf-8")
    quorum_text = (ROOT / "runtime/swarm/quorum.py").read_text(encoding="utf-8")
    helper_text = (ROOT / "runtime/swarm/agent_decisions.py").read_text(encoding="utf-8")
    state_text = (ROOT / "runtime/state.py").read_text(encoding="utf-8")

    assert "committee_decision" not in control_text
    assert "committee_decision" not in quorum_text
    assert "runtime_agent_decision(" in control_text
    assert "runtime_agent_decision(" in quorum_text
    assert "state_with_agent_decision(" in control_text
    assert "agent_decision:" in state_text
    assert "agent_outputs:" in state_text
    assert "committee_decision" in helper_text


def test_evidence_graph_uses_generic_agent_decision_helper() -> None:
    graph_text = (ROOT / "runtime/swarm/evidence_graph.py").read_text(encoding="utf-8")
    helper_text = (ROOT / "runtime/swarm/agent_decisions.py").read_text(encoding="utf-8")

    assert "committee_decision" not in graph_text
    assert "runtime_agent_decision(" in graph_text
    assert "runtime_agent_decision_source(" in graph_text
    assert '"decision_source"' in graph_text
    assert "committee_decision" in helper_text


def test_graph_model_contexts_use_generic_agent_state() -> None:
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")
    helper_text = (ROOT / "runtime/swarm/agent_decisions.py").read_text(encoding="utf-8")

    assert 'result.get("committee_decision")' not in graph_text
    assert 'state.get("committee_decision")' not in graph_text
    assert "legacy_committee_decision(" in graph_text
    assert "def legacy_committee_decision(" in helper_text

    for name in ("critic_context", "writer_context", "final_judge_context"):
        match = re.search(
            rf"def {name}\(state: AgentState\) -> str:\n(?P<body>.*?)(?=\n\ndef |\Z)",
            graph_text,
            re.DOTALL,
        )
        assert match is not None
        body = match.group("body")

        assert '"committee_outputs"' not in body
        assert '"committee_decision"' not in body
        assert '"agent_outputs"' in body
        assert '"agent_decision"' in body
        assert '"legacy_agent_outputs"' in body
        assert '"legacy_agent_decision"' in body


def test_shared_swarm_contract_text_uses_generic_agent_proposal_wording() -> None:
    shared_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "runtime/swarm/evidence_graph.py",
            "runtime/swarm/signal_verifier.py",
        )
    )

    assert "committee proposals" not in shared_text
    assert "Verified committee stop-signal proposal" not in shared_text
    assert "agent proposals" in shared_text
    assert "Verified agent stop-signal proposal" in shared_text


def test_preflight_and_memory_nodes_are_runtime_node_owned() -> None:
    preflight_text = (ROOT / "runtime/nodes/preflight.py").read_text(encoding="utf-8")
    memory_text = (ROOT / "runtime/nodes/memory.py").read_text(encoding="utf-8")
    graph_text = (ROOT / "runtime/graph.py").read_text(encoding="utf-8")

    assert "async def patroller_gate_node" in preflight_text
    assert "async def memory_agent_node" in memory_text

    patroller_method = re.search(
        r"async def _patroller_gate\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _memory_agent",
        graph_text,
        re.DOTALL,
    )
    memory_method = re.search(
        r"async def _memory_agent\(self, state: AgentState\) -> AgentState:\n(?P<body>.*?)\n    async def _wrds_agent",
        graph_text,
        re.DOTALL,
    )
    assert patroller_method is not None
    assert memory_method is not None
    assert "patroller_gate_node(self, state)" in patroller_method.group("body")
    assert "memory_agent_node(self, state)" in memory_method.group("body")
    assert "build_patroller_report(state)" not in patroller_method.group("body")
    assert "build_memory_context" not in memory_method.group("body")
