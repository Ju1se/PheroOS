from __future__ import annotations

import json
from typing import Any

from runtime.agent_metrics import metric_started_at, record_agent_metric
from runtime.data_sources import DataProviderDescriptor, DataSourceResult
from runtime.research_selection import selected_skills_request_direct_wrds_data
from runtime.state import AgentState


WRDS_CAPABILITY_ID = "wrds-financial-data"
WRDS_PROVIDER_ID = "wrds"


def build_data_provider_descriptor() -> dict[str, Any]:
    """Expose WRDS as a generic data-provider adapter descriptor."""

    return DataProviderDescriptor(
        provider_id=WRDS_PROVIDER_ID,
        capability_id=WRDS_CAPABILITY_ID,
        source_kind="professional_database",
        dataset_kind="financial_fundamentals",
        coverage={
            "scope": "Provider-visible WRDS libraries such as Compustat, CRSP, IBES, and segment datasets.",
            "tenant_dependent": True,
        },
        freshness={"policy": "provider_controlled", "reported_by_adapter": True},
        license={
            "kind": "restricted",
            "name": "WRDS institutional license",
            "raw_data_publication": "prohibited_by_runtime_output_policy",
        },
        reliability_level="licensed_provider",
        adapter_entrypoint="runtime_nodes.py:build_data_provider_descriptor",
        required_connections=[WRDS_PROVIDER_ID],
        required_permissions=["network:wrds", "secret:wrds", "data:read", "tool:deterministic-read"],
        tools=[
            "wrds_status",
            "wrds_capability_discovery",
            "wrds_company_search",
            "wrds_company_financials",
        ],
        data_packages=[
            "company_identity",
            "annual_financials_10y",
            "quarterly_financials_16q",
            "cash_flow_capex",
            "balance_sheet_debt",
            "inventory_working_capital",
            "valuation_snapshot",
        ],
        provenance_policy={
            "include_tool_name": True,
            "include_table_names": True,
            "include_row_counts": True,
            "exclude_raw_rows_from_public_results": True,
        },
        adapter_metadata={
            "legacy_alias": "wrds_result",
            "adapter_boundary": "capability_runtime_node",
        },
    ).to_dict()


def build_runtime_node_descriptor() -> dict[str, Any]:
    """Expose WRDS-owned runtime nodes to the capability runtime catalog."""

    return {
        "nodes": {
            "wrds_agent": "capabilities/wrds-financial-data/runtime_nodes.py:wrds_agent_node",
        },
        "result_collectors": {
            "wrds_result": "runtime_nodes.py:collect_wrds_results",
        },
        "argument_normalizers": {
            "wrds_company_search": "runtime_nodes.py:normalize_wrds_company_tool_args",
            "wrds_company_financials": "runtime_nodes.py:normalize_wrds_company_tool_args",
        },
        "routing": {
            "should_run_node": "runtime_nodes.py:should_run_wrds_agent",
            "should_bypass_graph": "runtime_nodes.py:should_bypass_graph_to_wrds",
            "direct_orchestration": "runtime_nodes.py:build_direct_wrds_orchestration",
        },
        "contracts": {
            "secrets": "connection_handle_only",
            "tools": "tool_registry_only",
            "model_calls": "gateway_only",
            "source_mode": "wrds_only_for_investment",
        },
    }


