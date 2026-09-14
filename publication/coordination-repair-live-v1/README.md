# Local diagnostic evidence publication

This additive publication preserves the authorized, complete `NOT_ADMITTED` actionability campaign collected from source commit `cbbf105804dca286846771ee7560f245ffcd42e7`. It adds no study-code change or confirmatory sample. Runtime PR #2 remains at `8d5c363c53c2e37e77163877b0a3aed34e0228e9`.

The [phase report](../../pheroos-bench/next-cycle/coordination-repair-live-v1/README.md), all raw JSON/SQLite data, process/CI receipts, independent audit and descriptive exports are stored directly with SHA-256 identities in [manifest.json](manifest.json). No failed episode was excluded. No collaboration or paired effect estimate was collected after the unchanged admission gate failed.

Verify from this publication commit, without opening any SQLite database:

```sh
python pheroos-bench/tools/restore_evidence_v1.py \
  --manifest publication/coordination-repair-live-v1/manifest.json \
  --root . --verify-only
```

The collected source commit and this later evidence publication commit serve different purposes. Old manifests remain bound to their historical commits; no older report is rewritten. A fresh machine can verify all publication bytes without recreating the original absolute paths. Full independent ledger/source audit additionally requires the exact retained execution paths documented in the phase report.
