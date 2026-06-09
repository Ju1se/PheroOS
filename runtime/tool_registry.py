from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from runtime.permission_policy import flatten_permission_grants, is_permission_granted
from runtime.ports import ProviderWebSearchCallable
from runtime.tool_names import (
    APPROVED_SOURCE_FETCH_TOOL_NAME,
    FETCH_URL_TOOL_NAME,
    PROVIDER_WEB_SEARCH_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
)
from tools.public_financial_tools import PublicFinancialDataTools
from tools.safe_tools import ToolResult, WorkspaceTools
from tools.web_tools import WebTools
from tools.wrds_tools import WRDSTools


ToolCallable = Callable[..., ToolResult]


class ToolRegistry:
    def __init__(
        self,
        *,
        workspace_root: str | Path = ".",
        provider_web_search: ProviderWebSearchCallable | None = None,
        provider_web_search_enabled: bool = False,
        wrds_enabled: bool | None = None,
        wrds_tools: WRDSTools | None = None,
        public_financial_tools: PublicFinancialDataTools | None = None,
        permission_grants: list[dict[str, Any]] | list[str] | set[str] | None = None,
        active_connections: list[str] | set[str] | None = None,
        allowed_tool_names: list[str] | set[str] | None = None,
        extra_tools: dict[str, ToolCallable] | None = None,
        extra_tool_manifest: list[dict[str, Any]] | None = None,
    ) -> None:
        self.workspace_tools = WorkspaceTools(workspace_root)
        self.web_tools = WebTools()
        self.wrds_tools = wrds_tools or WRDSTools()
        self.public_financial_tools = public_financial_tools or PublicFinancialDataTools()
        self.provider_web_search = provider_web_search
        self.provider_web_search_enabled = provider_web_search_enabled or provider_web_search is not None
        self.wrds_enabled = self._resolve_wrds_enabled(wrds_enabled)
        self.permission_grants = flatten_permission_grants(permission_grants)
        self.active_connections = normalize_connection_keys(active_connections)
        self.allowed_tool_names = normalize_tool_names(allowed_tool_names)
        if self.wrds_enabled:
            self.active_connections.update({"wrds"})
        if self.provider_web_search_enabled:
            self.active_connections.update({"model-provider", "model_provider"})
        self._extra_tool_manifest = list(extra_tool_manifest or [])
        self._tool_specs: dict[str, dict[str, Any]] = self._default_tool_specs()
        self._tools: dict[str, ToolCallable] = {
            "list_files": self.workspace_tools.list_files,
            "read_file": self.workspace_tools.read_file,
            "write_file": self.workspace_tools.write_file,
            "run_pytest": self.workspace_tools.run_pytest,
            WEB_SEARCH_TOOL_NAME: self.web_tools.web_search,
            FETCH_URL_TOOL_NAME: self.web_tools.fetch_url,
            APPROVED_SOURCE_FETCH_TOOL_NAME: self.web_tools.approved_source_fetch,
            "sec_company_search": self.public_financial_tools.sec_company_search,
            "sec_company_facts": self.public_financial_tools.sec_company_facts,
            "sec_recent_filings": self.public_financial_tools.sec_recent_filings,
            "fred_series": self.public_financial_tools.fred_series,
            "market_price_history": self.public_financial_tools.market_price_history,
            "kenneth_french_factors": self.public_financial_tools.kenneth_french_factors,
        }
        if self.wrds_enabled:
            self._tools.update(
                {
                    "wrds_status": self.wrds_tools.status,
                    "wrds_list_libraries": self.wrds_tools.list_libraries,
                    "wrds_list_tables": self.wrds_tools.list_tables,
                    "wrds_describe_table": self.wrds_tools.describe_table,
                    "wrds_capability_discovery": self.wrds_tools.capability_discovery,
                    "wrds_query": self.wrds_tools.query,
                    "wrds_company_search": self.wrds_tools.company_search,
                    "wrds_company_financials": self.wrds_tools.company_financials,
                }
            )
        if extra_tools:
            overlapping = sorted(set(extra_tools).intersection(self._tools))
            if overlapping:
                raise ValueError(f"extra tool names already exist: {', '.join(overlapping)}")
            self._tools.update(extra_tools)
            for item in self._normalized_extra_tool_manifest():
                self._tool_specs[str(item["name"])] = item
        self._apply_tool_allowlist()

    def names(self) -> list[str]:
        names = set(self._tools)
        if self.provider_web_search_enabled and self._tool_allowed(PROVIDER_WEB_SEARCH_TOOL_NAME):
            names.add(PROVIDER_WEB_SEARCH_TOOL_NAME)
        return sorted(names)

    def manifest(self) -> list[dict[str, Any]]:
        return [self._public_tool_spec(name) for name in self.names() if name in self._tool_specs]

    def _normalized_extra_tool_manifest(self) -> list[dict[str, Any]]:
        known = set(self._tools)
        manifests: list[dict[str, Any]] = []
        for item in self._extra_tool_manifest:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name not in known:
                continue
            manifests.append(
                {
                    "name": name,
                    "description": str(item.get("description") or "External extension tool."),
                    "args": item.get("args") if isinstance(item.get("args"), dict) else {},
                    "required_permissions": list(item.get("required_permissions") or item.get("permissions") or []),
                    "required_connections": list(item.get("required_connections") or item.get("connections") or []),
                    "risk_level": str(item.get("risk_level") or "low"),
                }
            )
        return manifests

    def _resolve_wrds_enabled(self, value: bool | None) -> bool:
        if value is not None:
            return value
        return self.wrds_tools.config.configured

    def run(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        if name == PROVIDER_WEB_SEARCH_TOOL_NAME:
            return ToolResult(False, {"name": name}, "provider_web_search is async; use arun")
        if name not in self._tools:
            return ToolResult(False, {"name": name}, f"unknown tool: {name}")
        denied = self._permission_denied_result(name)
        if denied is not None:
            return denied
        connection_denied = self._connection_denied_result(name)
        if connection_denied is not None:
            return connection_denied
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return ToolResult(False, {"name": name, "args": args}, "tool args must be an object")

        try:
            return self._tools[name](**args)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"name": name, "args": args}, str(exc))

    async def arun(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        if name != PROVIDER_WEB_SEARCH_TOOL_NAME:
            return self.run(name, args)
        denied = self._permission_denied_result(name)
        if denied is not None:
            return denied
        connection_denied = self._connection_denied_result(name)
        if connection_denied is not None:
            return connection_denied
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return ToolResult(False, {"name": name, "args": args}, "tool args must be an object")
        if self.provider_web_search is None:
            return ToolResult(False, {"name": name, "args": args}, "provider web search is not configured")
        try:
            data = await self.provider_web_search(**args)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"name": name, "args": args}, str(exc))
        return ToolResult(True, data)

    def _default_tool_specs(self) -> dict[str, dict[str, Any]]:
        specs = {
            "list_files": {
                "name": "list_files",
                "description": "List files under a workspace directory, excluding caches and dependency folders.",
                "args": {"path": "string", "pattern": "string", "max_results": "integer"},
                "required_permissions": ["data:read"],
                "required_connections": [],
                "risk_level": "low",
            },
            "read_file": {
                "name": "read_file",
                "description": "Read a UTF-8 text file inside the workspace.",
                "args": {"path": "string", "max_bytes": "integer"},
                "required_permissions": ["data:read"],
                "required_connections": [],
                "risk_level": "low",
            },
            "write_file": {
                "name": "write_file",
                "description": "Write a UTF-8 text file inside the workspace.",
                "args": {"path": "string", "content": "string", "create_parents": "boolean"},
                "required_permissions": ["filesystem:write"],
                "required_connections": [],
                "risk_level": "high",
            },
            "run_pytest": {
                "name": "run_pytest",
                "description": "Run pytest in the workspace with a safe argv list and timeout.",
                "args": {"args": "list[string]", "timeout_seconds": "integer"},
                "required_permissions": ["shell:execute"],
                "required_connections": [],
                "risk_level": "high",
            },
            WEB_SEARCH_TOOL_NAME: {
                "name": WEB_SEARCH_TOOL_NAME,
                "description": "Search the public web and return result titles, URLs, and snippets. Uses a proxy only when configured.",
                "args": {"query": "string", "max_results": "integer"},
                "required_permissions": ["network:arbitrary"],
                "required_connections": [],
                "risk_level": "medium",
            },
            FETCH_URL_TOOL_NAME: {
                "name": FETCH_URL_TOOL_NAME,
                "description": "Fetch a public http/https URL, reject private network targets, and return extracted text. Uses a proxy only when configured.",
                "args": {"url": "string", "max_bytes": "integer", "extract_text": "boolean"},
                "required_permissions": ["network:arbitrary"],
                "required_connections": [],
                "risk_level": "medium",
            },
            APPROVED_SOURCE_FETCH_TOOL_NAME: {
                "name": APPROVED_SOURCE_FETCH_TOOL_NAME,
                "description": "Fetch full text only for URLs already returned by an approved source-retrieval tool.",
                "args": {"url": "string", "approved_urls": "list[string]", "max_bytes": "integer", "extract_text": "boolean"},
                "required_permissions": ["network:approved-provider", "data:read"],
                "required_connections": [],
                "risk_level": "low",
            },
            PROVIDER_WEB_SEARCH_TOOL_NAME: {
                "name": PROVIDER_WEB_SEARCH_TOOL_NAME,
                "description": (
                    "Use the model provider's native web search capability through LiteLLM and return "
                    "source-aware search evidence. Prefer this for research tasks; fall back to web_search if it fails."
                ),
                "args": {"query": "string", "max_results": "integer"},
                "required_permissions": ["network:approved-provider", "model:chat"],
                "required_connections": ["model-provider"],
                "risk_level": "medium",
            },
            "sec_company_search": {
                "name": "sec_company_search",
                "description": "Resolve a company name, ticker, or CIK using SEC EDGAR's public company ticker index.",
                "args": {"query": "string", "max_results": "integer"},
                "required_permissions": ["data:read", "network:approved-provider"],
                "required_connections": [],
                "risk_level": "low",
            },
            "sec_company_facts": {
                "name": "sec_company_facts",
                "description": "Fetch SEC EDGAR XBRL company facts by query or CIK. Output is raw public filing evidence and must pass Data Gate before valuation use.",
                "args": {"query": "string", "cik": "string"},
                "required_permissions": ["data:read", "network:approved-provider"],
                "required_connections": [],
                "risk_level": "low",
            },
            "sec_recent_filings": {
                "name": "sec_recent_filings",
                "description": "Fetch recent SEC EDGAR filing metadata and primary document URLs by query or CIK.",
                "args": {"query": "string", "cik": "string", "forms": "list[string]", "count": "integer"},
                "required_permissions": ["data:read", "network:approved-provider"],
                "required_connections": [],
                "risk_level": "low",
            },
            "fred_series": {
                "name": "fred_series",
                "description": "Fetch FRED macroeconomic series observations using a configured FRED API key.",
                "args": {"series_id": "string", "start_date": "string", "end_date": "string", "limit": "integer"},
                "required_permissions": ["data:read", "network:approved-provider"],
                "required_connections": ["fred"],
                "risk_level": "low",
            },
            "market_price_history": {
                "name": "market_price_history",
                "description": "Fetch public daily market price history from Stooq, with optional yfinance support when installed.",
                "args": {"symbol": "string", "source": "string", "start_date": "string", "end_date": "string", "interval": "string", "max_rows": "integer"},
                "required_permissions": ["data:read", "network:approved-provider"],
                "required_connections": [],
                "risk_level": "low",
            },
            "kenneth_french_factors": {
                "name": "kenneth_french_factors",
                "description": "Fetch Kenneth French factor research datasets such as F-F_Research_Data_Factors.",
                "args": {"dataset": "string", "max_rows": "integer"},
                "required_permissions": ["data:read", "network:approved-provider"],
                "required_connections": [],
                "risk_level": "low",
            },
        }
        for name, description, args in (
            ("wrds_status", "Check local WRDS credential configuration, optionally testing the WRDS PostgreSQL connection.", {"check_connection": "boolean"}),
            ("wrds_list_libraries", "List WRDS libraries/schemas available to the configured account.", {"pattern": "string", "max_results": "integer"}),
            ("wrds_list_tables", "List tables inside a WRDS library/schema.", {"library": "string", "pattern": "string", "max_results": "integer"}),
            ("wrds_describe_table", "Describe columns for a WRDS table.", {"library": "string", "table": "string", "max_columns": "integer"}),
            ("wrds_capability_discovery", "Discover visible WRDS libraries/tables for Compustat, CRSP, IBES, Compustat Segments, Capital IQ, Audit Analytics, and OptionMetrics.", {"libraries": "list[string]", "max_tables_per_library": "integer"}),
            ("wrds_query", "Run a read-only SELECT/WITH SQL query against WRDS with a hard row limit.", {"sql": "string", "max_rows": "integer"}),
            ("wrds_company_search", "Resolve a company name, ticker, gvkey, CUSIP, or known alias to WRDS company candidates.", {"query": "string", "max_results": "integer"}),
            (
                "wrds_company_financials",
                "Resolve a company and fetch planned annual/quarterly Compustat fundamentals plus calculated ratios.",
                {
                    "query": "string",
                    "max_years": "integer",
                    "max_quarters": "integer",
                    "max_candidates": "integer",
                    "data_packages": "list[string]",
                },
            ),
        ):
            specs[name] = {
                "name": name,
                "description": description,
                "args": args,
                "required_permissions": ["data:read", "network:wrds", "secret:wrds"],
                "required_connections": ["wrds"],
                "risk_level": "low",
            }
        return specs

    def _public_tool_spec(self, name: str) -> dict[str, Any]:
        spec = dict(self._tool_specs[name])
        spec["granted"] = self._tool_granted(name)
        spec["connection_granted"] = self._connection_granted(name)
        return spec

    def _required_permissions(self, name: str) -> list[str]:
        spec = self._tool_specs.get(name) or {}
        return [str(item) for item in spec.get("required_permissions") or []]

    def _required_connections(self, name: str) -> list[str]:
        spec = self._tool_specs.get(name) or {}
        return [str(item) for item in spec.get("required_connections") or []]

    def _tool_granted(self, name: str) -> bool:
        return all(is_permission_granted(permission, self.permission_grants) for permission in self._required_permissions(name))

    def _connection_granted(self, name: str) -> bool:
        return all(connection_satisfied(connection, self.active_connections) for connection in self._required_connections(name))

    def _permission_denied_result(self, name: str) -> ToolResult | None:
        missing = [
            permission
            for permission in self._required_permissions(name)
            if not is_permission_granted(permission, self.permission_grants)
        ]
        if not missing:
            return None
        return ToolResult(
            False,
            {
                "name": name,
                "missing_permissions": missing,
                "permission_required": True,
            },
            f"tool {name} requires explicit permission grant(s): {', '.join(missing)}",
        )

    def _apply_tool_allowlist(self) -> None:
        if self.allowed_tool_names is None:
            return
        self._tools = {
            name: tool
            for name, tool in self._tools.items()
            if self._tool_allowed(name)
        }
        self._tool_specs = {
            name: spec
            for name, spec in self._tool_specs.items()
            if self._tool_allowed(name)
        }

    def _tool_allowed(self, name: str) -> bool:
        return self.allowed_tool_names is None or name in self.allowed_tool_names

    def _connection_denied_result(self, name: str) -> ToolResult | None:
        missing = [
            connection
            for connection in self._required_connections(name)
            if not connection_satisfied(connection, self.active_connections)
        ]
        if not missing:
            return None
        return ToolResult(
            False,
            {
                "name": name,
                "missing_connections": missing,
                "connection_required": True,
            },
            f"tool {name} requires active connection(s): {', '.join(missing)}",
        )


def normalize_connection_keys(value: Any) -> set[str]:
    output: set[str] = set()
    if value is None:
        return output
    if isinstance(value, str):
        text = value.strip()
        return {text} if text else output
    if isinstance(value, dict):
        for key in ("connection", "connection_key", "provider", "kind", "id"):
            output.update(normalize_connection_keys(value.get(key)))
        return {item for item in output if item}
    if isinstance(value, list | tuple | set):
        for item in value:
            output.update(normalize_connection_keys(item))
    return {item for item in output if item}


def normalize_tool_names(value: Any) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, list | tuple | set):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def connection_satisfied(required: str, active: set[str]) -> bool:
    required_text = str(required or "").strip()
    if not required_text:
        return True
    aliases = {
        "model-provider": {"model-provider", "model_provider", "model_provider_connection", "chat_model"},
        "model_provider": {"model-provider", "model_provider", "model_provider_connection", "chat_model"},
        "wrds": {"wrds", "financial_data_source", "professional_financial_database"},
        "fred": {"fred", "financial_data_source", "macro_data"},
    }
    accepted = aliases.get(required_text, {required_text})
    return bool(accepted.intersection(active))
