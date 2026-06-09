---
name: value-investing-research
description: Use this skill for company, stock, or investment research that should be evaluated through evidence, quant analysis, value-investing judgment, and critic verification.
---

# Value Investing Research Skill

## Goal

Produce an auditable value-investing research packet rather than a generic company summary. The runtime should keep evidence extraction, quantitative calculation, domain judgment, writing, and verification separate.

## Required Workflow

1. Use public source grounding first: filings, annual reports, investor relations, exchange disclosures, reputable financial news, and authoritative databases when available.
2. Separate return drivers from risk constraints.
3. Evaluate at least these dimensions when evidence is available:
   - valuation
   - financial health
   - earnings quality and cash flow
   - growth quality
   - competitive advantage / moat
   - management and capital allocation
   - macro, regulatory, liquidity, and concentration risk
   - portfolio fit and execution constraints
4. Treat low valuation as candidate generation, not a buy decision.
5. Use hard veto language when financial distress, manipulation risk, severe liquidity risk, or source insufficiency would block a confident conclusion.
6. Distinguish source facts from inference.
7. If source text is incomplete, lower confidence and list missing data instead of filling gaps with confident claims.

## Output Expectations

Return evidence and judgments through the daily multi-agent roles:

- Research Agent: sources, key facts, evidence gaps, reliability
- Quant Agent: assumptions, formulas, calculations, metrics, sensitivity, missing data
- Domain Expert Agent: business quality, moat, reinvestment runway, management/capital allocation, valuation gap, alpha source, key risks
- Critic Agent: overclaims, weak evidence, calculation errors, citation gaps, minimal fixes
- Writer Agent: final report without adding unverified facts
