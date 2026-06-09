---
name: data-analysis
description: Use this skill when analyzing CSV, spreadsheet-like, JSON, tabular, metric, experimental, operational, or user-provided structured data.
---

# Data Analysis Skill

## Goal

Analyze structured data using deterministic calculations first, then synthesize findings in plain language.

## Rules

1. Do not fabricate rows, metrics, samples, or statistical results.
2. Prefer structured parsers and deterministic calculations over model guessing.
3. Report data quality issues, missing columns, units, and time-period ambiguity.
4. Keep raw sensitive data out of prompts and final prose where summaries are sufficient.
5. Distinguish observed facts, computed metrics, and interpretation.

## Output Expectations

- Summarize dataset shape and quality.
- Show formulas or calculation assumptions for key metrics.
- Explain limitations and recommended next checks.
