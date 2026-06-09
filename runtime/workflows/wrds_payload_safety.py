from __future__ import annotations

from typing import Any


RAW_WRDS_PUBLIC_KEYS = {
    "rows",
    "quarterly_rows",
    "daily_rows",
    "ccm_links",
    "gvkey_rows",
    "company_rows",
    "symbol_rows",
    "description_rows",
    "actual_rows",
    "segment_rows",
    "tables",
    "columns",
}


def public_safe_execution_log(execution_log: Any) -> list[dict[str, Any]]:
    if not isinstance(execution_log, list):
        return []
    safe_log = []
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        safe_calls = []
        for call in step.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            if str(call.get("name") or "").startswith("wrds_"):
                result = public_safe_wrds_result(result)
            safe_calls.append({**call, "result": result})
        safe_log.append({**step, "tool_calls": safe_calls})
    return safe_log


def public_safe_wrds_result(wrds_result: Any) -> Any:
    if not isinstance(wrds_result, dict):
        return wrds_result
    sanitized = sanitize_wrds_public_payload(wrds_result)
    if isinstance(sanitized, dict):
        sanitized["raw_data_redacted"] = True
        sanitized["redaction_reason"] = "Raw WRDS rows are withheld from public API/trace responses; use metric_registry for report-ready values."
    return sanitized


def sanitize_wrds_public_payload(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {item_key: sanitize_wrds_public_payload(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        if key in RAW_WRDS_PUBLIC_KEYS or key.endswith("_rows"):
            return {
                "redacted": True,
                "count": len(value),
                "reason": "raw WRDS row data is not exposed through public run responses",
            }
        return [sanitize_wrds_public_payload(item) for item in value]
    return value


def summarize_wrds_result_for_model(wrds_result: Any) -> dict[str, Any]:
    if not isinstance(wrds_result, dict):
        return {"status": "missing"}
    data = wrds_result.get("data") if isinstance(wrds_result.get("data"), dict) else {}
    company_financials = data.get("company_financials") if isinstance(data.get("company_financials"), dict) else {}
    if not company_financials:
        return {
            "ok": wrds_result.get("ok"),
            "status": "no_company_financials",
        }
    company = company_financials.get("company") if isinstance(company_financials.get("company"), dict) else {}
    candidates = company_financials.get("candidates") if isinstance(company_financials.get("candidates"), list) else []
    return {
        "ok": wrds_result.get("ok"),
        "status": company_financials.get("status"),
        "company": {
            "gvkey": company.get("gvkey"),
            "ticker": company.get("tic"),
            "name": company.get("conm"),
            "cik": company.get("cik"),
            "sic": company.get("sic"),
            "naics": company.get("naics"),
        },
        "candidate_count": len(candidates),
        "row_count": company_financials.get("row_count"),
        "quarterly_row_count": company_financials.get("quarterly_row_count"),
        "table": company_financials.get("table"),
        "quarterly_table": company_financials.get("quarterly_table"),
        "data_packages": company_financials.get("data_packages") or [],
        "note": "Raw WRDS rows are intentionally withheld from model agents; use metric_registry.derived_metrics.",
    }


def audit_safe_wrds_result_summary(wrds_result: Any) -> dict[str, Any]:
    if not isinstance(wrds_result, dict):
        return {}
    data = wrds_result.get("data") if isinstance(wrds_result.get("data"), dict) else {}
    company_financials = data.get("company_financials") if isinstance(data.get("company_financials"), dict) else {}
    if company_financials:
        company = company_financials.get("company") if isinstance(company_financials.get("company"), dict) else {}
        return {
            "ok": wrds_result.get("ok"),
            "status": company_financials.get("status"),
            "company": {
                "gvkey": company.get("gvkey"),
                "tic": company.get("tic"),
                "conm": company.get("conm"),
                "source": company.get("source"),
                "match_score": company.get("match_score"),
            },
            "row_count": company_financials.get("row_count"),
            "table": company_financials.get("table"),
            "tool_call_count": len(data.get("tool_calls", [])) if isinstance(data.get("tool_calls"), list) else None,
        }
    return {
        "ok": wrds_result.get("ok"),
        "error": truncate_string(wrds_result.get("error"), 500),
        "row_count": data.get("row_count"),
        "truncated": data.get("truncated"),
        "columns": data.get("columns")[:20] if isinstance(data.get("columns"), list) else None,
        "libraries_count": data.get("count") if "libraries" in data else None,
        "table": data.get("table"),
        "library": data.get("library"),
        "sql_preview": truncate_string(data.get("sql_preview"), 300),
    }


def truncate_string(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
