from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from runtime.connection_inference import InferredConnection, infer_connection
from runtime.platform_config import SECRET_FIELDS, normalize_connection_id
from runtime.redaction import redact_secret_text
from runtime.secret_store import SecretStore, create_secret_store_from_env
from tools.wrds_tools import WRDSConfig, WRDSTools


ConnectionStatus = Literal["draft", "pending_confirmation", "active", "failed", "disabled"]
DEFAULT_CONNECTION_CONTROL_PATH = ".local/connections.json"
DEFAULT_TENANT_ID = "default"


MODEL_PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "zhipu-openai-compatible": {
        "provider": "zhipu",
        "endpoint": "https://open.bigmodel.cn/api/paas/v4",
        "preferred_models": ["glm-5.1", "GLM-5.1"],
        "capability_types": ["chat_model", "web_search"],
    },
    "minimax-openai-compatible": {
        "provider": "minimax",
        "endpoint": "https://api.minimaxi.com/v1",
        "preferred_models": ["minimax-m2.7", "MiniMax-M2.7"],
        "capability_types": ["chat_model"],
    },
    "moonshot-openai-compatible": {
        "provider": "moonshot",
        "endpoint": "https://api.moonshot.cn/v1",
        "preferred_models": [
            "kimi-k2.6",
            "kimi-k2.5",
            "moonshot-v1-auto",
            "kimi-k2-thinking",
            "kimi-k2-thinking-turbo",
            "kimi-k2-turbo-preview",
            "kimi-k2-0905-preview",
            "kimi-k2-0711-preview",
            "moonshot-v1-128k",
            "moonshot-v1-32k",
            "moonshot-v1-8k",
        ],
        "capability_types": ["chat_model"],
    },
    "openai-compatible": {
        "provider": "openai_compatible",
        "endpoint": "",
        "preferred_models": [],
        "capability_types": ["chat_model"],
    },
    "openai": {
        "provider": "openai",
        "endpoint": "https://api.openai.com/v1",
        "preferred_models": ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
        "capability_types": ["chat_model"],
    },
    "anthropic": {
        "provider": "anthropic",
        "endpoint": "https://api.anthropic.com/v1",
        "preferred_models": [
            "claude-sonnet-4-5",
            "claude-opus-4-1",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
        "capability_types": ["chat_model"],
    },
}


@dataclass(frozen=True)
class ConnectionTestOptions:
    validate: bool = True
    discover: bool = True


