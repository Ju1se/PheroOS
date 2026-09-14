# V2 retry preparation and validation

This adds the [prepared successor](../../pheroos-bench/next-cycle/coordination-repair-v2/README.md) to the original publication at `9393527fd830aff218b2f41b44438a1aa4136cf3`. It does not execute or authorize another campaign. Read the [proposal status](../../pheroos-bench/next-cycle/coordination-repair-v2/status.json) and [exact proposed configuration](../../pheroos-bench/next-cycle/coordination-repair-v2/pilot-config-proposal.json).

The v2 [manifest](manifest.json) verifies the new source, configuration, engineering build history, accepted wheel, tests and reports. All selected bytes are directly stored in Git. Its own manifest and verification receipt are publication metadata. No model weights, environment caches or credentials are distributed.

```sh
python pheroos-bench/tools/restore_evidence_v1.py --manifest publication/coordination-repair-v2/manifest.json --root . --verify-only
```

The previous publication manifest binds its original commit, including that cohort's `pyproject.toml` and installation CI. Verify it at that commit. This follow-up explicitly advances package metadata and CI to bench `0.1.1.dev3`; all frozen experimental modules, configs, raw results and prior distributions remain unchanged. The retained old wheel and installed legacy-runtime checks preserve reproduction of the previous consumer.

The original abort and reference null finding remain evidence. The v2 preparation is engineering work with zero new live model dispatches; actionability and efficacy remain unmeasured.