def normalize_wrds_action(plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    action = str(plan.get("action") or "status").strip().lower().replace("-", "_")
    if action in {"company_search", "search_company", "resolve_company"}:
        return "wrds_company_search", {
            "query": str(plan.get("query") or plan.get("company") or plan.get("pattern") or ""),
            "max_results": plan.get("max_results") or 8,
        }
    if action in {"company_financials", "company_fundamentals", "financials", "fundamentals"}:
        return "wrds_company_financials", {
            "query": str(plan.get("query") or plan.get("company") or plan.get("pattern") or ""),
            "max_years": plan.get("max_years") or 10,
            "max_quarters": plan.get("max_quarters") or plan.get("quarters") or 16,
            "max_candidates": plan.get("max_candidates") or 5,
            "data_packages": plan.get("data_packages") or plan.get("packages") or [],
        }
    if action in {"query", "sql", "run_query"}:
        return "wrds_query", {"sql": str(plan.get("sql") or ""), "max_rows": plan.get("max_rows") or 100}
    if action in {"list_libraries", "libraries", "schemas", "list_schemas"}:
        return "wrds_list_libraries", {
            "pattern": _empty_to_none(plan.get("pattern")),
            "max_results": plan.get("max_results") or 200,
        }
    if action in {"list_tables", "tables"}:
        library = _empty_to_none(plan.get("library"))
        if not library:
            return "wrds_list_libraries", {"pattern": _empty_to_none(plan.get("pattern")), "max_results": 200}
        return "wrds_list_tables", {
            "library": library,
            "pattern": _empty_to_none(plan.get("pattern")),
            "max_results": plan.get("max_results") or 200,
        }
    if action in {"describe", "describe_table", "columns"}:
        library = _empty_to_none(plan.get("library"))
        table = _empty_to_none(plan.get("table"))
        if not library or not table:
            return "wrds_list_libraries", {"pattern": _empty_to_none(plan.get("pattern")), "max_results": 200}
        return "wrds_describe_table", {
            "library": library,
            "table": table,
            "max_columns": plan.get("max_columns") or 300,
        }
    if action in {"capability_discovery", "capabilities", "discover_capabilities", "discover"}:
        libraries = plan.get("libraries")
        if isinstance(libraries, str):
            libraries = [item.strip() for item in libraries.split(",") if item.strip()]
        return "wrds_capability_discovery", {
            "libraries": libraries if isinstance(libraries, list) else [],
            "max_tables_per_library": plan.get("max_tables_per_library") or 50,
        }
    return "wrds_status", {"check_connection": _parse_bool_value(plan.get("check_connection"), True)}


def render_wrds_final(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    result: dict[str, Any],
    plan: dict[str, Any],
) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if not result.get("ok"):
        return (
            "WRDS Agent 未能完成数据获取。\n\n"
            f"- 动作：`{tool_name}`\n"
            f"- 错误：{result.get('error') or 'unknown error'}\n"
            "- 说明：WRDS Agent 只执行只读数据检索，不做投资判断。"
        )

    if tool_name == "wrds_query":
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        columns = data.get("columns") if isinstance(data.get("columns"), list) else []
        table = render_markdown_table(rows, columns)
        return (
            "WRDS Agent 已完成只读查询。\n\n"
            f"- 行数：{data.get('row_count', 0)}\n"
            f"- 截断：{data.get('truncated', False)}\n"
            f"- SQL：`{data.get('sql_preview', '')}`\n\n"
            f"{table}"
        )
    if tool_name == "wrds_company_search":
        candidates = data.get("candidates") if isinstance(data.get("candidates"), list) else []
        rows = [
            {
                "source": row.get("source"),
                "gvkey": row.get("gvkey"),
                "tic": row.get("tic"),
                "conm": row.get("conm"),
                "score": row.get("match_score"),
            }
            for row in candidates
        ]
        return (
            f"WRDS Agent 已完成公司匹配：`{data.get('query')}`\n\n"
            f"{render_markdown_table(rows, ['source', 'gvkey', 'tic', 'conm', 'score'])}"
        )
    if tool_name == "wrds_company_financials":
        company = data.get("company") if isinstance(data.get("company"), dict) else {}
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        quarterly_rows = data.get("quarterly_rows") if isinstance(data.get("quarterly_rows"), list) else []
        if not company:
            return (
                "WRDS Agent 未在 WRDS 中匹配到公司。\n\n"
                f"- 查询：`{data.get('query')}`\n"
                f"- 状态：`{data.get('status')}`\n"
                "- 说明：可以尝试提供英文公司名、ticker、gvkey、CUSIP 或交易所代码。"
            )
        visible = []
        for row in rows:
            calculated = row.get("calculated") if isinstance(row.get("calculated"), dict) else {}
            visible.append(
                {
                    "fyear": row.get("fyear"),
                    "date": row.get("datadate"),
                    "sale": row.get("sale") or row.get("revt"),
                    "ni": row.get("ni") or row.get("ib"),
                    "at": row.get("at"),
                    "gross_margin": calculated.get("gross_margin"),
                    "net_margin": calculated.get("net_margin"),
                    "fcf": calculated.get("free_cash_flow"),
                }
            )
        return (
            "WRDS Agent 已获取公司专业数据包。\n\n"
            f"- 匹配公司：`{company.get('conm')}`\n"
            f"- GVKEY：`{company.get('gvkey')}`\n"
            f"- Ticker：`{company.get('tic')}`\n"
            f"- 数据表：`{data.get('table')}`\n"
            f"- 季度数据表：`{data.get('quarterly_table') or 'not fetched'}`\n"
            f"- 年度行数：`{len(rows)}`\n"
            f"- 季度行数：`{len(quarterly_rows)}`\n"
            f"- 数据包：`{', '.join(data.get('data_packages') or []) or 'default'}`\n"
            f"- 状态：`{data.get('status')}`\n\n"
            f"{render_markdown_table(visible, ['fyear', 'date', 'sale', 'ni', 'at', 'gross_margin', 'net_margin', 'fcf'])}"
        )
    if tool_name == "wrds_list_libraries":
        libraries = data.get("libraries") if isinstance(data.get("libraries"), list) else []
        return "WRDS Agent 已列出可用 libraries/schemas：\n\n" + "\n".join(f"- `{name}`" for name in libraries[:200])
    if tool_name == "wrds_list_tables":
        tables = data.get("tables") if isinstance(data.get("tables"), list) else []
        return (
            f"WRDS Agent 已列出 `{data.get('library')}` 的 tables：\n\n"
            + "\n".join(f"- `{row.get('table_name')}` ({row.get('table_type')})" for row in tables[:200])
        )
    if tool_name == "wrds_describe_table":
        columns = data.get("columns") if isinstance(data.get("columns"), list) else []
        rows = [{"column": row.get("column_name"), "type": row.get("data_type")} for row in columns]
        return f"WRDS Agent 已读取 `{data.get('library')}.{data.get('table')}` 的字段：\n\n{render_markdown_table(rows, ['column', 'type'])}"
    if tool_name == "wrds_capability_discovery":
        capabilities = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
        rows = []
        for name, payload in capabilities.items():
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "capability": name,
                    "available": payload.get("available"),
                    "libraries": ", ".join(payload.get("libraries") or []),
                    "tables": payload.get("table_count"),
                }
            )
        return (
            "WRDS Agent 已完成 capability discovery。\n\n"
            f"- 可见 library 数：`{data.get('library_count', 0)}`\n"
            f"- 缺失 capability：`{', '.join(data.get('missing_capabilities') or []) or 'none'}`\n\n"
            f"{render_markdown_table(rows, ['capability', 'available', 'libraries', 'tables'])}"
        )

    return (
        "WRDS Agent 状态：\n\n"
        f"- configured: `{data.get('configured')}`\n"
        f"- host: `{data.get('host')}`\n"
        f"- database: `{data.get('dbname')}`\n"
        f"- connection: `{data.get('connection', 'not checked')}`"
    )


