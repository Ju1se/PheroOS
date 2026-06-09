from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.routes.platform import get_platform_config_store
from runtime.platform_config import PlatformConfigStore


def test_platform_config_store_redacts_secrets(tmp_path) -> None:
    store = PlatformConfigStore(tmp_path / "platform.json")

    saved = store.upsert_model_provider(
        "OpenAI",
        {
            "name": "OpenAI",
            "provider": "openai-compatible",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-secret",
        },
    )

    assert saved["id"] == "openai"
    assert "api_key" not in saved
    assert saved["secrets"]["api_key"]["last4"] == "cret"

    raw = json.loads((tmp_path / "platform.json").read_text(encoding="utf-8"))
    assert "api_key" not in raw["model_providers"]["openai"]
    assert raw["model_providers"]["openai"]["secret_meta"]["api_key"]["last4"] == "cret"
    assert "sk-test-secret" not in (tmp_path / "platform.json.secrets.json").read_text(encoding="utf-8")


def test_platform_config_store_preserves_existing_secret_on_blank_update(tmp_path) -> None:
    store = PlatformConfigStore(tmp_path / "platform.json")
    store.upsert_data_source(
        "wrds",
        {
            "name": "WRDS",
            "provider": "wrds",
            "api_key": "first-secret",
        },
    )

    saved = store.upsert_data_source(
        "wrds",
        {
            "name": "WRDS renamed",
            "provider": "wrds",
            "api_key": "",
        },
    )

    assert saved["name"] == "WRDS renamed"
    assert saved["secrets"]["api_key"]["last4"] == "cret"


def test_platform_config_api_redacts_keys(tmp_path) -> None:
    store = PlatformConfigStore(tmp_path / "platform.json")
    app.dependency_overrides[get_platform_config_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.put(
            "/platform/model-providers/openai",
            json={
                "name": "OpenAI",
                "provider": "openai-compatible",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-secret",
            },
        )
        config = client.get("/platform/config")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "api_key" not in response.json()
    assert config.status_code == 200
    assert config.json()["model_providers"][0]["secrets"]["api_key"]["configured"] is True


def test_auto_configure_detects_minimax_key(tmp_path) -> None:
    store = PlatformConfigStore(tmp_path / "platform.json")
    app.dependency_overrides[get_platform_config_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.post(
            "/platform/auto-configure",
            json={"raw": "sk-cp-abcdefghijklmnopqrstuvwxyz1234567890"},
        )
    finally:
        app.dependency_overrides.clear()

    data = response.json()
    assert response.status_code == 200
    assert data["kind"] == "model_provider"
    assert data["connection_id"] == "minimax"
    assert data["connection"]["secrets"]["api_key"]["configured"] is True


def test_auto_configure_detects_wrds_credentials(tmp_path) -> None:
    store = PlatformConfigStore(tmp_path / "platform.json")
    app.dependency_overrides[get_platform_config_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.post(
            "/platform/auto-configure",
            json={"raw": "wrds\nusername: student\npassword: very-secret"},
        )
        config = client.get("/platform/config")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["kind"] == "financial_data_source"
    assert config.json()["data_sources"][0]["id"] == "wrds"
    assert config.json()["data_sources"][0]["secrets"]["password"]["last4"] == "cret"


def test_auto_configure_rejects_unknown_input(tmp_path) -> None:
    store = PlatformConfigStore(tmp_path / "platform.json")
    app.dependency_overrides[get_platform_config_store] = lambda: store
    client = TestClient(app)
    try:
        response = client.post("/platform/auto-configure", json={"raw": "not a credential"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
