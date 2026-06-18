## Protocol-Core Review

- [ ] Public API or ABI impact is described, or this PR has no public API/ABI impact.
- [ ] Schema changes are reflected in checked-in schema artifacts and schema export tests, or no schema changed.
- [ ] Changelog or migration notes are updated when public behavior changes.
- [ ] Protocol models and validation remain domain-neutral.
- [ ] Kernel code does not import app/runtime/provider frameworks.
- [ ] Governance code keeps agents as proposal sources only.
- [ ] Driver code exposes capability only, not final authority.
- [ ] Conformance logic lives in `pheroos.conformance`, not CLI glue.
- [ ] `examples/toy-protocol` still validates and passes conformance.
- [ ] `examples/e2e-protocol` still validates and passes conformance.
- [ ] `examples/swarm-protocol` still validates and passes conformance when swarm behavior is changed.
- [ ] `python -m pytest -q` passes.
