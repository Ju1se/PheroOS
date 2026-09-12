## Problem and ownership

- What reproducible problem does this solve?
- Which existing module owns this behavior?
- Why is each new class, file, or public interface necessary? Name its caller.
- Which test proves the user behavior or protocol invariant independently?
- What happens to the previous implementation, and what must consumers migrate?

## Validation

List the commands run and their results, including unresolved failures.
Identify any changed generated artifacts and their source/generator. Explain
any snapshot, threshold, or expected-result change from the problem definition.
Keep unrelated refactoring, protocol changes, and experiments separately
reviewable.

## Protocol-Core Review

- [ ] Public API or ABI impact is described, or this PR has no public API/ABI impact.
- [ ] The current support matrix and module ownership remain accurate; provider/runtime and bench code stay outside the core distribution.
- [ ] Schema changes are reflected in checked-in schema artifacts and schema export tests, or no schema changed.
- [ ] Changelog or migration notes are updated when public behavior changes.
- [ ] Protocol models and validation remain domain-neutral.
- [ ] Kernel code does not import app/runtime/provider frameworks.
- [ ] Governance code keeps agents as proposal sources only.
- [ ] Driver code exposes capability only, not final authority.
- [ ] Conformance logic lives in `pheroos.conformance`, not CLI glue.
- [ ] `examples/toy-protocol` still validates and passes conformance.
- [ ] `examples/e2e-protocol` still validates and passes conformance.
- [ ] Optional contracts pass their selected profiles; private attention fixtures do not imply public swarm support.
- [ ] Relevant package tests and installed-artifact paths pass; full-suite results or limits are reported accurately.
