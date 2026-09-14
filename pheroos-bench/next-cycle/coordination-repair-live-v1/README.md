# Local actionability diagnostic v1

**COMPLETE / NOT_ADMITTED.** The authorized local campaign collected all 28 cells with known accounting. The CLI exited **3**, correctly distinguishing a complete negative diagnostic from an infrastructure abort. Collaboration was not run. This pilot contributes no confirmatory evidence and does not complete the Goal.

## Problem and hypothesis

The earlier campaign aborted before inference. This diagnostic asks whether the repaired adapter and CLI can collect actual model actions, whether the fixed local model can submit and solve the tasks, and whether the candidate changes executed work. The coordination hypothesis remains that provenance deduplication, local relevance and version reactivation can reduce redundant interaction without degrading success.

## Mechanism and baselines

The same installed runtime, tools, evaluator, accounting and model serve every cell. D0 gives current evidence and one submission opportunity; D1 gives current evidence and up to four turns; D2 starts without supplied evidence and allows up to eight turns. Two predeclared N=2 blackboard/candidate pairs test actual intervention relevance. The conditionally planned collaboration grid includes single, blackboard/dedup/TTL, candidate and ownership/reuse ablations; that grid remains unmeasured after the failed admission gate.

## Implementation and tests

No study implementation, threshold, model, task, seed or sampling setting changed during collection. Protocol-core and runtime are unchanged. The installed bench `0.1.1.dev4` supplies the already reviewed CLI exit contract, with runtime `0.1.0.dev3` and core `0.1.0`.

Before dispatch, source commit `cbbf105804dca286846771ee7560f245ffcd42e7` passed GitHub CI: 85 successes and one expected PR `provenance` skip, including `quality-gate`, release dry-run and both installed consumer cohorts. See [the exact CI observation](ci-before-dispatch.json). Existing local receipts at [CLI regressions](../coordination-repair-cli-v1/regressions) record 1,373 bench passes plus 12 subtests, and 161/151 installed consumer passes. These are prior engineering checks, not additional model results.

The [independent audit](independent-audit.json) passed 2,983 checks with no findings: 28 isolated SQLite copies match snapshots and aggregate records, token IDs reconcile usage, and independent fixture arithmetic and gate recomputation match the retained results. This proves the audited data relationships, not general robustness.

## Experimental design and identities

- Config: `coordination_repair_local_cycle_v2_cli_v1`; canonical SHA-256 `916e2b2f05e32059b2e0ca35e1ce70f9708b8a98059cc40aface055cb86b6193`. The exact [frozen config](campaign/frozen-config.json) retains all prior thresholds and budgets.
- Model: `Qwen/Qwen2.5-Coder-3B-Instruct`, revision `488639f1ff808d1d3d0ba301aef8c11461451ec5`; manifest SHA-256 `cf4593f14704152d28ea15c6630ee7abaca52580973524a386e05ba217391777`.
- Accepted bench wheel SHA-256: `19aadbd99992c5baae6f73cad2007b7240a6eb135400436e14c6dd28d88db6c3`. [Installed artifacts](installed-artifacts.json) bind all 682 installed wheel members, excluding pip-rewritten RECORD files.
- Eight fixed development worlds in four task families; seed 1729 with the frozen world offsets. 2,048 context tokens, 256 maximum output tokens, sampling temperature 0.7/top-p 0.9/top-k 50. One RTX 5070 Laptop GPU, sequential inference, no paid API or model download. [Preflight](execution-preflight.json) and [hardware observations](hardware-checks.json) retain exact metadata.
- Episode profile `coordination_repair_episode_v2`; CLI profile `coordination_repair_cli_v1`. [Descriptive export](descriptive-export/summary.json) uses `coordination_repair_live_descriptive_v1`. The planned `r_paired_world_mean_v1` and `coordination_repair_nested_forks_v1` retain their meanings; no collaboration effect estimate is emitted for an unrun phase.

## Results

| Condition | Cells | Public-accepted finals | Objective successes | Model calls | Tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| D0 | 8 | 0 | 0 | 8 | 6,711 |
| D1 | 8 | 7 | 2 | 24 | 18,372 |
| D2 | 8 | 3 | 2 | 57 | 28,496 |
| Intervention probes | 4 | 0 | 0 | 24 | 12,083 |

