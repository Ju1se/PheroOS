from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx


DEFAULT_SECRET_STORE_PATH = ".local/secrets.json"
DEFAULT_SECRET_KEY_PATH = ".local/secret.key"
DEFAULT_VAULT_MOUNT = "secret"
DEFAULT_VAULT_PREFIX = "multi-agent"


class SecretStore(Protocol):
    def put_secret(self, *, tenant_id: str, name: str, value: str) -> dict[str, str]:
        """Store a secret and return redacted metadata with a secret_ref."""

    def get_secret(self, secret_ref: str) -> str:
        """Resolve a secret_ref to a plaintext value."""

    def delete_secret(self, secret_ref: str) -> bool:
        """Delete a stored secret."""


class SecretStoreConfigurationError(RuntimeError):
    """Raised when a requested SecretStore backend is not configured."""


@dataclass(frozen=True)
class LocalEncryptedSecretStore:
    """Small local encrypted-at-rest store for OSS/self-hosted mode.

    This adapter is intentionally replaceable. Production SaaS deployments
    should provide a KMS/Vault-backed SecretStore with the same methods.
    """

    path: str | Path | None = None
    key_path: str | Path | None = None
    master_key: str | None = None

    @property
    def store_path(self) -> Path:
        return Path(self.path or os.getenv("PLATFORM_SECRET_STORE_PATH", DEFAULT_SECRET_STORE_PATH))

    @property
    def local_key_path(self) -> Path:
        return Path(self.key_path or os.getenv("PLATFORM_SECRET_KEY_PATH", DEFAULT_SECRET_KEY_PATH))

    def put_secret(self, *, tenant_id: str, name: str, value: str) -> dict[str, str]:
        value = str(value or "")
        if not value:
            raise ValueError("secret value must not be empty")
        data = self._read()
        secret_ref = f"local:{safe_part(tenant_id)}:{uuid.uuid4().hex}"
        data["secrets"][secret_ref] = {
            "tenant_id": safe_part(tenant_id),
            "name": safe_part(name),
            "ciphertext": self._encrypt(value),
            "last4": value[-4:],
            "created_at": utc_now(),
        }
        self._write(data)
        return {
            "secret_ref": secret_ref,
            "configured": True,
            "last4": value[-4:],
        }

    def get_secret(self, secret_ref: str) -> str:
        data = self._read()
        payload = data.get("secrets", {}).get(secret_ref)
        if not isinstance(payload, dict):
            raise KeyError(f"secret not found: {secret_ref}")
        return self._decrypt(str(payload.get("ciphertext") or ""))

    def delete_secret(self, secret_ref: str) -> bool:
        data = self._read()
        existed = secret_ref in data.get("secrets", {})
        data.setdefault("secrets", {}).pop(secret_ref, None)
        self._write(data)
        return existed

    def _read(self) -> dict[str, object]:
        if not self.store_path.exists():
            return {"schema_version": 1, "secrets": {}}
        try:
            with self.store_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "secrets": {}}
        if not isinstance(data, dict):
            return {"schema_version": 1, "secrets": {}}
        data.setdefault("schema_version", 1)
        data.setdefault("secrets", {})
        return data

    def _write(self, data: dict[str, object]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.store_path.with_suffix(f"{self.store_path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, self.store_path)
        try:
            self.store_path.chmod(0o600)
        except OSError:
            pass

    def _key(self) -> bytes:
        explicit = self.master_key or os.getenv("PLATFORM_SECRET_KEY")
        if explicit:
            return hashlib.sha256(explicit.encode("utf-8")).digest()

        if not self.local_key_path.exists():
            self.local_key_path.parent.mkdir(parents=True, exist_ok=True)
            key = secrets.token_urlsafe(48)
            with self.local_key_path.open("w", encoding="utf-8") as handle:
                handle.write(key)
                handle.write("\n")
            try:
                self.local_key_path.chmod(0o600)
            except OSError:
                pass
        return hashlib.sha256(self.local_key_path.read_text(encoding="utf-8").strip().encode("utf-8")).digest()

    def _encrypt(self, plaintext: str) -> str:
        key = self._key()
        nonce = secrets.token_bytes(16)
        plain = plaintext.encode("utf-8")
        cipher = xor_stream(plain, key=key, nonce=nonce)
        mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")

    def _decrypt(self, encoded: str) -> str:
        key = self._key()
        payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
        if len(payload) < 48:
            raise ValueError("invalid encrypted secret payload")
        nonce, mac, cipher = payload[:16], payload[16:48], payload[48:]
        expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("secret payload authentication failed")
        return xor_stream(cipher, key=key, nonce=nonce).decode("utf-8")


@dataclass(frozen=True)
class VaultKVSecretStore:
    """HashiCorp Vault KV-v2 backed SecretStore for production SaaS.

    The local connection-control plane stores only `vault:*` references and
    redacted metadata. Plaintext credentials are written to and resolved from
    Vault at runtime through this adapter. Tests can provide an `httpx`
    transport; production uses `VAULT_ADDR` and `VAULT_TOKEN`.
    """

    address: str | None = None
    token: str | None = None
    mount: str | None = None
    prefix: str | None = None
    namespace: str | None = None
    timeout: float = 10.0
    transport: httpx.BaseTransport | None = None

    @property
    def vault_addr(self) -> str:
        address = (self.address or os.getenv("VAULT_ADDR") or "").rstrip("/")
        if not address:
            raise SecretStoreConfigurationError("VAULT_ADDR is required for PLATFORM_SECRET_STORE_BACKEND=vault")
        return address

    @property
    def vault_token(self) -> str:
        token = self.token or os.getenv("VAULT_TOKEN") or os.getenv("PLATFORM_VAULT_TOKEN") or ""
        if not token:
            raise SecretStoreConfigurationError("VAULT_TOKEN is required for PLATFORM_SECRET_STORE_BACKEND=vault")
        return token

    @property
    def vault_mount(self) -> str:
        return safe_part(self.mount or os.getenv("VAULT_KV_MOUNT") or DEFAULT_VAULT_MOUNT)

    @property
    def vault_prefix(self) -> str:
        raw = self.prefix or os.getenv("VAULT_KV_PREFIX") or DEFAULT_VAULT_PREFIX
        return "/".join(safe_part(part) for part in str(raw).split("/") if part.strip())

    def put_secret(self, *, tenant_id: str, name: str, value: str) -> dict[str, str]:
        value = str(value or "")
        if not value:
            raise ValueError("secret value must not be empty")
        tenant = safe_part(tenant_id)
        secret_name = safe_part(name)
        path = f"{self.vault_prefix}/{tenant}/{secret_name}/{uuid.uuid4().hex}"
        payload = {
            "data": {
                "value": value,
                "tenant_id": tenant,
                "name": secret_name,
                "last4": value[-4:],
                "created_at": utc_now(),
            }
        }
        self._request("POST", self._data_url(path), json=payload)
        return {"secret_ref": self._secret_ref(path), "configured": True, "last4": value[-4:]}

    def get_secret(self, secret_ref: str) -> str:
        path = self._path_from_ref(secret_ref)
        response = self._request("GET", self._data_url(path))
        payload = response.json()
        value = (((payload.get("data") or {}).get("data") or {}).get("value")) if isinstance(payload, dict) else None
        if value is None:
            raise KeyError(f"secret not found: {secret_ref}")
        return str(value)

    def delete_secret(self, secret_ref: str) -> bool:
        path = self._path_from_ref(secret_ref)
        response = self._request("DELETE", self._data_url(path), allow_not_found=True)
        return response.status_code != 404

    def _headers(self) -> dict[str, str]:
        headers = {"X-Vault-Token": self.vault_token}
        namespace = self.namespace or os.getenv("VAULT_NAMESPACE")
        if namespace:
            headers["X-Vault-Namespace"] = namespace
        return headers

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, transport=self.transport, trust_env=False) as client:
            response = client.request(method, url, headers=self._headers(), json=json)
        if allow_not_found and response.status_code == 404:
            return response
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SecretStoreConfigurationError(
                f"Vault secret store request failed with HTTP {response.status_code}"
            ) from exc
        return response

    def _data_url(self, path: str) -> str:
        return f"{self.vault_addr}/v1/{self.vault_mount}/data/{path.strip('/')}"

    def _secret_ref(self, path: str) -> str:
        encoded_path = base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")
        return f"vault:{self.vault_mount}:{encoded_path}"

    def _path_from_ref(self, secret_ref: str) -> str:
        parts = str(secret_ref or "").split(":", 2)
        if len(parts) != 3 or parts[0] != "vault" or parts[1] != self.vault_mount:
            raise KeyError(f"secret not found: {secret_ref}")
        padding = "=" * (-len(parts[2]) % 4)
        try:
            path = base64.urlsafe_b64decode((parts[2] + padding).encode("ascii")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise KeyError(f"secret not found: {secret_ref}") from exc
        if not path.startswith(f"{self.vault_prefix}/"):
            raise KeyError(f"secret not found: {secret_ref}")
        return path


def create_secret_store_from_env() -> SecretStore:
    backend = os.getenv("PLATFORM_SECRET_STORE_BACKEND", "local").strip().lower().replace("_", "-")
    if backend in {"", "local", "local-encrypted", "file"}:
        return LocalEncryptedSecretStore()
    if backend in {"vault", "vault-kv", "hashicorp-vault", "kms-vault"}:
        return VaultKVSecretStore()
    raise SecretStoreConfigurationError(f"unknown PLATFORM_SECRET_STORE_BACKEND: {backend}")


def xor_stream(payload: bytes, *, key: bytes, nonce: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(payload):
        block = hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(byte ^ mask for byte, mask in zip(payload, output, strict=False))


def safe_part(value: str) -> str:
    text = "".join(char if char.isalnum() or char in {"_", "-", "."} else "-" for char in str(value or "default"))
    return text.strip("-._").lower() or "default"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
