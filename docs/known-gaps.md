# Known Gaps

- Built-in tools still need full capability-scoped permission registration.
- PheroOS has tenant-scoped SQLite debugger queries and tenant-filtered local
  JSONL/profile views, but full production run storage still needs retention,
  pagination, migrations, authentication/RBAC, and PostgreSQL support.
- Tool and permission event tables exist in the SQLite schema, but not every
  runtime tool/permission event is populated yet.
- SaaS deployment now has a Vault KV-v2 `SecretStore` adapter, but still needs
  real Vault/KMS operations work: auth/RBAC, token renewal, rotation policy,
  audit integration, backup/restore, and deployment runbooks.
- WRDS package coverage now has deterministic adapters for Compustat/CRSP,
  Capital IQ profile, OptionMetrics security snapshots, IBES estimates,
  Compustat segments, and peer comparison. Depth still depends on account
  entitlements, foreign-company coverage, and table-specific field availability.
- Dashboard now has a simpler OpenAI/Claude-like compose-first home surface
  covered by browser visual regression tests. Future work is product polish
  rather than an architecture blocker.
- Third-party capability security now has manifest diagnostics, checksum
  status, sandbox policy, import declarations, network allowlists, and
  PheroOS quarantine signals. Production marketplace support still needs real
  signature verification, sandboxed code execution, and a reviewed distribution
  pipeline.
