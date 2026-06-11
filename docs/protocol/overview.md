# Protocol ABI

`pheroos.protocol` defines the public manifest and validation surface for governed runtimes.

The protocol layer owns:

- capability manifests
- protocol manifests
- target declarations
- candidate declarations
- quorum policy
- recovery policy
- output policy
- trace policy
- validation diagnostics

The protocol layer is pure contract code. It does not import kernel, governance, driver, CLI, example, app, runtime, or provider modules.

## Invariants

- Every candidate references a declared target.
- Quorum fallback references a declared safe fallback candidate.
- Recovery trigger targets are declared.
- Recovery failure candidates are declared.
- Writer fact creation is not permitted.
- Trace policy includes lineage for block, commit, recovery, and output decisions.
