---
name: wrds-data
description: Use this skill when the user wants WRDS, Compustat, CRSP, IBES, or other professional financial database information through a read-only WRDS data retrieval agent.
---

# WRDS Data Skill

## Goal

Retrieve professional financial data from WRDS through a single read-only WRDS Agent.

## Rules

1. The WRDS Agent retrieves data only; it does not make investment recommendations.
2. Prefer schema/table discovery before writing SQL when the table is uncertain.
3. SQL must be read-only `SELECT` or `WITH`.
4. Always limit returned rows.
5. Do not expose WRDS credentials in prompts, logs, output, or generated files.

## Output expectations

- State the WRDS action performed.
- Show returned rows or available schemas/tables/columns.
- Mention data limitations and row truncation.
