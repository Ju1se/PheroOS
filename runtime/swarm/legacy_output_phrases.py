from __future__ import annotations

import re
from typing import Any


LEGACY_FORMAL_RECOMMENDATION_RE = re.compile(
    r"\b(Buy|Sell|Strong Buy|Strong Sell|Overweight|Underweight|target price|undervalued|overvalued)\b|"
    r"(买入|卖出|强烈推荐|目标价|低估|高估|正式估值|投资建议\s*[:：]\s*(买入|卖出))",
    re.IGNORECASE,
)
LEGACY_FORMAL_VALUATION_RE = re.compile(
    r"\b(Buy|Sell|target price|undervalued|overvalued)\b|买入|卖出|目标价|低估|高估",
    re.IGNORECASE,
)
LEGACY_FORMAL_VALUATION_PHRASES = ("Buy", "Sell", "target price", "目标价", "买入", "卖出", "正式估值")
LEGACY_INSUFFICIENT_DATA_PHRASES = ("Buy", "Sell", "target price", "目标价", "买入", "卖出")
LEGACY_FALLBACK_CANDIDATE_CONFLICT_TERMS = ("buy", "sell", "target price", "买入", "卖出", "目标价")
LEGACY_FORMAL_VALUATION_WRITER_ACTION = "writer:formal_valuation"
LEGACY_FORMAL_VALUATION_STOP_SIGNAL_FALLBACK_REASON = "- Formal valuation is blocked by swarm stop-signal."
LEGACY_FORMAL_VALUATION_STOP_SIGNAL_REPORT_SOURCE = "legacy_formal_valuation_stop_signal_report"


def legacy_formal_valuation_phrases() -> list[str]:
    return list(LEGACY_FORMAL_VALUATION_PHRASES)


def legacy_insufficient_data_phrases() -> list[str]:
    return list(LEGACY_INSUFFICIENT_DATA_PHRASES)


def legacy_formal_recommendation_present(text: Any) -> bool:
    return bool(LEGACY_FORMAL_RECOMMENDATION_RE.search(str(text or "")))


def legacy_formal_valuation_present(text: Any) -> bool:
    return bool(LEGACY_FORMAL_VALUATION_RE.search(str(text or "")))


def legacy_formal_valuation_writer_action() -> str:
    return LEGACY_FORMAL_VALUATION_WRITER_ACTION


def legacy_fallback_candidate_conflict_present(text: Any) -> bool:
    haystack = str(text or "").lower()
    return any(term in haystack for term in LEGACY_FALLBACK_CANDIDATE_CONFLICT_TERMS)


def legacy_formal_valuation_stop_signal_fallback_reason() -> str:
    return LEGACY_FORMAL_VALUATION_STOP_SIGNAL_FALLBACK_REASON


def legacy_formal_valuation_stop_signal_report(text: Any, *, reasons: str) -> str:
    return "\n".join(
        [
            "# Swarm Stop-Signal Guardrail Report",
            "",
            "当前版本不可发布为正式投资估值结论。Swarm Governance Layer 检测到 Writer / Final Judge 试图输出被 stop-signal 阻止的正式估值或买卖建议。",
            "",
            "## Blocking Signals",
            reasons,
            "",
            "## Required Action",
            "请先解决 Data Gate / evidence / permission 中的阻断项，再重新运行委员会工作流。当前只能输出初步、带限制条件的分析视图。",
            "",
            "## Blocked Draft Preview",
            str(text or "")[:1200],
        ]
    )
