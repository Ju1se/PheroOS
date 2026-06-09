# Security Policy

## Supported Versions

This project is pre-1.0. Security fixes target the current `main` branch.

## Reporting a Vulnerability

Please do not open a public issue for secrets, account credentials, data access
exposure, prompt injection bypasses, or tool permission bypasses. Report them
privately to the maintainers of your fork or deployment.

## Security Boundaries

- The runtime must not print secrets, API keys, WRDS passwords, or auth tokens.
- Direct `/wrds/*` API routes should be protected with `WRDS_API_TOKEN` if the
  service is reachable beyond localhost.
- Tool execution must go through `runtime/tool_registry.py`.
- Web tools must reject localhost, private networks, file URLs, and metadata
  endpoints.
- Investment analysis is WRDS-only by default and should not call web search
  unless the workflow is explicitly changed.
- Generated logs and reports may contain sensitive prompts or financial
  analysis. Keep `logs/`, `reports/`, and `output/` out of version control.
