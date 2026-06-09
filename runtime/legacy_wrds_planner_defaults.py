from __future__ import annotations

from typing import Any


LEGACY_INVESTMENT_TASK_TYPE = "investment"
BASE_INVESTMENT_PACKAGES = [
    "company_identity",
    "annual_financials_10y",
    "quarterly_financials_16q",
    "valuation_snapshot",
    "cash_flow_and_capex",
    "balance_sheet_and_debt",
    "profitability_and_margin",
    "inventory_and_working_capital",
    "debt_interest_coverage",
    "capital_returns",
    "goodwill_intangibles",
    "split_adjustment",
    "crsp_market_data",
    "capital_iq_profile",
]

# Verified against the user's current WRDS account. Keep unavailable packages in
# the catalog for explicit future use, but do not request them by default.
ACCOUNT_AVAILABLE_PACKAGES = frozenset(
    [
        "company_identity",
        "annual_financials_10y",
        "quarterly_financials_16q",
        "valuation_snapshot",
        "cash_flow_and_capex",
        "balance_sheet_and_debt",
        "profitability_and_margin",
        "inventory_and_working_capital",
        "debt_interest_coverage",
        "capital_returns",
        "goodwill_intangibles",
        "split_adjustment",
        "crsp_market_data",
        "capital_iq_profile",
        "optionmetrics_security",
        "semiconductor_cycle",
        "peer_comparison",
    ]
)

ACCOUNT_UNAVAILABLE_PACKAGES = frozenset(
    [
        "ibes_estimates",
        "compustat_segments",
        "audit_analytics",
        "capital_iq_keydev",
    ]
)

SEMICONDUCTOR_PACKAGES = [
    "semiconductor_cycle",
    "peer_comparison",
]

MARKET_RISK_PACKAGES = [
    "optionmetrics_security",
]

