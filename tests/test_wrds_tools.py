from __future__ import annotations

import pytest

from runtime.skill_loader import SkillLoader
from runtime.tool_registry import ToolRegistry
from tools.wrds_tools import WRDSConfig, WRDSTools, validate_read_only_sql


class FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: list[object] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: list[object] | None = None) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict[str, object]]:
        if "information_schema.schemata" in self.sql:
            return [{"schema_name": "comp"}, {"schema_name": "crsp"}]
        if "information_schema.tables" in self.sql:
            if self.params and "^borrate" in str(self.params[0]):
                return [{"table_name": "borrate2025", "table_type": "BASE TABLE"}]
            if self.params and "^hvold" in str(self.params[0]):
                return [{"table_name": "hvold2025", "table_type": "BASE TABLE"}]
            return [{"table_name": "funda", "table_type": "BASE TABLE"}]
        if "information_schema.columns" in self.sql:
            table = self.params[1] if self.params and len(self.params) > 1 else ""
            if table == "wrds_gvkey":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["companyid", "gvkey", "companyname", "startdate", "enddate", "primaryflag"],
                        start=1,
                    )
                ]
            if table == "ciqcompany":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["companyid", "companyname", "city", "simpleindustryid", "yearfounded", "webpage", "countryid", "stateid"],
                        start=1,
                    )
                ]
            if table == "wrds_ciqsymbol":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["companyid", "companyname", "symbolid", "symboltypename", "symbolvalue", "activeflag", "securityname", "primaryflag", "exchangename", "primaryflag_trd"],
                        start=1,
                    )
                ]
            if table == "ciqbusinessdescription":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(["companyid", "businessdescription"], start=1)
                ]
            if table == "securd":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["secid", "cusip", "ticker", "sic", "index_flag", "exchange_d", "class", "issue_type", "industry_group"],
                        start=1,
                    )
                ]
            if table == "borrate2025":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(["secid", "date", "expirationdate", "days", "borrowrate"], start=1)
                ]
            if table == "hvold2025":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(["secid", "date", "days", "volatility"], start=1)
                ]
            if table == "ccmxpf_linktable":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["gvkey", "linkprim", "liid", "linktype", "lpermno", "lpermco", "usedflag", "linkdt", "linkenddt"],
                        start=1,
                    )
                ]
            if table == "dsf":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["permno", "permco", "date", "prc", "ret", "retx", "vol", "shrout", "cfacpr", "cfacshr"],
                        start=1,
                    )
                ]
            if table == "statsum_epsus":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["ticker", "cusip", "oftic", "cname", "statpers", "measure", "fpi", "numest", "meanest", "fpedats", "actual"],
                        start=1,
                    )
                ]
            if table == "act_epsus":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["ticker", "cusip", "oftic", "cname", "pends", "measure", "anndats", "actdats", "value"],
                        start=1,
                    )
                ]
            if table == "wrds_segmerged":
                return [
                    {"column_name": name, "data_type": "text", "ordinal_position": index}
                    for index, name in enumerate(
                        ["gvkey", "stype", "sid", "snms", "sales", "ops", "oiadps", "atlls", "capxs", "datadate", "srcdate"],
                        start=1,
                    )
                ]
            if table == "fundq":
                return [
                    {"column_name": "gvkey", "data_type": "text", "ordinal_position": 1},
                    {"column_name": "datadate", "data_type": "date", "ordinal_position": 2},
                    {"column_name": "fyearq", "data_type": "integer", "ordinal_position": 3},
                    {"column_name": "fqtr", "data_type": "integer", "ordinal_position": 4},
                    {"column_name": "tic", "data_type": "text", "ordinal_position": 5},
                    {"column_name": "saleq", "data_type": "numeric", "ordinal_position": 6},
                    {"column_name": "cogsq", "data_type": "numeric", "ordinal_position": 7},
                    {"column_name": "gpq", "data_type": "numeric", "ordinal_position": 8},
                    {"column_name": "dpq", "data_type": "numeric", "ordinal_position": 9},
                    {"column_name": "niq", "data_type": "numeric", "ordinal_position": 10},
                    {"column_name": "oancfy", "data_type": "numeric", "ordinal_position": 11},
                    {"column_name": "capxy", "data_type": "numeric", "ordinal_position": 12},
                    {"column_name": "invtq", "data_type": "numeric", "ordinal_position": 13},
                ]
            return [
                {"column_name": "gvkey", "data_type": "text", "ordinal_position": 1},
                {"column_name": "datadate", "data_type": "date", "ordinal_position": 2},
                {"column_name": "fyear", "data_type": "integer", "ordinal_position": 3},
                {"column_name": "tic", "data_type": "text", "ordinal_position": 4},
                {"column_name": "conm", "data_type": "text", "ordinal_position": 5},
                {"column_name": "sale", "data_type": "numeric", "ordinal_position": 6},
                {"column_name": "cogs", "data_type": "numeric", "ordinal_position": 7},
                {"column_name": "gp", "data_type": "numeric", "ordinal_position": 8},
                {"column_name": "dp", "data_type": "numeric", "ordinal_position": 9},
                {"column_name": "ni", "data_type": "numeric", "ordinal_position": 10},
                {"column_name": "at", "data_type": "numeric", "ordinal_position": 11},
                {"column_name": "ceq", "data_type": "numeric", "ordinal_position": 12},
                {"column_name": "oancf", "data_type": "numeric", "ordinal_position": 13},
                {"column_name": "capx", "data_type": "numeric", "ordinal_position": 14},
                {"column_name": "dltt", "data_type": "numeric", "ordinal_position": 15},
                {"column_name": "dlc", "data_type": "numeric", "ordinal_position": 16},
                {"column_name": "che", "data_type": "numeric", "ordinal_position": 17},
                {"column_name": "oibdp", "data_type": "numeric", "ordinal_position": 18},
                {"column_name": "ebitda", "data_type": "numeric", "ordinal_position": 19},
                {"column_name": "prcc_f", "data_type": "numeric", "ordinal_position": 20},
                {"column_name": "csho", "data_type": "numeric", "ordinal_position": 21},
            ]
        if "current_user" in self.sql:
            return [{"user": "demo", "database": "wrds"}]
        if "from comp.names" in self.sql and "comp.g_names" in self.sql:
            return [
                {
                    "source": "comp.names",
                    "gvkey": "001690",
                    "tic": "AAPL",
                    "conm": "APPLE INC",
                    "cusip": "037833100",
                    "cik": "0000320193",
                    "sic": "3571",
                    "naics": "334220",
                    "gind": "452020",
                    "gsubind": "45202030",
                    "year1": 1980,
                    "year2": 2025,
                    "match_score": 100,
                }
            ]
        if "from comp.names n" in self.sql:
            return [
                {
                    "source": "comp.names",
                    "gvkey": "002000",
                    "tic": "MSFT",
                    "conm": "MICROSOFT CORP",
                    "cusip": "594918104",
                    "cik": "0000789019",
                    "sic": "3571",
                    "naics": "334220",
                    "gind": "452020",
                    "gsubind": "45202030",
                    "year1": 1986,
                    "year2": 2025,
                }
            ]
        if "from comp.funda f" in self.sql:
            gvkey = str((self.params or [""])[0])
            if gvkey == "002000":
                return [
                    {
                        "gvkey": "002000",
                        "datadate": "2025-06-30",
                        "fyear": 2025,
                        "tic": "MSFT",
                        "conm": "MICROSOFT CORP",
                        "sale": 281724,
                        "cogs": 90400,
                        "gp": 191324,
                        "dp": 15000,
                        "ni": 101832,
                        "at": 619003,
                        "ceq": 268477,
                        "oancf": 136200,
                        "capx": 44477,
                        "dltt": 43000,
                        "dlc": 6000,
                        "che": 75000,
                        "oibdp": 138000,
                        "prcc_f": 500,
                        "csho": 7400,
                    }
                ]
            return [
                {
                    "gvkey": "001690",
                    "datadate": "2025-09-30",
                    "fyear": 2025,
                    "tic": "AAPL",
                    "conm": "APPLE INC",
                    "sale": 416161,
                    "cogs": 210352,
                    "gp": 205809,
                    "dp": 10000,
                    "ni": 112010,
                    "at": 359241,
                    "ceq": 7332,
                    "oancf": 122000,
                    "capx": 12000,
                    "dltt": 95000,
                    "dlc": 5000,
                    "che": 60000,
                    "oibdp": 130000,
                    "prcc_f": 200,
                    "csho": 16000,
                }
            ]
        if "from comp.fundq f" in self.sql:
            return [
                {
                    "gvkey": "001690",
                    "datadate": "2025-09-30",
                    "fyearq": 2025,
                    "fqtr": 4,
                    "tic": "AAPL",
                    "saleq": 100000,
                    "cogsq": 50000,
                    "gpq": 50000,
                    "dpq": 2000,
                    "niq": 25000,
                    "oancfy": 30000,
                    "capxy": 5000,
                    "invtq": 9000,
                }
            ]
        if "from crsp.ccmxpf_linktable" in self.sql:
            return [
                {
                    "gvkey": "001690",
                    "linkprim": "P",
                    "liid": "01",
                    "linktype": "LC",
                    "lpermno": 14593,
                    "lpermco": 7,
                    "usedflag": 1,
                    "linkdt": "1980-12-12",
                    "linkenddt": None,
                }
            ]
        if "from crsp.dsf" in self.sql:
            return [
                {
                    "permno": 14593,
                    "permco": 7,
                    "date": "2026-05-26",
                    "prc": 200,
                    "ret": 0.01,
                    "retx": 0.01,
                    "vol": 1000000,
                    "shrout": 16000000,
                    "cfacpr": 1,
                    "cfacshr": 1,
                }
            ]
        if "from ciq.wrds_gvkey" in self.sql:
            return [
                {
                    "companyid": 24937,
                    "gvkey": "001690",
                    "companyname": "Apple Inc.",
                    "startdate": None,
                    "enddate": None,
                    "primaryflag": 1,
                }
            ]
        if "from ciq_common.ciqcompany" in self.sql:
            return [
                {
                    "companyid": 24937,
                    "companyname": "Apple Inc.",
                    "city": "Cupertino",
                    "simpleindustryid": 123,
                    "yearfounded": 1976,
                    "webpage": "www.apple.com",
                    "countryid": 213,
                    "stateid": 5,
                }
            ]
        if "from ciq.wrds_ciqsymbol" in self.sql:
            return [
                {
                    "companyid": 24937,
                    "companyname": "Apple Inc.",
                    "symbolid": 1,
                    "symboltypename": "Trading Item Ticker",
                    "symbolvalue": "AAPL",
                    "activeflag": 1,
                    "securityname": "Apple Inc.",
                    "primaryflag": 1,
                    "exchangename": "NasdaqGS",
                    "primaryflag_trd": 1,
                }
            ]
        if "from ciq.ciqbusinessdescription" in self.sql:
            return [{"companyid": 24937, "businessdescription": "Apple designs consumer electronics and services."}]
        if "from optionm.securd" in self.sql:
            return [
                {
                    "secid": 101594,
                    "cusip": "03783310",
                    "ticker": "AAPL",
                    "sic": "3571",
                    "index_flag": "0",
                    "exchange_d": 4,
                    "class": None,
                    "issue_type": "0",
                    "industry_group": None,
                }
            ]
        if "from optionm.borrate2025" in self.sql:
            return [{"secid": 101594, "date": "2025-08-29", "expirationdate": "2025-09-19", "days": 21, "borrowrate": 0.01}]
        if "from optionm.hvold2025" in self.sql:
            return [{"secid": 101594, "date": "2025-08-29", "days": 30, "volatility": 0.20}]
        if "from ibes.statsum_epsus" in self.sql:
            return [
                {
                    "ticker": "AAPL",
                    "cusip": "03783310",
                    "oftic": "AAPL",
                    "cname": "APPLE INC",
                    "statpers": "2026-05-15",
                    "measure": "EPS",
                    "fpi": "1",
                    "numest": 20,
                    "meanest": 8.5,
                    "fpedats": "2026-09-30",
                    "actual": None,
                }
            ]
        if "from ibes.act_epsus" in self.sql:
            return [
                {
                    "ticker": "AAPL",
                    "cusip": "03783310",
                    "oftic": "AAPL",
                    "cname": "APPLE INC",
                    "pends": "2025-09-30",
                    "measure": "EPS",
                    "anndats": "2025-10-30",
                    "actdats": "2025-10-30",
                    "value": 7.0,
                }
            ]
        if "from compseg.wrds_segmerged" in self.sql:
            return [
                {
                    "gvkey": "001690",
                    "stype": "BUSSEG",
                    "sid": "1",
                    "snms": "Products",
                    "sales": 300000,
                    "ops": 90000,
                    "oiadps": 88000,
                    "atlls": 200000,
                    "capxs": 8000,
                    "datadate": "2025-09-30",
                    "srcdate": "2025-10-30",
                }
            ]
        return [{"gvkey": "001690", "datadate": "2024-12-31"}]


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor()


