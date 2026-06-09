from __future__ import annotations

from typing import Any, Protocol

from runtime.connection_control import ConnectionControlPlane, wrds_tools_from_candidate
from tools.safe_tools import ToolResult
from tools.wrds_tools import WRDSTools


class FinancialDataSource(Protocol):
    def test_connection(self) -> ToolResult:
        """Return a structured connection test result."""

    def discover_capabilities(self) -> ToolResult:
        """Return source capabilities visible to the configured account."""

    def resolve_company(self, query: str) -> ToolResult:
        """Resolve a company or ticker to source-specific identifiers."""

    def fetch_company_profile(self, query: str) -> ToolResult:
        """Fetch basic company identity/profile data."""

    def fetch_fundamentals(self, query: str, *, data_packages: list[str] | None = None) -> ToolResult:
        """Fetch financial fundamentals and source rows."""

    def fetch_market_data(self, query: str) -> ToolResult:
        """Fetch market data where the source supports it."""

    def fetch_estimates(self, query: str) -> ToolResult:
        """Fetch estimates where the source supports it."""

    def fetch_segments(self, query: str) -> ToolResult:
        """Fetch segment data where the source supports it."""

    def fetch_metric_registry(self, query: str, *, data_packages: list[str] | None = None) -> ToolResult:
        """Fetch data used to build deterministic metric registry entries."""


class WRDSFinancialDataSource:
    """WRDS reference implementation of the FinancialDataSource protocol."""

    def __init__(self, tools: WRDSTools) -> None:
        self.tools = tools

    @classmethod
    def from_connection(
        cls,
        *,
        control_plane: ConnectionControlPlane,
        record: dict[str, Any],
    ) -> "WRDSFinancialDataSource":
        candidate = {
            "id": record.get("id"),
            "tenant_id": record.get("tenant_id"),
            "kind": record.get("kind"),
            "provider": record.get("provider"),
            "provider_key": record.get("provider_key"),
            "endpoint": record.get("endpoint"),
            "payload": {
                "username": control_plane.secret_value(record, "username"),
                "password": control_plane.secret_value(record, "password"),
                "base_url": record.get("endpoint"),
                "database": (record.get("config") or {}).get("database"),
            },
        }
        return cls(wrds_tools_from_candidate(candidate))

    def test_connection(self) -> ToolResult:
        return self.tools.status(check_connection=True)

    def discover_capabilities(self) -> ToolResult:
        return self.tools.capability_discovery(libraries=[], max_tables_per_library=50)

    def resolve_company(self, query: str) -> ToolResult:
        return self.tools.company_search(query=query, max_results=8)

    def fetch_company_profile(self, query: str) -> ToolResult:
        return self.resolve_company(query)

    def fetch_fundamentals(self, query: str, *, data_packages: list[str] | None = None) -> ToolResult:
        return self.tools.company_financials(
            query=query,
            max_years=10,
            max_quarters=16,
            max_candidates=5,
            data_packages=data_packages or [],
        )

    def fetch_market_data(self, query: str) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=["crsp_market_data"])

    def fetch_estimates(self, query: str) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=["ibes_estimates"])

    def fetch_segments(self, query: str) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=["compustat_segments"])

    def fetch_metric_registry(self, query: str, *, data_packages: list[str] | None = None) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=data_packages)


class GenericFinancialAPIDataSource:
    """Capability placeholder for user-supplied financial APIs.

    Adapters such as FMP, AlphaVantage, Polygon, and EODHD should implement the
    same FinancialDataSource protocol and can be registered without changing the
    investment committee workflow.
    """

    def __init__(self, *, provider: str, endpoint: str) -> None:
        self.provider = provider
        self.endpoint = endpoint

    def test_connection(self) -> ToolResult:
        return ToolResult(False, {"provider": self.provider, "endpoint": self.endpoint}, "generic financial adapter is not implemented")

    def discover_capabilities(self) -> ToolResult:
        return ToolResult(True, {"provider": self.provider, "capabilities": [], "status": "adapter_pending"})

    def resolve_company(self, query: str) -> ToolResult:
        return ToolResult(False, {"query": query}, "generic financial adapter is not implemented")

    def fetch_company_profile(self, query: str) -> ToolResult:
        return self.resolve_company(query)

    def fetch_fundamentals(self, query: str, *, data_packages: list[str] | None = None) -> ToolResult:
        return ToolResult(False, {"query": query, "data_packages": data_packages or []}, "generic financial adapter is not implemented")

    def fetch_market_data(self, query: str) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=["market_prices"])

    def fetch_estimates(self, query: str) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=["estimates"])

    def fetch_segments(self, query: str) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=["segments"])

    def fetch_metric_registry(self, query: str, *, data_packages: list[str] | None = None) -> ToolResult:
        return self.fetch_fundamentals(query, data_packages=data_packages)
