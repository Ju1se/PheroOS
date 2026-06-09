# Capability Security Roadmap

PheroOS capability security evolves in stages. The current runtime exposes the
same stages through each capability `security_diagnostics.roadmap` report so
security posture is visible to tests, dashboards, and reviewers.

## v0.1: Local Trusted Capabilities

Status: active.

Controls:

- `manifest_validation`: enforced;
- `checksum_display`: diagnostic;
- `network_allowlist_declaration`: declared;
- `permission_confirmation`: enforced;
- `quarantine_signal`: diagnostic;
- `model_gateway_boundary`: enforced;
- `tool_registry_boundary`: enforced;
- `secret_handle_boundary`: enforced.

This stage supports local first-party and reviewed capabilities. Untrusted
capabilities are blocked when they request arbitrary network, filesystem write,
direct secrets, direct model calls, direct tool execution, blocking governance
signals, or dangerous imports. Checksum and quarantine controls are currently
reported as diagnostics unless a downstream runtime policy chooses to turn them
into hard activation gates.

## v0.2: Signed Capabilities

Status: planned.

Controls:

- `capability_signing`: planned;
- `public_key_trust_store`: planned;
- `provenance_metadata`: planned;
- `revocation_list`: planned;
- `install_audit_log`: planned.

The v0.2 goal is supply-chain verification before activation, not a marketplace
UI. Installation should become explainable and revocable before distribution is
made easy.

## v0.3: Sandboxed Execution

Status: planned.

Controls:

- `restricted_imports`: planned;
- `subprocess_isolation`: planned;
- `network_policy_enforcement`: planned;
- `filesystem_mount_policy`: planned;
- `resource_limits`: planned;
- `deterministic_tool_boundary`: planned.

The v0.3 goal is execution isolation for third-party code. Agents and
capability code still do not receive raw secrets, direct provider clients, or
unmediated shell/network/filesystem authority.