def render_markdown_table(rows: list[dict[str, Any]], columns: list[str], *, limit: int = 20) -> str:
    if not columns:
        return "_No rows returned._"
    visible_rows = rows[:limit]
    header = "| " + " | ".join(str(col) for col in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in visible_rows:
        body.append("| " + " | ".join(_escape_table_cell(row.get(col, "")) for col in columns) + " |")
    suffix = "\n\n_Only first 20 rows shown in chat output._" if len(rows) > limit else ""
    return "\n".join([header, divider, *body]) + suffix


def collect_wrds_results(execution_log: list[dict[str, Any]]) -> dict[str, Any]:
    calls = []
    data_source_results = []
    company_financials = None
    company_search = None
    capability_discovery = None
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or "")
            if not name.startswith("wrds_"):
                continue
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            data_source_results.append(wrds_data_source_result(name, result))
            calls.append(
                {
                    "step_id": step.get("step_id"),
                    "name": name,
                    "ok": result.get("ok"),
                    "error": result.get("error"),
                    "status": data.get("status"),
                    "row_count": data.get("row_count"),
                    "quarterly_row_count": data.get("quarterly_row_count"),
                    "company": data.get("company"),
                    "table": data.get("table"),
                    "quarterly_table": data.get("quarterly_table"),
                    "data_packages": data.get("data_packages"),
                    "sql_preview": data.get("sql_preview"),
                }
            )
            if name == "wrds_company_financials":
                company_financials = data
            elif name == "wrds_company_search":
                company_search = data
            elif name == "wrds_capability_discovery":
                capability_discovery = data

    if not calls:
        return {}
    return {
        "ok": all(call.get("ok") is not False for call in calls),
        "data_source_results": data_source_results,
        "provider_results": data_source_results,
        "data": {
            "tool_calls": calls,
            "company_financials": company_financials,
            "company_search": company_search,
            "capability_discovery": capability_discovery,
            "data_source_results": data_source_results,
        },
        "result_collector_trace": [
            {
                "capability_id": WRDS_CAPABILITY_ID,
                "collector": "wrds_result",
                "source": "capability_result_collector",
                "status": "executed",
            }
        ],
    }


