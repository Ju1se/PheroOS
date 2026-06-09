# OS Kernel

`runtime/os_kernel.py` is the control plane brain. It plans capabilities; it
does not perform work.

## Responsibilities

- Infer task intent.
- Infer required capability types.
- Compare required capabilities with active tenant capabilities.
- Auto-enable low-risk local capabilities.
- Report missing capabilities and connections.
- Request confirmation for risky capabilities.
- Build default or user-selected committee plans.
- Decide graph mode and runtime readiness.

## Non-Responsibilities

- No WRDS queries.
- No direct model calls for domain analysis.
- No report writing.
- No arbitrary tool execution.
- No permission bypass.

## Investment Plan Shape

Investment tasks usually require:

- `chat_model`
- `financial_fundamentals`
- `skill:value-investing-research`

If WRDS is unavailable, the plan reports missing connection requirements instead
of silently falling back to web search.

## Task Taxonomy

The kernel currently recognizes these top-level intents:

For capabilities with first-class protocol manifests, protocol-declared intents
and required capability types are preferred before this legacy taxonomy is used
as a compatibility fallback.

| Intent | Trigger examples | Required capability types |
| --- | --- | --- |
| `investment_analysis` | stock/company valuation, fundamentals, value investing | `chat_model`, `financial_fundamentals`, `skill:value-investing-research` |
| `portfolio_review` | portfolio allocation, holdings, position sizing, rebalance | `chat_model`, `portfolio.review`, `skill:value-investing-research` |
| `financial_data_retrieval` | WRDS, Compustat, CRSP, IBES data pull | `chat_model`, `financial_fundamentals`, `skill:value-investing-research`, `professional_financial_database` when explicitly requested |
| `web_research` | public web/current/source comparison tasks | `chat_model`, `public_web_research`, `skill:web-research` |
| `code_development` | FastAPI/API/code/debug/test tasks | `chat_model`, `code_development`, `skill:fastapi-api` |
| `document_writing` | drafting, rewriting, summaries, proposals, memos | `chat_model`, `document_writing`, `skill:document-writing` |
| `data_analysis` | CSV/spreadsheet/dataset/statistics tasks | `chat_model`, `data_analysis`, `skill:data-analysis` |
| `general_chat` | ordinary conversation or simple direct answer | `chat_model` |

Portfolio review is investment-adjacent and can use committee agents, but it
does not automatically require WRDS unless the task explicitly asks for WRDS or
professional financial database retrieval. Document writing and data analysis
are separate first-party capabilities so users can compose committees and tools
without pretending every task is investment research.
