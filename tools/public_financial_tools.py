from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from datetime import date, timedelta
from typing import Any

import httpx

from runtime.redaction import redact_secret_text
from tools.safe_tools import ToolResult


SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
KENNETH_FRENCH_ZIP_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{dataset}_CSV.zip"

DEFAULT_SEC_USER_AGENT = "pheroos/0.1 (configure SEC_EDGAR_USER_AGENT for production contact)"
DEFAULT_TIMEOUT_SECONDS = 20


class PublicFinancialDataTools:
    """Read-only public financial data adapters for approved fixed providers."""

    def __init__(
        self,
        *,
        fred_api_key: str | None = None,
        sec_user_agent: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.fred_api_key = fred_api_key or os.getenv("FRED_API_KEY")
        self.sec_user_agent = sec_user_agent or os.getenv("SEC_EDGAR_USER_AGENT") or DEFAULT_SEC_USER_AGENT
        self.timeout_seconds = timeout_seconds

    def sec_company_search(self, *, query: str, max_results: int = 10) -> ToolResult:
        query = str(query or "").strip()
        max_results = clamp_int(max_results, minimum=1, maximum=50)
        if not query:
            return ToolResult(False, {"query": query}, "query is required")
        response = self._get_json(SEC_COMPANY_TICKERS_URL, headers=self._sec_headers())
        if not response.ok:
            return response
        raw = response.data.get("json")
        companies = list(raw.values()) if isinstance(raw, dict) else []
        matches = rank_sec_company_matches(companies, query)[:max_results]
        return ToolResult(
            True,
            {
                "provider": "sec_edgar",
                "source_url": SEC_COMPANY_TICKERS_URL,
                "query": query,
                "results": matches,
                "row_count": len(matches),
                "limitations": [
                    "SEC company_tickers.json is an identity resolver only; use company facts or submissions for filing data."
                ],
            },
        )

    def sec_company_facts(self, *, query: str | None = None, cik: str | int | None = None) -> ToolResult:
        cik_value = normalize_cik(cik)
        resolver: dict[str, Any] | None = None
        if not cik_value and query:
            search = self.sec_company_search(query=query, max_results=1)
            if not search.ok:
                return search
            results = search.data.get("results") if isinstance(search.data, dict) else []
            if not results:
                return ToolResult(False, {"query": query}, "no SEC company match found")
            resolver = results[0]
            cik_value = normalize_cik(resolver.get("cik"))
        if not cik_value:
            return ToolResult(False, {"query": query, "cik": cik}, "query or cik is required")
        url = SEC_COMPANY_FACTS_URL.format(cik=cik_value)
        response = self._get_json(url, headers=self._sec_headers())
        if not response.ok:
            return response
        payload = response.data.get("json") if isinstance(response.data, dict) else {}
        facts = payload.get("facts") if isinstance(payload, dict) else {}
        summary = summarize_sec_company_facts(facts)
        return ToolResult(
            True,
            {
                "provider": "sec_edgar",
                "source_url": url,
                "cik": cik_value,
                "company": {
                    "name": payload.get("entityName") if isinstance(payload, dict) else None,
                    "cik": cik_value,
                    "resolver": resolver,
                },
                "fact_summary": summary,
                "limitations": [
                    "Company facts are SEC XBRL facts, not normalized WRDS/Compustat metric-registry values.",
                    "Values must pass Data Gate before being used in formal valuation conclusions.",
                ],
            },
        )

    def sec_recent_filings(
        self,
        *,
        query: str | None = None,
        cik: str | int | None = None,
        forms: list[str] | str | None = None,
        count: int = 20,
    ) -> ToolResult:
        cik_value = normalize_cik(cik)
        if not cik_value and query:
            search = self.sec_company_search(query=query, max_results=1)
            if not search.ok:
                return search
            results = search.data.get("results") if isinstance(search.data, dict) else []
            if not results:
                return ToolResult(False, {"query": query}, "no SEC company match found")
            cik_value = normalize_cik(results[0].get("cik"))
        if not cik_value:
            return ToolResult(False, {"query": query, "cik": cik}, "query or cik is required")
        url = SEC_SUBMISSIONS_URL.format(cik=cik_value)
        response = self._get_json(url, headers=self._sec_headers())
        if not response.ok:
            return response
        payload = response.data.get("json") if isinstance(response.data, dict) else {}
        recent = payload.get("filings", {}).get("recent", {}) if isinstance(payload, dict) else {}
        wanted_forms = normalize_forms(forms)
        filings = []
        form_values = recent.get("form") if isinstance(recent, dict) else []
        accession_values = recent.get("accessionNumber") if isinstance(recent, dict) else []
        filing_dates = recent.get("filingDate") if isinstance(recent, dict) else []
        report_dates = recent.get("reportDate") if isinstance(recent, dict) else []
        primary_documents = recent.get("primaryDocument") if isinstance(recent, dict) else []
        for index, form in enumerate(form_values if isinstance(form_values, list) else []):
            form_text = str(form)
            if wanted_forms and form_text.upper() not in wanted_forms:
                continue
            accession = safe_list_get(accession_values, index)
            primary = safe_list_get(primary_documents, index)
            filings.append(
                {
                    "form": form_text,
                    "filing_date": safe_list_get(filing_dates, index),
                    "report_date": safe_list_get(report_dates, index),
                    "accession_number": accession,
                    "primary_document": primary,
                    "document_url": sec_document_url(cik_value, accession, primary),
                }
            )
            if len(filings) >= clamp_int(count, minimum=1, maximum=100):
                break
        return ToolResult(
            True,
            {
                "provider": "sec_edgar",
                "source_url": url,
                "cik": cik_value,
                "company": payload.get("name") if isinstance(payload, dict) else None,
                "filings": filings,
                "row_count": len(filings),
            },
        )

    def fred_series(
        self,
        *,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 120,
    ) -> ToolResult:
        series_id = str(series_id or "").strip().upper()
        if not series_id:
            return ToolResult(False, {"series_id": series_id}, "series_id is required")
        if not self.fred_api_key:
            return ToolResult(
                False,
                {"provider": "fred", "series_id": series_id, "missing_connection": "fred"},
                "FRED API key is not configured. Add a FRED connection through the AI OS connection flow.",
            )
        params = {
            "series_id": series_id,
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": str(clamp_int(limit, minimum=1, maximum=1000)),
        }
        if start_date:
            params["observation_start"] = str(start_date)
        if end_date:
            params["observation_end"] = str(end_date)
        response = self._get_json(FRED_OBSERVATIONS_URL, params=params)
        if not response.ok:
            return response
        payload = response.data.get("json") if isinstance(response.data, dict) else {}
        observations = payload.get("observations") if isinstance(payload, dict) else []
        return ToolResult(
            True,
            {
                "provider": "fred",
                "series_id": series_id,
                "source_url": "https://fred.stlouisfed.org/series/" + series_id,
                "observations": observations if isinstance(observations, list) else [],
                "row_count": len(observations) if isinstance(observations, list) else 0,
                "units": payload.get("units") if isinstance(payload, dict) else None,
            },
        )

    def market_price_history(
        self,
        *,
        symbol: str,
        source: str = "stooq",
        start_date: str | None = None,
        end_date: str | None = None,
        interval: str = "daily",
        max_rows: int = 250,
    ) -> ToolResult:
        source = str(source or "stooq").strip().lower()
        if source == "yfinance":
            return self._yfinance_price_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                max_rows=max_rows,
            )
        return self._stooq_price_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            max_rows=max_rows,
        )

    def kenneth_french_factors(self, *, dataset: str = "F-F_Research_Data_Factors", max_rows: int = 120) -> ToolResult:
        dataset = sanitize_kenneth_french_dataset(dataset)
        max_rows = clamp_int(max_rows, minimum=1, maximum=5000)
        url = KENNETH_FRENCH_ZIP_URL.format(dataset=dataset)
        response = self._get_bytes(url)
        if not response.ok:
            return response
        try:
            rows = parse_kenneth_french_zip(response.data["content"], max_rows=max_rows)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"provider": "kenneth_french", "dataset": dataset}, sanitize_error(exc))
        return ToolResult(
            True,
            {
                "provider": "kenneth_french",
                "dataset": dataset,
                "source_url": url,
                "rows": rows,
                "row_count": len(rows),
                "limitations": [
                    "Kenneth French data are factor research datasets; align frequency and units before using in valuation or risk models."
                ],
            },
        )

    def _stooq_price_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        interval: str,
        max_rows: int,
    ) -> ToolResult:
        symbol = normalize_stooq_symbol(symbol)
        if not symbol:
            return ToolResult(False, {"symbol": symbol}, "symbol is required")
        if str(interval or "daily").lower() not in {"daily", "d"}:
            return ToolResult(False, {"interval": interval}, "Stooq adapter currently supports daily interval only")
        end = normalize_yyyymmdd(end_date) or date.today().strftime("%Y%m%d")
        start = normalize_yyyymmdd(start_date) or (date.today() - timedelta(days=365 * 2)).strftime("%Y%m%d")
        params = {"s": symbol, "i": "d", "d1": start, "d2": end}
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.get(STOOQ_DAILY_URL, params=params)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"provider": "stooq", "symbol": symbol}, sanitize_error(exc))
        rows = parse_csv_dicts(response.text)
        rows = rows[-clamp_int(max_rows, minimum=1, maximum=5000) :]
        return ToolResult(
            True,
            {
                "provider": "stooq",
                "symbol": symbol,
                "source_url": str(response.url),
                "rows": rows,
                "row_count": len(rows),
                "limitations": ["Stooq data should be treated as market-data evidence, not audited fundamentals."],
            },
        )

    def _yfinance_price_history(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        interval: str,
        max_rows: int,
    ) -> ToolResult:
        try:
            import yfinance as yf  # type: ignore
        except Exception:
            return ToolResult(
                False,
                {"provider": "yfinance", "symbol": symbol, "optional_dependency": "yfinance"},
                "yfinance is not installed. Use source='stooq' or install the optional yfinance dependency.",
            )
        ticker = yf.Ticker(str(symbol).strip())
        history = ticker.history(
            start=start_date,
            end=end_date,
            interval="1d" if str(interval or "daily").lower() in {"daily", "d"} else str(interval),
        )
        rows = []
        for index, row in history.tail(clamp_int(max_rows, minimum=1, maximum=5000)).iterrows():
            rows.append(
                {
                    "Date": str(index.date() if hasattr(index, "date") else index),
                    "Open": none_or_float(row.get("Open")),
                    "High": none_or_float(row.get("High")),
                    "Low": none_or_float(row.get("Low")),
                    "Close": none_or_float(row.get("Close")),
                    "Volume": none_or_float(row.get("Volume")),
                }
            )
        return ToolResult(True, {"provider": "yfinance", "symbol": symbol, "rows": rows, "row_count": len(rows)})

    def _sec_headers(self) -> dict[str, str]:
        return {"User-Agent": self.sec_user_agent, "Accept-Encoding": "gzip, deflate", "Host": ""}

    def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> ToolResult:
        try:
            request_headers = {key: value for key, value in (headers or {}).items() if value}
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False, headers=request_headers) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return ToolResult(True, {"url": str(response.url), "json": response.json()})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"url": url}, sanitize_error(exc))

    def _get_bytes(self, url: str) -> ToolResult:
        try:
            with httpx.Client(timeout=self.timeout_seconds, trust_env=False) as client:
                response = client.get(url)
                response.raise_for_status()
                return ToolResult(True, {"url": str(response.url), "content": response.content})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, {"url": url}, sanitize_error(exc))


