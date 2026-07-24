# Security Policy

## Supported Versions

This project is pre-1.0. Security fixes target the current `main` branch.

## Reporting a Vulnerability

Do not open a public issue for a vulnerability report.

Use GitHub private vulnerability reporting when it is available for the
repository. It is the only repository-owned private reporting route documented
here. If it is unavailable for a repository or fork, consult that repository's
Security page or maintainer documentation for a verified private contact; do
not guess an address or open a public issue.

A useful report should include:

- affected commit, tag, or package version
- description of the issue
- protocol surface involved
- reproduction steps or a minimal manifest
- expected and observed behavior
- security impact
- suspected code location, if known
- proposed fix or mitigation, if known

## Protocol-Core Security Scope

PheroOS protocol-core provides contract-level safety invariants. In-scope
security issues include:

- manifest validation accepting secret-like fields or authority-bypassing metadata
- governance authority checks allowing agents to verify their own signals
- quorum or collective decision logic committing undeclared candidates
- output authorization succeeding without required evidence, stop resolution, or publication permission
- trace validation accepting lineage that hides required decision events
- conformance checks reporting compatibility for an incompatible ABI implementation
- driver declarations treating provider configuration as an in-core secret
- scoped-authority session or StateStore behavior accepting cross-scope, stale,
  non-atomic, or portable-data-only authority
- release verification rebuilding, substituting, or attesting bytes other than
  the exact candidate subject, or exposing workflow credentials

Out-of-scope issues include:

- vulnerabilities in external runtimes, provider adapters, applications, dashboards, queues, databases, or servers
- prompt injection behavior in application-specific agents
- provider SDK vulnerabilities
- deployment-specific secret handling outside protocol manifests
- domain workflow policy decisions outside protocol-core

## Boundary Rules

- Protocol manifests must not contain API keys, passwords, tokens, credentials, or secrets.
- Provider configuration belongs outside protocol-core and should be referenced only through opaque external references such as `config_ref`.
- Agents are proposal sources, not authority.
- Governance authority is required to verify signals and authorize output.
- Trace records explain lineage; trace records do not grant permission.
- Conformance proves compatibility; it does not replace deployment security review.

## Authority Trust Boundary

The legacy Draft v1 issuer surface is a trusted-host compatibility profile.
Passing `AuthorityLevel.GOVERNANCE`, an issuer string, a digest, a receipt id,
or a same-shaped record does not authenticate a principal. A deployment must
not expose those Python issuer functions directly to an agent, model, tool, or
untrusted plugin.

The accepted and locally implemented Draft v2 design is documented in the
[authority decision](docs/protocol/authority-v2-decision.md),
[threat model](docs/protocol/authority-trust-model-v2.md), and
[migration contract](docs/protocol/authority-v2-migration.md). Its public
[Authority Session ABI](docs/protocol/authority-session-v2.md) separates:

- a trusted host that binds a non-portable, scope- and operation-limited
  authority session;
- a selected `GovernanceStateStoreV2` writer that atomically validates the
  complete authority read-set and commits state, authority-critical Trace, and
  the receipt;
- a reader that may recover historical authority only after verifying local
  committed inclusion; and
- an external runtime that performs publication or execution only from a
  current, action-bound authorization.

Returning a committed terminal outcome is delivery, not publication or
execution. Denial of current action authority must not suppress that typed
terminal result.

The public Draft Authority Session v2 slice makes the local trust root an
opaque, store-bound, run- and request-specific session. The local profile proves
trusted-host/store possession only. The authenticated profile additionally
requires a host-selected issuer grant verifier for new activation and each
capability bind; protocol-core does not manage keys, KMS, IdP, credentials, or
network authentication. Passing the bundled provider-free Conformance matrix
demonstrates the Draft contract only in its test context; it does not activate
an authenticated deployment or satisfy formal Stable promotion, a production
runtime, or process isolation. Arbitrary Python code executing in the
coordinator or StateStore-writer process is outside the isolation guarantee. A
deployment claiming production isolation must keep untrusted code outside
those processes and enforce process, credential, and capability boundaries.
Hashes prove canonical integrity, not identity or permission.

## Disclosure and Fix Handling

Security fixes should be small, reviewable, and tied to a protocol invariant.

When a fix changes public API, ABI, schema shape, or conformance behavior, it
should include tests, migration notes, and a changelog entry.
