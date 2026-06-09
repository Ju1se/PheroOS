from __future__ import annotations

import re


LOCAL_WORKSPACE_HINTS = (
    "代码",
    "项目",
    "仓库",
    "文件",
    "目录",
    "函数",
    "类",
    "接口",
    "测试",
    "实现",
    "修改",
    "添加",
    "修复",
    "bug",
    "repo",
    "repository",
    "workspace",
)
WEB_RESEARCH_HINTS = (
    "联网",
    "搜索",
    "查询",
    "网上",
    "网页",
    "新闻",
    "动态",
    "官网",
    "官方",
    "来源",
    "引用",
    "资料",
    "财报",
    "年报",
    "季报",
    "公告",
    "股票",
    "股价",
    "估值",
    "港股",
    "a股",
    "美股",
    "行业",
    "竞品",
    "市场",
    "latest",
    "current",
    "news",
    "official",
    "source",
    "documentation",
)
KNOWN_PUBLIC_ENTITY_NAMES = (
    "药明康德",
    "wuxi apptec",
    "五粮液",
    "wuliangye",
    "贵州茅台",
    "kweichow moutai",
    "moutai",
    "兆易创新",
    "gigadevice",
    "giga device",
    "沪电股份",
    "wus printed circuit",
)
VALUE_INVESTING_HINTS = (
    "价值投资",
    "投资",
    "估值",
    "基本面",
    "财务健康",
    "盈利质量",
    "现金流",
    "护城河",
    "管理层",
    "资本配置",
    "组合",
    "回测",
    "value investing",
    "valuation",
    "fundamental",
    "financial health",
    "earnings quality",
    "cash flow",
    "moat",
    "capital allocation",
    "portfolio",
    "backtest",
)
DOCUMENT_WRITING_HINTS = (
    "文档",
    "memo",
    "proposal",
    "撰写",
    "改写",
    "润色",
    "总结",
    "draft",
    "rewrite",
    "summarize",
    "document",
)
DATA_ANALYSIS_HINTS = (
    "csv",
    "xlsx",
    "spreadsheet",
    "表格",
    "数据分析",
    "统计",
    "dataset",
    "data analysis",
    "summary statistics",
)
ENTITY_ANALYSIS_HINTS = (
    "分析",
    "研究",
    "调研",
    "怎么看",
    "怎么样",
    "如何评价",
    "报告",
    "业务",
    "风险",
)
WRDS_HINTS = (
    "wrds",
    "compustat",
    "crsp",
    "ibes",
    "professional data",
    "专业数据",
    "专业信息",
)


def infer_task_skill_names(task: str) -> list[str]:
    names = []
    if needs_wrds_data(task):
        names.append("wrds-data")
    if needs_web_research(task):
        names.append("web-research")
    if needs_value_investing_research(task):
        names.append("value-investing-research")
    if needs_data_analysis(task):
        names.append("data-analysis")
    if needs_document_writing(task):
        names.append("document-writing")
    return names


def needs_wrds_data(task: str) -> bool:
    lowered = task.lower()
    return any(hint in lowered for hint in WRDS_HINTS)


def needs_web_research(task: str) -> bool:
    lowered = task.lower()
    if any(entity in lowered for entity in KNOWN_PUBLIC_ENTITY_NAMES):
        return True
    if any(hint in lowered for hint in WEB_RESEARCH_HINTS):
        return True
    if any(hint in lowered for hint in ENTITY_ANALYSIS_HINTS) and not any(
        hint in lowered for hint in LOCAL_WORKSPACE_HINTS
    ):
        return bool(re.search(r"[\u4e00-\u9fff]{2,}", task) or re.search(r"\b[A-Z][A-Za-z0-9&.-]{1,}\b", task))
    return False


def needs_value_investing_research(task: str) -> bool:
    lowered = task.lower()
    if any(entity in lowered for entity in KNOWN_PUBLIC_ENTITY_NAMES):
        return True
    return any(hint in lowered for hint in VALUE_INVESTING_HINTS)


def needs_document_writing(task: str) -> bool:
    lowered = task.lower()
    if needs_value_investing_research(task):
        return False
    return any(hint in lowered for hint in DOCUMENT_WRITING_HINTS)


def needs_data_analysis(task: str) -> bool:
    lowered = task.lower()
    return any(hint in lowered for hint in DATA_ANALYSIS_HINTS)
