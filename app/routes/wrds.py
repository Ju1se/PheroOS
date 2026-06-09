from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from runtime.tool_registry import ToolRegistry


def require_wrds_api_access(
    authorization: str | None = Header(default=None),
    x_wrds_api_key: str | None = Header(default=None),
) -> None:
    enabled = os.getenv("WRDS_API_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        raise HTTPException(status_code=404, detail="WRDS API is disabled")

    token = os.getenv("WRDS_API_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="WRDS API token is not configured")

    bearer = f"Bearer {token}"
    if x_wrds_api_key == token or authorization == bearer:
        return
    raise HTTPException(status_code=401, detail="WRDS API token required")


router = APIRouter(prefix="/wrds", tags=["wrds"], dependencies=[Depends(require_wrds_api_access)])


class WRDSQueryRequest(BaseModel):
    sql: str = Field(min_length=1)
    max_rows: int = 100


class WRDSTablesRequest(BaseModel):
    library: str = Field(min_length=1)
    pattern: str | None = None
    max_results: int = 200


class WRDSDescribeRequest(BaseModel):
    library: str = Field(min_length=1)
    table: str = Field(min_length=1)
    max_columns: int = 300


class WRDSCapabilityDiscoveryRequest(BaseModel):
    libraries: list[str] = Field(default_factory=list)
    max_tables_per_library: int = 50


class WRDSCompanySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    max_results: int = 8


class WRDSCompanyFinancialsRequest(BaseModel):
    query: str = Field(min_length=1)
    max_years: int = 5
    max_quarters: int = 0
    max_candidates: int = 5
    data_packages: list[str] = Field(default_factory=list)


def run_wrds_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return ToolRegistry(wrds_enabled=True).run(name, args or {}).to_dict()


@router.get("/status")
def wrds_status(check_connection: bool = False) -> dict[str, Any]:
    return run_wrds_tool("wrds_status", {"check_connection": check_connection})


@router.get("/libraries")
def wrds_libraries(pattern: str | None = None, max_results: int = 200) -> dict[str, Any]:
    return run_wrds_tool("wrds_list_libraries", {"pattern": pattern, "max_results": max_results})


@router.post("/tables")
def wrds_tables(request: WRDSTablesRequest) -> dict[str, Any]:
    return run_wrds_tool(
        "wrds_list_tables",
        {"library": request.library, "pattern": request.pattern, "max_results": request.max_results},
    )


@router.post("/describe")
def wrds_describe(request: WRDSDescribeRequest) -> dict[str, Any]:
    return run_wrds_tool(
        "wrds_describe_table",
        {"library": request.library, "table": request.table, "max_columns": request.max_columns},
    )


@router.post("/capabilities")
def wrds_capabilities(request: WRDSCapabilityDiscoveryRequest) -> dict[str, Any]:
    return run_wrds_tool(
        "wrds_capability_discovery",
        {"libraries": request.libraries, "max_tables_per_library": request.max_tables_per_library},
    )


@router.post("/query")
def wrds_query(request: WRDSQueryRequest) -> dict[str, Any]:
    return run_wrds_tool("wrds_query", {"sql": request.sql, "max_rows": request.max_rows})


@router.post("/company/search")
def wrds_company_search(request: WRDSCompanySearchRequest) -> dict[str, Any]:
    return run_wrds_tool("wrds_company_search", {"query": request.query, "max_results": request.max_results})


@router.post("/company/financials")
def wrds_company_financials(request: WRDSCompanyFinancialsRequest) -> dict[str, Any]:
    return run_wrds_tool(
        "wrds_company_financials",
        {
            "query": request.query,
            "max_years": request.max_years,
            "max_quarters": request.max_quarters,
            "max_candidates": request.max_candidates,
            "data_packages": request.data_packages,
        },
    )
