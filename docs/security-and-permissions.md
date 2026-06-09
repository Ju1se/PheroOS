# Security and Permissions

## Permission Classes

Auto-grant low-risk permissions:

- `data:read`
- `model:chat`
- `skill:read`
- `tool:deterministic-read`
- `network:approved-provider`
- `network:wrds`
- `secret:wrds`
- `secret:model-provider`

Require confirmation:

- `filesystem:write`
- `shell:execute`
- `network:arbitrary`
- `email:send`
- `trade:execute`
- `database:write`
- `credential:export`

Unknown permissions are treated as confirmation-required.

## Secret Handling

- Secrets are stored by reference.
- API responses are redacted.
- Run metadata, audit logs, trace payloads, model prompts, and dashboard state
  must not include raw secrets.
- Tests should use fake keys and should assert redaction.

## Tool Boundary

All tool execution must go through `runtime/tool_registry.py`. New tools should
declare permissions, required connections, and return structured
success/failure results. Tool manifest entries expose both `granted` and
`connection_granted`; runtime execution fails with a structured
`permission_required` or `connection_required` result before the callable is
invoked.

## Capability Sandbox Contract

Capability manifests now carry a security contract in addition to permissions:

- `trust_level`: `core_system`, `first_party_reviewed`,
  `trusted_first_party`, `user_installed`, `third_party_untrusted`, or
  `external_content`.
- `sandbox.network`: `deny_by_default`, `approved_provider_only`,
  `wrds_only`, `allowlisted_domains`, or a stricter equivalent.
- `sandbox.filesystem`: defaults to `read_only`; write access must be declared
  and permission-gated.
- `sandbox.secrets`: must be `no_direct_access`; capabilities receive handles,
  not raw keys.
- `sandbox.model_calls`: must be `gateway_only`.
- `sandbox.tools`: must be `registry_only`.
- `allowed_imports` and `network_allowlist`: explicit declarations for
  reviewed capability code.
- `signature` / `checksum`: dashboard-visible supply-chain status. Unsigned
  first-party local capabilities are allowed, but untrusted capabilities without
  a signature or checksum are blocked by the sandbox auditor.

`runtime/capability_manifest_security.py` validates these fields and computes a
stable capability directory checksum. `runtime/swarm/capability_sandbox.py`
turns violations into PheroOS risk/quarantine signals. Third-party capabilities
cannot emit `stop_signal`, `quarantine`, or `trust_badge`, cannot use arbitrary
network or filesystem write access, and cannot bypass ModelGateway,
ToolRegistry, or SecretStore handles.

The staged capability security roadmap is documented in
[`docs/security/capability-security-roadmap.md`](security/capability-security-roadmap.md)
and is exposed in each capability `security_diagnostics.roadmap` report.

## Secret Store Backends

`runtime/secret_store.py` exposes a replaceable `SecretStore` interface.

- Default OSS/self-host mode uses `LocalEncryptedSecretStore` and owner-only
  local files.
- Production can set `PLATFORM_SECRET_STORE_BACKEND=vault` to use
  `VaultKVSecretStore` against HashiCorp Vault KV-v2.
- Required Vault configuration: `VAULT_ADDR`, `VAULT_TOKEN`; optional:
  `VAULT_KV_MOUNT`, `VAULT_KV_PREFIX`, `VAULT_NAMESPACE`.
- Connection records store only `secret_ref`, `configured`, and `last4`.
  Plaintext secrets are resolved only inside approved control-plane/model/data
  adapter code paths.
- Capabilities and agents never receive the `SecretStore` object or raw
  credential values; they receive capability/tool/model handles through
  `RuntimeContext`.