All 28 cells are `VALID_KNOWN`; none are missing, aborted or unresolved. Total usage is **113 model calls, 163 tool calls, 50,076 input + 15,586 output = 65,662 tokens**, with zero unknown calls/tokens. All 28 allocations are terminal. Including the predecessor's retained intent gives **114/1,000 intent slots** and **65,662/500,000 tokens**. The predecessor's three preparation tools remain separate historical work. Monetary cost is unmeasured (`null`), not zero. Control operations total 2,942, so logical `call_units` are **3,218 = 113 + 163 + 2,942**. Process elapsed time was 627.59 seconds, including setup; it is not parallel throughput.

Admission failed: D0 public submission 0/8 versus required 0.75; D0 objective 0/8 versus 0.5; interface rejection **66/89 (74.16%)** versus maximum 0.20; D2 objective 2/8 versus 0.5; D2 successful families 1 versus required 2. The interface denominator is the 24 capability cells' 89 actual returned model actions; probes remain fully counted in total usage. Complete-grid checks and intervention relevance passed. See [unchanged gate results](campaign/actionability/admission.json) and [process exit receipt](actionability-process.json).

## Negative findings

All eight D0 outputs echo the input envelope, reach exactly 256 output tokens, and end with incomplete fenced JSON. Complete single JSON fences are accepted elsewhere in these records; this observation does not identify a fence-parser defect or prove that a larger output cap would fix capability. D1 yields five public-accepted wrong finals; D2 yields one. The only successful family is `version_correction`. Public action acceptance is distinct from objective correctness and is not a Governance commit claim.

Both candidate probes execute one accepted source inspection where their blackboard counterparts execute none. Those receipts reach subsequent agent contexts, so the intervention changes actual work. Neither arm solves either probe. Across the two pairs, candidate tokens are 5,939 versus 6,144, but logical call units are 406 versus 346; model calls are 12 versus 12, tools 14 versus 12, and control operations 380 versus 322. Neither arm demonstrates avoided-inspection reuse or repeated-inspection reduction. These two descriptive pairs do not establish coordination efficacy.

## Known confounds and what was not proven

The worlds are constructed, finite and developmental, not a task-population sample. Fixed source ownership and centrally gathered manifests remain limitations. One sampled local model, one seed schedule, a 256-token output cap and sequential inference confound general claims about model capacity and scaling. Output-cap/envelope observations are post-run diagnostic labels, not preregistered causal endpoints. No stronger-model calibration, collaboration efficacy, sharing benefit, robustness, production readiness or Stable promotion is established. Mailbox is unused: its duplicate rate remains null; repeated prompt exposure is a separate metric.

## Next gate and retained evidence

Stop here under the frozen rule. No collaboration, new model, API integration, task expansion, architecture expansion or automatic retry was performed. Any future experiment needs a separately reviewable, versioned diagnostic decision; these observations do not authorize changing this cohort or reusing its one-campaign authorization. Historical E1/E2/E3, G1/R0 and all earlier configs/results/wheels are unchanged. Earlier preparation reports remain accurate descriptions of their earlier timestamps.

[Raw campaign](campaign) includes every prompt, output, generated token ID, validation response, event, SQLite ledger, snapshot, aggregate and admission/accounting record. [CSV](descriptive-export/episodes.csv) retains all 28 rows, including failed tasks. The operator's [preflight checker correction](preflight-config-check-v1.json) is also preserved: it used the wrong ASCII canonicalization convention before collection; no campaign or model call occurred in that failed helper check.

The retained [launcher](launch.py) records exact original paths and rejects reruns. Do not execute it to inspect data. The read-only audit and export can be reproduced into fresh paths:

```sh
python audit.py --campaign /absolute/path/to/campaign \
  --task-source /absolute/path/to/coordination_repair_v1_tasks.py \
  --output /tmp/fresh-actionability-audit.json
python export.py --root /absolute/path/to/coordination-repair-live-v1 \
  --output /tmp/fresh-actionability-descriptive
```

The audit also verifies original installed source paths and child ledger paths bound in raw records. Those paths must exist unchanged for a full audit; a relocated checkout alone does not recreate the execution environment. No raw paths or hashes are rewritten to make relocated replay pass.
