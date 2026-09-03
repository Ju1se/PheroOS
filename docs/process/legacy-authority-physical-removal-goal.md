# Legacy Authority Physical Removal Goal

Status: completed in the D-06 through D-14 cleanup

Owner: architecture removal decision D-06

The unreleased 0.1.0 package had no external v1 issuers, so the physical
removal gate was exercised immediately. The former registry module and public
compatibility cohort were removed in the bounded D-06 through D-14 cleanup.

## Entry conditions

The cleanup recorded these entry facts:

1. every v1 issuer/replay surface has a session-bound, StateStore-backed
   replacement or an explicit historical-reader-only disposition;
2. replacement lifecycle metadata and migration fixtures have shipped in at
   least one release candidate;
3. a source, wheel, and sdist consumer audit reports no supported consumer that
   still requires v1 issuance;
4. Stable facades, production profiles, examples, runtime TCKs, and independent
   adapters have zero transitive registry reach; and
5. the package remains unreleased (`0.1.0`, no PyPI publication), so no
   external compatibility commitment exists.

Portable historical v1 proof readers may remain only if they are data-only,
registry-free, and cannot issue, refresh, or authorize anything.

## Completed work

1. remove the registry imports from every active owner;
2. delete the registry module and obsolete compatibility exports with lifecycle,
   changelog, migration,
   and consumer evidence in the same change;
3. regenerate public ABI/lifecycle artifacts after the reviewed removals;
4. verify clean imports and source closure; and
5. update D-06 from `versioned-deferred` to `removed`.

No module-global dictionary, cursor, lock, singleton, receipt string, digest,
pickle payload, or caller-provided enum may replace the registry as authority.

## Verification

The cleanup run proves:

- legacy authority inventory reports zero registry importers; remaining
  private cursor/sentinel records are implementation details of non-public
  historical constructors and are not exposed as authority;
- source closure and fresh-process probes find no `_legacy.authority_registry`
  import or dynamic load;
- old committed bytes remain inspectable without becoming current authority;
- restart, retry, conflict, stale-parent, cross-scope, retirement, and
  historical-currentness matrices pass for every replacement owner;
- baseline, scoped replay, local Commit, certified, and distributed behavior
  does not silently downgrade or fall back;
- source and editable-install consumers agree; wheel/sdist external-CWD
  verification remains a release-gate check; and
- ABI/lifecycle generators pass with the registry file physically absent.

## Completion evidence

Completion evidence is recorded in the D-06 through D-14 removal ledger row;
the full test suite remains a separate follow-up because this cleanup is
explicitly bounded to the ABI and compatibility surfaces.
