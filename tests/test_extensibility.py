from __future__ import annotations

from runtime.factory import RuntimeComponents, build_runtime
from runtime.tool_registry import ToolRegistry
from tools.safe_tools import ToolResult


def test_tool_registry_accepts_external_tools(tmp_path) -> None:
    def echo(text: str) -> ToolResult:
        return ToolResult(True, {"text": text})

    registry = ToolRegistry(
        workspace_root=tmp_path,
        extra_tools={"echo": echo},
        extra_tool_manifest=[
            {
                "name": "echo",
                "description": "Echo text.",
                "args": {"text": "string"},
            }
        ],
    )

    assert "echo" in registry.names()
    assert any(tool["name"] == "echo" for tool in registry.manifest())
    result = registry.run("echo", {"text": "hello"})
    assert result.ok is True
    assert result.data == {"text": "hello"}


def test_tool_registry_denies_high_risk_tools_without_permission_grant(tmp_path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path)

    result = registry.run("write_file", {"path": "probe.txt", "content": "nope"})

    assert result.ok is False
    assert result.data["permission_required"] is True
    assert result.data["missing_permissions"] == ["filesystem:write"]
    assert not (tmp_path / "probe.txt").exists()


def test_tool_registry_allows_high_risk_tools_with_permission_grant(tmp_path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path, permission_grants=["filesystem:write"])

    result = registry.run("write_file", {"path": "probe.txt", "content": "ok"})

    assert result.ok is True
    assert (tmp_path / "probe.txt").read_text(encoding="utf-8") == "ok"


def test_tool_manifest_exposes_permission_metadata(tmp_path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path)

    tools = {tool["name"]: tool for tool in registry.manifest()}

    assert tools["write_file"]["required_permissions"] == ["filesystem:write"]
    assert tools["write_file"]["granted"] is False
    assert tools["read_file"]["required_permissions"] == ["data:read"]
    assert tools["read_file"]["granted"] is True
    assert tools["read_file"]["connection_granted"] is True


def test_tool_registry_denies_tools_when_required_connection_missing(tmp_path) -> None:
    def quote() -> ToolResult:
        return ToolResult(True, {"price": 10})

    registry = ToolRegistry(
        workspace_root=tmp_path,
        extra_tools={"quote": quote},
        extra_tool_manifest=[
            {
                "name": "quote",
                "description": "Fetch a quote from a configured provider.",
                "required_permissions": ["data:read"],
                "required_connections": ["market_data"],
            }
        ],
    )

    result = registry.run("quote")

    assert result.ok is False
    assert result.data["connection_required"] is True
    assert result.data["missing_connections"] == ["market_data"]
    assert {tool["name"]: tool for tool in registry.manifest()}["quote"]["connection_granted"] is False


def test_tool_registry_allows_tools_when_required_connection_is_active(tmp_path) -> None:
    def quote() -> ToolResult:
        return ToolResult(True, {"price": 10})

    registry = ToolRegistry(
        workspace_root=tmp_path,
        active_connections=["market_data"],
        extra_tools={"quote": quote},
        extra_tool_manifest=[
            {
                "name": "quote",
                "description": "Fetch a quote from a configured provider.",
                "required_permissions": ["data:read"],
                "required_connections": ["market_data"],
            }
        ],
    )

    result = registry.run("quote")

    assert result.ok is True
    assert result.data == {"price": 10}
    assert {tool["name"]: tool for tool in registry.manifest()}["quote"]["connection_granted"] is True


def test_tool_registry_filters_tools_by_runtime_allowlist(tmp_path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path, allowed_tool_names=["read_file"])

    assert registry.names() == ["read_file"]
    assert registry.run("list_files", {}).ok is False
    assert registry.run("list_files", {}).error == "unknown tool: list_files"


def test_tool_registry_rejects_external_tool_name_collision(tmp_path) -> None:
    def fake_read_file() -> ToolResult:
        return ToolResult(True, {})

    try:
        ToolRegistry(workspace_root=tmp_path, extra_tools={"read_file": fake_read_file})
    except ValueError as exc:
        assert "read_file" in str(exc)
    else:
        raise AssertionError("expected duplicate tool name to be rejected")


def test_build_runtime_uses_swappable_components(tmp_path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path, wrds_enabled=False)

    runtime = build_runtime(
        RuntimeComponents(
            tool_registry=registry,
            workspace_root=tmp_path,
        )
    )

    assert runtime.tool_registry is registry
