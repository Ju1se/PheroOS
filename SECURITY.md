# Security Policy

## Supported Versions

This project is pre-1.0. Security fixes target the current `main` branch.

## Reporting a Vulnerability

Do not open a public issue for a vulnerability report.

Use GitHub private vulnerability reporting when it is available for the
repository. If it is not available, contact the maintainers privately through
the maintainer channel for the fork or deployment you are using.

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

## Disclosure and Fix Handling

Security fixes should be small, reviewable, and tied to a protocol invariant.

When a fix changes public API, ABI, schema shape, or conformance behavior, it
should include tests, migration notes, and a changelog entry.
