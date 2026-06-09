from __future__ import annotations

import json
from pathlib import Path

from runtime.audit_log import append_run_audit, build_audit_record, read_run_audit_record


def test_build_audit_record_summarizes_run_without_full_tool_text() -> None:
    record = build_audit_record(
        {
            "run_id": "run-1",
            "task": "Analyze WuXi AppTec",
            "orchestration": {"task_type": "investment", "depth": "standard", "required_agents": {"research": True}},
            "selected_skills": [{"name": "web-research"}],
            "plan": [{"id": "1", "title": "Search", "action": "Search web", "tool_calls": [{"name": "web_search"}]}],
            "execution_log": [
                {
                    "step_id": "1",
                    "title": "Search",
                    "tool_calls": [
                        {
                            "name": "fetch_url",
                            "args": {"url": "https://example.com", "content": "secret"},
                            "result": {
                                "ok": True,
                                "data": {
                                    "url": "https://example.com",
                                    "title": "Example",
                                    "text": "long fetched body",
                                    "text_quality": "good",
                                    "word_count": 500,
                                },
                            },
                        }
                    ],
                }
            ],
            "research_brief": {"status": "completed", "key_facts": ["fact"], "sources": [{"url": "https://example.com"}]},
            "quant_analysis": {"status": "skipped", "missing_data": ["FCF"]},
            "domain_analysis": {"status": "completed", "domain": "investment", "judgment": "watchlist"},
            "review": {"status": "pass"},
            "final": "final answer",
            "agent_metrics": [
                {
                    "agent": "orchestrator",
                    "model": "local-fast",
                    "model_used": True,
                    "duration_ms": 12.5,
                    "status": "completed",
                    "failure_reason": None,
                }
            ],
        }
    )

    assert record["run_id"] == "run-1"
    assert record["status"] == "completed"
    assert record["selected_skills"] == ["web-research"]
    assert record["agent_metrics"][0]["model"] == "local-fast"
    assert record["tool_calls"][0]["args"]["content"] == "[redacted]"
    assert "text" not in record["tool_calls"][0]
    assert record["orchestration"]["task_type"] == "investment"
    assert record["research_brief"]["key_facts"] == ["fact"]
    assert record["domain_analysis"]["judgment"] == "watchlist"


def test_build_audit_record_includes_generic_blocked_conclusion_targets() -> None:
    record = build_audit_record(
        {
            "run_id": "run-generic-audit",
            "quorum_trace": {
                "status": "blocked_to_fallback",
                "blocked_conclusion_targets": ["decision:peer_valuation"],
                "formal_valuation_blocked": False,
            },
        }
    )

    governance = record["swarm_governance"]

    assert governance["blocked_conclusion_targets"] == ["decision:peer_valuation"]
    assert governance["formal_valuation_blocked"] is False


def test_audit_record_preserves_legacy_publication_allowed_field() -> None:
    record = build_audit_record(
        {
            "run_id": "run-legacy-gate-audit",
            "data_gate": {"status": "PASS", "report_publication_allowed": True},
        }
    )

    assert record["data_gate"]["report_publication_allowed"] is True


def test_audit_record_summarizes_generic_agent_outputs() -> None:
    record = build_audit_record(
        {
            "run_id": "run-agent-output-audit",
            "agent_outputs": {
                "toy_reviewer": {
                    "status": "completed",
                    "score": 0.8,
                    "confidence": "medium",
                    "thesis": "Toy output is acceptable.",
                    "missing_data": ["verifier note"],
                }
            },
        }
    )

    assert "committee_outputs" not in record
    assert record["agent_output_source"] == "agent_outputs"
    assert record["agent_outputs"]["toy_reviewer"]["status"] == "completed"
    assert record["agent_outputs"]["toy_reviewer"]["thesis"] == "Toy output is acceptable."
    assert record["legacy_agent_outputs"] == {}


def test_audit_record_marks_legacy_agent_output_compatibility_source() -> None:
    record = build_audit_record(
        {
            "run_id": "run-legacy-output-audit",
            "committee_outputs": {
                "legacy_reviewer": {
                    "status": "completed",
                    "thesis": "Legacy output is retained only for compatibility.",
                }
            },
        }
    )

    assert "committee_outputs" not in record
    assert record["agent_output_source"] == "legacy_agent_outputs"
    assert record["agent_outputs"]["legacy_reviewer"]["status"] == "completed"
    assert (
        record["legacy_agent_outputs"]["legacy_reviewer"]["thesis"]
        == "Legacy output is retained only for compatibility."
    )


