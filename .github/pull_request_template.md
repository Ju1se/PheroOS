## Protocol-Core Review

- [ ] Protocol models and validation remain domain-neutral.
- [ ] Kernel code does not import app/runtime/provider frameworks.
- [ ] Governance code keeps agents as proposal sources only.
- [ ] Driver code exposes capability only, not final authority.
- [ ] Conformance logic lives in `pheroos.conformance`, not CLI glue.
- [ ] `examples/toy-protocol` still validates and passes conformance.
- [ ] `python -m pytest -q` passes.