def wrds_data_source_result(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    company = data.get("company") if isinstance(data.get("company"), dict) else {}
    normalized_payload = {
        "status": data.get("status"),
        "tool_name": tool_name,
        "company": public_company_identity(company),
        "row_count": data.get("row_count"),
        "quarterly_row_count": data.get("quarterly_row_count"),
        "table": data.get("table"),
        "quarterly_table": data.get("quarterly_table"),
        "data_packages": data.get("data_packages") if isinstance(data.get("data_packages"), list) else [],
        "truncated": data.get("truncated"),
    }
    return DataSourceResult(
        provider_id=WRDS_PROVIDER_ID,
        source_kind="professional_database",
        dataset_kind=wrds_dataset_kind(tool_name),
        normalized_payload={key: value for key, value in normalized_payload.items() if value not in (None, [], {})},
        provenance={
            "capability_id": WRDS_CAPABILITY_ID,
            "provider_id": WRDS_PROVIDER_ID,
            "tool_name": tool_name,
            "tool_boundary": "ToolRegistry",
            "table": data.get("table"),
            "quarterly_table": data.get("quarterly_table"),
        },
        coverage={
            "company_matched": bool(company),
            "row_count": data.get("row_count"),
            "quarterly_row_count": data.get("quarterly_row_count"),
        },
        freshness={
            "latest_annual_period": latest_period(data.get("rows"), "fyear"),
            "latest_quarterly_period": latest_period(data.get("quarterly_rows"), "datadate"),
        },
        license={
            "kind": "restricted",
            "name": "WRDS institutional license",
            "raw_data_publication": "prohibited_by_runtime_output_policy",
        },
        adapter_metadata={
            "legacy_alias": "wrds_result",
            "raw_rows_excluded": True,
        },
        ok=bool(result.get("ok")),
        errors=[str(result.get("error"))] if result.get("error") else [],
    ).to_dict()


def wrds_dataset_kind(tool_name: str) -> str:
    if tool_name == "wrds_company_financials":
        return "financial_fundamentals"
    if tool_name == "wrds_company_search":
        return "company_identity"
    if tool_name == "wrds_capability_discovery":
        return "provider_capability_discovery"
    if tool_name == "wrds_query":
        return "provider_query"
    return "provider_status"


def public_company_identity(company: dict[str, Any]) -> dict[str, Any]:
    keys = ("gvkey", "tic", "conm", "cusip", "cik", "lpermno", "lpermco")
    return {key: company.get(key) for key in keys if company.get(key) is not None}


def latest_period(rows: Any, key: str) -> Any:
    if not isinstance(rows, list):
        return None
    values = [row.get(key) for row in rows if isinstance(row, dict) and row.get(key) is not None]
    return max(values, key=lambda item: str(item)) if values else None


def normalize_wrds_company_tool_args(
    args: dict[str, Any],
    *,
    state: dict[str, Any],
    step: dict[str, Any] | None = None,
    tool_name: str,
) -> dict[str, Any]:
    from runtime.wrds_company_planner import normalize_wrds_company_tool_args as normalize

    return normalize(args, state=state, step=step, tool_name=tool_name)


def should_run_wrds_agent(state: dict[str, Any]) -> bool:
    orchestration = state.get("orchestration") if isinstance(state.get("orchestration"), dict) else {}
    if orchestration.get("task_type") == "wrds":
        return True
    if selected_skills_request_direct_wrds_data(list(state.get("selected_skills", []) or [])):
        return True
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    return bool(metadata.get("wrds_sql") or metadata.get("wrds_action"))


def should_bypass_graph_to_wrds(*, task: str, metadata: dict[str, Any], skills: list[Any]) -> bool:
    if metadata.get("wrds_sql") or metadata.get("wrds_action"):
        return True
    if task.strip().lower().startswith(("select ", "with ")):
        return True
    return selected_skills_request_direct_wrds_data(list(skills))


def build_direct_wrds_orchestration() -> dict[str, Any]:
    return {
        "task_type": "wrds",
        "depth": "shallow",
        "committee": False,
        "required_agents": {
            "memory": False,
            "wrds": True,
            "research": False,
            "quant": False,
            "domain": False,
            "critic": False,
            "writer": False,
            "final_judge": False,
        },
        "rationale": "Explicit WRDS data retrieval request; bypassing the general multi-agent workflow.",
        "routing_source": "capability_runtime_routing",
    }


def redact_wrds_args(args: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(args)
    if "password" in redacted:
        redacted["password"] = "[redacted]"
    return redacted


def _escape_table_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")[:240]


def _empty_to_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _skipped_analysis(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": reason}


async def wrds_agent_node(runtime: Any, state: AgentState) -> AgentState:
    """Capability-owned direct WRDS retrieval node.

    The core graph may route to this node, but all WRDS retrieval policy lives
    in this capability. The node still uses the runtime ToolRegistry and model
    gateway only; it never receives or returns WRDS credentials.
    """

    started_at = metric_started_at()
    plan = await plan_wrds_action(runtime, state)
    tool_name, tool_args = normalize_wrds_action(plan)
    result = runtime.tool_registry.run(tool_name, tool_args)
    result_payload = result.to_dict()
    data_source_result = wrds_data_source_result(tool_name, result_payload)
    status = "completed" if result.ok else "completed_with_tool_failure"
    if result.ok and plan.get("_model_fallback_reason"):
        status = "completed_with_fallback"
    record_agent_metric(
        agent="wrds_agent",
        model=str(plan.get("_model_name") or runtime.model_config.wrds_agent),
        started_at=started_at,
        status=status,
        failure_reason=result.error or plan.get("_model_fallback_reason"),
        model_used=bool(plan.get("_model_used")),
    )
    final = render_wrds_final(
        tool_name=tool_name,
        tool_args=tool_args,
        result=result_payload,
        plan=plan,
    )
    return {
        "route": "wrds",
        "wrds_result": result_payload,
        "data_source_results": [data_source_result],
        "provider_results": [data_source_result],
        "execution_log": [
            {
                "step_id": "wrds",
                "title": "WRDS data retrieval",
                "status": "completed" if result.ok else "failed",
                "tool_calls": [
                    {
                        "index": 0,
                        "name": tool_name,
                        "args": redact_wrds_args(tool_args),
                        "result": result_payload,
                    }
                ],
            }
        ],
        "research_brief": _skipped_analysis("WRDS agent handled this data retrieval directly"),
        "quant_analysis": _skipped_analysis("WRDS agent only retrieved data; no quant analysis performed"),
        "domain_analysis": _skipped_analysis("WRDS agent does not make investment judgments"),
        "agent_outputs": {},
        "committee_outputs": {},
        "discussion_transcript": [],
        "agent_decision": _skipped_analysis("WRDS agent only retrieved data; no agent decision produced"),
        "committee_decision": _skipped_analysis("WRDS agent does not run an investment committee"),
        "review": {"status": "skipped", "issues": [], "summary": "WRDS data retrieval only."},
        "draft_final": final,
        "final": final,
    }


async def plan_wrds_action(runtime: Any, state: AgentState) -> dict[str, Any]:
    """Plan a single safe WRDS action through the model gateway when needed."""

    from runtime import graph as graph_runtime

    metadata = state.get("metadata", {})
    if metadata.get("wrds_sql"):
        return {
            "action": "query",
            "sql": metadata["wrds_sql"],
            "max_rows": metadata.get("max_rows", 100),
            "_model_used": False,
        }
    if metadata.get("wrds_action"):
        return {
            "action": metadata.get("wrds_action"),
            "library": metadata.get("library"),
            "table": metadata.get("table"),
            "pattern": metadata.get("pattern"),
            "max_rows": metadata.get("max_rows", 100),
            "max_results": metadata.get("max_results", 200),
            "max_years": metadata.get("max_years", 5),
            "max_candidates": metadata.get("max_candidates", 5),
            "check_connection": metadata.get("check_connection", False),
            "_model_used": False,
        }

    raw_task = state["task"].strip()
    if raw_task.lower().startswith(("select ", "with ")):
        return {"action": "query", "sql": raw_task, "max_rows": 100, "_model_used": False}

    try:
        content, model_used, fallback_reason = await runtime._chat_with_fallback(
            primary_model=runtime.model_config.wrds_agent,
            fallback_model=None,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the single WRDS Agent. Your only job is to retrieve professional data "
                        "from WRDS by choosing one safe action. Do not provide investment advice. "
                        "Return strict JSON only with keys: action, library, table, pattern, sql, "
                        "max_rows, max_results, max_years, max_candidates, libraries, max_tables_per_library, "
                        "check_connection, rationale. "
                        "action must be one of status, list_libraries, list_tables, describe_table, query, "
                        "company_search, company_financials, capability_discovery. For a company name or ticker, prefer "
                        "company_financials instead of writing SQL. SQL must be read-only SELECT/WITH and "
                        "should include explicit schema.table names."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": state["task"],
                            "metadata": metadata,
                            "available_wrds_tools": [
                                tool
                                for tool in runtime.tool_registry.manifest()
                                if str(tool.get("name", "")).startswith("wrds_")
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        payload = graph_runtime.parse_optional_json(content) or {}
        if str(payload.get("action") or "").strip().lower().replace("-", "_") in {
            "company_search",
            "search_company",
            "resolve_company",
            "company_financials",
            "company_fundamentals",
            "financials",
            "fundamentals",
        } and not (payload.get("query") or payload.get("company") or payload.get("pattern")):
            payload["query"] = graph_runtime.extract_company_query(raw_task)
        payload["_model_used"] = True
        payload["_model_name"] = model_used
        payload["_model_fallback_reason"] = str(fallback_reason) if fallback_reason else None
        return payload
    except Exception:
        return {"action": "status", "check_connection": True, "_model_used": False}
