from __future__ import annotations

import json

import pytest

from runtime.connection_control import ConnectionControlPlane
from runtime.model_gateway import provider_temperature
from runtime.model_gateway import ConnectionAwareModelGateway
from runtime.secret_store import LocalEncryptedSecretStore
from runtime.tool_registry import ToolRegistry
from runtime.workflows.domain_execution import available_tool_names


def test_moonshot_temperature_is_normalized_to_provider_required_value() -> None:
    assert provider_temperature(record={"provider": "moonshot"}, model="kimi-k2.6", requested=0.0) == 1.0
    assert provider_temperature(record={"provider": "moonshot"}, model="moonshot-v1-128k", requested=0.3) == 1.0


def test_non_moonshot_temperature_is_preserved() -> None:
    assert provider_temperature(record={"provider": "zhipu"}, model="glm-5.1", requested=0.2) == 0.2


def test_provider_web_search_uses_approved_provider_permission_not_arbitrary_network() -> None:
    registry = ToolRegistry(
        provider_web_search=lambda **_kwargs: None,
        provider_web_search_enabled=True,
        permission_grants=["network:approved-provider", "model:chat"],
        active_connections=["model-provider"],
    )
    manifest = {tool["name"]: tool for tool in registry.manifest()}

    assert manifest["provider_web_search"]["granted"] is True
    assert manifest["provider_web_search"]["connection_granted"] is True
    assert manifest["web_search"]["granted"] is False
    assert "network:arbitrary" not in manifest["provider_web_search"]["required_permissions"]


def test_domain_workflow_only_sees_granted_and_connected_tools() -> None:
    tools = available_tool_names(
        {
            "tool_manifest": [
                {"name": "provider_web_search", "granted": True, "connection_granted": True},
                {"name": "web_search", "granted": False, "connection_granted": True},
                {"name": "fred_series", "granted": True, "connection_granted": False},
            ]
        }
    )

    assert tools == {"provider_web_search"}


@pytest.mark.anyio
async def test_connection_aware_gateway_uses_moonshot_builtin_web_search(monkeypatch, tmp_path) -> None:
    control = ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(path=tmp_path / "secrets.json", key_path=tmp_path / "secret.key"),
    )
    control.confirm(
        raw="kimi cn\napi_key: sk-kimiexampleabcdefghijklmnopqrstuvwxyz123456",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, *, headers, json):
            calls.append({"url": url, "headers": headers, "json": json})
            if len(calls) == 1:
                return FakeResponse(
                    {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "tool-1",
                                            "type": "function",
                                            "function": {
                                                "name": "$web_search",
                                                "arguments": "{\"query\":\"ant colony multi-agent\"}",
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                )
            return FakeResponse(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": json_module_dumps(
                                    {
                                        "summary": "searched",
                                        "results": [
                                            {
                                                "title": "Paper",
                                                "url": "https://example.edu/paper",
                                                "evidence": "ACO is studied in MAS.",
                                            }
                                        ],
                                        "limitations": [],
                                    }
                                )
                            },
                        }
                    ]
                }
            )

    monkeypatch.setattr("runtime.model_gateway.httpx.AsyncClient", FakeAsyncClient)

    gateway = ConnectionAwareModelGateway(control_plane=control, tenant_id="tenant-a")
    result = await gateway.provider_web_search(query="ant colony multi-agent", max_results=3)

    assert len(calls) == 2
    assert calls[0]["json"]["tools"][0]["function"]["name"] == "$web_search"
    assert calls[0]["json"]["thinking"] == {"type": "disabled"}
    assert calls[0]["json"]["temperature"] == 0.6
    assert calls[1]["json"]["messages"][-1]["role"] == "tool"
    assert result["provider_model"] == "kimi-k2.6"
    assert result["results"][0]["url"] == "https://example.edu/paper"


def json_module_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
