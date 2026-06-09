from __future__ import annotations

import json

import httpx

from runtime.secret_store import (
    LocalEncryptedSecretStore,
    SecretStoreConfigurationError,
    VaultKVSecretStore,
    create_secret_store_from_env,
)


def test_secret_store_factory_defaults_to_local(monkeypatch) -> None:
    monkeypatch.delenv("PLATFORM_SECRET_STORE_BACKEND", raising=False)

    store = create_secret_store_from_env()

    assert isinstance(store, LocalEncryptedSecretStore)


def test_secret_store_factory_selects_vault(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_SECRET_STORE_BACKEND", "vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.example.test")
    monkeypatch.setenv("VAULT_TOKEN", "vault-token")

    store = create_secret_store_from_env()

    assert isinstance(store, VaultKVSecretStore)


def test_secret_store_factory_rejects_unknown_backend(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_SECRET_STORE_BACKEND", "surprise")

    try:
        create_secret_store_from_env()
    except SecretStoreConfigurationError as exc:
        assert "unknown PLATFORM_SECRET_STORE_BACKEND" in str(exc)
    else:
        raise AssertionError("expected unknown backend to fail closed")


def test_vault_kv_secret_store_round_trip_without_secret_in_ref_or_metadata() -> None:
    writes: dict[str, dict] = {}
    deleted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Vault-Token"] == "vault-token"
        path = request.url.path
        if request.method == "POST":
            writes[path] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(204)
        if request.method == "GET":
            payload = writes[path]
            return httpx.Response(200, json={"data": {"data": payload["data"]}})
        if request.method == "DELETE":
            deleted.append(path)
            return httpx.Response(204)
        return httpx.Response(405)

    store = VaultKVSecretStore(
        address="https://vault.example.test",
        token="vault-token",
        mount="kv",
        prefix="multi-agent-test",
        transport=httpx.MockTransport(handler),
    )
    secret = "sk-test-secret-value-1234567890"

    meta = store.put_secret(tenant_id="tenant-a", name="openai.api_key", value=secret)
    resolved = store.get_secret(meta["secret_ref"])
    deleted_ok = store.delete_secret(meta["secret_ref"])

    assert resolved == secret
    assert deleted_ok is True
    assert meta["secret_ref"].startswith("vault:kv:")
    assert meta["last4"] == "7890"
    assert secret not in json.dumps(meta)
    assert deleted
    stored_payload = next(iter(writes.values()))
    assert stored_payload["data"]["tenant_id"] == "tenant-a"
    assert stored_payload["data"]["name"] == "openai.api_key"


def test_vault_store_requires_configuration() -> None:
    store = VaultKVSecretStore(address="", token="")

    try:
        store.put_secret(tenant_id="tenant-a", name="key", value="secret")
    except SecretStoreConfigurationError as exc:
        assert "VAULT_ADDR" in str(exc)
    else:
        raise AssertionError("expected missing VAULT_ADDR to fail")