def rank_sec_company_matches(companies: list[Any], query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    output = []
    for item in companies:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip()
        title = str(item.get("title") or "").strip()
        cik = normalize_cik(item.get("cik_str"))
        haystack = f"{ticker} {title} {cik}".lower()
        if needle not in haystack and needle.upper() != ticker.upper():
            continue
        score = 100 if needle.upper() == ticker.upper() else 70 if title.lower().startswith(needle) else 50
        output.append({"ticker": ticker, "name": title, "cik": cik, "match_score": score})
    return sorted(output, key=lambda row: (-int(row.get("match_score") or 0), row.get("ticker") or ""))


def summarize_sec_company_facts(facts: Any) -> dict[str, Any]:
    if not isinstance(facts, dict):
        return {"taxonomy_count": 0, "concept_count": 0, "available_concepts": []}
    concepts = []
    for taxonomy, values in facts.items():
        if isinstance(values, dict):
            for concept in values:
                concepts.append(f"{taxonomy}:{concept}")
    important = [
        item
        for item in concepts
        if any(term in item.lower() for term in ("revenue", "sales", "netincome", "assets", "liabilities", "cash", "earnings"))
    ]
    return {
        "taxonomy_count": len(facts),
        "concept_count": len(concepts),
        "available_concepts": important[:50],
    }


def parse_kenneth_french_zip(content: bytes, *, max_rows: int) -> list[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("Kenneth French zip did not contain a CSV file")
        text = archive.read(csv_names[0]).decode("utf-8", errors="replace")
    return parse_kenneth_french_csv(text, max_rows=max_rows)


def parse_kenneth_french_csv(text: str, *, max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    headers: list[str] | None = None
    for raw_row in csv.reader(io.StringIO(text)):
        row = [cell.strip() for cell in raw_row]
        if not row or not any(row):
            if headers and rows:
                break
            continue
        if headers is None:
            if len(row) >= 2 and any("Mkt" in cell or "RF" == cell for cell in row):
                headers = ["date", *[cell or f"factor_{index}" for index, cell in enumerate(row[1:], start=1)]]
            continue
        if not re.fullmatch(r"\d{4,8}", row[0] or ""):
            if rows:
                break
            continue
        values = row[: len(headers)]
        rows.append({header: parse_numeric(value) for header, value in zip(headers, values, strict=False)})
        if len(rows) >= max_rows:
            break
    return rows


def parse_csv_dicts(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        if not row or all(not value for value in row.values()):
            continue
        rows.append({key: parse_numeric(value) for key, value in row.items()})
    return rows


def normalize_cik(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if not text:
        return ""
    return text.zfill(10)[-10:]


def normalize_forms(forms: list[str] | str | None) -> set[str]:
    if forms is None:
        return set()
    if isinstance(forms, str):
        forms = [item.strip() for item in forms.split(",")]
    return {str(item).strip().upper() for item in forms if str(item).strip()}


def sec_document_url(cik: str, accession: Any, primary_document: Any) -> str | None:
    accession_text = str(accession or "").strip()
    document = str(primary_document or "").strip()
    if not accession_text or not document:
        return None
    accession_nodash = accession_text.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{document}"


def normalize_stooq_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().lower()
    if not text:
        return ""
    if "." not in text:
        return f"{text}.us"
    return text


def normalize_yyyymmdd(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 8:
        return digits
    return None


def sanitize_kenneth_french_dataset(value: str) -> str:
    text = str(value or "F-F_Research_Data_Factors").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", text):
        raise ValueError("dataset must contain only letters, numbers, underscores, dots, and hyphens")
    return text


def safe_list_get(value: Any, index: int) -> Any:
    return value[index] if isinstance(value, list) and index < len(value) else None


def parse_numeric(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", ".", "-99.99", "-999"}:
        return None
    try:
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        return float(text)
    except ValueError:
        return text


def none_or_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp_int(value: Any, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def sanitize_error(exc: Exception) -> str:
    return redact_secret_text(str(exc), limit=500)
