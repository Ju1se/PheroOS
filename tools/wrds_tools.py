from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from tools.safe_tools import ToolResult, clamp_int


DEFAULT_WRDS_HOST = "wrds-pgdata.wharton.upenn.edu"
DEFAULT_WRDS_PORT = 9737
DEFAULT_WRDS_DB = "wrds"
MAX_WRDS_ROWS = 500
MAX_WRDS_TIMEOUT_SECONDS = 120
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COMPANY_QUERY_STOPWORDS_RE = re.compile(
    r"\b(analyze|analysis|research|report|valuation|investment|company|stock|wrds|query|data|financials?)\b",
    re.IGNORECASE,
)
FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|do|vacuum|analyze|refresh|merge)\b",
    re.IGNORECASE,
)
COMPANY_ALIASES = {
    "苹果": ["AAPL", "APPLE"],
    "apple": ["AAPL", "APPLE"],
    "微软": ["MSFT", "MICROSOFT"],
    "microsoft": ["MSFT", "MICROSOFT"],
    "英伟达": ["NVDA", "NVIDIA"],
    "nvidia": ["NVDA", "NVIDIA"],
    "特斯拉": ["TSLA", "TESLA"],
    "tesla": ["TSLA", "TESLA"],
    "药明康德": ["WUXI APPTEC"],
    "wuxi apptec": ["WUXI APPTEC"],
    "沪电股份": ["WUS PRINTED CIRCUIT (KUNSHAN", "WUS PRINTED CIRCUIT"],
    "wus printed circuit": ["WUS PRINTED CIRCUIT (KUNSHAN", "WUS PRINTED CIRCUIT"],
    "兆易创新": ["GIGADEVICE"],
    "gigadevice": ["GIGADEVICE"],
    "五粮液": ["WULIANGYE"],
    "wuliangye": ["WULIANGYE"],
    "贵州茅台": ["KWEICHOW MOUTAI", "MOUTAI"],
    "kweichow moutai": ["KWEICHOW MOUTAI", "MOUTAI", "600519"],
}

WRDS_CAPABILITY_TARGETS: dict[str, dict[str, tuple[str, ...]]] = {
    "compustat_fundamentals": {
        "library_patterns": ("comp",),
        "table_patterns": ("funda", "fundq", "names", "g_funda", "g_fundq"),
    },
    "crsp_market_data": {
        "library_patterns": ("crsp",),
        "table_patterns": ("dsf", "msf", "dsenames", "stocknames", "ccmxpf_linktable"),
    },
    "ibes_estimates": {
        "library_patterns": ("ibes", "tr_ibes"),
        "table_patterns": ("statsum", "det", "act", "summary", "detail", "actual"),
    },
    "compustat_segments": {
        "library_patterns": ("compseg", "comp_segments"),
        "table_patterns": ("segment", "segments", "seg", "business", "geographic"),
    },
    "capital_iq": {
        "library_patterns": ("ciq", "ciq_common", "ciq_keydev"),
        "table_patterns": ("company", "financial", "estimate", "keydev", "transcript"),
    },
    "audit_analytics": {
        "library_patterns": ("audit", "audit_analytics"),
        "table_patterns": ("audit", "restatement", "sox", "ic", "fees"),
    },
    "optionmetrics": {
        "library_patterns": ("optionm", "optionmetrics"),
        "table_patterns": ("opprcd", "option", "volatility", "securd", "hvold"),
    },
}

WRDS_DISCOVERY_PATTERNS = tuple(
    dict.fromkeys(
        pattern
        for spec in WRDS_CAPABILITY_TARGETS.values()
        for pattern in spec["library_patterns"]
    )
)

FUNDAMENTAL_COLUMNS = (
    "gvkey",
    "datadate",
    "fyear",
    "tic",
    "conm",
    "curcd",
    "datafmt",
    "indfmt",
    "consol",
    "popsrc",
    "fyr",
    "at",
    "lt",
    "dltt",
    "dlc",
    "che",
    "sale",
    "revt",
    "cogs",
    "gp",
    "xsga",
    "xint",
    "xrd",
    "oibdp",
    "oiadp",
    "ebit",
    "ebitda",
    "dp",
    "gdwl",
    "intan",
    "ni",
    "ib",
    "oancf",
    "capx",
    "ceq",
    "seq",
    "act",
    "lct",
    "invt",
    "rect",
    "ap",
    "prcc_f",
    "csho",
    "epspx",
    "epspi",
    "epsfi",
    "dvc",
    "dvp",
    "dvpsx_f",
    "prstkc",
    "sstk",
    "ajex",
)

QUARTERLY_COLUMNS = (
    "gvkey",
    "datadate",
    "fyearq",
    "fqtr",
    "fyr",
    "tic",
    "conm",
    "curcdq",
    "datafmt",
    "indfmt",
    "consol",
    "popsrc",
    "atq",
    "ltq",
    "dlttq",
    "dlcq",
    "cheq",
    "saleq",
    "revtq",
    "cogsq",
    "gpq",
    "xsgaq",
    "xintq",
    "xrdq",
    "oibdpq",
    "oiadpq",
    "dpq",
    "gdwlq",
    "intanq",
    "niq",
    "ibq",
    "oancfy",
    "capxy",
    "ceqq",
    "actq",
    "lctq",
    "invtq",
    "rectq",
    "apq",
    "prccq",
    "cshoq",
    "epspxq",
    "epsfiq",
    "ajexq",
    "dvy",
    "prstkcy",
    "sstky",
    "rdq",
)


ConnectionFactory = Callable[..., Any]


@dataclass(frozen=True)
class WRDSConfig:
    username: str | None
    password: str | None
    host: str = DEFAULT_WRDS_HOST
    port: int = DEFAULT_WRDS_PORT
    dbname: str = DEFAULT_WRDS_DB
    sslmode: str = "require"
    connect_timeout: int = 20
    statement_timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "WRDSConfig":
        return cls(
            username=os.getenv("WRDS_USERNAME") or os.getenv("WRDS_USER"),
            password=os.getenv("WRDS_PASSWORD"),
            host=os.getenv("WRDS_HOST", DEFAULT_WRDS_HOST),
            port=clamp_int(os.getenv("WRDS_PORT", DEFAULT_WRDS_PORT), minimum=1, maximum=65535),
            dbname=os.getenv("WRDS_DB", DEFAULT_WRDS_DB),
            sslmode=os.getenv("WRDS_SSLMODE", "require"),
            connect_timeout=clamp_int(os.getenv("WRDS_CONNECT_TIMEOUT", 20), minimum=1, maximum=120),
            statement_timeout_seconds=clamp_int(
                os.getenv("WRDS_STATEMENT_TIMEOUT_SECONDS", 60),
                minimum=1,
                maximum=MAX_WRDS_TIMEOUT_SECONDS,
            ),
        )

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password)


