# R1–R5 implementation and complete experimental evidence

Start with the [master empirical report](../../pheroos-bench/results/master-goal-audit-v1/FINAL-REPORT.md) and [final architecture acceptance](../../pheroos-bench/results/master-goal-audit-v1/MASTER-ACCEPTANCE-v1.json). The companion implementation is in [Ju1se/pheroos-runtime](https://github.com/Ju1se/pheroos-runtime), branch `codex/experimental-session-v1-20260913`.

This publication preserves **2,298 original files / 911,628,046 bytes**. 443 source, contract and report files are directly reviewable. The remaining original bytes are contained in 29 lossless tar.xz archives totaling **24,119,272 bytes**. [The manifest](manifest.json) lists every original relative path, SHA-256, byte length, mode and storage location. [Independent review](independent-packaging-review.json) checks both repositories against the original inventories. Compression is a transport representation and adds no experimental sample.

From a fresh repository checkout, restore the original paths before using archived reports, SQLite snapshots, packages or historical audit commands:

```sh
python pheroos-bench/tools/restore_evidence_v1.py --manifest publication/evidence-v1/manifest.json --root . --verify-only
python pheroos-bench/tools/restore_evidence_v1.py --manifest publication/evidence-v1/manifest.json --root .
```

The [restoration contract](RESTORE.md) explains exact verification and explicit `INVALID_PUBLICATION` failures. Restoration never opens SQLite or checkpoints WAL. All R3 database/WAL/SHM triplets, frozen distributions, R4 INVALID/ABORT rows and costs, and the original R5 failed checker audit are retained. Existing different bytes fail rather than being overwritten. Restore only into a quiescent checkout; filesystem timestamps and ownership are not part of byte restoration.

[Validation](validation.json) records full round-trip restoration and the current relevant tests. Earlier reports and commits retain their collection-time wording, source hashes, local absolute paths, version labels and original failures. Statements such as “not pushed” or “pending” in a frozen record describe its creation time; this additive publication does not rewrite them or turn pilots into confirmatory evidence. Absolute host paths may need explicit relocation for replay; original source/config/model identities must remain pinned.

Downloaded third-party model weights, Python environments and caches are excluded from Git. Exact model revisions, file manifests and environment records remain in the data. Frozen wheels/sdists are included even when ordinary ignore rules hid them. No model/provider secrets were found in the selected files; evidence was not redacted or normalized.

No general swarm advantage, success noninferiority, Stable API, production readiness, physical GPU concurrency scaling or long-soak claim follows. Protocol-core is unchanged. These PRs keep runtime infrastructure in its independent repository and research in bench.

The publication uses remote main `053a0d33d72a259d631ba5299e1452c0838aafe9`; the experiments identify their original local base `b154472becea561ac1f5fc442a7ccf372ab154f8`. Current root English/Chinese READMEs and the upstream reviewed plan remain unchanged. The bench README is retained byte-for-byte because the final acceptance binds it; its replacement therefore removes the six-line upstream handoff insertion. The same entry points remain here: [reviewed plan](../../pheroos-bench/docs/reviewed-runtime-plan.md), [external G0/G1 runtime](https://github.com/Ju1se/pheroos-runtime), and [Mac/WSL2 replication guide](https://github.com/Ju1se/pheroos-runtime/blob/main/docs/replication.md).
