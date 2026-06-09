# Contributing

Thanks for helping improve PheroOS. This project is an open AI-as-OS
kernel/protocol plus a reference runtime: components should be easy to replace,
easy to test, and hard to accidentally couple together.

## Design Principles

- Keep components internally cohesive and externally small.
- Prefer interfaces in `runtime/ports.py` over importing concrete adapters.
- Keep provider-specific code in adapters such as `runtime/llm.py`,
  `tools/web_tools.py`, and `tools/wrds_tools.py`.
- Keep orchestration policy separate from tool implementation.
- Do not add new production dependencies unless they remove meaningful
  complexity.
- Do not commit secrets, generated reports, local logs, screenshots, or
  `.env.local`.

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

For LiteLLM proxy support:

```bash
.venv/bin/pip install -e ".[proxy]"
scripts/start_litellm.sh
scripts/start_api.sh
```

## Extension Guidelines

New integrations should use these extension points:

- Model gateways: implement `runtime.ports.ChatModelClient`.
- Tools: register callables through `ToolRegistry(extra_tools=...)`.
- Skills: add `skills/<skill-name>/SKILL.md`.
- API apps: depend on `runtime.factory.build_runtime`, not concrete runtime
  internals.

## Pull Request Checklist

- Add or update tests for behavior changes.
- Run `.venv/bin/pytest`.
- Update docs when public behavior, config, or extension points change.
- Keep generated local artifacts out of the PR.
- Explain migration impact if changing API response fields or state shape.

## PheroOS Improvement Proposals

Protocol, kernel ABI, driver model, security model, conformance, and trace
contract changes should start as a PheroOS Improvement Proposal (PIP) under
`pips/`.

Use the template in [PIP-0001](pips/PIP-0001-process.md). A PIP should cover:

- abstract and motivation;
- specification;
- compatibility impact;
- security considerations;
- reference implementation plan;
- conformance tests;
- migration plan.

Ordinary bug fixes, capability examples, documentation corrections, and
reference runtime UI changes do not need a PIP unless they alter protocol or
kernel compatibility.
