# Commit Integrity ABI — Historical Design Record

Status: superseded by the implemented Optimal Commit Draft ABI.

This design record introduced the separation between attention/memory,
epistemic qualification, commit authority, certificate/finality, and output
actions. Its normative threat model, fixed-point semantics, bounded liveness,
assurance profiles, and action-scoped authority now live in:

- [Optimal Commit ABI](optimal-commit-abi.md)
- [Optimal Commit v1 Migration](optimal-commit-v1-migration.md)
- [Runtime Integration Contract](runtime-integration.md)
- [Conformance Suite](../conformance/conformance-suite.md)

Hybrid pheromone pressure remains non-authoritative. Evidence, risk,
membership, stability, certificate/finality, stop, and permission gates decide
commit and output.

The full historical proposal remains available in Git history. This stub is
kept only for link compatibility and is not an active source of requirements.
