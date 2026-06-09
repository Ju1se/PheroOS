from __future__ import annotations

from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.swarm.tool_policy_resolver import resolve_tool_policy
from runtime.tool_registry import ToolRegistry
from tools.safe_tools import ToolResult


def test_tool_policy_uses_capability_allowed_tools() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": tool_policy_plan(["tool:approved_source_fetch"])}}}
    manifest = [
        {
            "name": "approved_source_fetch",
            "required_permissions": ["network:approved-provider"],
            "granted": True,
            "connection_granted": True,
        },
        {"name": "read_file", "required_permissions": ["data:read"], "granted": True, "connection_granted": True},
    ]

    allowed = resolve_tool_policy(tool_name="approved_source_fetch", state=state, tool_manifest=manifest)
    denied = resolve_tool_policy(tool_name="read_file", state=state, tool_manifest=manifest)

    assert allowed["status"] == "allowed"
    assert denied["status"] == "denied"
    assert denied["reason"] == "not_declared_in_capability_tool_policy"


def test_permission_policy_overrides_capability_allowed_tool() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": tool_policy_plan(["tool:web_search"])}}}
    manifest = [
        {
            "name": "web_search",
            "required_permissions": ["network:arbitrary"],
            "granted": False,
            "connection_granted": True,
        }
    ]

    decision = resolve_tool_policy(tool_name="web_search", state=state, tool_manifest=manifest)

    assert decision["status"] == "denied"
    assert decision["reason"] == "global_permission_policy"


def test_stop_signal_blocks_declared_tool_aliases() -> None:
    plan = tool_policy_plan(["tool:toy_publish"])
    plan["stop_signal_policy"] = {
        "aliases": {"toy publish alias": "tool:toy_publish"},
        "rules": [
            {
                "trigger_targets": ["gate:toy_evidence_gate"],
                "blocked_actions": ["toy publish alias"],
            }
        ],
    }
    state = {
        "metadata": {"os_plan": {"swarm_plan": plan}},
        "stop_signals": [
            {
                "id": "sig-toy",
                "target": "gate:toy_evidence_gate",
                "blocking": True,
                "verification_state": "blocking",
            }
        ],
    }

    decision = resolve_tool_policy(
        tool_name="toy_publish",
        state=state,
        tool_manifest=[{"name": "toy_publish", "granted": True, "connection_granted": True}],
    )

    assert decision["status"] == "blocked"
    assert decision["reason"] == "stop_signal"
    assert decision["blocked_by_signal"] == "sig-toy"


def test_tool_output_quarantined_when_social_immunity_flags() -> None:
    state = {
        "metadata": {"os_plan": {"swarm_plan": tool_policy_plan(["tool:approved_source_fetch"])}},
        "social_immunity_report": {"status": "quarantine_required", "quarantine_count": 1},
    }

    decision = resolve_tool_policy(
        tool_name="approved_source_fetch",
        state=state,
        tool_manifest=[{"name": "approved_source_fetch", "granted": True, "connection_granted": True}],
    )

    assert decision["status"] == "allowed_with_quarantine"
    assert decision["reason"] == "tool_output_quarantine_required"


def test_no_direct_tool_execution_outside_registry(tmp_path) -> None:
    calls: list[str] = []

    def danger() -> ToolResult:
        calls.append("executed")
        return ToolResult(True, {"ok": True})

    registry = ToolRegistry(
        workspace_root=tmp_path,
        extra_tools={"danger": danger},
        extra_tool_manifest=[
            {"name": "danger", "description": "Test tool.", "required_permissions": [], "required_connections": []}
        ],
    )
    state = {"metadata": {"os_plan": {"swarm_plan": tool_policy_plan(["tool:danger"])}}}

    decision = resolve_tool_policy(tool_name="danger", state=state, tool_manifest=registry.manifest())

    assert decision["status"] == "allowed"
    assert calls == []


def tool_policy_plan(allowed_tools: list[str]) -> dict:
    return build_goal_routed_swarm_plan(
        task="Run a toy tool workflow",
        intent="toy_review",
        required_capability_types=["toy.review"],
        agents=[],
        capabilities=[
            {
                "id": "toy-review",
                "trust_level": "first_party_reviewed",
                "protocol": {
                    "intents": ["toy_review"],
                    "targets": [{"target": "gate:toy_evidence_gate"}],
                    "tool_policy": {
                        "allowed_tool_targets": allowed_tools,
                        "tool_aliases": {"toy_publish": "tool:toy_publish"},
                    },
                },
            }
        ],
    )
