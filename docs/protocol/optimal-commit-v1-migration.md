# Optimal Commit Draft ABI Migration

This migration is opt-in. Existing manifests that omit
`collective_commit_policy` keep their current core, swarm, or Hybrid profile
and their existing result/trace behavior.

## Activating Optimal Commit

Add one strict `collective_commit_policy` to the protocol manifest. It must
declare:

- the exact policy/model version and assurance;
- the active target and declared safe fallback candidate;
- evidence, counterevidence, challenge, support-lease, and risk-band rules;
- stability, absolute deadline, reset, and epoch-restart bounds;
- terminal delivery/publication/execution policy;
- certificate mode and, for distributed assurance, the complete fault model.

Activation changes profile precedence. A Commit declaration selects a Commit
profile before legacy swarm profile selection. Hybrid pheromone declarations
remain active as attention checks, but legacy blended swarm scores do not become
commit authority.

## Runtime call sequence

An external runtime should migrate in this order:

1. Load and validate the manifest and selected profile.
2. Create one tenant/run `RuntimeScope`; bind its `scope_ref` to the Kernel,
   Driver, Governance `AuthorityDomain`, store, and scoped Trace path.
3. Obtain governance-issued principal, risk, membership, replay, stop, and
   permission heads.
4. Verify observations, counterevidence dispositions, and challenges.
5. Bind candidate evidence and issue evidence-bound support leases.
6. Issue a `CommitEvaluationContext` and call `assess_optimal_commit(...)`.
7. Run Hybrid memory through `evaluate_hybrid_attention_step(...)` when Hybrid
   exploration is declared.
8. Initialize/advance the commit window with monotonic logical steps.
9. Submit the issued heads to `evaluate_hybrid_commit_step(request=...)`.
10. Prepare the result against the exact scoped Governance head, atomically
    commit state and Trace through a `GovernanceStateStore`, verify its receipt,
    and finalize. `evaluate_and_commit_hybrid_step(...)` is the high-aggregation
    helper for this explicit domain/store sequence. Only `committed` may expose
    durable output authority; stale heads request a retry.
11. When progress is returned, preserve its exact heads and follow
    `next_required_inputs` at the next monotonic step. Re-run the upstream
    qualification path when new evidence is required. Append its replay
    receipts, then issue a new immutable `CommitEvaluationContext` and fresh
    action gates for that current head; never mutate the prior context or
    synthesize a heartbeat for late certificate or distributed-finality input.
12. Treat delivery, publication, and execution as three different decisions.

An unavailable or invalid attention/directive binding is advisory degradation,
not commit degradation. Preserve its structured diagnostic, continue the
independent authority evaluation, and repair attention on a later step if it is
still useful for exploration.

For distributed retries, witnesses sign both the exact proposal digest and the
semantic commit-value root. A new proposal or proof-envelope identifier for the
same value is safe to retry; changing a candidate, claim, output, or authority
root creates a distinct value and can trigger conflict freeze after finality.

The core does not collect agents, schedule retries, call providers, manage
identity keys, or transport witness messages.

## Behavioral changes for opted-in manifests

- Pheromone, recruitment, inhibition, legacy scores, and layer proposals are
  attention only. There is no compatibility conversion from a legacy score to
  evidence.
- Caller booleans do not verify a principal, observation, stop, permission,
  certificate, witness, or prior state.
- Authority-bearing numeric values use bounded fixed-point integers.
- A unique leader must satisfy all risk-adjusted gates for a continuous stable
  window. Candidate identifiers do not break ties.
- The selected assurance cannot fall back to a lower certificate type.
- The absolute deadline cannot be extended by new evidence, attention, leader
  changes, window resets, or finality delay.
- Deadline completion may be a safe fallback, advisory, blocked, invalid,
  finality-unavailable, or safety-violation result. These are terminal outputs,
  not epistemic commits.
- Every governance-issued terminal outcome is deliverable; publish and execute
  require fresh, action-scoped authority. A structurally unusable authority
  envelope still returns an explicit non-authoritative invalid diagnostic
  envelope, but it cannot manufacture a governance-issued outcome.

## Portable consumer changes

Consumers that exchange certificates should use the public payload/from-payload
and verifier functions. Do not pickle process-local governance objects or copy
their private issuance markers. Verify the exact declared profile, output root,
authority leaves, issuer attestations, and, for distributed certificates,
witness attestations and current state before a current action.

Historical trace and outcome records remain append-only. Advancing a current
membership, permission, or distributed-state head can deny a new action without
rewriting the historical decision.

## Conformance and rollout

Before enabling the field in production adapters:

```bash
.venv/bin/python -m pheroos.cli.main validate path/to/capability.json
.venv/bin/python -m pheroos.cli.main conformance path/to/protocol-directory
.venv/bin/python -c \
  'from pheroos.conformance import run_commit_tck; assert run_commit_tck().ok'
.venv/bin/python -m pheroos.cli.main tck run --version v2
```

Run the same TCK from the built wheel and an external working directory. An
active Commit profile must have every required check registered and returning
PASS or FAIL; skip/N/A is not a compatibility result.

Unknown critical fields and versions fail closed. Place non-authoritative
adapter metadata in noncritical extension envelopes; it remains outside commit
roots and cannot grant authority.

New callers should use `evaluate_hybrid_commit_step(request=...)`.
`evaluate_hybrid_commit_evaluation(...)` is a deprecated compatibility alias
scheduled no earlier than the 0.3 Draft removal window.
