from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from runtime.secret_store import LocalEncryptedSecretStore, SecretStore, create_secret_store_from_env


ConnectionKind = Literal["model_provider", "financial_data_source"]
SECRET_FIELDS = {"api_key", "password", "access_token", "secret", "token"}
DEFAULT_PLATFORM_CONFIG_PATH = ".local/platform_config.json"
ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


class PlatformConfigStore:
    """Local BYOK/BYOD connection store.

    This store is intended for localhost/self-hosted deployments. It redacts
    secrets on read and keeps the on-disk file mode owner-only when possible.
    Production deployments should replace this adapter with a KMS/Vault backed
    implementation through the same API surface.
    """

    def __init__(self, path: str | Path | None = None, secret_store: SecretStore | None = None) -> None:
        self.path = Path(path or os.getenv("PLATFORM_CONFIG_PATH", DEFAULT_PLATFORM_CONFIG_PATH))
        self.secret_store = secret_store or (
            LocalEncryptedSecretStore(
                path=self.path.with_suffix(f"{self.path.suffix}.secrets.json"),
                key_path=self.path.with_suffix(f"{self.path.suffix}.secret.key"),
            )
            if not os.getenv("PLATFORM_SECRET_STORE_BACKEND")
            else create_secret_store_from_env()
        )

    def public_config(self) -> dict[str, Any]:
        data = self._read()
        return {
            "schema_version": data.get("schema_version", 1),
            "model_providers": [
                redact_connection(connection) for connection in data.get("model_providers", {}).values()
            ],
            "data_sources": [
                redact_connection(connection) for connection in data.get("data_sources", {}).values()
            ],
        }

    def upsert_model_provider(self, connection_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._upsert("model_provider", connection_id, payload)

    def upsert_data_source(self, connection_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._upsert("financial_data_source", connection_id, payload)

    def delete_model_provider(self, connection_id: str) -> bool:
        return self._delete("model_provider", connection_id)

    def delete_data_source(self, connection_id: str) -> bool:
        return self._delete("financial_data_source", connection_id)

    def _upsert(self, kind: ConnectionKind, connection_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_id = normalize_connection_id(connection_id)
        data = self._read()
        bucket_name = bucket_for_kind(kind)
        bucket = data.setdefault(bucket_name, {})
        existing = bucket.get(safe_id, {}) if isinstance(bucket.get(safe_id), dict) else {}
        merged = {
            **existing,
            **sanitize_connection_payload(payload),
            "id": safe_id,
            "kind": kind,
        }
        for field in SECRET_FIELDS:
            value = str(payload.get(field) or "").strip() if field in payload else ""
            secret_refs = merged.setdefault("secret_refs", existing.get("secret_refs", {}) if isinstance(existing.get("secret_refs"), dict) else {})
            secret_meta = merged.setdefault("secret_meta", existing.get("secret_meta", {}) if isinstance(existing.get("secret_meta"), dict) else {})
            if value:
                meta = self.secret_store.put_secret(tenant_id="default", name=f"{safe_id}.{field}", value=value)
                secret_refs[field] = meta["secret_ref"]
                secret_meta[field] = {"configured": True, "last4": meta["last4"]}
            elif field in existing and existing.get(field):
                meta = self.secret_store.put_secret(tenant_id="default", name=f"{safe_id}.{field}", value=str(existing[field]))
                secret_refs[field] = meta["secret_ref"]
                secret_meta[field] = {"configured": True, "last4": meta["last4"]}
        for field in SECRET_FIELDS:
            merged.pop(field, None)
        bucket[safe_id] = merged
        self._write(data)
        return redact_connection(merged)

    def _delete(self, kind: ConnectionKind, connection_id: str) -> bool:
        safe_id = normalize_connection_id(connection_id)
        data = self._read()
        bucket = data.setdefault(bucket_for_kind(kind), {})
        existed = safe_id in bucket
        bucket.pop(safe_id, None)
        self._write(data)
        return existed

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return empty_config()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return empty_config()
        if not isinstance(data, dict):
            return empty_config()
        data.setdefault("schema_version", 1)
        data.setdefault("model_providers", {})
        data.setdefault("data_sources", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def empty_config() -> dict[str, Any]:
    return {"schema_version": 1, "model_providers": {}, "data_sources": {}}


def bucket_for_kind(kind: ConnectionKind) -> str:
    return "model_providers" if kind == "model_provider" else "data_sources"


def normalize_connection_id(value: str) -> str:
    text = ID_RE.sub("-", str(value or "").strip()).strip("-._").lower()
    if not text:
        raise ValueError("connection id must not be empty")
    return text[:80]


def sanitize_connection_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "name",
        "provider",
        "base_url",
        "api_key",
        "username",
        "password",
        "access_token",
        "account",
        "database",
        "enabled",
        "config",
    }
    clean: dict[str, Any] = {}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        if key == "config":
            clean[key] = value if isinstance(value, dict) else {}
        elif key == "enabled":
            clean[key] = bool(value)
        elif value is None:
            clean[key] = None
        else:
            clean[key] = str(value).strip()
    clean.setdefault("enabled", True)
    clean.setdefault("config", {})
    return clean


def redact_connection(connection: dict[str, Any]) -> dict[str, Any]:
    redacted = {
        key: value
        for key, value in connection.items()
        if key not in SECRET_FIELDS
    }
    secrets = {}
    secret_meta = connection.get("secret_meta")
    if isinstance(secret_meta, dict):
        for field, meta in secret_meta.items():
            if isinstance(meta, dict) and meta.get("configured"):
                secrets[field] = {"configured": True, "last4": str(meta.get("last4") or "")}
    for field in SECRET_FIELDS:
        value = connection.get(field)
        if value:
            secrets[field] = {"configured": True, "last4": str(value)[-4:]}
    redacted["secrets"] = secrets
    return redacted
