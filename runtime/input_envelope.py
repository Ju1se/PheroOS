from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from runtime.redaction import SECRET_VALUE_PATTERNS, redact_secret_text


ENVELOPE_SCHEMA_VERSION = "ai_os.input_envelope.v1"
PREFLIGHT_SCHEMA_VERSION = "ai_os.preflight.v1"


PROMPT_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions?", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?(system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"bypass\s+(policy|permission|guardrail|safety|tool)", re.IGNORECASE),
    re.compile(r"忽略(之前|以上|所有|系统|开发者).{0,12}(指令|规则|约束)"),
    re.compile(r"(绕过|规避).{0,12}(权限|策略|安全|限制|工具)"),
    re.compile(r"(泄露|输出|展示).{0,12}(系统提示词|开发者提示词|密钥|密码|凭据)"),
)
HIGH_RISK_ACTION_PATTERNS = (
    re.compile(r"\b(export|send|email|trade|execute shell|run shell|delete database|drop table)\b", re.IGNORECASE),
    re.compile(r"(导出|发送|交易|下单|执行 shell|删除数据库|删除表|转账)"),
)
CONSTRAINT_PATTERNS = {
    "web_search_disabled": (
        re.compile(r"(不要|不需要|禁止|不能).{0,8}(web_search|联网|搜索|网页|web search)", re.IGNORECASE),
        re.compile(r"\bno\s+(web\s+)?search\b", re.IGNORECASE),
    ),
    "wrds_only": (
        re.compile(r"wrds[-_ ]?only", re.IGNORECASE),
        re.compile(r"只(使用|用)\s*wrds", re.IGNORECASE),
    ),
    "no_vpn": (
        re.compile(r"(不需要|不要|禁止).{0,8}(vpn|翻译|英文翻译)", re.IGNORECASE),
    ),
}


@dataclass(frozen=True)
class InputEnvelope:
    run_id: str
    tenant_id: str
    user_input: str
    user_input_redacted: str
    user_selected_agents: list[str] = field(default_factory=list)
    user_constraints: list[str] = field(default_factory=list)
    attached_files: list[dict[str, Any]] = field(default_factory=list)
    requested_output_format: str = "auto"
    risk_mode: str = "normal"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema_version: str = ENVELOPE_SCHEMA_VERSION

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "user_input": self.user_input_redacted,
            "user_selected_agents": self.user_selected_agents,
            "user_constraints": self.user_constraints,
            "attached_files": self.attached_files,
            "requested_output_format": self.requested_output_format,
            "risk_mode": self.risk_mode,
            "timestamp": self.timestamp,
            "redaction_status": "redacted",
        }


def build_input_envelope(
    *,
    task: str,
    tenant_id: str,
    selected_agent_ids: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> InputEnvelope:
    metadata = metadata if isinstance(metadata, dict) else {}
    explicit_constraints = [
        str(item).strip()
        for item in metadata.get("user_constraints", [])
        if str(item).strip()
    ] if isinstance(metadata.get("user_constraints"), list) else []
    constraints = sorted(set([*explicit_constraints, *detected_constraints(task)]))
    return InputEnvelope(
        run_id=str(metadata.get("run_id") or f"run_{uuid4().hex[:12]}"),
        tenant_id=str(tenant_id or metadata.get("tenant_id") or "default"),
        user_input=str(task or ""),
        user_input_redacted=redact_secret_text(task, limit=4000),
        user_selected_agents=[str(item) for item in selected_agent_ids or [] if str(item).strip()],
        user_constraints=constraints,
        attached_files=normalize_attached_files(metadata.get("attached_files")),
        requested_output_format=str(metadata.get("requested_output_format") or "auto"),
        risk_mode=str(metadata.get("risk_mode") or "normal"),
    )


def preflight_input_envelope(envelope: InputEnvelope) -> dict[str, Any]:
    secret_spans = detect_secret_spans(envelope.user_input)
    injection_hits = detect_pattern_hits(envelope.user_input, PROMPT_INJECTION_PATTERNS)
    high_risk_hits = detect_pattern_hits(envelope.user_input, HIGH_RISK_ACTION_PATTERNS)
    normalized_task = redact_secret_text(envelope.user_input, limit=8000)
    quarantine_artifacts = []
    for index, hit in enumerate([*secret_spans, *injection_hits]):
        quarantine_artifacts.append(
            {
                "artifact_id": f"input-artifact-{index + 1:03d}",
                "kind": hit.get("kind") or "input_risk",
                "reason": hit.get("reason") or hit.get("match") or "input risk",
                "redacted_preview": hit.get("redacted_preview") or "[redacted]",
                "source": "user_input",
            }
        )
    input_risks = []
    if secret_spans:
        input_risks.append({"code": "secret_like_input", "severity": "high", "count": len(secret_spans)})
    if injection_hits:
        input_risks.append({"code": "prompt_injection_like_input", "severity": "high", "count": len(injection_hits)})
    if high_risk_hits:
        input_risks.append({"code": "high_risk_action_request", "severity": "confirmation_required", "count": len(high_risk_hits)})
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "normalized_task": normalized_task,
        "detected_constraints": envelope.user_constraints,
        "input_risks": input_risks,
        "quarantine_artifacts": quarantine_artifacts,
        "requires_user_confirmation": bool(high_risk_hits),
        "contamination_detected": bool(injection_hits),
        "secret_detected": bool(secret_spans),
        "redaction_status": "redacted",
    }


def detected_constraints(task: str) -> list[str]:
    lowered = str(task or "")
    constraints = []
    for label, patterns in CONSTRAINT_PATTERNS.items():
        if any(pattern.search(lowered) for pattern in patterns):
            constraints.append(label)
    return constraints


def detect_secret_spans(text: str) -> list[dict[str, Any]]:
    output = []
    for pattern in SECRET_VALUE_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            output.append(
                {
                    "kind": "secret_like_span",
                    "reason": "input contains a credential-like token",
                    "start": match.start(),
                    "end": match.end(),
                    "redacted_preview": "[redacted]",
                }
            )
    return output


def detect_pattern_hits(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[dict[str, Any]]:
    hits = []
    for pattern in patterns:
        match = pattern.search(str(text or ""))
        if match:
            hits.append(
                {
                    "kind": "prompt_injection_like_span",
                    "match": pattern.pattern,
                    "redacted_preview": redact_secret_text(match.group(0), limit=120),
                }
            )
    return hits


def normalize_attached_files(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    files = []
    for item in value:
        if not isinstance(item, dict):
            continue
        files.append(
            {
                "name": str(item.get("name") or item.get("filename") or "attachment"),
                "mime_type": str(item.get("mime_type") or item.get("type") or "application/octet-stream"),
                "size": item.get("size"),
            }
        )
    return files
