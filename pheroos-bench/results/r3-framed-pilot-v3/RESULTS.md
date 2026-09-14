# R3 framed-action pilot v3 results

**The pilot completed and its evidence reconciles. No useful semantic interaction gain was demonstrated; G5 remains incomplete.**

All 20 declared episodes, 120 main calls and 40 probes completed with known costs. The common framing adapter admitted 160/160 responses; 49 main and 20 probe actions passed the unchanged public tool checker. Final hidden evaluation succeeded in 10/20 episodes.

| Arm | Successes / 4 | Main tokens | Probe tokens | Eligible probes | Valid semantic changes |
| --- | ---: | ---: | ---: | ---: | ---: |
| single | 2 | 13,951 | 4,921 | 0 | 0 |
| independent | 2 | 10,846 | 3,851 | 0 | 0 |
| manager_graph | 2 | 11,791 | 3,481 | 5 | 0 |
| blackboard | 2 | 12,806 | 3,633 | 6 | 0 |
| versioned_blackboard | 2 | 12,051 | 3,378 | 6 | 0 |

Actual total usage is **80,709 tokens**, including 45,504 tokens spent on 91 rejected actions. All 40 final durable ledgers retain zero reserved or unknown tokens; rejected actions and failed tasks were retained.

There were 17 forks with eligible current verified artifacts from other agents, and **0 semantic differences with both actions valid**. Probe classifications: `{"invalid_action_in_pair":17,"no_eligible_exact_repeat":23}`. The 23 no-eligible controls repeated text and completion count in 23 cases. Shared-artifact access was exercised, but these observations do not show useful behavioral adaptation or a coordination advantage. Probes are one-step forks; no alternative downstream rollout occurred.

Independent replay checked the complete grid, all original history/context selection and trimming, raw-response normalization and receipt bindings, 229 fresh public-core authority projections, all tool/final/prefix evaluations, 75,293 prompt tokens with the frozen offline tokenizer, all ledger rows and summary arithmetic. It verified 22 frozen source/config/test files, 627 installed artifact hashes, 630 bench-core files and 8 model files. Raw generated token IDs were not stored, so completion-token counts are reconciled to durable receipts and the frozen tensor-length implementation rather than independently reconstructed from decoded text.

Logical accounting retained 800 added processing operations, 2,325,593 processing bytes, 2,774,241 raw transport bytes, 2,599,994 serialized trace/probe bytes and 46,777 tool-receipt bytes. These overlapping stage/storage measures are not independent physical I/O totals or money. Peak measured CUDA tensor allocation was 3,177,662,464 bytes, excluding other device/process memory.

The model remains Qwen/Qwen2.5-Coder-1.5B-Instruct revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`, float16, on RTX 5070 Laptop with PyTorch 2.11.0+cu128, Transformers 4.57.3 and Python 3.12.3. One resident model served logical agents sequentially. CPU wheel/sdist acceptance ran concurrently from 2026-09-13 03:41:20.818771 UTC through 03:43:02.243118 UTC, using separate installation targets and leaving the GPU environment unchanged. The final main trace was written at 2026-09-13T03:41:52.873277+00:00. These file timestamps and the attached acceptance receipt document overlap; they are not an isolated timing instrument. Wall and GPU elapsed numbers must remain descriptive, not a fair latency, throughput or scaling ranking.

This is a separately frozen engineering pilot selected after the v2 format diagnostic, using four previously observed worlds and seed 1073. The earlier failed runs remain unchanged. No held-out or confirmatory evidence, noninferiority test, general model capability claim, R4 scaling result or strategy promotion follows. New tasks, models, parsers or escalation require a separately declared experiment. Runtime development-authority and recovery limitations remain.

Evidence: [frozen inputs](freeze.json), [environment](environment.json), [episodes](episodes.jsonl), [raw main trace](trace.jsonl), [probes](probes.jsonl), [summary](summary.json), [independent audit](independent_audit.json), [audit artifact hashes](independent-audit-hashes.json). The independent audit embeds the CPU acceptance context and source/evidence hashes. It made no new generation calls and did not modify frozen evidence.
