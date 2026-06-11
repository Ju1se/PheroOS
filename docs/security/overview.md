# Security Model

The protocol-core package provides contract-level safety invariants:

- agents are proposal sources
- governance authority verifies signals
- writers cannot create facts
- stop signals block target actions
- output requires committed candidate and publication permission
- drivers provide structured capability only
- trace events preserve decision lineage

Runtime sandboxing and provider enforcement belong to reference runtimes outside this core package.