def fake_connection_factory(config: WRDSConfig) -> FakeConnection:
    return FakeConnection()


class CapabilityFakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params: list[object] | None = None

    def __enter__(self) -> "CapabilityFakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: list[object] | None = None) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict[str, object]]:
        if "information_schema.schemata" in self.sql:
            patterns = [str(param).strip("%").lower() for param in (self.params or [])]
            schemas = ["comp", "crsp", "ibes", "compseg", "ciq", "audit", "optionm"]
            return [{"schema_name": schema} for schema in schemas if any(pattern in schema for pattern in patterns)]
        if "information_schema.tables" in self.sql:
            libraries = [str(param) for param in (self.params or []) if str(param) in {"comp", "crsp", "ibes", "compseg", "ciq", "audit", "optionm"}]
            tables_by_library = {
                "comp": ["names", "funda", "fundq"],
                "crsp": ["dsenames", "dsf", "msf"],
                "ibes": ["statsum_epsus", "det_epsus", "actu_epsus"],
                "compseg": ["business_segments", "geographic_segments"],
                "ciq": ["ciqcompany", "ciqfinperiod"],
                "audit": ["audit_fees", "restatements"],
                "optionm": ["opprcd", "securd"],
            }
            rows = []
            for library in libraries:
                rows.extend(
                    {
                        "table_schema": library,
                        "table_name": table,
                        "table_type": "BASE TABLE",
                    }
                    for table in tables_by_library.get(library, [])
                )
            return rows
        return []