class WRDSTools:
    """Read-only WRDS access through PostgreSQL."""

    def __init__(
        self,
        config: WRDSConfig | None = None,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.config = config or WRDSConfig.from_env()
        self.connection_factory = connection_factory

    def status(self, *, check_connection: bool = False) -> ToolResult:
        data: dict[str, Any] = {
            "configured": self.config.configured,
            "host": self.config.host,
            "port": self.config.port,
            "dbname": self.config.dbname,
            "username_set": bool(self.config.username),
            "password_set": bool(self.config.password),
        }
        if not self.config.configured:
            return ToolResult(False, data, "WRDS credentials are not configured")
        if not check_connection:
            return ToolResult(True, data)

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("select current_user as user, current_database() as database")
                    row = first_row(cur.fetchall())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, data, sanitize_wrds_error(exc, self.config))

        data["connection"] = "ok"
        data["authenticated_user_set"] = bool(row.get("user"))
        data["database"] = row.get("database")
        return ToolResult(True, data)

    def list_libraries(self, *, pattern: str | None = None, max_results: int = 200) -> ToolResult:
        max_results = clamp_int(max_results, minimum=1, maximum=1_000)
        sql = (
            "select schema_name from information_schema.schemata "
            "where schema_name not like 'pg_%%' and schema_name <> 'information_schema'"
        )
        params: list[Any] = []
        if pattern:
            sql += " and schema_name ilike %s"
            params.append(f"%{pattern}%")
        sql += " order by schema_name limit %s"
        params.append(max_results)

        try:
            rows = self._fetch(sql, params)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"pattern": pattern, "max_results": max_results}, sanitize_wrds_error(exc, self.config))

        return ToolResult(
            True,
            {
                "libraries": [row["schema_name"] for row in rows],
                "count": len(rows),
                "truncated": len(rows) >= max_results,
            },
        )

    def list_tables(self, *, library: str, pattern: str | None = None, max_results: int = 200) -> ToolResult:
        try:
            library = validate_identifier(library, label="library")
        except ValueError as exc:
            return ToolResult(False, {"library": library}, str(exc))

        max_results = clamp_int(max_results, minimum=1, maximum=1_000)
        sql = (
            "select table_name, table_type from information_schema.tables "
            "where table_schema = %s"
        )
        params: list[Any] = [library]
        if pattern:
            sql += " and table_name ilike %s"
            params.append(f"%{pattern}%")
        sql += " order by table_name limit %s"
        params.append(max_results)

        try:
            rows = self._fetch(sql, params)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"library": library, "pattern": pattern}, sanitize_wrds_error(exc, self.config))

        return ToolResult(
            True,
            {
                "library": library,
                "tables": rows,
                "count": len(rows),
                "truncated": len(rows) >= max_results,
            },
        )

    def describe_table(self, *, library: str, table: str, max_columns: int = 300) -> ToolResult:
        try:
            library = validate_identifier(library, label="library")
            table = validate_identifier(table, label="table")
        except ValueError as exc:
            return ToolResult(False, {"library": library, "table": table}, str(exc))

        max_columns = clamp_int(max_columns, minimum=1, maximum=1_000)
        sql = (
            "select column_name, data_type, ordinal_position "
            "from information_schema.columns "
            "where table_schema = %s and table_name = %s "
            "order by ordinal_position "
            "limit %s"
        )
        try:
            rows = self._fetch(sql, [library, table, max_columns])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"library": library, "table": table}, sanitize_wrds_error(exc, self.config))

        return ToolResult(
            True,
            {
                "library": library,
                "table": table,
                "columns": rows,
                "count": len(rows),
                "truncated": len(rows) >= max_columns,
            },
        )

    def capability_discovery(
        self,
        *,
        libraries: list[str] | None = None,
        max_tables_per_library: int = 50,
    ) -> ToolResult:
        """Discover which WRDS data capabilities are visible to the account."""
        max_tables_per_library = clamp_int(max_tables_per_library, minimum=1, maximum=200)
        requested_patterns = normalize_discovery_patterns(libraries)
        discovered_libraries: dict[str, dict[str, Any]] = {}

        try:
            library_rows = self._discover_libraries(requested_patterns)
            for row in library_rows:
                library_name = str(row.get("schema_name") or "")
                if not library_name:
                    continue
                matched_patterns = [
                    pattern
                    for pattern in requested_patterns
                    if pattern in library_name.lower()
                ]
                discovered_libraries[library_name] = {
                    "library": library_name,
                    "matched_patterns": matched_patterns,
                    "tables": [],
                    "table_count": 0,
                }

            table_rows = self._discover_tables(sorted(discovered_libraries), max_tables_per_library=max_tables_per_library)
            for row in table_rows:
                library_name = str(row.get("table_schema") or "")
                if library_name not in discovered_libraries:
                    continue
                discovered_libraries[library_name]["tables"].append(
                    {
                        "table_name": row.get("table_name"),
                        "table_type": row.get("table_type"),
                    }
                )
            for library_info in discovered_libraries.values():
                library_info["table_count"] = len(library_info["tables"])
                library_info["tables_truncated"] = len(library_info["tables"]) >= max_tables_per_library
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                False,
                {"libraries": sorted(discovered_libraries), "requested_patterns": requested_patterns},
                sanitize_wrds_error(exc, self.config),
            )

        capabilities = classify_wrds_capabilities(discovered_libraries)
        missing_capabilities = [
            name
            for name, payload in capabilities.items()
            if not payload.get("available")
        ]
        return ToolResult(
            True,
            {
                "status": "completed",
                "requested_patterns": requested_patterns,
                "available_libraries": sorted(discovered_libraries),
                "library_count": len(discovered_libraries),
                "libraries": [discovered_libraries[name] for name in sorted(discovered_libraries)],
                "capabilities": capabilities,
                "missing_capabilities": missing_capabilities,
                "notes": [
                    "Discovery uses WRDS information_schema visibility only.",
                    "A visible library/table means the account can see metadata; individual query permissions may still vary.",
                ],
            },
        )

    def _discover_libraries(self, patterns: list[str]) -> list[dict[str, Any]]:
        filters = " or ".join(["schema_name ilike %s" for _ in patterns])
        sql = (
            "select schema_name from information_schema.schemata "
            "where schema_name not like 'pg_%%' and schema_name <> 'information_schema' "
            f"and ({filters}) "
            "order by schema_name"
        )
        params = [f"%{pattern}%" for pattern in patterns]
        return self._fetch(sql, params)

    def _discover_tables(self, libraries: list[str], *, max_tables_per_library: int) -> list[dict[str, Any]]:
        if not libraries:
            return []
        placeholders = ", ".join(["%s" for _ in libraries])
        table_patterns = sorted(
            {
                pattern
                for spec in WRDS_CAPABILITY_TARGETS.values()
                for pattern in spec["table_patterns"]
            }
        )
        table_filters = " or ".join(["table_name ilike %s" for _ in table_patterns])
        sql = (
            "select table_schema, table_name, table_type from ("
            "select table_schema, table_name, table_type, "
            "row_number() over (partition by table_schema order by table_name) as rn "
            "from information_schema.tables "
            f"where table_schema in ({placeholders}) "
            f"and ({table_filters})"
            ") t "
            "where rn <= %s "
            "order by table_schema, table_name"
        )
        return self._fetch(sql, [*libraries, *[f"%{pattern}%" for pattern in table_patterns], max_tables_per_library])

    def query(self, *, sql: str, max_rows: int = 100) -> ToolResult:
        try:
            clean_sql = validate_read_only_sql(sql)
        except ValueError as exc:
            return ToolResult(False, {"sql_preview": preview_sql(sql)}, str(exc))

        max_rows = clamp_int(max_rows, minimum=1, maximum=MAX_WRDS_ROWS)
        wrapped_sql = f"select * from ({clean_sql}) as wrds_agent_query limit {max_rows + 1}"
        try:
            rows = self._fetch(wrapped_sql, [])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"sql_preview": preview_sql(sql), "max_rows": max_rows}, sanitize_wrds_error(exc, self.config))

        truncated = len(rows) > max_rows
        visible_rows = rows[:max_rows]
        columns = list(visible_rows[0].keys()) if visible_rows else []
        return ToolResult(
            True,
            {
                "columns": columns,
                "rows": visible_rows,
                "row_count": len(visible_rows),
                "truncated": truncated,
                "max_rows": max_rows,
                "sql_preview": preview_sql(sql),
            },
        )

    def company_search(self, *, query: str, max_results: int = 8) -> ToolResult:
        max_results = clamp_int(max_results, minimum=1, maximum=25)
        terms = company_search_terms(query)
        if not terms:
            return ToolResult(True, {"query": query, "search_terms": [], "candidates": [], "count": 0, "status": "no_query"})

        try:
            candidates = []
            seen = set()
            for term in terms[:8]:
                for candidate in self._search_company_term(term, max_results=max_results):
                    key = (
                        candidate.get("source"),
                        candidate.get("gvkey"),
                        candidate.get("tic"),
                        candidate.get("conm"),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(candidate)
            candidates.sort(key=company_candidate_sort_key, reverse=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"query": query, "search_terms": terms}, sanitize_wrds_error(exc, self.config))

        visible = candidates[:max_results]
        return ToolResult(
            True,
            {
                "query": query,
                "search_terms": terms,
                "candidates": visible,
                "count": len(visible),
                "truncated": len(candidates) > max_results,
                "status": "matched" if visible else "no_match",
            },
        )

    def company_financials(
        self,
        *,
        query: str,
        max_years: int = 5,
        max_quarters: int = 0,
        max_candidates: int = 5,
        data_packages: list[str] | None = None,
    ) -> ToolResult:
        max_years = clamp_int(max_years, minimum=1, maximum=12)
        max_quarters = clamp_int(max_quarters, minimum=0, maximum=24)
        max_candidates = clamp_int(max_candidates, minimum=1, maximum=10)
        data_packages = [str(item) for item in (data_packages or []) if str(item).strip()]
        search = self.company_search(query=query, max_results=max_candidates)
        if not search.ok:
            return search

        candidates = search.data.get("candidates") if isinstance(search.data, dict) else []
        if not isinstance(candidates, list) or not candidates:
            return ToolResult(
                True,
                {
                    "query": query,
                    "company": None,
                    "candidates": [],
                    "rows": [],
                    "row_count": 0,
                    "status": "no_match",
                    "data_packages": data_packages,
                    "evidence_gap": "No matching WRDS company record was found for the input.",
                },
            )

        company = candidates[0]
        table = "comp.g_funda" if str(company.get("source", "")).startswith("comp.g_") else "comp.funda"
        quarterly_table = "comp.g_fundq" if table == "comp.g_funda" else "comp.fundq"
        try:
            rows = self._fetch_company_fundamentals(company=company, table=table, max_years=max_years)
            quarterly_rows = (
                self._fetch_company_quarterly(company=company, table=quarterly_table, max_quarters=max_quarters)
                if max_quarters
                else []
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"query": query, "company": company, "table": table}, sanitize_wrds_error(exc, self.config))

        optional_data = self._fetch_optional_company_packages(company=company, data_packages=data_packages)
        return ToolResult(
            True,
            {
                "query": query,
                "company": company,
                "candidates": candidates,
                "table": table,
                "quarterly_table": quarterly_table if quarterly_rows else None,
                "rows": rows,
                "quarterly_rows": quarterly_rows,
                "row_count": len(rows),
                "quarterly_row_count": len(quarterly_rows),
                "max_years": max_years,
                "max_quarters": max_quarters,
                "data_packages": data_packages,
                **optional_data,
                "status": "matched_with_financials" if rows else "matched_no_financial_rows",
                "metrics_note": (
                    "Compustat values are returned in native WRDS units/currency. "
                    "Calculated ratios use available fields only and may be null when inputs are missing."
                ),
            },
        )

    def _fetch(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if not self.config.configured:
            raise RuntimeError("WRDS credentials are not configured")
        with self._connect() as conn:
            with conn.cursor() as cur:
                timeout_ms = self.config.statement_timeout_seconds * 1000
                cur.execute("set statement_timeout = %s", [timeout_ms])
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                return [json_safe_row(row) for row in cur.fetchall()]

    def _search_company_term(self, term: str, *, max_results: int) -> list[dict[str, Any]]:
        like = f"%{term}%"
        params = [
            term,
            term,
            like,
            term,
            term,
            term,
            like,
            term,
            max_results,
        ]
        sql = """
            with candidates as (
                select
                    'comp.names'::text as source,
                    gvkey,
                    tic,
                    conm,
                    null::varchar as fic,
                    null::varchar as loc,
                    cusip,
                    cik,
                    sic,
                    naics,
                    gind,
                    gsubind,
                    year1,
                    year2
                from comp.names
                where upper(coalesce(tic, '')) = upper(%s)
                   or gvkey = %s
                   or upper(coalesce(conm, '')) like upper(%s)
                   or upper(coalesce(cusip, '')) = upper(%s)
                union all
                select
                    'comp.g_names'::text as source,
                    n.gvkey,
                    s.tic,
                    n.conm,
                    n.fic,
                    null::varchar as loc,
                    s.cusip,
                    null::varchar as cik,
                    n.sic,
                    n.naics,
                    n.gind,
                    n.gsubind,
                    n.year1,
                    n.year2
                from comp.g_names n
                left join comp.g_security s on s.gvkey = n.gvkey
                where upper(coalesce(s.tic, '')) = upper(%s)
                   or n.gvkey = %s
                   or upper(coalesce(n.conm, '')) like upper(%s)
                   or upper(coalesce(n.isin, '')) = upper(%s)
            )
            select
                source,
                gvkey,
                tic,
                conm,
                fic,
                loc,
                cusip,
                cik,
                sic,
                naics,
                gind,
                gsubind,
                year1,
                year2,
                case
                    when upper(coalesce(tic, '')) = upper(%s) then 100
                    when gvkey = %s then 95
                    when upper(coalesce(conm, '')) = upper(%s) then 90
                    when upper(coalesce(conm, '')) like upper(%s) then 70
                    else 50
                end as match_score
            from candidates
            order by match_score desc, year2 desc nulls last, source
            limit %s
        """
        final_params = [*params[:-1], term, term, term, like, max_results]
        return self._fetch(sql, final_params)

    def _fetch_company_fundamentals(
        self,
        *,
        company: dict[str, Any],
        table: str,
        max_years: int,
    ) -> list[dict[str, Any]]:
        table_schema, table_name = table.split(".", 1)
        columns = self._table_columns(table_schema, table_name)
        selected = [column for column in FUNDAMENTAL_COLUMNS if column in columns]
        if "gvkey" not in selected or "datadate" not in selected:
            raise RuntimeError(f"{table} is missing required gvkey/datadate columns")

        select_sql = ", ".join(f"f.{column}" for column in selected)
        filters = ["f.gvkey = %s"]
        if "indfmt" in columns:
            filters.append("(f.indfmt = 'INDL' or f.indfmt is null)")
        if "consol" in columns:
            filters.append("(f.consol = 'C' or f.consol is null)")
        if "datafmt" in columns:
            filters.append("(f.datafmt in ('STD', 'HIST_STD') or f.datafmt is null)")
        sql = (
            f"select {select_sql} from {table} f "
            f"where {' and '.join(filters)} "
            "order by f.datadate desc "
            "limit %s"
        )
        rows = self._fetch(sql, [company["gvkey"], max_years])
        return add_financial_ratios(rows)

    def _fetch_company_quarterly(
        self,
        *,
        company: dict[str, Any],
        table: str,
        max_quarters: int,
    ) -> list[dict[str, Any]]:
        table_schema, table_name = table.split(".", 1)
        columns = self._table_columns(table_schema, table_name)
        selected = [column for column in QUARTERLY_COLUMNS if column in columns]
        if "gvkey" not in selected or "datadate" not in selected:
            return []

        select_sql = ", ".join(f"f.{column}" for column in selected)
        filters = ["f.gvkey = %s"]
        if "indfmt" in columns:
            filters.append("(f.indfmt = 'INDL' or f.indfmt is null)")
        if "consol" in columns:
            filters.append("(f.consol = 'C' or f.consol is null)")
        if "datafmt" in columns:
            filters.append("(f.datafmt in ('STD', 'HIST_STD') or f.datafmt is null)")
        sql = (
            f"select {select_sql} from {table} f "
            f"where {' and '.join(filters)} "
            "order by f.datadate desc "
            "limit %s"
        )
        rows = self._fetch(sql, [company["gvkey"], max_quarters])
        return add_quarterly_financial_ratios(rows)

    def _fetch_optional_company_packages(
        self,
        *,
        company: dict[str, Any],
        data_packages: list[str],
    ) -> dict[str, Any]:
        packages = set(data_packages)
        payload: dict[str, Any] = {
            "advanced_package_status": {},
            "identifier_map": {},
            "crsp_market_data": {},
            "capital_iq_profile": {},
            "optionmetrics_security": {},
            "ibes_estimates": {},
            "compustat_segments": {},
            "peer_comparison": {},
        }
        if not packages:
            return payload

        identifier_map = self._safe_optional_fetch(
            "identifier_map",
            lambda: self._fetch_identifier_map(company=company),
        )
        payload["identifier_map"] = identifier_map.get("data") or {}
        payload["advanced_package_status"]["identifier_map"] = optional_status(identifier_map)

        if "crsp_market_data" in packages:
            crsp = self._safe_optional_fetch(
                "crsp_market_data",
                lambda: self._fetch_crsp_market_data(identifier_map=payload["identifier_map"]),
            )
            payload["crsp_market_data"] = crsp.get("data") or {}
            payload["advanced_package_status"]["crsp_market_data"] = optional_status(crsp)

        if "capital_iq_profile" in packages:
            capital_iq = self._safe_optional_fetch(
                "capital_iq_profile",
                lambda: self._fetch_capital_iq_profile(company=company),
            )
            payload["capital_iq_profile"] = capital_iq.get("data") or {}
            payload["advanced_package_status"]["capital_iq_profile"] = optional_status(capital_iq)

        if "optionmetrics_security" in packages:
            optionmetrics = self._safe_optional_fetch(
                "optionmetrics_security",
                lambda: self._fetch_optionmetrics_security(company=company, identifier_map=payload["identifier_map"]),
            )
            payload["optionmetrics_security"] = optionmetrics.get("data") or {}
            payload["advanced_package_status"]["optionmetrics_security"] = optional_status(optionmetrics)

        if "ibes_estimates" in packages:
            ibes = self._safe_optional_fetch(
                "ibes_estimates",
                lambda: self._fetch_ibes_estimates(company=company, identifier_map=payload["identifier_map"]),
            )
            payload["ibes_estimates"] = ibes.get("data") or {}
            payload["advanced_package_status"]["ibes_estimates"] = optional_status(ibes)

        if "compustat_segments" in packages:
            segments = self._safe_optional_fetch(
                "compustat_segments",
                lambda: self._fetch_compustat_segments(company=company),
            )
            payload["compustat_segments"] = segments.get("data") or {}
            payload["advanced_package_status"]["compustat_segments"] = optional_status(segments)

        if "peer_comparison" in packages:
            peers = self._safe_optional_fetch(
                "peer_comparison",
                lambda: self._fetch_peer_comparison(company=company),
            )
            payload["peer_comparison"] = peers.get("data") or {}
            payload["advanced_package_status"]["peer_comparison"] = optional_status(peers)
        return payload

    def _safe_optional_fetch(self, package: str, fetcher: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return {"ok": True, "data": fetcher()}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "data": {"status": "failed", "package": package},
                "error": sanitize_wrds_error(exc, self.config),
            }

    def _fetch_identifier_map(self, *, company: dict[str, Any]) -> dict[str, Any]:
        gvkey = str(company.get("gvkey") or "")
        if not gvkey:
            return {"status": "missing_gvkey", "company": company, "ccm_links": [], "permnos": [], "permcos": []}
        ccm_columns = self._table_columns("crsp", "ccmxpf_linktable")
        required = {"gvkey", "lpermno", "lpermco", "linkdt", "linkenddt"}
        if not required <= ccm_columns:
            return {"status": "missing_ccm_columns", "company": company, "ccm_links": [], "permnos": [], "permcos": []}
        selected = [
            column
            for column in ("gvkey", "linkprim", "liid", "linktype", "lpermno", "lpermco", "usedflag", "linkdt", "linkenddt")
            if column in ccm_columns
        ]
        select_sql = ", ".join(selected)
        rows = self._fetch(
            f"""
            select {select_sql}
            from crsp.ccmxpf_linktable
            where gvkey = %s
            order by
                case when linkenddt is null then 1 else 0 end desc,
                linkenddt desc nulls first,
                linkdt desc nulls last
            limit 20
            """,
            [gvkey],
        )
        permnos = unique_terms([format_wrds_identifier_number(row.get("lpermno")) for row in rows if row.get("lpermno")])
        permcos = unique_terms([format_wrds_identifier_number(row.get("lpermco")) for row in rows if row.get("lpermco")])
        return {
            "status": "matched" if rows else "no_crsp_link",
            "company": company,
            "gvkey": gvkey,
            "ticker": company.get("tic"),
            "cusip": company.get("cusip"),
            "cik": company.get("cik"),
            "permnos": permnos,
            "permcos": permcos,
            "primary_permno": permnos[0] if permnos else None,
            "primary_permco": permcos[0] if permcos else None,
            "ccm_links": rows,
        }

    def _fetch_crsp_market_data(self, *, identifier_map: dict[str, Any], max_daily_rows: int = 260) -> dict[str, Any]:
        permno = identifier_map.get("primary_permno")
        if not permno:
            return {"status": "missing_permno", "daily_rows": [], "latest": None}
        permno_value = coerce_wrds_int_identifier(permno)
        columns = self._table_columns("crsp", "dsf")
        selected = [
            column
            for column in ("permno", "permco", "date", "prc", "ret", "retx", "vol", "shrout", "cfacpr", "cfacshr", "bidlo", "askhi")
            if column in columns
        ]
        if not {"permno", "date"} <= set(selected):
            return {"status": "missing_crsp_dsf_columns", "daily_rows": [], "latest": None}
        select_sql = ", ".join(f"d.{column}" for column in selected)
        rows = self._fetch(
            f"""
            select {select_sql}
            from crsp.dsf d
            where d.permno = %s
            order by d.date desc
            limit %s
            """,
            [permno_value, clamp_int(max_daily_rows, minimum=1, maximum=500)],
        )
        return {
            "status": "matched" if rows else "no_rows",
            "table": "crsp.dsf",
            "identifier_map": identifier_map,
            "daily_rows": rows,
            "latest": rows[0] if rows else None,
            "row_count": len(rows),
        }

    def _fetch_capital_iq_profile(self, *, company: dict[str, Any]) -> dict[str, Any]:
        gvkey = str(company.get("gvkey") or "")
        if not gvkey:
            return {"status": "missing_gvkey", "gvkey_rows": [], "company_rows": [], "symbol_rows": [], "description_rows": []}

        gvkey_columns = self._table_columns("ciq", "wrds_gvkey")
        selected_gvkey = [
            column
            for column in ("companyid", "gvkey", "companyname", "startdate", "enddate", "primaryflag")
            if column in gvkey_columns
        ]
        if not {"companyid", "gvkey"} <= set(selected_gvkey):
            return {"status": "missing_ciq_gvkey_columns", "gvkey_rows": [], "company_rows": [], "symbol_rows": [], "description_rows": []}

        gvkey_rows = self._fetch(
            f"""
            select {", ".join(selected_gvkey)}
            from ciq.wrds_gvkey
            where gvkey = %s
            order by
                primaryflag desc nulls last,
                enddate desc nulls first,
                startdate desc nulls last
            limit 10
            """,
            [gvkey],
        )
        company_id = first_non_empty([row.get("companyid") for row in gvkey_rows])
        if company_id is None:
            return {
                "status": "no_rows",
                "table": "ciq.wrds_gvkey",
                "gvkey": gvkey,
                "gvkey_rows": gvkey_rows,
                "company_rows": [],
                "symbol_rows": [],
                "description_rows": [],
                "row_count": len(gvkey_rows),
            }

        company_rows = self._fetch_ciq_company_rows(company_id=company_id)
        symbol_rows = self._fetch_ciq_symbol_rows(company_id=company_id)
        description_rows = self._fetch_ciq_description_rows(company_id=company_id)
        return {
            "status": "matched",
            "table": "ciq.wrds_gvkey",
            "company_table": "ciq_common.ciqcompany",
            "symbol_table": "ciq.wrds_ciqsymbol",
            "description_table": "ciq.ciqbusinessdescription",
            "gvkey": gvkey,
            "companyid": company_id,
            "gvkey_rows": gvkey_rows,
            "company_rows": company_rows,
            "symbol_rows": symbol_rows,
            "description_rows": description_rows,
            "row_count": len(gvkey_rows) + len(company_rows) + len(symbol_rows) + len(description_rows),
        }

    def _fetch_ciq_company_rows(self, *, company_id: Any) -> list[dict[str, Any]]:
        columns = self._table_columns("ciq_common", "ciqcompany")
        selected = [
            column
            for column in (
                "companyid",
                "companyname",
                "city",
                "companystatustypeid",
                "companytypeid",
                "simpleindustryid",
                "yearfounded",
                "webpage",
                "countryid",
                "stateid",
                "incorporationcountryid",
                "incorporationstateid",
            )
            if column in columns
        ]
        if "companyid" not in selected:
            return []
        return self._fetch(
            f"""
            select {", ".join(selected)}
            from ciq_common.ciqcompany
            where companyid = %s
            limit 1
            """,
            [company_id],
        )

    def _fetch_ciq_symbol_rows(self, *, company_id: Any) -> list[dict[str, Any]]:
        columns = self._table_columns("ciq", "wrds_ciqsymbol")
        selected = [
            column
            for column in (
                "companyid",
                "companyname",
                "symbolid",
                "symboltypeid",
                "symboltypecat",
                "symboltypename",
                "symbolvalue",
                "startdate",
                "enddate",
                "activeflag",
                "securityname",
                "primaryflag",
                "exchangeid",
                "exchangename",
                "tradingitemstatusname",
                "primaryflag_trd",
            )
            if column in columns
        ]
        if "companyid" not in selected:
            return []
        return self._fetch(
            f"""
            select {", ".join(selected)}
            from ciq.wrds_ciqsymbol
            where companyid = %s
            order by
                primaryflag desc nulls last,
                primaryflag_trd desc nulls last,
                activeflag desc nulls last,
                enddate desc nulls first,
                startdate desc nulls last
            limit 20
            """,
            [company_id],
        )

    def _fetch_ciq_description_rows(self, *, company_id: Any) -> list[dict[str, Any]]:
        columns = self._table_columns("ciq", "ciqbusinessdescription")
        selected = [column for column in ("companyid", "businessdescription") if column in columns]
        if "companyid" not in selected:
            return []
        return self._fetch(
            f"""
            select {", ".join(selected)}
            from ciq.ciqbusinessdescription
            where companyid = %s
            limit 1
            """,
            [company_id],
        )

    def _fetch_optionmetrics_security(self, *, company: dict[str, Any], identifier_map: dict[str, Any]) -> dict[str, Any]:
        ticker = str(company.get("tic") or identifier_map.get("ticker") or "").upper()
        cusip = str(company.get("cusip") or identifier_map.get("cusip") or "").upper()
        if not ticker and not cusip:
            return {"status": "missing_ticker_or_cusip", "security_rows": [], "borrow_rows": [], "historical_volatility_rows": []}

        securd_columns = self._table_columns("optionm", "securd")
        selected = [
            column
            for column in ("secid", "cusip", "ticker", "sic", "index_flag", "exchange_d", "class", "issue_type", "industry_group")
            if column in securd_columns
        ]
        if not {"secid", "ticker"} <= set(selected):
            return {"status": "missing_optionmetrics_securd_columns", "security_rows": [], "borrow_rows": [], "historical_volatility_rows": []}

        filters = []
        params: list[Any] = []
        if ticker:
            filters.append("upper(coalesce(ticker, '')) = upper(%s)")
            params.append(ticker)
        if cusip and "cusip" in securd_columns:
            filters.append("left(upper(coalesce(cusip, '')), 8) = left(upper(%s), 8)")
            params.append(cusip)
        where = " or ".join(filters) or "false"
        security_rows = self._fetch(
            f"""
            select {", ".join(selected)}
            from optionm.securd
            where ({where})
            order by
                case when upper(coalesce(ticker, '')) = upper(%s) then 0 else 1 end,
                secid
            limit 10
            """,
            [*params, ticker],
        )
        secid = first_non_empty([row.get("secid") for row in security_rows])
        if secid is None:
            return {
                "status": "no_security_match",
                "table": "optionm.securd",
                "ticker": ticker,
                "cusip": cusip,
                "security_rows": security_rows,
                "borrow_rows": [],
                "historical_volatility_rows": [],
                "row_count": len(security_rows),
            }

        borrow_table = self._latest_optionmetrics_year_table(prefix="borrate")
        hv_table = self._latest_optionmetrics_year_table(prefix="hvold")
        borrow_rows = self._fetch_optionmetrics_borrow_rows(secid=secid, table=borrow_table) if borrow_table else []
        hv_rows = self._fetch_optionmetrics_historical_volatility_rows(secid=secid, table=hv_table) if hv_table else []
        return {
            "status": "matched",
            "table": "optionm.securd",
            "borrow_table": f"optionm.{borrow_table}" if borrow_table else None,
            "historical_volatility_table": f"optionm.{hv_table}" if hv_table else None,
            "ticker": ticker,
            "cusip": cusip,
            "secid": secid,
            "security_rows": security_rows,
            "borrow_rows": borrow_rows,
            "historical_volatility_rows": hv_rows,
            "row_count": len(security_rows) + len(borrow_rows) + len(hv_rows),
        }

    def _latest_optionmetrics_year_table(self, *, prefix: str) -> str | None:
        if prefix not in {"borrate", "hvold"}:
            return None
        rows = self._fetch(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'optionm'
              and table_name ~ %s
            order by table_name desc
            limit 1
            """,
            [f"^{prefix}[0-9]{{4}}$"],
        )
        return str(rows[0].get("table_name")) if rows else None

    def _fetch_optionmetrics_borrow_rows(self, *, secid: Any, table: str) -> list[dict[str, Any]]:
        columns = self._table_columns("optionm", table)
        selected = [column for column in ("secid", "date", "expirationdate", "days", "borrowrate") if column in columns]
        if not {"secid", "date", "borrowrate"} <= set(selected):
            return []
        return self._fetch(
            f"""
            select {", ".join(selected)}
            from optionm.{table}
            where secid = %s
              and borrowrate is not null
              and borrowrate > -90
            order by date desc, abs(coalesce(days, 30) - 30), expirationdate nulls last
            limit 5
            """,
            [coerce_wrds_int_identifier(secid)],
        )

    def _fetch_optionmetrics_historical_volatility_rows(self, *, secid: Any, table: str) -> list[dict[str, Any]]:
        columns = self._table_columns("optionm", table)
        selected = [column for column in ("secid", "date", "days", "volatility") if column in columns]
        if not {"secid", "date", "volatility"} <= set(selected):
            return []
        return self._fetch(
            f"""
            select {", ".join(selected)}
            from optionm.{table}
            where secid = %s
              and volatility is not null
            order by date desc, abs(coalesce(days, 30) - 30)
            limit 5
            """,
            [coerce_wrds_int_identifier(secid)],
        )

    def _fetch_ibes_estimates(self, *, company: dict[str, Any], identifier_map: dict[str, Any]) -> dict[str, Any]:
        ticker = str(company.get("tic") or identifier_map.get("ticker") or "").upper()
        cusip = str(company.get("cusip") or identifier_map.get("cusip") or "").upper()
        if not ticker and not cusip:
            return {"status": "missing_ticker_or_cusip", "summary_rows": [], "actual_rows": []}
        errors: dict[str, str] = {}
        try:
            summary_rows = self._fetch_ibes_summary_rows(ticker=ticker, cusip=cusip)
        except Exception as exc:  # noqa: BLE001
            summary_rows = []
            errors["summary"] = sanitize_wrds_error(exc, self.config)
        try:
            actual_rows = self._fetch_ibes_actual_rows(ticker=ticker, cusip=cusip)
        except Exception as exc:  # noqa: BLE001
            actual_rows = []
            errors["actual"] = sanitize_wrds_error(exc, self.config)
        status = "matched" if summary_rows or actual_rows else ("failed" if errors else "no_rows")
        return {
            "status": status,
            "summary_table": "ibes.statsum_epsus",
            "actual_table": "ibes.act_epsus",
            "ticker": ticker,
            "cusip": cusip,
            "summary_rows": summary_rows,
            "actual_rows": actual_rows,
            "summary_row_count": len(summary_rows),
            "actual_row_count": len(actual_rows),
            "errors": errors,
        }

    def _fetch_ibes_summary_rows(self, *, ticker: str, cusip: str) -> list[dict[str, Any]]:
        columns = self._table_columns("ibes", "statsum_epsus")
        selected = [
            column
            for column in (
                "ticker",
                "cusip",
                "oftic",
                "cname",
                "statpers",
                "measure",
                "fiscalp",
                "fpi",
                "estflag",
                "curcode",
                "numest",
                "meanest",
                "medest",
                "stdev",
                "highest",
                "lowest",
                "fpedats",
                "actual",
                "actdats_act",
                "anndats_act",
                "curr_act",
            )
            if column in columns
        ]
        if not {"ticker", "statpers"} <= set(selected):
            return []
        select_sql = ", ".join(f"s.{column}" for column in selected)
        filters = []
        params: list[Any] = []
        if ticker:
            filters.append("upper(coalesce(s.ticker, '')) = upper(%s)")
            params.append(ticker)
            if "oftic" in columns:
                filters.append("upper(coalesce(s.oftic, '')) = upper(%s)")
                params.append(ticker)
        if cusip and "cusip" in columns:
            filters.append("upper(coalesce(s.cusip, '')) = upper(%s)")
            params.append(cusip[:8])
        where = " or ".join(filters) or "false"
        return self._fetch(
            f"""
            select {select_sql}
            from ibes.statsum_epsus s
            where ({where})
            order by s.statpers desc, s.fpedats desc nulls last
            limit 24
            """,
            params,
        )

    def _fetch_ibes_actual_rows(self, *, ticker: str, cusip: str) -> list[dict[str, Any]]:
        columns = self._table_columns("ibes", "act_epsus")
        selected = [
            column
            for column in ("ticker", "cusip", "oftic", "cname", "pends", "measure", "pdicity", "anndats", "actdats", "value", "curr_act")
            if column in columns
        ]
        if not {"ticker", "pends"} <= set(selected):
            return []
        select_sql = ", ".join(f"a.{column}" for column in selected)
        filters = []
        params: list[Any] = []
        if ticker:
            filters.append("upper(coalesce(a.ticker, '')) = upper(%s)")
            params.append(ticker)
            if "oftic" in columns:
                filters.append("upper(coalesce(a.oftic, '')) = upper(%s)")
                params.append(ticker)
        if cusip and "cusip" in columns:
            filters.append("upper(coalesce(a.cusip, '')) = upper(%s)")
            params.append(cusip[:8])
        where = " or ".join(filters) or "false"
        return self._fetch(
            f"""
            select {select_sql}
            from ibes.act_epsus a
            where ({where})
            order by a.anndats desc nulls last, a.pends desc
            limit 12
            """,
            params,
        )

    def _fetch_compustat_segments(self, *, company: dict[str, Any], max_rows: int = 50) -> dict[str, Any]:
        gvkey = str(company.get("gvkey") or "")
        if not gvkey:
            return {"status": "missing_gvkey", "rows": [], "row_count": 0}
        table = "wrds_segmerged"
        errors: dict[str, str] = {}
        try:
            columns = self._table_columns("compseg", table)
        except Exception as exc:  # noqa: BLE001
            columns = set()
            errors[table] = sanitize_wrds_error(exc, self.config)
        selected = [
            column
            for column in (
                "gvkey",
                "stype",
                "sid",
                "snms",
                "sales",
                "ops",
                "oiadps",
                "oibdps",
                "atlls",
                "capxs",
                "rds",
                "datadate",
                "srcdate",
                "curcds",
                "geotp",
                "naicss1",
                "sics1",
            )
            if column in columns
        ]
        if not {"gvkey", "datadate"} <= set(selected):
            table = "seg_annfund"
            try:
                columns = self._table_columns("compseg", table)
            except Exception as exc:  # noqa: BLE001
                errors[table] = sanitize_wrds_error(exc, self.config)
                return {"status": "failed", "rows": [], "row_count": 0, "errors": errors}
            selected = [
                column
                for column in (
                    "gvkey",
                    "stype",
                    "sid",
                    "sales",
                    "ops",
                    "oiadps",
                    "oibdps",
                    "atlls",
                    "capxs",
                    "rds",
                    "datadate",
                    "srcdate",
                )
                if column in columns
            ]
            if not {"gvkey", "datadate"} <= set(selected):
                return {"status": "missing_segment_columns", "rows": [], "row_count": 0, "errors": errors}
        select_sql = ", ".join(f"s.{column}" for column in selected)
        order_metric = "s.sales desc nulls last," if "sales" in columns else ""
        try:
            rows = self._fetch(
                f"""
                select {select_sql}
                from compseg.{table} s
                where s.gvkey = %s
                order by s.datadate desc, {order_metric} s.sid
                limit %s
                """,
                [gvkey, clamp_int(max_rows, minimum=1, maximum=100)],
            )
        except Exception as exc:  # noqa: BLE001
            errors[table] = sanitize_wrds_error(exc, self.config)
            return {"status": "failed", "rows": [], "row_count": 0, "errors": errors}
        return {
            "status": "matched" if rows else "no_rows",
            "table": f"compseg.{table}",
            "rows": rows,
            "row_count": len(rows),
            "errors": errors,
        }

    def _fetch_peer_comparison(self, *, company: dict[str, Any], max_peers: int = 8) -> dict[str, Any]:
        gvkey = str(company.get("gvkey") or "")
        if not gvkey:
            return {"status": "missing_gvkey", "peer_candidates": [], "peer_rows": [], "row_count": 0}

        filter_sql, params, selection_basis = peer_filter(company)
        if not filter_sql:
            return {
                "status": "missing_industry_identifier",
                "peer_candidates": [],
                "peer_rows": [],
                "row_count": 0,
                "selection_basis": selection_basis,
            }

        peer_limit = clamp_int(max_peers, minimum=1, maximum=20)
        candidates = self._fetch(
            f"""
            select
                'comp.names'::text as source,
                n.gvkey,
                n.tic,
                n.conm,
                n.cusip,
                n.cik,
                n.sic,
                n.naics,
                n.gind,
                n.gsubind,
                n.year1,
                n.year2
            from comp.names n
            where n.gvkey <> %s
              and ({filter_sql})
            order by n.year2 desc nulls last, n.conm
            limit %s
            """,
            [gvkey, *params, peer_limit],
        )

        errors: dict[str, str] = {}
        peer_rows: list[dict[str, Any]] = []
        for candidate in candidates:
            candidate_gvkey = str(candidate.get("gvkey") or "")
            if not candidate_gvkey:
                continue
            try:
                rows = self._fetch_company_fundamentals(company=candidate, table="comp.funda", max_years=1)
            except Exception as exc:  # noqa: BLE001
                errors[candidate_gvkey] = sanitize_wrds_error(exc, self.config)
                continue
            if not rows:
                continue
            latest = dict(rows[0])
            latest["peer_gvkey"] = candidate.get("gvkey")
            latest["peer_tic"] = candidate.get("tic")
            latest["peer_conm"] = candidate.get("conm")
            latest["peer_sic"] = candidate.get("sic")
            latest["peer_naics"] = candidate.get("naics")
            latest["peer_gind"] = candidate.get("gind")
            latest["peer_gsubind"] = candidate.get("gsubind")
            peer_rows.append(latest)

        return {
            "status": "matched" if peer_rows else ("no_financial_rows" if candidates else "no_peer_candidates"),
            "table": "comp.funda",
            "candidate_table": "comp.names",
            "selection_basis": selection_basis,
            "peer_candidates": candidates,
            "candidate_count": len(candidates),
            "peer_rows": peer_rows,
            "row_count": len(peer_rows),
            "errors": errors,
        }

    def _table_columns(self, library: str, table: str) -> set[str]:
        rows = self._fetch(
            "select column_name from information_schema.columns where table_schema = %s and table_name = %s",
            [library, table],
        )
        return {str(row.get("column_name")) for row in rows}

    def _connect(self) -> Any:
        if self.connection_factory is not None:
            return self.connection_factory(self.config)

        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            return psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                dbname=self.config.dbname,
                user=self.config.username,
                password=self.config.password,
                sslmode=self.config.sslmode,
                connect_timeout=self.config.connect_timeout,
                cursor_factory=RealDictCursor,
            )
        except ImportError:
            pass

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - covered by environment install
            raise RuntimeError("psycopg2-binary is not installed; run .venv/bin/pip install -e '.[dev]'") from exc

        return psycopg.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.dbname,
            user=self.config.username,
            password=self.config.password,
            sslmode=self.config.sslmode,
            connect_timeout=self.config.connect_timeout,
            row_factory=dict_row,
        )


def validate_identifier(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not IDENTIFIER_RE.fullmatch(text):
        raise ValueError(f"{label} must be a simple SQL identifier")
    return text


def validate_read_only_sql(sql: str) -> str:
    text = str(sql or "").strip()
    if not text:
        raise ValueError("sql must be non-empty")
    if "\x00" in text:
        raise ValueError("sql contains invalid characters")
    if text.endswith(";"):
        text = text[:-1].strip()
    if ";" in text:
        raise ValueError("only one SQL statement is allowed")

    lowered = text.lower().lstrip()
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        raise ValueError("WRDS agent only allows read-only SELECT/WITH queries")
    if FORBIDDEN_SQL_RE.search(text):
        raise ValueError("WRDS agent rejected a non-read-only SQL keyword")
    return text


def json_safe_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        try:
            row = dict(row)
        except (TypeError, ValueError):
            return {"value": json_safe_value(row)}
    return {str(key): json_safe_value(value) for key, value in row.items()}


def json_safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def first_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def first_non_empty(values: list[Any]) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def optional_status(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    status = data.get("status")
    return {
        "ok": result.get("ok") is True and status != "failed",
        "status": status,
        "error": result.get("error"),
        "errors": data.get("errors"),
        "row_count": data.get("row_count") or data.get("summary_row_count") or data.get("actual_row_count"),
    }


def peer_filter(company: dict[str, Any]) -> tuple[str, list[Any], list[str]]:
    """Build a deterministic Compustat peer filter from company identity fields."""
    gsubind = str(company.get("gsubind") or "").strip()
    gind = str(company.get("gind") or "").strip()
    sic = str(company.get("sic") or "").strip()
    naics = str(company.get("naics") or "").strip()
    if gsubind:
        return "coalesce(n.gsubind, '') = %s", [gsubind], [f"gsubind:{gsubind}"]
    if gind:
        return "coalesce(n.gind, '') = %s", [gind], [f"gind:{gind}"]
    if sic:
        return "coalesce(n.sic, '') = %s", [sic], [f"sic:{sic}"]
    if len(naics) >= 4:
        prefix = naics[:4]
        return "left(coalesce(n.naics, ''), 4) = %s", [prefix], [f"naics4:{prefix}"]
    if len(naics) >= 2:
        prefix = naics[:2]
        return "left(coalesce(n.naics, ''), 2) = %s", [prefix], [f"naics2:{prefix}"]
    return "", [], []


def format_wrds_identifier_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def coerce_wrds_int_identifier(value: Any) -> int:
    text = format_wrds_identifier_number(value)
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"WRDS identifier must be an integer-like value: {value}") from exc


def sanitize_wrds_error(exc: Exception, config: WRDSConfig) -> str:
    text = str(exc) or type(exc).__name__
    for secret in (config.password, config.username):
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:500]


def preview_sql(sql: str, *, limit: int = 240) -> str:
    text = " ".join(str(sql or "").split())
    return text if len(text) <= limit else text[:limit] + "..."


def normalize_discovery_patterns(libraries: list[str] | None) -> list[str]:
    if not libraries:
        return list(WRDS_DISCOVERY_PATTERNS)
    patterns: list[str] = []
    for value in libraries:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if not re.fullmatch(r"[a-z0-9_]+", text):
            continue
        patterns.append(text)
    return unique_terms(patterns) or list(WRDS_DISCOVERY_PATTERNS)


def classify_wrds_capabilities(discovered_libraries: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    capabilities: dict[str, dict[str, Any]] = {}
    for capability, spec in WRDS_CAPABILITY_TARGETS.items():
        library_patterns = spec["library_patterns"]
        table_patterns = spec["table_patterns"]
        matched_libraries: list[str] = []
        matched_tables: list[dict[str, str]] = []
        for library_name, library_info in discovered_libraries.items():
            library_lower = library_name.lower()
            library_matches = any(pattern in library_lower for pattern in library_patterns)
            if not library_matches:
                continue
            table_matches = []
            for table in library_info.get("tables", []):
                if not isinstance(table, dict):
                    continue
                table_name = str(table.get("table_name") or "")
                table_lower = table_name.lower()
                if any(pattern in table_lower for pattern in table_patterns):
                    table_matches.append(
                        {
                            "library": library_name,
                            "table": table_name,
                            "table_type": str(table.get("table_type") or ""),
                        }
                    )
            matched_libraries.append(library_name)
            matched_tables.extend(table_matches)
        capabilities[capability] = {
            "available": bool(matched_libraries),
            "libraries": sorted(set(matched_libraries)),
            "tables": matched_tables[:25],
            "table_count": len(matched_tables),
            "library_patterns": list(library_patterns),
            "table_patterns": list(table_patterns),
        }
    return capabilities


def company_search_terms(query: str) -> list[str]:
    text = str(query or "").strip()
    if not text:
        return []

    lowered = text.lower()
    terms: list[str] = []
    for alias, values in COMPANY_ALIASES.items():
        if alias in lowered or alias in text:
            terms.extend(values)

    cleaned = clean_company_query(text)
    if cleaned:
        terms.append(cleaned)

    ticker = extract_ticker_like_token(text)
    if ticker:
        terms.insert(0, ticker)

    return unique_terms(terms)


def clean_company_query(value: str) -> str:
    text = str(value or "").strip()
    replacements = (
        "深度分析",
        "分析一下",
        "分析",
        "研究",
        "报告",
        "估值",
        "价值投资",
        "是否符合",
        "财务数据",
        "财务",
        "公司",
        "股票",
        "专业数据",
        "专业信息",
        "查询",
        "获取",
        "用",
        "通过",
    )
    for item in replacements:
        text = text.replace(item, " ")
    text = COMPANY_QUERY_STOPWORDS_RE.sub(" ", text)
    text = re.sub(r"[，,。；;：:（）()【】\[\]{}\"'`]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_ticker_like_token(value: str) -> str | None:
    text = str(value or "").upper()
    stock_code = re.search(r"\b\d{6}\b", text)
    if stock_code:
        return stock_code.group(0)
    ticker = re.search(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b", text)
    if ticker:
        return ticker.group(0).split(".", 1)[0]
    return None


def unique_terms(values: list[str]) -> list[str]:
    seen = set()
    terms = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.upper()
        if key in seen:
            continue
        seen.add(key)
        terms.append(text)
    return terms


def company_candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float]:
    score = candidate.get("match_score")
    year = candidate.get("year2")
    try:
        score_number = float(score)
    except (TypeError, ValueError):
        score_number = 0
    try:
        year_number = float(year)
    except (TypeError, ValueError):
        year_number = 0
    if year_number and year_number < 2000:
        score_number -= 50
    elif year_number >= 2020:
        score_number += 10
    return score_number, year_number


def add_financial_ratios(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enhanced = []
    ascending = sorted(rows, key=lambda row: str(row.get("datadate") or ""))
    previous_by_date: dict[str, dict[str, Any]] = {}
    previous = None
    for row in ascending:
        dated_key = str(row.get("datadate") or "")
        enriched = dict(row)
        sale = numeric(enriched.get("sale") if enriched.get("sale") is not None else enriched.get("revt"))
        cogs = numeric(enriched.get("cogs"))
        gp = numeric(enriched.get("gp"))
        ni = numeric(enriched.get("ni") if enriched.get("ni") is not None else enriched.get("ib"))
        at = numeric(enriched.get("at"))
        ceq = numeric(enriched.get("ceq"))
        lt = numeric(enriched.get("lt"))
        dltt = numeric(enriched.get("dltt"))
        dlc = numeric(enriched.get("dlc"))
        oancf = numeric(enriched.get("oancf"))
        capx = numeric(enriched.get("capx"))
        ebit = numeric(enriched.get("ebit"))
        dp = numeric(enriched.get("dp"))
        debt = sum(value for value in (dltt, dlc) if value is not None)
        if debt == 0 and lt is not None:
            debt = lt
        gross_profit = gp if gp is not None else (sale - cogs if sale is not None and cogs is not None else None)
        gross_profit_after_depreciation = (
            gross_profit - dp if gross_profit is not None and dp is not None else None
        )
        gross_margin_before_depreciation = safe_divide(gross_profit, sale)
        gross_margin_after_depreciation = safe_divide(gross_profit_after_depreciation, sale)
        fcf = oancf - capx if oancf is not None and capx is not None else None
        previous_sale = numeric(previous.get("sale") if previous else None) if previous else None
        previous_ni = numeric(previous.get("ni") if previous else None) if previous else None
        enriched["calculated"] = {
            "gross_profit": round_number(gross_profit),
            "gross_profit_after_depreciation": round_number(gross_profit_after_depreciation),
            "gross_margin": round_number(gross_margin_before_depreciation),
            "gross_margin_before_depreciation": round_number(gross_margin_before_depreciation),
            "gross_margin_after_depreciation": round_number(gross_margin_after_depreciation),
            "reported_gross_margin_candidate": round_number(
                select_reported_gross_margin_candidate(
                    gross_margin_before_depreciation,
                    gross_margin_after_depreciation,
                )
            ),
            "operating_margin": round_number(safe_divide(ebit, sale)),
            "net_margin": round_number(safe_divide(ni, sale)),
            "roe": round_number(safe_divide(ni, ceq)),
            "roa": round_number(safe_divide(ni, at)),
            "debt_to_assets": round_number(safe_divide(debt, at)),
            "free_cash_flow": round_number(fcf),
            "fcf_margin": round_number(safe_divide(fcf, sale)),
            "revenue_growth_yoy": round_number(safe_divide(sale - previous_sale, previous_sale))
            if sale is not None and previous_sale not in (None, 0)
            else None,
            "net_income_growth_yoy": round_number(safe_divide(ni - previous_ni, previous_ni))
            if ni is not None and previous_ni not in (None, 0)
            else None,
        }
        previous_by_date[dated_key] = enriched
        previous = enriched
    for row in rows:
        enhanced.append(previous_by_date.get(str(row.get("datadate") or ""), row))
    return enhanced


def add_quarterly_financial_ratios(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enhanced = []
    ascending = sorted(rows, key=lambda row: str(row.get("datadate") or ""))
    previous_by_date: dict[str, dict[str, Any]] = {}
    previous = None
    for row in ascending:
        dated_key = str(row.get("datadate") or "")
        enriched = dict(row)
        sale = numeric(enriched.get("saleq") if enriched.get("saleq") is not None else enriched.get("revtq"))
        cogs = numeric(enriched.get("cogsq"))
        gp = numeric(enriched.get("gpq"))
        ni = numeric(enriched.get("niq") if enriched.get("niq") is not None else enriched.get("ibq"))
        at = numeric(enriched.get("atq"))
        ceq = numeric(enriched.get("ceqq"))
        dltt = numeric(enriched.get("dlttq"))
        dlc = numeric(enriched.get("dlcq"))
        oancf = numeric(enriched.get("oancfy"))
        capx = numeric(enriched.get("capxy"))
        oiadp = numeric(enriched.get("oiadpq"))
        dp = numeric(enriched.get("dpq"))
        debt = sum(value for value in (dltt, dlc) if value is not None)
        gross_profit = gp if gp is not None else (sale - cogs if sale is not None and cogs is not None else None)
        gross_profit_after_depreciation = (
            gross_profit - dp if gross_profit is not None and dp is not None else None
        )
        gross_margin_before_depreciation = safe_divide(gross_profit, sale)
        gross_margin_after_depreciation = safe_divide(gross_profit_after_depreciation, sale)
        fcf_ytd = oancf - capx if oancf is not None and capx is not None else None
        previous_sale = numeric(previous.get("saleq") if previous else None) if previous else None
        previous_ni = numeric(previous.get("niq") if previous else None) if previous else None
        enriched["calculated"] = {
            "gross_profit": round_number(gross_profit),
            "gross_profit_after_depreciation": round_number(gross_profit_after_depreciation),
            "gross_margin": round_number(gross_margin_before_depreciation),
            "gross_margin_before_depreciation": round_number(gross_margin_before_depreciation),
            "gross_margin_after_depreciation": round_number(gross_margin_after_depreciation),
            "reported_gross_margin_candidate": round_number(
                select_reported_gross_margin_candidate(
                    gross_margin_before_depreciation,
                    gross_margin_after_depreciation,
                )
            ),
            "operating_margin": round_number(safe_divide(oiadp, sale)),
            "net_margin": round_number(safe_divide(ni, sale)),
            "roe": round_number(safe_divide(ni, ceq)),
            "roa": round_number(safe_divide(ni, at)),
            "debt_to_assets": round_number(safe_divide(debt, at)),
            "free_cash_flow_ytd": round_number(fcf_ytd),
            "revenue_growth_qoq": round_number(safe_divide(sale - previous_sale, previous_sale))
            if sale is not None and previous_sale not in (None, 0)
            else None,
            "net_income_growth_qoq": round_number(safe_divide(ni - previous_ni, previous_ni))
            if ni is not None and previous_ni not in (None, 0)
            else None,
        }
        previous_by_date[dated_key] = enriched
        previous = enriched
    for row in rows:
        enhanced.append(previous_by_date.get(str(row.get("datadate") or ""), row))
    return enhanced


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def select_reported_gross_margin_candidate(
    before_depreciation: float | None,
    after_depreciation: float | None,
) -> float | None:
    """Prefer a filing-like gross margin when Compustat exposes D&A separately."""
    if before_depreciation is None:
        return after_depreciation
    if after_depreciation is None:
        return before_depreciation
    if before_depreciation - after_depreciation >= 0.1:
        return after_depreciation
    return before_depreciation


def round_number(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)