class ConnectionControlPlane:
    """Tenant-aware local connection registry for AI-as-OS configuration."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self.path = Path(path or os.getenv("PLATFORM_CONNECTIONS_PATH", DEFAULT_CONNECTION_CONTROL_PATH))
        self.secret_store = secret_store or create_secret_store_from_env()

    def infer(self, *, raw: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        inferred = infer_connection(raw)
        candidate = self._candidate_from_inferred(inferred, tenant_id=tenant_id)
        return {
            "candidate": redact_candidate(candidate),
            "confidence": inferred.confidence,
            "reason": inferred.reason,
            "warnings": inferred.warnings,
            "suggested_tests": suggested_tests_for(candidate),
        }

    def confirm(
        self,
        *,
        raw: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        validate: bool = True,
        discover: bool = True,
    ) -> dict[str, Any]:
        inferred = infer_connection(raw)
        candidate = self._candidate_from_inferred(inferred, tenant_id=tenant_id)
        validation_result = self.test_candidate(candidate, validate=validate)
        capabilities = self.discover_candidate_capabilities(candidate, validation_result=validation_result) if discover else []
        status: ConnectionStatus = "active" if validation_result.get("ok", True) else "failed"
        record = self._record_from_candidate(
            candidate,
            status=status,
            validation_result=validation_result,
            capabilities=capabilities,
        )
        data = self._read()
        tenant = data.setdefault("tenants", {}).setdefault(tenant_id, {"connections": {}})
        tenant.setdefault("connections", {})[record["id"]] = record
        self._write(data)
        return redact_connection_record(record)

    def list_connections(
        self,
        *,
        tenant_id: str = DEFAULT_TENANT_ID,
        include_disabled: bool = True,
    ) -> list[dict[str, Any]]:
        records = self._tenant_connections(tenant_id)
        output = []
        for record in records:
            if not include_disabled and record.get("status") == "disabled":
                continue
            output.append(redact_connection_record(record))
        return output

    def list_active_connections(self, *, tenant_id: str = DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
        return [record for record in self._tenant_connections(tenant_id) if record.get("status") == "active"]

    def get_connection(self, *, connection_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any] | None:
        return self._tenant_connection_map(tenant_id).get(normalize_connection_id(connection_id))

    def test_connection(self, *, connection_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        record = self.get_connection(connection_id=connection_id, tenant_id=tenant_id)
        if not record:
            raise ValueError("connection not found")
        result = self._test_record(record)
        self._update_record(tenant_id=tenant_id, connection_id=connection_id, updates={"validation_result": result})
        return result

    def discover_connection(self, *, connection_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        record = self.get_connection(connection_id=connection_id, tenant_id=tenant_id)
        if not record:
            raise ValueError("connection not found")
        capabilities = self._discover_record_capabilities(record)
        self._update_record(tenant_id=tenant_id, connection_id=connection_id, updates={"capabilities": capabilities})
        return {"connection_id": normalize_connection_id(connection_id), "capabilities": capabilities}

    def disable_connection(self, *, connection_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        record = self.get_connection(connection_id=connection_id, tenant_id=tenant_id)
        if not record:
            raise ValueError("connection not found")
        self._update_record(tenant_id=tenant_id, connection_id=connection_id, updates={"status": "disabled"})
        updated = self.get_connection(connection_id=connection_id, tenant_id=tenant_id)
        return redact_connection_record(updated or {})

    def revoke_connection(self, *, connection_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        data = self._read()
        connection_id = normalize_connection_id(connection_id)
        connections = data.setdefault("tenants", {}).setdefault(tenant_id, {"connections": {}}).setdefault("connections", {})
        record = connections.get(connection_id)
        if not isinstance(record, dict):
            raise ValueError("connection not found")
        deleted_count = delete_record_secrets(self.secret_store, record)
        record.update(
            {
                "status": "disabled",
                "secret_refs": {},
                "secret_meta": {},
                "capabilities": [],
                "validation_result": {
                    "ok": False,
                    "status": "revoked",
                    "message": "Connection secrets were revoked by the user.",
                },
                "updated_at": utc_now(),
            }
        )
        self._write(data)
        redacted = redact_connection_record(record)
        return {**redacted, "revoked": True, "secrets_deleted": deleted_count}

    def delete_connection(self, *, connection_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        data = self._read()
        connection_id = normalize_connection_id(connection_id)
        connections = data.setdefault("tenants", {}).setdefault(tenant_id, {"connections": {}}).setdefault("connections", {})
        record = connections.pop(connection_id, None)
        if not isinstance(record, dict):
            raise ValueError("connection not found")
        deleted_count = delete_record_secrets(self.secret_store, record)
        self._write(data)
        return {"connection_id": connection_id, "tenant_id": tenant_id, "deleted": True, "secrets_deleted": deleted_count}

    def capability_index(self, *, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        connections = [redact_connection_record(record) for record in self.list_active_connections(tenant_id=tenant_id)]
        capabilities: list[dict[str, Any]] = []
        for record in connections:
            capabilities.extend(record.get("capabilities", []))
        return {
            "tenant_id": tenant_id,
            "connections": connections,
            "capabilities": capabilities,
            "model_providers": [item for item in connections if item.get("kind") == "model_provider"],
            "financial_data_sources": [item for item in connections if item.get("kind") == "financial_data_source"],
        }

    def secret_value(self, record: dict[str, Any], field: str) -> str | None:
        refs = record.get("secret_refs") if isinstance(record.get("secret_refs"), dict) else {}
        ref = refs.get(field)
        if not ref:
            return None
        return self.secret_store.get_secret(str(ref))

    def legacy_public_config(self, *, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
        connections = self.list_connections(tenant_id=tenant_id)
        return {
            "schema_version": 2,
            "model_providers": [item for item in connections if item.get("kind") == "model_provider"],
            "data_sources": [item for item in connections if item.get("kind") == "financial_data_source"],
        }

    def test_candidate(self, candidate: dict[str, Any], *, validate: bool) -> dict[str, Any]:
        if not validate:
            return {"ok": True, "status": "not_validated", "message": "Validation was skipped."}
        if candidate.get("kind") == "financial_data_source" and candidate.get("provider") == "wrds":
            return test_wrds_candidate(candidate)
        if candidate.get("kind") == "financial_data_source" and candidate.get("provider") == "fred":
            return test_fred_candidate(candidate)
        if candidate.get("kind") == "model_provider":
            return test_model_candidate(candidate)
        return {"ok": True, "status": "not_validated", "message": "No validator is available for this provider."}

    def discover_candidate_capabilities(
        self,
        candidate: dict[str, Any],
        *,
        validation_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if candidate.get("kind") == "financial_data_source" and candidate.get("provider") == "wrds":
            if not validation_result.get("ok"):
                return default_wrds_capabilities(connection_id=str(candidate["id"]), health="unknown")
            return discover_wrds_capabilities(candidate)
        if candidate.get("kind") == "financial_data_source" and candidate.get("provider") == "fred":
            return default_fred_capabilities(
                connection_id=str(candidate["id"]),
                health="ok" if validation_result.get("ok") else "unknown",
            )
        if candidate.get("kind") == "model_provider":
            return discover_model_capabilities(candidate, validation_result=validation_result)
        return []

    def _candidate_from_inferred(self, inferred: InferredConnection, *, tenant_id: str) -> dict[str, Any]:
        payload = dict(inferred.payload)
        provider = normalize_provider(payload.get("provider"))
        defaults = MODEL_PROVIDER_DEFAULTS.get(provider, {})
        connection_id = normalize_connection_id(inferred.connection_id)
        if provider == "wrds":
            endpoint = normalize_wrds_host(str(payload.get("base_url") or "wrds-pgdata.wharton.upenn.edu"))
        else:
            endpoint = str(payload.get("base_url") or defaults.get("endpoint") or "").rstrip("/")
        return {
            "id": connection_id,
            "tenant_id": tenant_id,
            "kind": inferred.kind,
            "provider": defaults.get("provider") or provider,
            "provider_key": provider,
            "display_name": payload.get("name") or connection_id,
            "endpoint": endpoint,
            "payload": payload,
            "confidence": inferred.confidence,
            "reason": inferred.reason,
            "warnings": inferred.warnings,
        }

    def _record_from_candidate(
        self,
        candidate: dict[str, Any],
        *,
        status: ConnectionStatus,
        validation_result: dict[str, Any],
        capabilities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now()
        payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
        secret_refs: dict[str, str] = {}
        secret_meta: dict[str, dict[str, Any]] = {}
        for field in SECRET_FIELDS | {"username"}:
            value = str(payload.get(field) or "").strip()
            if not value:
                continue
            meta = self.secret_store.put_secret(
                tenant_id=str(candidate["tenant_id"]),
                name=f"{candidate['id']}.{field}",
                value=value,
            )
            secret_refs[field] = meta["secret_ref"]
            secret_meta[field] = {"configured": True, "last4": meta["last4"]}
        return {
            "id": candidate["id"],
            "tenant_id": candidate["tenant_id"],
            "kind": candidate["kind"],
            "provider": candidate["provider"],
            "provider_key": candidate["provider_key"],
            "display_name": candidate["display_name"],
            "endpoint": candidate["endpoint"],
            "status": status,
            "secret_refs": secret_refs,
            "secret_meta": secret_meta,
            "capabilities": capabilities,
            "validation_result": validation_result,
            "config": sanitize_config(payload.get("config")),
            "created_at": now,
            "updated_at": now,
        }

    def _test_record(self, record: dict[str, Any]) -> dict[str, Any]:
        candidate = self._candidate_from_record(record)
        return self.test_candidate(candidate, validate=True)

    def _discover_record_capabilities(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        candidate = self._candidate_from_record(record)
        return self.discover_candidate_capabilities(
            candidate,
            validation_result=record.get("validation_result") if isinstance(record.get("validation_result"), dict) else {},
        )

    def _candidate_from_record(self, record: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": record.get("display_name"),
            "provider": record.get("provider_key") or record.get("provider"),
            "base_url": record.get("endpoint"),
            "config": record.get("config") if isinstance(record.get("config"), dict) else {},
        }
        for field in SECRET_FIELDS | {"username"}:
            payload[field] = self.secret_value(record, field)
        return {
            "id": record.get("id"),
            "tenant_id": record.get("tenant_id") or DEFAULT_TENANT_ID,
            "kind": record.get("kind"),
            "provider": record.get("provider"),
            "provider_key": record.get("provider_key") or record.get("provider"),
            "display_name": record.get("display_name") or record.get("id"),
            "endpoint": record.get("endpoint") or "",
            "payload": payload,
            "confidence": "high",
            "reason": "stored connection",
            "warnings": [],
        }

    def _update_record(self, *, tenant_id: str, connection_id: str, updates: dict[str, Any]) -> None:
        data = self._read()
        connection_id = normalize_connection_id(connection_id)
        record = data.setdefault("tenants", {}).setdefault(tenant_id, {"connections": {}}).setdefault("connections", {}).get(connection_id)
        if not isinstance(record, dict):
            raise ValueError("connection not found")
        record.update(updates)
        record["updated_at"] = utc_now()
        self._write(data)

    def _tenant_connections(self, tenant_id: str) -> list[dict[str, Any]]:
        return list(self._tenant_connection_map(tenant_id).values())

    def _tenant_connection_map(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        data = self._read()
        tenant = data.get("tenants", {}).get(tenant_id, {})
        connections = tenant.get("connections", {}) if isinstance(tenant, dict) else {}
        return connections if isinstance(connections, dict) else {}

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "tenants": {}}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "tenants": {}}
        if not isinstance(data, dict):
            return {"schema_version": 1, "tenants": {}}
        data.setdefault("schema_version", 1)
        data.setdefault("tenants", {})
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


def normalize_provider(value: Any) -> str:
    provider = str(value or "").strip().lower().replace("_", "-")
    if provider in {"zhipu", "glm", "bigmodel", "zhipu-openai-compatible"}:
        return "zhipu-openai-compatible"
    if provider in {"minimax", "minimax-openai-compatible"}:
        return "minimax-openai-compatible"
    if provider in {"kimi", "kimi-cn", "moonshot", "moonshot-cn", "moonshot-openai-compatible"}:
        return "moonshot-openai-compatible"
    if provider in {"openai-compatible", "generic-openai-compatible"}:
        return "openai-compatible"
    if provider in {"openai"}:
        return "openai"
    if provider in {"anthropic", "claude"}:
        return "anthropic"
    if provider == "wrds":
        return "wrds"
    if provider == "fred":
        return "fred"
    return provider


def redact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
    secret_meta = {}
    for field in SECRET_FIELDS | {"username"}:
        value = payload.get(field)
        if value:
            secret_meta[field] = {"configured": True, "last4": str(value)[-4:]}
    return {
        key: value
        for key, value in candidate.items()
        if key != "payload"
    } | {
        "secrets": secret_meta,
    }


def redact_connection_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "tenant_id": record.get("tenant_id"),
        "kind": record.get("kind"),
        "provider": record.get("provider"),
        "provider_key": record.get("provider_key"),
        "display_name": record.get("display_name"),
        "name": record.get("display_name"),
        "endpoint": record.get("endpoint"),
        "base_url": record.get("endpoint"),
        "status": record.get("status"),
        "secrets": record.get("secret_meta") if isinstance(record.get("secret_meta"), dict) else {},
        "capabilities": record.get("capabilities") if isinstance(record.get("capabilities"), list) else [],
        "validation_result": sanitize_validation_result(record.get("validation_result")),
        "config": record.get("config") if isinstance(record.get("config"), dict) else {},
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "enabled": record.get("status") == "active",
    }


def delete_record_secrets(secret_store: SecretStore, record: dict[str, Any]) -> int:
    refs = record.get("secret_refs") if isinstance(record.get("secret_refs"), dict) else {}
    deleted = 0
    for ref in refs.values():
        try:
            if secret_store.delete_secret(str(ref)):
                deleted += 1
        except Exception:  # noqa: BLE001
            continue
    return deleted


def suggested_tests_for(candidate: dict[str, Any]) -> list[dict[str, str]]:
    if candidate.get("kind") == "model_provider":
        return [
            {"id": "list_models", "label": "List available models"},
            {"id": "minimal_chat", "label": "Run a minimal chat completion if model listing is unavailable"},
        ]
    if candidate.get("provider") == "wrds":
        return [
            {"id": "wrds_status", "label": "Test WRDS login"},
            {"id": "wrds_capability_discovery", "label": "Discover visible WRDS libraries and tables"},
        ]
    if candidate.get("provider") == "fred":
        return [
            {"id": "fred_series", "label": "Fetch a small FEDFUNDS observation sample"},
            {"id": "fred_capability", "label": "Enable macro data series capability"},
        ]
    return [{"id": "basic_connection", "label": "Run provider-specific connection test"}]


def test_model_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
    api_key = str(payload.get("api_key") or "")
    endpoint = str(candidate.get("endpoint") or "").rstrip("/")
    if not endpoint:
        return {"ok": False, "status": "missing_endpoint", "message": "Model provider endpoint is missing."}
    if not api_key and "localhost" not in endpoint and "127.0.0.1" not in endpoint:
        return {"ok": False, "status": "missing_api_key", "message": "API key is missing."}
    if candidate.get("provider") == "anthropic":
        return test_anthropic_model_candidate(candidate, api_key=api_key, endpoint=endpoint)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(timeout=12, trust_env=False) as client:
            response = client.get(f"{endpoint}/models", headers=headers)
            if response.status_code < 400:
                models_payload = response.json()
                models = extract_model_ids(models_payload)
                return {
                    "ok": True,
                    "status": "models_listed",
                    "model_count": len(models),
                    "models": models[:50],
                }
            return {
                "ok": False,
                "status": f"http_{response.status_code}",
                "message": sanitize_remote_error(response.text),
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "connection_error", "message": sanitize_remote_error(str(exc))}


def test_anthropic_model_candidate(candidate: dict[str, Any], *, api_key: str, endpoint: str) -> dict[str, Any]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    try:
        with httpx.Client(timeout=12, trust_env=False) as client:
            response = client.get(f"{endpoint}/models", headers=headers)
            if response.status_code < 400:
                models = extract_model_ids(response.json())
                return {
                    "ok": True,
                    "status": "models_listed",
                    "model_count": len(models),
                    "models": models[:50],
                }
            return {
                "ok": False,
                "status": f"http_{response.status_code}",
                "message": sanitize_remote_error(response.text),
            }
    except Exception as exc:  # noqa: BLE001
        defaults = MODEL_PROVIDER_DEFAULTS.get(str(candidate.get("provider_key") or "anthropic"), {})
        return {
            "ok": True,
            "status": "assumed_anthropic",
            "message": f"Could not list Anthropic models; using default Claude model catalog: {sanitize_remote_error(str(exc))}",
            "models": list(defaults.get("preferred_models") or []),
        }


def test_wrds_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    tools = wrds_tools_from_candidate(candidate)
    result = tools.status(check_connection=True)
    return {
        "ok": result.ok,
        "status": "connected" if result.ok else "failed",
        "data": result.data,
        "message": result.error,
    }


def test_fred_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
    api_key = str(payload.get("api_key") or "")
    if not api_key:
        return {"ok": False, "status": "missing_api_key", "message": "FRED API key is missing."}
    try:
        with httpx.Client(timeout=12, trust_env=False) as client:
            response = client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "FEDFUNDS",
                    "api_key": api_key,
                    "file_type": "json",
                    "limit": 1,
                    "sort_order": "desc",
                },
            )
            if response.status_code < 400:
                return {"ok": True, "status": "connected", "message": "FRED series endpoint is reachable."}
            return {
                "ok": False,
                "status": f"http_{response.status_code}",
                "message": sanitize_remote_error(response.text),
            }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "connection_error", "message": sanitize_remote_error(str(exc))}


def discover_model_capabilities(
    candidate: dict[str, Any],
    *,
    validation_result: dict[str, Any],
) -> list[dict[str, Any]]:
    connection_id = str(candidate["id"])
    models = validation_result.get("models") if isinstance(validation_result.get("models"), list) else []
    provider_key = str(candidate.get("provider_key") or "")
    defaults = MODEL_PROVIDER_DEFAULTS.get(provider_key, {})
    if not models:
        models = list(defaults.get("preferred_models") or [])
    capability_types = defaults.get("capability_types") or ["chat_model"]
    return [
        {
            "connection_id": connection_id,
            "type": capability_type,
            "provider": candidate.get("provider"),
            "models": models,
            "health": "ok" if validation_result.get("ok") else "unknown",
        }
        for capability_type in capability_types
    ]


def discover_wrds_capabilities(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    result = wrds_tools_from_candidate(candidate).capability_discovery(libraries=[], max_tables_per_library=25)
    if not result.ok:
        return default_wrds_capabilities(connection_id=str(candidate["id"]), health="unknown")
    capabilities = result.data.get("capabilities") if isinstance(result.data, dict) else {}
    output = []
    if isinstance(capabilities, dict):
        for name, payload in capabilities.items():
            payload = payload if isinstance(payload, dict) else {}
            output.append(
                {
                    "connection_id": candidate["id"],
                    "type": wrds_capability_type(name),
                    "provider": "wrds",
                    "package": name,
                    "available": bool(payload.get("available")),
                    "libraries": payload.get("libraries") or [],
                    "tables": payload.get("tables") or [],
                    "health": "ok",
                }
            )
    return output or default_wrds_capabilities(connection_id=str(candidate["id"]), health="unknown")


def default_wrds_capabilities(*, connection_id: str, health: str) -> list[dict[str, Any]]:
    return [
        {
            "connection_id": connection_id,
            "type": "financial_fundamentals",
            "provider": "wrds",
            "package": "compustat_fundamentals",
            "available": None,
            "health": health,
        }
    ]


def default_fred_capabilities(*, connection_id: str, health: str) -> list[dict[str, Any]]:
    return [
        {
            "connection_id": connection_id,
            "type": "macro_data",
            "provider": "fred",
            "package": "fred_series_observations",
            "available": True if health == "ok" else None,
            "health": health,
        }
    ]


def wrds_capability_type(name: str) -> str:
    mapping = {
        "compustat_fundamentals": "financial_fundamentals",
        "crsp_market_data": "market_prices",
        "ibes_estimates": "estimates",
        "compustat_segments": "segments",
        "capital_iq": "company_profile",
        "audit_analytics": "filings",
        "optionmetrics": "derivatives",
    }
    return mapping.get(name, "financial_data")


def wrds_tools_from_candidate(candidate: dict[str, Any]) -> WRDSTools:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
    host = normalize_wrds_host(str(candidate.get("endpoint") or payload.get("base_url") or "wrds-pgdata.wharton.upenn.edu"))
    return WRDSTools(
        config=WRDSConfig(
            username=str(payload.get("username") or payload.get("account") or "") or None,
            password=str(payload.get("password") or "") or None,
            host=host,
            dbname=str(payload.get("database") or "wrds"),
        )
    )


def normalize_wrds_host(value: str) -> str:
    text = str(value or "").strip() or "wrds-pgdata.wharton.upenn.edu"
    parsed = urlparse(text)
    return parsed.hostname or text.replace("https://", "").replace("http://", "").split("/", 1)[0]


def extract_model_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("models")
    if not isinstance(raw, list):
        return []
    ids = []
    for item in raw:
        if isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
            if model_id:
                ids.append(str(model_id))
        elif isinstance(item, str):
            ids.append(item)
    return ids


def sanitize_validation_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    clean = dict(result)
    if "message" in clean:
        clean["message"] = sanitize_remote_error(str(clean["message"]))
    return clean


def sanitize_remote_error(value: str) -> str:
    return redact_secret_text(value, limit=500)


def sanitize_config(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