class CapabilityFakeConnection:
    def __enter__(self) -> "CapabilityFakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> CapabilityFakeCursor:
        return CapabilityFakeCursor()


def capability_fake_connection_factory(config: WRDSConfig) -> CapabilityFakeConnection:
    return CapabilityFakeConnection()


def test_validate_read_only_sql_rejects_mutations() -> None:
    with pytest.raises(ValueError):
        validate_read_only_sql("drop table comp.funda")

    assert validate_read_only_sql("select * from comp.funda;") == "select * from comp.funda"


def test_wrds_tools_query_uses_row_limit() -> None:
    tools = WRDSTools(
        WRDSConfig(username="user", password="secret"),
        connection_factory=fake_connection_factory,
    )

    result = tools.query(sql="select gvkey, datadate from comp.funda", max_rows=5)

    assert result.ok is True
    assert result.data["row_count"] == 1
    assert result.data["rows"][0]["gvkey"] == "001690"


def test_wrds_tools_query_allows_like_percent_literals() -> None:
    tools = WRDSTools(
        WRDSConfig(username="user", password="secret"),
        connection_factory=fake_connection_factory,
    )

    result = tools.query(sql="select gvkey from comp.company where upper(conm) like '%APPLE%'", max_rows=5)

    assert result.ok is True


