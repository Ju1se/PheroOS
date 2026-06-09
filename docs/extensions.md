# Extension Guide

This guide describes how to add components without coupling new code to the
current implementation.

## Add a Capability

Capability is the preferred extension unit. A capability can package tools,
skills, data-source adapters, UI configuration, and permissions without editing
the Orchestrator.

```text
capabilities/my-capability/
  capability.json
  SKILL.md optional
  tools.py optional
  adapters.py optional
  ui.schema.json optional
```

Minimal `capability.json`:

```json
{
  "id": "my-financial-data",
  "name": "My Financial Data",
  "version": "0.1.0",
  "description": "Read-only financial data adapter.",
  "capability_types": ["financial_fundamentals"],
  "permissions": ["data:read", "network:approved-provider"],
  "risk_level": "low",
  "requires_confirmation": false,
  "connections": ["my_provider"],
  "tools": ["my_company_financials"],
  "skills": ["my-data"],
  "data_packages": ["annual_financials_10y"],
  "entrypoints": {
    "adapter_module": "capabilities.my_financial_data.adapters:MyAdapter"
  }
}
```

Capability rules:

- Declare every permission explicitly.
- Use `risk_level: "low"` only for read-only, reviewed local capabilities.
- Any `filesystem:write`, `shell:execute`, `trade:execute`, `database:write`,
  `email:send`, or arbitrary network action must require user confirmation.
- Do not put secrets in `capability.json`; use Connection Control Plane and
  SecretStore.
- Do not register tools with names that conflict with built-in tools.

The OS Kernel may auto-enable low-risk local capabilities. It never downloads
remote code.

## Add an Agent

Agents are resources inside a capability. For an investment committee member,
add an agent manifest under the capability that owns the workflow.

```text
capabilities/value-investing-research/agents/my_quality_agent.json
```

Example:

```json
{
  "key": "earnings_quality_agent",
  "name": "Earnings Quality Agent",
  "agent_type": "investment_committee_member",
  "description": "Audits accruals, cash conversion, one-time items, and accounting risk.",
  "focus": "盈利质量：现金流转化、应计利润、一次性项目、会计风险、收入确认和利润可持续性。",
  "model_attr": "fundamental_analyst_agent",
  "default_enabled": true,
  "order": 35,
  "tags": ["quality", "accounting", "cash-flow"],
  "accent": "green",
  "short": "EQ"
}
```

Agent rules:

- Keep each agent narrow: one role, one output responsibility.
- Agents do not call tools directly; tool and data access remain capability and
  Executor responsibilities.
- Use `model_attr` to route through an existing model role from `ModelConfig`.
- Users can override the active committee for a run with
  `metadata.committee_member_ids`.
- Dashboard exposes agent manifests in the `Agent Plugins` panel. Presets are:
  AI default, Core, and All; manual checkbox selection is also supported.

## Add a Tool

Register tools through a capability manifest and `ToolRegistry` instead of
editing executor logic.

```python
from tools.safe_tools import ToolResult
from runtime.tool_registry import ToolRegistry


def echo_tool(text: str) -> ToolResult:
    return ToolResult(True, {"text": text})


registry = ToolRegistry(
    extra_tools={"echo": echo_tool},
    extra_tool_manifest=[
        {
            "name": "echo",
            "description": "Return the input text.",
            "args": {"text": "string"},
        }
    ],
)
```

Tool rules:

- Return `ToolResult`.
- Validate inputs inside the tool.
- Do not execute arbitrary shell commands.
- Keep dangerous external actions behind explicit allowlists.

## Add a Model Gateway

Implement `runtime.ports.ChatModelClient`.

```python
from runtime.ports import ChatModelClient, Message


class MyModelClient(ChatModelClient):
    async def chat(self, *, model: str, messages: list[Message], temperature: float = 0.0) -> str:
        ...
```

Then assemble the runtime with `RuntimeComponents`.

```python
from runtime.factory import RuntimeComponents, build_runtime

runtime = build_runtime(RuntimeComponents(llm=MyModelClient()))
```

## Add a Skill

Create a folder under `skills/`:

```text
skills/my-skill/
  SKILL.md
```

`SKILL.md` must include frontmatter:

```markdown
---
name: my-skill
description: Use this skill when ...
---
```

## Add a Data Source

Prefer this shape:

```text
source adapter -> normalized package -> metric registry -> data gate -> agents
```

Do not let agents read raw data source responses directly when the result can
affect a final decision.

## Add Dashboard-Managed Connections

The dashboard stores user-provided model/data credentials through
`PlatformConfigStore`.

```python
from runtime.platform_config import PlatformConfigStore

store = PlatformConfigStore()
store.upsert_model_provider(
    "openai",
    {
        "name": "OpenAI",
        "provider": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key": "...",
    },
)
```

Read APIs return redacted records only:

```python
config = store.public_config()
```

For production, implement a replacement store that keeps the same public shape
but writes secrets to a managed secret backend.

## Add a New API Shell

Use `runtime.factory.build_runtime` rather than constructing concrete adapters
inside route handlers.

```python
from runtime.factory import RuntimeComponents, build_runtime

runtime = build_runtime(RuntimeComponents(workspace_root="/srv/workspace"))
```
