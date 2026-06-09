from __future__ import annotations


LEGACY_SOURCE_GROUNDING_KEYWORDS = (
    "summarize",
    "summary",
    "source",
    "sources",
    "documentation",
    "latest",
    "current",
    "总结",
    "来源",
    "文档",
    "最新",
    "分析",
    "研究",
    "调研",
    "报告",
    "业务",
    "风险",
    "财报",
    "年报",
    "季报",
    "公告",
    "股票",
    "股价",
)


def legacy_source_grounding_keywords() -> tuple[str, ...]:
    return LEGACY_SOURCE_GROUNDING_KEYWORDS