PACKAGE_CATALOG: dict[str, dict[str, Any]] = {
    "company_identity": {
        "description": "Resolve ticker, gvkey, CIK, CUSIP, company name, SIC/NAICS, and fiscal-year metadata.",
        "tables": ["comp.names", "comp.g_names"],
        "fields": ["gvkey", "tic", "conm", "cik", "cusip", "sic", "naics", "gind", "gsubind", "year1", "year2"],
    },
    "annual_financials_10y": {
        "description": "Ten years of annual Compustat fundamentals for through-cycle analysis.",
        "tables": ["comp.funda"],
        "period": {"annual_years": 10},
        "fields": [
            "gvkey",
            "datadate",
            "fyear",
            "fyr",
            "tic",
            "conm",
            "sale",
            "revt",
            "cogs",
            "gp",
            "dp",
            "oibdp",
            "oiadp",
            "ebit",
            "ebitda",
            "ni",
            "ib",
            "epspx",
            "epspi",
            "epsfi",
            "oancf",
            "capx",
            "at",
            "lt",
            "dltt",
            "dlc",
            "che",
            "ceq",
            "seq",
            "csho",
            "prcc_f",
            "invt",
            "rect",
            "ap",
            "xsga",
        ],
    },
    "quarterly_financials_16q": {
        "description": "Sixteen quarters of quarterly fundamentals to locate cycle inflections.",
        "tables": ["comp.fundq"],
        "period": {"quarterly_quarters": 16},
        "fields": [
            "gvkey",
            "datadate",
            "fyearq",
            "fqtr",
            "fyr",
            "tic",
            "conm",
            "saleq",
            "revtq",
            "cogsq",
            "gpq",
            "dpq",
            "oibdpq",
            "oiadpq",
            "niq",
            "epspxq",
            "epsfiq",
            "oancfy",
            "capxy",
            "actq",
            "lctq",
            "atq",
            "ltq",
            "dlttq",
            "dlcq",
            "cheq",
            "ceqq",
            "cshoq",
            "prccq",
            "invtq",
            "rectq",
            "apq",
            "rdq",
        ],
    },
    "valuation_snapshot": {
        "description": "Market price, shares, cash, debt, and enterprise-value inputs; multiples are computed deterministically later.",
        "tables": ["comp.funda", "comp.fundq", "crsp.dsf", "crsp.msf"],
        "fields": ["prcc_f", "prccq", "csho", "cshoq", "che", "cheq", "dltt", "dlttq", "dlc", "dlcq", "ceq", "sale", "saleq", "ebitda", "oibdp", "oibdpq", "oancf", "capx"],
    },
    "cash_flow_and_capex": {
        "description": "Operating cash flow, capex, depreciation, and conventional FCF / capex intensity inputs.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["oancf", "oancfy", "capx", "capxy", "dp", "dpq", "sale", "saleq"],
    },
    "balance_sheet_and_debt": {
        "description": "Cash, debt, liabilities, equity, liquidity, and balance-sheet risk inputs.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["at", "lt", "dltt", "dlc", "che", "ceq", "seq", "act", "lct", "atq", "ltq", "dlttq", "dlcq", "cheq", "ceqq", "actq", "lctq"],
    },
    "profitability_and_margin": {
        "description": "Revenue, cost, depreciation, gross/operating/net margin inputs; reported margin must be reconciled against filings.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["sale", "revt", "cogs", "gp", "dp", "oibdp", "oiadp", "ebit", "ni", "saleq", "revtq", "cogsq", "gpq", "dpq", "oibdpq", "oiadpq", "niq"],
    },
    "inventory_and_working_capital": {
        "description": "Inventory, receivables, payables, and working-capital cycle indicators.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["invt", "rect", "ap", "cogs", "sale", "invtq", "rectq", "apq", "cogsq", "saleq"],
    },
    "semiconductor_cycle": {
        "description": "Capital intensity, depreciation, inventory, and margin fields for semiconductor / memory-cycle analysis.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["sale", "saleq", "cogs", "cogsq", "gp", "gpq", "dp", "dpq", "capx", "capxy", "invt", "invtq", "oancf", "oancfy", "ebitda", "oibdp", "oibdpq"],
    },
    "crsp_market_data": {
        "description": "CRSP price, return, volume, shares, and split-adjustment inputs for market setup and valuation-date discipline.",
        "tables": ["crsp.dsf", "crsp.msf", "crsp.dsenames", "crsp.stocknames", "crsp.ccmxpf_linktable"],
        "fields": ["permno", "permco", "date", "ticker", "comnam", "cusip", "prc", "ret", "vol", "shrout", "cfacpr", "cfacshr", "namedt", "nameendt", "gvkey", "linkdt", "linkenddt", "linktype", "linkprim"],
    },
    "capital_iq_profile": {
        "description": "Capital IQ company profile, website, industry metadata, business description, and symbol map available to the account.",
        "tables": ["ciq.wrds_gvkey", "ciq.wrds_ciqsymbol", "ciq_common.ciqcompany", "ciq.ciqbusinessdescription"],
        "fields": ["companyid", "gvkey", "companyname", "primaryflag", "symbolvalue", "symboltypename", "webpage", "yearfounded", "simpleindustryid", "businessdescription"],
    },
    "optionmetrics_security": {
        "description": "OptionMetrics security identity plus latest accessible borrow-rate / historical-volatility snapshot for market-risk context.",
        "tables": ["optionm.securd", "optionm.borrateYYYY", "optionm.hvoldYYYY"],
        "fields": ["secid", "cusip", "ticker", "sic", "exchange_d", "issue_type", "industry_group", "date", "borrowrate", "volatility", "days"],
    },
    "ibes_estimates": {
        "description": "IBES consensus estimates and actuals for non-GAAP / Street EPS checks when the account has IBES access.",
        "tables": ["ibes.statsum_epsus", "ibes.det_epsus", "ibes.actu_epsus", "tr_ibes.statsum_epsus"],
        "fields": ["ticker", "cusip", "oftic", "cname", "statpers", "fpedats", "fpi", "measure", "meanest", "medest", "numest", "stdev", "actual", "value", "anndats", "anntims"],
    },
    "compustat_segments": {
        "description": "Compustat segment metadata for business/geographic segment revenue and margin checks when visible.",
        "tables": ["compseg", "comp.segments", "comp.wrds_segmerged"],
        "fields": ["gvkey", "datadate", "stype", "sid", "sname", "sales", "ops", "assets", "capx", "srcdate"],
    },
    "debt_interest_coverage": {
        "description": "Interest expense, debt, EBITDA/EBIT, and coverage metrics for balance-sheet risk.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["xint", "xintq", "ebit", "ebitda", "oibdp", "oibdpq", "oiadp", "oiadpq", "dltt", "dlttq", "dlc", "dlcq", "che", "cheq", "sale", "saleq"],
    },
    "capital_returns": {
        "description": "Dividends, buybacks, share issuance, and capital-return intensity inputs.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["dvc", "dvp", "dvpsx_f", "prstkc", "sstk", "dvy", "prstkcy", "sstky", "csho", "cshoq", "che", "cheq", "oancf", "oancfy"],
    },
    "goodwill_intangibles": {
        "description": "Goodwill and intangible asset intensity for acquisition-heavy companies and accounting-quality review.",
        "tables": ["comp.funda", "comp.fundq"],
        "fields": ["gdwl", "gdwlq", "intan", "intanq", "at", "atq", "ceq", "ceqq", "lt", "ltq", "ni", "niq"],
    },
    "split_adjustment": {
        "description": "Compustat and CRSP split adjustment factors to keep price, shares, EPS, and market-cap calculations aligned.",
        "tables": ["comp.funda", "comp.fundq", "crsp.dsf", "crsp.msf"],
        "fields": ["ajex", "ajexq", "csho", "cshoq", "prcc_f", "prccq", "epsfi", "epsfiq", "cfacpr", "cfacshr", "prc", "shrout"],
    },
    "peer_comparison": {
        "description": "Peer lookup request. Planner records peers; retrieval may require non-WRDS public filings for foreign issuers.",
        "tables": ["comp.names", "comp.g_names", "comp.funda", "comp.g_funda"],
        "fields": ["tic", "conm", "gvkey", "fic", "sale", "ni", "capx", "oancf", "at", "ceq", "prcc_f"],
        "default_peers": ["SK HYNIX", "SAMSUNG ELECTRONICS", "WESTERN DIGITAL", "KIOXIA"],
    },
}


