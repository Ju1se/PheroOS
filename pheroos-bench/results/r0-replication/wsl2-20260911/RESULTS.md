# G1 / R0 WSL2 replication

Executed 2026-09-11 America/Los_Angeles (2026-09-12 UTC).
**The tested G1 semantics match the published Mac evidence; R0 checks pass.**
This is mock engineering and instrument acceptance, with
`counts_toward_verdict=false` throughout R0.

The [reviewed plan](https://github.com/Ju1se/PheroOS-runtime/blob/e3ef1e8ed0812296601e4a901768af4a1068b5e0/docs/reviewed-plan.md)
and [replication handoff](https://github.com/Ju1se/PheroOS-runtime/blob/e3ef1e8ed0812296601e4a901768af4a1068b5e0/docs/replication.md)
define this bounded execution. Original G1 and R0 reports are preserved.

| Input | Frozen revision |
| --- | --- |
| Runtime implementation | `b3c0d4977c466c02a200d4fe63857682de53ddfd` |
| Core installed for runtime | `b4845e5972e74425af55ad9f306b17535957c68d` |
| R0 source and reference snapshots | `b154472becea561ac1f5fc442a7ccf372ab154f8` |
| Core installed for bench | `4f292de799b01e57bdbb87e915191f310d219579` |

Runtime and bench use separate isolated environments and installed wheels.
The analyzer and runtime implementations match the frozen sources. The new
comparison tool is a separate acceptance check; it does not change those inputs.

| Check | Result |
| --- | --- |
| Installed G1, external working directory | 43 passed in 27.84 s |
| G1 wheel / sdist, independent installations | 43 passed in 27.82 s / 43 passed in 28.56 s |
| Frozen bench suite, including wheel/sdist checks | 203 passed in 5.67 s |
| Bench plus new comparison counterexamples | 217 passed in 5.61 s |
| Stored and fresh R0 self-checks | Both `R0_INSTRUMENT_CHECKS_PASSED` |
| Complete stored R0 report vs historical report | Byte-identical SHA-256 `c64ccda26d570594a78767e4e8c589c4f55fc10485f53949b3d3f5100d8420ba` |
| Fresh runtime semantic comparison | `R0_REPLICATION_PASSED`, no differences |
| Toy and legacy swarm fixtures | Manifest validation and core conformance passed |

The full core pytest run was started, then manually stopped during its lengthy
unrelated TCK checks (exit 130). It is not reported as passing. Core source was
unchanged; the four example checks above and exact G1 core consumer acceptance
completed. The comparison tool and its tests pass Ruff.

| Fresh snapshot | Run status | Actual / reserved / unknown units |
| --- | --- | --- |
| Completed | completed; 13 tasks, result **204** | **26 / 0 / 0** |
| Cancelled after dispatch | cancelled, no artifact | **0 / 1 / 1** |
| Late receipt after cancellation | remains cancelled, no artifact | **1 / 0 / 0** |

The comparison independently recomputes all eight squares, four pair sums and
the final sum. It checks task versions, inputs, dependency/artifact lineage,
authority bindings, each call's Driver digests, publication after receipts and
parent publication before child claim. Cancellation retains the original event
prefix and call identity. Only checked UUIDs, worker identities and independent
task interleavings are normalized; raw snapshot hashes are preserved. Complete
payload/event accounting is 5,789 / 57,460 bytes on this run, matching the stored
counter values; these counters do not measure physical I/O.

The new environment is Ubuntu 24.04.4 / WSL2 x86_64, Python **3.14.7**, SQLite
**3.53.1**, with an **RTX 5070 Laptop GPU, 8,151 MiB, driver 616.92**. GPU identity
was read outside the sandbox because sandbox GPU access was blocked. No CUDA
workload or model inference ran. NumPy **2.5.3** is installed only in bench.
Historical Mac patch and complete development dependency versions are unavailable;
the recorded new package versions are not presented as the original lock.

Evidence: [commands and exit statuses](commands.jsonl),
[package versions](packages.stdout.log), [environment paths](installed-paths.stdout.log),
[GPU query](gpu.json), [source revisions](sources.json),
[G1 install acceptance](g1/g1-install-acceptance.json),
[G1 comparison](g1/g1-semantic-comparison.json),
[stored self-check](stored-snapshot-checks.json),
[fresh self-check](fresh-snapshot-checks.json),
[semantic comparison](semantic-comparison.json),
[fresh snapshot provenance](runtime/provenance.json), and
[evidence hashes](evidence-sha256.json).
Build archives and binary distributions are local rebuildable artifacts;
their hashes are recorded, and they are excluded from version control.

Recheck the captured semantics using an installed bench environment, from
`pheroos-bench/`, with a new output path:

```bash
python tools/compare_r0_replication.py \
  --reference results/r0/runtime \
  --candidate results/r0-replication/wsl2-20260911/runtime \
  --output /tmp/r0-new-semantic-comparison.json
```

Mac remains the correctness reference; WSL2 is now a verified replication
environment for these G1/R0 configurations. R1/R2 require separately frozen
simulation designs. R3/R4 can use WSL2 as the planned primary compute environment
after model, backend, context, concurrency and total-budget manifests are frozen.
Local inference throughput and GPU capacity have not yet been measured. This
replication makes no claim of universal hardware independence or swarm efficacy.
