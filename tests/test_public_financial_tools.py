from __future__ import annotations

import io
import zipfile

from runtime.tool_registry import ToolRegistry
from tools.public_financial_tools import (
    PublicFinancialDataTools,
    normalize_cik,
    parse_kenneth_french_zip,
    rank_sec_company_matches,
)


def test_sec_company_matching_and_cik_normalization() -> None:
    rows = [
        {"ticker": "AAPL", "title": "Apple Inc.", "cik_str": 320193},
        {"ticker": "MSFT", "title": "Microsoft Corp", "cik_str": "789019"},
    ]

    matches = rank_sec_company_matches(rows, "AAPL")

    assert matches[0]["ticker"] == "AAPL"
    assert matches[0]["cik"] == "0000320193"
    assert normalize_cik("CIK 789019") == "0000789019"


def test_kenneth_french_zip_parser_extracts_factor_rows() -> None:
    csv_text = """This file was created by CMPT_ME_BEME_RETS
,Mkt-RF,SMB,HML,RF
192607,2.96,-2.30,-2.87,0.22
192608,2.64,-1.40,4.19,0.25

Annual Factors: January-December
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("F-F_Research_Data_Factors.csv", csv_text)

    rows = parse_kenneth_french_zip(buffer.getvalue(), max_rows=10)

    assert rows == [
        {"date": 192607, "Mkt-RF": 2.96, "SMB": -2.3, "HML": -2.87, "RF": 0.22},
        {"date": 192608, "Mkt-RF": 2.64, "SMB": -1.4, "HML": 4.19, "RF": 0.25},
    ]


def test_fred_tool_requires_connection_before_secret_use() -> None:
    registry = ToolRegistry(
        permission_grants=["data:read", "network:approved-provider"],
        allowed_tool_names=["fred_series", "sec_company_search"],
        public_financial_tools=PublicFinancialDataTools(fred_api_key="secret-fred-key"),
    )

    result = registry.run("fred_series", {"series_id": "FEDFUNDS"})

    assert "sec_company_search" in registry.names()
    assert result.ok is False
    assert result.data["missing_connections"] == ["fred"]
    assert "secret-fred-key" not in str(result.to_dict())