def build_default_research_questions(task: str, *, industry_profile: str = "general") -> list[str]:
    questions = [
        "Is the company cheap or expensive relative to cycle-adjusted earnings and cash flow?",
        "Is current free-cash-flow generation sufficient after capital expenditures?",
        "What evidence would invalidate the investment thesis?",
    ]
    if industry_profile == "semiconductor_memory":
        questions.extend(
            [
                "Is AI/HBM demand creating company-specific alpha or mostly industry beta?",
                "Where is the company in the memory / semiconductor capital cycle?",
                "Are inventory and capex trends signaling margin expansion or mean reversion?",
            ]
        )
    return questions


def build_default_data_packages(task: str, *, task_type: str | None = None) -> list[str]:
    if not legacy_wrds_investment_defaults_enabled(task_type):
        return []
    packages = list(BASE_INVESTMENT_PACKAGES)
    if infer_industry_profile(task) == "semiconductor_memory":
        packages.extend(SEMICONDUCTOR_PACKAGES)
    if requires_optionmetrics_market_risk(task):
        packages.extend(MARKET_RISK_PACKAGES)
    return _dedupe_packages(packages)


def legacy_wrds_task_type(value: Any) -> str:
    return str(value or LEGACY_INVESTMENT_TASK_TYPE)


def legacy_wrds_investment_defaults_enabled(task_type: Any) -> bool:
    return str(task_type or LEGACY_INVESTMENT_TASK_TYPE) == LEGACY_INVESTMENT_TASK_TYPE


def infer_industry_profile(task: str) -> str:
    text = str(task or "").lower()
    semiconductor_markers = (
        "mu",
        "micron",
        "美光",
        "半导体",
        "semiconductor",
        "memory",
        "dram",
        "nand",
        "hbm",
        "英伟达",
        "nvidia",
        "nvda",
        "tsmc",
        "台积电",
        "intel",
        "amd",
        "avgo",
        "broadcom",
        "sndk",
        "sandisk",
        "sk hynix",
        "samsung",
    )
    if any(marker in text for marker in semiconductor_markers):
        return "semiconductor_memory"
    return "general"


def requires_optionmetrics_market_risk(task: str) -> bool:
    text = str(task or "").lower()
    markers = (
        "option",
        "options",
        "optionmetrics",
        "volatility",
        "historical volatility",
        "borrow rate",
        "borrowrate",
        "short borrow",
        "期权",
        "波动率",
        "借券",
        "融券",
        "交易执行",
        "market execution",
        "market risk",
    )
    return any(marker in text for marker in markers)


def _dedupe_packages(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