def test_wrds_tools_metadata_helpers() -> None:
    tools = WRDSTools(
        WRDSConfig(username="user", password="secret"),
        connection_factory=fake_connection_factory,
    )

    status = tools.status(check_connection=True).data
    assert status["connection"] == "ok"
    assert status["authenticated_user_set"] is True
    assert "user" not in status
    assert tools.list_libraries().data["libraries"] == ["comp", "crsp"]
    assert tools.list_tables(library="comp").data["tables"][0]["table_name"] == "funda"
    assert tools.describe_table(library="comp", table="funda").data["columns"][0]["column_name"] == "gvkey"


def test_tool_registry_exposes_wrds_tools_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRDS_USERNAME", "user")
    monkeypatch.setenv("WRDS_PASSWORD", "secret")

    names = ToolRegistry().names()

    assert {
        "wrds_status",
        "wrds_query",
        "wrds_list_libraries",
        "wrds_list_tables",
        "wrds_describe_table",
        "wrds_capability_discovery",
        "wrds_company_search",
        "wrds_company_financials",
    } <= set(names)


def test_wrds_capability_discovery_classifies_visible_libraries() -> None:
    tools = WRDSTools(
        WRDSConfig(username="user", password="secret"),
        connection_factory=capability_fake_connection_factory,
    )

    result = tools.capability_discovery(max_tables_per_library=10)

    assert result.ok is True
    capabilities = result.data["capabilities"]
    assert capabilities["compustat_fundamentals"]["available"] is True
    assert capabilities["crsp_market_data"]["available"] is True
    assert capabilities["ibes_estimates"]["available"] is True
    assert capabilities["compustat_segments"]["available"] is True
    assert capabilities["capital_iq"]["available"] is True
    assert capabilities["audit_analytics"]["available"] is True
    assert capabilities["optionmetrics"]["available"] is True
    assert result.data["missing_capabilities"] == []


