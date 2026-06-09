---
name: web-research
description: Use this skill when a task requires public internet research, current information, official documentation lookup, source comparison, webpage summarization, or citing web sources.
---

# Web Research Skill

## Goal

Research public web sources safely and summarize findings with clear source attribution.

## Required Workflow

1. Translate the user's research question into English before searching.
2. Use `web_search` when the user asks for current information, external documentation, product or library details, source comparison, or any task that cannot be answered from local files alone.
3. Use English-only search queries and English-language external sources. Do not use Chinese search terms or Chinese finance/wiki/media sites unless the user explicitly overrides this policy.
4. Prefer official documentation, primary sources, standards pages, repository docs, investor relations, exchange filings, annual reports, or publisher pages.
5. For company, stock, or industry analysis, search the official English entity name first, then combine it with English terms such as `annual report`, `financial results`, `filings`, `business`, `risks`, and `latest news`.
6. Treat dictionary, single-character encyclopedia, or Chinese-language finance result pages as irrelevant unless the user explicitly asks for them.
7. After a successful company/entity `web_search`, fetch the most relevant public sources so claims are grounded in page text rather than snippets only.
8. Use `fetch_url` only for public `http` or `https` URLs returned by search or provided by the user.
9. Do not fetch localhost, private network, file, or internal metadata URLs.
10. Keep claims grounded in fetched source text.
11. In the final answer, include source URLs when web results influenced the answer.

## Output Expectations

- Mention which sources were consulted.
- Distinguish direct source facts from your inference.
- Note uncertainty when sources are incomplete or conflicting.