def test_audit_record_summarizes_generic_agent_decision() -> None:
    record = build_audit_record(
        {
            "run_id": "run-agent-decision-audit",
            "agent_decision": {
                "status": "completed",
                "decision": "Approve generic artifact.",
                "final_decision": "Approve",
                "core_thesis": "Generic decision should be authoritative.",
            },
            "committee_decision": {
                "status": "completed",
                "decision": "Reject legacy artifact.",
                "final_decision": "Reject",
            },
        }
    )

    assert "committee_decision" not in record
    assert record["agent_decision_source"] == "agent_decision"
    assert record["agent_decision"]["decision"] == "Approve generic artifact."
    assert record["agent_decision"]["final_decision"] == "Approve"
    assert record["legacy_agent_decision"]["decision"] == "Reject legacy artifact."


def test_audit_record_marks_legacy_agent_decision_compatibility_source() -> None:
    record = build_audit_record(
        {
            "run_id": "run-legacy-decision-audit",
            "committee_decision": {
                "status": "completed",
                "decision": "Legacy decision is retained only for compatibility.",
                "final_decision": "Watch",
            },
        }
    )

    assert "committee_decision" not in record
    assert record["agent_decision_source"] == "legacy_agent_decision"
    assert record["agent_decision"]["decision"] == "Legacy decision is retained only for compatibility."
    assert (
        record["legacy_agent_decision"]["decision"]
        == "Legacy decision is retained only for compatibility."
    )


def test_audit_record_summarizes_wrds_without_raw_rows() -> None:
    record = build_audit_record(
        {
            "run_id": "run-wrds-audit",
            "wrds_result": {
                "ok": True,
                "data": {
                    "company_financials": {
                        "status": "complete",
                        "company": {"gvkey": "123", "tic": "ABC", "conm": "ABC Corp"},
                        "rows": [{"sale": 123, "ni": 4}],
                        "quarterly_rows": [{"saleq": 5}],
                        "row_count": 1,
                        "table": "comp.funda",
                    },
                    "tool_calls": [{"name": "wrds_company_financials"}],
                },
            },
        }
    )

    summary = record["wrds_result"]

    assert summary["ok"] is True
    assert summary["status"] == "complete"
    assert summary["company"]["tic"] == "ABC"
    assert summary["row_count"] == 1
    assert summary["tool_call_count"] == 1
    assert "rows" not in summary
    assert "quarterly_rows" not in json.dumps(summary)
    assert "sale" not in json.dumps(summary)


def test_append_run_audit_writes_jsonl(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "agent_runs.jsonl"
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "true")

    append_run_audit({"run_id": "run-1", "task": "hello", "final": "done"})

    line = path.read_text(encoding="utf-8").strip()
    assert json.loads(line)["run_id"] == "run-1"


def test_audit_record_is_recursively_redacted_before_persist(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "agent_runs.jsonl"
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "true")
    secret = "sk-cp-T145hjOnntfujsz_n4wWcbgf4-dFpRZGx_UZZHooKoPSDqkNQGcQY5O91Ep1-a5Gjr_5alc0lSmS2Tmap3thhXU7yuz16-5ZwjI3YYAQ2yoBePlU1BDsn3s"

    append_run_audit(
        {
            "run_id": "run-redact",
            "task": "hello",
            "review": {"status": "pass", "issues": [f"copied {secret}"]},
            "final": f"done {secret}",
        }
    )

    text = path.read_text(encoding="utf-8")
    assert secret not in text
    record = read_run_audit_record("run-redact")
    assert record is not None
    assert record["final_preview"] == "done [redacted]"
    assert record["review"]["issues"] == ["copied [redacted]"]


def test_audit_reader_filters_by_tenant(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "agent_runs.jsonl"
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "true")

    append_run_audit({"run_id": "run-tenant-a", "metadata": {"tenant_id": "tenant-a"}, "task": "A"})

    assert read_run_audit_record("run-tenant-a", tenant_id="tenant-a") is not None
    assert read_run_audit_record("run-tenant-a", tenant_id="tenant-b") is None
