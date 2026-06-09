# Public Financial Data Sources

This platform exposes SEC EDGAR, FRED, Stooq/yfinance, and Kenneth French as an AI-as-OS capability named `public-financial-data`.

## Capability

Manifest:

```text
capabilities/public-financial-data/capability.json
```

Capability types:

- `public_financial_data`
- `supplemental_financial_fundamentals`
- `filings`
- `macro_data`
- `market_prices`
- `asset_pricing_factors`

Permissions:

- `network:approved-provider`
- `data:read`
- `tool:deterministic-read`

These sources use fixed approved provider endpoints. They do not enable arbitrary web search.

## Tools

| Tool | Source | Purpose |
| --- | --- | --- |
| `sec_company_search` | SEC EDGAR | Resolve ticker/name/CIK candidates. |
| `sec_company_facts` | SEC EDGAR XBRL | Fetch company facts by query or CIK. |
| `sec_recent_filings` | SEC EDGAR submissions | Fetch filing metadata and document URLs. |
| `fred_series` | FRED | Fetch macro series observations using a configured FRED API key. |
| `market_price_history` | Stooq, optional yfinance | Fetch public daily market prices. |
| `kenneth_french_factors` | Kenneth French Data Library | Fetch factor research datasets. |

## Connection Handling

SEC EDGAR, Stooq, and Kenneth French do not require stored user secrets. FRED requires an API key:

```text
fred
api_key: <your-fred-api-key>
```

The Connection Control Plane stores the FRED key in the secret store and only exposes redacted metadata such as `configured=true` and `last4`.

## Investment Workflow Constraint

These sources are supplemental public data sources. They do not replace WRDS as the professional deterministic metric registry path. SEC company facts are raw XBRL filing evidence and must pass Data Gate before the Writer may use them in valuation conclusions.
