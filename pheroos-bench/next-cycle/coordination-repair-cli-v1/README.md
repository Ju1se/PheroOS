# Coordination repair CLI exit contract v1

The collector could retain an aborted campaign and then exit zero. This follow-up changes only the CLI outcome contract and package/config identities; collection, tasks, model, sampling, admission thresholds, statistical methods and budgets are unchanged. Runtime remains `0.1.0.dev3`; protocol-core is unchanged. No new learned-model campaign was run.

| Exit | `cli.status` | Meaning |
| --- | --- | --- |
| 0 | `COMPLETED` | Valid, complete, settled collection. Collaboration may have negative effects or no eligible prefixes. |
| 3 | `NOT_ADMITTED` | Actionability collection is complete and settled, but its existing admission gate does not admit collaboration. This is a valid research observation. |
| 2 | `INVALID_ABORT` | Collection is incomplete, invalid, unmeasured, or has unresolved/violating accounting; also used when required retained status files cannot be read. |

The printed JSON preserves report fields and adds `cli` with profile `coordination_repair_cli_v1`, status and exit code. `main()` returns the code; the actual `python -m` entry point propagates it through `SystemExit`. The CLI reads completion/accounting JSON without rewriting reports, raw records, outcomes or unknown spending. Errors before a report is returned retain Python/argparse's nonzero behavior; they do not promise report JSON. Exit zero does not confer execution authority or replace `validate_actionability()`.

## Validation and scope

The installed subprocess matrix checks admitted and non-admitted diagnostics, negative/null collaboration results, invalid/incomplete observations, unknown accounting, unresolved receipts and missing status artifacts. It verifies exact stdout fields, process exit codes and byte-identical retained files.

A separate installed `python -m` test exercises real collection and CampaignBudget with a synthetic adapter constructor failure. It retains 28 unstarted cells, zero executed episodes, empty model allocations and the predecessor's one reserved intent. Model-library imports are prohibited in this test. Its fixture contains only public model metadata, not weights or model observations.

See [regression receipts](regressions): installed dev3 passed 161 tests and installed dev2 passed 151, with no skips. The accepted wheel is identical in both checks. The full bench passed 1,373 tests plus 12 subtests with no skips; its log is retained separately. These checks establish the CLI boundary, not actionability or coordination efficacy. The historical reference null finding and initial campaign abort remain unchanged.

## Exact package and configuration

Use bench `0.1.1.dev4` from [artifacts/accepted](artifacts/accepted):

```text
pheroos_bench-0.1.1.dev4-py3-none-any.whl
sha256: 19aadbd99992c5baae6f73cad2007b7240a6eb135400436e14c6dd28d88db6c3
```

Its coordination module bytes match the reviewed source. The previous accepted dev3 hash was independently rechecked and remains `bc274b567650d1862a93e4b20e7545ca2e9065aeb1d216ccf8a149df02e7414d`; all old distributions and reports remain intact. Verify earlier source manifests at their bound commits (`9393527...` for v1 and `bc567552...` for v2).

The [unexecuted proposal](pilot-config-proposal.json) is `coordination_repair_local_cycle_v2_cli_v1`, canonical digest `916e2b2f05e32059b2e0ca35e1ce70f9708b8a98059cc40aface055cb86b6193`. Relative to the previous proposal, only `config_version` and `bench_version` change. The combined 500,000-token / 1,000-intent ceilings, retained old intent, 999 new-intent ceiling and 499,712-token maximum allotments remain identical.

To install and verify these exact bytes in an existing Python 3.12 validation environment, use fresh site/output paths:

```sh
python pheroos-bench/tools/verify_coordination_repair_install.py \
  --bench-cohort dev4 --runtime-cohort dev3 \
  --bench-wheel pheroos-bench/next-cycle/coordination-repair-cli-v1/artifacts/accepted/pheroos_bench-0.1.1.dev4-py3-none-any.whl \
  --bench-wheel-sha256 19aadbd99992c5baae6f73cad2007b7240a6eb135400436e14c6dd28d88db6c3 \
  --site /tmp/pheroos-cli-reviewed-site --output /tmp/pheroos-cli-reviewed-install.json
```

The verifier rejects a wrong hash before installation; a version label alone is insufficient. The same accepted wheel was also checked with retained runtime dev2 for legacy compatibility; live collection requires runtime dev3.

The next step remains one explicitly authorized local actionability campaign through `pheroos_bench.coordination_repair_v2_pilot`, using this proposal and a fresh output directory. No API integration, model/task changes, larger agent grid or architectural expansion is part of this fix. Apply the unchanged admission and intervention gates before any collaboration collection. The overall Goal remains incomplete.
