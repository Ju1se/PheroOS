The publication manifest maps every included original file to its unchanged
bytes, stored directly or in a lossless `.tar.xz` archive. Packaging is not new
experimental evidence and does not count toward a verdict.

From the repository root, with Python 3.10 or later:

```bash
python pheroos-bench/tools/restore_evidence_v1.py --manifest publication/evidence-v1/manifest.json --root . --verify-only
python pheroos-bench/tools/restore_evidence_v1.py --manifest publication/evidence-v1/manifest.json --root .
```

Verification checks all declared file and archive SHA-256 digests and byte
lengths, including original files inside the archives without extracting them.
Archive members must match the manifest exactly; duplicate members, symlinks,
special files and unsafe paths fail. Direct files must exist. Existing restored
files are also checked. Restoration verifies the entire manifest first, then
atomically creates missing files. Matching existing files remain untouched;
different existing bytes cause an explicit failure. Exit 2 and
`INVALID_PUBLICATION` identify verification failures. No SQLite database is
opened, checkpointed or rewritten; no archived code is executed.

The manifest uses `version: "publication_evidence_v1"`, `repository`, a full
`base_commit`, and `counts_toward_verdict: false`. Each `archives` entry contains
`path`, `sha256` and `size_bytes`. Each `files` entry contains those same fields
plus `storage: "direct"` or `"archive"`. Archived entries additionally specify
`archive` and `member`; `member` must exactly equal the original `path`. Paths
are canonical relative POSIX paths. Optional file `mode` is `"100644"` or
`"100755"`; missing restored files receive the corresponding permissions.

This is byte preservation under a trusted published manifest, not a signature,
an evaluator, or a hostile-host security boundary. Run against a quiescent
checkout: concurrent filesystem changes are outside this tool's guarantees.
The filesystem must support atomic hard-link creation for restoration. File
ownership, original timestamps and other filesystem metadata are not restored.
Matching files retain their current metadata. A failure during the write phase
can leave earlier, verified files restored; rerunning safely resumes. No
publication-verification result changes a study's PASS, INVALID or ABORT status.