def test_wrds_company_financials_resolves_company_and_calculates_ratios() -> None:
    tools = WRDSTools(
        WRDSConfig(username="user", password="secret"),
        connection_factory=fake_connection_factory,
    )

    result = tools.company_financials(
        query="Apple",
        max_years=3,
        max_quarters=4,
        data_packages=["company_identity", "quarterly_financials_16q"],
    )

    assert result.ok is True
    assert result.data["company"]["tic"] == "AAPL"
    assert result.data["rows"][0]["calculated"]["gross_margin"] is not None
    assert result.data["rows"][0]["calculated"]["gross_margin_after_depreciation"] is not None
    assert result.data["rows"][0]["calculated"]["reported_gross_margin_candidate"] is not None
    assert result.data["quarterly_row_count"] == 1
    assert result.data["quarterly_rows"][0]["calculated"]["gross_margin"] is not None
    assert result.data["data_packages"] == ["company_identity", "quarterly_financials_16q"]


def test_wrds_company_financials_fetches_advanced_packages() -> None:
    tools = WRDSTools(
        WRDSConfig(username="user", password="secret"),
        connection_factory=fake_connection_factory,
    )

    result = tools.company_financials(
        query="Apple",
        max_years=3,
        max_quarters=4,
        data_packages=[
            "crsp_market_data",
            "capital_iq_profile",
            "optionmetrics_security",
            "ibes_estimates",
            "compustat_segments",
            "peer_comparison",
        ],
    )

    assert result.ok is True
    assert result.data["identifier_map"]["primary_permno"] == "14593"
    assert result.data["crsp_market_data"]["latest"]["prc"] == 200
    assert result.data["capital_iq_profile"]["companyid"] == 24937
    assert result.data["capital_iq_profile"]["company_rows"][0]["webpage"] == "www.apple.com"
    assert result.data["optionmetrics_security"]["secid"] == 101594
    assert result.data["optionmetrics_security"]["historical_volatility_rows"][0]["volatility"] == 0.20
    assert result.data["ibes_estimates"]["summary_rows"][0]["meanest"] == 8.5
    assert result.data["compustat_segments"]["rows"][0]["sales"] == 300000
    assert result.data["peer_comparison"]["peer_rows"][0]["peer_tic"] == "MSFT"
    assert result.data["peer_comparison"]["peer_rows"][0]["calculated"]["free_cash_flow"] == 91723
    assert result.data["advanced_package_status"]["crsp_market_data"]["ok"] is True
    assert result.data["advanced_package_status"]["capital_iq_profile"]["ok"] is True
    assert result.data["advanced_package_status"]["optionmetrics_security"]["ok"] is True
    assert result.data["advanced_package_status"]["ibes_estimates"]["ok"] is True
    assert result.data["advanced_package_status"]["compustat_segments"]["ok"] is True
    assert result.data["advanced_package_status"]["peer_comparison"]["ok"] is True


def test_skill_loader_infers_wrds_skill(tmp_path) -> None:
    skill_dir = tmp_path / "wrds-data"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: wrds-data
description: WRDS professional data.
---

# WRDS
""",
        encoding="utf-8",
    )

    matches = SkillLoader(tmp_path).match("用 WRDS 查 Compustat 数据")

    assert [skill.name for skill in matches] == ["wrds-data"]
