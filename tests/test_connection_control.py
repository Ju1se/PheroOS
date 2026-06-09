from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.routes.dependencies import get_connection_control_plane
from runtime.connection_control import ConnectionControlPlane
from runtime.secret_store import LocalEncryptedSecretStore


def make_control(tmp_path) -> ConnectionControlPlane:
    return ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(
            path=tmp_path / "secrets.json",
            key_path=tmp_path / "secret.key",
        ),
    )


def test_infer_connection_does_not_persist_secret(tmp_path) -> None:
    control = make_control(tmp_path)

    result = control.infer(raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890", tenant_id="tenant-a")

    assert result["candidate"]["provider"] == "minimax"
    assert result["candidate"]["secrets"]["api_key"]["configured"] is True
    assert not (tmp_path / "connections.json").exists()
    assert not (tmp_path / "secrets.json").exists()
    assert "sk-cp" not in json.dumps(result)


def test_confirm_connection_encrypts_secret_and_returns_redacted_record(tmp_path) -> None:
    control = make_control(tmp_path)

    record = control.confirm(
        raw="glm fakeglmkey1234567890.fakeglmsecret1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    assert record["status"] == "active"
    assert record["provider"] == "zhipu"
    assert record["secrets"]["api_key"]["last4"] == "7890"
    assert "api_key" not in record
    raw_connections = (tmp_path / "connections.json").read_text(encoding="utf-8")
    raw_secrets = (tmp_path / "secrets.json").read_text(encoding="utf-8")
    assert "fakeglmsecret1234567890" not in raw_connections
    assert "fakeglmsecret1234567890" not in raw_secrets


def test_tenant_connections_are_isolated(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890", tenant_id="tenant-a", validate=False, discover=False)

    assert len(control.list_connections(tenant_id="tenant-a")) == 1
    assert control.list_connections(tenant_id="tenant-b") == []


def test_infer_openai_and_anthropic_keys_for_ai_os_routing(tmp_path) -> None:
    control = make_control(tmp_path)

    openai = control.confirm(
        raw="sk-proj-openaiabcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )
    anthropic = control.confirm(
        raw="sk-ant-api03-anthropicabcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    assert openai["provider"] == "openai"
    assert anthropic["provider"] == "anthropic"
    assert openai["capabilities"][0]["models"]
    assert any(model.startswith("gpt") for model in openai["capabilities"][0]["models"])
    assert any(model.startswith("claude") for model in anthropic["capabilities"][0]["models"])
    combined = json.dumps([openai, anthropic], ensure_ascii=False)
    assert "sk-proj-openai" not in combined
    assert "sk-ant-api03" not in combined


def test_infer_kimi_context_routes_to_moonshot_and_redacts(tmp_path) -> None:
    control = make_control(tmp_path)

    record = control.confirm(
        raw=(
            "kimi cn\n"
            "api_key: sk-kimiexampleabcdefghijklmnopqrstuvwxyz123456\n"
            "agent_scope: critic\n"
            "preferred_model: kimi-k2.6"
        ),
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    assert record["provider"] == "moonshot"
    assert record["provider_key"] == "moonshot-openai-compatible"
    assert record["endpoint"] == "https://api.moonshot.cn/v1"
    assert record["config"]["agent_scope"] == ["critic"]
    assert record["config"]["preferred_model"] == "kimi-k2.6"
    assert record["capabilities"][0]["models"][0] == "kimi-k2.6"
    combined = json.dumps([record, control.capability_index(tenant_id="tenant-a")], ensure_ascii=False)
    assert "sk-kimiexample" not in combined


def test_fred_connection_is_detected_and_redacted(tmp_path) -> None:
    control = make_control(tmp_path)

    record = control.confirm(
        raw="fred\napi_key: abcdefghijklmnopqrstuvwxyz123456",
        tenant_id="tenant-a",
        validate=False,
        discover=True,
    )

    assert record["kind"] == "financial_data_source"
    assert record["provider"] == "fred"
    assert record["secrets"]["api_key"]["last4"] == "3456"
    assert record["capabilities"][0]["type"] == "macro_data"
    combined = json.dumps([record, control.capability_index(tenant_id="tenant-a")], ensure_ascii=False)
    assert "abcdefghijklmnopqrstuvwxyz" not in combined


def test_revoke_connection_deletes_secrets_but_keeps_disabled_record(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890", tenant_id="tenant-a", validate=False, discover=True)
    internal = control.get_connection(connection_id="minimax", tenant_id="tenant-a")
    assert internal is not None
    secret_ref = internal["secret_refs"]["api_key"]
    assert control.secret_store.get_secret(secret_ref).startswith("sk-cp")

    revoked = control.revoke_connection(connection_id="minimax", tenant_id="tenant-a")

    assert revoked["status"] == "disabled"
    assert revoked["revoked"] is True
    assert revoked["secrets_deleted"] == 1
    assert revoked["secrets"] == {}
    assert control.list_active_connections(tenant_id="tenant-a") == []
    try:
        control.secret_store.get_secret(secret_ref)
    except KeyError:
        pass
    else:
        raise AssertionError("expected revoked secret to be deleted")


def test_delete_connection_removes_record_and_secrets(tmp_path) -> None:
    control = make_control(tmp_path)
    control.confirm(raw="sk-cp-abcdefghijklmnopqrstuvwxyz1234567890", tenant_id="tenant-a", validate=False, discover=True)
    internal = control.get_connection(connection_id="minimax", tenant_id="tenant-a")
    assert internal is not None
    secret_ref = internal["secret_refs"]["api_key"]

    deleted = control.delete_connection(connection_id="minimax", tenant_id="tenant-a")

    assert deleted == {"connection_id": "minimax", "tenant_id": "tenant-a", "deleted": True, "secrets_deleted": 1}
    assert control.list_connections(tenant_id="tenant-a") == []
    try:
        control.secret_store.get_secret(secret_ref)
    except KeyError:
        pass
    else:
        raise AssertionError("expected deleted connection secret to be deleted")


def test_connection_control_api_infer_and_confirm_are_redacted(tmp_path) -> None:
    control = make_control(tmp_path)
    app.dependency_overrides[get_connection_control_plane] = lambda: control
    client = TestClient(app)
    try:
        inferred = client.post(
            "/platform/connections/infer",
            json={"raw": "wrds\nusername: student\npassword: very-secret", "tenant_id": "tenant-a"},
        )
        confirmed = client.post(
            "/platform/connections/confirm",
            json={
                "raw": "wrds\nusername: student\npassword: very-secret",
                "tenant_id": "tenant-a",
                "validate": False,
                "discover": False,
            },
        )
        connections = client.get("/platform/connections", params={"tenant_id": "tenant-a"})
        capabilities = client.get("/platform/capabilities", params={"tenant_id": "tenant-a"})
    finally:
        app.dependency_overrides.clear()

    assert inferred.status_code == 200
    assert confirmed.status_code == 200
    assert connections.status_code == 200
    assert capabilities.status_code == 200
    combined = json.dumps(
        [inferred.json(), confirmed.json(), connections.json(), capabilities.json()],
        ensure_ascii=False,
    )
    assert "very-secret" not in combined
    assert connections.json()["connections"][0]["provider"] == "wrds"


def test_connection_control_api_revoke_and_delete_are_redacted(tmp_path) -> None:
    control = make_control(tmp_path)
    app.dependency_overrides[get_connection_control_plane] = lambda: control
    client = TestClient(app)
    try:
        client.post(
            "/platform/connections/confirm",
            json={
                "raw": "wrds\nusername: student\npassword: very-secret",
                "tenant_id": "tenant-a",
                "validate": False,
                "discover": False,
            },
        )
        revoked = client.post("/platform/connections/wrds/revoke", params={"tenant_id": "tenant-a"})
        deleted = client.delete("/platform/connections/wrds", params={"tenant_id": "tenant-a"})
        connections = client.get("/platform/connections", params={"tenant_id": "tenant-a"})
    finally:
        app.dependency_overrides.clear()

    assert revoked.status_code == 200
    assert deleted.status_code == 200
    assert connections.json()["connections"] == []
    combined = json.dumps([revoked.json(), deleted.json(), connections.json()], ensure_ascii=False)
    assert "very-secret" not in combined
    assert "student" not in combined
