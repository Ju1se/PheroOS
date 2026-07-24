# Legacy Authority Physical Removal Goal

Status: planned, non-skippable compatibility-exit Goal

Owner: architecture removal decision D-06

This Goal removes the frozen process-local authority registry after its Draft
v1 compatibility window closes. It is separate from WP-05: WP-05 must make all
Stable-candidate and production paths registry-free, while this Goal removes
the compatibility implementation itself. Until every gate below passes, docs
must say “Stable-path legacy exit” and must not say “repository legacy cleanup
complete.”

## Entry conditions

Work may start only after all of these facts are recorded:

1. every v1 issuer/replay surface has a session-bound, StateStore-backed
   replacement or an explicit historical-reader-only disposition;
2. replacement lifecycle metadata and migration fixtures have shipped in at
   least one release candidate;
3. a source, wheel, and sdist consumer audit reports no supported consumer that
   still requires v1 issuance;
4. Stable facades, production profiles, examples, runtime TCKs, and independent
   adapters have zero transitive registry reach; and
5. the declared earliest removal version in the migration contract has been
   reached. The current lower bound is `0.3.0`; it may move later but never
   earlier without an explicit compatibility decision.

Portable historical v1 proof readers may remain only if they are data-only,
registry-free, and cannot issue, refresh, or authorize anything.

## Required work

1. disable every remaining v1 issuer through exact profile/version dispatch;
2. remove the 16 checked registry importers one vertical owner at a time;
3. delete all legacy namespaces, cursors, sentinels, locks, and the registry;
4. retain only registry-free historical codecs/readers required by migration;
5. remove obsolete compatibility exports with lifecycle, changelog, migration,
   and consumer evidence in the same change;
6. regenerate public ABI/lifecycle artifacts only after the reviewed removals;
7. rehearse deletion in a clean subprocess and installed wheel/sdist; and
8. update D-06 from `versioned-deferred` to `removed` only after every gate is
   machine-green.

No module-global dictionary, cursor, lock, singleton, receipt string, digest,
pickle payload, or caller-provided enum may replace the registry as authority.

## Mandatory verification

The completion run must prove:

- legacy authority inventory counts for importers, namespaces, cursors, and
  sentinel-only issuance are all zero;
- source closure and fresh-process probes find no
  `_legacy.authority_registry` import or dynamic load;
- old committed bytes remain inspectable without becoming current authority;
- restart, retry, conflict, stale-parent, cross-scope, retirement, and
  historical-currentness matrices pass for every replacement owner;
- baseline, swarm, Hybrid, local Commit, certified, and distributed behavior
  does not silently downgrade or fall back;
- source, editable install, wheel, and sdist external-CWD consumers agree; and
- the full tests, TCKs, Conformance, ABI, schema, performance, and supply-chain
  gates pass with the registry file physically absent.

## Completion evidence

Completion requires an Evidence Ledger row containing the exact commit/PR,
removed-symbol list, inventory artifact root, consumer-audit result, deletion
rehearsal command, package hashes, and full validation results. Isolation,
deprecation, an empty runtime registry, or zero calls in one test run is not
physical removal.
